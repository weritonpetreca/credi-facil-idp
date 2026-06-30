import json
import pytest
from src.lambdas.pre_signed_url.handler import handler

@pytest.fixture
def api_gateway_event():
    """Simula o novo contrato de dados exigido pelo SRS v2.0 com validação de tamanho."""
    return {
        "requestContext": {
            "authorizer": {
                "claims": {
                    "email": "analista@credifacil.com"
                }
            }
        },
        "body": json.dumps({
            "documentos": [
                {"nome": "contrato_locacao.pdf", "tamanho": 512000},
                {"nome": "rg_frente.png", "tamanho": 204800}
            ],
            "execute_score": True
        })
    }

def test_deve_gerar_urls_pre_assinadas_com_sucesso(api_gateway_event, monkeypatch):
    """Garante o fluxo feliz se os tamanhos e extensões forem válidos."""
    # 🛡️ ISOLAMENTO TOTAL: Moca o S3 para não fazer chamadas reais de rede
    class MockS3Client:
        def generate_presigned_url(self, ClientMethod, Params, ExpiresIn):
            return f"https://mock-s3-bucket.s3.amazonaws.com/{Params['Key']}?token=mocked"

    # 🛡️ ISOLAMENTO TOTAL: Moca o DynamoDB para evitar side-effects em tabelas reais
    class MockDynamoClient:
        def put_item(self, TableName, Item):
            return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    monkeypatch.setattr("src.lambdas.pre_signed_url.handler.s3_client", MockS3Client())
    monkeypatch.setattr("src.lambdas.pre_signed_url.handler.db_client", MockDynamoClient())

    response = handler(api_gateway_event, None)
    assert response["statusCode"] == 200
    
    body = json.loads(response["body"])
    assert "package_id" in body
    assert "uploads" in body
    assert "contrato_locacao.pdf" in body["uploads"]
    assert "uploadUrl" in body["uploads"]["contrato_locacao.pdf"]
    assert "s3Key" in body["uploads"]["contrato_locacao.pdf"]

def test_deve_rejeitar_se_o_arquivo_ultrapassar_dez_megabytes(api_gateway_event, monkeypatch):
    """Proteção FinOps: Bloqueia uploads gigantes na borda da API."""
    class MockDynamoClient:
        def put_item(self, TableName, Item):
            return {}

    monkeypatch.setattr("src.lambdas.pre_signed_url.handler.db_client", MockDynamoClient())

    event = api_gateway_event
    event["body"] = json.dumps({
        "documentos": [
            {"nome": "video_pesado.mp4", "tamanho": 50 * 1024 * 1024} # 50 MB
        ],
        "execute_score": False
    })

    response = handler(event, None)
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "erro" in body
    assert "tamanho" in body["erro"].lower()