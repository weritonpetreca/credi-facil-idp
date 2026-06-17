import json
import os
import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger

logger = Logger(service="bda-invoker")

# Inicialização do cliente de controle do Bedrock
bedrock_client = boto3.client('bedrock-data-automation-runtime', region_name='us-east-1')

# Configurações externalizadas via variáveis de ambiente injetadas pelo SAM
BDA_PROJECT_ARN = os.environ.get("BDA_PROJECT_ARN")

def handler(event, context):
    try:
        package_id = event.get("package_id")
        user_id = event.get("user_id")
        
        # S3 caminhos que o Step Functions repassou da Lambda anterior
        bucket_saida = event.get("bda_output_bucket")
        prefixo_saida = f"bda-output/{package_id}/"
        
        # Em produção, o evento conteria a lista exata de URIs S3 dos documentos enviados
        input_s3_uri = f"s3://credifacil-docs-entrada-{os.environ.get('ENV', 'dev')}/packages/{package_id}/"

        logger.info(f"Iniciando Job assíncrono no BDA para o pacote {package_id}")

        # Chamada oficial da API Converse/Data Automation Assíncrona do Bedrock
        response = bedrock_client.invoke_data_automation_async(
            dataAutomationProjectArn=BDA_PROJECT_ARN,
            inputConfiguration={"s3Uri": input_s3_uri},
            outputConfiguration={"s3Uri": f"s3://{bucket_saida}/{prefixo_saida}"}
        )
        
        job_id = response["automationJobId"]
        logger.info(f"Job BDA criado com sucesso. ID: {job_id}")

        # Retorna o ID do Job para que a máquina de estados do Step Functions possa monitorar
        return {
            "package_id": package_id,
            "user_id": user_id,
            "bda_job_id": job_id,
            "bda_output_bucket": bucket_saida,
            "bda_output_key": f"{prefixo_saida}result.json"
        }

    except ClientError as e:
        logger.error(f"Falha de comunicação com a API do Bedrock BDA: {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"Erro inesperado no invoker: {str(e)}")
        raise e