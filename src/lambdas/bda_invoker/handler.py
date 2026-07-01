import json
import os
import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger

logger = Logger(service="bda-invoker")

bedrock_client = boto3.client("bedrock-data-automation-runtime", region_name="us-east-1")
s3_client = boto3.client("s3")
# 🚀 ADICIONADO: Inicialização do cliente DynamoDB para persistência do estado do Token
db_client = boto3.client("dynamodb", region_name="us-east-1") 

TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "credifacil-pacotes-dev")

def handler(event, context):
    try:
        package_id = event.get("package_id")
        user_id = event.get("user_id")
        bucket_saida = event.get("bda_output_bucket")
        # 🚀 ADICIONADO: Captura o token de sincronização injetado pela State Machine
        task_token = event.get("task_token") 
        
        prefixo_saida = f"bda-output/{package_id}/"
        bucket_entrada = os.environ.get("BUCKET_ENTRADA")
        prefix_entrada = f"packages/{package_id}/"

        logger.info(f"Listando caminhos de arquivos para processamento paralelo na Lambda: {package_id}")

        s3_objects = s3_client.list_objects_v2(Bucket=bucket_entrada, Prefix=prefix_entrada)
        if "Contents" not in s3_objects or len(s3_objects["Contents"]) == 0:
            raise FileNotFoundError(f"Nenhum documento encontrado na pasta {prefix_entrada}")

        project_arn = os.environ.get("BDA_PROJECT_ARN")
        profile_arn = os.environ.get("BDA_PROFILE_ARN")

        bda_job_ids = []

        for obj in s3_objects["Contents"]:
            key = obj["Key"]
            if key.endswith("/"): 
                continue
                
            nome_arquivo = key.split("/")[-1]
            input_s3_uri = f"s3://{bucket_entrada}/{key}"
            subprefixo_saida = f"{prefixo_saida}{nome_arquivo}/"

            logger.info(f"Disparando Bedrock BDA individual para o documento: {nome_arquivo}")
            
            response = bedrock_client.invoke_data_automation_async(
                inputConfiguration={"s3Uri": input_s3_uri},
                outputConfiguration={"s3Uri": f"s3://{bucket_saida}/{subprefixo_saida}"},
                dataAutomationConfiguration={"dataAutomationProjectArn": project_arn},
                dataAutomationProfileArn=profile_arn,
                notificationConfiguration={
                    "eventBridgeConfiguration": {
                        "eventBridgeEnabled": True
                    }
                }
            )
            
            invocation_arn = response["invocationArn"]
            bda_job_ids.append(invocation_arn)
            
            # Extrai o ID isolado do Job contido no final do ARN da AWS
            job_id = invocation_arn.split("/")[-1]
            
            # 🚀 REQUISITO [RF-02]: Registra a amarração do Job com o Token para o EventBridge ler
            logger.info(f"Persistindo mapeamento criptográfico para o JOB#{job_id}")
            db_client.put_item(
                TableName=TABLE_NAME,
                Item={
                    "PK": {"S": f"JOB#{job_id}"},
                    "SK": {"S": "METADATA"},
                    "task_token": {"S": task_token},
                    "package_id": {"S": package_id}
                }
            )

        # 🚀 REQUISITO [RF-02]: Grava o total de jobs concorrentes para o controle do Callback
        logger.info(f"Atualizando contador de concorrência FinOps para o lote {package_id}")
        db_client.update_item(
            TableName=TABLE_NAME,
            Key={"PK": {"S": package_id}, "SK": {"S": "METADATA"}},
            UpdateExpression="SET bda_pending_jobs = :total",
            ExpressionAttributeValues={
                ":total": {"N": str(len(bda_job_ids))}
            }
        )

        logger.info(f"Sucesso! {len(bda_job_ids)} jobs paralelos rastreados no DynamoDB.")

        return {
            "package_id": package_id,
            "user_id": user_id,
            "bda_job_ids": bda_job_ids,
            "bda_output_bucket": bucket_saida
        }

    except ClientError as e:
        logger.error(f"Falha de comunicação com a API do Bedrock BDA: {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"Erro inesperado no invoker: {str(e)}")
        raise e