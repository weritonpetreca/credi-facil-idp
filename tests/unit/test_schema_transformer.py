"""
Testes do SchemaTransformer — cobertura dedicada ao merge genérico
(mesclar_generico_por_template) introduzido para destravar o polimorfismo
de shared/tools.py nos 5 subtipos que não são pay_stub.

Os dados de teste replicam os documentos de amostra reais do projeto
(W2 de Arnav Desai, extrato de Jane Doe, apólice de Ziggy Starpixel /
Luna Starlight-Glitterdust) para que o teste falhe se o merge parar de
bater com o formato real, não só com um mock artificial.
"""
import json
import pytest

from src.lambdas.nova_structurer.schema_transformer import SchemaTransformer
from src.lambdas.nova_structurer.handler import MAPA_TEMPLATES


def _novo_transformer():
    return SchemaTransformer(MAPA_TEMPLATES)


def _s3_inputs_vazio():
    return {
        "bucket_entrada": "b-in", "key_entrada": "k-in",
        "bucket_saida": "b-out", "key_bda": "k-bda", "key_resultado": "k-res",
    }


# ==========================================================================
# W2_TAX_FORM — campos planos + box12_items (lista → dict achatado)
# ==========================================================================

def test_merge_w2_campos_planos_batem_com_o_formulario_de_arnav_desai():
    transformer = _novo_transformer()
    raw_fields_ia = {
        "tipo_classificado": "W2_TAX_FORM",
        "employer_name": "John Stiles",
        "employer_address": "100 Main Street, Anytown, USA",
        "employer_identification_number": "4963147952",
        "employee_first_name_and_initial": "Arnav",
        "employee_last_name": "Desai",
        "wages_tips_other_compensation": "100.00",
        "federal_income_tax_withheld": "500.00",
        "social_security_wages": "1000.00",
        "state_wages_tips_etc": "50.00",
        "state_income_tax": "500.00",
        "tax_year": "2022",
        "box12_items": [],
        "alertas_inconsistencias": [],
    }

    resultado = transformer.executar("w2_tax_form", "w2.pdf", raw_fields_ia, {}, _s3_inputs_vazio())
    campos = resultado["dados_extraidos_do_documento"]

    assert campos["employer_name"] == "John Stiles"
    assert campos["employee_first_name_and_initial"] == "Arnav"
    assert campos["employee_last_name"] == "Desai"
    assert campos["wages_tips_other_compensation"] == "100.00"
    assert campos["tax_year"] == "2022"
    # Nomes divididos não podem ser fundidos em um único campo
    assert "employee_name" not in campos


def test_merge_w2_box12_items_mapeia_lista_da_ia_para_dict_achatado_por_posicao():
    """
    A tool spec devolve uma LISTA (uma entrada por linha vista no documento).
    O template representa as 4 posições possíveis como um dict achatado
    (code_a/amount_a...code_d/amount_d). No W2 de amostra: 12a=A/$500.00,
    12b=C/$1500.00, 12c=A/$500.00, 12d=B/$1000.00.
    """
    transformer = _novo_transformer()
    raw_fields_ia = {
        "tipo_classificado": "W2_TAX_FORM",
        "employee_last_name": "Desai",
        "box12_items": [
            {"code": "A", "amount": "500.00"},
            {"code": "C", "amount": "1500.00"},
            {"code": "A", "amount": "500.00"},
            {"code": "B", "amount": "1000.00"},
        ],
        "alertas_inconsistencias": [],
    }

    resultado = transformer.executar("w2_tax_form", "w2.pdf", raw_fields_ia, {}, _s3_inputs_vazio())
    box12 = resultado["dados_extraidos_do_documento"]["box12_items"][0]

    assert box12 == {
        "code_a": "A", "amount_a": "500.00",
        "code_b": "C", "amount_b": "1500.00",
        "code_c": "A", "amount_c": "500.00",
        "code_d": "B", "amount_d": "1000.00",
    }


def test_merge_w2_box12_items_com_menos_de_4_linhas_nao_quebra():
    """O documento pode ter só 1 ou 2 linhas na Caixa 12 — não deve tentar
    acessar posições além do que a IA devolveu."""
    transformer = _novo_transformer()
    raw_fields_ia = {
        "tipo_classificado": "W2_TAX_FORM",
        "employee_last_name": "Desai",
        "box12_items": [{"code": "D", "amount": "200.00"}],
        "alertas_inconsistencias": [],
    }

    resultado = transformer.executar("w2_tax_form", "w2.pdf", raw_fields_ia, {}, _s3_inputs_vazio())
    box12 = resultado["dados_extraidos_do_documento"]["box12_items"][0]

    assert box12["code_a"] == "D"
    assert box12["amount_a"] == "200.00"
    assert box12["code_b"] is None
    assert box12["amount_b"] is None


# ==========================================================================
# ACCOUNT_STATEMENT — sub-objetos aninhados + listas de tamanho variável
# ==========================================================================

def test_merge_account_statement_campos_aninhados_your_details_e_balance():
    transformer = _novo_transformer()
    raw_fields_ia = {
        "tipo_classificado": "BANK_STATEMENT",
        "your_details": {
            "account_holder_name": "Jane Doe",
            "statement_period": "1 MAY 2021 to 31 MAY 2021",
            "account_number": "333 008755555",
            "account_name": "Jane Doe",
            "email_address": "Not Recorded",
        },
        "your_account_balance": {
            "opening_balance": "50,000.00",
            "closing_balance": "123,084.85",
        },
        "your_account_valuation": [],
        "alertas_inconsistencias": [],
    }

    resultado = transformer.executar("account_statement", "extrato.pdf", raw_fields_ia, {}, _s3_inputs_vazio())
    campos = resultado["dados_extraidos_do_documento"]

    assert campos["your_details"]["account_holder_name"] == "Jane Doe"
    assert campos["your_details"]["statement_period"] == "1 MAY 2021 to 31 MAY 2021"
    assert campos["your_account_balance"]["opening_balance"] == "50,000.00"
    assert campos["your_account_balance"]["closing_balance"] == "123,084.85"


def test_merge_account_statement_substitui_lista_de_valuation_pelo_tamanho_real():
    """
    O template tem só 2 linhas placeholder, mas o extrato de amostra tem 4
    opções de investimento. A lista inteira deve ser SUBSTITUÍDA (não casada
    posição a posição contra os 2 placeholders do template).
    """
    transformer = _novo_transformer()
    linhas_reais = [
        {"investment_option_name": "BT Active Balanced", "option_code": "210", "units": "1,3297.9090", "unit_price_$": "1,300", "value_$": "17,287.28", "percentage": "40"},
        {"investment_option_name": "First choice moderate", "option_code": "080", "units": "2,3000.5678", "unit_price_$": "100", "value_$": "23,005.68", "percentage": "30"},
        {"investment_option_name": "First choice Lifestaged 2001-09", "option_code": "010", "units": "7,100.9876", "unit_price_$": "900", "value_$": "63,908.89", "percentage": "20"},
        {"investment_option_name": "Perpetual Balanced growth", "option_code": "021", "units": "8,210.0021", "unit_price_$": "230", "value_$": "18,883.00", "percentage": "10"},
    ]
    raw_fields_ia = {
        "tipo_classificado": "BANK_STATEMENT",
        "your_account_valuation": linhas_reais,
        "account_value": {"value": "123,084.85", "percentage": "100.00"},
        "your_insurance_details": [
            {"benefit_type": "Amount paid on Death of Terminal illness", "insurance_cover_amount_$": "10,000.00", "benefit_amount_$": "17,000.00"},
            {"benefit_type": "Amount paid upon Total and Permanent Disablement", "insurance_cover_amount_$": "10,000.00", "benefit_amount_$": "17,000.00"},
        ],
        "alertas_inconsistencias": [],
    }

    resultado = transformer.executar("account_statement", "extrato.pdf", raw_fields_ia, {}, _s3_inputs_vazio())
    campos = resultado["dados_extraidos_do_documento"]

    assert len(campos["your_account_valuation"]) == 4
    assert campos["your_account_valuation"][0]["investment_option_name"] == "BT Active Balanced"
    assert campos["your_account_valuation"][3]["investment_option_name"] == "Perpetual Balanced growth"
    assert campos["account_value"]["value"] == "123,084.85"
    assert len(campos["your_insurance_details"]) == 2


def test_merge_account_statement_com_uma_unica_linha_de_valuation():
    """Não há número fixo de linhas — 1 linha também deve funcionar."""
    transformer = _novo_transformer()
    raw_fields_ia = {
        "tipo_classificado": "BANK_STATEMENT",
        "your_account_valuation": [
            {"investment_option_name": "Single Fund", "option_code": "999", "units": "10", "unit_price_$": "1", "value_$": "10.00", "percentage": "100"},
        ],
        "alertas_inconsistencias": [],
    }

    resultado = transformer.executar("account_statement", "extrato.pdf", raw_fields_ia, {}, _s3_inputs_vazio())
    campos = resultado["dados_extraidos_do_documento"]

    assert len(campos["your_account_valuation"]) == 1
    assert campos["your_account_valuation"][0]["investment_option_name"] == "Single Fund"


# ==========================================================================
# HOMEOWNERS_INSURANCE_APPLICATION — primary_applicant + co_applicant
# ==========================================================================

def test_merge_homeowners_insurance_distingue_primary_e_co_applicant():
    transformer = _novo_transformer()
    raw_fields_ia = {
        "tipo_classificado": "HOMEOWNERS_INSURANCE",
        "named_insured": "Ziggy Starpixel",
        "policy_number": "",
        "primary_applicant": {
            "name": "Ziggy Starpixel",
            "date_of_birth": "2/20/2000",
            "gender": "M",
            "marital_status": "S",
        },
        "co_applicant": {
            "name": "Luna Starlight-Glitterdust",
            "date_of_birth": "2/29/2000",
            "gender": "F",
            "marital_status": "S",
            "relationship_to_primary_applicant": "Domestic Partner",
        },
        "alertas_inconsistencias": [],
    }

    resultado = transformer.executar(
        "homeowners_insurance_application", "seguro.pdf", raw_fields_ia, {}, _s3_inputs_vazio()
    )
    campos = resultado["dados_extraidos_do_documento"]

    assert campos["named_insured"] == "Ziggy Starpixel"
    assert campos["primary_applicant"]["name"] == "Ziggy Starpixel"
    assert campos["primary_applicant"]["gender"] == "M"
    assert campos["co_applicant"]["name"] == "Luna Starlight-Glitterdust"
    assert campos["co_applicant"]["relationship_to_primary_applicant"] == "Domestic Partner"
    # Os dois blocos não podem se misturar
    assert campos["primary_applicant"]["name"] != campos["co_applicant"]["name"]


def test_merge_homeowners_insurance_sem_co_applicant_mantem_campos_nulos():
    """Se o documento não tiver co-requerente, o bloco deve continuar todo null,
    não deve herdar nada do primary_applicant nem quebrar."""
    transformer = _novo_transformer()
    raw_fields_ia = {
        "tipo_classificado": "HOMEOWNERS_INSURANCE",
        "named_insured": "Solo Applicant",
        "primary_applicant": {"name": "Solo Applicant", "gender": "M"},
        "co_applicant": {"name": None, "date_of_birth": None, "gender": None, "marital_status": None},
        "alertas_inconsistencias": [],
    }

    resultado = transformer.executar(
        "homeowners_insurance_application", "seguro.pdf", raw_fields_ia, {}, _s3_inputs_vazio()
    )
    campos = resultado["dados_extraidos_do_documento"]

    assert campos["primary_applicant"]["name"] == "Solo Applicant"
    assert campos["co_applicant"]["name"] is None


# ==========================================================================
# PAYROLL_CHECK — todos os campos são planos, sem estrutura aninhada
# ==========================================================================

def test_merge_payroll_check_campos_planos_do_cheque_de_john_stiles():
    transformer = _novo_transformer()
    raw_fields_ia = {
        "tipo_classificado": "PAYROLL_CHECK",
        "issuer_name": "ANY COMPANY CORP.",
        "payee_name": "JOHN STILES",
        "amount_numeric": "291.90",
        "amount_words": "TWO HUNDRED NINETY-ONE AND 90/100 DOLLARS",
        "sample_indicator": "SAMPLE",
        "non_negotiable_indicator": "NON-NEGOTIABLE",
        "void_indicator": "VOID",
        "alertas_inconsistencias": [],
    }

    resultado = transformer.executar("payroll_check", "check.pdf", raw_fields_ia, {}, _s3_inputs_vazio())
    campos = resultado["dados_extraidos_do_documento"]

    assert campos["payee_name"] == "JOHN STILES"
    assert campos["amount_numeric"] == "291.90"
    assert campos["sample_indicator"] == "SAMPLE"


# ==========================================================================
# REGRESSÃO — pay_stub continua usando o merge bespoke (não o genérico)
# ==========================================================================

def test_pay_stub_continua_usando_merge_bespoke_por_description():
    """
    Garante que a mudança não desviou pay_stub para o merge genérico.
    O casamento por 'description' (earnings_rows → template['earnings'])
    só existe no caminho bespoke — se isso quebrar, earnings ficaria vazio.
    """
    transformer = _novo_transformer()
    raw_fields_ia = {
        "tipo_classificado": "PAY_STUB",
        "nome_titular": "JOHN STILES",
        "earnings_rows": [
            {"description": "regular", "rate": "10.00", "hours": "32.00", "this_period": "320.00", "year_to_date": "16,640.00"},
        ],
        "alertas_inconsistencias": [],
    }

    resultado = transformer.executar("pay_stub", "holerite.pdf", raw_fields_ia, {}, _s3_inputs_vazio())
    earnings = resultado["dados_extraidos_do_documento"]["earnings"]
    linha_regular = next(e for e in earnings if e.get("description") == "regular")

    assert linha_regular["this_period"] == "320.00"
    assert linha_regular["year_to_date"] == "16,640.00"


# ==========================================================================
# INTEGRAÇÃO — merge genérico (IA) + overlay BDA (crítico) no mesmo doc
# ==========================================================================

def test_overlay_bda_sobrescreve_a_ia_em_campo_plano_do_w2():
    """
    BDA (fonte 2, mais confiável) deve prevalecer sobre a IA (fonte 1) quando
    os dois preenchem o mesmo campo plano — ordem de aplicação em executar().
    """
    transformer = _novo_transformer()
    raw_fields_ia = {
        "tipo_classificado": "W2_TAX_FORM",
        "employee_last_name": "Desai",
        "employer_name": "Valor incerto lido pela IA",
        "alertas_inconsistencias": [],
    }
    bda_json = {
        "inference_result": {"employer_name": "John Stiles"},
        "explainability_info": [{"employer_name": {"confidence": 0.95}}],
    }

    resultado = transformer.executar("w2_tax_form", "w2.pdf", raw_fields_ia, bda_json, _s3_inputs_vazio())
    campos = resultado["dados_extraidos_do_documento"]

    assert campos["employer_name"] == "John Stiles"
    assert resultado["confiabilidade_extracao"]["confianca_media"] == "0.9500"


# ==========================================================================
# GABARITO COMPLETO — replica CAMPO A CAMPO os 3 documentos de amostra reais
# (W2 de Arnav Desai, CNH de Maria Garcia, apólice de Ziggy/Luna) simulando
# uma resposta "perfeita" da IA seguindo exatamente o prompt escrito em
# handler.py. Isso não substitui rodar contra o Bedrock de verdade — mas
# prova que SE o Nova Lite responder o que o prompt pede, o merge produz
# a saída correta, campo por campo, sem perdas nem trocas. Serve também
# como referência viva do que "extração perfeita" significa para cada tipo.
# ==========================================================================

def test_gabarito_completo_w2_arnav_desai_todas_as_caixas():
    transformer = _novo_transformer()
    raw_fields_ia = {
        "tipo_classificado": "W2_TAX_FORM",
        "form_type": "W-2",
        "employee_social_security_number": "753-95-1846-13",
        "employer_identification_number": "4963147952",
        "employer_name": "John Stiles",
        "employer_address": "100 Main Street, Anytown, USA",
        "control_number": "753951852",
        "employee_first_name_and_initial": "Arnav",
        "employee_last_name": "Desai",
        "employee_address": "123 Any Street, Any Town, USA",
        "wages_tips_other_compensation": "100.00",
        "federal_income_tax_withheld": "500.00",
        "social_security_wages": "1000.00",
        "social_security_tax_withheld": "100.00",
        "medicare_wages_and_tips": "500.00",
        "medicare_tax_withheld": "5000.00",
        "social_security_tips": "500.00",
        "allocated_tips": "150.00",
        "dependent_care_benefits": "5000.00",
        "nonqualified_plans": "500.00",
        "state": "Any Town",
        "state_wages_tips_etc": "50.00",
        "state_income_tax": "500.00",
        "local_wages_tips_etc": "100.00",
        "local_income_tax": "550.00",
        "locality_name": "Any Town",
        "tax_year": "2022",
        "box12_items": [
            {"code": "A", "amount": "500.00"},
            {"code": "C", "amount": "1500.00"},
            {"code": "A", "amount": "500.00"},
            {"code": "B", "amount": "1000.00"},
        ],
        "alertas_inconsistencias": [],
    }

    resultado = transformer.executar("w2_tax_form", "lending_package_w2.pdf", raw_fields_ia, {}, _s3_inputs_vazio())
    c = resultado["dados_extraidos_do_documento"]

    # Identificação
    assert c["employer_name"] == "John Stiles"
    assert c["employer_identification_number"] == "4963147952"
    assert c["control_number"] == "753951852"
    assert c["employee_first_name_and_initial"] == "Arnav"
    assert c["employee_last_name"] == "Desai"
    # Caixas 1-8
    assert c["wages_tips_other_compensation"] == "100.00"
    assert c["federal_income_tax_withheld"] == "500.00"
    assert c["social_security_wages"] == "1000.00"
    assert c["social_security_tax_withheld"] == "100.00"
    assert c["medicare_wages_and_tips"] == "500.00"
    assert c["medicare_tax_withheld"] == "5000.00"
    assert c["social_security_tips"] == "500.00"
    assert c["allocated_tips"] == "150.00"
    # Caixas 10-11
    assert c["dependent_care_benefits"] == "5000.00"
    assert c["nonqualified_plans"] == "500.00"
    # Caixa 12 (a/b/c/d)
    assert c["box12_items"][0] == {
        "code_a": "A", "amount_a": "500.00",
        "code_b": "C", "amount_b": "1500.00",
        "code_c": "A", "amount_c": "500.00",
        "code_d": "B", "amount_d": "1000.00",
    }
    # Caixas 15-20
    assert c["state"] == "Any Town"
    assert c["state_wages_tips_etc"] == "50.00"
    assert c["state_income_tax"] == "500.00"
    assert c["local_wages_tips_etc"] == "100.00"
    assert c["local_income_tax"] == "550.00"
    assert c["locality_name"] == "Any Town"
    assert c["tax_year"] == "2022"


def test_gabarito_completo_driver_license_maria_garcia_com_ghost_dob():
    transformer = _novo_transformer()
    raw_fields_ia = {
        "tipo_classificado": "DRIVER_LICENSE",
        "identification_document_type": "DRIVER LICENSE",
        "document_number": "736HDV7874JSB",
        "full_name": "MARIA GARCIA",
        "date_of_birth": "03/18/2001",
        "issue_date": "03/18/2018",
        "expiration_date": "01/20/2028",
        "issuing_state": "MA",
        "issuing_country": "USA",
        "address": "100 MARKET STREET, BIGTOWN, MA, 02801",
        "class": "D",
        "restrictions": "NONE",
        "endorsements": "NONE",
        "sex": "F",
        "height": '4-6"',
        "eye_color": "BLK",
        "revision_date": "03/12/2017",
        # Ghost DOB: a mesma data 03/18/2001 reimpressa perto da assinatura,
        # separada do campo numerado "3 DOB" — é isso que o teste garante
        # que NÃO se perde nem se confunde com date_of_birth.
        "security_ghost_dob": "03/18/2001",
        "alertas_inconsistencias": [],
    }

    resultado = transformer.executar("driver_license", "lending_package_ID_Card.pdf", raw_fields_ia, {}, _s3_inputs_vazio())
    c = resultado["dados_extraidos_do_documento"]

    assert c["full_name"] == "MARIA GARCIA"
    assert c["document_number"] == "736HDV7874JSB"
    assert c["date_of_birth"] == "03/18/2001"
    assert c["security_ghost_dob"] == "03/18/2001"
    assert c["issue_date"] == "03/18/2018"
    assert c["expiration_date"] == "01/20/2028"
    assert c["class"] == "D"
    assert c["sex"] == "F"
    assert c["height"] == '4-6"'
    assert c["eye_color"] == "BLK"
    assert c["issuing_state"] == "MA"


def test_gabarito_completo_driver_license_sem_ghost_dob_nao_duplica():
    """Se a IA não relatar uma segunda data (documento sem esse elemento de
    segurança, ou não visível), security_ghost_dob deve ficar null — o merge
    genérico NUNCA deve copiar date_of_birth para lá sozinho."""
    transformer = _novo_transformer()
    raw_fields_ia = {
        "tipo_classificado": "DRIVER_LICENSE",
        "full_name": "MARIA GARCIA",
        "date_of_birth": "03/18/2001",
        "alertas_inconsistencias": [],
    }

    resultado = transformer.executar("driver_license", "cnh.pdf", raw_fields_ia, {}, _s3_inputs_vazio())
    c = resultado["dados_extraidos_do_documento"]

    assert c["date_of_birth"] == "03/18/2001"
    assert c["security_ghost_dob"] is None


def test_gabarito_completo_homeowners_ziggy_e_luna_blocos_nao_se_misturam():
    """
    Replica o pacote real: OCR devolve rótulos e depois valores em blocos
    separados (ver POLÍTICA DE COLUNAS no prompt). Este teste garante que,
    mesmo com os dois applicants tendo o MESMO padrão de campos (DOB/Gender/
    Marital Status), primary e co-applicant não se cruzam — inclusive o
    caso de 'education_level' vazio para um e preenchido para o outro.
    """
    transformer = _novo_transformer()
    raw_fields_ia = {
        "tipo_classificado": "HOMEOWNERS_INSURANCE",
        "named_insured": "Ziggy Starpixel",
        "mailing_address": "42 Rainbow Sparkle Boulevard, Unicornville, NV 12345",
        "primary_email": "rainbow.unicorn.987654@fakeemail.nowhere",
        "primary_phone": "555 555 1212",
        "alternate_phone": "555 555 1213",
        "insurance_company": "Fake Insurance Co",
        "insurance_company_address": "650 Davis Street, San Francisco, CA 94111",
        "insured_property_address": "42 Rainbow Sparkle Boulevard, Unicornville, NV 12345",
        "primary_applicant": {
            "name": "Ziggy Starpixel",
            "date_of_birth": "2/20/2000",
            "gender": "M",
            "marital_status": "S",
            "education_level": None,
            "existing_policy": "123456",
            "drivers_license_number": "1234567A",
            "dl_state": "NV",
            "currently_insured_auto": "Fake Auto Ins Co",
            "length_current_auto_carrier": "1 Year",
            "length_prior_auto_carrier": "2 years",
            "years_prior_property_company": "1 Year",
            "current_property_policy_type": "Home",
        },
        "co_applicant": {
            "name": "Luna Starlight-Glitterdust",
            "date_of_birth": "2/29/2000",
            "gender": "F",
            "marital_status": "S",
            "education_level": "Graduate",
            "relationship_to_primary_applicant": "Domestic Partner",
            "drivers_license_number": "987654A",
            "dl_state": "NV",
            "currently_insured_auto": "Fake Auto Ins Co.",
            "length_current_auto_carrier": "1 year",
            "length_prior_auto_carrier": "6 months",
        },
        "alertas_inconsistencias": [],
    }

    resultado = transformer.executar(
        "homeowners_insurance_application", "homeowner_insurance_application_sample.pdf",
        raw_fields_ia, {}, _s3_inputs_vazio()
    )
    c = resultado["dados_extraidos_do_documento"]

    # Topo (fora dos blocos de applicant)
    assert c["named_insured"] == "Ziggy Starpixel"
    assert c["primary_email"] == "rainbow.unicorn.987654@fakeemail.nowhere"

    # Primary applicant — existing_policy e drivers_license_number não se invertem
    pa = c["primary_applicant"]
    assert pa["name"] == "Ziggy Starpixel"
    assert pa["existing_policy"] == "123456"
    assert pa["drivers_license_number"] == "1234567A"
    assert pa["education_level"] is None  # em branco no documento real

    # Co-applicant — campos completamente diferentes do primary
    ca = c["co_applicant"]
    assert ca["name"] == "Luna Starlight-Glitterdust"
    assert ca["education_level"] == "Graduate"
    assert ca["relationship_to_primary_applicant"] == "Domestic Partner"
    assert ca["drivers_license_number"] == "987654A"
    assert ca["currently_insured_auto"] == "Fake Auto Ins Co."
    assert ca["length_current_auto_carrier"] == "1 year"
    assert ca["length_prior_auto_carrier"] == "6 months"

    # Os dois blocos nunca podem compartilhar valores de identidade
    assert pa["name"] != ca["name"]
    assert pa["date_of_birth"] != ca["date_of_birth"]
    assert pa["drivers_license_number"] != ca["drivers_license_number"]