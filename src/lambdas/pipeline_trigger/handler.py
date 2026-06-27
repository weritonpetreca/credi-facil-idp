import json
import os
from datetime import datetime, timezone
import boto3
from botocore.exceptions import ClientError  # Importação mandatória para tratamento robusto
from aws_lambda_powertools import Logger

logger = Logger(service="pipeline-trigger")

db_client = boto3.client("dynamodb")
sf_client = boto3.client("stepfunctions")

TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "credifacil-pacotes-dev")
STATE_MACHINE_ARN = os.environ.get("STATE_MACHINE_ARN", "arn:aws:states:us-east-1:123456789012:stateMachine:credifacil-idp-pipeline-dev")

def handler(event, context):
    try:
        body = json.loads(event.get("body", "{}"))
        package_id = body.get("package_id")
        user_id = body.get("user_id", "sistema-anonimo")
        document_count = body.get("document_count", 0)
        
        if not package_id:
            return {"statusCode": 400, "body": json.dumps({"erro": "O campo package_id é obrigatório."})}

        # Correção limpa do datetime sem warnings e compatível com Python 3.12
        timestamp_atual = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        # 1. PERSISTÊNCIA NO DYNAMODB
        item_dynamo = {
            "PK": {"S": package_id},
            "SK": {"S": "METADATA"},
            "status": {"S": "PROCESSING"},
            "uploadedBy": {"S": user_id},
            "uploadedAt": {"S": timestamp_atual},
            "documentCount": {"N": str(document_count)},
            "humanReview": {"BOOL": False}
        }
        
        db_client.put_item(TableName=TABLE_NAME, Item=item_dynamo)
        logger.info(f"Pacote {package_id} registrado no DynamoDB.")

        # 2. DISPARO DO WORKFLOW
        payload_input_step = {
            "package_id": package_id,
            "user_id": user_id,
            "bda_output_bucket": os.environ.get("BUCKET_SAIDA"),
            "bda_output_key": f"bda-output/{package_id}/result.json"
        }
        
        response_sf = sf_client.start_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            name=f"Execution-{package_id}",
            input=json.dumps(payload_input_step)
        )
        
        return {
            "statusCode": 202,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "mensagem": "Pipeline de inteligência iniciado com sucesso.",
                "package_id": package_id,
                "execution_arn": response_sf["executionArn"]
            })
        }

    except ClientError as e:
        # Abordagem padrão AWS: intercepta o código do erro dentro da estrutura do ClientError
        error_code = e.response["Error"]["Code"]
        if error_code == "ExecutionAlreadyExists":
            logger.warning(f"Tentativa de reprocessamento barrada por idempotência: {package_id}")
            return {
                "statusCode": 409,
                "body": json.dumps({"erro": "Este pacote de documentos já está sendo processado."})
            }
        # Se for outro ClientError desconhecido, propaga para o bloco genérico
        raise e
    except Exception as e:
        logger.error(f"Falha catastrófica ao iniciar pipeline: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"erro": "Erro interno ao disparar a esteira."})}