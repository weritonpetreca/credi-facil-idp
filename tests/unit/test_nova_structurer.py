import json
import pytest
from unittest.mock import MagicMock

# Importação explícita dos três handlers desacoplados para validação atômica
import src.lambdas.nova_structurer.lister as lister_module
import src.lambdas.nova_structurer.handler as unit_handler_module
import src.lambdas.nova_structurer.aggregator as aggregator_module

class MockS3Body:
    def __init__(self, text):
        self.text = text
    def read(self):
        return self.text.encode("utf-8")

@pytest.fixture
def base_event():
    return {
        "package_id": "pkg-map-999",
        "bda_output_bucket": "credifacil-outputs-dev"
    }

# ==========================================================================
# 🔍 1. TESTES DO COMPONENTE: LISTER
# ==========================================================================
def test_lister_deve_mapear_documentos_e_buscar_flags_do_banco(base_event, monkeypatch):
    """Garante que o Lister varre o S3 e envelopa o array correto para o Step Functions MAP."""
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
    
    # Valida se o leque de paralelismo granular foi montado com os 2 itens isolados
    assert "documentos_para_estruturar" in response
    assert len(response["documentos_para_estruturar"]) == 2
    assert response["documentos_para_estruturar"][0]["nome_pdf_original"] == "cnh_frente"

# ==========================================================================
# 🧠 2. TESTES DO COMPONENTE: UNIT STRUCTURER (HANDLER)
# ==========================================================================
def test_handler_unitario_deve_estruturar_um_unico_documento_via_tool_calling(monkeypatch):
    """Garante que o Structurer processa apenas um item sem loops e retorna as métricas de tokens."""
    mock_s3 = MagicMock()
    mock_bedrock = MagicMock()

    mock_s3.get_object.return_value = {
        "Body": MockS3Body('{"text": "Transcrição simulada OCR da CNH do cliente Weriton Luis Petreca"}')
    }
    
    mock_bedrock.converse.return_value = {
        "usage": {"inputTokens": 150, "outputTokens": 90},
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
                                "confianca_extracao": 0.98,
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

    # Simula o payload que o Step Functions MAP injetará para um único item do array
    mock_map_item_event = {
        "package_id": "pkg-map-999",
        "bda_output_bucket": "credifacil-outputs-dev",
        "nome_pdf_original": "cnh_frente.pdf",
        "s3_key_bda": "bda-output/pkg-map-999/cnh_frente/custom_output.json"
    }

    response = unit_handler_module.handler(mock_map_item_event, None)

    assert "blueprint" in response
    assert response["blueprint"]["subtipo_documento"] == "driver_license"
    assert response["input_tokens"] == 150
    assert response["output_tokens"] == 90
    assert response["blueprint"]["dados_extraidos_do_documento"]["full_name"] == "WERITON LUIS PETRECA"
    
    # Prova que salvou o arquivo individual na rota taxonômica isolada
    assert mock_s3.put_object.call_count == 1

# ==========================================================================
# 📊 3. TESTES DO COMPONENTE: AGGREGATOR
# ==========================================================================
def test_aggregator_deve_consolidar_lote_e_emitir_metricas_emf(monkeypatch):
    """Garante a agregação final dos resultados paralelos e persistência condicional do lote."""
    mock_s3 = MagicMock()
    monkeypatch.setattr(aggregator_module, "s3_client", mock_s3)
    
    # Desativa o envio real de métricas CloudWatch Powertools no teste para evitar side-effects
    monkeypatch.setattr(aggregator_module.metrics, "add_metric", lambda name, unit, value: None)

    # Simula a agregação de dois resultados que vieram das Lambdas paralelas do MAP
    mock_aggregator_event = {
        "package_id": "pkg-map-999",
        "user_id": "analista-weriton",
        "execute_score": False, # Gate fechado força escrita do output.json mestre
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
            },
            {
                "blueprint": {
                    "tipo_documento": "extrato_bancario",
                    "subtipo_documento": "account_statement",
                    "arquivo_original": "extrato.pdf",
                    "dados_extraidos_do_documento": {"account_number": "12345"},
                    "localizacao_documento_s3": {"s3_key_origem": "packages/pkg-map-999/extrato.pdf", "s3_key_resultado_bda": "k", "s3_key_resultado": "r"},
                    "confiabilidade_extracao": {"status_extracao": "sucesso", "confianca_media": "0.95", "observacoes": []}
                },
                "raw_ia": {},
                "input_tokens": 200,
                "output_tokens": 100
            }
        ]
    }

    response = aggregator_module.handler(mock_aggregator_event, None)

    assert response["package_id"] == "pkg-map-999"
    assert response["execute_score"] is False
    
    json_estruturado_final = response["json_estruturado"]
    assert len(json_estruturado_final["documentos_analisados"]) == 2
    
    # Valida o somatório consolidado de tokens de IA para auditoria FinOps
    assert json_estruturado_final["sistema"]["processamento"]["quantidade_tokens"]["total_tokens"] == 450
    
    # Como execute_score era falso, prova que salvou o arquivo mestre unificado de lote no S3
    mock_s3.put_object.assert_called_once()
    _, kwargs = mock_s3.put_object.call_args
    assert kwargs["Key"] == "results/packages/pkg-map-999/output.json"