import json
import os
import boto3
from aws_lambda_powertools import Logger

logger = Logger(service="confidence-checker")
s3_client = boto3.client("s3", region_name="us-east-1")

THRESHOLD = 0.80

CAMPOS_CRITICOS_POR_SUBTIPO = {
    "w2_tax_form": ["tax_year", "employer_name", "employer_identification_number", "employee_first_name_and_initial", "employee_last_name", "employee_address", "wages_tips_other_compensation", "federal_income_tax_withheld", "social_security_wages", "medicare_wages_and_tips", "state_wages_tips_etc", "state_income_tax"],
    "payroll_check": ["issuer_name", "payroll_check_number", "pay_date", "social_security_number", "payee_name", "amount_words", "amount_numeric", "sample_indicator", "non_negotiable_indicator", "void_indicator", "authorized_signature_present"],
    "driver_license": ["identification_document_type", "document_number", "full_name", "date_of_birth", "expiration_date", "issuing_state"],
    "account_statement": ["account_holder_name", "account_holder_address", "statement_period", "account_number", "account_name", "opening_balance", "closing_balance", "investment_option_name", "option_code", "units", "unit_price_$", "value_$", "percentage", "value"],
    "homeowners_insurance_application": ["named_insured", "insurance_company", "policy_number", "effective_date", "expiration_date", "mailing_address", "primary_applicant_name", "primary_applicant_date_of_birth", "primary_applicant_gender", "primary_applicant_marital_status", "primary_applicant_education_level", "primary_applicant_existing_policy", "primary_applicant_drivers_license_number", "primary_applicant_dl_state", "primary_applicant_currently_insured_auto", "primary_applicant_current_property_policy_type", "co_applicant_name", "co_applicant_date_of_birth", "co_applicant_gender", "co_applicant_marital_status", "co_applicant_relationship_to_primary_applicant", "co_applicant_drivers_license_number", "co_applicant_dl_state"],
    "pay_stub": ["employer_name", "employee_name", "social_security_number", "taxable_marital_status", "pay_period_ending", "pay_date", "gross_pay_this_period", "gross_pay_ytd", "net_pay_this_period", "federal_income_tax", "social_security_tax", "medicare_tax", "retirement_401k"]
}

def obter_confianca_campo_bda(bda_json: dict, campo_canonico: str) -> tuple:
    """Lê a confiança real e valor do campo baseado no design unificado do AWS BDA (02/07/2026)."""
    campo_norm = campo_canonico.lower().replace("_", "").replace(".", "").replace("$", "")
    inference_result = bda_json.get("inference_result", {})
    
    valor_encontrado = None
    chave_original = None
    for k, v in inference_result.items():
        if k.lower().replace("_", "").replace(".", "").replace("$", "") == campo_norm:
            valor_encontrado = str(v).strip() if v is not None else ""
            chave_original = k
            break
            
    if valor_encontrado is None:
        return -1.0, ""
    if not valor_encontrado or valor_encontrado.lower() == "none":
        return 0.0, ""
        
    exp_info = bda_json.get("explainability_info", {})
    
    # Formato A: dicionário estruturado por chave
    if isinstance(exp_info, dict) and chave_original in exp_info:
        dados_exp = exp_info[chave_original]
        if isinstance(dados_exp, dict):
            conf = dados_exp.get("confidence") or dados_exp.get("confidence_score") or dados_exp.get("score")
            if conf is not None:
                return float(conf), valor_encontrado
                
    # Formato B: lista de objetos de explainability
    if isinstance(exp_info, list):
        for item in exp_info:
            if isinstance(item, dict):
                nome = (item.get("label") or item.get("name") or item.get("field") or "").lower().replace("_", "")
                if nome == campo_norm:
                    conf = item.get("confidence") or item.get("confidence_score") or item.get("score")
                    if conf is not None:
                        return float(conf), valor_encontrado

    logger.warning(f"Campo '{campo_canonico}' localizado no inference_result, mas sem meta-dados em explainability_info. Adotando proxy=1.0")
    return 1.0, valor_encontrado

def handler(event, context):
    try:
        package_id = event.get("package_id")
        bucket_saida = event.get("bda_output_bucket")
        prefix_busca = f"bda-output/{package_id}/"

        s3_objects = s3_client.list_objects_v2(Bucket=bucket_saida, Prefix=prefix_busca)
        if "Contents" not in s3_objects:
            return {**event, "audit_status": "CLEAN", "failed_fields_count": 0, "failed_fields_metadata": []}

        campos_para_revisao = []
        needs_human_review = False

        for obj in s3_objects["Contents"]:
            key = obj["Key"]
            if not key.endswith(".json") or "manifest" in key.lower() or "job_metadata" in key.lower():
                continue
            if "standard_output" in key.lower():
                continue

            partes = key.split("/")
            if len(partes) < 3: continue
            nome_pdf_original = partes[2]

            subtipo = "pay_stub"
            if "w2" in nome_pdf_original.lower(): subtipo = "w2_tax_form"
            elif "check" in nome_pdf_original.lower(): subtipo = "payroll_check"
            elif "statement" in nome_pdf_original.lower(): subtipo = "account_statement"
            elif "insurance" in nome_pdf_original.lower(): subtipo = "homeowners_insurance_application"
            elif "license" in nome_pdf_original.lower() or "id_card" in nome_pdf_original.lower(): subtipo = "driver_license"

            s3_response = s3_client.get_object(Bucket=bucket_saida, Key=key)
            bda_json = json.loads(s3_response["Body"].read().decode("utf-8"))

            campos_criticos = CAMPOS_CRITICOS_POR_SUBTIPO.get(subtipo, [])

            for campo in campos_criticos:
                confidence, valor_extraido = obter_confianca_campo_bda(bda_json, campo)

                campo_falho = False
                motivo = ""

                if confidence == -1.0:
                    campo_falho = True
                    motivo = "Campo crítico ausente na extração do Blueprint."
                    confidence = 0.0
                elif confidence < THRESHOLD:
                    campo_falho = True
                    motivo = f"Acurácia óptica abaixo do limite aceitável ({confidence:.2%})."
                elif not str(valor_extraido).strip() or str(valor_extraido).lower() == "none":
                    campo_falho = True
                    motivo = "Campo detectado pela IA com valor nulo ou vazio."
                    confidence = 0.0

                if campo_falho:
                    needs_human_review = True
                    campos_para_revisao.append({
                        "arquivo": nome_pdf_original,
                        "subtipo": subtipo,
                        "campo_afetado": campo,
                        "confidence_score": round(confidence, 4),
                        "valor_bruto": str(valor_extraido) if valor_extraido else "",
                        "motivo": motivo
                    })

        return {
            **event,
            "audit_status": "NEEDS_REVISION" if needs_human_review else "CLEAN",
            "failed_fields_count": len(campos_para_revisao),
            "failed_fields_metadata": campos_para_revisao
        }

    except Exception as e:
        logger.error(f"Falha crítica na execução do validador de acurácia: {str(e)}")
        raise e