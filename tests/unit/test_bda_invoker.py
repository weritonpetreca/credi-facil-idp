import json
import os
import pytest
from unittest.mock import MagicMock
# 🚀 IMPORTAÇÃO DO MÓDULO: Permite injetar os Mocks diretamente nas variáveis internas do arquivo
import src.lambdas.bda_invoker.handler as bda_handler

@pytest.fixture(autouse=True)
def setup_env():
    """Injeta as variáveis de ambiente necessárias para a Lambda compilar sem quebras."""
    os.environ["BDA_PROJECT_ARN"] = "arn:aws:bedrock:us-east-1:635106763014:data-automation-project/credifacil-bda-dev"
    os.environ["BDA_PROJECT_ID"] = "projeto-credifacil-bda-default"
    os.environ["BUCKET_ENTRADA"] = "credifacil-docs-entrada-dev"
    os.environ["BUCKET_SAIDA"] = "credifacil-docs-saida-dev"
    os.environ["ENV"] = "dev"

def test_bda_invoker_handler_success(monkeypatch):
    """Garante que o invoker do BDA liste os arquivos de entrada e dispare o job assíncrono."""
    
    # 1. Configura os Mocks isolados de infraestrutura
    mock_s3 = MagicMock()
    mock_s3.list_objects_v2.return_value = {
        "Contents": [
            {"Key": "packages/pacote-999/rg.pdf"},
            {"Key": "packages/pacote-999/holerite.pdf"}
        ]
    }
    
    mock_sts = MagicMock()
    mock_sts.get_caller_identity.return_value = {"Account": "635106763014"}
    
    mock_bedrock_bda = MagicMock()
    mock_bedrock_bda.invoke_data_automation_async.return_value = {
        "invocationArn": "arn:aws:bedrock:us-east-1:635106763014:data-automation-invocation/mock-123",
        "status": "Submitted"
    }

    # 2. 🛡️ MONKEYPATCHING CIRÚRGICO: Substitui as instâncias reais pelos Mocks na memória do módulo
    monkeypatch.setattr(bda_handler, "s3_client", mock_s3)
    
    # Faz o patch preventivo cobrirem variações comuns de nomes de variáveis do STS e Bedrock Runtime
    for client_name in ["sts_client", "sts"]:
        if hasattr(bda_handler, client_name):
            monkeypatch.setattr(bda_handler, client_name, mock_sts)
            
    for bda_name in ["bda_client", "bedrock_client", "bedrock_runtime", "bda_runtime"]:
        if hasattr(bda_handler, bda_name):
            monkeypatch.setattr(bda_handler, bda_name, mock_bedrock_bda)

    # 3. Payload legítimo que inicia a orquestração do Step Functions
    mock_event = {
        "package_id": "pacote-999",
        "user_id": "user-123",
        "bda_output_bucket": "credifacil-docs-saida-dev"
    }

    # 4. Execução do Ponto de Entrada (Handler)
    response = bda_handler.handler(mock_event, None)

    # 5. 🛡️ VALIDAÇÃO DE CONTRATO ATUALIZADA: Adequada ao paralelismo granular do SRS v2.0
    assert response["package_id"] == "pacote-999"
    assert response["user_id"] == "user-123"
    assert response["bda_output_bucket"] == "credifacil-docs-saida-dev"
    
    # Garante que o array de descentralização de carga nasceu com os 2 jobs simulados
    assert "bda_job_ids" in response
    assert isinstance(response["bda_job_ids"], list)
    assert len(response["bda_job_ids"]) == 2
    assert response["bda_job_ids"][0] == "arn:aws:bedrock:us-east-1:635106763014:data-automation-invocation/mock-123"