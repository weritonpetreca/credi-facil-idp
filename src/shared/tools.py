def obter_especificacao_ferramenta_loan() -> dict:
    """
    Retorna a especificação da ferramenta analítica para extração isolada 
    de documentos focada em um único cliente mestre.
    """
    return {
        "toolSpec": {
            "name": "estruturar_dados_documento_cliente_unico",
            "description": "Extrai os dados cadastrais, financeiros e metadados de um único documento pertencente ao cliente do lote.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "tipo_classificado": {
                            "type": "string",
                            "enum": ["IDENTITY_DOCUMENT", "PAY_STUB", "BANK_STATEMENT", "TAX_DOCUMENT", "PAYROLL_CHECK", "PROPERTY_DOCUMENT", "UNKNOWN"],
                            "description": "Classificação estrita do tipo de documento analisado."
                        },
                        "nome_titular": {
                            "type": "string",
                            "description": "Nome completo do titular/beneficiário/empregado identificado no documento em caixa alta."
                        },
                        "numero_documento_identificacao": {
                            "type": "string",
                            "description": "Número do documento localizado (SSN, CPF, número do passaporte, CNH, etc) sem máscaras."
                        },
                        "data_nascimento": {
                            "type": "string",
                            "description": "Data de nascimento do titular se disponível (YYYY-MM-DD)."
                        },
                        "renda_bruta_informada": {
                            "type": "number",
                            "description": "Valor de Gross Pay, salários ou rendas brutas localizadas (Apenas para holerites, cheques de pagamento ou Tax Documents)."
                        },
                        "saldo_bancario_fechamento": {
                            "type": "number",
                            "description": "Saldo final ou de fechamento da conta (Apenas para Bank Statements)."
                        },
                        "detalhes_cadastrais": {
                            "type": "object",
                            "properties": {
                                "tipo_especifico_id": {"type": "string", "enum": ["RG", "CNH", "Passaporte", "Driver License", "Outro"]},
                                "orgao_emissor": {"type": "string"},
                                "estado_emissor": {"type": "string"},
                                "pais_emissor": {"type": "string"},
                                "data_emissao": {"type": "string"},
                                "data_validade": {"type": "string"}
                            }
                        },
                        "campos_extraidos_brutos": {
                            "type": "object",
                            "description": "Dicionário de chave-valor contendo os dados mais relevantes textuais extraídos do corpo do documento para auditoria rápida."
                        },
                        "confianca_extracao": {
                            "type": "number",
                            "description": "Score de 0.0 a 1.0 avaliando a clareza e legibilidade dos dados deste documento."
                        },
                        "alertas_inconsistencias": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Lista de alertas ou problemas visuais/cadastrais detectados neste documento específico."
                        }
                    },
                    "required": ["tipo_classificado", "nome_titular", "confianca_extracao", "campos_extraidos_brutos"]
                }
            }
        }
    }