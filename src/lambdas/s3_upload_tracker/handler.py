import json
import os
import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger

logger = Logger(service="s3-upload-tracker")

db_client = boto3.client("dynamodb")
sf_client = boto3.client("stepfunctions")

TABLE_NAME = os.environ.get("DYNAMODB_TABLE")
STATE_MACHINE_ARN = os.environ.get("STATE_MACHINE_ARN")

def handler(event, context):
    try:
        # Extrai o caminho (Key) do objeto criado direto da estrutura do EventBridge
        s3_key = event.get("detail", {}).get("object", {}).get("key", "")
        
        if not s3_key or not s3_key.startswith("packages/"):
            logger.info("Chave do S3 irrelevante para o escopo de rastreamento do pacote.")
            return {"status": "SKIPPED"}

        # Captura o package_id contido no padrão 'packages/{package_id}/{uuid}-filename.pdf'
        partes_caminho = s3_key.split("/")
        package_id = partes_caminho[1]

        logger.info(f"Arquivo recebido no S3. Incrementando progresso do lote {package_id}")

        # 🚀 ATUALIZAÇÃO ATÔMICA: Incrementa o contador e retorna os novos valores em uma única transação
        response = db_client.update_item(
            TableName=TABLE_NAME,
            Key={
                "PK": {"S": package_id},
                "SK": {"S": "METADATA"}
            },
            UpdateExpression="ADD uploadedCount :inc SET lastUploadedKey = :key",
            ExpressionAttributeValues={
                ":inc": {"N": "1"},
                ":key": {"S": s3_key}
            },
            ReturnValues="ALL_NEW"
        )
        
        atributos = response.get("Attributes", {})
        uploaded = int(atributos.get("uploadedCount", {}).get("N", "0"))
        expected = int(atributos.get("documentCount", {}).get("N", "0"))
        status_atual = atributos.get("status", {}).get("S", "")

        logger.info(f"Progresso do pacote {package_id}: {uploaded}/{expected} (Status Atual: {status_atual})")

        # 🏁 SE TODOS OS ARQUIVOS CHEGARAM, APLICA O LOCK OPTIMISTA
        if uploaded == expected and status_atual == "AWAITING_UPLOAD":
            try:
                logger.info(f"Dossiê completo para o pacote {package_id}. Aplicando trava atômica de processamento...")
                
                # Executa uma alteração condicional. Se duas chamadas baterem aqui juntas,
                # apenas uma conseguirá rodar sem estourar ConditionalCheckFailedException
                db_client.update_item(
                    TableName=TABLE_NAME,
                    Key={
                        "PK": {"S": package_id},
                        "SK": {"S": "METADATA"}
                    },
                    UpdateExpression="SET #st = :proc",
                    ConditionExpression="#st = :awaiting",
                    ExpressionAttributeNames={"#st": "status"},
                    ExpressionAttributeValues={
                        ":proc": {"S": "PROCESSING"},
                        ":awaiting": {"S": "AWAITING_UPLOAD"}
                    }
                )
                
                # 🚀 DISPARO AUTOMÁTICO: Inicia a máquina de estados reativamente sem intervenção humana!
                payload_input_step = {
                    "package_id": package_id,
                    "user_id": atributos.get("uploadedBy", {}).get("S", "evento-automatico"),
                    "bda_output_bucket": f"credifacil-docs-saida-{os.environ.get('ENV', 'dev')}",
                    "bda_output_key": f"bda-output/{package_id}/result.json"
                }
                
                logger.info(f"Disparando Step Functions reativamente para o pacote {package_id}...")
                sf_client.start_execution(
                    stateMachineArn=STATE_MACHINE_ARN,
                    name=f"AutoExecution-{package_id}",
                    input=json.dumps(payload_input_step)
                )
                
                return {"status": "TRIGGERED", "package_id": package_id}

            except ClientError as ce:
                if ce.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    logger.warning(f"Trava de concorrência ativada. O pipeline para o pacote {package_id} já foi startado por outra thread.")
                    return {"status": "CONCURRENCY_LOCKED", "package_id": package_id}
                raise ce
                
        return {"status": "WAITING_MORE_FILES", "current_progress": f"{uploaded}/{expected}"}

    except Exception as e:
        logger.error(f"Erro catastrófico no rastreador de uploads S3: {str(e)}")
        raise e