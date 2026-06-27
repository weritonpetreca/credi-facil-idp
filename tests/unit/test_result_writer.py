import json
import os
from unittest.mock import patch
from src.lambdas.result_writer.handler import handler

@patch.dict(os.environ, {"BUCKET_SAIDA": "bucket-teste-saida"})
@patch("src.lambdas.result_writer.handler.db_client")
@patch("src.lambdas.result_writer.handler.s3_client")
def test_deve_salvar_json_no_s3_e_marcar_como_concluido_no_dynamo(mock_s3, mock_db):
    """Garante que o handler escreve o resultado final no S3 e atualiza o status no DynamoDB."""
    
    mock_s3.put_object.return_value = {}
    mock_db.update_item.return_value = {}

    evento_input = {
        "package_id": "8f3b9c2e-4a1d-4f7b-9c3e-2a1b4c7d5e6f",
        "confianca_geral": 0.92,
        "revisao_humana": False,
        "json_estruturado": {
            "package_id": "8f3b9c2e-4a1d-4f7b-9c3e-2a1b4c7d5e6f",
            "status": "COMPLETED",
            "documentos": {"identidade": {"nome": "Weriton L Petreca"}}
        }
    }

    resposta = handler(evento_input, None)
    corpo_resposta = json.loads(resposta["body"])

    assert resposta["statusCode"] == 200
    assert corpo_resposta["status"] == "COMPLETED"
    
    # Valida a chamada para o S3
    s3_args, s3_kwargs = mock_s3.put_object.call_args
    assert s3_kwargs["Bucket"] == "bucket-teste-saida"
    assert s3_kwargs["Key"] == "results/packages/8f3b9c2e-4a1d-4f7b-9c3e-2a1b4c7d5e6f/output.json"
    assert json.loads(s3_kwargs["Body"])["documentos"]["identidade"]["nome"] == "Weriton L Petreca"

    # Valida a chamada para o DynamoDB
    db_args, db_kwargs = mock_db.update_item.call_args
    assert db_kwargs["TableName"] is not None
    assert db_kwargs["Key"] == {
        "PK": {"S": "8f3b9c2e-4a1d-4f7b-9c3e-2a1b4c7d5e6f"},
        "SK": {"S": "METADATA"}
    }
    assert ":status" in db_kwargs["ExpressionAttributeValues"]
    assert db_kwargs["ExpressionAttributeValues"][":status"]["S"] == "COMPLETED"
    assert ":resultS3Key" in db_kwargs["ExpressionAttributeValues"]
    assert db_kwargs["ExpressionAttributeValues"][":resultS3Key"]["S"] == "results/packages/8f3b9c2e-4a1d-4f7b-9c3e-2a1b4c7d5e6f/output.json"
    assert "SET #status = :status" in db_kwargs["UpdateExpression"]
    assert "#resultS3Key = :resultS3Key" in db_kwargs["UpdateExpression"]