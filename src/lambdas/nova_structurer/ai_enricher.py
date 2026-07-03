import json
from aws_lambda_powertools import Logger
from src.shared.tools import obter_especificacao_ferramenta_loan

logger = Logger(child=True)

class AiEnricher:
    """
    Camada especialista em LLM (Inference Layer).
    Responsável única por empacotar o contexto do documento e se comunicar com o Amazon Bedrock.
    Utiliza o texto completo para extrair subestruturas hierárquicas complexas com segurança.
    """
    def __init__(self, bedrock_runtime, model_id: str, prompt_sistema: str):
        self.bedrock_runtime = bedrock_runtime
        self.model_id = model_id
        self.prompt_sistema = prompt_sistema

    def executar(self, texto_integral: str, json_higienizado: dict, string_prompt_humanos: str = "") -> dict:
        """
        Envia o contexto robusto e unificado do documento para a Nova Lite,
        forçando o preenchimento estruturado via Tool Calling.
        """
        logger.info(f"AiEnricher acionando modelo {self.model_id} com payload de {len(texto_integral)} caracteres.")
        
        tool_config = {
            "tools": [obter_especificacao_ferramenta_loan()],
            "toolChoice": {"tool": {"name": "estruturar_dados_documento_cliente_unico"}}
        }
        
        # Alimenta a IA com a transcrição completa (Markdown de tabelas) vinda da standard_output
        conteudo_input_hibrido = (
            f"--- TRANSCRIÇÃO INTEGRAL E TABELAS DO DOCUMENTO ---\n{texto_integral}\n\n"
            f"--- ESTRUTURA DE METADADOS COMPLETA ---\n{json.dumps(json_higienizado, ensure_ascii=False)}"
            f"{string_prompt_humanos}"
        )

        response = self.bedrock_runtime.converse(
            modelId=self.model_id,
            messages=[{"role": "user", "content": [{"text": conteudo_input_hibrido}]}],
            system=[{"text": self.prompt_sistema}],
            toolConfig=tool_config,
            guardrailConfig={
                "guardrailIdentifier": None,  # Injetado dinamicamente via variáveis de ambiente no Handler principal se necessário
                "guardrailVersion": "1",
                "trace": "disabled"
            },
            inferenceConfig={"temperature": 0.0, "maxTokens": 4000}
        )

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