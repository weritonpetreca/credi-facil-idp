import json
from aws_lambda_powertools import Logger
from src.shared.tools import obter_especificacao_ferramenta

logger = Logger(child=True)

class AiEnricher:
    """
    Camada especialista em LLM (Inference Layer).
    Responsável única por empacotar o contexto do documento e se comunicar com o Amazon Bedrock.

    A tool spec NÃO é mais fixa: cada subtipo documental tem sua própria (ver
    shared/tools.py), escolhida em tempo de execução por quem chama executar().
    Isso é o que permite ao Nova Lite receber um "contrato" (schema) relevante
    para W2, CNH, extrato ou apólice, em vez de um único schema genérico
    enviesado para holerite.
    """
    def __init__(self, bedrock_runtime, model_id: str, prompt_sistema: str):
        self.bedrock_runtime = bedrock_runtime
        self.model_id = model_id
        self.prompt_sistema = prompt_sistema

    def executar(self, subtipo: str, texto_integral: str, json_higienizado: dict, string_prompt_humanos: str = "", guardrail_id: str = None, guardrail_version: str = "1") -> dict:
        """
        Envia o contexto do documento para a Nova Lite, montando os argumentos
        dinamicamente para evitar ParamValidationError com propriedades nulas.

        `subtipo` decide QUAL tool spec (e portanto qual "contrato" de extração)
        é oferecida ao modelo — ver obter_especificacao_ferramenta() em shared/tools.py.
        """
        logger.info(f"AiEnricher acionando modelo {self.model_id} (subtipo={subtipo}) com payload de {len(texto_integral)} caracteres.")

        tool_spec = obter_especificacao_ferramenta(subtipo)
        nome_ferramenta = tool_spec["toolSpec"]["name"]
        tool_config = {
            "tools": [tool_spec],
            "toolChoice": {"tool": {"name": nome_ferramenta}}
        }
        
        conteudo_input_hibrido = (
            f"--- TRANSCRIÇÃO INTEGRAL E TABELAS DO DOCUMENTO ---\n{texto_integral}\n\n"
            f"--- ESTRUTURA DE METADADOS COMPLETA ---\n{json.dumps(json_higienizado, ensure_ascii=False)}"
            f"{string_prompt_humanos}"
        )

        # 🚀 CONSTRUÇÃO DINÂMICA: Evita passar chaves com valor None para o Boto3
        converse_kwargs = {
            "modelId": self.model_id,
            "messages": [{"role": "user", "content": [{"text": conteudo_input_hibrido}]}],
            "system": [{"text": self.prompt_sistema}],
            "toolConfig": tool_config,
            "inferenceConfig": {"temperature": 0.0, "maxTokens": 4000}
        }

        # Só injeta o guardrail se ele realmente existir e for uma string válida
        if guardrail_id and str(guardrail_id).strip() and str(guardrail_id).lower() != "none":
            logger.info(f"Injetando configuração ativa de Guardrail: {guardrail_id} (v{guardrail_version})")
            converse_kwargs["guardrailConfig"] = {
                "guardrailIdentifier": str(guardrail_id),
                "guardrailVersion": str(guardrail_version),
                "trace": "disabled"
            }

        response = self.bedrock_runtime.converse(**converse_kwargs)

        usage = response.get("usage", {})
        content_blocks = response.get("output", {}).get("message", {}).get("content", [])
        tool_use_block = next((b["toolUse"] for b in content_blocks if "toolUse" in b), None)
        
        if not tool_use_block:
            raise ValueError("O modelo de fundação falhou ao tentar acionar a ferramenta de estruturação.")

        achado = tool_use_block.get("input", {})
        if isinstance(achado, str):
            achado = json.loads(achado)

        return {
            "raw_fields_ia": achado,
            "input_tokens": usage.get("inputTokens", 0),
            "output_tokens": usage.get("outputTokens", 0)
        }