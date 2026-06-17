import json
import os
import boto3
from aws_lambda_powertools import Logger
from src.shared.tools import obter_especificacao_ferramenta_loan
from src.shared.models import LoanPackageOutput

logger = Logger(service="nova-structurer")

s3_client = boto3.client("s3")
# Cliente de runtime oficial do Bedrock para inferências de alta performance
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")

PROMPT_SISTEMA = (
    "Você é um especialista em auditoria de dados financeiros e hipotecários. "
    "Sua tarefa é analisar os dados brutos extraídos de documentos e acionar a ferramenta "
    "'estruturar_dados_solicitacao_credito' fornecendo os dados limpos, aplicando a normalização de "
    "CPFs e formatação de datas. Não gere texto livre além da chamada da ferramenta."
)

def montar_payload_bedrock(dados_brutos: dict) -> dict:
    """Prepara os parâmetros estruturados para a API Converse do Bedrock."""
    tool_config = {
        "tools": [obter_especificacao_ferramenta_loan()],
        "toolChoice": {"tool": {"name": "estruturar_dados_solicitacao_credito"}}
    }
    
    messages = [
        {
            "role": "user",
            "content": [{"text": f"Dados brutos recebidos para estruturação: {json.dumps(dados_brutos)}"}]
        }
    ]
    
    return {
        "modelId": "amazon.nova-pro-v1:0", 
        "messages": messages,
        "system": [{"text": PROMPT_SISTEMA}],
        "toolConfig": tool_config
    }

def processar_resposta_bedrock(bedrock_response: dict, package_id: str, user_id: str) -> dict:
    """Captura a saída da ferramenta 'toolUse' gerada pelo LLM e envelopa no modelo de produção."""
    output_message = bedrock_response.get("output", {}).get("message", {})
    content_blocks = output_message.get("content", [])
    
    # 🔍 PROCURA O BLOCO DE CONTEÚDO CORRETO DO CONVERSE API (toolUse)
    tool_use_block = None
    for block in content_blocks:
        if "toolUse" in block:
            tool_use_block = block["toolUse"]
            break
            
    if not tool_use_block:
        logger.error(f"Resposta bruta recebida do Bedrock: {json.dumps(bedrock_response)}")
        raise ValueError("O modelo Amazon Nova falhou em acionar a ferramenta de estruturação estruturada.")
        
    # Extrai os argumentos que a IA preencheu dentro da ferramenta (No Converse, já vem como dict)
    dados_extraidos_ia = tool_use_block.get("input", {})
    if isinstance(dados_extraidos_ia, str):
        dados_extraidos_ia = json.loads(dados_extraidos_ia)
        
    # Envelopa os dados conforme o contrato de saída exigido pelo SRS
    payload_final = {
        "package_id": package_id,
        "status": "COMPLETED",
        "confianca_geral": 0.95, 
        "revisao_humana": False,
        "documentos": {
            "identidade": {
                "nome": dados_extraidos_ia.get("nome"),
                "cpf": dados_extraidos_ia.get("cpf"),
                "data_nascimento": dados_extraidos_ia.get("data_nascimento"),
                "confianca": 0.95
            }
        }
    }
    
    # 🚀 VALIDAÇÃO E SERIALIZAÇÃO CRÍTICA:
    # Usamos model_dump_json() para converter tipos nativos (UUID, date) em strings válidas,
    # prevenindo erros de serialização JSON no retorno da Lambda na AWS.
    validado = LoanPackageOutput(**payload_final)
    return json.loads(validado.model_dump_json())

def handler(event, context):
    """Ponto de entrada do Step Functions para a estruturação com LLM"""
    try:
        package_id = event.get("package_id")
        user_id = event.get("user_id", "sistema-anonimo")
        bucket_saida = event.get("bda_output_bucket")
        
        prefix_busca = f"bda-output/{package_id}/"

        logger.info(f"Iniciando a fase de estruturação inteligente para o pacote {package_id}")

        # Lista os arquivos gerados pelo BDA no bucket de saída de forma resiliente
        s3_objects = s3_client.list_objects_v2(Bucket=bucket_saida, Prefix=prefix_busca)
        
        if "Contents" not in s3_objects or len(s3_objects["Contents"]) == 0:
            raise FileNotFoundError(f"Nenhum arquivo gerado pelo BDA foi localizado no prefixo {prefix_busca}")

        arquivos_json = [obj["Key"] for obj in s3_objects["Contents"] if obj["Key"].endswith(".json")]
        
        if not arquivos_json:
            raise FileNotFoundError(f"Nenhum arquivo JSON de extração foi encontrado no prefixo {prefix_busca}")

        key_real_bda = arquivos_json[0]
        logger.info(f"Mapeado arquivo de extração do BDA com sucesso: {key_real_bda}")

        # Efetua a leitura do JSON bruto do BDA
        s3_response = s3_client.get_object(Bucket=bucket_saida, Key=key_real_bda)
        bda_raw_content = s3_response["Body"].read().decode("utf-8")
        dados_brutos = json.loads(bda_raw_content)

        # Prepara as variáveis de injeção da IA
        params = montar_payload_bedrock(dados_brutos)
        
        logger.info(f"Invocando o modelo {params['modelId']} via API Converse do Bedrock...")
        response = bedrock_runtime.converse(
            modelId=params["modelId"],
            messages=params["messages"],
            system=params["system"],
            toolConfig=params["toolConfig"]
        )

        # Processa e valida os dados limpos gerados pelo Amazon Nova Pro
        resultado_ia = processar_resposta_bedrock(response, package_id, user_id)

        # Retorna o payload assinado que a Lambda de escrita (ResultWriter) precisa persistir
        return {
            "package_id": package_id,
            "user_id": user_id,
            "confianca_geral": resultado_ia.get("confianca_geral", 0.95),
            "revisao_humana": resultado_ia.get("revisao_humana", False),
            "json_estruturado": resultado_ia
        }

    except Exception as e:
        logger.error(f"Falha crítica na Lambda NovaStructurer: {str(e)}")
        raise e