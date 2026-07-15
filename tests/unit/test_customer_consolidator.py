import json
import pytest
from unittest.mock import patch, MagicMock

# Importa as funções que serão testadas
from src.lambdas.customer_consolidator.handler import handler, calcular_scorecard_financeiro, safe_float

# --- Testes para a função utilitária safe_float ---
@pytest.mark.parametrize("input_val, expected_output", [
    ("R$ 1.234,56", 1234.56),
    ("1,234.56", 1234.56),
    ("1234.56", 1234.56),
    ("1234,56", 1234.56),
    (1234.56, 1234.56),
    (1234, 1234.0),
    (None, 0.0),
    ("Texto Inválido", 0.0),
    ("", 0.0)
])
def test_safe_float_converte_corretamente_diferentes_formatos(input_val, expected_output):
    """Garante que a conversão de valores monetários é robusta e segura."""
    assert safe_float(input_val) == expected_output

# --- Testes para a lógica de negócio: calcular_scorecard_financeiro ---
#
# IMPORTANTE: estes cenários foram recalculados a partir da fórmula REAL
# implementada em calcular_scorecard_financeiro (capacidade de amortização
# BACEN 30% + meses de reserva de liquidez + 4 checks de KYC nomeados
# nome_consistente_entre_documentos / documento_identificacao_presente /
# comprovante_renda_presente / extrato_bancario_presente). A versão anterior
# deste teste comparava um dict a um int (sempre False) e usava uma chave de
# KYC (data_nascimento_consistente) que a função nunca leu — por isso nunca
# detectou a regressão de verdade.
@pytest.mark.parametrize("validacao, docs, expected_score, expected_faixa", [
    # Cenário ideal: teto de todos os fatores (capacidade + liquidez + KYC completo)
    (
        {
            "nome_consistente_entre_documentos": True,
            "documento_identificacao_presente": True,
            "comprovante_renda_presente": True,
            "extrato_bancario_presente": True,
        },
        [
            {"tipo_documento": "PAY_STUB", "campos_extraidos": {"Gross Pay": "12000.00"}},
            {"tipo_documento": "BANK_STATEMENT", "campos_extraidos": {"closing_balance": "25000.00"}}
        ],
        # 300 base + 300 capacidade (parcela 3600 >= 3000) + 200 liquidez (25000/3600=6,9 meses >= 6)
        # + 100 nome + 50 doc + 30 comprovante_renda + 20 extrato = 1000 (teto)
        1000,
        "baixo_risco",
    ),
    # Cenário mediano: renda/saldo moderados, inconsistência de nome entre documentos
    (
        {
            "nome_consistente_entre_documentos": False,
            "documento_identificacao_presente": True,
            "comprovante_renda_presente": True,
            "extrato_bancario_presente": True,
        },
        [
            {"tipo_documento": "COMPROVANTE_RENDA", "campos_extraidos": {"amount_numeric": 2600}},
            {"tipo_documento": "EXTRATO_BANCARIO", "campos_extraidos": {"saldo_bancario_fechamento": "R$ 4.500,00"}}
        ],
        # 300 base + 100 capacidade (parcela 780, faixa 500-1500) + 100 liquidez (4500/780=5,8 meses, faixa 3-6)
        # + 0 nome (inconsistente) + 50 doc + 30 comprovante_renda + 20 extrato = 600
        600,
        "risco_medio",
    ),
    # Cenário de recusa: pacote vazio, KYC zerado — piso absoluto da fórmula
    (
        {
            "nome_consistente_entre_documentos": False,
            "documento_identificacao_presente": False,
            "comprovante_renda_presente": False,
            "extrato_bancario_presente": False,
        },
        [],
        # Nenhum fator positivo: min(1000, max(300, 300)) = 300 (piso absoluto)
        300,
        "alto_risco",
    ),
])
def test_calcular_scorecard_financeiro_para_diferentes_perfis(validacao, docs, expected_score, expected_faixa):
    """Garante que o algoritmo de scorecard calcula pontuação e faixa de risco corretamente."""
    resultado = calcular_scorecard_financeiro(validacao, docs)
    assert resultado["score_calculado"] == expected_score
    assert resultado["faixa"] == expected_faixa


def test_parcela_abaixo_do_minimo_habitacional_e_penalidade_em_motivos_negativos():
    """
    Decisão de política tomada pelo Weriton após a primeira correção: quando
    renda_maxima > 0 mas a parcela recomendada (30% da renda) fica abaixo de
    USD 500 (piso da faixa 'mínima'), isso é tratado como PENALIDADE real
    (score -= 30) em motivos_negativos — não como bônus marginal em
    motivos_positivos (que foi o fix anterior, só corrigindo a categorização
    sem mudar o sinal). Usa os números reais do caso de teste do Weriton:
    renda 291.90 -> parcela 87.57 (dentro de 0-500). O piso de score_final =
    max(300, score) garante que a subtração nunca gera um número abaixo de
    300, mesmo se essa fosse a única fonte de pontos do pacote.
    """
    validacao = {
        "nome_consistente_entre_documentos": True,
        "documento_identificacao_presente": True,
        "comprovante_renda_presente": True,
        "extrato_bancario_presente": False,
    }
    docs = [
        {"tipo_documento": "PAYROLL_CHECK", "dados_extraidos_do_documento": {"amount_numeric": "$291.90"}},
    ]

    resultado = calcular_scorecard_financeiro(validacao, docs)

    assert resultado["parcela_maxima_estimada"] == pytest.approx(87.57, abs=0.01)
    textos_positivos = " | ".join(resultado["motivos_positivos"])
    textos_negativos = " | ".join(resultado["motivos_negativos"])

    assert "abaixo do mínimo habitacional" in textos_negativos
    assert "abaixo do mínimo habitacional" not in textos_positivos
    # score: 300 base - 30 (parcela baixa) + 100 nome + 50 doc + 30 comprovante_renda
    # + 0 extrato (ausente) = 450
    assert resultado["score_calculado"] == 450

# --- Testes para o handler principal ---
#
# IMPORTANTE: o teste anterior mockava `bedrock_runtime.invoke_model` com uma
# resposta de texto livre, e esperava `cliente.score_credito.valor`. O handler
# real chama `bedrock_runtime.converse` (tool calling) só para a validação KYC
# cruzada — o score em si é 100% determinístico via calcular_scorecard_financeiro
# (decisão arquitetural para conformidade com o Marco Legal da IA, ver docstring
# de calcular_scorecard_financeiro). A chave gravada é sempre "pontuacao".
@patch.dict("os.environ", {"BUCKET_SAIDA": "bucket-teste-saida"})
@patch("src.lambdas.customer_consolidator.handler.s3_client")
@patch("src.lambdas.customer_consolidator.handler.bedrock_runtime")
def test_handler_consolida_e_calcula_score_com_sucesso(mock_bedrock, mock_s3):
    """
    Garante que o handler orquestra a chamada ao Bedrock (validação KYC via
    tool calling), o cálculo determinístico do score e a gravação dos DOIS
    artefatos (customer_consolidated.json + output.json) no S3.
    """
    # 1. Mock do Bedrock: resposta de tool calling (converse), não texto livre
    mock_bedrock.converse.return_value = {
        "usage": {"inputTokens": 200, "outputTokens": 80},
        "output": {
            "message": {
                "content": [
                    {
                        "toolUse": {
                            "name": "consolidar_e_validar_dados_esteira",
                            "input": {
                                "validacao": {
                                    "nome_consistente_entre_documentos": True,
                                    "documento_identificacao_presente": True,
                                    "comprovante_renda_presente": True,
                                    "extrato_bancario_presente": True,
                                }
                            },
                        }
                    }
                ]
            }
        },
    }

    # 2. Evento de entrada
    evento_entrada = {
        "package_id": "pkg-consolidar-123",
        "bda_output_bucket": "bucket-teste-saida",
        "execute_score": True,
        "json_estruturado": {
            "documentos_analisados": [
                {"tipo_documento": "PAY_STUB", "arquivo_original": "holerite.pdf", "campos_extraidos": {"Gross Pay": "15000"}},
                {"tipo_documento": "BANK_STATEMENT", "arquivo_original": "extrato.pdf", "campos_extraidos": {"closing_balance": "20000"}}
            ]
        }
    }

    # 3. Execução
    resultado = handler(evento_entrada, None)

    # 4. Asserções
    mock_bedrock.converse.assert_called_once()
    assert mock_s3.put_object.call_count == 2  # customer_consolidated.json + output.json

    gravacoes = {c.kwargs["Key"]: c.kwargs["Body"] for c in mock_s3.put_object.call_args_list}
    assert "results/clientes/pkg-consolidar-123/customer_consolidated.json" in gravacoes
    assert "results/packages/pkg-consolidar-123/output.json" in gravacoes

    # score esperado: 300 base + 300 capacidade (parcela 4500 >= 3000) + 100 liquidez
    # (20000/4500 = 4.4 meses, faixa 3-6) + 100 nome + 50 doc + 30 comprovante + 20 extrato = 900
    crm_gravado = json.loads(gravacoes["results/clientes/pkg-consolidar-123/customer_consolidated.json"])
    assert crm_gravado["score_credito"]["pontuacao"] == 900

    pacote_gravado = json.loads(gravacoes["results/packages/pkg-consolidar-123/output.json"])
    assert pacote_gravado["cliente"]["score_credito"]["pontuacao"] == 900

    assert resultado["execute_score"] is True
    assert resultado["json_estruturado"]["cliente"]["score_credito"]["pontuacao"] == 900

@patch.dict("os.environ", {"BUCKET_SAIDA": "bucket-teste-saida"})
@patch("src.lambdas.customer_consolidator.handler.s3_client")
def test_handler_busca_dados_do_s3_se_nao_estiverem_no_evento(mock_s3):
    """
    Testa o fallback: se 'json_estruturado' não vier no evento,
    a função deve buscá-lo no S3.
    """
    # 1. Mocks
    mock_s3_get_content = { "documentos_analisados": [] }
    mock_s3.get_object.return_value = {
        "Body": MagicMock(read=lambda: json.dumps(mock_s3_get_content).encode('utf-8'))
    }
    
    # Mock do Bedrock para a função não quebrar
    with patch("src.lambdas.customer_consolidator.handler.bedrock_runtime") as mock_bedrock:
        mock_bedrock_response_content = {
            "output": {"message": {"content": [{"text": json.dumps({"cliente": {}, "validacao": {}})}]}}
        }
        mock_bedrock.invoke_model.return_value = {
            "body": MagicMock(read=lambda: json.dumps(mock_bedrock_response_content).encode('utf-8'))
        }

        # 2. Evento de entrada (sem 'json_estruturado')
        evento_entrada = {
            "package_id": "pkg-fallback-s3-456",
            "bda_output_bucket": "bucket-teste-saida"
        }

        # 3. Execução
        handler(evento_entrada, None)

        # 4. Asserção
        mock_s3.get_object.assert_called_once_with(
            Bucket="bucket-teste-saida",
            Key="results/packages/pkg-fallback-s3-456/output.json"
        )