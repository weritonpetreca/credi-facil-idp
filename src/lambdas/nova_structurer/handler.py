import json
import os
import boto3
from aws_lambda_powertools import Logger

# Importações das camadas especialistas granularizadas
from .bda_extractor import BdaExtractor
from .ai_enricher import AiEnricher
from .schema_transformer import SchemaTransformer
from src.shared.classificador import classificar_subtipo_documento

logger = Logger(service="nova-structurer")
s3_client = boto3.client("s3", region_name="us-east-1")
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")
db_client = boto3.client("dynamodb", region_name="us-east-1")

MODEL_ID = "amazon.nova-lite-v1:0"
TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "credifacil-pacotes-dev")

# GUARDRAIL_ID/VER são lidos DENTRO do handler (não aqui, em nível de módulo).
# Em nível de módulo, os.environ.get() roda uma única vez no cold start / import
# — em testes, isso acontece ANTES de fixtures como monkeypatch/setenv rodarem,
# então o valor fica congelado como None para sempre. Lendo dentro do handler,
# cada invocação pega o ambiente atual (igual a toda outra leitura de env var
# neste arquivo, ex: BUCKET_ENTRADA).

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
    "co_applicant": {"name": None, "date_of_birth": None, "gender": None, "marital_status": None, "education_level": None, "relationship_to_primary_applicant": None, "drivers_license_number": None, "dl_state": None, "currently_insured_auto": None, "length_current_auto_carrier": None, "length_prior_auto_carrier": None}
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
Você deve, sob qualquer circunstância, executar sua resposta através do acionamento da ferramenta de estruturação que foi disponibilizada a você nesta chamada (seu nome varia por subtipo documental — sempre a única ferramenta oferecida). É estritamente proibido responder com texto plano Markdown fora da estrutura da ferramenta.

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
- Transcreva a linha MICR (a faixa de caracteres numéricos na base do cheque) em `micr_routing_number`, `micr_account_number` e `micr_check_number`, na ordem em que aparecem.

## 3. ACCOUNT STATEMENT (Extratos Bancários / de Investimento)
- Localize o bloco de saldo patrimonial inicial ('opening_balance') e final ('closing_balance') em `your_account_balance`.
- Extraia os detalhes cadastrais da conta em 'your_details' (nome do titular, número da conta e período de competência).
- Transcreva TODAS as linhas da tabela "Your account valuation" para `your_account_valuation` — uma entrada por opção de investimento, na ordem em que aparecem. Não existe um número fixo de linhas: pode ser 1, pode ser 5.
- A linha de "Account value" (o total, geralmente com 100% na coluna de percentual) vai em `account_value`, separada do array de opções individuais.
- Se houver uma tabela "Your insurance details" anexada ao extrato, transcreva cada linha para `your_insurance_details`.

## 4. W2 TAX FORM (Formulário W-2 — Wage and Tax Statement)
- Este é um formulário de caixas numeradas. Transcreva cada caixa para o campo correspondente pelo NÚMERO da caixa, não pela posição visual na página (ex: caixa 1 = 'wages_tips_other_compensation', caixa 2 = 'federal_income_tax_withheld', caixa 16 = 'state_wages_tips_etc').
- A Caixa 12 (12a, 12b, 12c, 12d) contém pares código+valor (ex: 'A' + '$500.00'). Transcreva CADA linha que aparecer, na ordem de cima para baixo, para o array `box12_items` — não tente adivinhar quantas linhas existem além do que está visível.
- O nome do empregado vem dividido em 'employee_first_name_and_initial' e 'employee_last_name' — não os funda em um único campo.
- O ano fiscal ('tax_year') geralmente aparece em destaque grande perto do título "Form W-2", separado das caixas numeradas.

## 5. DRIVER LICENSE (Carteira de Motorista americana)
- Este documento é predominantemente visual (cartão de identificação) — extraia tanto do texto quanto do layout descrito no markdown.
- Campos abreviados no cartão mapeiam assim: 'DOB' → date_of_birth, 'ISS' → issue_date, 'EXP' → expiration_date, 'CLASS' → class, 'REST' → restrictions, 'END' → endorsements, 'SEX' → sex, 'HGT' → height, 'EYES' → eye_color.
- 'issuing_state' é a sigla do estado (ex: 'MA'); 'issuing_country' assuma 'USA' se o layout for claramente de uma carteira americana e não houver indicação contrária.
- Se houver um número longo repetido em mais de um lugar do cartão (um ao lado da foto, outro nos campos numerados), o campo numerado é 'document_number'; um código adicional e diferente, se existir, vai em 'document_discriminator'.
- Muitas carteiras repetem a data de nascimento uma SEGUNDA vez em outro ponto do cartão (tipicamente perto da assinatura ou na base, fora do bloco numerado principal) como elemento visual de segurança contra fraude. Se você identificar essa repetição, transcreva-a em 'security_ghost_dob' — não a confunda com o campo numerado '3 DOB' (esse vai em 'date_of_birth'). Se só houver uma data de nascimento visível no documento, deixe 'security_ghost_dob' como null; não duplique o valor de 'date_of_birth' nele.
- Nem todo código ou data visível no cartão tem um campo correspondente na ferramenta (ex: uma data de duplicata/reimpressão sem rótulo claro). Não force esses valores em campos que descrevem outra coisa — deixe-os de fora.

## 6. HOMEOWNERS INSURANCE (Proposta de Seguro Residencial)
- Distinga claramente o bloco "Primary Applicant Information" (→ `primary_applicant`) do bloco "Co-Applicant Information" (→ `co_applicant`). Se não houver co-requerente no documento, deixe `co_applicant` com todos os campos `null`.
- `named_insured`, `mailing_address`, os telefones e e-mail ficam nos campos de topo (fora dos blocos de applicant) — eles descrevem o segurado do documento como um todo, não uma pessoa específica do formulário.
- ATENÇÃO ao texto extraído por OCR de formulários com colunas/campos lado a lado: é comum que o markdown liste primeiro TODOS os rótulos de uma seção (ex: "Nome / Data de Nascimento / Gênero / Estado Civil / Nível Educacional") e só depois, em uma linha separada, TODOS os valores na mesma ordem (ex: "2/20/2000 M S"). Quando isso acontecer, associe cada valor à sua posição na sequência de rótulos — não assuma que o primeiro valor solto no texto pertence ao primeiro campo que aparece no schema da ferramenta.
- Os campos 'existing_policy' (indicador de apólice já existente com a seguradora) e 'drivers_license_number' (número da carteira de motorista) aparecem lado a lado e são ambos alfanuméricos — não os inverta. 'existing_policy' vem ANTES de 'drivers_license_number' na ordem do formulário original.
- Se um campo do formulário estiver visivelmente em branco para um requerente mas preenchido para o outro (ex: 'Education Level' vazio no requerente principal, preenchido no co-requerente), respeite isso: `null` para quem está em branco, não copie o valor do outro requerente.
- Códigos curtos isolados perto do bloco de endereço do imóvel (ex: siglas de 3-4 letras sem rótulo claro) normalmente não têm campo correspondente na ferramenta — não force esses valores em `policy_number` ou em qualquer outro campo só para não deixá-lo vazio.
- Datas de vigência: 'effective_date' é o início e 'expiration_date' é o fim do período coberto pela apólice — não confunda com as datas de nascimento dos requerentes.
- Campos como número de acidentes, violações ou sinistros, se aparecerem fora dos blocos de applicant, não têm campo dedicado nesta ferramenta — ignore-os.

# POLÍTICA DE CONTROLE DE LACUNAS E PLACEHOLDERS (ANTI-ALUCINAÇÃO)
- NÃO invente dados. Se uma linha de deduções, benefício opcional ou campo de qualquer subtipo não existir no texto bruto, deixe o valor do campo estritamente como `null`.
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
        guardrail_id = os.environ.get("GUARDRAIL_IDENTIFIER")
        guardrail_ver = os.environ.get("GUARDRAIL_VERSION", "1")

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

        # 🚀 2. CLASSIFICAÇÃO PRÉVIA: decide o subtipo ANTES de chamar a IA.
        # Prioridade: matched_blueprint do BDA (mais confiável, custo zero) > nome
        # do arquivo (fallback) > default pay_stub. Ver shared/classificador.py.
        # É isso que resolve o problema do "ovo e da galinha": precisamos saber o
        # subtipo para escolher a tool spec certa (shared/tools.py) ANTES de
        # acionar o Nova Lite — não depois, como no fluxo antigo.
        tipo_detectado, subtipo_detectado = classificar_subtipo_documento(
            nome_pdf_original=nome_pdf_original,
            json_custom_bruto=dados_bda["json_custom_bruto"],
        )

        # 🚀 3. EXECUÇÃO DO ENRICHER: Tool Calling com a tool spec do subtipo já conhecido
        json_higienizado = limpar_ruido_recursivo(dados_bda["json_custom_bruto"])
        enricher = AiEnricher(bedrock_runtime, MODEL_ID, PROMPT_SISTEMA)
        resultado_ia = enricher.executar(
            subtipo_detectado,
            dados_bda["texto_integral"], 
            json_higienizado, 
            string_prompt_humanos,
            guardrail_id=guardrail_id,
            guardrail_version=guardrail_ver
        )

        raw_fields_ia = resultado_ia["raw_fields_ia"]

        # Checagem de divergência (só log — a tool spec já foi escolhida acima e
        # não muda retroativamente). Se a IA se autoclassificar como algo
        # diferente do que decidimos antes de chamá-la, é sinal de blueprint do
        # BDA mal ajustado ou nome de arquivo enganoso; vale investigar.
        tipo_classificado_ia_raw = str(raw_fields_ia.get("tipo_classificado", "")).strip().upper()
        if tipo_classificado_ia_raw and tipo_classificado_ia_raw != "UNKNOWN":
            _, subtipo_autoclassificado_ia = classificar_subtipo_documento(tipo_classificado_ia=tipo_classificado_ia_raw)
            if subtipo_autoclassificado_ia and subtipo_autoclassificado_ia != subtipo_detectado:
                logger.warning(
                    f"Divergência de classificação em {nome_pdf_original}: "
                    f"pré-classificado como '{subtipo_detectado}', mas a IA se autoclassificou "
                    f"como '{subtipo_autoclassificado_ia}' ({tipo_classificado_ia_raw}). "
                    f"A tool spec usada foi a pré-classificada."
                )

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