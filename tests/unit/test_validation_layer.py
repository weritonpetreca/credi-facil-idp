import pytest
from pydantic import ValidationError
from src.shared.models import LoanPackageOutput, ScoreAnalise

def test_deve_validar_payload_da_ia_com_schema_pydantic_completo_e_valido():
    """Garante que o modelo LoanPackageOutput compila perfeitamente com os novos campos mandatórios."""
    payload_valido = {
        "package_id": "8f3b9c2e-4a1d-4f7b-9c3e-2a1b4c7d5e6f",
        "status": "COMPLETED",
        "score_global": {
            "pontuacao": 92,
            "classificacao_risco": "BAIXO_RISCO",
            "justificativa": "Metadados extraídos em conformidade total e score de crédito excelente."
        },
        "tabela_clientes": {
            "Weriton_L_Petreca": {
                "cadastro": {
                    "nome": "Weriton L Petreca",
                    "documento_identificacao": "529.982.247-25",
                    "data_nascimento": "1989-10-12"
                },
                "documentos_vinculados": []
            }
        }
    }
    
    model = LoanPackageOutput(**payload_valido)
    assert model.status == "COMPLETED"
    assert model.score_global.pontuacao == 92
    assert "Weriton_L_Petreca" in model.tabela_clientes
    assert model.tabela_clientes["Weriton_L_Petreca"].cadastro.nome == "Weriton L Petreca"

def test_deve_falhar_se_o_score_global_obrigatorio_estiver_ausente():
    """Garante a barreira do Pydantic barrando a criação se o nó de score sumir."""
    payload_incompleto = {
        "package_id": "8f3b9c2e-4a1d-4f7b-9c3e-2a1b4c7d5e6f",
        "status": "COMPLETED",
        "tabela_clientes": {}
    }
    
    with pytest.raises(ValidationError) as exc_info:
        LoanPackageOutput(**payload_incompleto)
        
    assert "score_global" in str(exc_info.value)
    assert "Field required" in str(exc_info.value)

def test_deve_falhar_se_pontuacao_do_score_passar_do_limite_maximo_permitido():
    """Garante a validação de fronteira (le=100) do Pydantic para a nota de crédito."""
    with pytest.raises(ValidationError) as exc_info:
        ScoreAnalise(
            pontuacao=150,  # Ultrapassa o teto máximo de 100
            classificacao_risco="ALTO_RISCO",
            justificativa= "Pontuação fraudulenta/inválida"
        )
        
    assert "Input should be less than or equal to 100" in str(exc_info.value)