"""
shared/classificador.py — Classificação de subtipo documental.

POR QUE ISSO EXISTE:
Antes, a classificação de "que tipo de documento é este arquivo" era feita
de duas formas DIFERENTES em dois lugares:
  - nova_structurer/handler.py: heurística de nome de arquivo, aplicada
    DEPOIS da chamada ao Nova Lite (tarde demais para escolher uma tool
    spec certa por tipo — ver shared/tools.py).
  - confidence_checker/handler.py: a MESMA heurística, copiada e colada,
    sujeita a divergir da primeira com o tempo.

Este módulo centraliza a decisão e adiciona uma fonte de verdade melhor:
o `matched_blueprint` que o próprio Amazon Bedrock Data Automation (BDA)
já devolve no custom_output — o BDA já classificou o documento ao casar
com um dos blueprints customizados (bda_provisioner.py), então usar essa
informação é mais confiável que adivinhar pelo nome do arquivo E não
custa nenhuma chamada extra de LLM.

Ordem de prioridade (da mais para a menos confiável):
  1. matched_blueprint do BDA         → praticamente certo, custo zero
  2. Nome do arquivo (heurística)     → fallback para quando o BDA não
                                         casou com nenhum blueprint
  3. Autoclassificação do Nova Lite   → último recurso (só disponível
                                         DEPOIS da chamada à IA — usado
                                         hoje só como checagem de
                                         divergência/log, não para
                                         escolher a tool spec)
  4. Default: pay_stub                → comportamento histórico do pipeline

Analogia Java: um DocumentClassifier único injetado nos dois Services,
em vez de cada um reimplementar (e divergir) sua própria heurística.
"""

# Nomes dos blueprints são criados como "CrediFacil-{Nome}-Blueprint" pelo
# bda_provisioner.py. Normalizamos (lowercase, sem hífen/underscore) para
# casar com robustez contra pequenas variações de grafia.
_MAPA_BLUEPRINT_PARA_SUBTIPO = {
    "w2taxform": "w2_tax_form",
    "payrollcheck": "payroll_check",
    "driverlicense": "driver_license",
    "accountstatement": "account_statement",
    "homeownersinsurance": "homeowners_insurance_application",
    "paystub": "pay_stub",
}

# subtipo_documento (chave técnica, em inglês) → tipo_documento (rótulo de
# negócio em PT-BR usado no S3 key e no scorecard). Mantém EXATAMENTE os
# mesmos valores que o pipeline já gravava antes desta mudança, para não
# quebrar contratos downstream (customer_consolidator, query_handler etc.)
_MAPA_SUBTIPO_PARA_TIPO_PT = {
    "w2_tax_form": "comprovante_renda",
    "pay_stub": "comprovante_renda",
    "payroll_check": "comprovante_complementar",
    "account_statement": "extrato_bancario",
    "homeowners_insurance_application": "documento_imovel",
    "driver_license": "documento_identificacao",
}

# Enum que a própria tool do Nova Lite usa para tipo_classificado (ver shared/tools.py)
_MAPA_AUTOCLASSIFICACAO_IA = {
    "PAY_STUB": "pay_stub",
    "PAYROLL_CHECK": "payroll_check",
    "DRIVER_LICENSE": "driver_license",
    "W2_TAX_FORM": "w2_tax_form",
    "BANK_STATEMENT": "account_statement",
    "HOMEOWNERS_INSURANCE": "homeowners_insurance_application",
}

SUBTIPO_DEFAULT = "pay_stub"


def _por_matched_blueprint(json_custom_bruto: dict) -> str:
    if not json_custom_bruto:
        return ""
    matched = json_custom_bruto.get("matched_blueprint")
    nome_blueprint = ""
    if isinstance(matched, dict):
        nome_blueprint = str(
            matched.get("name") or matched.get("blueprintName") or matched.get("blueprintArn") or ""
        )
    elif isinstance(matched, str):
        nome_blueprint = matched

    nome_norm = (
        nome_blueprint.lower()
        .replace("credifacil-", "")
        .replace("-blueprint", "")
        .replace("_", "")
        .replace(" ", "")
    )
    for chave, subtipo in _MAPA_BLUEPRINT_PARA_SUBTIPO.items():
        if chave in nome_norm:
            return subtipo
    return ""


def _por_nome_arquivo(nome_pdf_original: str) -> str:
    nome = (nome_pdf_original or "").lower()
    if "w2" in nome:
        return "w2_tax_form"
    if "check" in nome:
        return "payroll_check"
    if "statement" in nome:
        return "account_statement"
    if "insurance" in nome:
        return "homeowners_insurance_application"
    if "license" in nome or "id_card" in nome:
        return "driver_license"
    return ""


def _por_autoclassificacao_ia(tipo_classificado_ia: str) -> str:
    return _MAPA_AUTOCLASSIFICACAO_IA.get((tipo_classificado_ia or "").strip().upper(), "")


def classificar_subtipo_documento(
    nome_pdf_original: str = "",
    json_custom_bruto: dict = None,
    tipo_classificado_ia: str = "",
) -> tuple:
    """
    Retorna (tipo_detectado_pt, subtipo_detectado) para um documento.

    Em nova_structurer/handler.py, chame isso ANTES de acionar o Nova Lite,
    passando nome_pdf_original + json_custom_bruto (tipo_classificado_ia
    ainda não existe nesse ponto — a classificação prévia é o que permite
    escolher a tool spec certa por subtipo, ver shared/tools.py).

    Em confidence_checker/handler.py, também passe json_custom_bruto: essa
    Lambda já carrega o bda_json completo do S3 para checar confidence, então
    o matched_blueprint está disponível ali também — não precisa cair direto
    para a heurística de nome de arquivo.
    """
    subtipo = _por_matched_blueprint(json_custom_bruto)
    if not subtipo:
        subtipo = _por_nome_arquivo(nome_pdf_original)
    if not subtipo:
        subtipo = _por_autoclassificacao_ia(tipo_classificado_ia)
    if not subtipo:
        subtipo = SUBTIPO_DEFAULT

    tipo = _MAPA_SUBTIPO_PARA_TIPO_PT.get(subtipo, "comprovante_renda")
    return tipo, subtipo