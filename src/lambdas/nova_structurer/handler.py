import json
import os
import boto3
from aws_lambda_powertools import Logger
from src.shared.tools import obter_especificacao_ferramenta_loan
from src.shared.models import LoanPackageOutput

logger = Logger(service="nova-structurer")

s3_client = boto3.client("s3")
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")

PROMPT_SISTEMA = (
    "Você é um motor analítico de submissão de crédito imobiliário internacional. "
    "Sua tarefa é analisar os dados consolidados extraídos de múltiplos documentos do pacote, "
    "classificar os tipos de documentos identificados e preencher a ferramenta estruturada. "
    "Identifique nomes, documentos (SSN/DL/CPF), rendas (Gross/Net) e saldos bancários."
)

def limpar_ruido_bda(bda_json: dict) -> dict:
    """Remove metadados geométricos e estruturais pesados para focar apenas no texto útil."""
    dados_limpos = {}
    
    # Captura textos puros e linhagens textuais se existirem
    if "text" in bda_json:
        dados_limpos["texto_extraido"] = bda_json["text"]
        
    # Captura o sumário analítico ou blocos de chaves/valores simplificados
    if "key_values" in bda_json:
        dados_limpos["chaves_valores"] = [
            {"chave": kv.get("key"), "valor": kv.get("value")} 
            for kv in bda_json["key_values"] if kv.get("key")
        ]
        
    # Se a estrutura for baseada em arvores de blocos padrão (estilo Textract)
    if "blocks" in bda_json:
        dados_limpos["linhas_texto"] = [
            b.get("text") for b in bda_json["blocks"] 
            if b.get("blockType") == "LINE" and b.get("text")
        ]
        
    # Retorna o dicionário higienizado ou o payload cru caso não encontre chaves conhecidas
    return dados_limpos if dados_limpos else bda_json

def calcular_matriz_score(tabela_clientes: dict) -> dict:
    """Aplica o motor determinístico de scoring sobre o consolidado da tabela de clientes."""
    pontuacao = 100
    justificativas = []
    
    if len(tabela_clientes) > 1:
        pontuacao -= 30
        justificativas.append("Presença de múltiplos proponentes/fiadores no lote (-30 pts).")
        
    for nome, dados in tabela_clientes.items():
        docs = [d["tipo_documento"] for d in dados["documentos_vinculados"]]
        
        # Validação de consistência de acervo por cliente
        if "IDENTITY_DOCUMENT" not in docs:
            pontuacao -= 20
            justificativas.append(f"Cliente {nome} carece de documento oficial de identidade homologado (-20 pts).")
            
        # Avaliação de ranges de renda/balanço
        for doc in dados["documentos_vinculados"]:
            fin = doc["dados_financeiros"]
            renda = fin.get("renda_bruta_informada", 0.0)
            saldo = fin.get("saldo_bancario_fechamento", 0.0)
            
            if doc["tipo_documento"] in ["PAY_STUB", "TAX_DOCUMENT"] and renda < 1000.0 and renda > 0:
                pontuacao -= 15
                justificativas.append(f"Renda identificada para {nome} abaixo do range de segurança (-15 pts).")
            if doc["tipo_documento"] == "BANK_STATEMENT" and saldo > 50000.0:
                pontuacao += 15
                justificativas.append(f"Balanço bancário de {nome} indica liquidez excelente (+15 pts).")

    pontuacao = max(0, min(100, pontuacao))
    risco = "LOW_RISK" if pontuacao >= 80 else ("MEDIUM_RISK" if pontuacao >= 50 else "HIGH_RISK")
    
    return {
        "pontuacao": pontuacao,
        "classificacao_risco": risco,
        "justificativa": " | ".join(justificativas) if justificativas else "Dossiê limpo e em conformidade técnica."
    }

def handler(event, context):
    try:
        package_id = event.get("package_id")
        user_id = event.get("user_id", "sistema")
        bucket_saida = event.get("bda_output_bucket")
        prefix_busca = f"bda-output/{package_id}/"

        logger.info(f"Iniciando varredura relacional para o pacote {package_id}")

        # Lista a pasta inteira de saídas do BDA no S3
        s3_objects = s3_client.list_objects_v2(Bucket=bucket_saida, Prefix=prefix_busca)
        if "Contents" not in s3_objects or len(s3_objects["Contents"]) == 0:
            raise FileNotFoundError(f"Nenhum artefato do BDA localizado no prefixo {prefix_busca}")

        conteudos_brutos = []
        for obj in s3_objects["Contents"]:
            if obj["Key"].endswith(".json") and "manifest" not in obj["Key"].lower():
                s3_response = s3_client.get_object(Bucket=bucket_saida, Key=obj["Key"])
                json_bruto = json.loads(s3_response["Body"].read().decode("utf-8"))
                
                # 🚀 HIGIENIZAÇÃO ATIVADA: Remove o ruído geométrico de cada arquivo individualmente
                json_higienizado = limpar_ruido_bda(json_bruto)
                conteudos_brutos.append(json_higienizado)

        # Configura as ferramentas seguindo o padrão oficial Bedrock Converse
        tool_config = {
            "tools": [obter_especificacao_ferramenta_loan()],
            "toolChoice": {"tool": {"name": "estruturar_dados_solicitacao_credito"}}
        }
        
        messages = [{
            "role": "user",
            "content": [{"text": f"Consolide e classifique a seguinte massa de dados bruta extraída do pacote: {json.dumps(conteudos_brutos)}"}]
        }]

        logger.info("Invocando o Amazon Nova Pro via API Converse...")
        response = bedrock_runtime.converse(
            modelId="amazon.nova-pro-v1:0",
            messages=messages,
            system=[{"text": PROMPT_SISTEMA}],
            toolConfig=tool_config
        )

        # 🚀 CORREÇÃO CRÍTICA: Varre o array content para extrair o toolUse no formato nativo da AWS
        content_blocks = response.get("output", {}).get("message", {}).get("content", [])
        tool_use_block = next((b["toolUse"] for b in content_blocks if "toolUse" in b), None)
        
        if not tool_use_block:
            logger.error(f"Resposta crua do Bedrock sem chamada de ferramenta: {json.dumps(response)}")
            raise ValueError("O modelo falhou em popular a tabela analítica do dossiê.")

        dados_ia = tool_use_block.get("input", {})
        if isinstance(dados_ia, str):
            dados_ia = json.loads(dados_ia)
        
        # Agrupa os achados documentais por cliente (Nome)
        tabela_clientes_final = {}
        for achado in dados_ia.get("achados_documentais", []):
            nome = achado["nome_titular"]
            if nome not in tabela_clientes_final:
                tabela_clientes_final[nome] = {
                    "cadastro": {
                        "nome": nome,
                        "documento_identificacao": achado.get("numero_identificacao", "Não Localizado"),
                        "data_nascimento": achado.get("data_nascimento") if achado.get("data_nascimento") else None
                    },
                    "documentos_vinculados": []
                }
            
            tabela_clientes_final[nome]["documentos_vinculados"].append({
                "tipo_documento": achado["tipo_documento"],
                "confianca": 0.95,
                "dados_financeiros": {
                    "renda_bruta_informada": achado.get("renda_bruta_informada", 0.0),
                    "saldo_bancario_fechamento": achado.get("saldo_bancario_fechamento", 0.0)
                }
            })

        # Calcula a matriz final de score de crédito
        scoring = calcular_matriz_score(tabela_clientes_final)

        # Montagem do payload de saída final validado via Pydantic
        payload_saida = {
            "package_id": package_id,
            "status": "COMPLETED",
            "score_global": scoring,
            "tabela_clientes": tabela_clientes_final
        }

        validado = LoanPackageOutput(**payload_saida)
        return {
            "package_id": package_id,
            "user_id": user_id,
            "confianca_geral": 0.95,
            "revisao_humana": True if scoring["classificacao_risco"] == "HIGH_RISK" else False,
            "json_estruturado": json.loads(validado.model_dump_json())
        }

    except Exception as e:
        logger.error(f"Falha crítica no motor estruturador: {str(e)}")
        raise e