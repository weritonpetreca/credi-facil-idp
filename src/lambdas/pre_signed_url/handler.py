import json
import os
import uuid
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timezone
from aws_lambda_powertools import Logger

logger = Logger(service="pre-signed-url")

s3_client = boto3.client("s3", region_name="us-east-1")
db_client = boto3.client("dynamodb", region_name="us-east-1")
TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "credifacil-pacotes-dev")

def mapear_content_type(doc_name: str) -> str:
    extensoes_suportadas = {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp"
    }
    ext = doc_name.lower().split('.')[-1]
    if ext not in extensoes_suportadas:
        raise ValueError(f"Extensão .{ext} inválida para o arquivo {doc_name}. Permitidos: PDF, PNG, JPG, JPEG e WEBP.")
    return extensoes_suportadas[ext]

def gerar_urls_upload(lista_documentos: list[str], package_id: str) -> dict:
    if len(lista_documentos) > 8:
        raise ValueError("O limite máximo permitido é de 8 documentos por pacote.")
        
    urls_geradas = {}
    for doc_name in lista_documentos:
        content_type_dinamico = mapear_content_type(doc_name)
        s3_key = f"packages/{package_id}/{uuid.uuid4()}-{doc_name}"
        
        try:
            url = s3_client.generate_presigned_url(
                ClientMethod="put_object",
                Params={
                    "Bucket": os.environ.get("BUCKET_ENTRADA", "credifacil-docs-entrada-dev"),
                    "Key": s3_key,
                    "ContentType": content_type_dinamico
                },
                ExpiresIn=900
            )
            urls_geradas[doc_name] = {
                "s3Key": s3_key,
                "uploadUrl": url
            }
        except ClientError as e:
            logger.error(f"Erro do SDK S3 ao gerar URL pré-assinada para {doc_name}: {str(e)}")
            raise e
            
    return urls_geradas

def handler(event, context):
    try:
        logger.info(f"Evento recebido na pre_signed_url: {json.dumps(event)}")
        
        body_raw = event.get("body")
        if not body_raw:
            body = {}
        elif isinstance(body_raw, str):
            body = json.loads(body_raw)
        elif isinstance(body_raw, dict):
            body = body_raw
        else:
            body = {}

        documentos = body.get("documentos", [])
        # 🚀 CAPTURA SEGURA: Resgata a intenção de execução de score enviada pelo Front
        execute_score = body.get("execute_score", False)
        
        if not documentos:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"erro": "A lista de documentos não pode estar vazia."})
            }
            
        package_id = str(uuid.uuid4())
        timestamp_atual = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        logger.info(f"Gravando expectativa de {len(documentos)} documentos para o pacote {package_id} com execute_score={execute_score} no DynamoDB")
        
        db_client.put_item(
            TableName=TABLE_NAME,
            Item={
                "PK": {"S": package_id},
                "SK": {"S": "METADATA"},
                "status": {"S": "AWAITING_UPLOAD"},
                "uploadedBy": {"S": "analista-weriton"},
                "uploadedAt": {"S": timestamp_atual},
                "documentCount": {"N": str(len(documentos))},
                "uploadedCount": {"N": "0"},
                "humanReview": {"BOOL": False},
                "execute_score": {"BOOL": execute_score} # 🎯 SALVAMENTO DO CONTRATO: Persiste a flag de forma tipada!
            }
        )
        
        links = gerar_urls_upload(documentos, package_id)
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "package_id": package_id,
                "uploads": links
            })
        }
        
    except ValueError as val_err:
        logger.warning(f"Erro de validação de regras de negócio: {str(val_err)}")
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"erro": str(val_err)})
        }
    except Exception as e:
        logger.exception(f"Falha não tratada na geração de URLs pré-assinadas: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"erro": "Erro interno ao processar."})
        }