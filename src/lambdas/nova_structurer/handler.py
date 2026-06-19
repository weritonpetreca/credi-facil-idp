import json
import os
import boto3
from datetime import datetime
from aws_lambda_powertools import Logger
from src.shared.tools import obter_especificacao_ferramenta_loan

logger = Logger(service="nova-structurer")
s3_client = boto3.client("s3", region_name="us-east-1")
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")

MODEL_ID = "amazon.nova-pro-v1:0"

PROMPT_SISTEMA = (
    "Você é um agente IDP especialista em extração e mapeamento de documentos corporativos.\n"
    "Sua missão é extrair os dados do documento fornecido e estruturá-los rigorosamente de acordo com os schemas oficiais.\n\n"
    "DIRETRIZES CRÍTICAS DE EXTRAÇÃO:\n"
    "1. Classifique o documento em um dos seguintes pares de TIPO e SUBTIPO:\n"
    "   - tipo_documento: 'comprovante_renda', subtipo_documento: 'pay_stub'\n"
    "   - tipo_documento: 'comprovante_renda', subtipo_documento: 'w2_tax_form'\n"
    "   - tipo_documento: 'documento_imovel', subtipo_documento: 'homeowners_insurance_application'\n"
    "   - tipo_documento: 'documento_identificacao', subtipo_documento: 'driver_license'\n"
    "   - tipo_documento: 'extrato_bancario', subtipo_documento: 'account_statement'\n"
    "   - tipo_documento: 'comprovante_complementar', subtipo_documento: 'payroll_check'\n\n"
    "2. Mapeie os dados extraídos fielmente dentro do campo 'campos_extraidos_brutos'.\n"
    "3. Identifique o nome completo do titular principal no campo 'nome_titular' em CAIXA ALTA.\n"
    "4. Defina o 'confianca_extracao' de forma realista entre 0.0 e 1.0 baseando-se na legibilidade do texto."
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

def formatar_conforme_blueprint(tipo: str, subtipo: str, arquivo: str, payload_ia: dict, s3_inputs: dict) -> dict:
    """Monta a estrutura JSON rígida de saída mapeando o padrão solicitado pelo seu grupo."""
    return {
        "tipo_documento": tipo.lower(),
        "subtipo_documento": subtipo.lower(),
        "arquivo_original": arquivo,
        "dados_extraidos_do_documento": payload_ia.get("campos_extraidos_brutos", {}),
        "localizacao_documento_s3": {
            "bucket_origem": s3_inputs["bucket_entrada"],
            "s3_key_origem": s3_inputs["key_entrada"],
            "s3_uri_origem": f"s3://{s3_inputs['bucket_entrada']}/{s3_inputs['key_entrada']}",
            "bucket_resultado_bda": s3_inputs["bucket_saida"],
            "s3_key_resultado_bda": s3_inputs["key_bda"],
            "s3_uri_resultado_bda": f"s3://{s3_inputs['bucket_saida']}/{s3_inputs['key_bda']}"
        },
        "confiabilidade_extracao": {
            "status_extracao": "sucesso" if payload_ia.get("confianca_extracao", 1.0) >= 0.8 else "parcial",
            "confianca_media": str(payload_ia.get("confianca_extracao", 1.0)),
            "fonte_confiabilidade": "matched_blueprint.confidence",
            "observacoes": payload_ia.get("alertas_inconsistencias", [])
        }
    }

def consolidar_dossie_unico_cliente(package_id: str, intermediarios: list, metricas_tokens: dict) -> dict:
    timestamp_atual = datetime.utcnow().isoformat() + "Z"
    nome_final = None
    documentos_identificacao = []
    documentos_analisados = []
    
    presenca = {"identificacao": False, "renda": False, "extrato": False, "imovel": False}
    nomes_coletados = set()
    pendencias = []
    
    renda_acumulada = 0.0
    saldo_acumulado = 0.0
    PLACEHOLDERS = {"N/A", "—", "-", "NONE", "NULL", ""}

    for item in intermediarios:
        bp = item["blueprint"]
        raw_ia = item["raw_ia"]
        
        tipo = bp["tipo_documento"]
        subtipo = bp["subtipo_documento"]
        nome_doc = str(raw_ia.get("nome_titular", "")).strip().upper()
        
        if nome_doc and nome_doc not in PLACEHOLDERS:
            nomes_coletados.add(nome_doc)
            if not nome_final:
                nome_final = nome_doc

        campos = bp["dados_extraidos_do_documento"]
        confianca_num = float(bp["confiabilidade_extracao"]["confianca_media"])

        if tipo == "documento_identificacao":
            presenca["identificacao"] = True
            documentos_identificacao.append({
                "tipo_documento": campos.get("tipo_documento_identificacao") or "Outro",
                "numero_documento": raw_ia.get("numero_documento_identificacao"),
                "orgao_emissor": campos.get("orgao_emissor") or "Não Informado",
                "estado_emissor": campos.get("estado_emissor") or "Não Informado",
                "pais_emissor": campos.get("pais_emissor") or "Não Informado",
                "data_emissao": campos.get("data_emissao"),
                "data_validade": campos.get("data_validade"),
                "arquivo_origem": bp["arquivo_original"]
            })
        elif tipo == "comprovante_renda":
            presenca["renda"] = True
            renda_acumulada += float(raw_ia.get("renda_bruta_informada", 0.0) or 0.0)
        elif tipo == "extrato_bancario":
            presenca["extrato"] = True
            saldo_acumulado += float(raw_ia.get("saldo_bancario_fechamento", 0.0) or 0.0)
        elif tipo == "documento_imovel":
            presenca["imovel"] = True

        documentos_analisados.append({
            "tipo_documento": tipo.upper(),
            "arquivo_original": bp["arquivo_original"],
            "s3_key_origem": bp["localizacao_documento_s3"]["s3_key_origem"],
            "s3_key_resultado_bda": bp["localizacao_documento_s3"]["s3_key_resultado_bda"],
            "status_extracao": bp["confiabilidade_extracao"]["status_extracao"],
            "campos_extraidos": campos,
            "confianca_media": confianca_num,
            "observacoes": bp["confiabilidade_extracao"]["observacoes"]
        })

    nome_consistente = True if len(nomes_coletados) == 1 else (False if len(nomes_coletados) > 1 else None)

    if not presenca["identificacao"]: pendencias.append("Falta Documento de Identificação Oficial (RG/CNH/Passaporte).")
    if not presenca["renda"]: pendencias.append("Falta Comprovante de Renda Válido (Holerite/W-2).")
    if not presenca["extrato"]: pendencias.append("Falta Extrato Bancário para comprovação de liquidez.")

    score_calculado = 0
    if presenca["identificacao"] and nome_consistente: score_calculado += 30
    if renda_acumulada > 0: score_calculado += 40
    if saldo_acumulado > 0: score_calculado += 30

    if score_calculado >= 70 and len(pendencias) == 0:
        decisao, categoria_risco, resumo = "aprovar", "baixo", "Dossiê regularizado. Proponente possui KYC consistente e saúde financeira estável."
    elif score_calculado >= 30 or len(pendencias) > 0:
        decisao, categoria_risco, resumo = "revisar", "medio", f"Crédito em atenção. Foram localizadas {len(pendencias)} pendências documentais na esteira."
    else:
        decisao, categoria_risco, resumo = "recusar", "alto", "Solicitação recusada devido à ausência severa de comprovações de renda ou KYC inválido."

    nome_modelo_final = "Amazon Nova Pro" if "pro" in MODEL_ID.lower() else "Amazon Nova"

    return {
        "cliente": {
            "nome": nome_final or "Não Identificado",
            "data_nascimento": None,
            "score_credito": {"valor": score_calculado, "fonte": "documentos", "observacao": "Score computado via análise sintática e volumetria do dossiê."},
            "classificacao_risco": {"categoria": categoria_risco, "justificativa": resumo},
            "documentos_identificacao": documentos_identificacao
        },
        "sistema": {
            "chave_cliente": f"CLIENT#{nome_final.replace(' ', '_')}" if nome_final else "CLIENT#UNKNOWN",
            "ultimo_package_vinculado": {"package_id": package_id, "client_folder": f"packages/{package_id}/", "data_recebimento": timestamp_atual},
            "processamento": {
                "status": "processado",
                "modelo_utilizado": nome_modelo_final,
                "bda_project_arn": os.environ.get("BDA_PROJECT_ARN"),
                "quantidade_tokens": {"input_tokens": metricas_tokens["input"], "output_tokens": metricas_tokens["output"], "total_tokens": metricas_tokens["input"] + metricas_tokens["output"]},
                "data_processamento": timestamp_atual
            },
            "tipos_documentos_analisados": [k for k, v in presenca.items() if v]
        },
        "documentos_analisados": documentos_analisados,
        "validacao": {
            "nome_consistente_entre_documentos": nome_consistente,
            "data_nascimento_consistente": None,
            "documento_identificacao_presente": presenca["identificacao"],
            "comprovante_renda_presente": presenca["renda"],
            "extrato_bancario_presente": presenca["extrato"],
            "documentacao_imovel_presente": presenca["imovel"],
            "pendencias": pendencias
        },
        "resultado_final": {"decisao_sugerida": decisao, "resumo_analise": resumo, "principais_alertas": []}
    }

def handler(event, context):
    try:
        package_id = event.get("package_id")
        bucket_saida = event.get("bda_output_bucket") or os.environ.get("BUCKET_SAIDA")
        bucket_entrada = f"credifacil-docs-entrada-{os.environ.get('ENV', 'dev')}"
        prefix_busca = f"bda-output/{package_id}/"

        logger.info(f"Iniciando segmentação analítica por categorias para o lote {package_id}")

        s3_objects = s3_client.list_objects_v2(Bucket=bucket_saida, Prefix=prefix_busca)
        if "Contents" not in s3_objects or len(s3_objects["Contents"]) == 0:
            raise FileNotFoundError(f"Nenhum arquivo BDA localizado sob o prefixo {prefix_busca}")

        mapa_documentos = {}
        for obj in s3_objects["Contents"]:
            key = obj["Key"]
            if not key.endswith(".json") or "manifest" in key.lower() or "job_metadata" in key.lower():
                continue
            partes = key.split("/")
            if len(partes) < 3: continue
            nome_pdf_original = partes[2]
            
            if nome_pdf_original not in mapa_documentos:
                mapa_documentos[nome_pdf_original] = []
            mapa_documentos[nome_pdf_original].append(obj)

        intermediarios_coletados = []
        total_input_tokens = 0
        total_output_tokens = 0

        # Processamento atômico e roteamento de arquivos
        for nome_pdf_original, lista_objetos in mapa_documentos.items():
            obj_selecionado = next((o for o in lista_objetos if "custom_output" in o["Key"]), None)
            if not obj_selecionado:
                obj_selecionado = next((o for o in lista_objetos if "standard_output" in o["Key"]), lista_objetos[0])

            logger.info(f"Processando arquivo original: {nome_pdf_original}")
            
            s3_response = s3_client.get_object(Bucket=bucket_saida, Key=obj_selecionado["Key"])
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

            # Execução de inferência com temperatura travada em determinismo máximo (0.0)
            response = bedrock_runtime.converse(
                modelId=MODEL_ID,
                messages=[{"role": "user", "content": [{"text": conteudo_input_hibrido}]}],
                system=[{"text": PROMPT_SISTEMA}],
                toolConfig=tool_config,
                inferenceConfig={"temperature": 0.0, "maxTokens": 3000}
            )

            usage = response.get("usage", {})
            total_input_tokens += usage.get("inputTokens", 0)
            total_output_tokens += usage.get("outputTokens", 0)

            content_blocks = response.get("output", {}).get("message", {}).get("content", [])
            tool_use_block = next((b["toolUse"] for b in content_blocks if "toolUse" in b), None)
            
            if not tool_use_block: continue

            achado = tool_use_block.get("input", {})
            if isinstance(achado, str): achado = json.loads(achado)

            # Extração de metadados dinâmicos para a herança estrutural
            tipo_detectado = str(achado.get("tipo_classificado", "UNKNOWN")).lower()
            
            # Normalização de sub-pastas para casar exatamente com os Blueprints solicitados
            subtipo_detectado = "pay_stub"
            if "w2" in nome_pdf_original.lower() or tipo_detectado == "tax_document":
                tipo_detectado = "comprovante_renda"
                subtipo_detectado = "w2_tax_form"
            elif "check" in nome_pdf_original.lower() or tipo_detectado == "payroll_check":
                tipo_detectado = "comprovante_complementar"
                subtipo_detectado = "payroll_check"
            elif "statement" in nome_pdf_original.lower() or tipo_detectado == "bank_statement":
                tipo_detectado = "extrato_bancario"
                subtipo_detectado = "account_statement"
            elif "insurance" in nome_pdf_original.lower() or tipo_detectado == "property_document":
                tipo_detectado = "documento_imovel"
                subtipo_detectado = "homeowners_insurance_application"
            elif "license" in nome_pdf_original.lower() or tipo_detectado == "identity_document":
                tipo_detectado = "documento_identificacao"
                subtipo_detectado = "driver_license"

            s3_meta_inputs = {
                "bucket_entrada": bucket_entrada,
                "key_entrada": f"packages/{package_id}/{nome_pdf_original}",
                "bucket_saida": bucket_saida,
                "key_bda": obj_selecionado["Key"]
            }

            # 🚀 CONFORMIDADE COM O CASE A: Geração de arquivo rico padronizado pelo Blueprint do grupo
            blueprint_json = formatar_conforme_blueprint(tipo_detectado, subtipo_detectado, nome_pdf_original, achado, s3_meta_inputs)

            # 🚀 DIRETÓRIOS ESPECÍFICOS POR CATEGORIA NO S3: results/{package_id}/{tipo_documento}/{subtipo_documento}/...
            s3_target_key = f"results/{package_id}/{tipo_detectado}/{subtipo_detectado}/{nome_pdf_original.replace('.pdf', '')}_structured.json"
            
            logger.info(f"Salvando JSON estruturado no diretório categórico: {s3_target_key}")
            s3_client.put_object(
                Bucket=bucket_saida,
                Key=s3_target_key,
                Body=json.dumps(blueprint_json, ensure_ascii=False),
                ContentType="application/json"
            )

            intermediarios_coletados.append({"blueprint": blueprint_json, "raw_ia": achado})

        # Geração consolidada do dossiê geral para retrocompatibilidade do front-end
        metricas = {"input": total_input_tokens, "output": total_output_tokens}
        json_final_consolidado = consolidar_dossie_unico_cliente(package_id, intermediarios_coletados, metricas)

        s3_client.put_object(
            Bucket=bucket_saida,
            Key=f"results/{package_id}/output.json",
            Body=json.dumps(json_final_consolidado, ensure_ascii=False),
            ContentType="application/json"
        )

        return {
            "package_id": package_id,
            "user_id": event.get("user_id", "sistema"),
            "bda_output_bucket": bucket_saida,
            "confianca_geral": round(1.0, 2),
            "decisao_sugerida": json_final_consolidado["resultado_final"]["decisao_sugerida"],
            "revisao_humana": json_final_consolidado["cliente"]["classificacao_risco"]["categoria"] == "medio",
            "json_estruturado": json_final_consolidado
        }

    except Exception as e:
        logger.error(f"Falha crítica na segmentação categórica de documentos: {str(e)}")
        raise e