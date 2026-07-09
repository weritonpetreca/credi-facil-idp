import json
import os
import pytest
from unittest.mock import MagicMock

import src.lambdas.nova_structurer.lister as lister_module
import src.lambdas.nova_structurer.handler as unit_handler_module
import src.lambdas.nova_structurer.aggregator as aggregator_module

class MockS3Body:
    def __init__(self, text):
        self.text = text
    def read(self):
        return self.text.encode("utf-8")

@pytest.fixture(autouse=True)
def setup_env():
    """Injeta as variáveis de ambiente necessárias para a Lambda compilar sem quebras."""
    os.environ["DYNAMODB_TABLE"] = "credifacil-pacotes-dev"
    os.environ["BDA_PROJECT_ARN"] = "arn:aws:bedrock:us-east-1:635106763014:data-automation-project/credifacil-bda-dev"
    os.environ["BDA_PROFILE_ARN"] = "arn:aws:bedrock:us-east-1:635106763014:data-automation-profile/us.data-automation-v1"
    os.environ["BUCKET_ENTRADA"] = "credifacil-docs-entrada-dev"
    os.environ["BUCKET_SAIDA"] = "credifacil-docs-saida-dev"
    os.environ["ENV"] = "dev"
    # 🚀 ADICIONADO: Variáveis de ambiente de segurança para emular a infraestrutura do CloudFormation
    os.environ["GUARDRAIL_IDENTIFIER"] = "guardrail-idp-mock-123"
    os.environ["GUARDRAIL_VERSION"] = "1"

# ==========================================================================
# 🔍 1. TESTES DO COMPONENTE: LISTER (Mantido estável)
# ==========================================================================
def test_lister_deve_mapear_documentos_e_buscar_flags_do_banco(base_event, monkeypatch):
    mock_db = MagicMock()
    mock_s3 = MagicMock()

    mock_db.get_item.return_value = {
        "Item": {
            "execute_score": {"BOOL": True},
            "uploadedBy": {"S": "analista-weriton"}
        }
    }
    mock_s3.list_objects_v2.return_value = {
        "Contents": [
            {"Key": "bda-output/pkg-map-999/cnh_frente/custom_output.json"},
            {"Key": "bda-output/pkg-map-999/holerite/standard_output.json"}
        ]
    }

    monkeypatch.setattr(lister_module, "db_client", mock_db)
    monkeypatch.setattr(lister_module, "s3_client", mock_s3)

    response = lister_module.handler(base_event, None)

    assert response["package_id"] == "pkg-map-999"
    assert response["execute_score"] is True
    assert response["user_id"] == "analista-weriton"
    assert "documentos_para_estruturar" in response
    assert len(response["documentos_para_estruturar"]) == 2

@pytest.fixture
def base_event():
    return {
        "package_id": "pkg-map-999",
        "bda_output_bucket": "credifacil-outputs-dev"
    }

# ==========================================================================
# 🧠 2. TESTES DO COMPONENTE: UNIT STRUCTURER (HANDLER VALIDA COMPLIANCE)
# ==========================================================================
def test_handler_unitario_deve_estruturar_um_unico_documento_via_tool_calling(monkeypatch):
    mock_s3 = MagicMock()
    mock_bedrock = MagicMock()

    # 🚀 Simula os DOIS arquivos reais que o BdaExtractor busca: custom_output
    # (com matched_blueprint — a fonte de verdade da classificação, ver
    # shared/classificador.py) e standard_output (markdown completo).
    custom_output_body = json.dumps({
        "matched_blueprint": {"name": "CrediFacil-DriverLicense-Blueprint"},
        "inference_result": {"full_name": "WERITON LUIS PETRECA"},
        "explainability_info": [{"full_name": {"confidence": 0.97}}],
    })
    standard_output_body = json.dumps({
        "pages": [{"representation": {"markdown": "Transcrição simulada OCR da CNH do cliente Weriton Luis Petreca"}}]
    })

    def s3_get_object_side_effect(Bucket, Key):
        if "standard_output" in Key:
            return {"Body": MockS3Body(standard_output_body)}
        return {"Body": MockS3Body(custom_output_body)}

    mock_s3.get_object.side_effect = s3_get_object_side_effect

    mock_bedrock.converse.return_value = {
        "usage": {"inputTokens": 150, "outputTokens": 90},
        "output": {
            "message": {
                "content": [
                    {
                        "toolUse": {
                            "input": {
                                "tipo_classificado": "DRIVER_LICENSE",
                                "full_name": "WERITON LUIS PETRECA",
                                "document_number": "MG-12.345.678",
                                "alertas_inconsistencias": []
                            }
                        }
                    }
                ]
            }
        }
    }

    monkeypatch.setattr(unit_handler_module, "s3_client", mock_s3)
    monkeypatch.setattr(unit_handler_module, "bedrock_runtime", mock_bedrock)

    mock_map_item_event = {
        "package_id": "pkg-map-999",
        "bda_output_bucket": "credifacil-outputs-dev",
        "nome_pdf_original": "cnh_frente.pdf",
        "s3_key_bda": "bda-output/pkg-map-999/cnh_frente/custom_output.json"
    }

    response = unit_handler_module.handler(mock_map_item_event, None)

    assert "blueprint" in response
    assert response["blueprint"]["subtipo_documento"] == "driver_license"
    assert response["blueprint"]["dados_extraidos_do_documento"]["full_name"] == "WERITON LUIS PETRECA"
    
    # 🚀 VALIDAÇÃO DEVSECOPS CRÍTICA: Assegura que o código acionou o Guardrail de segurança contra injeção de prompt
    mock_bedrock.converse.assert_called_once()
    _, kwargs = mock_bedrock.converse.call_args
    assert "guardrailConfig" in kwargs
    assert kwargs["guardrailConfig"]["guardrailIdentifier"] == "guardrail-idp-mock-123"
    assert kwargs["guardrailConfig"]["guardrailVersion"] == "1"

    assert mock_s3.put_object.call_count == 1

# ==========================================================================
# 📊 3. TESTES DO COMPONENTE: AGGREGATOR (Mantido estável)
# ==========================================================================
def test_aggregator_deve_consolidar_lote_e_emitir_metricas_emf(monkeypatch):
    mock_s3 = MagicMock()
    monkeypatch.setattr(aggregator_module, "s3_client", mock_s3)
    monkeypatch.setattr(aggregator_module.metrics, "add_metric", lambda name, unit, value: None)

    mock_aggregator_event = {
        "package_id": "pkg-map-999",
        "user_id": "analista-weriton",
        "execute_score": False,
        "bda_output_bucket": "credifacil-outputs-dev",
        "map_results": [
            {
                "blueprint": {
                    "tipo_documento": "documento_identificacao",
                    "subtipo_documento": "driver_license",
                    "arquivo_original": "cnh.pdf",
                    "dados_extraidos_do_documento": {"full_name": "WERITON LUIS PETRECA"},
                    "localizacao_documento_s3": {"s3_key_origem": "packages/pkg-map-999/cnh.pdf", "s3_key_resultado_bda": "k", "s3_key_resultado": "r"},
                    "confiabilidade_extracao": {"status_extracao": "sucesso", "confianca_media": "0.98", "observacoes": []}
                },
                "raw_ia": {},
                "input_tokens": 100,
                "output_tokens": 50
            }
        ]
    }

    response = aggregator_module.handler(mock_aggregator_event, None)

    assert response["package_id"] == "pkg-map-999"
    json_estruturado_final = response["json_estruturado"]
    assert len(json_estruturado_final["documentos_analisados"]) == 1
    mock_s3.put_object.assert_called_once()