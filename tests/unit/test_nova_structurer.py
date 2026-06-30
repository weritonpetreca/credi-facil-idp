import json
import pytest
from src.lambdas.nova_structurer.handler import handler

class MockS3Body:
    def __init__(self, text):
        self.text = text
    def read(self):
        return self.text.encode("utf-8")

@pytest.fixture
def pipeline_event():
    return {
        "package_id": "pkg-struct-999",
        "bda_output_bucket": "credifacil-outputs-dev"
    }

def test_deve_estruturar_documento_via_bedrock_tool_calling_com_sucesso(pipeline_event, monkeypatch):
    """Garante que a orquestração Nova captura a resposta estruturada da IA e persiste o blueprint no S3."""
    
    # 1. Mock do DynamoDB para responder que a flag execute_score está falsa
    monkeypatch.setattr("src.lambdas.nova_structurer.handler.db_client.get_item",
        lambda TableName, Key: {"Item": {"execute_score": {"BOOL": False}}})

    # 2. Mock do S3 listando um arquivo de saída do BDA pendente de estruturação
    monkeypatch.setattr("src.lambdas.nova_structurer.handler.s3_client.list_objects_v2",
        lambda Bucket, Prefix: {"Contents": [{"Key": "bda-output/pkg-struct-999/identidade.json"}]})

    # 3. Mock do download do JSON bruto do S3
    monkeypatch.setattr("src.lambdas.nova_structurer.handler.s3_client.get_object",
        lambda Bucket, Key: {"Body": MockS3Body('{"text": "Simulação de transcrição OCR da CNH de Weriton Luis Petreca"}')})

    # 4. Mock da chamada do Amazon Bedrock simulando a injeção nativa de Tool Calling do modelo Nova
    def mock_converse(modelId, messages, system, toolConfig, inferenceConfig):
        return {
            "usage": {"inputTokens": 120, "outputTokens": 85},
            "output": {
                "message": {
                    "content": [
                        {
                            "toolUse": {
                                "input": {
                                    "tipo_classificado": "identity_document",
                                    "campos_extraidos_brutos": {
                                        "full_name": "WERITON LUIS PETRECA",
                                        "document_number": "MG-12.345.678"
                                    },
                                    "confianca_extracao": 0.95,
                                    "alertas_inconsistencias": []
                                }
                            }
                        }
                    ]
                }
            }
        }
    monkeypatch.setattr("src.lambdas.nova_structurer.handler.bedrock_runtime.converse", mock_converse)

    # 5. Capturador de escrita do S3 para provar que salvamos o blueprint final de resultados
    arquivos_salvos_s3 = []
    monkeypatch.setattr("src.lambdas.nova_structurer.handler.s3_client.put_object",
        lambda Bucket, Key, Body, ContentType: arquivos_salvos_s3.append(Key))

    response = handler(pipeline_event, None)

    # Asserções de conformidade de contrato
    assert response["package_id"] == "pkg-struct-999"
    assert response["execute_score"] is False
    assert len(arquivos_salvos_s3) == 2
    # Valida se a rota dinâmica de salvamento obedeceu a classificação taxonômica da IA
    assert "results/documento_identificacao/driver_license/" in arquivos_salvos_s3[0]