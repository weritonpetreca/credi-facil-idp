import json
import os
import boto3
from aws_lambda_powertools import Logger

logger = Logger(service="human-review-consumer")
db_client = boto3.client("dynamodb", region_name="us-east-1")

TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "credifacil-pacotes-dev")

def handler(event, context):
    try:
        logger.info(f"Recebido lote de mensagens da fila SQS de Revisão: {json.dumps(event)}")
        
        for record in event.get("Records", []):
            # 1. Desembrulha o SQS Body que contém o JSON do EventBridge
            body = json.loads(record.get("body", "{}"))
            
            # 2. Captura o bloco 'detail' que injetamos no putEvents da State Machine
            detail = body.get("detail", {})
            
            package_id = detail.get("package_id")
            task_token = detail.get("task_token")
            failed_fields = detail.get("failed_fields_metadata", [])
            
            if not package_id or not task_token:
                logger.warning("Mensagem ignorada: package_id ou task_token ausentes no payload.")
                continue
                
            logger.info(f"Processando revisão humana para o pacote {package_id}. Persistindo Token.")
            
            # 3. Salva um registro dedicado isolando a revisão para o front-end consumir
            db_client.put_item(
                TableName=TABLE_NAME,
                Item={
                    "PK": {"S": package_id},
                    "SK": {"S": "REVISION"},
                    "task_token": {"S": task_token},
                    "status_revisao": {"S": "PENDENTE"},
                    "campos_reprovados_json": {"S": json.dumps(failed_fields, ensure_ascii=False)},
                    "total_campos_falhos": {"N": str(len(failed_fields))}
                }
            )
            logger.info(f"Sucesso! Registro REVISION persistido para o pacote {package_id}")
            
        return {"statusCode": 200, "body": "Lote SQS de revisão processado."}
        
    except Exception as e:
        logger.error(f"Erro crítico ao consumir mensagens da fila de revisão: {str(e)}")
        raise e