import json
import os
import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger

logger = Logger(service="query-handler")

db_client = boto3.client("dynamodb", region_name="us-east-1")
s3_client = boto3.client("s3", region_name="us-east-1")

TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "credifacil-pacotes-dev")
BUCKET_SAIDA = os.environ.get("BUCKET_SAIDA", "credifacil-docs-saida-dev")

def handler(event, context):
    """Handler AWS Lambda encarregado de buscar metadados do lote e assinar URLs de leitura para o S3."""
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
                dados_extraidos = json.loads(json_completo_content)
                
                # 🚀 ASSINATURA DO COMPONENTE MESTRE: Assina o próprio arquivo consolidado final do lote
                try:
                    presigned_url_mestre = s3_client.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': BUCKET_SAIDA, 'Key': s3_key},
                        ExpiresIn=300
                    )
                    dados_extraidos["s3_url_consolidado"] = presigned_url_mestre
                except Exception as mestre_url_err:
                    logger.warning(f"Não foi possível assinar a URL mestre do lote: {str(mestre_url_err)}")
                
                # 🎯 COMPONENTE ADICIONADO: Se for um fluxo com score, gera a assinatura para a planilha executiva mestre (.xlsx)
                if "clientes" in s3_key:
                    s3_key_excel_mestre = f"results/planilhas/{package_id}/excel_metadados_customer_consolidated.xlsx"
                    try:
                        presigned_url_excel_mestre = s3_client.generate_presigned_url(
                            'get_object',
                            Params={'Bucket': BUCKET_SAIDA, 'Key': s3_key_excel_mestre},
                            ExpiresIn=300
                        )
                        dados_extraidos["s3_url_excel_consolidado"] = presigned_url_excel_mestre
                    except Exception as mestre_excel_err:
                        logger.warning(f"Não foi possível assinar o Excel consolidado mestre: {str(mestre_excel_err)}")

                # ==========================================================================
                # 🔒 GERAÇÃO DE PRE-SIGNED URLS INDIVIDUAIS (Mata o erro 403 do S3)
                # ==========================================================================
                if "documentos_analisados" in dados_extraidos:
                    for doc in dados_extraidos["documentos_analisados"]:
                        s3_key_res = doc.get("s3_key_resultado")
                        orig_file = doc.get("arquivo_original", "")
                        nome_limpo = orig_file.replace(".pdf", "").replace(".png", "").replace(".jpg", "").replace(".jpeg", "")
                        
                        if not s3_key_res:
                            tipo = str(doc.get("tipo_documento", "UNKNOWN")).lower()
                            subtipo = str(doc.get("subtipo_documento", "pay_stub")).lower()
                            s3_key_res = f"results/{tipo}/{subtipo}/{package_id}/{orig_file.replace('.pdf', '')}_structured.json"

                        s3_key_excel = f"results/planilhas/{package_id}/excel_metadados_{nome_limpo}.xlsx"
                        
                        try:
                            doc["s3_url_final"] = s3_client.generate_presigned_url(
                                'get_object', Params={'Bucket': BUCKET_SAIDA, 'Key': s3_key_res}, ExpiresIn=300
                            )
                            doc["s3_url_excel"] = s3_client.generate_presigned_url(
                                'get_object', Params={'Bucket': BUCKET_SAIDA, 'Key': s3_key_excel}, ExpiresIn=300
                            )

                        except Exception as url_err:
                            logger.warning(f"Não foi possível assinar as URLs para o arquivo {orig_file}: {str(url_err)}")
                            doc["s3_url_final"] = f"https://{BUCKET_SAIDA}.s3.amazonaws.com/{s3_key_res}"
                            doc["s3_url_excel"] = f"https://{BUCKET_SAIDA}.s3.amazonaws.com/{s3_key_excel}"
                            
                resposta_base["dados_extraidos"] = dados_extraidos
                
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