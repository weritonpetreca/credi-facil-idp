import json
import os
import boto3
from datetime import datetime, timezone
from aws_lambda_powertools import Logger

logger = Logger(service="confidence-checker")

s3_client = boto3.client("s3", region_name="us-east-1")

THRESHOLD = 0.80

# 🎯 SLA DE COMPLIANCE: Apenas a oscilação destes campos críticos gerará alertas humanos
CAMPOS_CRITICOS_POR_SUBTIPO = {
    "homeowners_insurance_application": ["policy_number", "effective_date", "named_insured", "insurance_company"],
    "driver_license": ["document_number", "full_name", "expiration_date"],
    "w2_tax_form": ["employer_identification_number", "wages_tips_other_compensation", "employee_social_security_number"],
    "pay_stub": ["employee_name", "pay_date", "employer_name"],
    "account_statement": ["account_number", "account_holder_name"],
    "payroll_check": ["payee_name", "amount_numeric", "payroll_check_number"]
}

def handler(event, context):
    try:
        package_id = event.get("package_id")
        bucket_saida = event.get("bda_output_bucket")
        prefix_busca = f"bda-output/{package_id}/"

        logger.info(f"Iniciando varredura granular de acurácia BDA para o lote {package_id}")

        s3_objects = s3_client.list_objects_v2(Bucket=bucket_saida, Prefix=prefix_busca)
        if "Contents" not in s3_objects:
            logger.warning(f"Nenhum output do BDA localizado para auditoria no prefixo {prefix_busca}")
            return {
                **event,
                "audit_status": "CLEAN",
                "failed_fields_count": 0,
                "failed_fields_metadata": []
            }

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
                dados_campo = extracted_fields.get(campo, {})
                confidence = float(dados_campo.get("confidenceScore") or dados_campo.get("confidence", 0.0))

                if confidence < THRESHOLD:
                    needs_human_review = True
                    campos_com_falha_geral.append({
                        "arquivo": nome_pdf_original,
                        "subtipo": subtipo,
                        "campo_afetado": campo,
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