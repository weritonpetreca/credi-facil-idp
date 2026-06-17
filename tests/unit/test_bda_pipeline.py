from unittest.mock import patch, MagicMock
import os

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
    # 1. Configura o Mock do cliente do Bedrock Data Automation Runtime
    mock_bedrock = MagicMock()
    mock_bedrock.invoke_data_automation_async.return_value = {
        "invocationArn": "arn:aws:bedrock:us-east-1:635106763014:data-automation-invocation/mock-123",
        "status": "Submitted"
    }

    # Configura o Mock do STS
    mock_sts = MagicMock()
    mock_sts.get_caller_identity.return_value = {"Account": "635106763014"}

    # 🔄 CORREÇÃO: Intercepta o novo nome do cliente usado no BDA GA
    def side_effect(service_name, *args, **kwargs):
        if service_name == "bedrock-data-automation-runtime":
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

    # 5. Asserções de Saída
    assert response is not None
    assert response["package_id"] == "pacote-999"
    assert response["user_id"] == "user-123"
    assert response["bda_job_id"] == "arn:aws:bedrock:us-east-1:635106763014:data-automation-invocation/mock-123"
    
    # 🛡️ ASSERÇÃO DE QUALIDADE: Valida se a Lambda envelopou os parâmetros corretamente
    mock_bedrock.invoke_data_automation_async.assert_called_once_with(
        inputConfiguration={"s3Uri": "s3://credifacil-docs-entrada-dev/packages/pacote-999/"},
        outputConfiguration={"s3Uri": "s3://credifacil-docs-saida-dev/bda-output/pacote-999/"},
        dataAutomationConfiguration={
            "dataAutomationProjectArn": "arn:aws:bedrock:us-east-1:635106763014:data-automation-project/projeto-credifacil-bda-default"
        },
        dataAutomationProfileArn="arn:aws:bedrock:us-east-1:635106763014:data-automation-profile/us.data-automation-v1"
    )