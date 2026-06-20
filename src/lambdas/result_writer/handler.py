import json
import os
import boto3
from datetime import datetime, timezone
from aws_lambda_powertools import Logger

logger = Logger(service="result-writer")
db_client = boto3.client("dynamodb", region_name="us-east-1")

TABLE_PACOTES = os.environ.get("DYNAMODB_TABLE", "credifacil-pacotes-dev")
TABLE_CLIENTES = os.environ.get("CLIENTS_DYNAMODB_TABLE", "credifacil-clientes-dev")

def safe_float(val) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    try:
        limpo = "".join(c for c in str(val) if c.isdigit() or c in [".", ","])
        if "," in limpo and "." in limpo:
            if limpo.rfind(",") > limpo.rfind("."):
                limpo = limpo.replace(".", "").replace(",", ".")
            else:
                limpo = limpo.replace(",", "")
        elif "," in limpo:
            limpo = limpo.replace(",", ".")
        return float(limpo) if limpo else 0.0
    except:
        return 0.0

def handler(event, context):
    """Handler AWS Lambda atuando como Camada de Persistência Inteligente (Smart Writer)."""
    try:
        logger.info(f"Payload de escrita recebido para otimização de CRM: {json.dumps(event)}")
        
        package_id = event.get("package_id")
        json_estruturado = event.get("json_estruturado", {})
        execute_score = event.get("execute_score", False)
        
        timestamp_atual = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        # 🚀 DIRETÓRIO DINÂMICO: Modula o ponteiro final do S3 baseado na flag de execução do Score
        if execute_score:
            s3_key_final = f"results/clientes/{package_id}/customer_consolidated.json"
        else:
            s3_key_final = f"results/{package_id}/output.json"
        
        try:
            confianca_lote = str(float(event.get("confianca_geral", 1.0)))
        except (ValueError, TypeError):
            confianca_lote = "1.0"
            
        decisao_lote = str(event.get("decisao_sugerida") or "revisar")
        
        proc_data = json_estruturado.get("sistema", {}).get("processamento", {})
        tokens_data = proc_data.get("quantidade_tokens", {})
        total_tokens = tokens_data.get("total_tokens", 0)
        tokens_uso = f"{total_tokens} tokens"
        
        # ==========================================================================
        # 📦 1. ATUALIZAÇÃO MESTRE DA TABELA DE PACOTES (Sempre Executa)
        # ==========================================================================
        logger.info(f"Atualizando metadados de ciclo de vida do lote {package_id} para COMPLETED apontando para {s3_key_final}")
        db_client.update_item(
            TableName=TABLE_PACOTES,
            Key={
                "PK": {"S": package_id},
                "SK": {"S": "METADATA"}
            },
            UpdateExpression="SET #st = :comp, processedAt = :ts, resultS3Key = :s3k, confidenceScore = :cs, tokens_consumidos = :tk, decisaoSugerida = :ds",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":comp": {"S": "COMPLETED"},
                ":ts": {"S": timestamp_atual},
                ":s3k": {"S": s3_key_final},
                ":cs": {"N": confianca_lote},
                ":tk": {"S": tokens_uso},
                ":ds": {"S": decisao_lote}
            }
        )
        
        # ==========================================================================
        # 🎯 2. PERSISTÊNCIA REATIVA DO CLIENTE NO CRM (Executa apenas por demanda)
        # ==========================================================================
        cliente_data = json_estruturado.get("cliente") or event.get("cliente")
        
        if execute_score and cliente_data:
            logger.info(f"Gate de Score Ativo (execute_score={execute_score}). Iniciando gravação do Proponente Mestre.")
            
            sistema_data = json_estruturado.get("sistema", {})
            documentos_analisados = json_estruturado.get("documentos_analisados", [])
            
            nome_cliente = cliente_data.get("nome", "Não Identificado")
            pk_cliente = sistema_data.get("chave_cliente") or f"CLIENT#{nome_cliente.replace(' ', '_')}"
            
            renda_maxima_promovida = 0.0
            saldo_maximo_promovido = 0.0
            ledger_documentos_enxuto = []

            for doc in documentos_analisados:
                tipo = str(doc.get("tipo_documento", "UNKNOWN")).upper()
                campos = doc.get("campos_extraidos", {})
                
                if tipo in ["COMPROVANTE_RENDA", "COMPROVANTE_COMPLEMENTAR", "PAY_STUB", "PAYROLL_CHECK", "TAX_DOCUMENT", "W2_TAX_FORM"]:
                    v_renda = campos.get("amount_numeric") or campos.get("Gross Pay") or campos.get("wages_tips_other_compensation") or campos.get("gross_pay_year_to_date") or campos.get("renda_bruta_informada")
                    renda_maxima_promovida = max(renda_maxima_promovida, safe_float(v_renda))
                elif tipo in ["EXTRATO_BANCARIO", "BANK_STATEMENT", "ACCOUNT_STATEMENT"]:
                    v_saldo = campos.get("closing_account_balance") or campos.get("saldo_bancario_fechamento") or campos.get("amount") or campos.get("balance") or campos.get("closing_balance")
                    saldo_maximo_promovido = max(saldo_maximo_promovido, safe_float(v_saldo))

                ledger_documentos_enxuto.append({
                    "tipo_documento": tipo,
                    "arquivo_original": doc.get("arquivo_original", "documento.pdf"),
                    "s3_key_origem": doc.get("s3_key_origem", ""),
                    "s3_key_resultado": doc.get("s3_key_resultado", ""),
                    "status_extracao": doc.get("status_extracao", "sucesso"),
                    "confianca_media": doc.get("confianca_media", 1.0)
                })

            tipo_id = "Não Informado"
            num_id = "Não Informado"
            orgao_emissor = "Não Informado"
            data_emissao = "Não Informada"
            data_validade = "Não Informada"
            
            docs_id_list = cliente_data.get("documentos_identificacao", [])
            if docs_id_list and isinstance(docs_id_list, list) and len(docs_id_list) > 0:
                primer_doc = docs_id_list[0]
                tipo_id = primer_doc.get("tipo_documento") or "Não Informado"
                num_id = primer_doc.get("numero_documento") or "Não Informado"
                orgao_emissor = primer_doc.get("orgao_emissor") or "Não Informado"
                data_emissao = primer_doc.get("data_emissao") or "Não Informada"
                data_validade = primer_doc.get("data_validade") or "Não Informada"
            else:
                num_id = cliente_data.get("documento_identificacao") or "Não Informado"

            score_individuo = cliente_data.get("score_credito", {}).get("valor", 0)
            risco_data = cliente_data.get("classificacao_risco", {})
            risco_individuo = risco_data.get("categoria", "inconclusivo")
            justificativa_individuo = risco_data.get("justificativa", "Sem justificativa cadastrada.")
            
            logger.info(f"Persistindo registro de CRM achatado e otimizado para o cliente: {nome_cliente}")
            
            db_client.put_item(
                TableName=TABLE_CLIENTES,
                Item={
                    "PK": {"S": pk_cliente},
                    "nome_completo": {"S": nome_cliente},
                    "documento_identificacao": {"S": str(num_id)},
                    "tipo_documento_id": {"S": str(tipo_id)},
                    "orgao_emissor": {"S": str(orgao_emissor)},
                    "data_emissao": {"S": str(data_emissao)},
                    "data_validade": {"S": str(data_validade)},
                    "data_nascimento": {"S": cliente_data.get("data_nascimento") or "Não Informada"},
                    "score_atribuido": {"N": str(score_individuo)},
                    "classificacao_risco": {"S": str(risco_individuo).upper() + "_RISK" if risco_individuo in ["baixo", "medio", "alto"] else "UNKNOWN_RISK"},
                    "justificativa_analise": {"S": justificativa_individuo},
                    "renda_bruta_estimada": {"N": str(renda_maxima_promovida)},
                    "saldo_bancario_fechamento": {"N": str(saldo_maxido_promovido)},
                    "documentos_indexados_ledger": {"S": json.dumps(ledger_documentos_enxuto, ensure_ascii=False)},
                    "ultimo_package_vinculado": {"S": package_id},
                    "data_ultima_atualizacao": {"S": timestamp_atual}
                }
            )
        else:
            logger.info(f"Gate de Score Fechado ou Nó Omisso (execute_score={execute_score}). Escrita de cliente ignorada com sucesso.")
            
        return {
            "statusCode": 200,
            "body": json.dumps({
                "package_id": package_id,
                "status": "COMPLETED",
                "score_calculado": execute_score and bool(cliente_data)
            })
        }
        
    except Exception as e:
        logger.error(f"Erro ao persistir na camada de escrita otimizada: {str(e)}")
        raise e