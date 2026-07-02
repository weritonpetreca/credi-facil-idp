import json
import urllib.request
from aws_lambda_powertools import Logger
import boto3

logger = Logger(service="bda-custom-resource-provisioner")
bda_client = boto3.client("bedrock-data-automation", region_name="us-east-1")

def send_cfn_response(event, context, response_status, response_data=None, physical_resource_id=None):
    """Garante o envio do sinal para desatarraxar a Stack do CloudFormation sob qualquer circunstância."""
    response_body = json.dumps({
        "Status": response_status,
        "Reason": f"Log de execução detalhado disponível no CloudWatch Stream: {context.log_stream_name}",
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
            logger.info(f"Sinalizador enviado ao CloudFormation. HTTP Status: {res.status}")
    except Exception as e:
        logger.error(f"Falha crítica ao tentar responder ao CloudFormation URL: {str(e)}")

def obter_schemas_sincronizados():
    # 🚀 CORREÇÃO CRÍTICA: Contrato ajustado para o padrão de array proprietário do Amazon BDA
    return {
        "W2TaxForm": {
            "fields": [
                {"name": "tax_year", "type": "string", "description": "Ano fiscal do imposto."},
                {"name": "employer_name", "type": "string", "description": "Nome da empresa empregadora."},
                {"name": "employer_identification_number", "type": "string", "description": "O número EIN do empregador."},
                {"name": "employee_first_name_and_initial", "type": "string", "description": "Primeiro nome do funcionário."},
                {"name": "employee_last_name", "type": "string", "description": "Sobrenome do funcionário."},
                {"name": "employee_address", "type": "string", "description": "Endereço completo de residência do empregado."},
                {"name": "wages_tips_other_compensation", "type": "string", "description": "Valor numérico da Caixa 1 de salários."},
                {"name": "federal_income_tax_withheld", "type": "string", "description": "Imposto de renda federal retido na Caixa 2."},
                {"name": "social_security_wages", "type": "string", "description": "Salários sujeitos ao Social Security da Caixa 3."},
                {"name": "medicare_wages_and_tips", "type": "string", "description": "Salários e gorjetas do Medicare contidos na Caixa 5."},
                {"name": "state_wages_tips_etc", "type": "string", "description": "Salários estaduais contidos na Caixa 16."},
                {"name": "state_income_tax", "type": "string", "description": "Imposto de renda estadual retido contido na Caixa 17."}
            ]
        },
        "PayrollCheck": {
            "fields": [
                {"name": "issuer_name", "type": "string", "description": "Nome da empresa emissora do cheque."},
                {"name": "payroll_check_number", "type": "string", "description": "Número do cheque impresso no documento."},
                {"name": "pay_date", "type": "string", "description": "A data de emissão contida no cheque de folha de pagamento."},
                {"name": "social_security_number", "type": "string", "description": "Número do SSN associado impresso no documento."},
                {"name": "payee_name", "type": "string", "description": "Nome do beneficiário impresso após Pay to the order of."},
                {"name": "amount_words", "type": "string", "description": "O valor por extenso do cheque de pagamento."},
                {"name": "amount_numeric", "type": "string", "description": "O valor numérico monetário do cheque precedido por cifrão."},
                {"name": "sample_indicator", "type": "string", "description": "Marcador textual caso o documento seja uma amostra (SAMPLE)."},
                {"name": "non_negotiable_indicator", "type": "string", "description": "Marcador de documento não negociável (NON-NEGOTIABLE)."},
                {"name": "void_indicator", "type": "string", "description": "Indicadores textuais de anulação impressos (VOID)."},
                {"name": "authorized_signature_present", "type": "string", "description": "Presença de assinatura autorizada no campo de firma."}
            ]
        },
        "DriverLicense": {
            "fields": [
                {"name": "identification_document_type", "type": "string", "description": "O tipo do documento de identificação (DRIVER LICENSE/ID)."},
                {"name": "document_number", "type": "string", "description": "O número de registro oficial ou número da carteira."},
                {"name": "full_name", "type": "string", "description": "Nome completo do titular impresso no documento."},
                {"name": "date_of_birth", "type": "string", "description": "A data de nascimento do titular."},
                {"name": "expiration_date", "type": "string", "description": "A data de validade/expiração do documento."},
                {"name": "issuing_state", "type": "string", "description": "O estado emissor do documento de identidade."}
            ]
        },
        "AccountStatement": {
            "fields": [
                {"name": "account_holder_name", "type": "string", "description": "Nome do titular da conta bancária."},
                {"name": "account_holder_address", "type": "string", "description": "Endereço completo impresso do titular."},
                {"name": "statement_period", "type": "string", "description": "O período de vigência ou data do extrato bancário."},
                {"name": "account_number", "type": "string", "description": "Número da conta corrente ou conta poupança."},
                {"name": "account_name", "type": "string", "description": "Tipo ou nome comercial da conta bancária."},
                {"name": "opening_balance", "type": "string", "description": "Saldo bancário de abertura do período."},
                {"name": "closing_balance", "type": "string", "description": "Saldo bancário líquido de fechamento do período."},
                {"name": "investment_option_name", "type": "string", "description": "Nome do fundo de investimento cadastrado na tabela."},
                {"name": "option_code", "type": "string", "description": "Código identificador da opção ativa de aplicação."},
                {"name": "units", "type": "string", "description": "Quantidade de cotas/unidades retidas do investimento."},
                {"name": "unit_price_$", "type": "string", "description": "Preço unitário da cota monetária."},
                {"name": "value_$", "type": "string", "description": "Valor líquido total consolidado do investimento."},
                {"name": "percentage", "type": "string", "description": "Percentual de representatividade patrimonial do fundo."},
                {"name": "value", "type": "string", "description": "Valor da avaliação geral patrimonial da conta."}
            ]
        },
        "HomeownersInsurance": {
            "fields": [
                {"name": "named_insured", "type": "string", "description": "Segurado nomeado e proprietário da apólice de imóvel."},
                {"name": "insurance_company", "type": "string", "description": "Companhia ou seguradora emitente do documento."},
                {"name": "policy_number", "type": "string", "description": "Número de registro oficial da apólice de seguros."},
                {"name": "effective_date", "type": "string", "description": "Data de início da vigência da cobertura securitária."},
                {"name": "expiration_date", "type": "string", "description": "Data de expiração/término do contrato de seguro."},
                {"name": "mailing_address", "type": "string", "description": "Endereço completo de correspondência postal cadastrado."},
                {"name": "primary_applicant_name", "type": "string", "description": "Nome completo do proponente titular principal."},
                {"name": "primary_applicant_date_of_birth", "type": "string", "description": "Data de nascimento do proponente principal."},
                {"name": "primary_applicant_gender", "type": "string", "description": "Gênero do proponente principal cadastrado."},
                {"name": "primary_applicant_marital_status", "type": "string", "description": "Estado civil do proponente principal."},
                {"name": "primary_applicant_education_level", "type": "string", "description": "Nível de escolaridade do proponente titular."},
                {"name": "primary_applicant_existing_policy", "type": "string", "description": "Número de apólice pré-existente do titular."},
                {"name": "primary_applicant_drivers_license_number", "type": "string", "description": "Número da CNH do candidato principal."},
                {"name": "primary_applicant_dl_state", "type": "string", "description": "Estado emissor da CNH do candidato titular."},
                {"name": "primary_applicant_currently_insured_auto", "type": "string", "description": "Seguradora automotiva atual vinculada."},
                {"name": "primary_applicant_current_property_policy_type", "type": "string", "description": "Tipo de apólice de propriedade ativa atual."},
                {"name": "co_applicant_name", "type": "string", "description": "Nome completo do co-proponente cadastrado."},
                {"name": "co_applicant_date_of_birth", "type": "string", "description": "Data de nascimento do co-proponente secundário."},
                {"name": "co_applicant_gender", "type": "string", "description": "Gênero do co-proponente secundário cadastrado."},
                {"name": "co_applicant_marital_status", "type": "string", "description": "Estado civil do proponente secundário de risco."},
                {"name": "co_applicant_relationship_to_primary_applicant", "type": "string", "description": "Vínculo relacional com o proponente principal."},
                {"name": "co_applicant_drivers_license_number", "type": "string", "description": "Número da CNH do co-proponente de seguros."},
                {"name": "co_applicant_dl_state", "type": "string", "description": "Estado emissor da CNH do co-proponente associado."}
            ]
        },
        "PayStub": {
            "fields": [
                {"name": "employer_name", "type": "string", "description": "Nome da empresa empregadora contido no holerite."},
                {"name": "employee_name", "type": "string", "description": "Nome completo do funcionário/beneficiário."},
                {"name": "social_security_number", "type": "string", "description": "Número do SSN impresso no holerite do funcionário."},
                {"name": "taxable_marital_status", "type": "string", "description": "O status marital para fins fiscais (Married/Single)."},
                {"name": "pay_period_ending", "type": "string", "description": "A data de fechamento do período de competência trabalhado."},
                {"name": "pay_date", "type": "string", "description": "A data física de pagamento do salário."},
                {"name": "gross_pay_this_period", "type": "string", "description": "O salário bruto total ganho neste período."},
                {"name": "gross_pay_ytd", "type": "string", "description": "O salário bruto acumulado no ano fiscal corrente até agora."},
                {"name": "net_pay_this_period", "type": "string", "description": "O valor líquido monetário recebido na conta pelo funcionário."},
                {"name": "federal_income_tax", "type": "string", "description": "O valor de imposto federal retido contido nas deduções."},
                {"name": "social_security_tax", "type": "string", "description": "O valor de imposto de seguridade social retido."},
                {"name": "medicare_tax", "type": "string", "description": "O valor de taxa de saúde Medicare retido."},
                {"name": "retirement_401k", "type": "string", "description": "Descontos voltados para fundos de previdência corporativa 401k."}
            ]
        }
    }

def handler(event, context):
    logger.info(f"Custom Resource invocado pelo CloudFormation para a operação: {event['RequestType']}")
    
    status_final = "SUCCESS"
    payload_resposta = {"Message": "Operação concluída sem anomalias cadastrais."}
    id_recurso_fisico = event.get("PhysicalResourceId", "BDABlueprintsConfigurador")
    
    if event["RequestType"] == "Delete":
        send_cfn_response(event, context, "SUCCESS", payload_resposta, id_recurso_fisico)
        return

    try:
        properties = event.get("ResourceProperties", {})
        project_id = properties.get("BdaProjectId")
        
        if not project_id:
            raise ValueError("O parâmetro essencial BdaProjectId está ausente no contrato de propriedades.")

        schemas = obter_schemas_sincronizados()
        associacoes_blueprints = []

        for nome, schema_corpo in schemas.items():
            nome_blueprint_canonica = f"CrediFacil-{nome}-Blueprint"
            logger.info(f"Registrando blueprint customizado no BDA: {nome_blueprint_canonica}")
            
            bp_response = bda_client.create_blueprint(
                blueprintName=nome_blueprint_canonica,
                type="DOCUMENT",
                blueprintStage="LIVE",
                schema=json.dumps(schema_corpo, ensure_ascii=False)
            )
            arn_gerado = bp_response.get("blueprintArn")
            associacoes_blueprints.append({"blueprintArn": arn_gerado})

        logger.info(f"Consolidando amarração de {len(associacoes_blueprints)} Blueprints no projeto BDA: {project_id}")
        bda_client.update_project(
            projectId=project_id,
            blueprintAssociations=associacoes_blueprints
        )
        
        payload_resposta["BlueprintsProvisionados"] = len(associacoes_blueprints)

    except Exception as err:
        logger.exception(f"Erro catastrófico interceptado no provisionamento do BDA Custom Resource: {str(err)}")
        status_final = "FAILED"
        payload_resposta = {"Error": str(err)}
        
    finally:
        send_cfn_response(event, context, status_final, payload_resposta, id_recurso_fisico)