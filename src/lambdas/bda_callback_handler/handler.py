import json
import os
import boto3
from botocore.exceptions import ClientError # 🚀 ADICIONADO: Importação estável para tratamento de erros
from aws_lambda_powertools import Logger

logger = Logger(service="bda-callback-handler")

db_client = boto3.client("dynamodb", region_name="us-east-1")
sfn_client = boto3.client("stepfunctions", region_name="us-east-1")

TABLE_NAME = os.environ.get("DYNAMODB_TABLE")

def buscar_contexto_token(job_id: str) -> dict:
    """Busca o Task Token e o Package ID associados ao Job ID do Bedrock no DynamoDB."""
    try:
        response = db_client.get_item(
            TableName=TABLE_NAME,
            Key={
                "PK": {"S": f"JOB#{job_id}"},
                "SK": {"S": "METADATA"}
            }
        )
        item = response.get("Item")
        if not item:
            logger.error(f"Nenhum Task Token localizado para o Job ID: {job_id}")
            return {}
            
        return {
            "task_token": item["task_token"]["S"],
            "package_id": item["package_id"]["S"]
        }
    except Exception as e:
        logger.exception(f"Falha de I/O ao interrogar a tabela do DynamoDB: {str(e)}")
        raise e

def handler(event, context):
    try:
        logger.info(f"Evento do EventBridge interceptado com sucesso: {json.dumps(event)}")
        
        detail = event.get("detail", {})
        job_id = detail.get("automationJobId")
        bda_status = detail.get("status")
        output_config = detail.get("outputConfiguration", {})
        
        if not job_id or not bda_status:
            logger.warning("Payload do EventBridge fora do contrato esperado. Abortando execução.")
            return {"statusCode": 400, "body": "Contrato inválido."}
            
        contexto = buscar_contexto_token(job_id)
        if not contexto:
            return {"statusCode": 404, "body": "Task Token não localizado."}
            
        task_token = contexto["task_token"]
        package_id = contexto["package_id"]
        
        logger.info(f"Contexto recuperado. Vinculando Job {job_id} ao Lote {package_id} com status {bda_status}")

        if bda_status == "COMPLETED":
            output_payload = {
                "package_id": package_id,
                "status": "SUCCESS",
                "bda_output_bucket": output_config.get("s3Bucket"),
                "bda_output_prefix": output_config.get("s3Prefix")
            }
            
            logger.info(f"Disparando SendTaskSuccess para acordar o lote {package_id}")
            sfn_client.send_task_success(
                taskToken=task_token,
                output=json.dumps(output_payload)
            )
        else:
            logger.warning(f"O Job do Bedrock falhou na nuvem. Notificando a quebra do lote {package_id}")
            sfn_client.send_task_failure(
                taskToken=task_token,
                error="BedrockDataAutomationFailure",
                cause=f"O processamento assíncrono do BDA falhou com o status: {bda_status}"
            )
            
        return {
            "statusCode": 200,
            "body": json.dumps({"mensagem": "Callback processado e retransmitido com sucesso."})
        }
        
    # 🛡️ CORREÇÃO DA ARMADILHA: Captura via ClientError estável e analisa o código interno da AWS
    except ClientError as e:
        codigo_erro = e.response.get("Error", {}).get("Code")
        if codigo_erro == "TaskDoesNotExist":
            logger.warning("O token fornecido já expirou, foi cancelado ou a execução já avançou na AWS.")
            return {"statusCode": 410, "body": "Task Token expirado ou inexistente."}
        
        logger.exception(f"Erro de infraestrutura gerado pelo SDK da AWS: {str(e)}")
        return {"statusCode": 500, "body": "Erro interno de integração corporativa."}
        
    except Exception as e:
        logger.exception(f"Erro crítico não tratado no barramento de Callback: {str(e)}")
        return {"statusCode": 500, "body": "Erro interno de processamento."}