def obter_especificacao_ferramenta_loan() -> dict:
    """
    Retorna a especificação da ferramenta analítica para o Amazon Bedrock.
    Contrato unificado e tipado para extração multi-documento e multi-cliente.
    """
    return {
        "toolSpec": {
            "name": "estruturar_dados_solicitacao_credito",
            "description": "Classifica e extrai os dados de todos os documentos e pessoas localizadas no pacote.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "achados_documentais": {
                            "type": "array",
                            "description": "Lista de todos os documentos e registros de pessoas identificados na massa de dados",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "nome_titular": {
                                        "type": "string",
                                        "description": "Nome completo associado a este documento específico"
                                    },
                                    "tipo_documento": {
                                        "type": "string",
                                        "enum": ["IDENTITY_DOCUMENT", "PAY_STUB", "BANK_STATEMENT", "TAX_DOCUMENT", "UNKNOWN"]
                                    },
                                    "numero_identificacao": {
                                        "type": "string",
                                        "description": "SSN, CPF ou número de licença encontrado"
                                    },
                                    "data_nascimento": {
                                        "type": "string",
                                        "description": "Data de nascimento se disponível (YYYY-MM-DD)"
                                    },
                                    "renda_bruta_informada": {
                                        "type": "number",
                                        "description": "Valor de Gross Pay ou salários localizados"
                                    },
                                    "saldo_bancario_fechamento": {
                                        "type": "number",
                                        "description": "Saldo final de contas correntes ou investimentos"
                                    },
                                    "confianca_extracao": {
                                        "type": "number",
                                        "description": "Score de 0.0 a 1.0 avaliando a clareza e ausência de rasuras nos dados deste documento."
                                    }
                                },
                                "required": ["nome_titular", "tipo_documento", "confianca_extracao"]
                            }
                        }
                    },
                    "required": ["achados_documentais"]
                }
            }
        }
    }