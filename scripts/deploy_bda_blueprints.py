import json
import os
import boto3
from aws_lambda_powertools import Logger

logger = Logger(service="bda-blueprint-deployer")

try:
    from dotenv import load_dotenv
    load_dotenv() 
    logger.info("Arquivo .env local carregado com sucesso.")
except ImportError:
    pass

# Inicializa o cliente especializado do Bedrock Data Automation
bda_client = boto3.client("bedrock-data-automation", region_name="us-east-1")

def obter_schema_w2():
    return {
        "type": "object",
        "properties": {
            "tax_year": {"type": "string", "description": "Ano fiscal do imposto no topo do formulário W2."},
            "employer_name": {"type": "string", "description": "Nome da empresa ou empregador corporativo."},
            "employer_identification_number": {"type": "string", "description": "O número EIN de identificação do empregador."},
            "employee_first_name_and_initial": {"type": "string", "description": "Primeiro nome e inicial do funcionário."},
            "employee_last_name": {"type": "string", "description": "Sobrenome completo do funcionário."},
            "employee_address": {"type": "string", "description": "Endereço completo de residência do empregado."},
            "wages_tips_other_compensation": {"type": "string", "description": "Valor numérico da Caixa 1 de salários."},
            "federal_income_tax_withheld": {"type": "string", "description": "Imposto de renda federal retido na Caixa 2."},
            "social_security_wages": {"type": "string", "description": "Salários sujeitos à retenção de Social Security da Caixa 3."},
            "medicare_wages_and_tips": {"type": "string", "description": "Salários e gorjetas do Medicare contidos na Caixa 5."},
            "state_wages_tips_etc": {"type": "string", "description": "Salários estaduais contidos na Caixa 16."},
            "state_income_tax": {"type": "string", "description": "Imposto de renda estadual retido contido na Caixa 17."}
        }
    }

def obter_schema_payroll_check():
    return {
        "type": "object",
        "properties": {
            "issuer_name": {"type": "string", "description": "Nome da empresa emissora do cheque."},
            "payroll_check_number": {"type": "string", "description": "Número do cheque impresso no documento."},
            "pay_date": {"type": "string", "description": "A data de emissão contida no cheque de folha de pagamento."},
            "social_security_number": {"type": "string", "description": "Número do SSN associado impresso no documento."},
            "payee_name": {"type": "string", "description": "Nome do beneficiário impresso após Pay to the order of."},
            "amount_words": {"type": "string", "description": "O valor por extenso do cheque de pagamento."},
            "amount_numeric": {"type": "string", "description": "O valor numérico monetário do cheque precedido por cifrão."},
            "sample_indicator": {"type": "string", "description": "Marcador textual caso o documento seja uma amostra (SAMPLE)."},
            "non_negotiable_indicator": {"type": "string", "description": "Marcador textual de documento não negociável (NON-NEGOTIABLE)."},
            "void_indicator": {"type": "string", "description": "Indicadores textuais de anulação impressos (VOID)."},
            "authorized_signature_present": {"type": "string", "description": "Presença de assinatura autorizada no campo de firma."}
        }
    }

def obter_schema_id_card():
    return {
        "type": "object",
        "properties": {
            "identification_document_type": {"type": "string", "description": "O tipo do documento de identificação (DRIVER LICENSE/ID)."},
            "document_number": {"type": "string", "description": "O número de registro oficial ou número da carteira."},
            "full_name": {"type": "string", "description": "Nome completo do titular impresso no documento."},
            "date_of_birth": {"type": "string", "description": "A data de nascimento do titular."},
            "expiration_date": {"type": "string", "description": "A data de validade/expiração do documento."},
            "issuing_state": {"type": "string", "description": "O estado emissor do documento de identidade."}
        }
    }

def obter_schema_account_statement():
    return {
        "type": "object",
        "properties": {
            "your_details": {
                "type": "object",
                "properties": {
                    "account_holder_name": {"type": "string"},
                    "account_holder_address": {"type": "string"},
                    "statement_period": {"type": "string"},
                    "account_number": {"type": "string"},
                    "account_name": {"type": "string"}
                }
            },
            "your_account_balance": {
                "type": "object",
                "properties": {
                    "opening_balance": {"type": "string"},
                    "closing_balance": {"type": "string"}
                }
            },
            "your_account_valuation": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "investment_option_name": {"type": "string"},
                        "option_code": {"type": "string"},
                        "units": {"type": "string"},
                        "unit_price__$": {"type": "string"},
                        "value_$": {"type": "string"},
                        "percentage": {"type": "string"}
                    }
                }
            },
            "account_value": {
                "type": "object",
                "properties": {
                    "value": {"type": "string"},
                    "percentage": {"type": "string"}
                }
            }
        }
    }

def obter_schema_homeowners():
    return {
        "type": "object",
        "properties": {
            "named_insured": {"type": "string"},
            "insurance_company": {"type": "string"},
            "policy_number": {"type": "string"},
            "effective_date": {"type": "string"},
            "expiration_date": {"type": "string"},
            "mailing_address": {"type": "string"},
            "primary_applicant": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "date_of_birth": {"type": "string"},
                    "gender": {"type": "string"},
                    "marital_status": {"type": "string"},
                    "education_level": {"type": "string"},
                    "existing_policy": {"type": "string"},
                    "drivers_license_number": {"type": "string"},
                    "dl_state": {"type": "string"},
                    "currently_insured_auto": {"type": "string"},
                    "current_property_policy_type": {"type": "string"}
                }
            },
            "co_applicant": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "date_of_birth": {"type": "string"},
                    "gender": {"type": "string"},
                    "marital_status": {"type": "string"},
                    "relationship_to_primary_applicant": {"type": "string"},
                    "drivers_license_number": {"type": "string"},
                    "dl_state": {"type": "string"}
                }
            }
        }
    }

def obter_schema_pay_stub():
    return {
        "type": "object",
        "properties": {
            "employer_name": {"type": "string", "description": "Nome da empresa empregadora contido no holerite."},
            "employee_name": {"type": "string", "description": "Nome completo do funcionário/beneficiário."},
            "social_security_number": {"type": "string", "description": "Número do SSN impresso no holerite do funcionário."},
            "taxable_marital_status": {"type": "string", "description": "O status marital para fins fiscais (Married/Single)."},
            "pay_period_ending": {"type": "string", "description": "A data de fechamento do período de competência trabalhado."},
            "pay_date": {"type": "string", "description": "A data física de pagamento do salário."},
            "gross_pay_this_period": {"type": "string", "description": "O salário bruto total ganho neste período."},
            "gross_pay_ytd": {"type": "string", "description": "O salário bruto acumulado no ano fiscal corrente até agora."},
            "net_pay_this_period": {"type": "string", "description": "O valor líquido monetário recebido na conta pelo funcionário."},
            "federal_income_tax": {"type": "string", "description": "O valor de imposto federal retido contido nas deduções."},
            "social_security_tax": {"type": "string", "description": "O valor de imposto de seguridade social retido."},
            "medicare_tax": {"type": "string", "description": "O valor de taxa de saúde Medicare retido."},
            "retirement_401k": {"type": "string", "description": "Descontos voltados para fundos de previdência corporativa 401k."}
        }
    }

def deploy_lote_blueprints():
    project_id = os.environ.get("BDA_PROJECT_ID", "bda-project-default-635106763014")
    logger.info(f"Iniciando deploy de Blueprints Vinculados ao Projeto BDA: {project_id}")

    blueprints_mapeados = {
        "W2TaxForm": obter_schema_w2(),
        "PayrollCheck": obter_schema_payroll_check(),
        "DriverLicense": obter_schema_id_card(),
        "AccountStatement": obter_schema_account_statement(),
        "HomeownersInsurance": obter_schema_homeowners(),
        "PayStub": obter_schema_pay_stub()
    }

    for nome, schema in blueprints_mapeados.items():
        try:
            logger.info(f"Provisionando ou atualizando custom blueprint: CrediFacil-{nome}-Blueprint")
            
            response = bda_client.create_blueprint(
                blueprintName=f"CrediFacil-{nome}-Blueprint",
                type="DOCUMENT",
                blueprintStage="LIVE",
                schema=json.dumps(schema, ensure_ascii=False)
            )
            
            blueprint_arn = response.get("blueprintArn")
            logger.info(f"✅ Sucesso! Blueprint {nome} ativo sob o ARN: {blueprint_arn}")
            
        except Exception as e:
            logger.error(f"❌ Erro ao criar o blueprint {nome}: {str(e)}")

if __name__ == "__main__":
    deploy_lote_blueprints()