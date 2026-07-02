import json
import urllib.request
from aws_lambda_powertools import Logger
import boto3

logger = Logger(service="bda-custom-resource-provisioner")
bda_client = boto3.client("bedrock-data-automation", region_name="us-east-1")

def send_cfn_response(event, context, response_status, response_data=None, physical_resource_id=None):
    """Garante a liberação da Stack do CloudFormation sob qualquer circunstância."""
    response_body = json.dumps({
        "Status": response_status,
        "Reason": f"Log detalhado disponível no CloudWatch Stream: {context.log_stream_name}",
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
            logger.info(f"Sinal enviado ao CloudFormation. HTTP Status: {res.status}")
    except Exception as e:
        logger.error(f"Falha ao responder ao CloudFormation: {str(e)}")

def obter_schemas_oficiais_bda():
    """Retorna a estrutura exata de dicionário plano exigida pela API do Amazon Bedrock Data Automation."""
    return {
        "W2TaxForm": {
            "tax_year": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the tax year of the W2 form."},
            "employer_name": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the employer name."},
            "employer_identification_number": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the Employer Identification Number (EIN)."},
            "employee_first_name_and_initial": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the employee's first name and middle initial."},
            "employee_last_name": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the employee's last name."},
            "employee_address": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the employee's full address."},
            "wages_tips_other_compensation": {"type": "string", "inferenceType": "explicit", "instruction": "Extract Box 1 wages, tips, and other compensation."},
            "federal_income_tax_withheld": {"type": "string", "inferenceType": "explicit", "instruction": "Extract Box 2 federal income tax withheld."},
            "social_security_wages": {"type": "string", "inferenceType": "explicit", "instruction": "Extract Box 3 social security wages."},
            "medicare_wages_and_tips": {"type": "string", "inferenceType": "explicit", "instruction": "Extract Box 5 medicare wages and tips."},
            "state_wages_tips_etc": {"type": "string", "inferenceType": "explicit", "instruction": "Extract Box 16 state wages, tips, etc."},
            "state_income_tax": {"type": "string", "inferenceType": "explicit", "instruction": "Extract Box 17 state income tax."}
        },
        "PayrollCheck": {
            "issuer_name": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the issuer company name from the check."},
            "payroll_check_number": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the payroll check number."},
            "pay_date": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the pay date printed on the check."},
            "social_security_number": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the social security number if visible."},
            "payee_name": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the payee name after 'Pay to the order of'."},
            "amount_words": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the check amount written in words."},
            "amount_numeric": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the numeric amount preceded by a dollar sign."},
            "sample_indicator": {"type": "string", "inferenceType": "explicit", "instruction": "Extract if 'SAMPLE' watermark or text is present."},
            "non_negotiable_indicator": {"type": "string", "inferenceType": "explicit", "instruction": "Extract if 'NON-NEGOTIABLE' text is present."},
            "void_indicator": {"type": "string", "inferenceType": "explicit", "instruction": "Extract if 'VOID' text is present."},
            "authorized_signature_present": {"type": "string", "inferenceType": "explicit", "instruction": "Identify if an authorized signature text or block is present."}
        },
        "DriverLicense": {
            "identification_document_type": {"type": "string", "inferenceType": "explicit", "instruction": "Extract document type like Driver License."},
            "document_number": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the document or license number."},
            "full_name": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the full name of the license holder."},
            "date_of_birth": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the date of birth."},
            "expiration_date": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the document expiration date."},
            "issuing_state": {"type": "string", "inferenceType": "explicit", "instruction": "Extract the issuing state abbreviation."}
        },
        "AccountStatement": {
            "your_details": {
                "type": "object",
                "properties": {
                    "account_holder_name": {"type": "string", "inferenceType": "explicit"},
                    "account_holder_address": {"type": "string", "inferenceType": "explicit"},
                    "statement_period": {"type": "string", "inferenceType": "explicit"},
                    "account_number": {"type": "string", "inferenceType": "explicit"},
                    "account_name": {"type": "string", "inferenceType": "explicit"}
                }
            },
            "your_account_balance": {
                "type": "object",
                "properties": {
                    "opening_balance": {"type": "string", "inferenceType": "explicit"},
                    "closing_balance": {"type": "string", "inferenceType": "explicit"}
                }
            },
            "your_account_valuation": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "investment_option_name": {"type": "string", "inferenceType": "explicit"},
                        "option_code": {"type": "string", "inferenceType": "explicit"},
                        "units": {"type": "string", "inferenceType": "explicit"},
                        "unit_price__$": {"type": "string", "inferenceType": "explicit"},
                        "value_$": {"type": "string", "inferenceType": "explicit"},
                        "percentage": {"type": "string", "inferenceType": "explicit"}
                    }
                }
            },
            "account_value": {
                "type": "object",
                "properties": {
                    "value": {"type": "string", "inferenceType": "explicit"},
                    "percentage": {"type": "string", "inferenceType": "explicit"}
                }
            }
        },
        "HomeownersInsurance": {
            "named_insured": {"type": "string", "inferenceType": "explicit"},
            "insurance_company": {"type": "string", "inferenceType": "explicit"},
            "policy_number": {"type": "string", "inferenceType": "explicit"},
            "effective_date": {"type": "string", "inferenceType": "explicit"},
            "expiration_date": {"type": "string", "inferenceType": "explicit"},
            "mailing_address": {"type": "string", "inferenceType": "explicit"},
            "primary_applicant": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "inferenceType": "explicit"},
                    "date_of_birth": {"type": "string", "inferenceType": "explicit"},
                    "gender": {"type": "string", "inferenceType": "explicit"},
                    "marital_status": {"type": "string", "inferenceType": "explicit"},
                    "education_level": {"type": "string", "inferenceType": "explicit"},
                    "existing_policy": {"type": "string", "inferenceType": "explicit"},
                    "drivers_license_number": {"type": "string", "inferenceType": "explicit"},
                    "dl_state": {"type": "string", "inferenceType": "explicit"},
                    "currently_insured_auto": {"type": "string", "inferenceType": "explicit"},
                    "current_property_policy_type": {"type": "string", "inferenceType": "explicit"}
                }
            },
            "co_applicant": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "inferenceType": "explicit"},
                    "date_of_birth": {"type": "string", "inferenceType": "explicit"},
                    "gender": {"type": "string", "inferenceType": "explicit"},
                    "marital_status": {"type": "string", "inferenceType": "explicit"},
                    "relationship_to_primary_applicant": {"type": "string", "inferenceType": "explicit"},
                    "drivers_license_number": {"type": "string", "inferenceType": "explicit"},
                    "dl_state": {"type": "string", "inferenceType": "explicit"}
                }
            }
        },
        "PayStub": {
            "employer_name": {"type": "string", "inferenceType": "explicit"},
            "employee_name": {"type": "string", "inferenceType": "explicit"},
            "social_security_number": {"type": "string", "inferenceType": "explicit"},
            "taxable_marital_status": {"type": "string", "inferenceType": "explicit"},
            "pay_period_ending": {"type": "string", "inferenceType": "explicit"},
            "pay_date": {"type": "string", "inferenceType": "explicit"},
            "gross_pay_this_period": {"type": "string", "inferenceType": "explicit"},
            "gross_pay_ytd": {"type": "string", "inferenceType": "explicit"},
            "net_pay_this_period": {"type": "string", "inferenceType": "explicit"},
            "federal_income_tax": {"type": "string", "inferenceType": "explicit"},
            "social_security_tax": {"type": "string", "inferenceType": "explicit"},
            "medicare_tax": {"type": "string", "inferenceType": "explicit"},
            "retirement_401k": {"type": "string", "inferenceType": "explicit"}
        }
    }

def handler(event, context):
    logger.info(f"Custom Resource Event Recebido: {event['RequestType']}")
    properties = event.get("ResourceProperties", {})
    project_id = properties.get("BdaProjectId")
    
    # Monta o ARN completo caso apenas o ID plano tenha sido repassado
    project_arn = project_id
    if project_id and not project_id.startswith("arn:aws:"):
        account_id = context.invoked_function_arn.split(":")[4]
        project_arn = f"arn:aws:bedrock-data-automation:us-east-1:{account_id}:project/{project_id}"

    if event["RequestType"] in ["Create", "Update"]:
        try:
            if not project_id:
                raise ValueError("O parametro BdaProjectId e obrigatorio.")
                
            schemas = obter_schemas_oficiais_bda()
            blueprint_associations = []
            
            # 1. Provisiona cada um dos 6 Custom Blueprints no Bedrock
            for nome, schema_dict in schemas.items():
                blueprint_name = f"CrediFacil-{nome}-Blueprint"
                logger.info(f"Criando Custom Blueprint: {blueprint_name}")
                
                bp_res = bda_client.create_blueprint(
                    blueprintName=blueprint_name,
                    type="DOCUMENT",
                    blueprintStage="LIVE",
                    schema=json.dumps(schema_dict, ensure_ascii=False)
                )
                blueprint_arn = bp_res["blueprint"]["blueprintArn"]
                blueprint_associations.append({
                    "blueprintArn": blueprint_arn,
                    "blueprintStage": "LIVE"
                })
            
            # 2. Resgata o estado atual do projeto para herdar as configurações obrigatorias
            logger.info(f"Buscando metadados atuais do projeto BDA: {project_arn}")
            project_details = bda_client.get_data_automation_project(projectArn=project_arn)
            std_output_config = project_details["project"]["standardOutputConfiguration"]
            
            # 3. Vincula os ARNs das Blueprints criadas ao escopo Custom do projeto
            logger.info(f"Vinculando {len(blueprint_associations)} Blueprints ao projeto...")
            bda_client.update_data_automation_project(
                projectArn=project_arn,
                standardOutputConfiguration=std_output_config,
                customOutputConfiguration={"blueprints": blueprint_associations}
            )
            
            send_cfn_response(event, context, "SUCCESS", {"Message": "Contratos ativados com sucesso!"}, "BDABlueprintsConfig")
        except Exception as e:
            logger.exception(f"Falha catastrofica no Custom Resource do BDA: {str(e)}")
            send_cfn_response(event, context, "FAILED", {"Error": str(e)}, "BDABlueprintsConfig")
    else:
        send_cfn_response(event, context, "SUCCESS", {"Message": "Stack destruida limpa."}, event.get("PhysicalResourceId"))