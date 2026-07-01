import json
import pytest
from unittest.mock import MagicMock
from botocore.exceptions import ClientError
import src.lambdas.human_review_submit.handler as submit_handler

@pytest.fixture
def api_gateway_success_event():
    """Simula um evento legítimo vindo do API Gateway com o payload de correções."""
    return {
        "pathParameters": {
            "packageId": "pkg-test-999"
        },
        "body": json.dumps({
            "correcoes": {
                "employee_name": "Weriton Luis Petreca",
                "pay_date": "2026-07-01"
            }
        })
    }

def test_human_review_submit_success(api_gateway_success_event, monkeypatch):
    """GANTE O FLUXO FELIZ: O Token é recuperado, a máquina acorda e o banco volta para PROCESSING."""
    mock_db = MagicMock()
    mock_sfn = MagicMock()

    # Simula a linha SK=REVISION contendo o token válido no DynamoDB
    mock_db.get_item.return_value = {
        "Item": {
            "task_token": {"S": "AAAApZW5jb2RlZHRva2VuAAA="}
        }
    }
    mock_db.update_item.return_value = {}
    mock_sfn.send_task_success.return_value = {}

    # Monkeypatching cirúrgico nas instâncias internas da Lambda
    monkeypatch.setattr(submit_handler, "db_client", mock_db)
    monkeypatch.setattr(submit_handler, "sfn_client", mock_sfn)

    response = submit_handler.handler(api_gateway_success_event, None)

    # Asserções significativas de comportamento e contrato
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert "ativado com sucesso" in body["mensagem"]
    
    # Valida se os side-effects obrigatórios de infraestrutura foram disparados
    mock_sfn.send_task_success.assert_called_once()
    mock_db.update_item.assert_called_once()

def test_human_review_submit_token_expirado(api_gateway_success_event, monkeypatch):
    """GARANTE O FAIL-SAFE 410: Se o token já foi processado ou expirou, a API avisa o front de forma limpa."""
    mock_db = MagicMock()
    mock_sfn = MagicMock()

    mock_db.get_item.return_value = {
        "Item": {
            "task_token": {"S": "TOKEN_VELHO_OU_EXPIRADO"}
        }
    }
    
    # Força o SDK do Step Functions a lançar o erro de Token Expirado/Inexistente
    resposta_erro_aws = {"Error": {"Code": "TaskDoesNotExist", "Message": "Task timed out"}}
    mock_sfn.send_task_success.side_effect = ClientError(
        error_response=resposta_erro_aws,
        operation_name="SendTaskSuccess"
    )

    monkeypatch.setattr(submit_handler, "db_client", mock_db)
    monkeypatch.setattr(submit_handler, "sfn_client", mock_sfn)

    response = submit_handler.handler(api_gateway_success_event, None)

    assert response["statusCode"] == 410
    body = json.loads(response["body"])
    assert "expirou" in body["erro"]

def test_human_review_submit_missing_parameter(monkeypatch):
    """GARANTE O GUARDRAIL 400: Se a rota vier sem o packageId, a execução barra imediatamente."""
    event_invalido = {"pathParameters": {}, "body": "{}"}
    
    response = submit_handler.handler(event_invalido, None)
    
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "obrigatório" in body["erro"]