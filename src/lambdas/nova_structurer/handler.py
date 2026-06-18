import json
import os
import boto3
from aws_lambda_powertools import Logger
from src.shared.tools import obter_especificacao_ferramenta_loan
from src.shared.models import LoanPackageOutput

logger = Logger(service="nova-structurer")

s3_client = boto3.client("s3")
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")

# 🚀 PROMPT REFINADO: Regras explícitas para decodificação de Formulários W-2 e Tax Documents
PROMPT_SISTEMA = (
    "Você é um agente analítico de elite especialista em extração de dados financeiros.\n"
    "Sua tarefa é analisar o texto bruto e a estrutura JSON de um único documento para preencher a ferramenta.\n\n"
    "DIRETRIZES DE OURO PARA FORMULÁRIOS W-2 E TAX DOCUMENTS:\n"
    "1. Se o documento contiver 'Form W-2', 'Wage and Tax Statement' ou declarações de imposto, classifique obrigatoriamente como 'TAX_DOCUMENT'.\n"
    "2. IDENTIFICAÇÃO DO TITULAR: Em formulários W-2, o titular ('nome_titular') é SEMPRE o Empregado (Employee), localizado em campos como 'Employee's first name and initial / Last name'. NUNCA use o nome do Empregador (Employer).\n"
    "3. NÚMERO DE IDENTIFICAÇÃO: Capture o 'Employee's social security number' ou 'SSN' e injete inteiramente sem máscaras no campo 'numero_identificacao'.\n"
    "4. DADOS FINANCEIROS: Mapeie o valor de 'Wages, tips, other compensation' (geralmente Box 1) para o campo 'renda_bruta_informada'.\n"
    "Seja extremamente rigoroso e preciso. Não ignore dados explícitos."
)

# 🚀 ENGENHARIA DE DADOS: Extrator recursivo para criar uma linha do tempo de texto plano legível para o LLM
def extrair_texto_linear(dados: any) -> list:
    textos = []
    if isinstance(dados, dict):
        for k, v in dados.items():
            if k in ["text", "textString", "value", "content"] and isinstance(v, str):
                if len(v.strip()) > 0:
                    textos.append(v.strip())
            else:
                textos.extend(extrair_texto_linear(v))
    elif isinstance(dados, list):
        for item in dados:
            textos.extend(extrair_texto_linear(item))
    return textos

def limpar_ruido_recursivo(dados: any) -> any:
    CHAVES_INUTEIS = {"boundingBox", "polygon", "geometry", "coordinates", "location", "pageNumber", "blockId", "relationships", "bounding_box", "spatial_insight", "geometryData", "xy", "box"}
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
        if doc_id and "não localizado" not in doc_id.lower() and "não informado" not in doc_id.lower():
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
        elif 100.0 <= renda_maxima < 4000.0:
            score_individuo += 25
            justificativas_individuo.append(f"Renda ${renda_maxima:.2f} identificada (25/40 pts).")
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

        dados["score_atribuido"] = score_individuo
        dados["justificativa_individual"] = " ".join(justificativas_individuo)
        pontuacao += score_individuo
        justificativas.append(f"[{nome}]: " + " ".join(justificativas_individuo))

    pontuacao_final = max(0, min(100, int(pontuacao / max(1, len(tabela_clientes)))))
    risco = "LOW_RISK" if pontuacao_final >= 80 else ("MEDIUM_RISK" if pontuacao_final >= 50 else "HIGH_RISK")
    return {"pontuacao": pontuacao_final, "classificacao_risco": risco, "justificativa": " | ".join(justificativas)}

def handler(event, context):
    try:
        package_id = event.get("package_id")
        user_id = event.get("user_id", "sistema")
        bucket_saida = event.get("bda_output_bucket") or os.environ.get("BUCKET_SAIDA")
        prefix_busca = f"bda-output/{package_id}/"

        s3_objects = s3_client.list_objects_v2(Bucket=bucket_saida, Prefix=prefix_busca)
        if "Contents" not in s3_objects or len(s3_objects["Contents"]) == 0:
            raise FileNotFoundError(f"Nenhum artefato do BDA localizado no prefixo {prefix_busca}")

        tabela_clientes_final = {}
        confiancas_acumuladas = []
        
        total_input_tokens = 0
        total_output_tokens = 0

        for obj in s3_objects["Contents"]:
            if not obj["Key"].endswith(".json") or "manifest" in obj["Key"].lower():
                continue
                
            partes_caminho = obj["Key"].split("/")
            nome_pdf_original = partes_caminho[2] if len(partes_caminho) > 2 else "desconhecido.pdf"
            nome_arquivo_unico = obj["Key"].replace("bda-output/", "").replace("/", "_")
            
            s3_response = s3_client.get_object(Bucket=bucket_saida, Key=obj["Key"])
            json_bruto = json.loads(s3_response["Body"].read().decode("utf-8"))
            
            # 🚀 FLATTENING CONTEXT: Junta o texto linearizado e o JSON estruturado para dar visão total à IA
            texto_corrido_plano = " ".join(extrair_texto_linear(json_bruto))
            json_higienizado = limpar_ruido_recursivo(json_bruto)

            tool_config = {
                "tools": [obter_especificacao_ferramenta_loan()],
                "toolChoice": {"tool": {"name": "estruturar_dados_documento_individual"}}
            }
            
            # Montagem rica do payload de entrada da IA
            conteudo_input_hibrido = (
                f"--- TRANSCRIÇÃO DE TEXTO LINEAR DO DOCUMENTO ---\n{texto_corrido_plano}\n\n"
                f"--- ESTRUTURA DE METADADOS COMPLETA ---\n{json.dumps(json_higienizado, ensure_ascii=False)}"
            )

            messages = [{
                "role": "user",
                "content": [{"text": conteudo_input_hibrido}]
            }]

            response = bedrock_runtime.converse(
                modelId="amazon.nova-pro-v1:0",
                messages=messages,
                system=[{"text": PROMPT_SISTEMA}],
                toolConfig=tool_config
            )

            usage = response.get("usage", {})
            total_input_tokens += usage.get("inputTokens", 0)
            total_output_tokens += usage.get("outputTokens", 0)

            content_blocks = response.get("output", {}).get("message", {}).get("content", [])
            tool_use_block = next((b["toolUse"] for b in content_blocks if "toolUse" in b), None)
            
            if not tool_use_block:
                continue

            achado = tool_use_block.get("input", {})
            if isinstance(achado, str):
                achado = json.loads(achado)

            s3_client.put_object(
                Bucket=bucket_saida,
                Key=f"results/{package_id}/intermediates/{nome_arquivo_unico}",
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

            uri_s3_entrada = f"s3://credifacil-docs-entrada-{os.environ.get('ENV', 'dev')}/packages/{package_id}/{nome_pdf_original}"

            tabela_clientes_final[nome]["documentos_vinculados"].append({
                "tipo_documento": achado["tipo_documento"],
                "confianca": score_doc,
                "arquivo_origem_s3": uri_s3_entrada,
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

        return {
            "package_id": package_id,
            "user_id": user_id,
            "bda_output_bucket": bucket_saida,
            "confianca_geral": round(confianca_global, 2),
            "revisao_humana": True if scoring["classificacao_risco"] == "MEDIUM_RISK" else False,
            "metricas_consumo": {"input_tokens": total_input_tokens, "output_tokens": total_output_tokens, "custo_estimado_usd": round((total_input_tokens*0.0008/1000)+(total_output_tokens*0.0032/1000), 6)},
            "json_estruturado": json_estruturado_final
        }

    except Exception as e:
        logger.error(f"Falha crítica no motor isolado por documento: {str(e)}")
        raise e