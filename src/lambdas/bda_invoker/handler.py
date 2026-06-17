import json
import os
import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger

logger = Logger(service="bda-invoker")

# Inicialização do cliente especializado de runtime do BDA
bedrock_client = boto3.client("bedrock-data-automation-runtime", region_name="us-east-1")

BDA_PROJECT_ID = os.environ.get("BDA_PROJECT_ID", "projeto-credifacil-bda-default")

def handler(event, context):
    try:
        package_id = event.get("package_id")
        user_id = event.get("user_id")
        bucket_saida = event.get("bda_output_bucket")
        prefixo_saida = f"bda-output/{package_id}/"
        
        input_s3_uri = f"s3://credifacil-docs-entrada-{os.environ.get('ENV', 'dev')}/packages/{package_id}/"
        account_id = boto3.client('sts').get_caller_identity()['Account']

        logger.info(f"Iniciando Job assíncrono no BDA para o pacote {package_id}")

        # Dynamic ARNs adequados ao padrão GA do Bedrock
        project_arn = os.environ.get("BDA_PROJECT_ARN")
        profile_arn = f"arn:aws:bedrock:us-east-1:{account_id}:data-automation-profile/us.data-automation-v1"

        # 🚀 CONTRATO ATUALIZADO: Parâmetros mapeados conforme a especificação GA da AWS
        response = bedrock_client.invoke_data_automation_async(
            inputConfiguration={"s3Uri": input_s3_uri},
            outputConfiguration={"s3Uri": f"s3://{bucket_saida}/{prefixo_saida}"},
            dataAutomationConfiguration={
                "dataAutomationProjectArn": project_arn
            },
            dataAutomationProfileArn=profile_arn
        )
        
        job_id = response["automationJobId"]
        logger.info(f"Job BDA criado com sucesso. ID: {job_id}")

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