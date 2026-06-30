import json
import os
import pytest
from unittest.mock import MagicMock
import src.lambdas.result_writer.handler as result_writer

@pytest.fixture(autouse=True)
def setup_env():
    """Injeta as tabelas do DynamoDB esperadas pela Lambda."""
    os.environ["DYNAMODB_TABLE"] = "credifacil-pacotes-dev"
    os.environ["CLIENTS_DYNAMODB_TABLE"] = "credifacil-clientes-dev"

def test_deve_atualizar_status_do_pacote_quando_score_estiver_desativado(monkeypatch):
    """Garante que o ciclo padrão sem score atualiza apenas os metadados de lote do Dynamo."""
    mock_db = MagicMock()
    mock_db.update_item.return_value = {}
    monkeypatch.setattr(result_writer, "db_client", mock_db)

    evento_sem_score = {
        "package_id": "pkg-123",
        "execute_score": False,
        "confianca_geral": 0.88,
        "decisao_sugerida": "revisar",
        "json_estruturado": {
            "sistema": {
                "processamento": {
                    "quantidade_tokens": {"total_tokens": 2500}
                }
            }
        }
    }

    response = result_writer.handler(evento_sem_score, None)
    assert response["statusCode"] == 200
    
    body = json.loads(response["body"])
    assert body["status"] == "COMPLETED"
    assert body["score_calculado"] is False

    # Valida se a chamada ao Dynamo usou as chaves estruturadas reais do código
    mock_db.update_item.assert_called_once()
    _, kwargs = mock_db.update_item.call_args
    assert kwargs["Key"] == {"PK": {"S": "pkg-123"}, "SK": {"S": "METADATA"}}
    
    valores_db = kwargs["ExpressionAttributeValues"]
    assert valores_db[":comp"]["S"] == "COMPLETED"
    assert valores_db[":ds"]["S"] == "revisar"
    assert valores_db[":tk"]["S"] == "2500 tokens"

def test_deve_persistir_proponente_no_crm_quando_gate_de_score_estiver_ativo(monkeypatch):
    """Garante o comportamento reativo do CRM gravando os dados achatados financeiros do cliente."""
    mock_db = MagicMock()
    mock_db.update_item.return_value = {}
    mock_db.put_item.return_value = {}
    monkeypatch.setattr(result_writer, "db_client", mock_db)

    evento_com_score = {
        "package_id": "pkg-crm-999",
        "execute_score": True,
        "confianca_geral": 0.95,
        "json_estruturado": {
            "sistema": {
                "processamento": {"quantidade_tokens": {"total_tokens": 1200}},
                "chave_cliente": "CLIENT#WERITON_PETRECA"
            },
            "cliente": {
                "nome": "Weriton Luis Petreca",
                "documento_identificacao": "529.982.247-25",
                "data_nascimento": "1989-10-12",
                "score_credito": {"valor": 95},
                "classificacao_risco": {"categoria": "baixo", "justificativa": "Renda sólida comprovada."}
            },
            "documentos_analisados": [
                {
                    "tipo_documento": "COMPROVANTE_RENDA",
                    "arquivo_original": "holerite_maio.pdf",
                    "campos_extraidos": {"amount_numeric": 7500.00},
                    "status_extracao": "sucesso",
                    "confianca_media": 0.98
                }
            ]
        }
    }

    response = result_writer.handler(evento_com_score, None)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["score_calculado"] is True

    # Comprova que além de atualizar o lote, fez o put do cliente no CRM
    assert mock_db.put_item.call_count == 1
    _, kwargs_put = mock_db.put_item.call_args
    assert kwargs_put["TableName"] == "credifacil-clientes-dev"
    
    item_crm = kwargs_put["Item"]
    assert item_crm["PK"]["S"] == "CLIENT#WERITON_PETRECA"
    assert item_crm["nome_completo"]["S"] == "Weriton Luis Petreca"
    assert item_crm["renda_bruta_estimada"]["N"] == "7500.0"
    assert item_crm["classificacao_risco"]["S"] == "BAIXO_RISK"