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
    """Garante o fluxo feliz se os tamanhos e extensões forem válidos e retorna o layout POST."""
    
    # 🛡️ ALINHAMENTO DE MOCK: Agora implementa a assinatura do Presigned POST
    class MockS3Client:
        def generate_presigned_post(self, Bucket, Key, Fields=None, Conditions=None, ExpiresIn=3600):
            return {
                "url": f"https://{Bucket}.s3.amazonaws.com",
                "fields": {
                    "key": Key,
                    "AWSAccessKeyId": "mock-access-key",
                    "policy": "mock-cryptographic-policy",
                    "signature": "mock-signature"
                }
            }

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
    
    # 🚀 AS SERÇÕES ATUALIZADAS: Valida o novo contrato multipart exigido pelo S3
    doc_upload_config = body["uploads"]["contrato_locacao.pdf"]
    assert "url" in doc_upload_config
    assert "fields" in doc_upload_config
    assert "s3Key" in doc_upload_config
    assert doc_upload_config["fields"]["key"] == doc_upload_config["s3Key"]

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