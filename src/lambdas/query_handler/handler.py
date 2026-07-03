import json
import os
import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger

logger = Logger(service="query-handler")

db_client = boto3.client("dynamodb", region_name="us-east-1")
s3_client = boto3.client("s3", region_name="us-east-1")

TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "credifacil-pacotes-dev")
BUCKET_ENTRADA = os.environ.get("BUCKET_ENTRADA", "credifacil-docs-entrada-dev")
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
        
        failed_fields_metadata = []
        if status == "PROCESSING":
            try:
                rev_response = db_client.get_item(
                    TableName=TABLE_NAME,
                    Key={
                        "PK": {"S": package_id},
                        "SK": {"S": "REVISION"}
                    }
                )
                rev_item = rev_response.get("Item")
                if rev_item and rev_item.get("status_revisao", {}).get("S") == "PENDENTE":
                    status = "NEEDS_REVISION"
                    campos_json = rev_item.get("campos_reprovados_json", {}).get("S", "[]")
                    failed_fields_metadata = json.loads(campos_json)

                    for field in failed_fields_metadata:
                        nome_arquivo = field.get("arquivo")
                        if nome_arquivo:
                            s3_key_origem = f"packages/{package_id}/{nome_arquivo}"
                            try:
                                url_documento = s3_client.generate_presigned_url(
                                    'get_object',
                                    Params={'Bucket': BUCKET_ENTRADA, 'Key': s3_key_origem},
                                    ExpiresIn=900 
                                )
                                field["s3_url_documento_original"] = url_documento
                            except Exception as url_err:
                                logger.warning(f"Não foi possível assinar o documento de origem {nome_arquivo}: {str(url_err)}")

                    logger.info(f"Barreira detectada! Retornando status {status} com {len(failed_fields_metadata)} campos falhos.")
            except Exception as rev_err:
                logger.warning(f"Não foi possível verificar barreira de revisão humana: {str(rev_err)}")
        
        resposta_base = {
            "package_id": package_id,
            "status": status,
            "uploaded_by": uploaded_by,
            "uploaded_at": uploaded_at,
            "human_review": item.get("humanReview", {}).get("BOOL", False) or (status == "NEEDS_REVISION"),
            "confidence_score": float(item.get("confidenceScore", {}).get("N", "0.0")),
            "tokens_consumidos": item.get("tokens_consumidos", {}).get("S", "Não computado"),
            "failed_fields_metadata": failed_fields_metadata,
            "bda_output_bucket": item.get("bda_output_bucket", {}).get("S") or BUCKET_SAIDA
        }

        if status == "COMPLETED" and "resultS3Key" in item:
            s3_key = item["resultS3Key"]["S"]
            logger.info(f"Pacote concluído. Buscando payload estruturado no S3: {s3_key}")
            
            key_completa = s3_key
            key_consolidada = s3_key if "customer_consolidated.json" in s3_key else f"results/clientes/{package_id}/customer_consolidated.json"
            
            if "customer_consolidated.json" in s3_key:
                key_completa = f"results/packages/{package_id}/output.json"
            
            dados_extraidos = {}
            try:
                s3_response = s3_client.get_object(Bucket=BUCKET_SAIDA, Key=key_completa)
                dados_extraidos = json.loads(s3_response["Body"].read().decode("utf-8"))
            except Exception as e:
                logger.warning(f"Não foi possível ler o arquivo mestre {key_completa}, tentando fallback: {str(e)}")
                try:
                    s3_response = s3_client.get_object(Bucket=BUCKET_SAIDA, Key=s3_key)
                    dados_extraidos = json.loads(s3_response["Body"].read().decode("utf-8"))
                except ClientError as s3_err:
                    logger.error(f"Falha de consistência: registro concluído no Dynamo mas ausente no S3: {str(s3_err)}")
                    return {
                        "statusCode": 500,
                        "body": json.dumps({"erro": "Erro de consistência ao recuperar os dados finais do storage."})
                    }
            
            try:
                dados_extraidos["s3_url_consolidado"] = s3_client.generate_presigned_url(
                    'get_object', Params={'Bucket': BUCKET_SAIDA, 'Key': key_consolidada}, ExpiresIn=900
                )
                s3_key_excel_mestre = f"results/planilhas/{package_id}/excel_metadados_customer_consolidated.xlsx"
                dados_extraidos["s3_url_excel_consolidado"] = s3_client.generate_presigned_url(
                    'get_object', Params={'Bucket': BUCKET_SAIDA, 'Key': s3_key_excel_mestre}, ExpiresIn=900
                )
            except Exception as mestre_url_err:
                logger.warning(f"Não foi possível assinar as URLs mestres do lote: {str(mestre_url_err)}")
            
            if "customer_consolidated.json" in s3_key:
                try:
                    s3_res_c = s3_client.get_object(Bucket=BUCKET_SAIDA, Key=key_consolidada)
                    json_c = json.loads(s3_res_c["Body"].read().decode("utf-8"))
                    for k_c in ["cliente", "score_credito", "sumario_financeiro", "validacao", "validacao_cruzada", "parecer", "renda_bruta_estimada", "saldo_bancario_fechamento"]:
                        if k_c in json_c:
                            dados_extraidos[k_c] = json_c[k_c]
                except Exception as merge_err:
                    logger.warning(f"Falha ao realizar merge dinâmico do score do cliente: {str(merge_err)}")

            renda = dados_extraidos.get("renda_bruta_estimada") or dados_extraidos.get("sumario_financeiro", {}).get("renda_bruta_estimada") or 0.0
            saldo = dados_extraidos.get("saldo_bancario_fechamento") or dados_extraidos.get("sumario_financeiro", {}).get("saldo_bancario_fechamento") or 0.0
            
            dados_extraidos["renda_bruta_estimada"] = renda
            dados_extraidos["saldo_bancario_fechamento"] = saldo
            if "sumario_financeiro" not in dados_extraidos:
                dados_extraidos["sumario_financeiro"] = {}
            dados_extraidos["sumario_financeiro"]["renda_bruta_estimada"] = renda
            dados_extraidos["sumario_financeiro"]["saldo_bancario_fechamento"] = saldo

            raw_docs = dados_extraidos.get("documentos_analisados") or dados_extraidos.get("documentos_processados") or []
            normalized_docs = []
            
            for doc in raw_docs:
                if not isinstance(doc, dict): continue
                
                orig_file = doc.get("arquivo_original") or doc.get("arquivo") or ""
                tipo = doc.get("tipo_documento") or doc.get("tipo") or "UNKNOWN"
                subtipo = doc.get("subtipo_documento") or doc.get("subtipo") or "pay_stub"
                s3_key_res = doc.get("s3_key_resultado") or doc.get("s3_json_detalhado")
                conf_media = doc.get("confianca_media") or doc.get("confianca_bda") or 1.0
                status_extracao = doc.get("status_extracao") or doc.get("confiabilidade_extracao", {}).get("status_extracao", "sucesso")
                observacoes = doc.get("observacoes") or doc.get("confiabilidade_extracao", {}).get("observacoes", [])
                campos_internos = doc.get("dados_extraidos_do_documento") or doc.get("campos_extraidos") or {}
                
                if not s3_key_res and orig_file:
                    tipo_lower = str(tipo).lower()
                    subtipo_lower = str(subtipo).lower()
                    s3_key_res = f"results/{tipo_lower}/{subtipo_lower}/{package_id}/{orig_file.replace('.pdf', '')}_structured.json"
                    
                nome_limpo = orig_file.replace(".pdf", "").replace(".png", "").replace(".jpg", "").replace(".jpeg", "")
                s3_key_excel = f"results/planilhas/{package_id}/excel_metadados_{nome_limpo}.xlsx"
                
                try:
                    s3_url_final = s3_client.generate_presigned_url(
                        'get_object', Params={'Bucket': BUCKET_SAIDA, 'Key': s3_key_res}, ExpiresIn=900
                    )
                    s3_url_excel = s3_client.generate_presigned_url(
                        'get_object', Params={'Bucket': BUCKET_SAIDA, 'Key': s3_key_excel}, ExpiresIn=900
                    )
                except Exception as url_err:
                    logger.warning(f"Não foi possível assinar as URLs para o arquivo {orig_file}: {str(url_err)}")
                    s3_url_final = f"https://{BUCKET_SAIDA}.s3.amazonaws.com/{s3_key_res}"
                    s3_url_excel = f"https://{BUCKET_SAIDA}.s3.amazonaws.com/{s3_key_excel}"
                    
                normalized_docs.append({
                    "arquivo_original": orig_file,
                    "tipo_documento": tipo,
                    "subtipo_documento": subtipo,
                    "s3_key_resultado": s3_key_res,
                    "confianca_media": float(conf_media),
                    "status_extracao": status_extracao,
                    "observacoes": observacoes,
                    "s3_url_final": s3_url_final,
                    "s3_url_excel": s3_url_excel,
                    "dados_extraidos_do_documento": campos_internos,
                    "campos_extraidos": campos_internos
                })
                
            dados_extraidos["documentos_analisados"] = normalized_docs
            dados_extraidos["documentos_processados"] = normalized_docs
            resposta_base["dados_extraidos"] = dados_extraidos
            
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