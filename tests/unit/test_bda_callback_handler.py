import json
import pytest
from unittest.mock import MagicMock
from botocore.exceptions import ClientError
import src.lambdas.bda_callback_handler.handler as callback_handler

@pytest.fixture
def eventbridge_completed_event():
    return {
        "source": "aws.bedrock",
        "detail-type": "Bedrock Data Automation Job Status Change",
        "detail": {
            "automationJobId": "bda-job-8f3b9c2e-4a1d",
            "status": "COMPLETED",
            "outputConfiguration": {
                "s3Bucket": "credifacil-docs-saida-dev",
                "s3Prefix": "results/packages/pkg-123/"
            }
        }
    }

@pytest.fixture
def eventbridge_failed_event():
    return {
        "source": "aws.bedrock",
        "detail-type": "Bedrock Data Automation Job Status Change",
        "detail": {
            "automationJobId": "bda-job-8f3b9c2e-4a1d",
            "status": "FAILED_WITH_ERROR"
        }
    }

def test_deve_reativar_step_functions_com_sucesso_quando_job_bda_concluir(eventbridge_completed_event, monkeypatch):
    mock_db = MagicMock()
    mock_sfn = MagicMock()
    
    mock_db.get_item.return_value = {
        "Item": {
            "task_token": {"S": "AAAApZW5jb2RlZHRva2VuAAA="},
            "package_id": {"S": "pkg-123"}
        }
    }
    # 🚀 GARANTIA: Força o contador a retornar 0 para simular o último arquivo do lote
    mock_db.update_item.return_value = {
        "Attributes": {
            "bda_pending_jobs": {"N": "0"}
        }
    }
    mock_sfn.send_task_success.return_value = {}

    monkeypatch.setattr(callback_handler, "db_client", mock_db)
    monkeypatch.setattr(callback_handler, "sfn_client", mock_sfn)

    response = callback_handler.handler(eventbridge_completed_event, None)
    
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert "sucesso" in body["mensagem"]

def test_deve_notificar_falha_para_step_functions_quando_job_bda_falhar(eventbridge_failed_event, monkeypatch):
    mock_db = MagicMock()
    mock_sfn = MagicMock()
    
    mock_db.get_item.return_value = {
        "Item": {
            "task_token": {"S": "AAAApZW5jb2RlZHRva2VuAAA="},
            "package_id": {"S": "pkg-123"}
        }
    }
    mock_sfn.send_task_failure.return_value = {}

    monkeypatch.setattr(callback_handler, "db_client", mock_db)
    monkeypatch.setattr(callback_handler, "sfn_client", mock_sfn)

    response = callback_handler.handler(eventbridge_failed_event, None)
    
    assert response["statusCode"] == 200
    mock_sfn.send_task_failure.assert_called_once()

def test_deve_retornar_bad_request_se_payload_do_eventbridge_for_invalido(monkeypatch):
    payload_quebrado = {"source": "aws.bedrock", "detail": {}}
    response = callback_handler.handler(payload_quebrado, None)
    assert response["statusCode"] == 400
    assert "Contrato inválido" in response["body"]

def test_deve_retornar_not_found_se_o_token_nao_existir_no_dynamodb(eventbridge_completed_event, monkeypatch):
    mock_db = MagicMock()
    mock_db.get_item.return_value = {}
    monkeypatch.setattr(callback_handler, "db_client", mock_db)

    response = callback_handler.handler(eventbridge_completed_event, None)
    assert response["statusCode"] == 404
    assert "não localizado" in response["body"].lower()

def test_deve_tratar_com_sucesso_se_o_token_estiver_expirado_na_step_functions(eventbridge_completed_event, monkeypatch):
    mock_db = MagicMock()
    mock_sfn = MagicMock()
    
    mock_db.get_item.return_value = {
        "Item": {
            "task_token": {"S": "TOKEN_EXPIRADO"},
            "package_id": {"S": "pkg-123"}
        }
    }
    
    # 🚀 CORREÇÃO CIRÚRGICA: Força o retorno como 0 para obrigar a execução do send_task_success
    mock_db.update_item.return_value = {
        "Attributes": {
            "bda_pending_jobs": {"N": "0"}
        }
    }
    
    resposta_erro_aws = {"Error": {"Code": "TaskDoesNotExist", "Message": "Task timed out"}}
    mock_sfn.send_task_success.side_effect = ClientError(
        error_response=resposta_erro_aws,
        operation_name="SendTaskSuccess"
    )

    monkeypatch.setattr(callback_handler, "db_client", mock_db)
    monkeypatch.setattr(callback_handler, "sfn_client", mock_sfn)

    response = callback_handler.handler(eventbridge_completed_event, None)
    assert response["statusCode"] == 410
    assert "expirado ou inexistente" in response["body"].lower()