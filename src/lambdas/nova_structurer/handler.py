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
Mapeie e extraia absolutamente TODOS os campos do gabarito a partir do texto linear e metadados fornecidos.

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
    """Calcula a média real varrendo os sub-objetos de propriedade dentro de inference_result."""
    confiancas = []
    inf_res = bda_json.get("inference_result", {})
    if isinstance(inf_res, dict):
        for v in inf_res.values():
            if isinstance(v, dict):
                score = v.get("confidence") or v.get("confidenceScore") or v.get("confidence_score")
                if score is not None:
                    confiancas.append(float(score))
    return round(sum(confiancas) / len(confiancas), 4) if confiancas else 1.0000

def formatar_conforme_blueprint(tipo: str, subtipo: str, arquivo: str, payload_ia: dict, s3_inputs: dict, correcoes_humanas: dict = None, bda_json: dict = None) -> dict:
    MAPA_TEMPLATES = {
        "payroll_check": TEMPLATE_PAYROLL_CHECK,
        "driver_license": TEMPLATE_DRIVER_LICENSE,
        "w2_tax_form": TEMPLATE_W2_FORM,
        "pay_stub": TEMPLATE_PAY_STUB,
        "account_statement": TEMPLATE_ACCOUNT_STATEMENT,
        "homeowners_insurance_application": TEMPLATE_HOMEOWNERS_INSURANCE
    }
    
    import copy
    template_final = json.loads(json.dumps(MAPA_TEMPLATES.get(subtipo.lower(), {})))
    
    CHAVES_CONTROLE_IA = {"tipo_classificado", "nome_titular", "alertas_inconsistencias", "confianca_extracao"}
    raw_fields = payload_ia.get("campos_extraidos_brutos") or {k: v for k, v in payload_ia.items() if k not in CHAVES_CONTROLE_IA}
    if isinstance(raw_fields, str): 
        raw_fields = json.loads(raw_fields)
        
    fields_planos_bda = {}
    if bda_json and "inference_result" in bda_json:
        inf_res = bda_json.get("inference_result", {})
        if isinstance(inf_res, dict):
            for k, v in inf_res.items():
                if isinstance(v, dict):
                    fields_planos_bda[k.lower().replace("_", "").replace(" ", "")] = str(v.get("value") or v.get("text") or "")
                else:
                    fields_planos_bda[k.lower().replace("_", "").replace(" ", "")] = str(v)

    # 1. Alimenta o template base plano
    for chave_template in template_final.keys():
        if isinstance(template_final[chave_template], (dict, list)):
            continue
        chave_limpa = chave_template.lower().replace(".", "").replace("_", "")
        valor_encontrado = fields_planos_bda.get(chave_limpa)
        if not valor_encontrado:
            for k_ia, v_ia in raw_fields.items():
                if k_ia.lower().replace(" ", "").replace("_", "").replace(".", "") == chave_limpa:
                    valor_encontrado = v_ia
                    break
        if valor_encontrado is not None:
            template_final[chave_template] = valor_encontrado

    # 🚀 MAPEAMENTO EXPLÍCITO DE SUB-ESTRUTURAS DO HOLERITE (Evita valores null)
    if subtipo.lower() == "pay_stub":
        val_gross = fields_planos_bda.get("grosspaythisperiod") or raw_fields.get("gross_pay_this_period") or raw_fields.get("gross_pay", {}).get("this_period")
        val_gross_ytd = fields_planos_bda.get("grosspayytd") or raw_fields.get("gross_pay_ytd") or raw_fields.get("gross_pay", {}).get("year_to_date")
        
        for e in template_final.get("earnings", []):
            if "gross_pay" in e:
                if val_gross: e["gross_pay"]["this_period"] = val_gross
                if val_gross_ytd: e["gross_pay"]["year_to_date"] = val_gross_ytd
            elif e.get("description") == "regular":
                if val_gross: e["this_period"] = val_gross
                if val_gross_ytd: e["year_to_date"] = val_gross_ytd

        val_net = fields_planos_bda.get("netpaythisperiod") or raw_fields.get("net_pay_this_period") or raw_fields.get("net_pay", {}).get("this_period")
        if val_net:
            template_final["net_pay"]["this_period"] = val_net

        mapeamento_deducoes = {"federalincometax": "Federal Income tax", "socialsecuritytax": "Social Security Tax", "medicaretax": "Medicare Tax"}
        for k_flat, desc in mapeamento_deducoes.items():
            val_deducao = fields_planos_bda.get(k_flat) or raw_fields.get(k_flat)
            if val_deducao and "deductions" in template_final:
                for item in template_final["deductions"].get("statutory", []):
                    if item["description"].lower() == desc.lower():
                        item["this_period"] = val_deducao

    is_human_override = False
    if correcoes_humanas:
        for composite_key, valor_corrigido in correcoes_humanas.items():
            if "__" in composite_key:
                file_part, field_part = composite_key.split("__", 1)
                if file_part == arquivo:
                    is_human_override = True
                    def injetar_correcao_recursiva(d_busca):
                        if isinstance(d_busca, dict):
                            if field_part in d_busca: d_busca[field_part] = valor_corrigido
                            for val in d_busca.values(): injetar_correcao_recursiva(val)
                        elif isinstance(d_busca, list):
                            for item in d_busca: injetar_correcao_recursiva(item)
                    injetar_correcao_recursiva(template_final)

    media_real_bda = calcular_media_real_inference(bda_json) if bda_json else 1.0000

    alertas_observacoes = list(payload_ia.get("alertas_inconsistencias", []))
    if media_real_bda < 0.80 and not is_human_override:
        alertas_observacoes.append(f"Aviso de Qualidade Óptica: Média de acurácia de caracteres baixa ({media_real_bda:.2%}).")

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
            "status_extracao": "sucesso" if is_human_override or media_real_bda >= 0.8 else "parcial",
            "confianca_media": "1.0000" if is_human_override else f"{media_real_bda:.4f}",
            "fonte_confiabilidade": "human_audit_override" if is_human_override else "amazon_bedrock_data_automation",
            "observacoes": alertas_observacoes
        }
    }