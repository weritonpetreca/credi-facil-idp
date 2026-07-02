import json
import urllib.request
from aws_lambda_powertools import Logger
import boto3

logger = Logger(service="bda-custom-resource-provisioner")
bda_client = boto3.client("bedrock-data-automation", region_name="us-east-1")

def send_cfn_response(event, context, response_status, response_data=None, physical_resource_id=None):
    response_body = json.dumps({
        "Status": response_status,
        "Reason": f"Log Stream: {context.log_stream_name}",
        "PhysicalResourceId": physical_resource_id or context.log_stream_name,
        "StackId": event["StackId"],
        "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
        "Data": response_data or {}
    }).encode('utf-8')
    
    req = urllib.request.Request(
        event["ResponseURL"],
        data=response_body,
        headers={"content-type": "", "content-length": str(len(response_body))},
        method="PUT"
    )
    try:
        with urllib.request.urlopen(req) as res:
            logger.info(f"Sinal CFN enviado: {res.status}")
    except Exception as e:
        logger.error(f"Erro no envio CFN: {str(e)}")

def criar_blueprint_limpo(classe, descricao, propriedades_planas):
    """Gera exatamente a estrutura homologada via CLI: chaves planas sem aninhamentos."""
    return {
        "class": classe,
        "description": descricao,
        "type": "object",
        "definitions": {},
        "properties": propriedades_planas
    }

def obter_schemas_oficiais_bda():
    return {
        "W2TaxForm": criar_blueprint_limpo("W2TaxForm", "Blueprint for W2 extraction", {
            "tax_year": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the tax year."},
            "employer_name": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the employer name."},
            "employer_identification_number": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the EIN."},
            "employee_first_name_and_initial": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the employee's first name and initial."},
            "employee_last_name": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the employee's last name."},
            "employee_address": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the employee's full address."},
            "wages_tips_other_compensation": {"type": "string", "inferenceType": "explicit", "instruction": "Extract Box 1 wages."},
            "federal_income_tax_withheld": {"type": "string", "inferenceType": "explicit", "instruction": "Extract Box 2 federal income tax."},
            "social_security_wages": {"type": "string", "inferenceType": "explicit", "instruction": "Extract Box 3 social security wages."},
            "medicare_wages_and_tips": {"type": "string", "inferenceType": "explicit", "instruction": "Extract Box 5 medicare wages."},
            "state_wages_tips_etc": {"type": "string", "inferenceType": "explicit", "instruction": "Extract Box 16 state wages."},
            "state_income_tax": {"type": "string", "inferenceType": "explicit", "instruction": "Extract Box 17 state income tax."}
        }),
        "PayrollCheck": criar_blueprint_limpo("PayrollCheck", "Blueprint for Payroll Check", {
            "issuer_name": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the issuer company name."},
            "payroll_check_number": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the payroll check number."},
            "pay_date": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the pay date."},
            "social_security_number": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the social security number."},
            "payee_name": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the payee name."},
            "amount_words": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the check amount in words."},
            "amount_numeric": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the numeric amount."},
            "sample_indicator": {"type": "string", "inferenceType": "explicit", "instruction": "Extract if SAMPLE text is present."},
            "non_negotiable_indicator": {"type": "string", "inferenceType": "explicit", "instruction": "Extract if NON-NEGOTIABLE text is present."},
            "void_indicator": {"type": "string", "inferenceType": "explicit", "instruction": "Extract if VOID text is present."},
            "authorized_signature_present": {"type": "string", "inferenceType": "explicit", "instruction": "Identify if an authorized signature is present."}
        }),
        "DriverLicense": criar_blueprint_limpo("DriverLicense", "Blueprint for Driver License", {
            "identification_document_type": {"type": "string", "inferenceType": "explicit", "instruction": "Extract document type."},
            "document_number": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the document number."},
            "full_name": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the full name."},
            "date_of_birth": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the date of birth."},
            "expiration_date": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the expiration date."},
            "issuing_state": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the issuing state."}
        }),
        "AccountStatement": criar_blueprint_limpo("AccountStatement", "Blueprint for Account Statement", {
            "account_holder_name": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the account holder name."},
            "account_holder_address": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the account holder address."},
            "statement_period": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the statement period."},
            "account_number": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the account number."},
            "account_name": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the account name."},
            "opening_balance": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the opening balance."},
            "closing_balance": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the closing balance."},
            "investment_option_name": {"type": "string", "inferenceType": "explicit", "instruction": "Extract investment option name."},
            "option_code": {"type": "string", "inferenceType": "explicit", "instruction": "Extract option code."},
            "units": {"type": "string", "inferenceType": "explicit", "instruction": "Extract units."},
            "unit_price_$": {"type": "string", "inferenceType": "explicit", "instruction": "Extract unit price."},
            "value_$": {"type": "string", "inferenceType": "explicit", "instruction": "Extract value."},
            "percentage": {"type": "string", "inferenceType": "explicit", "instruction": "Extract percentage."},
            "value": {"type": "string", "inferenceType": "explicit", "instruction": "Extract total value."}
        }),
        "HomeownersInsurance": criar_blueprint_limpo("HomeownersInsurance", "Blueprint for Homeowners Application", {
            "named_insured": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the named insured."},
            "insurance_company": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the insurance company name."},
            "policy_number": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the policy number."},
            "effective_date": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the effective date."},
            "expiration_date": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the expiration date."},
            "mailing_address": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the full mailing address."},
            "primary_applicant_name": {"type": "string", "inferenceType": "explicit", "instruction": "Extract primary applicant name."},
            "primary_applicant_date_of_birth": {"type": "string", "inferenceType": "explicit", "instruction": "Extract primary applicant date of birth."},
            "primary_applicant_gender": {"type": "string", "inferenceType": "explicit", "instruction": "Extract primary applicant gender."},
            "primary_applicant_marital_status": {"type": "string", "inferenceType": "explicit", "instruction": "Extract primary applicant marital status."},
            "primary_applicant_education_level": {"type": "string", "inferenceType": "explicit", "instruction": "Extract primary applicant education level."},
            "primary_applicant_existing_policy": {"type": "string", "inferenceType": "explicit", "instruction": "Extract primary applicant existing policy number."},
            "primary_applicant_drivers_license_number": {"type": "string", "inferenceType": "explicit", "instruction": "Extract primary applicant drivers license number."},
            "primary_applicant_dl_state": {"type": "string", "inferenceType": "explicit", "instruction": "Extract primary applicant driver license state."},
            "primary_applicant_currently_insured_auto": {"type": "string", "inferenceType": "explicit", "instruction": "Extract primary applicant currently insured auto carrier."},
            "primary_applicant_current_property_policy_type": {"type": "string", "inferenceType": "explicit", "instruction": "Extract primary applicant current property policy type."},
            "co_applicant_name": {"type": "string", "inferenceType": "explicit", "instruction": "Extract co-applicant name."},
            "co_applicant_date_of_birth": {"type": "string", "inferenceType": "explicit", "instruction": "Extract co-applicant date of birth."},
            "co_applicant_gender": {"type": "string", "inferenceType": "explicit", "instruction": "Extract co-applicant gender."},
            "co_applicant_marital_status": {"type": "string", "inferenceType": "explicit", "instruction": "Extract co-applicant marital status."},
            "co_applicant_relationship_to_primary_applicant": {"type": "string", "inferenceType": "explicit", "instruction": "Extract relationship to primary applicant."},
            "co_applicant_drivers_license_number": {"type": "string", "inferenceType": "explicit", "instruction": "Extract co-applicant drivers license number."},
            "co_applicant_dl_state": {"type": "string", "inferenceType": "explicit", "instruction": "Extract co-applicant driver license state."}
        }),
        "PayStub": criar_blueprint_limpo("PayStub", "Blueprint for Pay Stub", {
            "employer_name": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the employer name."},
            "employee_name": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the employee name."},
            "social_security_number": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the social security number."},
            "taxable_marital_status": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the marital status."},
            "pay_period_ending": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the pay period ending date."},
            "pay_date": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the pay date."},
            "gross_pay_this_period": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the gross pay for this period."},
            "gross_pay_ytd": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the gross pay year to date."},
            "net_pay_this_period": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the net pay for this period."},
            "federal_income_tax": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the federal income tax deduction."},
            "social_security_tax": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the social security tax deduction."},
            "medicare_tax": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the medicare tax deduction."},
            "retirement_401k": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the 401k retirement deduction."}
        })
    }

def handler(event, context):
    logger.info(f"Operacao CFN: {event['RequestType']}")
    
    status_final = "SUCCESS"
    payload_resposta = {"Message": "Operacao concluida com sucesso."}
    id_recurso_fisico = event.get("PhysicalResourceId", "BDABlueprintsConfig")
    
    if event["RequestType"] == "Delete":
        send_cfn_response(event, context, "SUCCESS", payload_resposta, id_recurso_fisico)
        return

    try:
        properties = event.get("ResourceProperties", {})
        project_id = properties.get("BdaProjectId")
        if not project_id:
            raise ValueError("BdaProjectId ausente.")

        account_id = context.invoked_function_arn.split(":")[4]
        project_arn = project_id if project_id.startswith("arn:aws:") else f"arn:aws:bedrock-data-automation:us-east-1:{account_id}:project/{project_id}"

        schemas = obter_schemas_oficiais_bda()
        associacoes_blueprints = []

        for nome, schema_corpo in schemas.items():
            nome_blueprint_canonica = f"CrediFacil-{nome}-Blueprint"
            logger.info(f"Registrando Blueprint: {nome_blueprint_canonica}")
            
            bp_res = bda_client.create_blueprint(
                blueprintName=nome_blueprint_canonica,
                type="DOCUMENT",
                blueprintStage="LIVE",
                schema=json.dumps(schema_corpo, ensure_ascii=False)
            )
            associacoes_blueprints.append({
                "blueprintArn": bp_res["blueprint"]["blueprintArn"],
                "blueprintStage": "LIVE"
            })
            
        logger.info(f"Buscando metadados e amarrando {len(associacoes_blueprints)} contratos...")
        project_details = bda_client.get_data_automation_project(projectArn=project_arn)
        std_output_config = project_details["project"]["standardOutputConfiguration"]
        
        bda_client.update_data_automation_project(
            projectArn=project_arn,
            standardOutputConfiguration=std_output_config,
            customOutputConfiguration={"blueprints": associacoes_blueprints}
        )
        
    except Exception as err:
        logger.exception(f"Erro no provisionamento: {str(err)}")
        status_final = "FAILED"
        payload_resposta = {"Error": str(err)}
        
    finally:
        send_cfn_response(event, context, status_final, payload_resposta, id_recurso_fisico)