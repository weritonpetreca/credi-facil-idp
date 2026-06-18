import json
import os
import uuid
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timezone

s3_client = boto3.client("s3")
# 🚀 NOVO: Cliente do DynamoDB inicializado fora do Handler
db_client = boto3.client("dynamodb")
TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "credifacil-pacotes-dev")

def gerar_urls_upload(lista_documentos: list[str], package_id: str) -> dict:
    if len(lista_documentos) > 8:
        raise ValueError("O limite máximo permitido é de 8 documentos por pacote.")
        
    urls_geradas = {}
    for doc_name in lista_documentos:
        if not doc_name.lower().endswith('.pdf'):
            raise ValueError(f"Extensão inválida para o arquivo {doc_name}. Apenas PDFs são permitidos.")
            
        s3_key = f"packages/{package_id}/{uuid.uuid4()}-{doc_name}"
        
        try:
            url = s3_client.generate_presigned_url(
                ClientMethod="put_object",
                Params={
                    "Bucket": os.environ.get("BUCKET_ENTRADA", "credifacil-docs-entrada-dev"),
                    "Key": s3_key,
                    "ContentType": "application/pdf"
                },
                ExpiresIn=900
            )
            urls_geradas[doc_name] = {
                "s3_key": s3_key,
                "upload_url": url
            }
        except ClientError as e:
            raise e
            
    return urls_geradas

def handler(event, context):
    try:
        body = json.loads(event.get("body", "{}"))
        documentos = body.get("documentos", [])
        
        if not documentos:
            return {
                "statusCode": 400,
                "body": json.dumps({"erro": "A lista de documentos não pode estar vazia."})
            }
            
        package_id = str(uuid.uuid4())
        
        # 🚀 NOVO: Salva a expectativa atômica no banco antes de entregar os links
        timestamp_atual = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
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
                "humanReview": {"BOOL": False}
            }
        )
        
        links = gerar_urls_upload(documentos, package_id)
        
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "package_id": package_id,
                "uploads": links
            })
        }
        
    except ValueError as val_err:
        return {"statusCode": 400, "body": json.dumps({"erro": str(val_err)})}
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"erro": "Erro interno ao processar."})}