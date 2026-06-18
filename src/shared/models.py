from pydantic import BaseModel, Field, UUID4
from typing import Optional, List, Dict, Any
from datetime import date

class ScoreAnalise(BaseModel):
    pontuacao: int = Field(..., ge=0, le=100)
    classificacao_risco: str
    justificativa: str

class CadastroModel(BaseModel):
    nome: str = Field(..., description="Nome completo do indivíduo")
    documento_identificacao: str = Field(..., description="SSN, Driver License ou CPF identificado")
    data_nascimento: Optional[date] = Field(None, description="Data de nascimento formatada")

class DocumentoExtraido(BaseModel):
    tipo_documento: str = Field(..., description="IDENTITY_DOCUMENT, PAY_STUB, BANK_STATEMENT, TAX_DOCUMENT")
    confianca: float = Field(..., ge=0.0, le=1.0)
    dados_financeiros: Dict[str, Any] = Field(default_factory=dict, description="Dados de renda ou saldo absorvidos")

class ClienteConsolidado(BaseModel):
    cadastro: CadastroModel
    documentos_vinculados: List[DocumentoExtraido] = Field(default_factory=list)

class LoanPackageOutput(BaseModel):
    package_id: UUID4
    status: str
    score_global: ScoreAnalise
    tabela_clientes: Dict[str, ClienteConsolidado] = Field(
        default_factory=dict, 
        description="Mapeamento tipo tabela indexada pelo nome do cliente"
    )