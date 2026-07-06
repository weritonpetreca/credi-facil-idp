"""
shared/tools.py — Especificação das ferramentas (tools) para o Amazon Bedrock Nova Lite.

Por que a tool spec importa:
Quando o Nova Lite usa tool calling, ele preenche campos conforme o schema definido aqui.
Se o schema for genérico (apenas "type": "object" sem propriedades definidas), o modelo
decide sozinho quais campos retornar — e frequentemente deixa as tabelas como null.

Com schemas explícitos, o modelo sabe exatamente o que preencher:
- earnings_rows com as colunas rate, hours, this_period, year_to_date
- statutory_deductions com this_period e year_to_date
- etc.

Analogia Java: é como a diferença entre Map<String, Object> (genérico)
e um DTO com todos os campos declarados. Com o DTO, o compilador sabe
o que esperar; com o Map, o desenvolvedor adivinha.
"""


def obter_especificacao_ferramenta_loan() -> dict:
    """
    Tool spec da Lambda nova_structurer para extração de campos secundários.

    Esta ferramenta recebe o markdown completo do documento (incluindo tabelas)
    e deve preencher apenas os campos que o blueprint BDA NÃO cobre:
    - Linhas das tabelas (earnings, deductions, benefits)
    - Endereços
    - Notas

    Os campos críticos (employee_name, pay_date, net_pay_this_period, etc.)
    já foram extraídos diretamente do inference_result do BDA com alta confiança
    e não precisam ser re-extraídos pelo Nova Lite.
    """
    return {
        "toolSpec": {
            "name": "estruturar_dados_documento_cliente_unico",
            "description": (
                "Extrai campos SECUNDÁRIOS de um documento financeiro a partir do markdown estruturado. "
                "Os campos principais (nomes, datas, valores de renda, SSN) já foram extraídos pelo BDA "
                "e serão informados no prompt como 'CAMPOS JÁ EXTRAÍDOS'. "
                "Sua tarefa é preencher as tabelas detalhadas e campos complementares. "
                "Para holerites (pay_stub): preencher obrigatoriamente earnings_rows, "
                "statutory_deductions, other_deductions, other_benefits e important_notes. "
                "Cada item de lista deve ter ao menos um campo não-nulo para ser incluído."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {

                        # ── METADADOS DE CLASSIFICAÇÃO ────────────────────────────
                        "tipo_classificado": {
                            "type": "string",
                            "enum": [
                                "PAY_STUB", "PAYROLL_CHECK", "DRIVER_LICENSE",
                                "W2_TAX_FORM", "BANK_STATEMENT",
                                "HOMEOWNERS_INSURANCE", "UNKNOWN"
                            ],
                            "description": "Tipo do documento identificado no markdown."
                        },
                        "nome_titular": {
                            "type": "string",
                            "description": "Nome completo do titular em CAIXA ALTA. Ex: 'JOHN STILES'."
                        },

                        # ── CAMPOS PLANOS COMPLEMENTARES ──────────────────────────
                        "employer_address": {
                            "type": "string",
                            "description": (
                                "Endereço completo do empregador (rua, número, cidade, estado, CEP). "
                                "Ex: '475 ANY AVENUE ANYTOWN, USA 10101'."
                            )
                        },
                        "employee_address": {
                            "type": "string",
                            "description": (
                                "Endereço completo do empregado. "
                                "Ex: '101 MAIN STREET ANYTOWN, USA 12345'."
                            )
                        },
                        "document_title": {
                            "type": "string",
                            "description": "Título do documento. Ex: 'Earnings Statement', 'Payroll Check'."
                        },
                        "federal_taxable_wages_this_period": {
                            "type": "string",
                            "description": (
                                "Valor dos salários tributáveis federais neste período. "
                                "Geralmente indicado como 'Your federal wages this period are $X'. "
                                "Ex: '386.15'."
                            )
                        },
                        "exemptions_federal": {
                            "type": "string",
                            "description": "Número de isenções federais declaradas. Ex: '3'."
                        },
                        "exemptions_state": {
                            "type": "string",
                            "description": "Número de isenções estaduais declaradas. Ex: '2'."
                        },
                        "exemptions_local": {
                            "type": "string",
                            "description": "Número de isenções locais declaradas. Ex: '2'."
                        },
                        "additional_federal_tax": {
                            "type": "string",
                            "description": "Imposto federal adicional declarado. Ex: '$25'."
                        },

                        # ── TABELA DE EARNINGS ────────────────────────────────────
                        # Cada linha da tabela "Earnings" do holerite deve virar um item.
                        # Exemplo da tabela no markdown:
                        #   | Earnings | rate  | hours | this period | year to date |
                        #   | Regular  | 10.00 | 32.00 | 320.00      | 16,640.00    |
                        #   | Overtime | 15.00 |  1.00 |  15.00      |    780.00    |
                        #   | Gross Pay|       |       | 452.43      | 23,526.80    |
                        "earnings_rows": {
                            "type": "array",
                            "description": (
                                "OBRIGATÓRIO para pay_stub: cada linha da tabela Earnings. "
                                "Inclui Regular, Overtime, Holiday, Tuition, e Gross Pay. "
                                "Preencher SOMENTE linhas que aparecem no documento. "
                                "NÃO inventar linhas. NÃO colocar o nome da linha como valor numérico."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "description": {
                                        "type": "string",
                                        "description": (
                                            "Nome da linha exatamente como aparece no documento: "
                                            "'regular', 'overtime', 'holiday', 'tuition', 'gross pay'."
                                        )
                                    },
                                    "rate": {
                                        "type": "string",
                                        "description": (
                                            "Valor da coluna 'rate' para esta linha. "
                                            "Para Regular: '10.00'. Para Gross Pay: deixar null."
                                        )
                                    },
                                    "hours": {
                                        "type": "string",
                                        "description": (
                                            "Valor da coluna 'hours' para esta linha. "
                                            "Para Regular: '32.00'. Para Tuition e Gross Pay: deixar null."
                                        )
                                    },
                                    "this_period": {
                                        "type": "string",
                                        "description": (
                                            "Valor da coluna 'this period' para esta linha. "
                                            "Para Regular: '320.00'. Para Gross Pay: '452.43'."
                                        )
                                    },
                                    "year_to_date": {
                                        "type": "string",
                                        "description": (
                                            "Valor da coluna 'year to date' para esta linha. "
                                            "Para Regular: '16,640.00'."
                                        )
                                    }
                                },
                                "required": ["description"]
                            }
                        },

                        # ── DEDUÇÕES STATUTÁRIAS ──────────────────────────────────
                        # Grupo "Statutory" da tabela Deductions (impostos obrigatórios).
                        # Exemplo:
                        #   | Federal Income Tax  | 40.60  | 2,111.20 |
                        #   | Social Security Tax | -28.05 | 1,458.60 |
                        "statutory_deductions": {
                            "type": "array",
                            "description": (
                                "OBRIGATÓRIO para pay_stub: linhas do grupo 'Statutory' da tabela Deductions. "
                                "Inclui: Federal Income Tax, Social Security Tax, Medicare Tax, "
                                "NY State Income Tax, NYC Income Tax, NY SUI/SDI Tax (ou equivalentes). "
                                "Preencher SOMENTE o que aparecer no documento."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "description": {
                                        "type": "string",
                                        "description": "Nome do imposto como aparece no documento."
                                    },
                                    "this_period": {
                                        "type": "string",
                                        "description": (
                                            "Valor descontado neste período. "
                                            "Ignorar o sinal negativo se houver. "
                                            "Para Federal Income Tax: '40.60'."
                                        )
                                    },
                                    "year_to_date": {
                                        "type": "string",
                                        "description": "Total acumulado no ano. Para Federal Income Tax: '2,111.20'."
                                    }
                                },
                                "required": ["description"]
                            }
                        },

                        # ── OUTRAS DEDUÇÕES ───────────────────────────────────────
                        # Grupo "Other" da tabela Deductions (benefícios, empréstimos, etc.)
                        "other_deductions": {
                            "type": "array",
                            "description": (
                                "Linhas do grupo 'Other' da tabela Deductions. "
                                "Inclui: Bond, 401(k), Stock Plan, Life Insurance, Loan. "
                                "Preencher SOMENTE o que aparecer no documento."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "description": {
                                        "type": "string",
                                        "description": "Nome do desconto como aparece no documento. Ex: '401(k)', 'Bond'."
                                    },
                                    "this_period": {
                                        "type": "string",
                                        "description": "Valor descontado neste período. Para 401(k): '28.85'."
                                    },
                                    "year_to_date": {
                                        "type": "string",
                                        "description": "Total acumulado no ano. Para 401(k): '1,500.20'."
                                    }
                                },
                                "required": ["description"]
                            }
                        },

                        # ── AJUSTES DE DEDUÇÕES ───────────────────────────────────
                        # Linhas de ajuste positivo (ex: Life Insurance como crédito)
                        "deduction_adjustments": {
                            "type": "array",
                            "description": (
                                "Ajustes de deduções — valores positivos que aparecem na seção Other "
                                "do holerite. Ex: '+ 13.50 Life Insurance'."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "description": {"type": "string"},
                                    "this_period": {
                                        "type": "string",
                                        "description": "Valor do ajuste (sem o sinal +). Ex: '13.50'."
                                    }
                                },
                                "required": ["description"]
                            }
                        },

                        # ── TABELA OTHER BENEFITS ─────────────────────────────────
                        # Exemplo:
                        #   | Group Term Life | 0.51 | 27.00 |
                        #   | Vac Hrs         |      | 40.00 |
                        "other_benefits": {
                            "type": "array",
                            "description": (
                                "Linhas da tabela 'Other Benefits and Information'. "
                                "Inclui: Group Term Life, Loan Amt Paid, Vac Hrs, Sick Hrs, Title."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "description": {"type": "string"},
                                    "this_period": {
                                        "type": "string",
                                        "description": "Valor neste período. Pode ser null se não houver."
                                    },
                                    "total_to_date": {
                                        "type": "string",
                                        "description": "Total acumulado. Ex: para Vac Hrs: '40.00'."
                                    }
                                },
                                "required": ["description"]
                            }
                        },

                        # ── NOTAS IMPORTANTES ─────────────────────────────────────
                        "important_notes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Textos da seção 'Important Notes' do documento. "
                                "Cada parágrafo é um item separado na lista."
                            )
                        },

                        # ── ALERTAS DE QUALIDADE ──────────────────────────────────
                        "alertas_inconsistencias": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Alertas sobre problemas detectados: legibilidade comprometida, "
                                "campos contraditórios, selos de VOID/SAMPLE/SPECIMEN no documento."
                            )
                        }
                    },
                    "required": ["tipo_classificado", "nome_titular"]
                }
            }
        }
    }