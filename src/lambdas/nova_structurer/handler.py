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
    "Você é um motor analítico avançado de submissão de crédito imobiliário e hipotecário. "
    "A entrada contém um array com dados limpos de MÚLTIPLOS documentos extraídos do pacote de empréstimo. "
    "Sua obrigação absoluta é iterar por CADA objeto do array de entrada, extrair TODAS as pessoas e "
    "documentos localizados e mapear na ferramenta estruturada. "
    "Atenção: Você encontrará documentos de pessoas distintas (ex: MARÍA GARCÍA e JOHN STILES). "
    "Você NÃO PODE omitir nenhum indivíduo. Popule o array 'achados_documentais' com todos os achados."
)

def limpar_ruido_recursivo(dados: any) -> any:
    """
    Filtro Recursivo Profundo: Varre toda a árvore do JSON eliminando dados geométricos pesados,
    reduzindo o tamanho do payload e preservando chaves úteis de formulários e identidades do BDA.
    """
    CHAVES_INUTEIS = {
        "boundingBox", "polygon", "geometry", "coordinates", "location", 
        "pageNumber", "blockId", "relationships", "bounding_box", "spatial_insight",
        "geometryData", "xy", "box"
    }
    
    if isinstance(dados, dict):
        return {
            k: limpar_ruido_recursivo(v) 
            for k, v in dados.items() 
            if k not in CHAVES_INUTEIS
        }
    elif isinstance(dados, list):
        return [limpar_ruido_recursivo(item) for item in dados]
        
    return dados

def calcular_matriz_score_mercado(tabela_clientes: dict) -> dict:
    """
    Motor de Scoring Bancário Realista (Modelo FICO / DTI Framework):
    Distribui 100 pontos objetivos entre Rigor Cadastral, Renda e Reserva Líquida.
    """
    pontuacao = 0
    justificativas = []
    
    if len(tabela_clientes) > 1:
        justificativas.append("Análise consolidada para múltiplos proponentes identificados no dossiê.")

    for nome, dados in tabela_clientes.items():
        score_individuo = 0
        justificativas_individuo = []
        docs_detectados = [d["tipo_documento"] for d in dados["documentos_vinculados"]]
        
        # 🛡️ PILAR 1: Rigor Cadastral & KYC (Max: 30 pontos)
        doc_id = dados["cadastro"].get("documento_identificacao", "")
        if doc_id and "não localizado" not in doc_id.lower():
            score_individuo += 30
            justificativas_individuo.append("Homologação cadastral e KYC validados (30/30 pts).")
        else:
            justificativas_individuo.append("Inconsistência cadastral severa. Documento oficial ausente (0/30 pts).")

        # 💼 PILAR 2: Renda e Estabilidade Financeira (Max: 40 pontos)
        renda_maxima = 0.0
        for doc in dados["documentos_vinculados"]:
            if doc["tipo_documento"] in ["PAY_STUB", "TAX_DOCUMENT"]:
                renda_doc = float(doc["dados_financeiros"].get("renda_bruta_informada", 0.0))
                if renda_doc > renda_maxima:
                    renda_maxima = renda_doc
                    
        if renda_maxima >= 4000.0:
            score_individuo += 40
            justificativas_individuo.append(f"Renda comprovada de ${renda_maxima:.2f} em range excelente (40/40 pts).")
        elif 2000.0 <= renda_maxima < 4000.0:
            score_individuo += 25
            justificativas_individuo.append(f"Renda comprovada de ${renda_maxima:.2f} em range moderado (25/40 pts).")
        else:
            justificativas_individuo.append("Renda ausente ou abaixo do range mínimo de segurança de crédito (0/40 pts).")

        # 🏦 PILAR 3: Liquidez e Reserva de Amortização (Max: 30 pontos)
        saldo_maximo = 0.0
        for doc in dados["documentos_vinculados"]:
            if doc["tipo_documento"] == "BANK_STATEMENT":
                saldo_doc = float(doc["dados_financeiros"].get("saldo_bancario_fechamento", 0.0))
                if saldo_doc > saldo_maximo:
                    saldo_maximo = saldo_doc
                    
        if saldo_maximo >= 10000.0:
            score_individuo += 30
            justificativas_individuo.append(f"Reserva de liquidez de ${saldo_maximo:.2f} robusta (30/30 pts).")
        elif 1500.0 <= saldo_maximo < 10000.0:
            score_individuo += 15
            justificativas_individuo.append(f"Reserva de liquidez de ${saldo_maximo:.2f} em range de atenção (15/30 pts).")
        else:
            justificativas_individuo.append("Ausência de colchão financeiro ou extrato com saldo zerado (0/30 pts).")

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

        logger.info(f"Iniciando consolidação com deep sifting para o pacote {package_id}")

        s3_objects = s3_client.list_objects_v2(Bucket=bucket_saida, Prefix=prefix_busca)
        if "Contents" not in s3_objects or len(s3_objects["Contents"]) == 0:
            raise FileNotFoundError(f"Nenhum artefato do BDA localizado no prefixo {prefix_busca}")

        conteudos_brutos = []
        for obj in s3_objects["Contents"]:
            if obj["Key"].endswith(".json") and "manifest" not in obj["Key"].lower():
                s3_response = s3_client.get_object(Bucket=bucket_saida, Key=obj["Key"])
                json_bruto = json.loads(s3_response["Body"].read().decode("utf-8"))
                
                # 🚀 DEEP SIFTING: Varre recursivamente limpando apenas o lixo geométrico
                json_higienizado = limpar_ruido_recursivo(json_bruto)
                conteudos_brutos.append(json_higienizado)

        tool_config = {
            "tools": [obter_especificacao_ferramenta_loan()],
            "toolChoice": {"tool": {"name": "estruturar_dados_solicitacao_credito"}}
        }
        
        messages = [{
            "role": "user",
            "content": [{"text": f"Processe a seguinte lista de payloads extraídos do BDA: {json.dumps(conteudos_brutos)}"}]
        }]

        logger.info("Invocando o Amazon Nova Pro via API Converse...")
        response = bedrock_runtime.converse(
            modelId="amazon.nova-pro-v1:0",
            messages=messages,
            system=[{"text": PROMPT_SISTEMA}],
            toolConfig=tool_config
        )

        usage = response.get("usage", {})
        input_tokens = usage.get("inputTokens", 0)
        output_tokens = usage.get("outputTokens", 0)
        custo_calculado_usd = ((input_tokens / 1000) * 0.0008) + ((output_tokens / 1000) * 0.0032)
        
        logger.info(f"Consumo de Tokens - Input: {input_tokens} | Output: {output_tokens} | Custo USD: ${custo_calculado_usd:.6f}")

        content_blocks = response.get("output", {}).get("message", {}).get("content", [])
        tool_use_block = next((b["toolUse"] for b in content_blocks if "toolUse" in b), None)
        
        if not tool_use_block:
            raise ValueError("O Amazon Nova falhou ao popular o esquema estruturado de ferramentas.")

        dados_ia = tool_use_block.get("input", {})
        if isinstance(dados_ia, str):
            dados_ia = json.loads(dados_ia)
        
        tabela_clientes_final = {}
        confiancas_acumuladas = []

        for achado in dados_ia.get("achados_documentais", []):
            nome = achado["nome_titular"].strip().upper()
            if not nome:
                continue

            score_doc = float(achado.get("confianca_extracao", 0.95))
            confiancas_acumuladas.append(score_doc)
                
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
                "confianca": score_doc,
                "dados_financeiros": {
                    "renda_bruta_informada": float(achado.get("renda_bruta_informada", 0.0) or 0.0),
                    "saldo_bancario_fechamento": float(achado.get("saldo_bancario_fechamento", 0.0) or 0.0)
                }
            })

        confianca_global = sum(confiancas_acumuladas) / max(1, len(confiancas_acumuladas))
        scoring = calcular_matriz_score_mercado(tabela_clientes_final)

        json_estruturado_final = {
            "package_id": package_id,
            "status": "COMPLETED",
            "score_global": scoring,
            "tabela_clientes": tabela_clientes_final
        }

        metricas_auditoria = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "custo_estimado_usd": round(custo_calculado_usd, 6)
        }

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
        logger.error(f"Falha crítica no motor estruturador Nova: {str(e)}")
        raise e