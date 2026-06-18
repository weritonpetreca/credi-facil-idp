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

        logger.info(f"Listando caminhos de arquivos para processamento paralelo na Lambda: {package_id}")

        # 🔍 A Lambda lista os objetos (Aqui o Permission Boundary permite)
        s3_objects = s3_client.list_objects_v2(Bucket=bucket_entrada, Prefix=prefix_entrada)
        if "Contents" not in s3_objects or len(s3_objects["Contents"]) == 0:
            raise FileNotFoundError(f"Nenhum documento encontrado na pasta {prefix_entrada}")

        project_arn = os.environ.get("BDA_PROJECT_ARN")
        account_id = boto3.client('sts').get_caller_identity()['Account']
        profile_arn = f"arn:aws:bedrock:us-east-1:{account_id}:data-automation-profile/us.data-automation-v1"

        bda_job_ids = []

        # 🚀 DISPARO PARALELO: Envia arquivo por arquivo, contornando o erro de ListBucket do Bedrock
        for obj in s3_objects["Contents"]:
            key = obj["Key"]
            if key.endswith("/"): 
                continue
                
            nome_arquivo = key.split("/")[-1]
            input_s3_uri = f"s3://{bucket_entrada}/{key}"
            
            # Isolamos a saída de cada arquivo em uma subpasta dedicada para o Structurer ler depois
            subprefixo_saida = f"{prefixo_saida}{nome_arquivo}/"

            logger.info(f"Disparando Bedrock BDA individual para o documento: {nome_arquivo}")
            
            response = bedrock_client.invoke_data_automation_async(
                inputConfiguration={"s3Uri": input_s3_uri},
                outputConfiguration={"s3Uri": f"s3://{bucket_saida}/{subprefixo_saida}"},
                dataAutomationConfiguration={"dataAutomationProjectArn": project_arn},
                dataAutomationProfileArn=profile_arn
            )
            
            bda_job_ids.append(response["invocationArn"])

        logger.info(f"Sucesso! {len(bda_job_ids)} jobs paralelos foram descentralizados no Amazon Bedrock.")

        return {
            "package_id": package_id,
            "user_id": user_id,
            "bda_job_ids": bda_job_ids,  # Transmite a lista de IDs para o monitor do Step Functions
            "bda_output_bucket": bucket_saida
        }

    except ClientError as e:
        logger.error(f"Falha de comunicação com a API do Bedrock BDA: {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"Erro inesperado no invoker: {str(e)}")
        raise e