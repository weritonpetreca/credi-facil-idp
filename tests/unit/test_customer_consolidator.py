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
@pytest.mark.parametrize("validacao, docs, expected_score", [
    # Cenário ideal: pontuação máxima
    (
        {"nome_consistente_entre_documentos": True, "data_nascimento_consistente": True, "documento_identificacao_presente": True},
        [
            {"tipo_documento": "PAY_STUB", "campos_extraidos": {"Gross Pay": "6000.00"}},
            {"tipo_documento": "BANK_STATEMENT", "campos_extraidos": {"closing_balance": "15000.00"}}
        ],
        1000 # (300 base + 150 kyc + 450 renda + 400 saldo)
    ),
    # Cenário mediano: renda e saldo menores, KYC inconsistente
    (
        {"nome_consistente_entre_documentos": True, "data_nascimento_consistente": False, "documento_identificacao_presente": True},
        [
            {"tipo_documento": "COMPROVANTE_RENDA", "campos_extraidos": {"amount_numeric": 2600}},
            {"tipo_documento": "EXTRATO_BANCARIO", "campos_extraidos": {"saldo_bancario_fechamento": "R$ 4.500,00"}}
        ],
        800 # (300 base + 100 kyc + 300 renda + 100 saldo)
    ),
    # Cenário de recusa: pontuação mínima
    (
        {"nome_consistente_entre_documentos": False, "data_nascimento_consistente": False, "documento_identificacao_presente": False},
        [], # Sem documentos de renda/saldo
        350 # (300 base + 0 kyc + 50 renda + 0 saldo)
    )
])
def test_calcular_scorecard_financeiro_para_diferentes_perfis(validacao, docs, expected_score):
    """Garante que o algoritmo de scorecard calcula a pontuação corretamente."""
    score = calcular_scorecard_financeiro(validacao, docs)
    assert score == expected_score

# --- Testes para o handler principal ---
@patch.dict("os.environ", {"BUCKET_SAIDA": "bucket-teste-saida"})
@patch("src.lambdas.customer_consolidator.handler.s3_client")
@patch("src.lambdas.customer_consolidator.handler.bedrock_runtime")
def test_handler_consolida_e_calcula_score_com_sucesso(mock_bedrock, mock_s3):
    """
    Garante que o handler orquestra a chamada ao Bedrock, o cálculo do score
    e a gravação do resultado no S3.
    """
    # 1. Mocks
    mock_bedrock_response_content = {
        "output": { "message": { "content": [{ "text": json.dumps({
            "cliente": { "nome": "CLIENTE TESTE" },
            "validacao": { "nome_consistente_entre_documentos": True, "data_nascimento_consistente": True, "documento_identificacao_presente": True }
        })}]}}
    }
    mock_bedrock.invoke_model.return_value = {
        "body": MagicMock(read=lambda: json.dumps(mock_bedrock_response_content).encode('utf-8'))
    }

    # 2. Evento de entrada
    evento_entrada = {
        "package_id": "pkg-consolidar-123",
        "bda_output_bucket": "bucket-teste-saida",
        "json_estruturado": {
            "documentos_analisados": [
                {"tipo_documento": "PAY_STUB", "campos_extraidos": {"Gross Pay": "15000"}},
                {"tipo_documento": "BANK_STATEMENT", "campos_extraidos": {"closing_balance": "20000"}}
            ]
        }
    }

    # 3. Execução
    resultado = handler(evento_entrada, None)

    # 4. Asserções
    mock_bedrock.invoke_model.assert_called_once()
    mock_s3.put_object.assert_called_once()
    
    args, kwargs = mock_s3.put_object.call_args
    assert kwargs["Bucket"] == "bucket-teste-saida"
    assert kwargs["Key"] == "results/clientes/pkg-consolidar-123/customer_consolidated.json"
    
    body_gravado = json.loads(kwargs["Body"])
    assert body_gravado["cliente"]["score_credito"]["valor"] == 1000

    assert resultado["cliente"]["score_credito"]["valor"] == 1000
    assert "json_estruturado" in resultado

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