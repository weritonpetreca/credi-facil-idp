import os
import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger

logger = Logger(service="bda-status-poller")

# 🚀 CORREÇÃO CRÍTICA 1: Instancia o cliente de runtime correto do Data Automation (GA)
bedrock_client = boto3.client("bedrock-data-automation-runtime", region_name="us-east-1")

def handler(event, context):
    try:
        job_id = event.get("bda_job_id")
        package_id = event.get("package_id")
        
        if not job_id:
            raise ValueError("O parâmetro bda_job_id não foi fornecido no estado do fluxo.")

        logger.info(f"Consultando status do Job BDA via invocationArn para o pacote {package_id}")

        # 🔑 CORREÇÃO CRÍTICA 2: No cliente GA, o método exige 'invocationArn' no lugar de 'automationJobId'
        response = bedrock_client.get_data_automation_status(
            invocationArn=job_id
        )
        
        # Captura o status retornado pela AWS (ex: 'Success', 'InProgress', 'Failed')
        status_bruto = response.get("status", "FAILED")
        logger.info(f"Status bruto retornado pelo Bedrock BDA: {status_bruto}")

        # 🔄 ALINHAMENTO COM A STATE MACHINE: Força a string para caixa alta ('SUCCESS' ou 'FAILED')
        # Isso garante que o Choice State ($.status) no idp_pipeline.json tome a decisão correta
        status_normalizado = status_bruto.upper()
        
        if "ERROR" in status_normalizado or "VALIDATION" in status_normalizado:
            status_normalizado = "FAILED"

        # Injeta o status normalizado na raiz do evento para o Step Functions mapear
        event["status"] = status_normalizado
        event["status_bda"] = status_bruto  # Mantém o original para fins de rastreabilidade
        
        return event

    except ClientError as e:
        logger.error(f"Erro do SDK ao consultar status no Bedrock: {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"Erro inesperado no poller de status: {str(e)}")
        raise e