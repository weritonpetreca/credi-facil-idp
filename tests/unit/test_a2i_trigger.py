import json
import pytest
from unittest.mock import patch
from src.lambdas.a2i_trigger.handler import handler

@patch("src.lambdas.a2i_trigger.handler.a2i_client")
def test_deve_iniciar_human_loop_com_sucesso(mock_a2i):
    mock_a2i.start_human_loop.return_value = {"HumanLoopArn": "arn:aws:sagemaker:human-loop/123"}

    evento_entrada = {
        "package_id": "pacote-teste-123",
        "user_id": "analista-weriton",
        "bda_output_bucket": "meu-bucket",
        "bda_output_key": "bda-output/result.json"
    }

    resposta = handler(evento_entrada, None)

    assert resposta["revisao_humana"] is True
    assert resposta["human_loop_arn"] == "arn:aws:sagemaker:human-loop/123"
    mock_a2i.start_human_loop.assert_called_once()