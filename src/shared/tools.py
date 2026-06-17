def obter_especificacao_ferramenta_loan() -> dict:
    """
    Retorna a especificação da ferramenta que o Amazon Nova preencherá.
    Este formato segue estritamente o padrão exigido pela API Converse do Bedrock.
    """
    return {
        "toolSpec": {
            "name": "estruturar_dados_solicitacao_credito",
            "description": "Formata e padroniza os dados extraídos de documentos hipotecários e de identidade internacionais.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "nome": {"type": "string", "description": "Nome completo do cliente extraído do documento"},
                        # 🚀 MUDANÇA: Campo generalizado para aceitar SSN, Driver License ou CPF
                        "documento_identificacao": {
                            "type": "string", 
                            "description": "Número do documento de identidade localizado (pode ser SSN, Driver License ou CPF)"
                        },
                        "data_nascimento": {"type": "string", "description": "Data de nascimento no padrão YYYY-MM-DD"}
                    },
                    "required": ["nome", "documento_identificacao", "data_nascimento"]
                }
            }
        }
    }