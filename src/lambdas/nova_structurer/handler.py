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
    "Você é um agente analítico especialista em extração de dados para crédito imobiliário. "
    "Sua única tarefa é analisar o texto bruto extraído de UM ÚNICO documento e mapear seus dados "
    "na ferramenta estruturada fornecida. Identifique com precisão o nome do titular e valores financeiros."
)

def limpar_ruido_recursivo(dados: any) -> any:
    CHAVES_INUTEIS = {
        "boundingBox", "polygon", "geometry", "coordinates", "location", 
        "pageNumber", "blockId", "relationships", "bounding_box", "spatial_insight",
        "geometryData", "xy", "box"
    }
    if isinstance(dados, dict):
        return {k: limpar_ruido_recursivo(v) for k, v in dados.items() if k not in CHAVES_INUTEIS}
    elif isinstance(dados, list):
        return [limpar_ruido_recursivo(item) for item in dados]
    return dados

def calcular_matriz_score_mercado(tabela_clientes: dict) -> dict:
    pontuacao = 0
    justificativas = []
    
    if len(tabela_clientes) > 1:
        justificativas.append("Análise consolidada multi-proponente detectada no dossiê.")

    for nome, dados in tabela_clientes.items():
        score_individuo = 0
        justificativas_individuo = []
        
        doc_id = dados["cadastro"].get("documento_identificacao", "")
        if doc_id and "não localizado" not in doc_id.lower():
            score_individuo += 30
            justificativas_individuo.append("KYC homologado (30/30 pts).")
        else:
            justificativas_individuo.append("Inconsistência cadastral (0/30 pts).")

        renda_maxima = 0.0
        for doc in dados["documentos_vinculados"]:
            if doc["tipo_documento"] in ["PAY_STUB", "TAX_DOCUMENT"]:
                renda_doc = float(doc["dados_financeiros"].get("renda_bruta_informada", 0.0))
                if renda_doc > renda_maxima:
                    renda_maxima = renda_doc
                    
        if renda_maxima >= 4000.0:
            score_individuo += 40
            justificativas_individuo.append(f"Renda ${renda_maxima:.2f} excelente (40/40 pts).")
        elif 2000.0 <= renda_maxima < 4000.0:
            score_individuo += 25
            justificativas_individuo.append(f"Renda ${renda_maxima:.2f} moderada (25/40 pts).")
        else:
            justificativas_individuo.append("Renda insuficiente ou não localizada (0/40 pts).")

        saldo_maximo = 0.0
        for doc in dados["documentos_vinculados"]:
            if doc["tipo_documento"] == "BANK_STATEMENT":
                saldo_doc = float(doc["dados_financeiros"].get("saldo_bancario_fechamento", 0.0))
                if saldo_doc > saldo_maximo:
                    saldo_maximo = saldo_doc
                    
        if saldo_maximo >= 10000.0:
            score_individuo += 30
            justificativas_individuo.append(f"Liquidez ${saldo_maximo:.2f} robusta (30/30 pts).")
        elif 1500.0 <= saldo_maximo < 10000.0:
            score_individuo += 15
            justificativas_individuo.append(f"Liquidez ${saldo_maximo:.2f} em atenção (15/30 pts).")
        else:
            justificativas_individuo.append("Sem colchão de liquidez (0/30 pts).")

        pontuacao += score_individuo
        justificativas.append(f"[{nome}]: " + " ".join(justificativas_individuo))

    pontuacao_final = max(0, min(100, int(pontuacao / max(1, len(tabela_clientes)))))
    risco = "LOW_RISK" if pontuacao_final >= 80 else ("MEDIUM_RISK" if pontuacao_final >= 50 else "HIGH_RISK")
    
    return {
        "pontuacao": pontuacao_final,
        "classificacao_risco": risco,
        "justificativa": " | ".join(justificativas)
    }

def handler(event, context):
    try:
        package_id = event.get("package_id")
        user_id = event.get("user_id", "sistema")
        bucket_saida = event.get("bda_output_bucket") or os.environ.get("BUCKET_SAIDA")
        prefix_busca = f"bda-output/{package_id}/"

        logger.info(f"Iniciando processamento isolado por documento para o pacote {package_id}")

        s3_objects = s3_client.list_objects_v2(Bucket=bucket_saida, Prefix=prefix_busca)
        if "Contents" not in s3_objects or len(s3_objects["Contents"]) == 0:
            raise FileNotFoundError(f"Nenhum artefato do BDA localizado no prefixo {prefix_busca}")

        tabela_clientes_final = {}
        confiancas_acumuladas = []
        
        total_input_tokens = 0
        total_output_tokens = 0
        total_custo_usd = 0.0
        idx = 0

        for obj in s3_objects["Contents"]:
            # 🚀 CORREÇÃO CRÍTICA: Pula se NÃO for json ou se FOR o arquivo de manifesto
            if not obj["Key"].endswith(".json") or "manifest" in obj["Key"].lower():
                continue
                
            idx += 1
            nome_arquivo_bda = obj["Key"].split("/")[-1]
            logger.info(f"Processando documento individual [{idx}]: {nome_arquivo_bda}")
            
            s3_response = s3_client.get_object(Bucket=bucket_saida, Key=obj["Key"])
            json_bruto = json.loads(s3_response["Body"].read().decode("utf-8"))
            json_higienizado = limpar_ruido_recursivo(json_bruto)

            tool_config = {
                "tools": [obter_especificacao_ferramenta_loan()],
                "toolChoice": {"tool": {"name": "estruturar_dados_documento_individual"}}
            }
            
            messages = [{
                "role": "user",
                "content": [{"text": f"Extraia os dados deste documento: {json.dumps(json_higienizado)}"}]
            }]

            response = bedrock_runtime.converse(
                modelId="amazon.nova-pro-v1:0",
                messages=messages,
                system=[{"text": PROMPT_SISTEMA}],
                toolConfig=tool_config
            )

            usage = response.get("usage", {})
            in_t = usage.get("inputTokens", 0)
            out_t = usage.get("outputTokens", 0)
            total_input_tokens += in_t
            total_output_tokens += out_t
            total_custo_usd += ((in_t / 1000) * 0.0008) + ((out_t / 1000) * 0.0032)

            content_blocks = response.get("output", {}).get("message", {}).get("content", [])
            tool_use_block = next((b["toolUse"] for b in content_blocks if "toolUse" in b), None)
            
            if not tool_use_block:
                logger.warning(f"O Amazon Nova falhou ao estruturar o arquivo {nome_arquivo_bda}. Ignorando.")
                continue

            achado = tool_use_block.get("input", {})
            if isinstance(achado, str):
                achado = json.loads(achado)

            s3_key_intermediaria = f"results/{package_id}/intermediates/{nome_arquivo_bda}_structured.json"
            s3_client.put_object(
                Bucket=bucket_saida,
                Key=s3_key_intermediaria,
                Body=json.dumps(achado, ensure_ascii=False),
                ContentType="application/json"
            )

            nome = achado.get("nome_titular", "").strip().upper()
            if not nome or "UNKNOWN" in nome or len(nome) < 3:
                continue

            score_doc = float(achado.get("confianca_extracao", 0.95))
            confiancas_acumuladas.append(score_doc)
                
            if nome not in tabela_clientes_final:
                tabela_clientes_final[nome] = {
                    "cadastro": {
                        "nome": nome,
                        "documento_identificacao": achado.get("numero_identificacao") or "Não Localizado",
                        "data_nascimento": achado.get("data_nascimento") if achado.get("data_nascimento") else None
                    },
                    "documentos_vinculados": []
                }
            
            if tabela_clientes_final[nome]["cadastro"]["documento_identificacao"] == "Não Localizado" and achado.get("numero_identificacao"):
                tabela_clientes_final[nome]["cadastro"]["documento_identificacao"] = achado.get("numero_identificacao")

            tabela_clientes_final[nome]["documentos_vinculados"].append({
                "tipo_documento": achado["tipo_documento"],
                "confianca": score_doc,
                "dados_financeiros": {
                    "renda_bruta_informada": float(achado.get("renda_bruta_informada", 0.0) or 0.0),
                    "saldo_bancario_fechamento": float(achado.get("saldo_bancario_fechamento", 0.0) or 0.0)
                }
            })

        if not tabela_clientes_final:
            raise ValueError("Nenhum cliente válido pôde ser extraído de nenhum dos arquivos do lote.")

        confianca_global = sum(confiancas_acumuladas) / max(1, len(confiancas_acumuladas))
        scoring = calcular_matriz_score_mercado(tabela_clientes_final)

        json_estruturado_final = {
            "package_id": package_id,
            "status": "COMPLETED",
            "score_global": scoring,
            "tabela_clientes": tabela_clientes_final
        }

        metricas_auditoria = {
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "custo_estimado_usd": round(total_custo_usd, 6)
        }

        logger.info(f"Fim da esteira. Custos acumulados: ${total_custo_usd:.6f} | Clientes localizados: {list(tabela_clientes_final.keys())}")
        LoanPackageOutput(**json_estruturado_final)

        return {
            "package_id": package_id,
            "user_id": user_id,
            "bda_output_bucket": bucket_saida,
            "confianca_geral": round(confianca_global, 2),
            "revisao_humana": True if scoring["classificacao_risco"] == "MEDIUM_RISK" else False,
            "metricas_consumo": metricas_auditoria,
            "json_estruturado": json_estruturado_final
        }

    except Exception as e:
        logger.error(f"Falha crítica no motor isolado por documento: {str(e)}")
        raise e