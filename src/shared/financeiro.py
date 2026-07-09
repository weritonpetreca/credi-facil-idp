"""
shared/financeiro.py — Extração determinística de renda e saldo bancário.

CONTEXTO DO BUG QUE ESTE ARQUIVO CORRIGE:
Antes desta mudança, existiam DUAS implementações independentes da "mesma"
lógica de extração financeira:
  - customer_consolidator/handler.py: extrair_renda_do_documento() / extrair_saldo_do_documento()
  - result_writer/handler.py:         extrair_renda_segura()       / extrair_saldo_seguro()

Elas divergiam nos aliases de campo aceitos (ex: só result_writer reconhecia
a chave solta "Gross Pay"), e uma delas dependia de subtipo_documento sem
fallback para tipo_documento. Resultado: o MESMO documento podia ter renda
detectada corretamente no Excel/JSON individual e aparecer como $0.00 no
CRM (DynamoDB) ou no dossiê consolidado, dependendo de qual Lambda tocava
o dado por último.

Este módulo é a ÚNICA fonte de verdade agora. As duas Lambdas importam daqui.

Analogia Java: é a diferença entre ter a mesma regra de negócio duplicada
(e divergente) em dois Services, versus extrair um único FinancialExtractor
e injetá-lo nos dois. Uma mudança de regra passa a acontecer em um lugar só.
"""


def safe_float(val) -> float:
    """
    Converte qualquer valor em float de forma segura.
    Trata vírgula como separador de milhar (EUA) ou decimal (BR):
      "16,640.00" → 16640.0   |   "R$ 1.234,56" → 1234.56
    """
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    try:
        limpo = "".join(c for c in str(val) if c.isdigit() or c in [".", ","])
        if "," in limpo and "." in limpo:
            if limpo.rfind(",") > limpo.rfind("."):
                limpo = limpo.replace(".", "").replace(",", ".")
            else:
                limpo = limpo.replace(",", "")
        elif "," in limpo:
            limpo = limpo.replace(",", ".")
        return float(limpo) if limpo else 0.0
    except (ValueError, TypeError):
        return 0.0


# Mapa de fallback: quando subtipo_documento vem vazio (pacote legado, dado de
# teste manual, documento não reclassificado), usamos tipo_documento — mais
# genérico, mas quase sempre presente porque é setado cedo no pipeline.
_MAPA_TIPO_PARA_SUBTIPO = {
    "PAY_STUB": "pay_stub",
    "COMPROVANTE_RENDA": "pay_stub",
    "PAYROLL_CHECK": "payroll_check",
    "COMPROVANTE_COMPLEMENTAR": "payroll_check",
    "W2_TAX_FORM": "w2_tax_form",
    "TAX_DOCUMENT": "w2_tax_form",
}


def resolver_subtipo_efetivo(tipo: str = "", subtipo: str = "") -> str:
    """
    Strategy resolver com fallback: subtipo_documento manda; se vazio, deriva
    de tipo_documento. Analogia Java: Optional<Strategy>.orElseGet(...).
    """
    s = (subtipo or "").lower().strip()
    if s:
        return s
    return _MAPA_TIPO_PARA_SUBTIPO.get((tipo or "").upper().strip(), "")


# Chaves "de atalho" — cobrem casos em que o valor já foi pré-calculado e
# colocado na raiz de `campos` por alguma etapa anterior do pipeline, ou em
# que o BDA/Nova Lite devolveu um nome de campo fora do padrão dos templates.
_ALIASES_RENDA_RAIZ = [
    "amount_numeric", "Gross Pay", "wages_tips_other_compensation",
    "gross_pay_year_to_date", "gross_pay_this_period", "net_pay_this_period",
    "renda_bruta_informada",
]

_ALIASES_SALDO_RAIZ = [
    "closing_balance", "closing_account_balance", "saldo_bancario_fechamento", "balance", "amount",
]


def extrair_renda_do_documento(campos: dict, tipo: str = "", subtipo: str = "") -> float:
    """
    Extrai a renda de um documento, tentando (1) atalhos de campo já
    conhecidos e (2) a estrutura real de cada template por subtipo:

    - pay_stub:      net_pay.this_period (dict aninhado) ou earnings[].gross_pay
    - payroll_check: amount_numeric (campo raiz)
    - w2_tax_form:   wages_tips_other_compensation (campo raiz)

    Analogia Java: Strategy Pattern — cada subtipo tem sua própria forma de
    navegar a árvore de dados, mas todas passam primeiro por um scan raso
    de aliases comuns antes de mergulhar na estrutura aninhada.
    """
    if not isinstance(campos, dict):
        return 0.0

    for chave in _ALIASES_RENDA_RAIZ:
        v = campos.get(chave)
        if v is not None and safe_float(v) > 0:
            return safe_float(v)

    subtipo_efetivo = resolver_subtipo_efetivo(tipo, subtipo)

    if subtipo_efetivo in ("pay_stub", "comprovante_renda"):
        net_pay = campos.get("net_pay")
        if isinstance(net_pay, dict):
            v = net_pay.get("this_period") or net_pay.get("year_to_date")
            if v:
                return safe_float(v)

        for item in campos.get("earnings", []) or []:
            if not isinstance(item, dict):
                continue
            gp = item.get("gross_pay")
            if isinstance(gp, dict):
                v = gp.get("this_period")
                if v:
                    return safe_float(v)
            v = item.get("this_period")
            if v and str(item.get("description", "")).lower() == "gross pay":
                return safe_float(v)

    elif subtipo_efetivo in ("payroll_check", "comprovante_complementar"):
        v = campos.get("amount_numeric") or campos.get("amount_words")
        if v:
            return safe_float(v)

    elif subtipo_efetivo == "w2_tax_form":
        v = campos.get("wages_tips_other_compensation")
        if v:
            return safe_float(v)

    return 0.0


def extrair_saldo_do_documento(campos: dict) -> float:
    """
    Extrai o saldo de fechamento de um extrato bancário (account_statement).
    Não depende de subtipo — a estrutura de saldo só existe nesse tipo de
    documento, então tentamos todos os aliases conhecidos direto.
    """
    if not isinstance(campos, dict):
        return 0.0

    for chave in _ALIASES_SALDO_RAIZ:
        v = campos.get(chave)
        if v is not None and safe_float(v) > 0:
            return safe_float(v)

    saldo_aninhado = campos.get("your_account_balance")
    if isinstance(saldo_aninhado, dict):
        v = saldo_aninhado.get("closing_balance") or saldo_aninhado.get("value")
        if v:
            return safe_float(v)

    return 0.0