import json
import os
import boto3
from botocore.exceptions import ClientError
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
        
        detail_type = event.get("detail-type", "")
        detail = event.get("detail", {})
        
        # 🚀 EXTRAÇÃO BLINDADA: Suporta tanto o contrato oficial quanto fallbacks
        raw_job_id = detail.get("job_id") or detail.get("automationJobId") or detail.get("invocationArn", "")
        bda_status = detail.get("job_status") or detail.get("status", "")
        output_s3_location = detail.get("output_s3_location", {})
        
        # Normaliza o ID eliminando paths de ARNs se vier completo
        job_id = raw_job_id.split("/")[-1] if "/" in raw_job_id else raw_job_id
        
        # Linha 50 Corrigida: Agora as variáveis estarão devidamente preenchidas com o log real
        if not job_id or not bda_status:
            logger.warning(f"Payload fora do contrato esperado. job_id: {job_id}, bda_status: {bda_status}. Abortando.")
            return {"statusCode": 400, "body": "Contrato inválido."}
            
        contexto = buscar_contexto_token(job_id)
        if not contexto:
            logger.warning(f"Task Token não localizado no DynamoDB para o job_id: {job_id}")
            return {"statusCode": 404, "body": "Task Token não localizado."}
            
        task_token = contexto["task_token"]
        package_id = contexto["package_id"]
        
        logger.info(f"Contexto localizado. Vinculando Job {job_id} ao Pacote {package_id} com status {bda_status}")

        status_normalizado = bda_status.upper()

        if detail_type == "Bedrock Data Automation Job Succeeded" or status_normalizado in ["SUCCESS", "COMPLETED"]:
            res = db_client.update_item(
                TableName=TABLE_NAME,
                Key={"PK": {"S": package_id}, "SK": {"S": "METADATA"}},
                UpdateExpression="SET bda_pending_jobs = bda_pending_jobs - :one",
                ExpressionAttributeValues={":one": {"N": "1"}},
                ReturnValues="UPDATED_NEW"
            )
            
            jobs_restantes = int(res["Attributes"]["bda_pending_jobs"]["N"])
            logger.info(f"Sub-job processado. Pendentes para o lote {package_id}: {jobs_restantes}")
            
            if jobs_restantes == 0:
                # Extrai o nome limpo do bucket do contrato real do log
                bucket_saida = output_s3_location.get("s3_bucket") or "credifacil-docs-saida-635106763014-dev"

                output_payload = {
                    "package_id": package_id,
                    "status": "SUCCESS",
                    "bda_output_bucket": bucket_saida,
                    "bda_output_prefix": f"bda-output/{package_id}/"
                }
                
                logger.info(f"🏁 Lote {package_id} concluído por completo! Acordando a State Machine.")
                sfn_client.send_task_success(
                    taskToken=task_token,
                    output=json.dumps(output_payload)
                )
        else:
            logger.warning(f"O Job {job_id} reportou falha operacional. Abortando lote {package_id}.")
            sfn_client.send_task_failure(
                taskToken=task_token,
                error="BedrockDataAutomationFailure",
                cause=f"O sub-job {job_id} falhou com status {bda_status}"
            )
            
        return {
            "statusCode": 200,
            "body": json.dumps({"mensagem": "Callback processado com sucesso."})
        }
        
    except ClientError as e:
        codigo_erro = e.response.get("Error", {}).get("Code")
        if codigo_erro == "TaskDoesNotExist":
            logger.warning("O token fornecido já foi processado ou a execução expirou.")
            return {"statusCode": 410, "body": "Task Token expirado."}
        
        logger.exception(f"Erro de SDK na AWS: {str(e)}")
        return {"statusCode": 500, "body": "Erro interno de infraestrutura."}
        
    except Exception as e:
        logger.exception(f"Erro crítico não tratado no barramento: {str(e)}")
        return {"statusCode": 500, "body": "Erro interno."}