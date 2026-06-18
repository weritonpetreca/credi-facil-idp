import json
import os
import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger

logger = Logger(service="bda-invoker")

bedrock_client = boto3.client("bedrock-data-automation-runtime", region_name="us-east-1")
s3_client = boto3.client("s3")

def handler(event, context):
    try:
        package_id = event.get("package_id")
        user_id = event.get("user_id")
        bucket_saida = event.get("bda_output_bucket")
        prefixo_saida = f"bda-output/{package_id}/"
        
        bucket_entrada = f"credifacil-docs-entrada-{os.environ.get('ENV', 'dev')}"
        prefix_entrada = f"packages/{package_id}/"

        logger.info(f"Iniciando orquestração em lote do BDA para o pacote: {package_id}")

        # 🚀 CORREÇÃO CIRÚRGICA: Apontamos para a PASTA (prefixo) e não mais para o index [0].
        # O Bedrock Data Automation vai varrer e processar todos os 6 PDFs do diretório em paralelo.
        input_s3_uri = f"s3://{bucket_entrada}/{prefix_entrada}"
        logger.info(f"URI de lote configurada para o BDA: {input_s3_uri}")

        project_arn = os.environ.get("BDA_PROJECT_ARN")
        account_id = boto3.client('sts').get_caller_identity()['Account']
        profile_arn = f"arn:aws:bedrock:us-east-1:{account_id}:data-automation-profile/us.data-automation-v1"

        # Chamada assíncrona passando o ponteiro da pasta completa
        response = bedrock_client.invoke_data_automation_async(
            inputConfiguration={"s3Uri": input_s3_uri},
            outputConfiguration={"s3Uri": f"s3://{bucket_saida}/{prefixo_saida}"},
            dataAutomationConfiguration={
                "dataAutomationProjectArn": project_arn
            },
            dataAutomationProfileArn=profile_arn
        )
        
        job_id = response["invocationArn"]
        logger.info(f"Job BDA em Lote criado com sucesso. ARN de Invocação: {job_id}")

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