import json
import os
import boto3
from datetime import datetime
from aws_lambda_powertools import Logger
from src.shared.tools import obter_especificacao_ferramenta_loan

logger = Logger(service="nova-structurer")
s3_client = boto3.client("s3", region_name="us-east-1")
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")

MODEL_ID = "amazon.nova-pro-v1:0"

# ==========================================================================
# 📊 GABARITOS DE COMPLIANCE (ESPELHO FIEL DOS SEUS BLUEPRINTS EM INGLÊS)
# ==========================================================================

TEMPLATE_PAYROLL_CHECK = {
    "issuer_name": None, "issuer_address": None, "check_stock_control_number": None,
    "payroll_check_number": None, "pay_date": None, "social_security_number": None,
    "payee_name": None, "amount_words": None, "amount_numeric": None, "bank_name": None,
    "bank_address": None, "sample_indicator": None, "non_negotiable_indicator": None,
    "void_indicator": None, "authorized_signature_present": None, "void_after_text": None,
    "micr_check_number": None, "micr_routing_number": None, "micr_account_number": None,
    "security_notice_bottom": None
}

TEMPLATE_DRIVER_LICENSE = {
    "identification_document_type": None, "document_number": None, "full_name": None,
    "date_of_birth": None, "issue_date": None, "expiration_date": None,
    "issuing_authority": None, "issuing_state": None, "issuing_country": None,
    "address": None, "class": None, "restrictions": None, "endorsements": None,
    "sex": None, "height": None, "eye_color": None, "document_discriminator": None,
    "revision_date": None, "security_ghost_dob": None
}

TEMPLATE_W2_FORM = {
    "form_type": None, "employee_social_security_number": None, "OMB_No.": None,
    "employer_identification_number": None, "employer_name": None, "employer_address": None,
    "control_number": None, "employee_first_name_and_initial": None, "employee_last_name": None,
    "employee_address": None, "wages_tips_other_compensation": None, "federal_income_tax_withheld": None,
    "social_security_wages": None, "social_security_tax_withheld": None, "medicare_wages_and_tips": None,
    "medicare_tax_withheld": None, "social_security_tips": None, "allocated_tips": None,
    "dependent_care_benefits": None, "nonqualified_plans": None, 
    "box12_items": [
        {
            "code_a": None, "amount_a": None, "code_b": None, "amount_b": None,
            "code_c": None, "amount_c": None, "code_d": None, "amount_d": None
        }
    ],
    "staturoty employee": None, "retirement plan": None, "third-party_sick_pay": None, 
    "other": None, "state": None, "employer's_state_id_number": None, "state_wages_tips_etc": None, 
    "state_income_tax": None, "local_wages_tips_etc": None, "local_income_tax": None, 
    "locality_name": None, "tax_year": None
}

TEMPLATE_PAY_STUB = {
    "document_title": None, "pay_period_ending": None, "pay_date": None, "co.": None,
    "file": None, "dept": None, "clock": None, "number": None, "employer_name": None,
    "employer_address": None, "social_security_number": None, "taxable_marital_status": None,
    "exemptions_or_allowances": [{"federal": None, "state": None, "local": None}],
    "employee_name": None, "employee_address": None,
    "earnings": [
        {"description": "regular", "rate": None, "hours": None, "this_period": None, "year_to_date": None},
        {"description": "overtime", "rate": None, "hours": None, "this_period": None, "year_to_date": None},
        {"description": "holiday", "rate": None, "hours": None, "this_period": None, "year_to_date": None},
        {"description": "tuition", "rate": None, "hours": None, "this_period": None, "year_to_date": None},
        {"gross_pay": {"this_period": None, "year_to_date": None}}
    ],
    "deductions": {
        "statutory": [
            {"description": "Federal Income tax", "this_period": None, "year_to_date": None},
            {"description": "Social Security Tax", "this_period": None, "year_to_date": None},
            {"description": "Medicare Tax", "this_period": None, "year_to_date": None},
            {"description": "NY State Income tax", "this_period": None, "year_to_date": None},
            {"description": "NYC Income tax", "this_period": None, "year_to_date": None},
            {"description": "NY SUI/SDI tax", "this_period": None, "year_to_date": None}
        ],
        "other": [
            {"description": "Bond", "this_period": None, "year_to_date": None},
            {"description": "401(k)", "this_period": None, "year_to_date": None},
            {"description": "Stock Plan", "this_period": None, "year_to_date": None},
            {"description": "Life Insurance", "this_period": None, "year_to_date": None},
            {"description": "Loan", "this_period": None, "year_to_date": None}
        ],
        "adjustments": [{"description": "Life Insurance", "this_period": None}]
    },
    "net_pay": {"this_period": None},
    "taxable_wages": {
        "excluded_from_federal_taxable_wages_note": None,
        "your_federal_taxable_wages_this_period_are": None
    },
    "other_benefits_and_information": [
        {"description": "Group Term life", "this_period": None, "total_to_date": None},
        {"description": "Loan Amt Paid", "this_period": None, "total_to_date": None},
        {"description": "Vac Hrs", "this_period": None, "total_to_date": None},
        {"description": "Sick Hrs", "this_period": None, "total_to_date": None},
        {"description": "Title", "this_period": "Operator", "total_to_date": None}
    ],
    "important_notes": [{"note_text": None}, {"note_text": None}]
}

TEMPLATE_ACCOUNT_STATEMENT = {
    "your_details": {
        "account_holder_name": None, "account_holder_address": None, "account_holder_phone_number": None,
        "statement_period": None, "account_number": None, "account_name": None, "email_address": None
    },
    "your_account_balance": {"opening_balance": None, "closing_balance": None},
    "your_account_valuation": [
        {"investment_option_name": None, "option_code": None, "units": None, "unit_price_$": None, "value_$": None, "percentage": None},
        {"investment_option_name": None, "option_code": None, "units": None, "unit_price_$": None, "value_$": None, "percentage": None},
        {"investment_option_name": None, "option_code": None, "units": None, "unit_price_$": None, "value_$": None, "percentage": None},
        {"investment_option_name": None, "option_code": None, "units": None, "unit_price_$": None, "value_$": None, "percentage": None},
        {"investment_option_name": None, "option_code": None, "units": None, "unit_price_$": None, "value_$": None, "percentage": None}
    ],
    "account_value": {"value": None, "percentage": None},
    "your_insurance_details": [
        {"benefit_type": None, "insurance_cover_amount_$": None, "benefit_amount_$": None},
        {"benefit_type": None, "insurance_cover_amount_$": None, "benefit_amount_$": None},
        {"benefit_type": None, "insurance_cover_amount_$": None, "benefit_amount_$": None}
    ]
}

TEMPLATE_HOMEOWNERS_INSURANCE = {
    "named_insured": None, "mailing_address": None, "primary_email": None, "primary_phone": None,
    "alternate_phone": None, "insurance_company": None, "insurance_company_address": None,
    "insured_property_address": None, "notice_of_insurance_information_practices": None,
    "notice": None, "policy_number": None, "purchase_date_time": None, "effective_date": None, "expiration_date": None,
    "primary_applicant": {
        "name": None, "date_of_birth": None, "gender": None, "marital_status": None,
        "education_level": None, "existing_policy": None, "drivers_license_number": None,
        "dl_state": None, "currently_insured_auto": None, "length_current_auto_carrier": None,
        "length_prior_auto_carrier": None, "years_prior_property_company": None, "current_property_policy_type": None
    },
    "co_applicant": {
        "name": None, "date_of_birth": None, "gender": None, "marital_status": None,
        "education_level": None, "relationship_to_primary_applicant": None, "drivers_license_number": None,
        "dl_state": None, "currently_insured_auto": None, "length_current_auto_carrier": None, "length_prior_auto_carrier": None
    },
    "total_auto_claims_accidents_violations_all_applicants": {
        "number_auto_accidents": {"at_fault": None, "not_at_fault": None},
        "number_violations": {"major": None, "minor": None},
        "number_comp_claims": None
    }
}

PROMPT_SISTEMA = f"""
Você é um agente IDP analítico sênior especialista em extração de dados e conformidade cadastral.
Sua tarefa é analisar o documento e preencher a ferramenta fornecida seguindo moldes estruturais rígidos.

DIRETRIZES OPERACIONAIS OBRIGATÓRIAS:
1. Classifique o documento em um dos pares de tipo/subtipo aceitos.
2. No campo 'campos_extraidos_brutos', você DEVE retornar obrigatoriamente um objeto que possua EXATAMENTE as mesmas chaves e a mesma hierarquia estrutural (aninhamento) do gabarito correspondente abaixo.
3. NÃO altere o nome das chaves, NÃO mude a hierarquia e NÃO remova chaves. Se um campo do gabarito não for localizado no texto, mantenha a chave preenchendo o valor como null (None).
4. Datas (effective_date, expiration_date, date_of_birth): Devem seguir estritamente formatos válidos de data (ex: MM/DD/YYYY ou YYYY-MM-DD). Se contiver apenas letras ou caracteres especiais aleatórios, force para null.
5. Números de Apólice/Documento (policy_number, document_number): Não podem conter apenas caracteres especiais repetidos (ex: %()*, ###). Devem possuir caracteres alfanuméricos válidos.
6. Valores Financeiros (wages, amounts): Devem conter números e pontuações monetárias coerentes. Textos corrompidos devem ser anulados.
7. Classe da Habilitação (chave 'class'): Remova qualquer prefixo como 'CLASS', 'CLASSE' ou numerais extras gerados por tabelas de OCR. O valor deve ser estritamente restrito a letras isoladas ou combinações oficiais de categorias de condução (Exemplos válidos: 'D', 'B', 'A', 'E', 'C'). Se o valor visual não for uma letra limpa, force para null.

⚠️ REGRA ESTRITA ANTI-ALUCINAÇÃO DE COMPACTAÇÃO:
Se você identificar valores na transcrição original contendo ruídos visuais puros, strings corrompidas ou falhas de leitura de fontes (Exemplos: '&()*', 'SPSESS', '##88%', '#8SS UHila'), ignore esses caracteres completamente. Nunca repasse esses símbolos para o JSON final; marque o campo estritamente como null.

GABARITOS DE COMPLIANCE (Siga estritamente a hierarquia destes blocos):
- Subtipo 'payroll_check': {json.dumps(TEMPLATE_PAYROLL_CHECK)}
- Subtipo 'driver_license': {json.dumps(TEMPLATE_DRIVER_LICENSE)}
- Subtipo 'w2_tax_form': {json.dumps(TEMPLATE_W2_FORM)}
- Subtipo 'pay_stub': {json.dumps(TEMPLATE_PAY_STUB)}
- Subtipo 'account_statement': {json.dumps(TEMPLATE_ACCOUNT_STATEMENT)}
- Subtipo 'homeowners_insurance_application': {json.dumps(TEMPLATE_HOMEOWNERS_INSURANCE)}

Identifique o nome completo do titular principal no campo 'nome_titular' em CAIXA ALTA.
"""

def extrair_texto_linear(dados: any) -> list:
    textos = []
    if isinstance(dados, dict):
        for k, v in dados.items():
            if k in ["text", "textString", "value", "content"] and isinstance(v, str):
                if len(v.strip()) > 0:
                    textos.append(v.strip())
            else:
                textos.extend(extrair_texto_linear(v))
    elif isinstance(dados, list):
        for item in dados:
            textos.extend(extrair_texto_linear(item))
    return textos

def limpar_ruido_recursivo(dados: any) -> any:
    CHAVES_INUTEIS = {"boundingBox", "polygon", "geometry", "coordinates", "location", "pageNumber", "blockId", "relationships", "bounding_box", "spatial_insight", "geometryData", "xy", "box"}
    if isinstance(dados, dict):
        return {k: limpar_ruido_recursivo(v) for k, v in dados.items() if k not in CHAVES_INUTEIS}
    elif isinstance(dados, list):
        return [limpar_ruido_recursivo(item) for item in dados]
    return dados

def formatar_conforme_blueprint(tipo: str, subtipo: str, arquivo: str, payload_ia: dict, s3_inputs: dict) -> dict:
    """Monta a estrutura JSON rica respeitando a integridade dos campos internos."""
    raw_fields = payload_ia.get("campos_extraidos_brutos", {})
    
    # 🚀 FIX CIRÚRGICO: Mantém 'total_auto_claims_accidents_violations_all_applicants' 
    # intocado dentro de 'dados_extraidos_do_documento', evitando o vazamento para a raiz.
    return {
        "tipo_documento": tipo.lower(),
        "subtipo_documento": subtipo.lower(),
        "arquivo_original": arquivo,
        "dados_extraidos_do_documento": raw_fields,
        "localizacao_documento_s3": {
            "bucket_origem": s3_inputs["bucket_entrada"],
            "s3_key_origem": s3_inputs["key_entrada"],
            "s3_uri_origem": f"s3://{s3_inputs['bucket_entrada']}/{s3_inputs['key_entrada']}",
            "bucket_resultado_bda": s3_inputs["bucket_saida"],
            "s3_key_resultado_bda": s3_inputs["key_bda"],
            "s3_uri_resultado_bda": f"s3://{s3_inputs['bucket_saida']}/{s3_inputs['key_bda']}"
        },
        "confiabilidade_extracao": {
            "status_extracao": "sucesso" if payload_ia.get("confianca_extracao", 1.0) >= 0.8 else "parcial",
            "confianca_media": str(payload_ia.get("confianca_extracao", 1.0)),
            "fonte_confiabilidade": "matched_blueprint.confidence",
            "observacoes": payload_ia.get("alertas_inconsistencias", [])
        }
    }

def consolidar_dossie_unico_cliente(package_id: str, intermediarios: list, metricas_tokens: dict) -> dict:
    timestamp_atual = datetime.utcnow().isoformat() + "Z"
    nome_final = None
    documentos_identificacao = []
    documentos_analisados = []
    
    presenca = {"identificacao": False, "renda": False, "extrato": False, "imovel": False}
    nomes_coletados = set()
    pendencias = []
    
    renda_acumulada = 0.0
    saldo_acumulado = 0.0
    PLACEHOLDERS = {"N/A", "—", "-", "NONE", "NULL", ""}

    for item in intermediarios:
        bp = item["blueprint"]
        raw_ia = item["raw_ia"]
        
        tipo = bp["tipo_documento"]
        nome_doc = str(raw_ia.get("nome_titular", "")).strip().upper()
        
        if nome_doc and nome_doc not in PLACEHOLDERS:
            nomes_coletados.add(nome_doc)
            if not nome_final:
                nome_final = nome_doc

        campos = bp["dados_extraidos_do_documento"]
        confianca_num = float(bp["confiabilidade_extracao"]["confianca_media"])

        if tipo == "documento_identificacao":
            presenca["identificacao"] = True
            documentos_identificacao.append({
                "tipo_documento": campos.get("identification_document_type") or "Outro",
                "numero_documento": campos.get("document_number") or raw_ia.get("numero_documento_identificacao"),
                "orgao_emissor": campos.get("issuing_authority") or "Não Informado",
                "estado_emissor": campos.get("issuing_state") or "Não Informado",
                "pais_emissor": campos.get("issuing_country") or "Não Informado",
                "data_emissao": campos.get("issue_date"),
                "data_validade": campos.get("expiration_date"),
                "arquivo_origem": bp["arquivo_original"]
            })
        elif tipo == "comprovante_renda":
            presenca["renda"] = True
            renda_acumulada += float(raw_ia.get("renda_bruta_informada", 0.0) or 0.0)
        elif tipo == "extrato_bancario":
            presenca["extrato"] = True
            saldo_acumulado += float(raw_ia.get("saldo_bancario_fechamento", 0.0) or 0.0)
        elif tipo == "documento_imovel":
            presenca["imovel"] = True

        documentos_analisados.append({
            "tipo_documento": tipo.upper(),
            "arquivo_original": bp["arquivo_original"],
            "s3_key_origem": bp["localizacao_documento_s3"]["s3_key_origem"],
            "s3_key_resultado_bda": bp["localizacao_documento_s3"]["s3_key_resultado_bda"],
            "status_extracao": bp["confiabilidade_extracao"]["status_extracao"],
            "campos_extraidos": campos,
            "confianca_media": confianca_num,
            "observacoes": bp["confiabilidade_extracao"]["observacoes"]
        })

    nome_consistente = True if len(nomes_coletados) == 1 else (False if len(nomes_coletados) > 1 else None)

    if not presenca["identificacao"]: pendencias.append("Falta Documento de Identificação Oficial (RG/CNH/Passaporte).")
    if not presenca["renda"]: pendencias.append("Falta Comprovante de Renda Válido (Holerite/W-2).")
    if not presenca["extrato"]: pendencias.append("Falta Extrato Bancário para comprovação de liquidez.")

    score_calculado = 0
    if presenca["identificacao"] and nome_consistente: score_calculado += 30
    if renda_acumulada > 0: score_calculado += 40
    if saldo_acumulado > 0: score_calculado += 30

    if score_calculado >= 70 and len(pendencias) == 0:
        decisao, categoria_risco, resumo = "aprovar", "baixo", "Dossiê regularizado. Proponente possui KYC consistente e saúde financeira estável."
    elif score_calculado >= 30 or len(pendencias) > 0:
        decisao, categoria_risco, resumo = "revisar", "medio", f"Crédito em atenção. Foram localizadas {len(pendencias)} pendências documentais na esteira."
    else:
        decisao, categoria_risco, resumo = "recusar", "alto", "Solicitação recusada devido à ausência severa de comprovações de renda ou KYC inválido."

    nome_modelo_final = "Amazon Nova Pro" if "pro" in MODEL_ID.lower() else "Amazon Nova"

    return {
        "cliente": {
            "nome": nome_final or "Não Identificado",
            "data_nascimento": None,
            "score_credito": {"valor": score_calculado, "fonte": "documentos", "observacao": "Score computado via análise sintática e volumetria do dossiê."},
            "classificacao_risco": {"categoria": categoria_risco, "justificativa": resumo},
            "documentos_identificacao": documentos_identificacao
        },
        "sistema": {
            "chave_cliente": f"CLIENT#{nome_final.replace(' ', '_')}" if nome_final else "CLIENT#UNKNOWN",
            "ultimo_package_vinculado": {"package_id": package_id, "client_folder": f"packages/{package_id}/", "data_recebimento": timestamp_atual},
            "processamento": {
                "status": "processado",
                "modelo_utilizado": nome_modelo_final,
                "bda_project_arn": os.environ.get("BDA_PROJECT_ARN"),
                "quantidade_tokens": {"input_tokens": metricas_tokens["input"], "output_tokens": metricas_tokens["output"], "total_tokens": metricas_tokens["input"] + metricas_tokens["output"]},
                "data_processamento": timestamp_atual
            },
            "tipos_documentos_analisados": [k for k, v in presenca.items() if v]
        },
        "documentos_analisados": documentos_analisados,
        "validacao": {
            "nome_consistente_entre_documentos": nome_consistente,
            "data_nascimento_consistente": None,
            "documento_identificacao_presente": presenca["identificacao"],
            "comprovante_renda_presente": presenca["renda"],
            "extrato_bancario_presente": presenca["extrato"],
            "documentacao_imovel_presente": presenca["imovel"],
            "pendencias": pendencias
        },
        "resultado_final": {"decisao_sugerida": decisao, "resumo_analise": resumo, "principais_alertas": []}
    }

def handler(event, context):
    try:
        package_id = event.get("package_id")
        bucket_saida = event.get("bda_output_bucket") or os.environ.get("BUCKET_SAIDA")
        bucket_entrada = f"credifacil-docs-entrada-{os.environ.get('ENV', 'dev')}"
        prefix_busca = f"bda-output/{package_id}/"

        logger.info(f"Iniciando segmentação analítica por categorias para o lote {package_id}")

        s3_objects = s3_client.list_objects_v2(Bucket=bucket_saida, Prefix=prefix_busca)
        if "Contents" not in s3_objects or len(s3_objects["Contents"]) == 0:
            raise FileNotFoundError(f"Nenhum arquivo BDA localizado sob o prefixo {prefix_busca}")

        mapa_documentos = {}
        for obj in s3_objects["Contents"]:
            key = obj["Key"]
            if not key.endswith(".json") or "manifest" in key.lower() or "job_metadata" in key.lower():
                continue
            partes = key.split("/")
            if len(partes) < 3: continue
            nome_pdf_original = partes[2]
            
            if nome_pdf_original not in mapa_documentos:
                mapa_documentos[nome_pdf_original] = []
            mapa_documentos[nome_pdf_original].append(obj)

        intermediarios_coletados = []
        total_input_tokens = 0
        total_output_tokens = 0

        for nome_pdf_original, lista_objetos in mapa_documentos.items():
            obj_selecionado = next((o for o in lista_objetos if "custom_output" in o["Key"]), None)
            if not obj_selecionado:
                obj_selecionado = next((o for o in lista_objetos if "standard_output" in o["Key"]), lista_objetos[0])

            logger.info(f"Processando arquivo original: {nome_pdf_original}")
            
            s3_response = s3_client.get_object(Bucket=bucket_saida, Key=obj_selecionado["Key"])
            json_bruto = json.loads(s3_response["Body"].read().decode("utf-8"))
            
            texto_corrido_plano = " ".join(extrair_texto_linear(json_bruto))
            json_higienizado = limpar_ruido_recursivo(json_bruto)

            tool_config = {
                "tools": [obter_especificacao_ferramenta_loan()],
                "toolChoice": {"tool": {"name": "estruturar_dados_documento_cliente_unico"}}
            }
            
            conteudo_input_hibrido = (
                f"--- TRANSCRIÇÃO DE TEXTO LINEAR DO DOCUMENTO ---\n{texto_corrido_plano}\n\n"
                f"--- ESTRUTURA DE METADADOS COMPLETA ---\n{json.dumps(json_higienizado, ensure_ascii=False)}"
            )

            response = bedrock_runtime.converse(
                modelId=MODEL_ID,
                messages=[{"role": "user", "content": [{"text": conteudo_input_hibrido}]}],
                system=[{"text": PROMPT_SISTEMA}],
                toolConfig=tool_config,
                inferenceConfig={"temperature": 0.0, "maxTokens": 4000}
            )

            usage = response.get("usage", {})
            total_input_tokens += usage.get("inputTokens", 0)
            total_output_tokens += usage.get("outputTokens", 0)

            content_blocks = response.get("output", {}).get("message", {}).get("content", [])
            tool_use_block = next((b["toolUse"] for b in content_blocks if "toolUse" in b), None)
            
            if not tool_use_block: continue

            achado = tool_use_block.get("input", {})
            if isinstance(achado, str): achado = json.loads(achado)

            tipo_detectado = str(achado.get("tipo_classificado", "UNKNOWN")).lower()
            subtipo_detectado = "pay_stub"
            
            if "w2" in nome_pdf_original.lower() or tipo_detectado == "tax_document":
                tipo_detectado = "comprovante_renda"
                subtipo_detectado = "w2_tax_form"
            elif "check" in nome_pdf_original.lower() or tipo_detectado == "payroll_check":
                tipo_detectado = "comprovante_complementar"
                subtipo_detectado = "payroll_check"
            elif "statement" in nome_pdf_original.lower() or tipo_detectado == "bank_statement":
                tipo_detectado = "extrato_bancario"
                subtipo_detectado = "account_statement"
            elif "insurance" in nome_pdf_original.lower() or tipo_detectado == "property_document":
                tipo_detectado = "documento_imovel"
                subtipo_detectado = "homeowners_insurance_application"
            elif "license" in nome_pdf_original.lower() or tipo_detectado == "identity_document":
                tipo_detectado = "documento_identificacao"
                subtipo_detectado = "driver_license"

            s3_meta_inputs = {
                "bucket_entrada": bucket_entrada,
                "key_entrada": f"packages/{package_id}/{nome_pdf_original}",
                "bucket_saida": bucket_saida,
                "key_bda": obj_selecionado["Key"]
            }

            blueprint_json = formatar_conforme_blueprint(tipo_detectado, subtipo_detectado, nome_pdf_original, achado, s3_meta_inputs)
            s3_target_key = f"results/{tipo_detectado}/{subtipo_detectado}/{package_id}/{nome_pdf_original.replace('.pdf', '')}_structured.json"
            
            logger.info(f"Salvando JSON no caminho global agrupado estável: {s3_target_key}")
            s3_client.put_object(
                Bucket=bucket_saida,
                Key=s3_target_key,
                Body=json.dumps(blueprint_json, ensure_ascii=False),
                ContentType="application/json"
            )

            intermediarios_coletados.append({"blueprint": blueprint_json, "raw_ia": achado})

        metricas = {"input": total_input_tokens, "output": total_output_tokens}
        json_final_consolidado = consolidar_dossie_unico_cliente(package_id, intermediarios_coletados, metricas)

        s3_client.put_object(
            Bucket=bucket_saida,
            Key=f"results/{package_id}/output.json",
            Body=json.dumps(json_final_consolidado, ensure_ascii=False),
            ContentType="application/json"
        )

        return {
            "package_id": package_id,
            "user_id": event.get("user_id", "sistema"),
            "bda_output_bucket": bucket_saida,
            "confianca_geral": round(1.0, 2),
            "decisao_sugerida": json_final_consolidado["resultado_final"]["decisao_sugerida"],
            "revisao_humana": json_final_consolidado["cliente"]["classificacao_risco"]["categoria"] == "medio",
            "json_estruturado": json_final_consolidado
        }

    except Exception as e:
        logger.error(f"Falha crítica na segmentação categórica de documentos: {str(e)}")
        raise e