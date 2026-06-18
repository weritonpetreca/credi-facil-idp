import json
import boto3
from aws_lambda_powertools import Logger

logger = Logger(service="bda-status-poller")
bedrock_client = boto3.client("bedrock-data-automation-runtime", region_name="us-east-1")

def handler(event, context):
    try:
        package_id = event.get("package_id")
        job_ids = event.get("bda_job_ids", [])
        
        if not job_ids and event.get("bda_job_id"):
            job_ids = [event.get("bda_job_id")]

        if not job_ids:
            raise ValueError("Nenhum identificador de Job (bda_job_ids) foi localizado no payload.")

        logger.info(f"Avaliando o progresso de {len(job_ids)} sub-jobs ativos no BDA para o pacote {package_id}")

        todos_concluidos = True

        for job_id in job_ids:
            response = bedrock_client.get_data_automation_status(invocationArn=job_id)
            
            # Log do payload bruto para auditoria caso necessário no CloudWatch
            logger.info(f"Resposta bruta do Bedrock para o job {job_id}: {json.dumps(response)}")
            
            # 🚀 CORREÇÃO CIRÚRGICA: Captura insensível a caixa para chaves do Boto3 (Status ou status)
            raw_status = response.get("Status") or response.get("status") or "IN_PROGRESS"
            status_upper = str(raw_status).upper()
            
            logger.info(f"Sub-job [{job_id}] -> Estado extraído e normalizado: {status_upper}")

            # Validação elástica para estados de falha
            if status_upper in ["FAILED", "ERROR"]:
                msg_erro = (
                    response.get("Error", {}).get("Message") or 
                    response.get("error", {}).get("message", "Erro interno BDA")
                )
                return {
                    "status": "FAILED",
                    "package_id": package_id,
                    "errorMessage": f"O processamento do arquivo no Job {job_id} quebrou: {msg_erro}"
                }
            
            # Só consideramos aceitável o avanço se bater em um dos ranges de sucesso estáveis
            if status_upper not in ["COMPLETED", "SUCCESS", "SUCCESSFUL"]:
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