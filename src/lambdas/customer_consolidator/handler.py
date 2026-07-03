import json
import os
import datetime
import boto3
from aws_lambda_powertools import Logger

logger = Logger(service="customer-consolidator")
s3_client = boto3.client("s3")
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")

MODEL_ID = "amazon.nova-lite-v1:0"

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
    """Aplica o scorecard de crédito blindado contra bônus em faixas de renda nula."""
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
    elif renda_maxima > 0.0:
        score_calculado += 50
        motivos_detalhados.append(f"+50: Capacidade de renda em faixa mínima de amortização (US$ {renda_maxima:.2f}).")
    else:
        motivos_detalhados.append("+0: Nenhuma renda comprovada ou identificada nos documentos analisados.")

    if saldo_maximo >= 10000.0:
        score_calculado += 400
        motivos_detalhados.append(f"+400: Excelente liquidez de fechamento patrimonial (US$ {saldo_maximo:.2f}).")
    elif saldo_maximo >= 5000.0:
        score_calculado += 250
        motivos_detalhados.append(f"+250: Liquidez de fechamento estável (US$ {saldo_maximo:.2f}).")
    elif saldo_maximo >= 3000.0:
        score_calculado += 100
        motivos_detalhados.append(f"+100: Colchão de amortização patrimonial mínimo preenchido (US$ {saldo_maximo:.2f}).")
    else:
        motivos_detalhados.append("+0: Nenhum saldo bancário expressivo ou identificado nos extratos.")

    return {
        "score_calculado": min(1000, max(300, score_calculado)),
        "motivos_detalhados": motivos_detalhados,
        "renda_maxima": renda_maxima,
        "saldo_maximo": saldo_maximo,
        "classificacao": "baixo" if score_calculado >= 700 else "medio" if score_calculado >= 500 else "alto"
    }

def montar_dossie_executivo(package_id: str, consolidado_json: dict, score: dict, docs_analisados: list) -> dict:
    """Gera o dossiê leve exclusivo para cruzamento de dados e auditoria de score."""
    return {
        "package_id": package_id,
        "status": "COMPLETED",
        "versao_algoritmo": "1.0.0",
        "renda_bruta_estimada": score["renda_maxima"],
        "saldo_bancario_fechamento": score["saldo_maximo"],
        "cliente": {
            "nome": consolidado_json.get("cliente", {}).get("nome") or "NAO INFORMADO",
            "documento_identificacao": consolidado_json.get("cliente", {}).get("documento_identificacao") or "NAO INFORMADO",
            "classificacao_risco": consolidado_json.get("cliente", {}).get("classificacao_risco"),
            "score_credito": {
                "valor": score["score_calculado"],
                "motivos": score["motivos_detalhados"],
                "renda_final": score["renda_maxima"],
                "liquidez_final": score["saldo_maximo"]
            }
        },
        "validacao": consolidado_json.get("validacao", {}),
        "requerente": {
            "nome": consolidado_json.get("cliente", {}).get("nome") or "NAO INFORMADO",
            "documento_identificacao": consolidado_json.get("cliente", {}).get("documento_identificacao") or "NAO INFORMADO",
        },
        "sumario_financeiro": {
            "renda_bruta_estimada": score["renda_maxima"],
            "saldo_bancario_fechamento": score["saldo_maximo"],
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
            "modelo_consolidacao": MODEL_ID,
            "revisao_humana": any(doc.get("status_extracao") == "parcial" for doc in docs_analisados),
            "timestamp_utc": datetime.datetime.utcnow().isoformat() + "Z"
        }
    }

def obter_especificacao_ferramenta_consolidacao():
    """Garante o contrato JSON estrito via Tool Calling para a Nova Lite."""
    return {
        "name": "consolidar_e_validar_dados_esteira",
        "description": "Consolida a validação cadastral cruzada e a análise de risco do proponente.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "cliente": {
                        "type": "object",
                        "properties": {
                            "nome": {"type": "string", "description": "Nome completo do proponente em CAIXA ALTA."},
                            "documento_identificacao": {"type": "string", "description": "Número do documento de identificação civil."},
                            "classificacao_risco": {
                                "type": "object",
                                "properties": {
                                    "categoria": {"type": "string", "enum": ["baixo", "medio", "alto"]},
                                    "justificativa": {"type": "string", "description": "Texto sucinto e analítico do parecer técnico de crédito."}
                                },
                                "required": ["categoria", "justificativa"]
                            }
                        },
                        "required": ["nome", "documento_identificacao", "classificacao_risco"]
                    },
                    "validacao": {
                        "type": "object",
                        "properties": {
                            "nome_consistente_entre_documentos": {"type": "boolean"},
                            "data_nascimento_consistente": {"type": "boolean"},
                            "documento_identificacao_presente": {"type": "boolean"},
                            "comprovante_renda_presente": {"type": "boolean"},
                            "extrato_bancario_presente": {"type": "boolean"}
                        },
                        "required": ["nome_consistente_entre_documentos", "data_nascimento_consistente", "documento_identificacao_presente"]
                    }
                },
                "required": ["cliente", "validacao"]
            }
        }
    }

def handler(event, context):
    try:
        package_id = event.get("package_id")
        bucket = event.get("bda_output_bucket") or os.environ.get("BUCKET_SAIDA")
        execute_score = event.get("execute_score", False)
        
        logger.info(f"Iniciando consolidação analítica de score para o pacote {package_id}")

        json_base_lote = event.get("json_estruturado") or {}
        if not json_base_lote or "documentos_analisados" not in json_base_lote:
            key_base = f"results/packages/{package_id}/output.json"
            s3_response = s3_client.get_object(Bucket=bucket, Key=key_base)
            json_base_lote = json.loads(s3_response["Body"].read().decode("utf-8"))

        # Desembrulha o contrato híbrido vindo do Map/Aggregator
        raw_docs = json_base_lote.get("documentos_analisados", [])
        docs_analisados = []
        for d in raw_docs:
            if isinstance(d, dict) and "blueprint" in d and isinstance(d["blueprint"], dict):
                doc_obj = d["blueprint"]
            else:
                doc_obj = d
                
            if isinstance(doc_obj, dict) and doc_obj.get("arquivo_original"):
                docs_analisados.append(doc_obj)

        # 🚀 TELEMETRIA: Resgata tokens base acumulados nas Lambdas anteriores
        tokens_base = json_base_lote.get("sistema", {}).get("processamento", {}).get("quantidade_tokens", {})
        input_t = int(tokens_base.get("input_tokens", 0))
        output_t = int(tokens_base.get("output_tokens", 0))

        consolidado_json = {}
        scorecard_completo = {
            "score_calculado": 300, "motivos_detalhados": ["Scorecard não executado por demanda do fluxo."],
            "renda_maxima": 0.0, "saldo_maximo": 0.0, "classificacao": "alto"
        }
        report_cliente_dossie = {}

        # ==========================================================================
        # 🎯 BLOCO REATIVO: EXECUTA O SCORE E O TOOL CALLING CASO SOLICITADO
        # ==========================================================================
        if execute_score and docs_analisados:
            logger.info("Gate de Score Ativo. Disparando Tool Calling na Nova Lite.")
            dossie_textual = json.dumps(docs_analisados, ensure_ascii=False)

            prompt_sistema_consolidacao = """
            Você é um analista sênior de risco de crédito. Analise o dossiê de documentos estruturados fornecido para realizar a validação cadastral cruzada do proponente mestre.
            Sua resposta deve ser obrigatoriamente despachada através do acionamento da ferramenta 'consolidar_e_validar_dados_esteira'.
            Regra Estrita de Negócio: O campo 'data_nascimento_consistente' só pode ser marcado como true se a data constar explicitamente em algum documento de identificação oficial. Se estiver omissa, defina como false.
            """

            tool_config = {
                "tools": [obter_especificacao_ferramenta_consolidacao()],
                "toolChoice": {"tool": {"name": "consolidar_e_validar_dados_esteira"}}
            }

            response = bedrock_runtime.converse(
                modelId=MODEL_ID,
                messages=[{"role": "user", "content": [{"text": f"Dossiê de Documentos:\n{dossie_textual}"}]}],
                system=[{"text": prompt_sistema_consolidacao}],
                toolConfig=tool_config,
                inferenceConfig={"temperature": 0.0, "maxTokens": 1500}
            )

            usage_tokens = response.get("usage", {})
            input_t += usage_tokens.get("inputTokens", 0)
            output_t += usage_tokens.get("outputTokens", 0)

            content_blocks = response.get("output", {}).get("message", {}).get("content", [])
            tool_use_block = next((b["toolUse"] for b in content_blocks if "toolUse" in b), None)
            
            if not tool_use_block:
                raise ValueError("A Nova Lite falhou ao tentar acionar a ferramenta de validação cruzada.")

            consolidado_json = tool_use_block.get("input", {})
            if isinstance(consolidado_json, str): 
                consolidado_json = json.loads(consolidado_json)

            validacao_data = consolidado_json.get("validacao", {})
            scorecard_completo = calcular_scorecard_financeiro(validacao_data, docs_analisados)

        # ==========================================================================
        # 📦 CONSTRUÇÃO DA LISTA INTEGRAL PARA O OUTPUT.JSON (Sem perder nenhum campo)
        # ==========================================================================
        resumo_docs_completo = []
        for doc in docs_analisados:
            subtipo = str(doc.get("subtipo_documento", "")).lower()
            campos_brutos = doc.get("dados_extraidos_do_documento") or doc.get("campos_extraidos") or {}
            
            renda_calc = extrair_renda_do_documento(campos_brutos, subtipo)
            saldo_calc = (campos_brutos.get("your_account_balance") or {}).get("closing_balance")
            if not saldo_calc:
                saldo_calc = campos_brutos.get("closing_account_balance") or campos_brutos.get("saldo_bancario_fechamento") or campos_brutos.get("closing_balance") or campos_brutos.get("balance")
            if isinstance(saldo_calc, dict):
                saldo_calc = saldo_calc.get("closing_balance") or saldo_calc.get("value")
            saldo_calc = safe_float(saldo_calc)

            # Injeta a árvore completa mantendo chaves legadas e hierárquicas coexistindo
            resumo_docs_completo.append({
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
                "balance": saldo_calc,
                "dados_extraidos_do_documento": campos_brutos,  # 🚀 CRUCIAL: Expõe a árvore completa no painel
                "campos_extraidos": campos_brutos
            })

        # ==========================================================================
        # 💾 ESCRITA DOS ARTEFATOS NO S3 BASEADO NAS REGRAS DE NEGÓCIO
        # ==========================================================================
        if execute_score:
            report_cliente_dossie = montar_dossie_executivo(package_id, consolidado_json, scorecard_completo, resumo_docs_completo)
            logger.info("Gravando dossiê leve de crédito do cliente no S3.")
            s3_client.put_object(
                Bucket=bucket, Key=f"results/clientes/{package_id}/customer_consolidated.json",
                Body=json.dumps(report_cliente_dossie, ensure_ascii=False), ContentType="application/json"
            )

        pacote_completo_json = {
            "package_id": package_id,
            "status": "COMPLETED",
            "execute_score": execute_score,
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
                    "modelo_utilizado": "Amazon Nova Lite",
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
            "cliente": report_cliente_dossie.get("cliente", {
                "nome": "NAO REQUISITADO", "documento_identificacao": "NAO REQUISITADO",
                "score_credito": {"valor": 0, "motivos": ["Score não requisitado neste lote."]}
            }),
            "validacao": consolidado_json.get("validacao", {}),
            "documentos_analisados": resumo_docs_completo
        }

        logger.info("Gravando arquivo mestre do pacote integral (output.json) no S3.")
        s3_client.put_object(
            Bucket=bucket, Key=f"results/packages/{package_id}/output.json",
            Body=json.dumps(pacote_completo_json, ensure_ascii=False), ContentType="application/json"
        )

        return {
            "package_id": package_id,
            "user_id": event.get("user_id", "sistema"),
            "execute_score": execute_score,
            "bda_output_bucket": bucket,
            "confianca_general": 1,
            "json_estruturado": pacote_completo_json
        }

    except Exception as e:
        logger.error(f"Falha crítica na esteira de consolidação: {str(e)}")
        raise e