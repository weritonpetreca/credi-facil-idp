import os
import sys
from unittest.mock import MagicMock, patch
import pytest

# Configuração isolada do ambiente antes das importações
@patch.dict(os.environ, {
    "BDA_PROJECT_ARN": "arn:aws:bedrock:us-east-1:635106763014:data-automation-project/credifacil-bda-dev",
    "BDA_PROJECT_ID": "projeto-credifacil-bda-default",
    "BUCKET_SAIDA": "credifacil-docs-saida-dev",
    "ENV": "dev"
})
@patch("boto3.client")
def test_bda_invoker_handler_success(mock_boto3_client):
    """
    Garante que o invoker do BDA execute a chamada assíncrona
    e retorne o payload mapeado corretamente para o Step Functions.
    """
    # 1. Configura o Mock do cliente do Bedrock
    mock_bedrock = MagicMock()
    mock_bedrock.invoke_data_automation_async.return_value = {
        "automationJobId": "automation-job-mock-123",
        "status": "Submitted"
    }
    
    # Configura o Mock do STS caso a Lambda ainda use a versão antiga com String Concat
    mock_sts = MagicMock()
    mock_sts.get_caller_identity.return_value = {"Account": "635106763014"}
    
    def side_effect(service_name, *args, **kwargs):
        if service_name == "bedrock":
            return mock_bedrock
        if service_name == "sts":
            return mock_sts
        return MagicMock()
        
    mock_boto3_client.side_effect = side_effect

    # 2. Importa o handler com o escopo mockado
    from src.lambdas.bda_invoker.handler import handler

    # 3. Payload de entrada no padrão real do Step Functions
    mock_event = {
        "package_id": "pacote-999",
        "user_id": "user-123",
        "bda_output_bucket": "credifacil-docs-saida-dev"
    }
    
    # 4. Executa a função
    response = handler(mock_event, None)

    # 5. Asserções Corretas (Mapeadas ao seu Dicionário de Retorno)
    assert response is not None
    assert response["package_id"] == "pacote-999"
    assert response["user_id"] == "user-123"
    
    # 💥 CORREÇÃO: Chave mapeada de negócio do seu ecossistema
    assert "bda_job_id" in response
    assert response["bda_job_id"] == "automation-job-mock-123"
    assert "result.json" in response["bda_output_key"]
    
    # Valida que o disparo para a API assíncrona foi efetuado com sucesso
    mock_bedrock.invoke_data_automation_async.assert_called_once()


@patch("src.lambdas.bda_status_poller.handler.bedrock_client")
def test_bda_status_poller_deve_retornar_status_atual_da_ia(mock_bedrock):
    """Garante que o Poller capture o estado do processamento assíncrono do BDA."""
    mock_bedrock.get_data_automation_status.return_value = {"status": "IN_PROGRESS"}
    
    from src.lambdas.bda_status_poller.handler import handler as poller_handler

    evento_polling = {
        "package_id": "pacote-uuid-teste",
        "bda_job_id": "job-ia-abc-123"
    }
    
    resposta = poller_handler(evento_polling, None)
    
    assert resposta["status_bda"] == "IN_PROGRESS"
    mock_bedrock.get_data_automation_status.assert_called_once()