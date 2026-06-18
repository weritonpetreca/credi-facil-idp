import json
import os
import boto3
from datetime import datetime
from aws_lambda_powertools import Logger

logger = Logger(service="result-writer")
db_client = boto3.client("dynamodb", region_name="us-east-1")

TABLE_PACOTES = os.environ.get("DYNAMODB_TABLE", "credifacil-pacotes-dev")
TABLE_CLIENTES = os.environ.get("CLIENTS_DYNAMODB_TABLE", "credifacil-clientes-dev")

def safe_float(val) -> float:
    """Converte valores monetários textuais ou mistos vindo da IA em floats puros de forma segura."""
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
    try:
        logger.info(f"Payload de escrita recebido para otimização de CRM: {json.dumps(event)}")
        
        package_id = event.get("package_id")
        json_estruturado = event.get("json_estruturado", {})
        
        timestamp_atual = datetime.utcnow().isoformat() + "Z"
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
        
        # 1. Atualização mestre da tabela de Pacotes (Metadata Log)
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
        
        # 2. INTELIGÊNCIA COMERCIAL: Extração e Agregação Financeira/Cadastral para o CRM
        cliente_data = json_estruturado.get("cliente", {})
        sistema_data = json_estruturado.get("sistema", {})
        documentos_analisados = json_estruturado.get("documentos_analisados", [])
        
        nome_cliente = cliente_data.get("nome", "Não Identificado")
        pk_cliente = sistema_data.get("chave_cliente") or f"CLIENT#{nome_cliente.replace(' ', '_')}"
        
        # Agregação de Perfil Financeiro de primeiro nível
        renda_maxima_promovida = 0.0
        saldo_maximo_promovido = 0.0
        
        # Ledger Enxuto de Documentos (Elimina os 'campos_extraidos' pesados do DynamoDB)
        ledger_documentos_enxuto = []

        for doc in documentos_analisados:
            tipo = doc.get("tipo_documento", "UNKNOWN")
            campos = doc.get("campos_extraidos", {})
            
            # Captura dinâmica e defensiva de indicadores de grana
            if tipo in ["PAY_STUB", "PAYROLL_CHECK", "TAX_DOCUMENT"]:
                v_renda = campos.get("amount_numeric") or campos.get("Gross Pay") or campos.get("gross_pay_year_to_date") or campos.get("renda_bruta_informada")
                renda_maxima_promovida = max(renda_maxima_promovida, safe_float(v_renda))
            elif tipo == "BANK_STATEMENT":
                v_saldo = campos.get("saldo_bancario_fechamento") or campos.get("amount") or campos.get("balance")
                saldo_maximo_promovido = max(saldo_maximo_promovido, safe_float(v_saldo))

            # Constrói a referência física limpa de rastreamento para auditoria
            ledger_documentos_enxuto.append({
                "tipo_documento": tipo,
                "arquivo_original": doc.get("arquivo_original", "documento.pdf"),
                "s3_key_origem": doc.get("s3_key_origem", ""),
                "status_extracao": doc.get("status_extracao", "sucesso"),
                "confianca_media": doc.get("confianca_media", 1.0)
            })

        # Mapeamento isolado de KYC Cadastral Promovido
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
        
        # 3. Escrita Limpa e Indexada no DynamoDB
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
                
                # 🚀 OS NOVOS CAMPOS PROMOVIDOS DE PRIMEIRO NÍVEL: CRM & Front-End Ready!
                "renda_bruta_estimada": {"N": str(renda_maxima_promovida)},
                "saldo_bancario_fechamento": {"N": str(saldo_maximo_promovido)},
                
                # Ledger enxuto stringificado (Apenas ponteiros lógicos, livre de bloat)
                "documentos_indexados_ledger": {"S": json.dumps(ledger_documentos_enxuto, ensure_ascii=False)},
                
                "ultimo_package_vinculado": {"S": package_id},
                "data_ultima_atualizacao": {"S": timestamp_atual}
            }
        )
            
        return {
            "statusCode": 200,
            "body": json.dumps({
                "package_id": package_id,
                "status": "COMPLETED",
                "total_proponentes": 1
            })
        }
        
    except Exception as e:
        logger.error(f"Erro ao persistir na camada de escrita otimizada: {str(e)}")
        raise e