import json
import pytest
from unittest.mock import MagicMock
import src.lambdas.human_review_consumer.handler as consumer_handler

@pytest.fixture
def sqs_eventbridge_event():
    """Simula o envelope legítimo da SQS encapsulando o evento do EventBridge Custom Bus."""
    event_bridge_payload = {
        "source": "credifacil.idp",
        "detail-type": "LowConfidenceFieldsDetected",
        "detail": {
            "package_id": "pkg-test-888",
            "task_token": "TOKEN_CRIPTOGRAFICO_DA_FILA",
            "failed_fields_metadata": [
                {"arquivo": "doc.pdf", "campo_afetado": "employee_name", "confidence_score": 0.35}
            ]
        }
    }
    return {
        "Records": [
            {
                "body": json.dumps(event_bridge_payload),
                "receiptHandle": "handle-sqs-mock-123"
            }
        ]
    }

def test_human_review_consumer_success(sqs_eventbridge_event, monkeypatch):
    """GARANTE O FLUXO FELIZ: Desembrulha o SQS/EventBridge e persiste a linha REVISION no banco."""
    mock_db = MagicMock()
    mock_db.put_item.return_value = {}
    monkeypatch.setattr(consumer_handler, "db_client", mock_db)

    response = consumer_handler.handler(sqs_eventbridge_event, None)

    # Asserções de contrato de execução
    assert response["statusCode"] == 200
    mock_db.put_item.assert_called_once()
    
    # Valida detalhadamente a integridade do schema persistido no DynamoDB
    call_kwargs = mock_db.put_item.call_args[1]
    item_persistido = call_kwargs["Item"]
    
    assert item_persistido["PK"]["S"] == "pkg-test-888"
    assert item_persistido["SK"]["S"] == "REVISION"
    assert item_persistido["task_token"]["S"] == "TOKEN_CRIPTOGRAFICO_DA_FILA"
    assert item_persistido["status_revisao"]["S"] == "PENDENTE"
    assert item_persistido["total_campos_falhos"]["N"] == "1"
    
    # Garante que os metadados dos campos foram serializados sem corrupção de string
    campos_json = json.loads(item_persistido["campos_reprovados_json"]["S"])
    assert campos_json[0]["campo_afetado"] == "employee_name"

def test_human_review_consumer_should_skip_malformed_record(monkeypatch):
    """GARANTE RESILIÊNCIA: Mensagens corrompidas sem chaves essenciais são puladas sem quebrar o lote."""
    payload_corrompido = {
        "Records": [
            {
                "body": json.dumps({
                    "detail": {
                        "package_id": "pkg-malformado-sem-token"
                        # task_token ausente de propósito
                    }
                })
            }
        ]
    }
    
    mock_db = MagicMock()
    monkeypatch.setattr(consumer_handler, "db_client", mock_db)

    response = consumer_handler.handler(payload_corrompido, None)

    # Deve retornar HTTP 200 e NUNCA salvar sujeira no DynamoDB
    assert response["statusCode"] == 200
    mock_db.put_item.assert_not_called()