import json
import os
import boto3
from aws_lambda_powertools import Logger

logger = Logger(service="customer-consolidator")
s3_client = boto3.client("s3")
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")

def safe_float(val) -> float:
    """Converte valores monetários textuais ou mistos em floats puros de forma segura."""
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

def extrair_renda_documento(campos: dict, tipo: str) -> float:
    """Extrai a renda do documento respeitando a estrutura de cada template."""
    tipo_upper = tipo.upper()
    
    if tipo_upper in ["COMPROVANTE_RENDA", "PAY_STUB", "COMPROVANTE_COMPLEMENTAR", "PAYROLL_CHECK"]:
        net_pay = campos.get("net_pay")
        if isinstance(net_pay, dict):
            v = net_pay.get("this_period") or net_pay.get("year_to_date")
            if v: return safe_float(v)
        
        for earning in campos.get("earnings", []):
            if isinstance(earning, dict) and "gross_pay" in earning:
                gp = earning["gross_pay"]
                if isinstance(gp, dict):
                    v = gp.get("this_period")
                    if v: return safe_float(v)
        
        v = campos.get("amount_numeric")
        if v: return safe_float(v)
    
    elif tipo_upper in ["W2_TAX_FORM", "COMPROVANTE_RENDA"]:
        v = campos.get("wages_tips_other_compensation")
        if v: return safe_float(v)
    
    return 0.0

def calcular_scorecard_financeiro(validacao: dict, docs_analisados: list) -> dict:
    """Aplica o algoritmo determinístico de Application Scorecard."""
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
        campos = doc.get("dados_extraidos_do_documento") or doc.get("campos_extraidos", {}) or {}
        
        renda_doc = extrair_renda_documento(campos, tipo)
        renda_maxima = max(renda_maxima, renda_doc)

        if tipo in ["EXTRATO_BANCARIO", "BANK_STATEMENT", "ACCOUNT_STATEMENT"]:
            v_saldo = campos.get("closing_account_balance") or campos.get("saldo_bancario_fechamento") or campos.get("closing_balance") or campos.get("balance")
            saldo_maximo = max(saldo_maximo, safe_float(v_saldo))

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
        "valor": min(1000, max(300, score_calculado)),
        "detalhes_calculo": motivos_detalhados,
        "renda_apurada": renda_maxima,
        "liquidez_apurada": saldo_maximo
    }

def handler(event, context):
    try:
        package_id = event.get("package_id")
        bucket = event.get("bda_output_bucket") or os.environ.get("BUCKET_SAIDA")
        
        logger.info(f"Iniciando consolidação analítica de score para o pacote {package_id}")

        json_base_lote = event.get("json_estruturado")
        if not json_base_lote:
            logger.warning("Linha de base não localizada em memória. Recorrendo ao S3...")
            key_base = f"results/packages/{package_id}/output.json"
            s3_response = s3_client.get_object(Bucket=bucket, Key=key_base)
            json_base_lote = json.loads(s3_response["Body"].read().decode("utf-8"))

        docs_analisados = json_base_lote.get("documentos_analisados", [])
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
          * 'data_nascimento_consistente': Só pode ser true se a data de nascimento constar de forma explícita e visível em pelo menos um ou mais documentos e não houver divergência. SE A DATA DE NASCIMENTO ESTIVER AUSENTE OU NÃO CONSTAR EM NENHUM DOS DOCUMENTOS DO DOSSIÊ, VOCÊ DEVE OBRIGATORIAMENTE DEFINIR ESTE CAMPO COMO false. Nunca alucine consistência se o dado não existe.

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

        logger.info(f"Invocando o motor Amazon Nova Pro para o lote {package_id}")
        bedrock_response = bedrock_runtime.invoke_model(
            modelId="amazon.nova-pro-v1:0", contentType="application/json", accept="application/json", body=body_request
        )

        response_body = json.loads(bedrock_response["body"].read().decode("utf-8"))
        texto_resposta = response_body["output"]["message"]["content"][0]["text"].strip()
        
        if texto_resposta.startswith("```json"):
            texto_resposta = texto_resposta.split("```json")[1].split("```")[0].strip()
        elif texto_resposta.startswith("```"):
            texto_resposta = texto_resposta.split("```")[1].split("```")[0].strip()

        consolidado_json = json.loads(texto_resposta)

        validacao_data = consolidado_json.get("validacao", {})
        scorecard_completo = calcular_scorecard_financeiro(validacao_data, docs_analisados)
        
        # 🚀 CORREÇÃO DE CONTRATO: Chaves mapeadas conforme expectativa das Lambdas downstream
        resumo_docs = [
            {
                "arquivo_original": doc.get("arquivo_original", ""),
                "tipo_documento": doc.get("tipo_documento", ""),
                "subtipo_documento": doc.get("subtipo_documento", ""),
                "status_extracao": doc.get("confiabilidade_extracao", {}).get("status_extracao", "sucesso"),
                "confianca_media": float(doc.get("confiabilidade_extracao", {}).get("confianca_media", "1.0000")),
                "s3_key_origem": doc.get("localizacao_documento_s3", {}).get("s3_key_origem", ""),
                "s3_key_resultado": doc.get("localizacao_documento_s3", {}).get("s3_key_resultado", ""),
                "dados_extraidos_do_documento": doc.get("dados_extraidos_do_documento", {})
            }
            for doc in docs_analisados
        ]

        report_final = {
            "package_id": package_id,
            "status": "COMPLETED",
            "auditoria": {
                "versao_algoritmo_score": "1.0.0",
                "modelo_ia_consolidacao": "amazon.nova-pro-v1:0"
            },
            "cliente": {
                "nome": consolidado_json.get("cliente", {}).get("nome"),
                "documento_identificacao": consolidado_json.get("cliente", {}).get("documento_identificacao"),
                "classificacao_risco": consolidado_json.get("cliente", {}).get("classificacao_risco"),
                "score_credito": {
                    "valor": scorecard_completo["valor"],
                    "motivos": scorecard_completo["detalhes_calculo"],
                    "renda_final": scorecard_completo["renda_apurada"],
                    "liquidez_final": scorecard_completo["liquidez_apurada"]
                }
            },
            "validacao": validacao_data,
            "documentos_analisados": resumo_docs
        }

        s3_target_key = f"results/clientes/{package_id}/customer_consolidated.json"
        logger.info(f"Gravando Dossiê do Cliente estruturado em: {s3_target_key}")
        s3_client.put_object(
            Bucket=bucket, Key=s3_target_key,
            Body=json.dumps(report_final, ensure_ascii=False), ContentType="application/json"
        )

        return {
            **event,
            "cliente": report_final["cliente"],
            "validacao": report_final["validacao"],
            "json_estruturado": report_final
        }

    except Exception as e:
        logger.error(f"Falha crítica na esteira de consolidação cadastral: {str(e)}")
        raise e