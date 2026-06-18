import json
import os
import boto3
import urllib.parse
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger

logger = Logger(service="s3-upload-tracker")

db_client = boto3.client("dynamodb", region_name="us-east-1")
# 🚀 CORREÇÃO DEFINITIVA: O nome correto do serviço no Boto3 é 'stepfunctions'
sf_client = boto3.client("stepfunctions", region_name="us-east-1")

TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "credifacil-pacotes-dev")
STATE_MACHINE_ARN = os.environ.get("STATE_MACHINE_ARN")

def handler(event, context):
    try:
        logger.info(f"Evento bruto do S3 recebido no Tracker: {json.dumps(event)}")
        
        records = event.get("Records", [])
        if not records:
            logger.warning("Nenhum registro localizado no payload do evento.")
            return {"status": "SKIPPED"}
            
        # Captura e decodifica caracteres especiais e espaços da URL do S3
        raw_key = records[0].get("s3", {}).get("object", {}).get("key", "")
        s3_key = urllib.parse.unquote_plus(raw_key)
        
        # Limpa barras iniciais e espaços que quebram validações de string
        s3_key = s3_key.lstrip("/")
        logger.info(f"Chave S3 higienizada para análise: '{s3_key}'")
        
        # Validação flexível e robusta de escopo
        if not s3_key or "packages/" not in s3_key:
            logger.warning(f"Chave do S3 irrelevante para o escopo de rastreamento do pacote: {s3_key}")
            return {"status": "SKIPPED"}

        # Separa o caminho com segurança: packages/{package_id}/{nome_arquivo}
        partes_caminho = [p for p in s3_key.split("/") if p]
        if len(partes_caminho) < 3:
            logger.warning(f"Estrutura de chave fora do padrão esperado: {s3_key}")
            return {"status": "SKIPPED"}
            
        package_id = partes_caminho[1]
        logger.info(f"Identificado processamento para o lote: {package_id}. Incrementando progresso atômico...")

        # Incremento matemático atômico no DynamoDB
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

        logger.info(f"Contador do pacote {package_id}: {uploaded}/{expected} | Estado atual: {status_atual}")

        # DISPARO AUTOMÁTICO REATIVO: Ativa quando o último arquivo bate no storage
        if uploaded == expected and status_atual == "AWAITING_UPLOAD":
            try:
                # Altera o estado para evitar execuções concorrentes duplicadas
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
                
                payload_input_step = {
                    "package_id": package_id,
                    "user_id": atributos.get("uploadedBy", {}).get("S", "analista-weriton"),
                    "bda_output_bucket": f"credifacil-docs-saida-{os.environ.get('ENV', 'dev')}"
                }
                
                logger.info(f"Lote completo! Disparando Step Functions de forma 100% automatizada para {package_id}")
                sf_client.start_execution(
                    stateMachineArn=STATE_MACHINE_ARN,
                    name=f"AutoExecution-{package_id}",
                    input=json.dumps(payload_input_step)
                )
                return {"status": "TRIGGERED", "package_id": package_id}

            except ClientError as ce:
                if ce.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    logger.warning("Trava de idempotência ativa. O Step Functions já foi startado por outra thread.")
                    return {"status": "CONCURRENCY_LOCKED", "package_id": package_id}
                raise ce
                
        return {"status": "WAITING_MORE_FILES", "progress": f"{uploaded}/{expected}"}

    except Exception as e:
        logger.error(f"Falha crítica no rastreador de uploads S3: {str(e)}")
        raise e