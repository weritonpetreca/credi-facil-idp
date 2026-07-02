import json
import os
import boto3
from aws_lambda_powertools import Logger

logger = Logger(service="customer-consolidator")
s3_client = boto3.client("s3")
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")

def safe_float(val) -> float:
    if val is None: return 0.0
    if isinstance(val, (int, float)): return float(val)
    try:
        limpo = "".join(c for c in str(val) if c.isdigit() or c in [".", ","])
        if "," in limpo and "." in limpo:
            if limpo.rfind(",") > limpo.rfind("."): limpo = limpo.replace(".", "").replace(",", ".")
            else: limpo = limpo.replace(",", "")
        elif "," in limpo: limpo = limpo.replace(",", ".")
        return float(limpo) if limpo else 0.0
    except: return 0.0

def extrair_renda_do_documento(campos: dict, subtipo: str) -> float:
    """Extrai a renda respeitando estritamente os nós complexos e aninhados do blueprint."""
    subtipo_lower = subtipo.lower() if subtipo else ""
    
    if subtipo_lower in ("pay_stub", "comprovante_renda"):
        net_pay = campos.get("net_pay")
        if isinstance(net_pay, dict):
            v = net_pay.get("this_period") or net_pay.get("year_to_date")
            if v: return safe_float(v)
            
        for item in campos.get("earnings", []):
            if isinstance(item, dict):
                gp = item.get("gross_pay", {})
                if isinstance(gp, dict):
                    v = gp.get("this_period")
                    if v: return safe_float(v)
                if item.get("description") == "regular":
                    v = item.get("this_period")
                    if v: return safe_float(v)
                    
    elif subtipo_lower in ("payroll_check", "comprovante_complementar"):
        v = campos.get("amount_numeric")
        if v: return safe_float(v)
        
    elif subtipo_lower == "w2_tax_form":
        v = campos.get("wages_tips_other_compensation")
        if v: return safe_float(v)
        
    return 0.0

def calcular_scorecard_financeiro(validacao: dict, docs_analisados: list) -> dict:
    score_calculado = 300
    motivos_detalhados = []
    
    if validacao.get("nome_consistente_entre_documentos") is True:
        score_calculado += 50
        motivos_detalhados.append("+50: Consistência nominal unificada entre toda a esteira documental.")
    if validacao.get("data_nascimento_consistente") is True:
        score_calculado += 50
        motivos_detalhados.append("+50: Data de nascimento validada e sem divergências cadastrais.")
    if validacao.get("documento_identificacao_presente") is True:
        score_calculado += 50
        motivos_detalhados.append("+50: Documento de identificação oficial regularizado presente.")
        
    renda_maxima = 0.0
    saldo_maximo = 0.0
    
    for doc in docs_analisados:
        tipo = str(doc.get("tipo_documento", "UNKNOWN")).upper()
        subtipo = str(doc.get("subtipo_documento", "")).lower()
        campos = doc.get("dados_extraidos_do_documento") or doc.get("campos_extraidos") or {}
        
        if tipo in ["COMPROVANTE_RENDA", "COMPROVANTE_COMPLEMENTAR", "PAY_STUB", "PAYROLL_CHECK", "W2_TAX_FORM"]:
            renda = extrair_renda_do_documento(campos, subtipo)
            renda_maxima = max(renda_maxima, renda)

        elif tipo in ["EXTRATO_BANCARIO", "BANK_STATEMENT", "ACCOUNT_STATEMENT"]:
            saldo_raw = (campos.get("your_account_balance") or {}).get("closing_balance")
            if not saldo_raw:
                saldo_raw = campos.get("closing_account_balance") or campos.get("saldo_bancario_fechamento") or campos.get("closing_balance") or campos.get("balance")
            if isinstance(saldo_raw, dict): 
                saldo_raw = saldo_raw.get("closing_balance") or saldo_raw.get("value")
            saldo_maximo = max(saldo_maximo, safe_float(saldo_raw))

    if renda_maxima >= 5000.0:
        score_calculado += 450
        motivos_detalhados.append(f"+450: Capacidade de renda líquida elevada comprovada (US$ {renda_maxima:.2f}).")
    elif renda_maxima >= 2500.0:
        score_calculado += 300
        motivos_detalhados.append(f"+300: Capacidade de renda líquida média-alta (US$ {renda_maxima:.2f}).")
    elif renda_maxima >= 1200.0:
        score_calculado += 150
        motivos_detalhados.append(f"+150: Capacidade de renda líquida básica (US$ {renda_maxima:.2f}).")
    else:
        score_calculado += 50
        motivos_detalhados.append("+50: Capacidade de renda em faixa mínima de amortização.")

    if saldo_maximo >= 10000.0:
        score_calculado += 400
        motivos_detalhados.append(f"+400: Excelente liquidez de fechamento patrimonial (US$ {saldo_maximo:.2f}).")
    elif saldo_maximo >= 5000.0:
        score_calculado += 250
        motivos_detalhados.append(f"+250: Liquidez de fechamento estável (US$ {saldo_maximo:.2f}).")
    elif saldo_maximo >= 3000.0:
        score_calculado += 100
        motivos_detalhados.append(f"+100: Colchão de amortização patrimonial mínimo preenchido.")

    return {
        "score_calculado": min(1000, max(300, score_calculado)),
        "motivos_detalhados": motivos_detalhados,
        "renda_maxima": renda_maxima,
        "saldo_maximo": saldo_maximo,
        "classificacao": "baixo" if score_calculado >= 700 else "medio" if score_calculado >= 500 else "alto"
    }

def montar_dossie_executivo(package_id: str, consolidado_json: dict, score: dict, docs_analisados: list) -> dict:
    """Gera um dossiê executivo unificado suportando chaves legadas e novas em paralelo (Multi-Contrato)."""
    import datetime
    
    # Estrutura base original para o front-end renderizar sem quebras
    return {
        "package_id": package_id,
        "status": "COMPLETED",
        "versao_algoritmo": "1.0.0",
        "renda_bruta_estimada": score["renda_maxima"],
        "saldo_bancario_fechamento": score["saldo_maximo"],
        
        # 🚀 RESTAURADO: Mapeamento de 'cliente' original exigido pelo Front-end
        "cliente": {
            "nome": consolidado_json.get("cliente", {}).get("nome"),
            "documento_identificacao": consolidado_json.get("cliente", {}).get("documento_identificacao"),
            "classificacao_risco": consolidado_json.get("cliente", {}).get("classificacao_risco"),
            "score_credito": {
                "valor": score["score_calculado"],
                "motivos": score["motivos_detalhados"],
                "renda_final": score["renda_maxima"],
                "liquidez_final": score["saldo_maximo"]
            }
        },
        "validacao": consolidado_json.get("validacao", {}),
        
        # 🚀 RESTAURADO: Chave original que o query_handler varre para assinar os links S3
        "documentos_analisados": docs_analisados,
        
        # ──────────────────────────────────────────────────────────────
        # Chaves Novas do Dossiê do Clau injetadas em paralelo (Compliance)
        # ──────────────────────────────────────────────────────────────
        "requerente": {
            "nome": consolidado_json.get("cliente", {}).get("nome"),
            "documento_identificacao": consolidado_json.get("cliente", {}).get("documento_identificacao"),
        },
        "sumario_financeiro": {
            "renda_bruta_estimada_usd": score["renda_maxima"],
            "saldo_bancario_fechamento_usd": score["saldo_maximo"],
            "parcela_maxima_estimada_usd": round(score["renda_maxima"] * 0.30, 2),
        },
        "score_credito": {
            "pontuacao": score["score_calculado"],
            "classificacao": score["classificacao"],
            "motivos": score["motivos_detalhados"],
        },
        "validacao_cruzada": consolidado_json.get("validacao", {}),
        "parecer": consolidado_json.get("cliente", {}).get("classificacao_risco", {}).get("justificativa", ""),
        "documentos_processados": [
            {
                "arquivo": doc.get("arquivo_original", ""),
                "tipo": doc.get("tipo_documento", ""),
                "subtipo": doc.get("subtipo_documento", ""),
                "confianca_bda": doc.get("confianca_media", 1.0),
                "s3_json_detalhado": doc.get("s3_key_resultado", "")
            } for doc in docs_analisados
        ],
        "auditoria": {
            "modelo_extracao": "amazon.bedrock.data-automation",
            "modelo_estruturacao": "amazon.nova-lite-v1:0",
            "modelo_consolidacao": "amazon.nova-pro-v1:0",
            "revisao_humana": any(doc.get("status_extracao") == "parcial" for doc in docs_analisados),
            "timestamp_utc": datetime.datetime.utcnow().isoformat() + "Z"
        }
    }

def handler(event, context):
    try:
        package_id = event.get("package_id")
        bucket = event.get("bda_output_bucket") or os.environ.get("BUCKET_SAIDA")
        
        logger.info(f"Iniciando consolidação analítica de score para o pacote {package_id}")

        json_base_lote = event.get("json_estruturado") or {}
        if not json_base_lote or "documentos_analisados" not in json_base_lote:
            key_base = f"results/packages/{package_id}/output.json"
            s3_response = s3_client.get_object(Bucket=bucket, Key=key_base)
            json_base_lote = json.loads(s3_response["Body"].read().decode("utf-8"))

        docs_analisados = [d for d in json_base_lote.get("documentos_analisados", []) if d.get("arquivo_original")]
        dossie_textual = json.dumps(docs_analisados, ensure_ascii=False)

        prompt_consolidacao = f"""
        Você é um analista sênior de risco de crédito. Analise o dossiê de documentos estruturados abaixo para realizar a validação cadastral cruzada do proponente mestre.

        Dossiê de Documentos Estruturados:
        {dossie_textual}

        DIRETRIZES DE CRÉDITO OBRIGATÓRIAS:
        - Mapeie o nome completo e documento civil do proponente baseado nos documentos de identificação oficiais mais confiáveis (ex: Driver License).
        - Classifique a categoria de risco em 'baixo', 'medio' ou 'alto', fornecendo uma justificativa técnica sucinta e fundamentada na saúde patrimonial e financeira demonstrada.
        
        - VALIDAÇÃO ESTRITA DE CONSISTÊNCIA CADASTRAL (REGRAS DE BOOLEANOS):
          * 'nome_consistente_entre_documentos': true se o nome completo do proponente for idêntico em todos os arquivos onde ele foi localizado.
          * 'data_nascimento_consistente': Só pode ser true se a data de nascimento constar de forma explícita e visível em pelo menos um ou mais documentos e não houver divergência. SE A DATA DE NASCIMENTO ESTIVER AUSENTE OU NÃO CONSTAR EM NENHUM DOS DOCUMENTOS DO DOSSIÊ, VOCÊ DEVE OBRIGATORIAMENTE DEFINIR ESTE CAMPO COMO false.

        Retorne RIGOROSAMENTE o formato JSON plano abaixo, sem tags markdown (como ```json) ou qualquer texto complementar explicativo antes ou depois:
        {{
          "cliente": {{
            "nome": "NOME COMPLETO EM CAIXA ALTA",
            "documento_identificacao": "NUMERO",
            "classificacao_risco": {{ "categoria": "baixo", "justificativa": "Texto analítico base do parecer de crédito." }}
          }},
          "validacao": {{
            "nome_consistente_entre_documentos": true,
            "data_nascimento_consistente": false,
            "documento_identificacao_presente": true,
            "comprovante_renda_presente": true,
            "extrato_bancario_presente": true
          }}
        }}
        """

        body_request = json.dumps({
            "inferenceConfig": {"temperature": 0.0, "maxTokens": 1500},
            "messages": [{"role": "user", "content": [{"text": prompt_consolidacao}]}]
        })

        bedrock_response = bedrock_runtime.invoke_model(
            modelId="amazon.nova-pro-v1:0", contentType="application/json", accept="application/json", body=body_request
        )

        response_body = json.loads(bedrock_response["body"].read().decode("utf-8"))
        texto_resposta = response_body["output"]["message"]["content"][0]["text"].strip()
        usage_tokens = response_body.get("usage", {})
        
        if "```json" in texto_resposta:
            texto_resposta = texto_resposta.split("```json")[1].split("```")[0].strip()
        elif "```" in texto_resposta:
            texto_resposta = texto_resposta.split("```")[1].split("```")[0].strip()

        consolidado_json = json.loads(texto_resposta)
        validacao_data = consolidado_json.get("validacao", {})
        
        scorecard_completo = calcular_scorecard_financeiro(validacao_data, docs_analisados)
        
        input_t = int(json_base_lote.get("sistema", {}).get("processamento", {}).get("quantidade_tokens", {}).get("input_tokens", 0)) + usage_tokens.get("inputTokens", 0)
        output_t = int(json_base_lote.get("sistema", {}).get("processamento", {}).get("quantidade_tokens", {}).get("output_tokens", 0)) + usage_tokens.get("outputTokens", 0)

        resumo_docs_enxuto = []
        resumo_docs_completo = []
        
        for doc in docs_analisados:
            tipo = str(doc.get("tipo_documento", "")).lower()
            subtipo = str(doc.get("subtipo_documento", "")).lower()
            campos_brutos = doc.get("dados_extraidos_do_documento") or doc.get("campos_extraidos") or {}
            
            renda_calc = extrair_renda_do_documento(campos_brutos, subtipo)
            
            saldo_calc = (campos_brutos.get("your_account_balance") or {}).get("closing_balance")
            if not saldo_calc:
                saldo_calc = campos_brutos.get("closing_account_balance") or campos_brutos.get("saldo_bancario_fechamento") or campos_brutos.get("closing_balance") or campos_brutos.get("balance")
            if isinstance(saldo_calc, dict):
                saldo_calc = saldo_calc.get("closing_balance") or saldo_calc.get("value")
            saldo_calc = safe_float(saldo_calc)

            base_item_summary = {
                "arquivo_original": doc.get("arquivo_original", ""),
                "tipo_documento": doc.get("tipo_documento", ""),
                "subtipo_documento": doc.get("subtipo_documento", ""),
                "status_extracao": doc.get("status_extracao") or doc.get("confiabilidade_extracao", {}).get("status_extracao", "sucesso"),
                "confianca_media": float(doc.get("confianca_media") or doc.get("confiabilidade_extracao", {}).get("confianca_media", 1.0000)),
                "s3_key_origem": doc.get("s3_key_origem") or doc.get("localizacao_documento_s3", {}).get("s3_key_origem", ""),
                "s3_key_resultado": doc.get("s3_key_resultado") or doc.get("localizacao_documento_s3", {}).get("s3_key_resultado", ""),
                "observacoes": doc.get("observacoes") or doc.get("confiabilidade_extracao", {}).get("observacoes", []),
                "amount_numeric": renda_calc,
                "Gross Pay": renda_calc,
                "wages_tips_other_compensation": renda_calc,
                "saldo_bancario_fechamento": saldo_calc,
                "closing_balance": saldo_calc,
                "balance": saldo_calc
            }

            resumo_docs_enxuto.append(base_item_summary)
            
            item_completo = dict(base_item_summary)
            item_completo["campos_extraidos"] = campos_brutos
            item_completo["dados_extraidos_do_documento"] = campos_brutos
            resumo_docs_completo.append(item_completo)

        # Geração do Dossiê Híbrido Retrocompatível
        report_cliente_dossie = montar_dossie_executivo(package_id, consolidado_json, scorecard_completo, resumo_docs_enxuto)

        # Geração do JSON Mestre Completo (output.json)
        pacote_completo_json = {
            "package_id": package_id,
            "status": "COMPLETED",
            "execute_score": True,
            "bda_output_bucket": bucket,
            "confianca_general": 1,
            "renda_bruta_estimada": scorecard_completo["renda_maxima"],
            "saldo_bancario_fechamento": scorecard_completo["saldo_maximo"],
            "sumario_financeiro": {
                "renda_bruta_estimada": scorecard_completo["renda_maxima"],
                "saldo_bancario_fechamento": scorecard_completo["saldo_maximo"]
            },
            "sistema": {
                "ultimo_package_vinculado": json_base_lote.get("sistema", {}).get("ultimo_package_vinculado", {}),
                "processamento": {
                    "status": "processado",
                    "modelo_utilizado": "Amazon Nova Pro",
                    "bda_project_arn": json_base_lote.get("sistema", {}).get("processamento", {}).get("bda_project_arn"),
                    "quantidade_tokens": {
                        "input_tokens": input_t,
                        "output_tokens": output_t,
                        "total_tokens": input_t + output_t
                    },
                    "data_processamento": json_base_lote.get("sistema", {}).get("processamento", {}).get("data_processamento")
                },
                "tipos_documentos_analisados": json_base_lote.get("sistema", {}).get("tipos_documentos_analisados", [])
            },
            "cliente": report_cliente_dossie["cliente"],
            "validacao": validacao_data,
            "documentos_analisados": resumo_docs_completo
        }

        s3_client.put_object(
            Bucket=bucket, Key=f"results/clientes/{package_id}/customer_consolidated.json",
            Body=json.dumps(report_cliente_dossie, ensure_ascii=False), ContentType="application/json"
        )
        s3_client.put_object(
            Bucket=bucket, Key=f"results/packages/{package_id}/output.json",
            Body=json.dumps(pacote_completo_json, ensure_ascii=False), ContentType="application/json"
        )

        return {
            "package_id": package_id,
            "user_id": event.get("user_id", "sistema"),
            "execute_score": True,
            "bda_output_bucket": bucket,
            "confianca_general": 1,
            "json_estruturado": pacote_completo_json
        }

    except Exception as e:
        logger.error(f"Falha crítica na esteira de consolidação: {str(e)}")
        raise e