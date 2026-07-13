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


def test_query_handler_extrai_confianca_real_do_caminho_aninhado_do_aggregator(api_event, monkeypatch):
    """
    Regressão direta do bug relatado em produção: TODO documento aparecia com
    confianca_media=1 (100%) no painel, mesmo com o aggregator.py logando
    valores reais e variados (0.87, 0.92, 0.83...). Causa: aggregator.py grava
    a confiança ANINHADA em confiabilidade_extracao.confianca_media — nunca
    existiu um confianca_media solto na raiz do documento. query_handler.py
    lia doc.get("confianca_media") (raiz) e caía sempre no fallback ou 1.0.
    """
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

    # Formato REAL que aggregator.py produz (confiabilidade_extracao aninhado,
    # sem nenhuma chave confianca_media solta na raiz do documento)
    payload_s3 = {
        "documentos_analisados": [
            {
                "arquivo_original": "cnh.pdf",
                "tipo_documento": "documento_identificacao",
                "subtipo_documento": "driver_license",
                "s3_key_resultado": "results/documento_identificacao/driver_license/pkg-123/cnh_structured.json",
                "dados_extraidos_do_documento": {"full_name": "WERITON LUIS PETRECA"},
                "confiabilidade_extracao": {
                    "status_extracao": "sucesso",
                    "confianca_media": "0.8342",
                    "observacoes": [],
                },
            }
        ]
    }

    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": MockS3Body(payload_s3)}
    mock_s3.generate_presigned_url.return_value = "https://credifacil-storage.s3.amazonaws.com/mock-signed-url"

    monkeypatch.setattr(query_handler, "db_client", mock_db)
    monkeypatch.setattr(query_handler, "s3_client", mock_s3)

    response = query_handler.handler(api_event, None)
    body = json.loads(response["body"])

    doc = body["dados_extraidos"]["documentos_analisados"][0]
    assert doc["confianca_media"] == pytest.approx(0.8342)
    assert doc["confianca_media"] != 1.0


def test_query_handler_documento_com_falha_mostra_confianca_zero_nao_100_por_cento(api_event, monkeypatch):
    """Documento que falhou na estruturação (status_extracao='falha', confianca
    '0.0000' gravada pelo aggregator) não pode aparecer como 100% no painel —
    esse é o pior caso possível do mesmo bug: uma falha parecendo sucesso."""
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
    payload_s3 = {
        "documentos_analisados": [
            {
                "arquivo_original": "arquivo_desconhecido",
                "tipo_documento": "DESCONHECIDO",
                "subtipo_documento": "desconhecido",
                "s3_key_resultado": None,
                "dados_extraidos_do_documento": {},
                "confiabilidade_extracao": {
                    "status_extracao": "falha",
                    "confianca_media": "0.0000",
                    "observacoes": ["Estruturação falhou."],
                },
            }
        ]
    }
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": MockS3Body(payload_s3)}
    mock_s3.generate_presigned_url.return_value = "https://credifacil-storage.s3.amazonaws.com/mock-signed-url"

    monkeypatch.setattr(query_handler, "db_client", mock_db)
    monkeypatch.setattr(query_handler, "s3_client", mock_s3)

    response = query_handler.handler(api_event, None)
    body = json.loads(response["body"])

    doc = body["dados_extraidos"]["documentos_analisados"][0]
    assert doc["status_extracao"] == "falha"
    assert doc["confianca_media"] == pytest.approx(0.0)
    assert body["dados_extraidos"]["documentos_analisados"][0]["s3_url_final"] == "https://credifacil-storage.s3.amazonaws.com/mock-signed-url"