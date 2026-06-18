import json
import boto3
from aws_lambda_powertools import Logger

logger = Logger(service="bda-status-poller")
bedrock_client = boto3.client("bedrock-data-automation-runtime", region_name="us-east-1")

def handler(event, context):
    try:
        package_id = event.get("package_id")
        job_ids = event.get("bda_job_ids", [])
        
        # Mantém compatibilidade caso o payload mude de formato
        if not job_ids and event.get("bda_job_id"):
            job_ids = [event.get("bda_job_id")]

        if not job_ids:
            raise ValueError("Nenhum identificador de Job (bda_job_ids) foi localizado no payload.")

        logger.info(f"Avaliando o progresso de {len(job_ids)} sub-jobs ativos no BDA para o pacote {package_id}")

        todos_concluidos = True

        for job_id in job_ids:
            response = bedrock_client.get_data_automation_status(invocationArn=job_id)
            status = response.get("status", "IN_PROGRESS")
            logger.info(f"Sub-job [{job_id}] -> Estado: {status}")

            if status == "FAILED":
                msg_erro = response.get("error", {}).get("message", "Erro não mapeado no motor do BDA")
                return {
                    "status": "FAILED",
                    "package_id": package_id,
                    "errorMessage": f"O processamento do arquivo no Job {job_id} quebrou: {msg_erro}"
                }
            
            if status != "COMPLETED":
                todos_concluidos = False

        if todos_concluidos:
            logger.info("🔥 Malha de processamento concluída! Todos os documentos foram triturados com sucesso.")
            return {
                "status": "COMPLETED",
                "package_id": package_id,
                "bda_output_bucket": event.get("bda_output_bucket"),
                "user_id": event.get("user_id")
            }

        # Se houver arquivo pendente, devolve a lista para manter o loop de espera do Step Functions
        return {
            "status": "IN_PROGRESS",
            "package_id": package_id,
            "bda_job_ids": job_ids,
            "bda_output_bucket": event.get("bda_output_bucket"),
            "user_id": event.get("user_id")
        }

    except Exception as e:
        logger.error(f"Falha ao computar status da malha de sub-jobs: {str(e)}")
        raise e