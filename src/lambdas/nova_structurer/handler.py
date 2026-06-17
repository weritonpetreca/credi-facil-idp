import json
import os
import boto3
from aws_lambda_powertools import Logger
from src.shared.tools import obter_especificacao_ferramenta_loan
from src.shared.models import LoanPackageOutput

logger = Logger(service="nova-structurer")

# Inicialização dos clientes fora do handler para otimização de Cold Start
s3_client = boto3.client("s3")
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")

# Prompt de Sistema para blindar o comportamento do Modelo (DevSecOps Mindset)
PROMPT_SISTEMA = (
    "Você é um especialista em auditoria de dados financeiros e hipotecários. "
    "Sua tarefa é analisar os dados brutos extraídos de documentos e acionar a ferramenta "
    "'estruturar_dados_solicitacao_credito' fornecendo os dados limpos, aplicando a normalização de "
    "CPFs e formatação de datas. Não gere texto livre além da chamada da ferramenta."
)

def montar_payload_bedrock(dados_brutos: dict) -> dict:
    """Prepara o corpo da requisição para a API Converse do Bedrock."""
    tool_config = {
        "tools": [obter_especificacao_ferramenta_loan()]
    }
    
    messages = [
        {
            "role": "user",
            "content": [{"text": f"Dados brutos recebidos para estruturação: {json.dumps(dados_brutos)}"}]
        }
    ]
    
    return {
        "modelId": "amazon.nova-pro-v1:0", # Modelo Pro exigido no SRS
        "messages": messages,
        "system": [{"text": PROMPT_SISTEMA}],
        "toolConfig": tool_config
    }

def processar_resposta_bedrock(bedrock_response: dict, package_id: str, userId: str) -> dict:
    """Captura a saída da ferramenta gerada pelo LLM e envelopa no modelo final de produção."""
    output_message = bedrock_response["output"]["message"]
    tool_requests = output_message.get("toolRequests", [])
    
    if not tool_requests:
        raise ValueError("O modelo Amazon Nova falhou em acionar a ferramenta de estruturação estruturada.")
        
    # Extrai os argumentos que a IA preencheu dentro da ferramenta
    dados_extraidos_ia = json.loads(tool_requests[0]["input"])
    
    # Envelopa os dados conforme o contrato de saída do nosso SRS
    payload_final = {
        "package_id": package_id,
        "status": "COMPLETED",
        "confianca_geral": 0.95, 
        "revisao_humana": False,
        "documentos": {
            "identidade": {
                "nome": dados_extraidos_ia["nome"],
                "cpf": dados_extraidos_ia["cpf"],
                "data_nascimento": dados_extraidos_ia["data_nascimento"],
                "confianca": 0.95
            }
        }
    }
    
    # Validação em runtime: se a IA mandou algo fora do contrato, estoura o erro aqui!
    validado = LoanPackageOutput(**payload_final)
    return validado.model_dump()

def handler(event, context):
    """Ponto de entrada do Step Functions para a estruturação com LLM"""
    try:
        package_id = event.get("package_id")
        user_id = event.get("user_id", "sistema-anonimo")
        bucket_saida = event.get("bda_output_bucket")
        
        # Prefixo base onde o BDA salvou os resultados desse pacote
        prefix_busca = f"bda-output/{package_id}/"

        logger.info(f"Iniciando a fase de estruturação inteligente para o pacote {package_id}")
        logger.info(f"Listando o prefixo {prefix_busca} no bucket {bucket_saida} para mapear a saída real do BDA")

        # 🔍 SOLUÇÃO SÊNIOR: Lista tudo o que o BDA cuspiu dentro da pasta do pacote
        s3_objects = s3_client.list_objects_v2(Bucket=bucket_saida, Prefix=prefix_busca)
        
        if "Contents" not in s3_objects or len(s3_objects["Contents"]) == 0:
            raise FileNotFoundError(f"Nenhum arquivo gerado pelo BDA foi localizado no prefixo {prefix_busca}")

        # Filtra todas as chaves encontradas que terminam com .json
        arquivos_json = [obj["Key"] for obj in s3_objects["Contents"] if obj["Key"].endswith(".json")]
        
        if not arquivos_json:
            raise FileNotFoundError(f"Nenhum arquivo JSON de extração foi encontrado no prefixo {prefix_busca}")

        logger.info(f"Arquivos JSON encontrados no bucket de saída: {arquivos_json}")
        
        # Mapeia dinamicamente a chave real do arquivo gerado pelo Bedrock
        key_real_bda = arquivos_json[0]
        logger.info(f"Puxando dados extraídos diretamente do arquivo real da AWS: {key_real_bda}")

        # 1. Busca o conteúdo do arquivo JSON dinâmico diretamente no S3
        try:
            s3_response = s3_client.get_object(Bucket=bucket_saida, Key=key_real_bda)
            bda_raw_content = s3_response["Body"].read().decode("utf-8")
            dados_brutos = json.loads(bda_raw_content)
        except Exception as s3_err:
            logger.error(f"Falha ao ler o arquivo intermediário do BDA no S3 ({key_real_bda}): {str(s3_err)}")
            raise s3_err

        # 2. Prepara o payload seguindo as especificações da API do Bedrock
        payload_bedrock = montar_payload_bedrock(dados_brutos)
        model_id = payload_bedrock.pop("modelId")

        # 3. Invoca o modelo Amazon Nova Pro via Bedrock Runtime
        logger.info(f"Invocando o modelo {model_id} via Bedrock Runtime...")
        response = bedrock_runtime.invoke_model(
            modelId=model_id,
            body=json.dumps(payload_bedrock)
        )

        response_body = json.loads(response["body"].read().decode("utf-8"))

        # 4. Processa a resposta do modelo e valida usando o Pydantic Model
        resultado_ia = processar_resposta_bedrock(response_body, package_id, user_id)

        # 5. RETORNO ESTRUTURADO: Alinha o contrato exato que a ResultWriter espera receber
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