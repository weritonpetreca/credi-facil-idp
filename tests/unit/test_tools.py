"""
Testes do shared/tools.py — a fábrica polimórfica de tool specs.

O teste mais importante deste arquivo é test_nenhuma_tool_spec_tem_caractere_
arriscado_em_nome_de_propriedade: regressão direta do bug real encontrado em
produção em 13/07/2026, onde account_statement era o ÚNICO subtipo (de 6) a
falhar consistentemente com "ModelErrorException: Model produced invalid
sequence as part of ToolUse" — e o único com nomes de propriedade como
'unit_price_$' (cifrão dentro da chave JSON). Renomeado para 'unit_price_usd'.
Este teste varre TODAS as tool specs recursivamente para garantir que essa
classe de bug não volte a aparecer em nenhum subtipo, presente ou futuro.
"""
import re
import pytest

from src.shared.tools import obter_especificacao_ferramenta


SUBTIPOS = [
    "pay_stub",
    "payroll_check",
    "driver_license",
    "w2_tax_form",
    "account_statement",
    "homeowners_insurance_application",
]

# Identificador seguro: letras, números, underscore — o que qualquer gerador
# de JSON estruturado (Nova Lite via Bedrock Converse tool-use) deveria lidar
# sem ambiguidade. Nada de $, espaço, acento, ou outro símbolo.
PADRAO_NOME_SEGURO = re.compile(r"^[a-zA-Z0-9_]+$")


def _coletar_nomes_de_propriedade(schema: dict) -> list:
    """Percorre um JSON Schema recursivamente (properties, items, objetos
    aninhados) e devolve todo nome de propriedade encontrado em qualquer
    profundidade."""
    nomes = []
    props = schema.get("properties", {})
    for nome, sub_schema in props.items():
        nomes.append(nome)
        if isinstance(sub_schema, dict):
            if sub_schema.get("type") == "object":
                nomes.extend(_coletar_nomes_de_propriedade(sub_schema))
            elif sub_schema.get("type") == "array" and isinstance(sub_schema.get("items"), dict):
                nomes.extend(_coletar_nomes_de_propriedade(sub_schema["items"]))
    return nomes


@pytest.mark.parametrize("subtipo", SUBTIPOS)
def test_dispatcher_resolve_todos_os_6_subtipos_sem_erro(subtipo):
    """obter_especificacao_ferramenta(subtipo) tem que resolver pra uma tool
    spec válida (com toolSpec.name e inputSchema) pra cada um dos 6 subtipos
    — nenhum deve cair no default silencioso por erro de digitação na chave."""
    spec = obter_especificacao_ferramenta(subtipo)
    assert "toolSpec" in spec
    assert spec["toolSpec"]["name"]
    assert "inputSchema" in spec["toolSpec"]


@pytest.mark.parametrize("subtipo", SUBTIPOS)
def test_nenhuma_tool_spec_tem_caractere_arriscado_em_nome_de_propriedade(subtipo):
    """
    Regressão do bug real de produção: nenhum nome de propriedade, em
    nenhuma profundidade de nenhuma tool spec, pode ter caracteres fora de
    [a-zA-Z0-9_]. account_statement já teve 4 campos assim (unit_price_$,
    value_$, insurance_cover_amount_$, benefit_amount_$) e era o único
    subtipo que falhava a geração estruturada da Nova Lite em produção.
    """
    spec = obter_especificacao_ferramenta(subtipo)
    schema = spec["toolSpec"]["inputSchema"]["json"]
    nomes = _coletar_nomes_de_propriedade(schema)

    assert nomes, f"Nenhuma propriedade encontrada em {subtipo} — schema pode estar malformado"

    nomes_arriscados = [n for n in nomes if not PADRAO_NOME_SEGURO.match(n)]
    assert not nomes_arriscados, (
        f"Subtipo '{subtipo}' tem nome(s) de propriedade com caractere arriscado: "
        f"{nomes_arriscados} — isso é exatamente o padrão que causou ModelErrorException "
        f"em produção para account_statement (unit_price_$, value_$...)."
    )


def test_account_statement_especificamente_usa_sufixo_usd_nao_cifrao():
    """Trava o fix específico: os 4 campos que tinham cifrão agora usam
    sufixo _usd, e o cifrão não aparece em lugar nenhum do schema."""
    spec = obter_especificacao_ferramenta("account_statement")
    schema = spec["toolSpec"]["inputSchema"]["json"]
    nomes = _coletar_nomes_de_propriedade(schema)

    assert "unit_price_usd" in nomes
    assert "value_usd" in nomes
    assert "insurance_cover_amount_usd" in nomes
    assert "benefit_amount_usd" in nomes
    assert not any("$" in n for n in nomes)
