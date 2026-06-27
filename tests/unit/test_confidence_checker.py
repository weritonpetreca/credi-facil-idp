import json
import pytest
from src.lambdas.confidence_checker.handler import avaliar_confianca

def test_deve_exigir_revisao_humana_quando_campo_critico_tiver_baixa_confianca():
    # Mock de dados que antes estava em um arquivo externo
    mock_data = {
        "documentType": "IdentityDocument",
        "extractedFields": {
            "nome": {"value": "Weriton", "confidence": 0.95},
            "cpf": {"value": "529.982.247-25", "confidence": 0.78},
            "data_nascimento": {"value": "1989-12-25", "confidence": 0.91}
        }
    }
    resultado = avaliar_confianca(mock_data)
    # O sistema precisa detectar que precisa de revisão por causa do CPF
    assert resultado["needs_human_review"] is True
    assert "cpf" in resultado["low_confidence_fields"]
    assert resultado["status"] == "NEEDS_REVIEW"

def test_deve_passar_direto_se_todos_os_campos_forem_confiaveis():
    mock_perfeito = {
        "documentType": "IdentityDocument",
        "extractedFields": {
            "nome": {"value": "Weriton", "confidence": 0.95},
            "cpf": {"value": "529.982.247-25", "confidence": 0.99},
            "data_nascimento": {"value": "1989-12-25", "confidence": 0.91}
        }
    }
    
    resultado = avaliar_confianca(mock_perfeito)
    
    assert resultado["needs_human_review"] is False
    assert len(resultado["low_confidence_fields"]) == 0
    assert resultado["status"] == "PROCESSING"