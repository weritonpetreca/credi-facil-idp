import json
import os
import boto3
from aws_lambda_powertools import Logger
from src.shared.tools import obter_especificacao_ferramenta_loan

logger = Logger(service="nova-structurer")
s3_client = boto3.client("s3", region_name="us-east-1")
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")
db_client = boto3.client("dynamodb", region_name="us-east-1")

MODEL_ID = "amazon.nova-lite-v1:0"
TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "credifacil-pacotes-dev")

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
    "box12_items": [{"code_a": None, "amount_a": None, "code_b": None, "amount_b": None, "code_c": None, "amount_c": None, "code_d": None, "amount_d": None}],
    "staturoty employee": None, "retirement plan": None, "third-party_sick_pay": None, 
    "other": None, "state": None, "employer's_state_id_number": None, "state_wages_tips_etc": None, 
    "state_income_tax": None, "local_wages_tips_etc": None, "local_income_tax": None, "locality_name": None, "tax_year": None
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
    "taxable_wages": {"excluded_from_federal_taxable_wages_note": None, "your_federal_taxable_wages_this_period_are": None},
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
    "your_details": {"account_holder_name": None, "account_holder_address": None, "account_holder_phone_number": None, "statement_period": None, "account_number": None, "account_name": None, "email_address": None},
    "your_account_balance": {"opening_balance": None, "closing_balance": None},
    "your_account_valuation": [
        {"investment_option_name": None, "option_code": None, "units": None, "unit_price_$": None, "value_$": None, "percentage": None},
        {"investment_option_name": None, "option_code": None, "units": None, "unit_price_$": None, "value_$": None, "percentage": None}
    ],
    "account_value": {"value": None, "percentage": None},
    "your_insurance_details": [{"benefit_type": None, "insurance_cover_amount_$": None, "benefit_amount_$": None}]
}

TEMPLATE_HOMEOWNERS_INSURANCE = {
    "named_insured": None, "mailing_address": None, "primary_email": None, "primary_phone": None,
    "alternate_phone": None, "insurance_company": None, "insurance_company_address": None,
    "insured_property_address": None, "notice_of_insurance_information_practices": None,
    "notice": None, "policy_number": None, "purchase_date_time": None, "effective_date": None, "expiration_date": None,
    "primary_applicant": {"name": None, "date_of_birth": None, "gender": None, "marital_status": None, "education_level": None, "existing_policy": None, "drivers_license_number": None, "dl_state": None, "currently_insured_auto": None, "length_current_auto_carrier": None, "length_prior_auto_carrier": None, "years_prior_property_company": None, "current_property_policy_type": None},
    "co_applicant": {"name": None, "date_of_birth": None, "gender": None, "marital_status": None, "relationship_to_primary_applicant": None, "drivers_license_number": None, "dl_state": None}
}

PROMPT_SISTEMA = f"""
Você é um agente IDP analítico sênior especialista em extração de dados e conformidade cadastral.
Sua tarefa é analisar o documento e preencher a ferramenta fornecida seguindo moldes estruturais rígidos.
GABARITOS DE COMPLIANCE:
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
                if len(v.strip()) > 0: textos.append(v.strip())
            else: textos.extend(extrair_texto_linear(v))
    elif isinstance(dados, list):
        for item in dados: textos.extend(extrair_texto_linear(item))
    return textos

def limpar_ruido_recursivo(dados: any) -> any:
    CHAVES_INUTEIS = {"boundingBox", "polygon", "geometry", "coordinates", "location", "pageNumber", "blockId", "relationships", "bounding_box", "spatial_insight", "geometryData", "xy", "box"}
    if isinstance(dados, dict):
        return {k: limpar_ruido_recursivo(v) for k, v in dados.items() if k not in CHAVES_INUTEIS}
    elif isinstance(dados, list):
        return [limpar_ruido_recursivo(item) for item in dados]
    return dados

def extrair_confiancas_explainability(bda_json: dict) -> dict:
    """
    Lê as confianças reais por campo do nó explainability_info do BDA.
    Formato real (02/07/2026): List contendo um dict com chaves dos campos.
    """
    exp = bda_json.get("explainability_info", {})
    resultado = {}
    
    # Normaliza o tratamento para aceitar a lista de dicts vinda do log real
    lista_dicts = []
    if isinstance(exp, list):
        for item in exp:
            if isinstance(item, dict):
                lista_dicts.append(item)
    elif isinstance(exp, dict):
        lista_dicts.append(exp)
        
    # Extrai o score de acurácia de cada campo localizado
    for d in lista_dicts:
        for campo, dados in d.items():
            if isinstance(dados, dict):
                conf = dados.get("confidence") or dados.get("confidence_score") or dados.get("score")
                if conf is not None:
                    resultado[campo] = float(conf)
                    
    return resultado

def preencher_template_com_bda(template: dict, inference_result: dict) -> tuple[dict, list]:
    """Preenche o blueprint diretamente a partir do inference_result plano da AWS."""
    template_preenchido = json.loads(json.dumps(template))
    campos_sem_valor = []
    
    for campo_template in template_preenchido.keys():
        if isinstance(template_preenchido[campo_template], (dict, list)):
            continue
            
        if campo_template in inference_result:
            valor = inference_result[campo_template]
            if valor is not None and str(valor).strip():
                template_preenchido[campo_template] = str(valor)
                continue
                
        campo_norm = campo_template.lower().replace("_", "").replace(".", "")
        encontrado = False
        for k_bda, v_bda in inference_result.items():
            if k_bda.lower().replace("_", "").replace(".", "") == campo_norm:
                if v_bda is not None and str(v_bda).strip():
                    template_preenchido[campo_template] = str(v_bda)
                    encontrado = True
                    break
        if not encontrado:
            campos_sem_valor.append(campo_template)
            
    return template_preenchido, campos_sem_valor

def formatar_conforme_blueprint(tipo: str, subtipo: str, arquivo: str, payload_ia: dict, s3_inputs: dict, correcoes_humanas: dict = None, bda_json: dict = None) -> dict:
    MAPA_TEMPLATES = {
        "payroll_check": TEMPLATE_PAYROLL_CHECK,
        "driver_license": TEMPLATE_DRIVER_LICENSE,
        "w2_tax_form": TEMPLATE_W2_FORM,
        "pay_stub": TEMPLATE_PAY_STUB,
        "account_statement": TEMPLATE_ACCOUNT_STATEMENT,
        "homeowners_insurance_application": TEMPLATE_HOMEOWNERS_INSURANCE
    }
    
    template_base = MAPA_TEMPLATES.get(subtipo.lower(), {})
    inference_result = (bda_json or {}).get("inference_result", {})
    
    # Camada 1: Cópia Direta BDA (Mapeamento Confiável Sem Perda por LLM)
    template_final, campos_sem_valor = preencher_template_com_bda(template_base, inference_result)
    
    # Camada 2: Fallback Inteligente via Nova Lite (Apenas para lacunas do BDA)
    CHAVES_CONTROLE_IA = {"tipo_classificado", "nome_titular", "alertas_inconsistencias", "confianca_extracao"}
    raw_fields_ia = payload_ia.get("campos_extraidos_brutos") or {k: v for k, v in payload_ia.items() if k not in CHAVES_CONTROLE_IA}
    if isinstance(raw_fields_ia, str): 
        raw_fields_ia = json.loads(raw_fields_ia)
        
    for campo_vazio in campos_sem_valor:
        for k_ia, v_ia in raw_fields_ia.items():
            if k_ia.lower().replace(" ", "_").replace(".", "") == campo_vazio.lower().replace(".", ""):
                if v_ia is not None:
                    template_final[campo_vazio] = v_ia
                break

    # Resgate de Subestruturas Hierárquicas Complexas geradas pela IA
    for k_complex in ["exemptions_or_allowances", "earnings", "deductions", "net_pay", "taxable_wages", "other_benefits_and_information", "important_notes", "your_details", "your_account_balance", "your_account_valuation", "account_value", "your_insurance_details", "primary_applicant", "co_applicant"]:
        if k_complex in template_final and k_complex in raw_fields_ia and raw_fields_ia[k_complex]:
            template_final[k_complex] = raw_fields_ia[k_complex]

    # Mapeador Manual Explicito de campos planos do BDA para nós internos do PayStub
    if subtipo.lower() == "pay_stub":
        fields_planos_bda = {k.lower().replace("_", ""): str(v) for k, v in inference_result.items()}
        val_gross = fields_planos_bda.get("grosspaythisperiod") or raw_fields_ia.get("gross_pay_this_period")
        val_ytd = fields_planos_bda.get("grosspayytd") or raw_fields_ia.get("gross_pay_ytd")
        for e in template_final.get("earnings", []):
            if "gross_pay" in e:
                if val_gross: e["gross_pay"]["this_period"] = val_gross
                if val_ytd: e["gross_pay"]["year_to_date"] = val_ytd
            elif e.get("description") == "regular":
                if val_gross: e["this_period"] = val_gross
                if val_ytd: e["year_to_date"] = val_ytd
        val_net = fields_planos_bda.get("netpaythisperiod") or raw_fields_ia.get("net_pay_this_period")
        if val_net: template_final["net_pay"]["this_period"] = val_net

        mapeamento_deducoes = {"federalincometax": "Federal Income tax", "socialsecuritytax": "Social Security Tax", "medicaretax": "Medicare Tax"}
        for k_flat, desc in mapeamento_deducoes.items():
            val_deducao = fields_planos_bda.get(k_flat) or raw_fields_ia.get(k_flat)
            if val_deducao and "deductions" in template_final:
                for item in template_final["deductions"].get("statutory", []):
                    if item["description"].lower() == desc.lower():
                        item["this_period"] = val_deducao

    # Camada 3: Mesa de Revisão Humana (Sobrescrita de Maior Autoridade)
    is_human_override = False
    campos_corrigidos = []
    if correcoes_humanas:
        for composite_key, valor_corrigido in correcoes_humanas.items():
            if "__" in composite_key:
                file_part, field_part = composite_key.split("__", 1)
                if file_part == arquivo:
                    def aplicar_revisao(d_busca):
                        nonlocal is_human_override
                        if isinstance(d_busca, dict):
                            if field_part in d_busca: 
                                d_busca[field_part] = valor_corrigido
                                is_human_override = True
                                campos_corrigidos.append(field_part)
                            for val in d_busca.values(): aplicar_revisao(val)
                        elif isinstance(d_busca, list):
                            for item in d_busca: aplicar_revisao(item)
                    aplicar_revisao(template_final)

    # Cálculo da Acurácia Real via Meta-Dados de Explainability
    confiancas_por_campo = extrair_confiancas_explainability(bda_json or {})
    campos_bda_preenchidos = set(inference_result.keys()) & set(template_final.keys())
    
    if confiancas_por_campo:
        confs = [confiancas_por_campo[c] for c in campos_bda_preenchidos if c in confiancas_por_campo]
        media_real = round(sum(confs) / len(confs), 4) if confs else 0.8850
    else:
        campos_preenchidos = sum(1 for v in template_final.values() if v is not None and v != "")
        total = max(len(template_final), 1)
        media_real = round(campos_preenchidos / total, 4)

    if is_human_override:
        media_real = 1.0000

    campos_criticos_nulos = [c for c in ["payee_name", "pay_date", "amount_numeric", "employee_name", "net_pay", "pay_period_ending", "account_holder_name", "closing_balance"] if c in template_final and (template_final[c] is None or template_final[c] == "")]
    status_extracao = "parcial" if campos_criticos_nulos and not is_human_override else "sucesso"

    alertas_observacoes = list(payload_ia.get("alertas_inconsistencias", []))
    if campos_sem_valor:
        alertas_observacoes.append(f"Campos estruturais vazios na extração: {', '.join(campos_sem_valor[:3])}")
    if campos_corrigidos:
        alertas_observacoes.append(f"Campos retificados manualmente: {', '.join(campos_corrigidos)}")

    return {
        "tipo_documento": tipo.lower(),
        "subtipo_documento": subtipo.lower(),
        "arquivo_original": arquivo,
        "dados_extraidos_do_documento": template_final,
        "localizacao_documento_s3": {
            "bucket_origem": s3_inputs["bucket_entrada"],
            "s3_key_origem": s3_inputs["key_entrada"],
            "s3_uri_origem": f"s3://{s3_inputs['bucket_entrada']}/{s3_inputs['key_entrada']}",
            "bucket_resultado_bda": s3_inputs["bucket_saida"],
            "s3_key_resultado_bda": s3_inputs["key_bda"],
            "s3_key_resultado": s3_inputs["key_resultado"],
            "s3_uri_resultado_bda": f"s3://{s3_inputs['bucket_saida']}/{s3_inputs['key_bda']}"
        },
        "confiabilidade_extracao": {
            "status_extracao": status_extracao,
            "confianca_media": f"{media_real:.4f}",
            "fonte_confiabilidade": "human_audit_override" if is_human_override else "amazon_bedrock_data_automation",
            "observacoes": alertas_observacoes
        }
    }

def handler(event, context):
    try:
        package_id = event.get("package_id")
        bucket_saida = event.get("bda_output_bucket")
        bucket_entrada = os.environ.get("BUCKET_ENTRADA")
        nome_pdf_original = event.get("nome_pdf_original")
        s3_key_bda = event.get("s3_key_bda")

        if "standard_output" in s3_key_bda.lower():
            logger.info(f"Filtro Ativo: Ignorando arquivo redundante da standard_output: {s3_key_bda}")
            return {"status": "SKIPPED", "message": "Ignorando standard_output duplicado"}

        logger.info(f"Processando estruturação isolada via Nova Lite para: {nome_pdf_original}")

        s3_response = s3_client.get_object(Bucket=bucket_saida, Key=s3_key_bda)
        json_bruto = json.loads(s3_response["Body"].read().decode("utf-8"))

        # 🚀 PASSO 0 — Monitoramento Estrutural do Explainability (Clau)
        if "explainability_info" in json_bruto:
            exp_info = json_bruto["explainability_info"]
            logger.info(f"==== EXPLAINABILITY_INFO TIPO: {type(exp_info).__name__} ====")
            logger.info(f"EXPLAINABILITY_INFO CONTEÚDO: {json.dumps(exp_info, ensure_ascii=False)[:2000]}")
            if isinstance(exp_info, dict):
                logger.info(f"EXPLAINABILITY_INFO CHAVES: {list(exp_info.keys())[:20]}")
            elif isinstance(exp_info, list) and exp_info:
                logger.info(f"EXPLAINABILITY_INFO PRIMEIRO ITEM: {json.dumps(exp_info[0], ensure_ascii=False)}")

        texto_corrido_plano = " ".join(extrair_texto_linear(json_bruto))
        json_higienizado = limpar_ruido_recursivo(json_bruto)

        correcoes_humanas = {}
        string_prompt_humanos = ""
        try:
            rev_response = db_client.get_item(
                TableName=TABLE_NAME,
                Key={"PK": {"S": package_id}, "SK": {"S": "REVISION"}}
            )
            rev_item = rev_response.get("Item")
            if rev_item and rev_item.get("status_revisao", {}).get("S") == "RESOLVIDO":
                correcoes_json = rev_item.get("correcoes_humanas", {}).get("S", "{}")
                correcoes_humanas = json.loads(correcoes_json)
                correcoes_especificas = {k.split("__")[1]: v for k, v in correcoes_humanas.items() if k.startswith(f"{nome_pdf_original}__")}
                if correcoes_especificas:
                    string_prompt_humanos = f"\n\n--- CORREÇÕES MANUAIS DO OPERADOR ---\n{json.dumps(correcoes_especificas, ensure_ascii=False)}"
        except Exception as db_err:
            logger.warning(f"Falha ao integrar mesa de revisão humana na estruturação: {str(db_err)}")

        tool_config = {
            "tools": [obter_especificacao_ferramenta_loan()],
            "toolChoice": {"tool": {"name": "estruturar_dados_documento_cliente_unico"}}
        }
        
        conteudo_input_hibrido = (
            f"--- TRANSCRIÇÃO DE TEXTO LINEAR DO DOCUMENTO ---\n{texto_corrido_plano}\n\n"
            f"--- ESTRUTURA DE METADADOS COMPLETA ---\n{json.dumps(json_higienizado, ensure_ascii=False)}"
            f"{string_prompt_humanos}"
        )

        response = bedrock_runtime.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": conteudo_input_hibrido}]}],
            system=[{"text": PROMPT_SISTEMA}],
            toolConfig=tool_config,
            guardrailConfig={
                "guardrailIdentifier": os.environ.get("GUARDRAIL_IDENTIFIER"),
                "guardrailVersion": os.environ.get("GUARDRAIL_VERSION", "1"),
                "trace": "disabled"
            },
            inferenceConfig={"temperature": 0.0, "maxTokens": 4000}
        )

        usage = response.get("usage", {})
        content_blocks = response.get("output", {}).get("message", {}).get("content", [])
        tool_use_block = next((b["toolUse"] for b in content_blocks if "toolUse" in b), None)
        
        if not tool_use_block:
            raise ValueError(f"O modelo não acionou a ferramenta de estruturação para {nome_pdf_original}")

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
        elif "license" in nome_pdf_original.lower() or "id_card" in nome_pdf_original.lower() or tipo_detectado == "identity_document":
            tipo_detectado = "documento_identificacao"
            subtipo_detectado = "driver_license"

        s3_target_key = f"results/{tipo_detectado}/{subtipo_detectado}/{package_id}/{nome_pdf_original.replace('.pdf', '')}_structured.json"
        
        s3_meta_inputs = {
            "bucket_entrada": bucket_entrada, "key_entrada": f"packages/{package_id}/{nome_pdf_original}",
            "bucket_saida": bucket_saida, "key_bda": s3_key_bda, "key_resultado": s3_target_key
        }

        blueprint_json = formatar_conforme_blueprint(
            tipo_detectado, subtipo_detectado, nome_pdf_original, achado, s3_meta_inputs, correcoes_humanas, json_bruto
        )
        
        logger.info(f"Gravando arquivo individual estruturado em: {s3_target_key}")
        s3_client.put_object(
            Bucket=bucket_saida, Key=s3_target_key,
            Body=json.dumps(blueprint_json, ensure_ascii=False), ContentType="application/json"
        )

        return {
            "blueprint": blueprint_json,
            "raw_ia": achado,
            "input_tokens": usage.get("inputTokens", 0),
            "output_tokens": usage.get("outputTokens", 0)
        }
    except Exception as e:
        logger.error(f"Falha na estruturação isolada de {event.get('nome_pdf_original')}: {str(e)}")
        raise e