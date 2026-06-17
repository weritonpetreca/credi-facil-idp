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

        logger.info(f"Iniciando busca pelo arquivo real no S3 para o pacote {package_id}")

        # 🔍 SOLUÇÃO 1: Lista a pasta do S3 para capturar o nome real do PDF válido
        s3_objects = s3_client.list_objects_v2(Bucket=bucket_entrada, Prefix=prefix_entrada)
        
        if "Contents" not in s3_objects or len(s3_objects["Contents"]) == 0:
            raise FileNotFoundError(f"Nenhum documento encontrado na pasta {prefix_entrada}")

        # Pega o primeiro arquivo real listado (ignora a estrutura de pastas)
        arquivo_real_key = s3_objects["Contents"][0]["Key"]
        
        # Monta a URI apontando cirurgicamente para o ARQUIVO, e nao para a pasta
        input_s3_uri = f"s3://{bucket_entrada}/{arquivo_real_key}"
        logger.info(f"URI de entrada resolvida com sucesso: {input_s3_uri}")

        project_arn = os.environ.get("BDA_PROJECT_ARN")
        account_id = boto3.client('sts').get_caller_identity()['Account']
        profile_arn = f"arn:aws:bedrock:us-east-1:{account_id}:data-automation-profile/us.data-automation-v1"

        # 🚀 CHAMADA ATUALIZADA: Agora com o ponteiro do arquivo exato
        response = bedrock_client.invoke_data_automation_async(
            inputConfiguration={"s3Uri": input_s3_uri},
            outputConfiguration={"s3Uri": f"s3://{bucket_saida}/{prefixo_saida}"},
            dataAutomationConfiguration={
                "dataAutomationProjectArn": project_arn
            },
            dataAutomationProfileArn=profile_arn
        )
        
        job_id = response["invocationArn"]
        logger.info(f"Job BDA criado com sucesso. ARN de Invocação: {job_id}")

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