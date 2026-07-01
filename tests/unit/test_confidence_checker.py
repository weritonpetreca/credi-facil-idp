import json
import pytest
from src.lambdas.confidence_checker.handler import handler

class MockS3Body:
    def __init__(self, content_dict):
        self.content_str = json.dumps(content_dict)
    def read(self):
        return self.content_str.encode("utf-8")

@pytest.fixture
def base_event():
    """Gera o payload padrão que a State Machine injeta na Lambda de auditoria."""
    return {
        "package_id": "pkg-test-123",
        "bda_output_bucket": "credifacil-bda-output-dev"
    }

def test_deve_marcar_como_clean_se_todos_os_campos_forem_confiaveis(base_event, monkeypatch):
    """Garante o fluxo feliz se a IA extraiu dados cadastrais com alta acurácia."""
    
    monkeypatch.setattr("src.lambdas.confidence_checker.handler.s3_client.list_objects_v2", 
        lambda Bucket, Prefix: {"Contents": [{"Key": "bda-output/pkg-test-123/driver_license.json"}]})

    bda_output_perfeito = {
        "extractedFields": {
            "document_number": {"value": "1234567", "confidence": 0.95},
            "full_name": {"value": "WERITON LUIS PETRECA", "confidence": 0.99},
            "expiration_date": {"value": "2030-10-12", "confidence": 0.92}
        }
    }
    monkeypatch.setattr("src.lambdas.confidence_checker.handler.s3_client.get_object",
        lambda Bucket, Key: {"Body": MockS3Body(bda_output_perfeito)})

    response = handler(base_event, None)
    
    assert response["audit_status"] == "CLEAN"
    assert response["failed_fields_count"] == 0
    assert "failed_fields_metadata" in response
    assert len(response["failed_fields_metadata"]) == 0

def test_deve_exigir_revisao_humana_e_notificar_se_campo_critico_tiver_baixa_confianca(base_event, monkeypatch):
    """Garante o Fail-Safe do SRS: Se um dado crucial falhar, retorna os metadados estruturados para a State Machine."""
    
    monkeypatch.setattr("src.lambdas.confidence_checker.handler.s3_client.list_objects_v2", 
        lambda Bucket, Prefix: {"Contents": [{"Key": "bda-output/pkg-test-123/pay_stub.json"}]})

    bda_output_corrompido = {
        "extractedFields": {
            "employee_name": {"value": "W#riton Lui%", "confidence": 0.45},
            "pay_date": {"value": "2026-06-20", "confidence": 0.91},
            "employer_name": {"value": "CrediFacil Corp", "confidence": 0.88}
        }
    }
    monkeypatch.setattr("src.lambdas.confidence_checker.handler.s3_client.get_object",
        lambda Bucket, Key: {"Body": MockS3Body(bda_output_corrompido)})

    response = handler(base_event, None)
    
    assert response["audit_status"] == "NEEDS_REVISION"
    assert response["failed_fields_count"] == 1
    assert "failed_fields_metadata" in response
    assert len(response["failed_fields_metadata"]) == 1
    assert response["failed_fields_metadata"][0]["campo_afetado"] == "employee_name"
    assert response["failed_fields_metadata"][0]["confidence_score"] == 0.45