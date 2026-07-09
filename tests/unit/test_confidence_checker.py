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

    # Formato real confirmado em produção (result.json do BDA custom_output):
    # inference_result é FLAT (campo: valor); explainability_info é uma LISTA com 1 dict.
    campos_dl = {
        "identification_document_type": "DRIVER LICENSE",
        "document_number": "1234567",
        "full_name": "WERITON LUIS PETRECA",
        "date_of_birth": "1989-10-12",
        "expiration_date": "2030-10-12",
        "issuing_state": "MG",
    }
    bda_output_perfeito = {
        "inference_result": campos_dl,
        "explainability_info": [
            {campo: {"success": True, "confidence": 0.95} for campo in campos_dl}
        ],
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

    # CAMPOS_CRITICOS_POR_SUBTIPO["pay_stub"] exige 13 campos — o fixture precisa
    # cobrir todos eles (senão os "ausentes" também contam como falha, e o teste
    # deixa de isolar exatamente 1 falha). Só employee_name fica com confiança baixa.
    campos_ps = {
        "employer_name": "CrediFacil Corp",
        "employee_name": "W#riton Lui%",
        "social_security_number": "987-65-4321",
        "taxable_marital_status": "Married",
        "pay_period_ending": "2026-06-18",
        "pay_date": "2026-06-20",
        "gross_pay_this_period": "452.43",
        "gross_pay_ytd": "23526.80",
        "net_pay_this_period": "291.90",
        "federal_income_tax": "40.60",
        "social_security_tax": "28.05",
        "medicare_tax": "6.56",
        "retirement_401k": "28.85",
    }
    confiancas = {campo: {"success": True, "confidence": 0.90} for campo in campos_ps}
    confiancas["employee_name"] = {"success": True, "confidence": 0.45}  # único campo ruim

    bda_output_corrompido = {
        "inference_result": campos_ps,
        "explainability_info": [confiancas],
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