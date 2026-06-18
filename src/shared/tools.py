def obter_especificacao_ferramenta_loan() -> dict:
    """
    Retorna a especificação da ferramenta analítica para um ÚNICO documento.
    Evita sobrecarga de contexto ao processar um arquivo por vez.
    """
    return {
        "toolSpec": {
            "name": "estruturar_dados_documento_individual",
            "description": "Extrai os dados cadastrais e financeiros de um único documento específico do pacote.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "nome_titular": {
                            "type": "string",
                            "description": "Nome completo da pessoa associada a este documento específico (Ex: JOHN STILES, MARÍA GARCÍA)."
                        },
                        "tipo_documento": {
                            "type": "string",
                            "enum": ["IDENTITY_DOCUMENT", "PAY_STUB", "BANK_STATEMENT", "TAX_DOCUMENT", "UNKNOWN"],
                            "description": "Classificação estrita do tipo de documento analisado."
                        },
                        "numero_identificacao": {
                            "type": "string",
                            "description": "Número de documento localizado (CPF, SSN, Licença de motorista, etc)."
                        },
                        "data_nascimento": {
                            "type": "string",
                            "description": "Data de nascimento se disponível no documento (YYYY-MM-DD)."
                        },
                        "renda_bruta_informada": {
                            "type": "number",
                            "description": "Valor de Gross Pay, salários ou rendas brutas localizadas (Apenas para holerites ou Tax Documents)."
                        },
                        "saldo_bancario_fechamento": {
                            "type": "number",
                            "description": "Saldo final ou de fechamento da conta (Apenas para Bank Statements)."
                        },
                        "confianca_extracao": {
                            "type": "number",
                            "description": "Score de 0.0 a 1.0 avaliando a clareza e legibilidade dos dados deste documento."
                        }
                    },
                    "required": ["nome_titular", "tipo_documento", "confianca_extracao"]
                }
            }
        }
    }