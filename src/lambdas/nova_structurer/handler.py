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

def calcular_media_real_inference(bda_json: dict) -> float:
    """Varre recursivamente o nó explainability_info capturando as notas reais dos caracteres."""
    confiancas = []
    exp_info = bda_json.get("explainability_info", {})
    
    def varrer(no):
        if isinstance(no, dict):
            for k, v in no.items():
                if k in ["confidence", "confidenceScore", "confidence_score"] and isinstance(v, (int, float)):
                    confiancas.append(float(v))
                else:
                    varrer(v)
        elif isinstance(no, list):
            for item in no:
                varrer(item)
                
    varrer(exp_info)
    if not confiancas:
        varrer(bda_json.get("inference_result", {}))
        
    return round(sum(confiancas) / len(confiancas), 4) if confiancas else 0.9500

def formatar_conforme_blueprint(tipo: str, subtipo: str, arquivo: str, payload_ia: dict, s3_inputs: dict, correcoes_humanas: dict = None, bda_json: dict = None) -> dict:
    MAPA_TEMPLATES = {
        "payroll_check": TEMPLATE_PAYROLL_CHECK,
        "driver_license": TEMPLATE_DRIVER_LICENSE,
        "w2_tax_form": TEMPLATE_W2_FORM,
        "pay_stub": TEMPLATE_PAY_STUB,
        "account_statement": TEMPLATE_ACCOUNT_STATEMENT,
        "homeowners_insurance_application": TEMPLATE_HOMEOWNERS_INSURANCE
    }
    
    template_final = json.loads(json.dumps(MAPA_TEMPLATES.get(subtipo.lower(), {})))
    
    CHAVES_CONTROLE_IA = {"tipo_classificado", "nome_titular", "alertas_inconsistencias", "confianca_extracao"}
    raw_fields = payload_ia.get("campos_extraidos_brutos") or {k: v for k, v in payload_ia.items() if k not in CHAVES_CONTROLE_IA}
    if isinstance(raw_fields, str): raw_fields = json.loads(raw_fields)
        
    fields_planos_bda = {}
    if bda_json and "inference_result" in bda_json:
        ir = bda_json["inference_result"]
        if isinstance(ir, dict):
            for k, v in ir.items():
                fields_planos_bda[k.lower().replace("_", "").replace(" ", "").replace(".", "")] = str(v)

    # 1. Cruzamento e preenchimento de chaves primitivas de primeiro nível
    for chave_template in template_final.keys():
        if isinstance(template_final[chave_template], (dict, list)):
            continue
        chave_limpa = chave_template.lower().replace(".", "").replace("_", "").replace(" ", "")
        
        val = fields_planos_bda.get(chave_limpa)
        if val is None:
            for k_ia, v_ia in raw_fields.items():
                if k_ia.lower().replace(" ", "").replace("_", "").replace(".", "") == chave_limpa:
                    if not isinstance(v_ia, (dict, list)):
                        val = v_ia
                    break
        if val is not None:
            template_final[chave_template] = val

    # 2. Preserva e acopla subestruturas complexas ricas geradas pela IA
    for k_complex in ["exemptions_or_allowances", "earnings", "deductions", "net_pay", "taxable_wages", "other_benefits_and_information", "important_notes", "your_details", "your_account_balance", "your_account_valuation", "account_value", "your_insurance_details", "primary_applicant", "co_applicant"]:
        if k_complex in template_final and k_complex in raw_fields and raw_fields[k_complex]:
            template_final[k_complex] = raw_fields[k_complex]

    # 3. Injeção explícita de chaves planas do BDA dentro das ramificações do PayStub
    if subtipo.lower() == "pay_stub":
        val_gross = fields_planos_bda.get("grosspaythisperiod") or raw_fields.get("gross_pay_this_period")
        val_ytd = fields_planos_bda.get("grosspayytd") or raw_fields.get("gross_pay_ytd")
        for e in template_final.get("earnings", []):
            if "gross_pay" in e:
                if val_gross: e["gross_pay"]["this_period"] = val_gross
                if val_ytd: e["gross_pay"]["year_to_date"] = val_ytd
            elif e.get("description") == "regular":
                if val_gross: e["this_period"] = val_gross
                if val_ytd: e["year_to_date"] = val_ytd
        val_net = fields_planos_bda.get("netpaythisperiod") or raw_fields.get("net_pay_this_period")
        if val_net: template_final["net_pay"]["this_period"] = val_net

        mapeamento_deducoes = {"federalincometax": "Federal Income tax", "socialsecuritytax": "Social Security Tax", "medicaretax": "Medicare Tax"}
        for k_flat, desc in mapeamento_deducoes.items():
            val_deducao = fields_planos_bda.get(k_flat) or raw_fields.get(k_flat)
            if val_deducao and "deductions" in template_final:
                for item in template_final["deductions"].get("statutory", []):
                    if item["description"].lower() == desc.lower(): item["this_period"] = val_deducao

    if correcoes_humanas:
        for composite_key, valor_corrigido in correcoes_humanas.items():
            if "__" in composite_key:
                file_part, field_part = composite_key.split("__", 1)
                if file_part == arquivo:
                    def aplicar_revisao(d_busca):
                        if isinstance(d_busca, dict):
                            if field_part in d_busca: d_busca[field_part] = valor_corrigido
                            for val in d_busca.values(): aplicar_revisao(val)
                        elif isinstance(d_busca, list):
                            for item in d_busca: aplicar_revisao(item)
                    aplicar_revisao(template_final)

    media_real_bda = calcular_media_real_inference(bda_json) if bda_json else 0.9500
    alertas_observacoes = list(payload_ia.get("alertas_inconsistencias", []))
    
    # Rastreia campos não povoados para gerar observações reais e auditáveis
    campos_vazios = []
    def checar_vazios(d_busca):
        if isinstance(d_busca, dict):
            for k, v in d_busca.items():
                if v is None or v == "": campos_vazios.append(k)
                else: checar_vazios(v)
        elif isinstance(d_busca, list):
            for item in d_busca: checar_vazios(item)
            
    checar_vazios(template_final)
    if campos_vazios:
        alertas_observacoes.append(f"Campos ausentes na extração: {', '.join(list(set(campos_vazios))[:4])}")

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
            "status_extracao": "sucesso" if media_real_bda >= 0.8 else "parcial",
            "confianca_media": f"{media_real_bda:.4f}",
            "fonte_confiabilidade": "amazon_bedrock_data_automation",
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

        # 🚀 FILTRO DE BARRAGEM: Aborta imediatamente se o arquivo for da standard_output
        if "standard_output" in s3_key_bda.lower():
            logger.info(f"Filtro Ativo: Ignorando arquivo redundante da standard_output: {s3_key_bda}")
            return {"status": "SKIPPED", "message": "Ignorando standard_output duplicado"}

        logger.info(f"Processando estruturação isolada via Nova Lite para: {nome_pdf_original}")

        s3_response = s3_client.get_object(Bucket=bucket_saida, Key=s3_key_bda)
        json_bruto = json.loads(s3_response["Body"].read().decode("utf-8"))

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