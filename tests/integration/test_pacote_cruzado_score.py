"""
Teste de integração: prova que o pipeline cruza dados de MÚLTIPLOS documentos
do mesmo pacote para gerar um único score — não apenas que cada Lambda
funciona isolada com mocks.

Fluxo coberto (sem tocar S3/Bedrock/DynamoDB reais):
  SchemaTransformer (extração individual, 2 subtipos diferentes)
    -> calcular_scorecard_financeiro (score determinístico cruzado)
    -> montar_crm_json (artefato 1: customer_consolidated.json)
    -> renderizar_crm_consolidado (o MESMO renderer que excel_generator.py usa)

Os dados replicam os documentos de amostra reais do projeto (holerite de
John Stiles + extrato de Jane Doe), incluindo a divergência de nome entre
eles — de propósito, para provar que o alerta de KYC cruzado dispara.
"""
import datetime
from openpyxl import Workbook

from src.lambdas.nova_structurer.schema_transformer import SchemaTransformer
from src.lambdas.nova_structurer.handler import MAPA_TEMPLATES
from src.lambdas.customer_consolidator.handler import (
    calcular_scorecard_financeiro,
    montar_crm_json,
)
from src.lambdas.excel_generator.handler import (
    renderizar_crm_consolidado,
    aplicar_estilo_corporativo,
    auto_ajustar_largura_colunas,
)


def _s3_inputs(nome):
    return {
        "bucket_entrada": "in", "key_entrada": f"packages/pkg-e2e/{nome}",
        "bucket_saida": "out", "key_bda": f"bda-output/pkg-e2e/{nome}/custom_output.json",
        "key_resultado": f"results/x/{nome}_structured.json",
    }


def _construir_pacote_dois_documentos():
    """Monta os dois documentos analisados usando o SchemaTransformer real
    (não JSON hardcoded) — se o merge genérico quebrar, este teste quebra."""
    transformer = SchemaTransformer(MAPA_TEMPLATES)

    raw_ia_paystub = {
        "tipo_classificado": "PAY_STUB",
        "nome_titular": "JOHN STILES",
        "earnings_rows": [
            {"description": "regular", "rate": "10.00", "hours": "32.00", "this_period": "320.00", "year_to_date": "16,640.00"},
        ],
        "alertas_inconsistencias": [],
    }
    bda_paystub = {
        "inference_result": {"employee_name": "JOHN STILES", "net_pay_this_period": "291.90"},
        "explainability_info": [{"employee_name": {"confidence": 0.93}, "net_pay_this_period": {"confidence": 0.91}}],
    }
    doc_paystub = transformer.executar(
        "pay_stub", "lending_package_pay_stub.pdf", raw_ia_paystub, bda_paystub, _s3_inputs("paystub")
    )
    doc_paystub["tipo_documento"] = "comprovante_renda"
    doc_paystub["subtipo_documento"] = "pay_stub"

    raw_ia_extrato = {
        "tipo_classificado": "BANK_STATEMENT",
        "your_details": {"account_holder_name": "Jane Doe", "account_number": "333 008755555"},
        "your_account_balance": {"opening_balance": "50,000.00", "closing_balance": "123,084.85"},
        "your_account_valuation": [
            {"investment_option_name": "BT Active Balanced", "value_usd": "17,287.28", "percentage": "40"},
            {"investment_option_name": "First choice moderate", "value_usd": "23,005.68", "percentage": "30"},
            {"investment_option_name": "First choice Lifestaged 2001-09", "value_usd": "63,908.89", "percentage": "20"},
            {"investment_option_name": "Perpetual Balanced growth", "value_usd": "18,883.00", "percentage": "10"},
        ],
        "alertas_inconsistencias": [],
    }
    doc_extrato = transformer.executar(
        "account_statement", "lending_package_account_statement.pdf", raw_ia_extrato, {}, _s3_inputs("extrato")
    )
    doc_extrato["tipo_documento"] = "extrato_bancario"
    doc_extrato["subtipo_documento"] = "account_statement"

    return [doc_paystub, doc_extrato]


def test_score_cruza_renda_do_paystub_com_saldo_do_extrato():
    """O score é UM SÓ, calculado a partir de DOIS documentos diferentes —
    não é a soma nem a média de scores individuais por documento."""
    docs = _construir_pacote_dois_documentos()
    validacao = {
        "nome_consistente_entre_documentos": False,
        "documento_identificacao_presente": False,
        "comprovante_renda_presente": True,
        "extrato_bancario_presente": True,
    }

    score = calcular_scorecard_financeiro(validacao, docs)

    # Renda veio do pay_stub (net_pay.this_period), saldo veio do extrato
    # (your_account_balance.closing_balance) — dois documentos, dois campos
    # de fontes de dados completamente diferentes, um resultado só.
    assert score["renda_maxima"] == 291.90
    assert score["saldo_maximo"] == 123084.85
    assert 300 <= score["score_calculado"] <= 1000


def test_divergencia_de_nome_entre_documentos_vira_alerta_de_compliance():
    """John Stiles (pay_stub) vs Jane Doe (extrato) no mesmo pacote deve
    gerar um alerta explícito — é exatamente o tipo de inconsistência que
    o KYC cruzado existe para pegar."""
    docs = _construir_pacote_dois_documentos()
    validacao = {"nome_consistente_entre_documentos": False}

    score = calcular_scorecard_financeiro(validacao, docs)

    assert any("nome" in m.lower() for m in score["alertas_compliance"] + score["motivos_negativos"])


def test_artefato_consolidado_json_e_excel_saem_consistentes_entre_si():
    """
    Gera o customer_consolidated.json (montar_crm_json) e o Excel a partir
    DELE (renderizar_crm_consolidado — a mesma função que excel_generator.py
    usa em produção) e confere que os dois concordam no valor do score.
    Isso pega exatamente o tipo de mismatch de schema que quebra o Excel
    consolidado silenciosamente (chave errada, branch de dispatch errado).
    """
    docs = _construir_pacote_dois_documentos()
    validacao = {
        "nome_consistente_entre_documentos": False,
        "comprovante_renda_presente": True,
        "extrato_bancario_presente": True,
    }
    score = calcular_scorecard_financeiro(validacao, docs)

    consolidado_ia = {
        "cliente": {
            "nome": "JOHN STILES",
            "documento_identificacao": "987-65-4321",
            "classificacao_risco": {"justificativa": "Renda comprovada; saldo pertence a outro titular."},
        },
        "validacao": validacao,
    }
    crm_json = montar_crm_json(
        package_id="pkg-e2e",
        consolidado_ia=consolidado_ia,
        score=score,
        docs_analisados=docs,
        tokens_total={"total": 1234},
        timestamp_inicio=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )

    # O JSON tem que ter exatamente o shape que excel_generator.py espera
    # para disparar o branch renderizar_crm_consolidado (não o branch legado
    # nem o branch de documento individual).
    assert "requerente" in crm_json and "score_credito" in crm_json
    assert crm_json["score_credito"]["pontuacao"] == score["score_calculado"]

    wb = Workbook()
    ws = wb.active
    ws.append(["Propriedade Analisada", "Valor Identificado"])
    renderizar_crm_consolidado(ws, crm_json)
    aplicar_estilo_corporativo(ws)
    auto_ajustar_largura_colunas(ws)

    # Varre a planilha gerada e confirma que a pontuação do JSON aparece
    # literalmente na célula certa — prova que Excel e JSON não divergem.
    linha_pontuacao = next(
        (row for row in ws.iter_rows(values_only=True) if row and row[0] == "Pontuação"), None
    )
    assert linha_pontuacao is not None
    assert str(score["score_calculado"]) in str(linha_pontuacao[1])