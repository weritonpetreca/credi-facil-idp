import json
import os
import boto3
from datetime import datetime
from aws_lambda_powertools import Logger
from src.shared.tools import obter_especificacao_ferramenta_loan

logger = Logger(service="nova-structurer")
s3_client = boto3.client("s3")
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")

PROMPT_SISTEMA = (
    "Você é um agente analítico especialista em análise de crédito imobiliário e KYC.\n"
    "Sua tarefa é extrair os dados de um único documento focado estritamente no cliente solicitante.\n\n"
    "DIRETRIZES CRÍTICAS:\n"
    "1. Identifique quem é a pessoa principal do documento (o dono da conta, o empregado do holerite, o beneficiário do cheque).\n"
    "2. Mapeie os dados na ferramenta fornecida. No campo 'campos_extraidos_brutos', monte um dicionário limpo contendo chaves e valores cruciais localizados no texto.\n"
    "3. Se você detectar que o documento pertence inteiramente a outra pessoa que não seja o solicitante mestre (ex: um formulário W-2 onde o Employee é um terceiro), preencha o tipo_classificado correspondente, mas adicione um alerta explícito no campo 'alertas_inconsistencias'."
)

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

def consolidar_dossie_unico_cliente(package_id: str, intermediarios: list, metricas_tokens: dict) -> dict:
    timestamp_atual = datetime.utcnow().isoformat() + "Z"
    
    nome_final = None
    data_nascimento_final = None
    documentos_identificacao = []
    documentos_analisados = []
    
    presenca = {
        "identificacao": False,
        "renda": False,
        "extrato": False,
        "imovel": False
    }
    
    nomes_coletados = set()
    datas_nascimento_coletadas = set()
    pendencias = []
    principais_alertas = []
    
    renda_acumulada = 0.0
    saldo_acumulado = 0.0

    for doc in intermediarios:
        tipo = doc.get("tipo_classificado", "UNKNOWN")
        nome_doc = doc.get("nome_titular", "").strip().upper()
        
        if nome_doc and "UNKNOWN" not in nome_doc:
            nomes_coletados.add(nome_doc)
            if not nome_final:
                nome_final = nome_doc
                
        if doc.get("data_nascimento"):
            datas_nascimento_coletadas.add(doc.get("data_nascimento"))
            if not data_nascimento_final:
                data_nascimento_final = doc.get("data_nascimento")

        if doc.get("alertas_inconsistencias"):
            principais_alertas.extend(doc["alertas_inconsistencias"])

        if tipo == "IDENTITY_DOCUMENT":
            presenca["identificacao"] = True
            detalhes = doc.get("detalhes_cadastrais", {})
            documentos_identificacao.append({
                "tipo_documento": detalhes.get("tipo_especifico_id") or "Outro",
                "numero_documento": doc.get("numero_documento_identificacao"),
                "orgao_emissor": detalhes.get("orgao_emissor") or "Não Informado",
                "estado_emissor": detalhes.get("estado_emissor") or "Não Informado",
                "pais_emissor": detalhes.get("pais_emissor") or "Não Informado",
                "data_emissao": detalhes.get("data_emissao"),
                "data_validade": detalhes.get("data_validade"),
                "arquivo_origem": doc.get("arquivo_original", "documento.pdf")
            })
        elif tipo in ["PAY_STUB", "PAYROLL_CHECK", "TAX_DOCUMENT"]:
            presenca["renda"] = True
            renda_acumulada += float(doc.get("renda_bruta_informada", 0.0) or 0.0)
        elif tipo == "BANK_STATEMENT":
            presenca["extrato"] = True
            saldo_acumulado += float(doc.get("saldo_bancario_fechamento", 0.0) or 0.0)
        elif tipo == "PROPERTY_DOCUMENT":
            presenca["imovel"] = True

        documentos_analisados.append({
            "tipo_documento": tipo,
            "arquivo_original": doc.get("arquivo_original", "desconhecido.pdf"),
            "s3_key_origem": doc.get("s3_key_origem", ""),
            "s3_key_resultado_bda": doc.get("s3_key_resultado_bda", ""),
            "status_extracao": "sucesso" if doc.get("confianca_extracao", 0.0) > 0.7 else "parcial",
            "campos_extraidos": doc.get("campos_extraidos_brutos", {}),
            "confianca_media": doc.get("confianca_extracao", 1.0),
            "observacoes": doc.get("alertas_inconsistencias", [])
        })

    nome_consistente = True if len(nomes_coletados) <= 1 else False
    dt_nascimento_consistente = True if len(datas_nascimento_coletadas) <= 1 else False

    if not presenca["identificacao"]:
        pendencias.append("Falta Documento de Identificação Oficial (RG/CNH/Passaporte).")
    if not presenca["renda"]:
        pendencias.append("Falta Comprovante de Renda Válido (Holerite/W-2).")
    if not presenca["extrato"]:
        pendencias.append("Falta Extrato Bancário para comprovação de liquidez.")
        
    if not nome_consistente:
        principais_alertas.append(f"Divergência nominal detectada entre os arquivos: {list(nomes_coletados)}")

    score_calculado = 0
    if presenca["identificacao"] and nome_consistente: score_calculado += 30
    if renda_acumulada > 0: score_calculado += 40
    if saldo_acumulado > 0: score_calculado += 30

    if score_calculado >= 70 and len(pendencias) == 0:
        decisao = "aprovar"
        categoria_risco = "baixo"
        resumo = "Dossiê regularizado. Proponente possui KYC consistente e saúde financeira estável."
    elif score_calculado >= 30 or len(pendencias) > 0:
        decisao = "revisar"
        categoria_risco = "medio"
        resumo = f"Crédito em atenção. Foram localizadas {len(pendencias)} pendências documentais na esteira."
    else:
        decisao = "recusar"
        categoria_risco = "alto"
        resumo = "Solicitação recusada devido à ausência severa de comprovações de renda ou KYC inválido."

    return {
        "cliente": {
            "nome": nome_final or "Não Identificado",
            "data_nascimento": data_nascimento_final,
            "score_credito": {
                "valor": score_calculado,
                "fonte": "documentos",
                "observacao": "Score computado via análise sintática e volumetria do dossiê."
            },
            "classificacao_risco": {
                "categoria": categoria_risco,
                "justificativa": resumo
            },
            "documentos_identificacao": documentos_identificacao
        },
        "sistema": {
            "chave_cliente": f"CLIENT#{nome_final.replace(' ', '_')}" if nome_final else "CLIENT#UNKNOWN",
            "ultimo_package_vinculado": {
                "package_id": package_id,
                "client_folder": f"packages/{package_id}/",
                "data_recebimento": timestamp_atual
            },
            "processamento": {
                "status": "processado_com_alertas" if len(principais_alertas) > 0 else "processado",
                "modelo_utilizado": "Amazon Nova",
                "bda_project_arn": os.environ.get("BDA_PROJECT_ARN"),
                "quantidade_tokens": {
                    "input_tokens": metricas_tokens["input"],
                    "output_tokens": metricas_tokens["output"],
                    "total_tokens": metricas_tokens["input"] + metricas_tokens["output"]
                },
                "data_processamento": timestamp_atual
            },
            "tipos_documentos_analisados": [k for k, v in presenca.items() if v]
        },
        "documentos_analisados": documentos_analisados,
        "validacao": {
            "nome_consistente_entre_documentos": nome_consistente,
            "data_nascimento_consistente": dt_nascimento_consistente,
            "documento_identificacao_presente": presenca["identificacao"],
            "comprovante_renda_presente": presenca["renda"],
            "extrato_bancario_presente": presenca["extrato"],
            "documentacao_imovel_presente": presenca["imovel"],
            "pendencias": pendencias
        },
        "resultado_final": {
            "decisao_sugerida": decisao,
            "resumo_analise": resumo,
            "principais_alertas": list(set(principais_alertas))
        }
    }

def handler(event, context):
    try:
        package_id = event.get("package_id")
        bucket_saida = event.get("bda_output_bucket") or os.environ.get("BUCKET_SAIDA")
        prefix_busca = f"bda-output/{package_id}/"

        s3_objects = s3_client.list_objects_v2(Bucket=bucket_saida, Prefix=prefix_busca)
        if "Contents" not in s3_objects or len(s3_objects["Contents"]) == 0:
            raise FileNotFoundError(f"Nenhum arquivo BDA localizado sob o prefixo {prefix_busca}")

        intermediarios_coletados = []
        confiancas_físicas = []
        total_input_tokens = 0
        total_output_tokens = 0

        for obj in s3_objects["Contents"]:
            if not obj["Key"].endswith(".json") or "manifest" in obj["Key"].lower():
                continue
                
            partes = obj["Key"].split("/")
            nome_pdf_original = partes[2] if len(partes) > 2 else "documento.pdf"
            nome_arquivo_unico = obj["Key"].replace("bda-output/", "").replace("/", "_")
            
            s3_response = s3_client.get_object(Bucket=bucket_saida, Key=obj["Key"])
            json_bruto = json.loads(s3_response["Body"].read().decode("utf-8"))
            
            texto_corrido_plano = " ".join(extrair_texto_linear(json_bruto))
            json_higienizado = limpar_ruido_recursivo(json_bruto)

            tool_config = {
                "tools": [obter_especificacao_ferramenta_loan()],
                "toolChoice": {"tool": {"name": "estruturar_dados_documento_cliente_unico"}}
            }
            
            conteudo_input_hibrido = (
                f"--- TRANSCRIÇÃO DE TEXTO LINEAR DO DOCUMENTO ---\n{texto_corrido_plano}\n\n"
                f"--- ESTRUTURA DE METADADOS COMPLETA ---\n{json.dumps(json_higienizado, ensure_ascii=False)}"
            )

            response = bedrock_runtime.converse(
                modelId="amazon.nova-pro-v1:0",
                messages=[{"role": "user", "content": [{"text": conteudo_input_hibrido}]}],
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

            achado["arquivo_original"] = nome_pdf_original
            achado["s3_key_origem"] = f"packages/{package_id}/{nome_pdf_original}"
            achado["s3_key_resultado_bda"] = obj["Key"]
            
            confiancas_físicas.append(float(achado.get("confianca_extracao", 1.0)))

            s3_client.put_object(
                Bucket=bucket_saida,
                Key=f"results/{package_id}/intermediates/{nome_arquivo_unico}_structured.json",
                Body=json.dumps(achado, ensure_ascii=False),
                ContentType="application/json"
            )

            intermediarios_coletados.append(achado)

        metricas = {"input": total_input_tokens, "output": total_output_tokens}
        json_final_consolidado = consolidar_dossie_unico_cliente(package_id, intermediarios_coletados, metricas)

        s3_client.put_object(
            Bucket=bucket_saida,
            Key=f"results/{package_id}/output.json",
            Body=json.dumps(json_final_consolidado, ensure_ascii=False),
            ContentType="application/json"
        )

        confianca_global_media = sum(confiancas_físicas) / max(1, len(confiancas_físicas))

        return {
            "package_id": package_id,
            "user_id": event.get("user_id", "sistema"),
            "bda_output_bucket": bucket_saida,
            "confianca_geral": round(confianca_global_media, 2), # 🚀 CORRIGIDO: Agora sempre retorna um número (Ex: 0.95)
            "decisao_sugerida": json_final_consolidado["resultado_final"]["decisao_sugerida"], # Novo campo limpo de texto
            "revisao_humana": True if json_final_consolidado["cliente"]["classificacao_risco"]["categoria"] == "medio" else False,
            "json_estruturado": json_final_consolidado
        }

    except Exception as e:
        logger.error(f"Falha crítica no estruturador de cliente único: {str(e)}")
        raise e