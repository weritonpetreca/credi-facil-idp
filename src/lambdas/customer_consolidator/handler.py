"""
customer_consolidator/handler.py

Responsabilidade: analisar o pacote completo de documentos e produzir dois artefatos:

ARTEFATO 1 — CRM JSON (customer_consolidated.json):
  Compacto, sem redundâncias, focado na decisão de crédito.
  Vai para o S3 em results/clientes/{package_id}/customer_consolidated.json

ARTEFATO 2 — Pacote completo (output.json):
  Todos os dados extraídos de todos os documentos + metadados do sistema.
  Vai para o S3 em results/packages/{package_id}/output.json

Analogia Java:
  Este handler é como um serviço de Report que recebe um List<DocumentoDTO>
  e produz dois relatórios: um ExecutiveSummaryReport e um FullAuditReport.
  O executivo tem só o que o gerente precisa para decidir.
  O audit tem tudo para o departamento de compliance.
"""
import json
import os
import datetime
import boto3
from aws_lambda_powertools import Logger

logger = Logger(service="customer-consolidator")
s3_client = boto3.client("s3")
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")

# Nova Lite é suficiente para validação cruzada de campos simples.
# Nova Pro foi removido desta Lambda (RF-18 do SRS).
MODEL_ID = "amazon.nova-lite-v1:0"

# Preços Amazon Bedrock us-east-1 (confirmar em aws.amazon.com/bedrock/pricing)
PRECO_NOVA_LITE_INPUT_PER_1K = 0.00006    # USD por 1.000 tokens de input
PRECO_NOVA_LITE_OUTPUT_PER_1K = 0.00024   # USD por 1.000 tokens de output
PRECO_BDA_POR_PAGINA = 0.040              # USD por página (blueprint com ≤30 campos)


# ─────────────────────────────────────────────────────────────────────────────
# UTILITÁRIOS
# ─────────────────────────────────────────────────────────────────────────────

def safe_float(val) -> float:
    """
    Converte qualquer valor em float de forma segura.
    Trata vírgula como separador de milhar (ex: "16,640.00" → 16640.0).
    """
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    try:
        limpo = "".join(c for c in str(val) if c.isdigit() or c in [".", ","])
        if "," in limpo and "." in limpo:
            # Detecta se a vírgula é decimal (BR) ou separador de milhar (EUA)
            if limpo.rfind(",") > limpo.rfind("."):
                limpo = limpo.replace(".", "").replace(",", ".")
            else:
                limpo = limpo.replace(",", "")
        elif "," in limpo:
            limpo = limpo.replace(",", ".")
        return float(limpo) if limpo else 0.0
    except (ValueError, TypeError):
        return 0.0


def extrair_renda_do_documento(campos: dict, subtipo: str) -> float:
    """
    Extrai a renda do documento respeitando a estrutura real de cada template.

    Cada tipo de documento tem uma estrutura diferente para a renda:
    - pay_stub:      net_pay.this_period  (dict aninhado)
    - payroll_check: amount_numeric       (string na raiz)
    - w2_tax_form:   wages_tips_other_compensation (string na raiz)

    Analogia Java: é um Strategy Pattern — cada subtipo tem sua própria
    estratégia de extração de renda.
    """
    subtipo_lower = (subtipo or "").lower()

    if subtipo_lower in ("pay_stub", "comprovante_renda"):
        # net_pay é um dict: {"this_period": "$291.90", ...}
        net_pay = campos.get("net_pay")
        if isinstance(net_pay, dict):
            v = net_pay.get("this_period") or net_pay.get("year_to_date")
            if v:
                return safe_float(v)

        # Fallback: percorre a lista de earnings buscando o gross_pay
        for item in campos.get("earnings", []):
            if not isinstance(item, dict):
                continue
            gp = item.get("gross_pay", {})
            if isinstance(gp, dict):
                v = gp.get("this_period")
                if v:
                    return safe_float(v)

        # Último fallback: campo plano net_pay_this_period (novos templates)
        v = campos.get("net_pay_this_period") or campos.get("gross_pay_this_period")
        if v:
            return safe_float(v)

    elif subtipo_lower in ("payroll_check", "comprovante_complementar"):
        v = campos.get("amount_numeric") or campos.get("amount_words")
        if v:
            return safe_float(v)

    elif subtipo_lower == "w2_tax_form":
        v = campos.get("wages_tips_other_compensation")
        if v:
            return safe_float(v)

    return 0.0


def extrair_saldo_do_documento(campos: dict) -> float:
    """
    Extrai o saldo de fechamento de um extrato bancário.
    Tenta várias chaves que podem estar no template de account_statement.
    """
    candidatos = [
        campos.get("closing_balance"),
        (campos.get("your_account_balance") or {}).get("closing_balance"),
        campos.get("closing_account_balance"),
        campos.get("saldo_bancario_fechamento"),
        campos.get("balance"),
    ]
    for c in candidatos:
        if c is not None:
            return safe_float(c)
    return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# SCORECARD DE CRÉDITO (critérios orientados ao mercado imobiliário)
# ─────────────────────────────────────────────────────────────────────────────

def calcular_scorecard_financeiro(validacao: dict, docs_analisados: list) -> dict:
    """
    Calcula o score de crédito (300–1000) com critérios do mercado imobiliário.

    Modelo de pontuação:
    - Capacidade de amortização (renda × 30% = parcela máxima recomendada pelo BACEN)
    - Reserva de liquidez (quantos meses de parcela o saldo cobre)
    - Consistência documental (KYC)

    Analogia Java: é como um método calcularScore() num serviço de Domain Layer
    que recebe um DTO com dados financeiros e retorna um ScoreResult imutável.
    O score é 100% determinístico (sem IA) — o mesmo input sempre gera o mesmo output.
    Isso é obrigatório para conformidade com o Marco Legal da IA (explicabilidade).
    """
    score = 300
    motivos_positivos = []
    motivos_negativos = []
    alertas_compliance = []

    # ── Extração de renda e saldo dos documentos ──────────────────────────────
    renda_maxima = 0.0
    saldo_maximo = 0.0

    for doc in docs_analisados:
        tipo = str(doc.get("tipo_documento", "UNKNOWN")).upper()
        subtipo = str(doc.get("subtipo_documento", "")).lower()
        campos = (
            doc.get("dados_extraidos_do_documento")
            or doc.get("campos_extraidos")
            or {}
        )

        if tipo in ("COMPROVANTE_RENDA", "COMPROVANTE_COMPLEMENTAR",
                    "PAY_STUB", "PAYROLL_CHECK", "W2_TAX_FORM"):
            renda = extrair_renda_do_documento(campos, subtipo)
            renda_maxima = max(renda_maxima, renda)

        elif tipo in ("EXTRATO_BANCARIO", "BANK_STATEMENT", "ACCOUNT_STATEMENT"):
            saldo = extrair_saldo_do_documento(campos)
            saldo_maximo = max(saldo_maximo, saldo)

    # ── FATOR 1: Capacidade de amortização ────────────────────────────────────
    # Regra BACEN: comprometimento máximo de 30% da renda líquida.
    # Uma parcela de 30% da renda = parcela que o BACEN considera sustentável.
    parcela_max = round(renda_maxima * 0.30, 2)

    if parcela_max >= 3000:
        score += 300
        motivos_positivos.append(
            f"+300: Capacidade de amortização elevada — parcela máx. estimada USD {parcela_max:.2f}/mês."
        )
    elif parcela_max >= 1500:
        score += 200
        motivos_positivos.append(
            f"+200: Capacidade de amortização média — parcela máx. estimada USD {parcela_max:.2f}/mês."
        )
    elif parcela_max >= 500:
        score += 100
        motivos_positivos.append(
            f"+100: Capacidade de amortização mínima — parcela máx. estimada USD {parcela_max:.2f}/mês."
        )
    elif parcela_max > 0:
        score += 30
        motivos_negativos.append(
            f"+30: Renda presente, mas parcela máx. (USD {parcela_max:.2f}) abaixo do mínimo habitacional."
        )
    else:
        motivos_negativos.append("+0: Nenhuma renda líquida comprovada nos documentos.")
        alertas_compliance.append(
            "ALERTA: Renda não identificada. Análise de crédito severamente prejudicada."
        )

    # ── FATOR 2: Reserva de liquidez ─────────────────────────────────────────
    # Quantos meses de parcela o saldo bancário cobre.
    # Ex: saldo 874 / parcela 87 = 10 meses de reserva → excelente.
    if saldo_maximo > 0 and parcela_max > 0:
        meses_reserva = saldo_maximo / parcela_max
        if meses_reserva >= 6:
            score += 200
            motivos_positivos.append(
                f"+200: Liquidez elevada — {meses_reserva:.1f} meses de parcela em reserva."
            )
        elif meses_reserva >= 3:
            score += 100
            motivos_positivos.append(
                f"+100: Liquidez adequada — {meses_reserva:.1f} meses de parcela em reserva."
            )
        elif meses_reserva >= 1:
            score += 50
            motivos_positivos.append(
                f"+50: Liquidez mínima — {meses_reserva:.1f} meses de parcela em reserva."
            )
        else:
            motivos_negativos.append(
                f"+0: Saldo insuficiente para reserva de emergência (< 1 mês de parcela)."
            )
    elif saldo_maximo == 0:
        motivos_negativos.append("+0: Extrato bancário ausente ou saldo de fechamento não identificado.")

    # ── FATOR 3: Consistência documental (KYC) ────────────────────────────────
    if validacao.get("nome_consistente_entre_documentos"):
        score += 100
        motivos_positivos.append(
            "+100: Identidade validada — nome consistente em todos os documentos."
        )
    else:
        motivos_negativos.append("+0: Nome inconsistente entre documentos.")
        alertas_compliance.append(
            "ALERTA: Inconsistência de nome detectada — verificação manual obrigatória antes de aprovação."
        )

    if validacao.get("documento_identificacao_presente"):
        score += 50
        motivos_positivos.append("+50: Documento de identificação oficial presente e verificado.")
    else:
        alertas_compliance.append("ALERTA: Nenhum documento de identificação no pacote.")

    if validacao.get("comprovante_renda_presente"):
        score += 30
        motivos_positivos.append("+30: Comprovante de renda formal incluído no pacote.")

    if validacao.get("extrato_bancario_presente"):
        score += 20
        motivos_positivos.append("+20: Extrato bancário presente — análise de liquidez realizada.")
    else:
        motivos_negativos.append("+0: Extrato bancário ausente — liquidez não verificada.")

    score_final = min(1000, max(300, score))
    faixa = "baixo_risco" if score_final >= 700 else "risco_medio" if score_final >= 500 else "alto_risco"

    return {
        "score_calculado": score_final,
        "faixa": faixa,
        "renda_maxima": renda_maxima,
        "saldo_maximo": saldo_maximo,
        "parcela_maxima_estimada": parcela_max,
        "motivos_positivos": motivos_positivos,
        "motivos_negativos": motivos_negativos,
        "alertas_compliance": alertas_compliance,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MONTAGEM DOS DOIS ARTEFATOS DE SAÍDA
# ─────────────────────────────────────────────────────────────────────────────

def montar_crm_json(
    package_id: str,
    consolidado_ia: dict,
    score: dict,
    docs_analisados: list,
    tokens_total: dict,
    timestamp_inicio: str,
) -> dict:
    """
    ARTEFATO 1: JSON compacto para o CRM.

    Princípio: um analista de crédito precisa de ~15 campos para decidir.
    Esse JSON não deve ter campos duplicados nem dados brutos dos documentos.
    Os dados brutos ficam no output.json (artefato 2).

    Analogia Java: é como um ExecutiveSummaryDTO — só o que importa para a decisão.
    """
    timestamp_agora = datetime.datetime.utcnow().isoformat() + "Z"
    pontuacao = score["score_calculado"]

    # Campos corrigidos pelo humano (para auditoria do Marco Legal da IA)
    campos_revisados = []
    revisao_realizada = False
    for doc in docs_analisados:
        obs = doc.get("confiabilidade_extracao", {}).get("observacoes", [])
        for o in obs:
            if "retificados manualmente" in str(o).lower():
                revisao_realizada = True
                partes = str(o).replace("Campos retificados manualmente: ", "").split(", ")
                campos_revisados.extend(partes)

    return {
        "package_id": package_id,
        "versao_algoritmo": "1.0.0",

        # Quem é o requerente
        "requerente": {
            "nome": consolidado_ia.get("cliente", {}).get("nome") or "NAO INFORMADO",
            "documento_identificacao": consolidado_ia.get("cliente", {}).get("documento_identificacao") or "NAO INFORMADO",
        },

        # Números para a decisão financeira
        "sumario_financeiro": {
            "renda_liquida_mensal_usd": score["renda_maxima"],
            "saldo_bancario_fechamento_usd": score["saldo_maximo"],
            "parcela_maxima_recomendada_usd": score["parcela_maxima_estimada"],
            "comprometimento_renda_perc": round(
                (score["parcela_maxima_estimada"] / score["renda_maxima"] * 100), 1
            ) if score["renda_maxima"] > 0 else 0.0,
        },

        # Score e justificativas separadas em positivas e negativas
        "score_credito": {
            "pontuacao": pontuacao,
            "faixa": score["faixa"],
            "motivos_positivos": score["motivos_positivos"],
            "motivos_negativos": score["motivos_negativos"],
            "alertas_compliance": score["alertas_compliance"],
        },

        # Checklist do KYC (apenas booleanos)
        "validacao_kyc": {
            "nome_consistente": consolidado_ia.get("validacao", {}).get("nome_consistente_entre_documentos", False),
            "data_nascimento_consistente": consolidado_ia.get("validacao", {}).get("data_nascimento_consistente", False),
            "documento_identidade_presente": consolidado_ia.get("validacao", {}).get("documento_identificacao_presente", False),
            "comprovante_renda_presente": consolidado_ia.get("validacao", {}).get("comprovante_renda_presente", False),
            "extrato_bancario_presente": consolidado_ia.get("validacao", {}).get("extrato_bancario_presente", False),
        },

        # Parecer narrativo da IA (só o texto — sem os dados brutos)
        "parecer_analise": (
            consolidado_ia.get("cliente", {})
                          .get("classificacao_risco", {})
                          .get("justificativa", "")
        ),

        # Referências para os JSONs detalhados (não replica o conteúdo)
        "documentos_do_pacote": [
            {
                "arquivo": doc.get("arquivo_original", ""),
                "tipo": doc.get("subtipo_documento") or doc.get("tipo_documento", ""),
                "status": (doc.get("confiabilidade_extracao") or {}).get("status_extracao", "desconhecido"),
                "confianca_bda": (doc.get("confiabilidade_extracao") or {}).get("confianca_media", "0.0"),
                "s3_json_detalhado": (doc.get("localizacao_documento_s3") or {}).get("s3_key_resultado", ""),
            }
            for doc in docs_analisados
        ],

        # Trilha de auditoria (para o Marco Legal da IA)
        "auditoria": {
            "timestamp_conclusao_utc": timestamp_agora,
            "timestamp_inicio_processamento_utc": timestamp_inicio,
            "versao_pipeline": "1.2.0",
            "modelo_extracao": "amazon.bedrock.data-automation",
            "modelo_estruturacao": "amazon.nova-lite-v1:0",
            "modelo_consolidacao": MODEL_ID,
            "revisao_humana_realizada": revisao_realizada,
            "campos_revisados_manualmente": campos_revisados,
            "tokens_total_consumidos": tokens_total.get("total", 0),
        },
    }


def montar_pacote_completo_json(
    package_id: str,
    status: str,
    execute_score: bool,
    score: dict,
    consolidado_ia: dict,
    docs_analisados: list,
    sistema_base: dict,
    tokens_total: dict,
    timestamp_inicio: str,
) -> dict:
    """
    ARTEFATO 2: JSON completo do pacote para auditoria e frontend.

    Contém:
    - Todos os dados extraídos de todos os documentos
    - Metadados do sistema (versão, timestamp, tokens, custo estimado)
    - Score completo (se solicitado)

    Analogia Java: é como um FullAuditReport que vai para o arquivo morto —
    tem tudo, mas não é o que o gerente lê todo dia.
    """
    timestamp_agora = datetime.datetime.utcnow().isoformat() + "Z"

    # Custo estimado em USD
    custo_nova_lite = (
        (tokens_total.get("input_nova_lite", 0) * PRECO_NOVA_LITE_INPUT_PER_1K / 1000)
        + (tokens_total.get("output_nova_lite", 0) * PRECO_NOVA_LITE_OUTPUT_PER_1K / 1000)
    )
    custo_bda = len(docs_analisados) * PRECO_BDA_POR_PAGINA  # 1 doc ≈ 1 página

    return {
        "package_id": package_id,
        "status": status,
        "execute_score": execute_score,

        # Score (preenchido só se execute_score=True)
        "renda_bruta_estimada": score["renda_maxima"],
        "saldo_bancario_fechamento": score["saldo_maximo"],

        # Validação KYC
        "validacao": consolidado_ia.get("validacao", {}),

        # Dados do cliente consolidados pela IA
        "cliente": {
            "nome": consolidado_ia.get("cliente", {}).get("nome", "NAO REQUISITADO"),
            "documento_identificacao": consolidado_ia.get("cliente", {}).get("documento_identificacao", "NAO REQUISITADO"),
            "score_credito": {
                "pontuacao": score["score_calculado"],
                "faixa": score["faixa"],
                "motivos_positivos": score["motivos_positivos"],
                "motivos_negativos": score["motivos_negativos"],
                "alertas_compliance": score["alertas_compliance"],
            } if execute_score else {"pontuacao": 0, "motivos_positivos": [], "motivos_negativos": [], "alertas_compliance": []},
            "classificacao_risco": consolidado_ia.get("cliente", {}).get("classificacao_risco", {}),
        },

        # Todos os documentos com dados completos extraídos
        "documentos_analisados": [
            {
                "arquivo_original": doc.get("arquivo_original", ""),
                "tipo_documento": doc.get("tipo_documento", ""),
                "subtipo_documento": doc.get("subtipo_documento", ""),
                "status_extracao": (doc.get("confiabilidade_extracao") or {}).get("status_extracao", ""),
                "confianca_media": float((doc.get("confiabilidade_extracao") or {}).get("confianca_media", 0.0)),
                "confiancas_por_campo_bda": (doc.get("confiabilidade_extracao") or {}).get("confiancas_por_campo_bda", {}),
                "s3_key_origem": (doc.get("localizacao_documento_s3") or {}).get("s3_key_origem", ""),
                "s3_key_resultado": (doc.get("localizacao_documento_s3") or {}).get("s3_key_resultado", ""),
                "observacoes": (doc.get("confiabilidade_extracao") or {}).get("observacoes", []),
                "dados_extraidos_do_documento": (
                    doc.get("dados_extraidos_do_documento")
                    or doc.get("campos_extraidos")
                    or {}
                ),
            }
            for doc in docs_analisados
        ],

        # Metadados do sistema — rastreabilidade completa
        "sistema": {
            "versao_pipeline": "1.2.0",
            "package_id": package_id,
            "timestamp_inicio_utc": timestamp_inicio,
            "timestamp_conclusao_utc": timestamp_agora,
            "bda_project_arn": sistema_base.get("processamento", {}).get("bda_project_arn"),
            "processamento": {
                "status": "processado",
                "documentos_processados": len(docs_analisados),
                "tipos_documentos": sistema_base.get("tipos_documentos_analisados", []),
                "quantidade_tokens": {
                    "input_tokens_nova_lite": tokens_total.get("input_nova_lite", 0),
                    "output_tokens_nova_lite": tokens_total.get("output_nova_lite", 0),
                    "input_tokens_consolidacao": tokens_total.get("input_consolidacao", 0),
                    "output_tokens_consolidacao": tokens_total.get("output_consolidacao", 0),
                    "total_input": tokens_total.get("total_input", 0),
                    "total_output": tokens_total.get("total_output", 0),
                    "total_tokens": tokens_total.get("total", 0),
                },
                "custo_estimado_usd": {
                    "bda_extracao": round(custo_bda, 5),
                    "nova_lite_estruturacao": round(custo_nova_lite, 5),
                    "nova_lite_consolidacao": round(
                        (tokens_total.get("input_consolidacao", 0) * PRECO_NOVA_LITE_INPUT_PER_1K / 1000)
                        + (tokens_total.get("output_consolidacao", 0) * PRECO_NOVA_LITE_OUTPUT_PER_1K / 1000),
                        5
                    ),
                    "total": round(
                        custo_bda + custo_nova_lite
                        + (tokens_total.get("input_consolidacao", 0) * PRECO_NOVA_LITE_INPUT_PER_1K / 1000)
                        + (tokens_total.get("output_consolidacao", 0) * PRECO_NOVA_LITE_OUTPUT_PER_1K / 1000),
                        5
                    ),
                },
            },
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL SPEC DO CONSOLIDADOR (validação cruzada de KYC)
# ─────────────────────────────────────────────────────────────────────────────

def obter_especificacao_ferramenta_consolidacao() -> dict:
    return {
        "toolSpec": {
            "name": "consolidar_e_validar_dados_esteira",
            "description": (
                "Consolida a validação cadastral cruzada do proponente. "
                "Analise os documentos do dossiê e preencha os campos de validação. "
                "Regra estrita: 'data_nascimento_consistente' só é true se a data "
                "aparecer explicitamente em ao menos um documento de identificação."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "cliente": {
                            "type": "object",
                            "properties": {
                                "nome": {"type": "string", "description": "Nome completo em CAIXA ALTA."},
                                "documento_identificacao": {"type": "string"},
                                "classificacao_risco": {
                                    "type": "object",
                                    "properties": {
                                        "categoria": {"type": "string", "enum": ["baixo", "medio", "alto"]},
                                        "justificativa": {"type": "string"}
                                    },
                                    "required": ["categoria", "justificativa"]
                                }
                            },
                            "required": ["nome", "documento_identificacao", "classificacao_risco"]
                        },
                        "validacao": {
                            "type": "object",
                            "properties": {
                                "nome_consistente_entre_documentos": {"type": "boolean"},
                                "data_nascimento_consistente": {"type": "boolean"},
                                "documento_identificacao_presente": {"type": "boolean"},
                                "comprovante_renda_presente": {"type": "boolean"},
                                "extrato_bancario_presente": {"type": "boolean"}
                            },
                            "required": [
                                "nome_consistente_entre_documentos",
                                "data_nascimento_consistente",
                                "documento_identificacao_presente",
                                "comprovante_renda_presente",
                                "extrato_bancario_presente"
                            ]
                        }
                    },
                    "required": ["cliente", "validacao"]
                }
            }
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# HANDLER PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def handler(event, context):
    """
    Ponto de entrada da Lambda.

    Recebe o json_estruturado do aggregator via event e:
    1. Executa a validação cruzada de KYC via Nova Lite (se execute_score=True)
    2. Calcula o scorecard determinístico (sempre)
    3. Grava os dois artefatos no S3 e retorna o pacote completo
    """
    try:
        package_id = event.get("package_id")
        bucket = event.get("bda_output_bucket") or os.environ.get("BUCKET_SAIDA")
        execute_score = event.get("execute_score", False)
        user_id = event.get("user_id", "sistema")

        logger.info(f"Iniciando consolidação para o pacote {package_id}. Score: {execute_score}")

        # ── Carrega o json base do aggregator ─────────────────────────────────
        json_base_lote = event.get("json_estruturado") or {}
        if not json_base_lote or "documentos_analisados" not in json_base_lote:
            key_base = f"results/packages/{package_id}/output.json"
            s3_resp = s3_client.get_object(Bucket=bucket, Key=key_base)
            json_base_lote = json.loads(s3_resp["Body"].read().decode("utf-8"))

        # ── Normaliza a lista de documentos ───────────────────────────────────
        raw_docs = json_base_lote.get("documentos_analisados", [])
        docs_analisados = []
        for d in raw_docs:
            doc_obj = d.get("blueprint", d) if isinstance(d, dict) and "blueprint" in d else d
            if isinstance(doc_obj, dict) and doc_obj.get("arquivo_original"):
                docs_analisados.append(doc_obj)

        # ── Recupera tokens acumulados pelo aggregator ─────────────────────────
        tokens_base = (
            json_base_lote.get("sistema", {})
                          .get("processamento", {})
                          .get("quantidade_tokens", {})
        )
        input_lite_acum = int(tokens_base.get("input_tokens", 0))
        output_lite_acum = int(tokens_base.get("output_tokens", 0))
        timestamp_inicio = (
            json_base_lote.get("sistema", {})
                          .get("ultimo_package_vinculado", {})
                          .get("data_recebimento", datetime.datetime.utcnow().isoformat() + "Z")
        )

        # ── Executa tool calling de KYC (se solicitado) ───────────────────────
        consolidado_ia = {}
        input_consolidacao = 0
        output_consolidacao = 0

        scorecard_vazio = {
            "score_calculado": 300,
            "faixa": "alto_risco",
            "renda_maxima": 0.0,
            "saldo_maximo": 0.0,
            "parcela_maxima_estimada": 0.0,
            "motivos_positivos": [],
            "motivos_negativos": ["Scorecard não executado — gate de score inativo."],
            "alertas_compliance": [],
        }

        if execute_score and docs_analisados:
            # Monta o dossiê textual: apenas os campos estruturados, sem coordenadas
            # ou metadados internos que aumentam tokens desnecessariamente
            dossie_resumido = []
            for doc in docs_analisados:
                campos = doc.get("dados_extraidos_do_documento") or doc.get("campos_extraidos") or {}
                dossie_resumido.append({
                    "tipo": doc.get("subtipo_documento", ""),
                    "arquivo": doc.get("arquivo_original", ""),
                    "campos": campos,
                })
            dossie_textual = json.dumps(dossie_resumido, ensure_ascii=False)

            response = bedrock_runtime.converse(
                modelId=MODEL_ID,
                messages=[{
                    "role": "user",
                    "content": [{"text": f"Dossiê para validação cruzada:\n{dossie_textual}"}]
                }],
                system=[{
                    "text": (
                        "Você é um analista sênior de risco de crédito. "
                        "Analise o dossiê e realize a validação cadastral cruzada. "
                        "Use a ferramenta obrigatoriamente."
                    )
                }],
                toolConfig={
                    "tools": [obter_especificacao_ferramenta_consolidacao()],
                    "toolChoice": {"tool": {"name": "consolidar_e_validar_dados_esteira"}}
                },
                inferenceConfig={"temperature": 0.0, "maxTokens": 1000}
            )

            usage = response.get("usage", {})
            input_consolidacao = usage.get("inputTokens", 0)
            output_consolidacao = usage.get("outputTokens", 0)

            content = response.get("output", {}).get("message", {}).get("content", [])
            tool_block = next((b["toolUse"] for b in content if "toolUse" in b), None)

            if tool_block:
                raw = tool_block.get("input", {})
                consolidado_ia = json.loads(raw) if isinstance(raw, str) else raw
            else:
                logger.warning("Nova Lite não acionou a tool de consolidação. Usando defaults.")

            validacao_data = consolidado_ia.get("validacao", {})
            scorecard_completo = calcular_scorecard_financeiro(validacao_data, docs_analisados)
        else:
            scorecard_completo = scorecard_vazio

        # ── Consolida os totais de tokens ─────────────────────────────────────
        total_input = input_lite_acum + input_consolidacao
        total_output = output_lite_acum + output_consolidacao
        tokens_total = {
            "input_nova_lite": input_lite_acum,
            "output_nova_lite": output_lite_acum,
            "input_consolidacao": input_consolidacao,
            "output_consolidacao": output_consolidacao,
            "total_input": total_input,
            "total_output": total_output,
            "total": total_input + total_output,
        }

        # ── Monta e grava os dois artefatos ───────────────────────────────────
        sistema_base = json_base_lote.get("sistema", {})

        if execute_score:
            crm_json = montar_crm_json(
                package_id, consolidado_ia, scorecard_completo,
                docs_analisados, tokens_total, timestamp_inicio
            )
            s3_client.put_object(
                Bucket=bucket,
                Key=f"results/clientes/{package_id}/customer_consolidated.json",
                Body=json.dumps(crm_json, ensure_ascii=False, default=str),
                ContentType="application/json"
            )
            logger.info(f"CRM JSON gravado. Score: {scorecard_completo['score_calculado']}")

        pacote_completo = montar_pacote_completo_json(
            package_id, "COMPLETED", execute_score, scorecard_completo,
            consolidado_ia, docs_analisados, sistema_base,
            tokens_total, timestamp_inicio
        )
        s3_client.put_object(
            Bucket=bucket,
            Key=f"results/packages/{package_id}/output.json",
            Body=json.dumps(pacote_completo, ensure_ascii=False, default=str),
            ContentType="application/json"
        )
        logger.info(f"Pacote completo gravado. Tokens totais: {tokens_total['total']}")

        return {
            "package_id": package_id,
            "user_id": user_id,
            "execute_score": execute_score,
            "bda_output_bucket": bucket,
            "confianca_general": 1,
            "json_estruturado": pacote_completo,
        }

    except Exception as e:
        logger.error(f"Falha crítica na consolidação do pacote {event.get('package_id')}: {str(e)}")
        raise e