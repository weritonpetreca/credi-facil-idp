import json
import os
import boto3
from aws_lambda_powertools import Logger

# Importações das camadas especialistas granularizadas
from .bda_extractor import BdaExtractor
from .ai_enricher import AiEnricher
from .schema_transformer import SchemaTransformer

logger = Logger(service="nova-structurer")
s3_client = boto3.client("s3", region_name="us-east-1")
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")
db_client = boto3.client("dynamodb", region_name="us-east-1")

MODEL_ID = "amazon.nova-lite-v1:0"
TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "credifacil-pacotes-dev")

GUARDRAIL_ID = os.environ.get("GUARDRAIL_IDENTIFIER")
GUARDRAIL_VER = os.environ.get("GUARDRAIL_VERSION", "1")

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

MAPA_TEMPLATES = {
    "payroll_check": TEMPLATE_PAYROLL_CHECK,
    "driver_license": TEMPLATE_DRIVER_LICENSE,
    "w2_tax_form": TEMPLATE_W2_FORM,
    "pay_stub": TEMPLATE_PAY_STUB,
    "account_statement": TEMPLATE_ACCOUNT_STATEMENT,
    "homeowners_insurance_application": TEMPLATE_HOMEOWNERS_INSURANCE
}

# 🚀 PROMPT ENGINNERING DE ALTA PERFORMANCE (Contrato Estrito de Ferramenta)
PROMPT_SISTEMA = """
# ATRIBUIÇÃO DE PAPEL
Você atuará como um Motor IDP de Nível Bancário e Auditor Sênior de Riscos de Crédito. Sua especialidade exclusiva é transcrever documentos brutos de compliance e convertê-los em árvores JSON perfeitamente estruturadas.

# INSTRUÇÃO CORE: CHAMADA DE FERRAMENTA (TOOL CALLING)
Você deve, sob qualquer circunstância, executar sua resposta através do acionamento da ferramenta `estruturar_dados_documento_cliente_unico`. É estritamente proibido responder com texto plano Markdown fora da estrutura da ferramenta.

# DIRETRIZES DE EXTRAÇÃO POR SUBTIPO DOCUMENTAL

## 1. PAY STUB (Holerites / Comprovantes de Salário)
- Analise minuciosamente a tabela de 'Earnings' (Ganhos) contida no texto Markdown da standard_output.
- Mapeie as linhas para o array de `earnings`, identificando a descrição correta ('regular', 'overtime', 'holiday'). Colete 'this_period' e 'year_to_date' de cada linha.
- Localize o nó de Deduções Estatutárias ('statutory deductions'). Transcreva rigorosamente os valores de 'Federal Income tax', 'Social Security Tax' e 'Medicare Tax' para as linhas do objeto correspondente.
- Mapeie o 'net_pay' capturando o valor líquido associado à string 'Net Pay' ou 'Net Pay This Period'.

## 2. PAYROLL CHECK (Cheques de Pagamento / Ordens Bancárias)
- Mapeie o nome do emitente ('issuer_name') e do beneficiário ('payee_name') em caixa alta.
- Extraia o valor numérico em 'amount_numeric' e por extenso em 'amount_words'.
- Valide marcadores de amostra: Se encontrar as palavras explicíticas 'SAMPLE', 'VOID' ou 'NON-NEGOTIABLE', preencha as respectivas propriedades com a string idêntica em caixa alta.

## 3. ACCOUNT STATEMENT (Extratos Bancários)
- Localize o bloco de saldo patrimonial inicial ('opening_balance') e final ('closing_balance').
- Extraia os detalhes cadastrais da conta em 'your_details' (nome do titular, número da conta e período de competência).

# POLÍTICA DE CONTROLE DE LACUNAS E PLACEHOLDERS (ANTI-ALUCINAÇÃO)
- NÃO invente dados. Se uma linha de deduções ou benefício opcional não existir no texto bruto, deixe o valor do campo estritamente como `null`.
- Strings genéricas como 'BANK NAME' ou 'ADDRESS PLACEHOLDER' em documentos de teste devem ser transcritas exatamente como estão escritas na imagem, pois servem para a mesa de auditoria humana identificar amostras incompletas.
"""

def limpar_ruido_recursivo(dados: any) -> any:
    CHAVES_INUTEIS = {"boundingBox", "polygon", "geometry", "coordinates", "location", "pageNumber", "blockId", "relationships", "bounding_box", "spatial_insight", "geometryData", "xy", "box"}
    if isinstance(dados, dict):
        return {k: limpar_ruido_recursivo(v) for k, v in dados.items() if k not in CHAVES_INUTEIS}
    elif isinstance(dados, list):
        return [limpar_ruido_recursivo(item) for item in dados]
    return dados

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

        logger.info(f"Orquestrando Solução Desacoplada IDP para: {nome_pdf_original}")

        # 🚀 1. EXECUÇÃO DO EXTRACTOR: Unifica caminhos standard e custom do S3
        extractor = BdaExtractor(s3_client, bucket_saida)
        dados_bda = extractor.executar(s3_key_bda)

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

        # 🚀 2. EXECUÇÃO DO ENRICHER: Tool Calling puro com texto completo
        json_higienizado = limpar_ruido_recursivo(dados_bda["json_custom_bruto"])
        enricher = AiEnricher(bedrock_runtime, MODEL_ID, PROMPT_SISTEMA)
        resultado_ia = enricher.executar(
            dados_bda["texto_integral"], 
            json_higienizado, 
            string_prompt_humanos,
            guardrail_id=GUARDRAIL_ID,
            guardrail_version=GUARDRAIL_VER
        )

        raw_fields_ia = resultado_ia["raw_fields_ia"]
        tipo_detectado = str(raw_fields_ia.get("tipo_classificado", "UNKNOWN")).lower()
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

        # 🚀 3. EXECUÇÃO DO TRANSFORMER: Lógica determinística e cravação de chaves por cima
        transformer = SchemaTransformer(MAPA_TEMPLATES)
        blueprint_json = transformer.executar(
            subtipo_detectado, nome_pdf_original, raw_fields_ia, 
            dados_bda["json_custom_bruto"], s3_meta_inputs, correcoes_humanas
        )

        blueprint_json["tipo_documento"] = tipo_detectado
        blueprint_json["subtipo_documento"] = subtipo_detectado
        
        logger.info(f"Gravando arquivo individual estruturado em: {s3_target_key}")
        s3_client.put_object(
            Bucket=bucket_saida, Key=s3_target_key,
            Body=json.dumps(blueprint_json, ensure_ascii=False), ContentType="application/json"
        )

        return {
            "blueprint": blueprint_json,
            "raw_ia": raw_fields_ia,
            "input_tokens": resultado_ia["input_tokens"],
            "output_tokens": resultado_ia["output_tokens"]
        }
    except Exception as e:
        logger.error(f"Falha na estruturação isolada de {event.get('nome_pdf_original')}: {str(e)}")
        raise e