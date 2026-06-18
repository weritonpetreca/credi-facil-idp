import json
import os
import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger

logger = Logger(service="query-handler")

# 🚀 CORREÇÃO CIRÚRGICA: Força a região us-east-1 para garantir o alinhamento com o ecossistema do lote
db_client = boto3.client("dynamodb", region_name="us-east-1")
s3_client = boto3.client("s3", region_name="us-east-1")

TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "credifacil-pacotes-dev")
BUCKET_SAIDA = os.environ.get("BUCKET_SAIDA", "credifacil-docs-saida-dev")

def handler(event, context):
    try:
        path_parameters = event.get("pathParameters") or {}
        package_id = path_parameters.get("packageId")
        
        if not package_id:
            return {
                "statusCode": 400,
                "body": json.dumps({"erro": "O parâmetro packageId na URL é obrigatório."})
            }

        logger.info(f"Buscando metadados do pacote {package_id} no DynamoDB regional.")

        db_response = db_client.get_item(
            TableName=TABLE_NAME,
            Key={
                "PK": {"S": package_id},
                "SK": {"S": "METADATA"}
            }
        )
        
        item = db_response.get("Item")
        if not item:
            return {
                "statusCode": 404,
                "body": json.dumps({"erro": f"Solicitação de pacote {package_id} não localizada."})
            }

        status = item.get("status", {}).get("S", "UNKNOWN")
        uploaded_by = item.get("uploadedBy", {}).get("S", "sistema")
        uploaded_at = item.get("uploadedAt", {}).get("S", "")
        
        resposta_base = {
            "package_id": package_id,
            "status": status,
            "uploaded_by": uploaded_by,
            "uploaded_at": uploaded_at,
            "human_review": item.get("humanReview", {}).get("BOOL", False),
            "confidence_score": float(item.get("confidenceScore", {}).get("N", "0.0")),
            "tokens_consumidos": item.get("tokens_consumidos", {}).get("S", "Não computado")
        }

        if status == "COMPLETED" and "resultS3Key" in item:
            s3_key = item["resultS3Key"]["S"]
            logger.info(f"Pacote concluído. Buscando payload estruturado no S3: {s3_key}")
            
            try:
                s3_response = s3_client.get_object(Bucket=BUCKET_SAIDA, Key=s3_key)
                json_completo_content = s3_response["Body"].read().decode("utf-8")
                resposta_base["dados_extraidos"] = json.loads(json_completo_content)
            except ClientError as s3_err:
                logger.error(f"Falha de consistência: registro concluído no Dynamo mas ausente no S3: {str(s3_err)}")
                return {
                    "statusCode": 500,
                    "body": json.dumps({"erro": "Erro de consistência ao recuperar os dados finais do storage."})
                }

        elif status == "FAILED" and "errorMessage" in item:
            resposta_base["erro_processamento"] = item["errorMessage"]["S"]

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps(resposta_base, ensure_ascii=False)
        }

    except Exception as e:
        logger.error(f"Falha ao processar consulta GET: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"erro": "Erro interno ao processar a consulta."})
        }