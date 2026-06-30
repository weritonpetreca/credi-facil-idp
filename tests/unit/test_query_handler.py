import json
import pytest
from unittest.mock import MagicMock
# 🚀 IMPORTAÇÃO DO MÓDULO: Evita bugs de ciclo de vida do Python
import src.lambdas.query_handler.handler as query_handler

class MockS3Body:
    """Simula o fluxo de leitura (streaming) de um arquivo vindo do S3."""
    def __init__(self, content_dict):
        self.content_str = json.dumps(content_dict)
    def read(self):
        return self.content_str.encode("utf-8")

@pytest.fixture
def api_event():
    """Gera o payload de evento padrão que o API Gateway injeta na rota GET."""
    return {
        "pathParameters": {"packageId": "8f3b9c2e-4a1d-4f7b-9c3e-2a1b4c7d5e6f"}
    }

def test_query_handler_deve_retornar_apenas_status_se_estiver_em_processamento(api_event, monkeypatch):
    """Garante que se o lote estiver rodando na IA, não tenta buscar nada no S3."""
    mock_db = MagicMock()
    mock_db.get_item.return_value = {
        "Item": {
            "PK": {"S": "8f3b9c2e-4a1d-4f7b-9c3e-2a1b4c7d5e6f"},
            "SK": {"S": "METADATA"},
            "status": {"S": "PROCESSING"},
            "uploadedBy": {"S": "analista-weriton"},
            "uploadedAt": {"S": "2026-06-16T14:30:00Z"}
        }
    }
    monkeypatch.setattr(query_handler, "db_client", mock_db)

    response = query_handler.handler(api_event, None)
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert body["status"] == "PROCESSING"
    assert "dados_extraidos" not in body

def test_query_handler_deve_trazer_json_do_s3_se_status_for_completed(api_event, monkeypatch):
    """Garante o download e assinatura de links quando o processamento finaliza com sucesso."""
    mock_db = MagicMock()
    mock_db.get_item.return_value = {
        "Item": {
            "PK": {"S": "8f3b9c2e-4a1d-4f7b-9c3e-2a1b4c7d5e6f"},
            "SK": {"S": "METADATA"},
            "status": {"S": "COMPLETED"},
            "uploadedBy": {"S": "analista-weriton"},
            "uploadedAt": {"S": "2026-06-16T14:30:00Z"},
            "resultS3Key": {"S": "results/8f3b9c2e-4a1d-4f7b-9c3e-2a1b4c7d5e6f/output.json"}
        }
    }

    # Simula a massa de dados final estruturada que o Consolidador salvou no S3
    payload_s3 = {
        "documentos_analisados": [
            {
                "arquivo_original": "holerite.pdf", 
                "tipo_documento": "comprovante_renda",
                "s3_key_resultado": "results/comprovante_renda/pay_stub/pkg-123/holerite_structured.json"
            }
        ]
    }
    
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": MockS3Body(payload_s3)}
    
    # 🛡️ SOLUÇÃO DEFINITIVA DO BUG: Obriga o construtor a retornar uma String válida (texto plano)
    mock_s3.generate_presigned_url.return_value = "https://credifacil-storage.s3.amazonaws.com/mock-signed-url"

    monkeypatch.setattr(query_handler, "db_client", mock_db)
    monkeypatch.setattr(query_handler, "s3_client", mock_s3)

    response = query_handler.handler(api_event, None)
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert body["status"] == "COMPLETED"
    assert "dados_extraidos" in body
    
    # Valida se os injetores de URLs assinaram os componentes de forma válida e tratável pelo JSON
    assert body["dados_extraidos"]["s3_url_consolidado"] == "https://credifacil-storage.s3.amazonaws.com/mock-signed-url"
    assert body["dados_extraidos"]["documentos_analisados"][0]["s3_url_final"] == "https://credifacil-storage.s3.amazonaws.com/mock-signed-url"