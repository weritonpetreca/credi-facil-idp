import json
import os
import boto3
from aws_lambda_powertools import Logger

logger = Logger(service="confidence-checker")
s3_client = boto3.client("s3", region_name="us-east-1")

THRESHOLD = 0.80

# 🎯 SLA DE COMPLIANCE: Mapeamento de campos canônicos do SRS
CAMPOS_CRITICOS_POR_SUBTIPO = {
    "homeowners_insurance_application": ["policy_number", "effective_date", "named_insured", "insurance_company"],
    "driver_license": ["document_number", "full_name", "expiration_date"],
    "w2_tax_form": ["employer_identification_number", "wages_tips_other_compensation", "employee_social_security_number"],
    "pay_stub": ["employee_name", "pay_date", "employer_name"],
    "account_statement": ["account_number", "account_holder_name"],
    "payroll_check": ["payroll_check_number", "pay_date", "payee_name", "amount_numeric"]
}

# 🚀 DICIONÁRIO DE TRADUÇÃO: Mapeia chaves canônicas para as extrações brutas do Amazon BDA
MAPEA_CHAVES_BDA = {
    "payroll_check_number": ["payroll check number", "check number", "number"],
    "pay_date": ["pay date", "date", "statement period", "effective date"],
    "payee_name": ["pay to the order of", "payee name", "employee name", "named insured", "account holder name"],
    "amount_numeric": ["this amount", "amount numeric", "amount", "gross pay"],
    "policy_number": ["policy number"],
    "effective_date": ["effective date"],
    "named_insured": ["named insured", "account holder name", "employee name"],
    "insurance_company": ["insurance company", "issuer name"],
    "document_number": ["document number", "licence number", "id number"],
    "full_name": ["full name", "name", "employee name"],
    "expiration_date": ["expiration date"],
    "employer_identification_number": ["employer identification number (ein)", "employer identification number"],
    "wages_tips_other_compensation": ["wages, tips, other compensation", "amount"],
    "employee_social_security_number": ["employee's social security number", "social_security no.", "ssn"],
    "employee_name": ["employee name", "full name"],
    "employer_name": ["employer name", "company name"],
    "account_number": ["account number"],
    "account_holder_name": ["account holder name", "full name"]
}

def obter_dados_campo_real(extracted_fields, campo_canonico):
    """Varre o dicionário do BDA de forma flexível suportando variações de escrita e espaçamento."""
    if campo_canonico in extracted_fields:
        return extracted_fields[campo_canonico]
    
    variacoes = MAPEA_CHAVES_BDA.get(campo_canonico, [])
    for var in variacoes:
        for key, val in extracted_fields.items():
            key_normalizada = key.lower().strip().replace(" ", "").replace("_", "")
            var_normalizada = var.replace(" ", "").replace("_", "")
            if key_normalizada == var_normalizada:
                return val
    return {}

def handler(event, context):
    try:
        package_id = event.get("package_id")
        bucket_saida = event.get("bda_output_bucket")
        prefix_busca = f"bda-output/{package_id}/"

        logger.info(f"Iniciando varredura granular de acurácia BDA para o lote {package_id}")

        s3_objects = s3_client.list_objects_v2(Bucket=bucket_saida, Prefix=prefix_busca)
        if "Contents" not in s3_objects:
            return {**event, "audit_status": "CLEAN", "failed_fields_count": 0, "failed_fields_metadata": []}

        campos_com_falha_geral = []
        needs_human_review = False

        for obj in s3_objects["Contents"]:
            key = obj["Key"]
            if not key.endswith(".json") or "manifest" in key.lower() or "job_metadata" in key.lower():
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
            
            extracted_fields = bda_json.get("extractedFields", {})
            campos_criticos = CAMPOS_CRITICOS_POR_SUBTIPO.get(subtipo, [])

            for campo in campos_criticos:
                # 🚀 RESOLVIDO: Busca o campo real mapeado pelas strings nativas do BDA
                dados_campo = obter_dados_campo_real(extracted_fields, campo)
                confidence = float(dados_campo.get("confidenceScore") or dados_campo.get("confidence") or 0.0)

                if confidence < THRESHOLD:
                    needs_human_review = True
                    campos_com_falha_geral.append({
                        "arquivo": nome_pdf_original,
                        "subtipo": subtipo,
                        "campo_afetado": campo, # Preserva o nome canônico para o front-end
                        "confidence_score": confidence,
                        "valor_bruto": dados_campo.get("value", "")
                    })

        return {
            **event,
            "audit_status": "NEEDS_REVISION" if needs_human_review else "CLEAN",
            "failed_fields_count": len(campos_com_falha_geral),
            "failed_fields_metadata": campos_com_falha_geral
        }

    except Exception as e:
        logger.error(f"Falha catastrófica na checagem granular de confiança: {str(e)}")
        raise e