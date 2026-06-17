from pydantic import BaseModel, Field, UUID4
from typing import Optional
from datetime import date

class IdentidadeModel(BaseModel):
    nome: str = Field(..., description="Nome completo extraído do documento")
    # 🚀 MUDANÇA: Campo internacionalizado para suportar a massa de dados do Hackathon
    documento_identificacao: str = Field(..., description="Documento de identificação (SSN, Driver License ou CPF)")
    data_nascimento: date = Field(..., description="Data de nascimento no padrão ISO YYYY-MM-DD")
    confianca: float = Field(..., ge=0.0, le=1.0)

class DocumentosPacote(BaseModel):
    identidade: IdentidadeModel

class LoanPackageOutput(BaseModel):
    package_id: UUID4
    status: str
    confianca_geral: float = Field(..., ge=0.0, le=1.0)
    revisao_humana: bool
    documentos: DocumentosPacote