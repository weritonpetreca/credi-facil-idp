"""
shared/tools.py — Fábrica polimórfica de tool specs para o Amazon Bedrock Nova Lite.

POR QUE ISSO MUDOU (contexto para quem ler este arquivo no futuro):
Até a versão anterior, existia UMA ÚNICA tool spec (`estruturar_dados_documento_cliente_unico`),
fortemente enviesada para pay_stub (earnings_rows, statutory_deductions...). Ela era usada
para TODOS os 6 tipos de documento do pacote. Resultado: W2, CNH, extrato bancário e apólice
de seguro praticamente não tinham campos extraídos pela IA — só o que o BDA cobria de forma
plana (ver aplicar_overlay_bda_estrito em schema_transformer.py), e nada preenchia as
estruturas ANINHADAS de cada tipo (primary_applicant/co_applicant do seguro, your_account_valuation
do extrato, box12_items do W2 etc).

Agora existe UMA tool spec POR SUBTIPO, cada uma desenhada para ESPELHAR 1:1 a estrutura do
template correspondente em nova_structurer/handler.py (MAPA_TEMPLATES). Isso permite que
schema_transformer.py use um merge GENÉRICO E RECURSIVO (mesclar_generico_por_template) em vez
de código bespoke por tipo — a única exceção é pay_stub, que mantém sua lógica bespoke original
(mesclar_tabelas_ia_contextual) por já estar validada em produção e usar um casamento por
'description' que não se generaliza trivialmente.

Analogia Java: é a diferença entre um único Map<String,Object> genérico e seis DTOs
fortemente tipados, um por subtipo de documento — cada um com só os campos que fazem
sentido para aquele tipo. Com o DTO certo, o "compilador" (o próprio schema JSON que
vai para o Bedrock) já guia o modelo a preencher a coisa certa.

Quem decide QUAL tool spec usar é shared/classificador.py + o dispatcher
obter_especificacao_ferramenta(subtipo) no final deste arquivo.
"""

# Campos comuns a todas as tool specs — reaproveitados para não repetir descrição.
_CAMPO_TIPO_CLASSIFICADO = {
    "type": "string",
    "enum": [
        "PAY_STUB", "PAYROLL_CHECK", "DRIVER_LICENSE",
        "W2_TAX_FORM", "BANK_STATEMENT", "HOMEOWNERS_INSURANCE", "UNKNOWN"
    ],
    "description": "Tipo do documento identificado no markdown. Deve refletir o tipo real, mesmo que já tenhamos uma classificação prévia — serve como checagem cruzada.",
}

_CAMPO_ALERTAS = {
    "type": "array",
    "items": {"type": "string"},
    "description": "Alertas sobre problemas detectados: legibilidade comprometida, campos contraditórios, selos de VOID/SAMPLE/SPECIMEN no documento.",
}


def obter_especificacao_ferramenta_pay_stub() -> dict:
    """
    Tool spec para pay_stub (holerites). Mantida EXATAMENTE como validada em produção —
    é a lógica mais antiga e testada do pipeline, casada com mesclar_tabelas_ia_contextual
    (merge bespoke por 'description', não pelo merge genérico).
    """
    return {
        "toolSpec": {
            "name": "estruturar_pay_stub",
            "description": (
                "Extrai campos SECUNDÁRIOS de um holerite (pay_stub) a partir do markdown estruturado. "
                "Os campos principais (nomes, datas, valores de renda, SSN) já foram extraídos pelo BDA "
                "e serão informados no prompt como 'CAMPOS JÁ EXTRAÍDOS'. "
                "Sua tarefa é preencher as tabelas detalhadas e campos complementares. "
                "Preencher obrigatoriamente earnings_rows, statutory_deductions, other_deductions, "
                "other_benefits e important_notes. Cada item de lista deve ter ao menos um campo "
                "não-nulo para ser incluído."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "tipo_classificado": _CAMPO_TIPO_CLASSIFICADO,
                        "nome_titular": {
                            "type": "string",
                            "description": "Nome completo do titular em CAIXA ALTA. Ex: 'JOHN STILES'.",
                        },
                        "employer_address": {
                            "type": "string",
                            "description": "Endereço completo do empregador. Ex: '475 ANY AVENUE ANYTOWN, USA 10101'.",
                        },
                        "employee_address": {
                            "type": "string",
                            "description": "Endereço completo do empregado. Ex: '101 MAIN STREET ANYTOWN, USA 12345'.",
                        },
                        "document_title": {
                            "type": "string",
                            "description": "Título do documento. Ex: 'Earnings Statement', 'Payroll Check'.",
                        },
                        "federal_taxable_wages_this_period": {
                            "type": "string",
                            "description": "Ex: 'Your federal wages this period are $X'. Ex: '386.15'.",
                        },
                        "exemptions_federal": {"type": "string", "description": "Número de isenções federais. Ex: '3'."},
                        "exemptions_state": {"type": "string", "description": "Número de isenções estaduais. Ex: '2'."},
                        "exemptions_local": {"type": "string", "description": "Número de isenções locais. Ex: '2'."},
                        "additional_federal_tax": {"type": "string", "description": "Imposto federal adicional. Ex: '$25'."},
                        "earnings_rows": {
                            "type": "array",
                            "description": (
                                "OBRIGATÓRIO: cada linha da tabela Earnings (Regular, Overtime, Holiday, "
                                "Tuition, Gross Pay). Preencher SOMENTE linhas que aparecem no documento. "
                                "NÃO inventar linhas."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "description": {"type": "string", "description": "'regular', 'overtime', 'holiday', 'tuition', 'gross pay'."},
                                    "rate": {"type": "string", "description": "Coluna 'rate'. Para Gross Pay: null."},
                                    "hours": {"type": "string", "description": "Coluna 'hours'. Para Tuition/Gross Pay: null."},
                                    "this_period": {"type": "string", "description": "Coluna 'this period'."},
                                    "year_to_date": {"type": "string", "description": "Coluna 'year to date'."},
                                },
                                "required": ["description"],
                            },
                        },
                        "statutory_deductions": {
                            "type": "array",
                            "description": "OBRIGATÓRIO: linhas do grupo 'Statutory' da tabela Deductions.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "description": {"type": "string"},
                                    "this_period": {"type": "string", "description": "Ignorar sinal negativo."},
                                    "year_to_date": {"type": "string"},
                                },
                                "required": ["description"],
                            },
                        },
                        "other_deductions": {
                            "type": "array",
                            "description": "Linhas do grupo 'Other' da tabela Deductions (Bond, 401(k), Stock Plan, Life Insurance, Loan).",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "description": {"type": "string"},
                                    "this_period": {"type": "string"},
                                    "year_to_date": {"type": "string"},
                                },
                                "required": ["description"],
                            },
                        },
                        "deduction_adjustments": {
                            "type": "array",
                            "description": "Ajustes positivos na seção Other. Ex: '+ 13.50 Life Insurance'.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "description": {"type": "string"},
                                    "this_period": {"type": "string", "description": "Sem o sinal +."},
                                },
                                "required": ["description"],
                            },
                        },
                        "other_benefits": {
                            "type": "array",
                            "description": "Linhas de 'Other Benefits and Information' (Group Term Life, Loan Amt Paid, Vac Hrs, Sick Hrs, Title).",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "description": {"type": "string"},
                                    "this_period": {"type": "string"},
                                    "total_to_date": {"type": "string"},
                                },
                                "required": ["description"],
                            },
                        },
                        "important_notes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Cada parágrafo de 'Important Notes' é um item separado.",
                        },
                        "alertas_inconsistencias": _CAMPO_ALERTAS,
                    },
                    "required": ["tipo_classificado", "nome_titular"],
                }
            },
        }
    }


def obter_especificacao_ferramenta_payroll_check() -> dict:
    """Tool spec para payroll_check — espelha TEMPLATE_PAYROLL_CHECK 1:1 (merge genérico)."""
    props_texto = {
        "issuer_name": "Nome da empresa emissora, em CAIXA ALTA.",
        "issuer_address": "Endereço completo da empresa emissora.",
        "check_stock_control_number": "Número de controle do talão/formulário do cheque, se houver (geralmente no canto superior).",
        "payroll_check_number": "Número do cheque de pagamento.",
        "pay_date": "Data de pagamento (Pay date).",
        "social_security_number": "Número do seguro social (SSN) impresso no cheque.",
        "payee_name": "Nome de quem vai receber o pagamento (Pay to the order of), em CAIXA ALTA.",
        "amount_words": "Valor do cheque por extenso.",
        "amount_numeric": "Valor numérico do cheque (ex: '291.90').",
        "bank_name": "Nome do banco emissor.",
        "bank_address": "Endereço do banco emissor.",
        "sample_indicator": "'SAMPLE' se esse selo aparecer estampado no cheque, senão null.",
        "non_negotiable_indicator": "'NON-NEGOTIABLE' se esse selo aparecer, senão null.",
        "void_indicator": "'VOID' se esse selo aparecer, senão null.",
        "authorized_signature_present": "'true' se houver uma assinatura na linha 'Authorized Signature', senão 'false'.",
        "void_after_text": "Texto tipo 'VOID AFTER 90 DAYS', se presente.",
        "micr_check_number": "Número do cheque na linha MICR (a linha de caracteres na parte inferior do cheque).",
        "micr_routing_number": "Número de roteamento (routing number) na linha MICR.",
        "micr_account_number": "Número da conta na linha MICR.",
        "security_notice_bottom": "Texto do aviso de segurança no rodapé do cheque, se legível.",
    }
    properties = {k: {"type": "string", "description": v} for k, v in props_texto.items()}
    properties["tipo_classificado"] = _CAMPO_TIPO_CLASSIFICADO
    properties["alertas_inconsistencias"] = _CAMPO_ALERTAS

    return {
        "toolSpec": {
            "name": "estruturar_payroll_check",
            "description": (
                "Extrai todos os campos de um cheque de pagamento (payroll check) a partir do markdown "
                "estruturado. Preencha campos com null quando o dado não aparecer no documento — não invente."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": properties,
                    "required": ["tipo_classificado", "payee_name"],
                }
            },
        }
    }


def obter_especificacao_ferramenta_driver_license() -> dict:
    """Tool spec para driver_license — espelha TEMPLATE_DRIVER_LICENSE 1:1 (merge genérico)."""
    props_texto = {
        "identification_document_type": "Tipo do documento, ex: 'DRIVER LICENSE'.",
        "document_number": "Número do documento/licença.",
        "full_name": "Nome completo do titular, em CAIXA ALTA.",
        "date_of_birth": "Data de nascimento (DOB).",
        "issue_date": "Data de emissão (ISS).",
        "expiration_date": "Data de validade (EXP).",
        "issuing_authority": "Órgão emissor, se explicitado (ex: um selo ou nome de agência).",
        "issuing_state": "Sigla do estado emissor (ex: 'MA', 'NV').",
        "issuing_country": "País emissor, se explicitado (assuma 'USA' se o documento for claramente americano e não houver texto contrário).",
        "address": "Endereço completo do titular.",
        "class": "Classe da licença (CLASS), ex: 'D'.",
        "restrictions": "Restrições (REST), ex: 'NONE' ou códigos de restrição.",
        "endorsements": "Endossos (END), ex: 'NONE'.",
        "sex": "Sexo (SEX), ex: 'F' ou 'M'.",
        "height": "Altura (HGT), ex: '4-6\\\"'.",
        "eye_color": "Cor dos olhos (EYES), ex: 'BLK'.",
        "document_discriminator": "Número discriminador do documento, se houver um código longo separado do document_number.",
        "revision_date": "Data de revisão (REV), se presente.",
        "security_ghost_dob": "Data de nascimento 'ghost' impressa como elemento de segurança (geralmente repetida em outro canto do cartão), se visível.",
    }
    properties = {k: {"type": "string", "description": v} for k, v in props_texto.items()}
    properties["tipo_classificado"] = _CAMPO_TIPO_CLASSIFICADO
    properties["alertas_inconsistencias"] = _CAMPO_ALERTAS

    return {
        "toolSpec": {
            "name": "estruturar_driver_license",
            "description": (
                "Extrai todos os campos visíveis de uma carteira de motorista (driver license / CNH americana) "
                "a partir do markdown estruturado e da transcrição visual do cartão. Preencha com null o que "
                "não estiver legível ou presente — não invente valores."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": properties,
                    "required": ["tipo_classificado", "full_name"],
                }
            },
        }
    }


def obter_especificacao_ferramenta_w2_tax_form() -> dict:
    """
    Tool spec para w2_tax_form — espelha os campos "limpos" de TEMPLATE_W2_FORM 1:1.

    Campos do template com nomes problemáticos para schema (contêm ponto, espaço ou
    apóstrofo: "OMB_No.", "staturoty employee", "retirement plan", "third-party_sick_pay",
    "other", "employer's_state_id_number") ficam de fora da tool spec — são baixo valor
    para o score de crédito e continuam disponíveis via aplicar_overlay_bda_estrito()
    caso o BDA os capture. box12_items é tratado à parte (ver _mesclar_box12_w2 em
    schema_transformer.py) porque o template representa as 4 linhas (a/b/c/d) como um
    único dict achatado, não como uma lista de linhas repetidas.
    """
    props_texto = {
        "form_type": "Tipo do formulário, ex: 'W-2'.",
        "employee_social_security_number": "Número do seguro social do empregado (campo 'a').",
        "employer_identification_number": "EIN do empregador (campo 'b').",
        "employer_name": "Nome do empregador (campo 'c').",
        "employer_address": "Endereço completo do empregador (campo 'c').",
        "control_number": "Número de controle (campo 'd').",
        "employee_first_name_and_initial": "Primeiro nome e inicial do empregado (campo 'e').",
        "employee_last_name": "Sobrenome do empregado (campo 'e').",
        "employee_address": "Endereço completo do empregado (campo 'f').",
        "wages_tips_other_compensation": "Caixa 1 — Wages, tips, other compensation.",
        "federal_income_tax_withheld": "Caixa 2 — Federal income tax withheld.",
        "social_security_wages": "Caixa 3 — Social security wages.",
        "social_security_tax_withheld": "Caixa 4 — Social security tax withheld.",
        "medicare_wages_and_tips": "Caixa 5 — Medicare wages and tips.",
        "medicare_tax_withheld": "Caixa 6 — Medicare tax withheld.",
        "social_security_tips": "Caixa 7 — Social security tips.",
        "allocated_tips": "Caixa 8 — Allocated tips.",
        "dependent_care_benefits": "Caixa 10 — Dependent care benefits.",
        "nonqualified_plans": "Caixa 11 — Nonqualified plans.",
        "state": "Caixa 15 — sigla do estado.",
        "state_wages_tips_etc": "Caixa 16 — State wages, tips, etc.",
        "state_income_tax": "Caixa 17 — State income tax.",
        "local_wages_tips_etc": "Caixa 18 — Local wages, tips, etc.",
        "local_income_tax": "Caixa 19 — Local income tax.",
        "locality_name": "Caixa 20 — Locality name.",
        "tax_year": "Ano fiscal do formulário (impresso em destaque, ex: '2022').",
    }
    properties = {k: {"type": "string", "description": v} for k, v in props_texto.items()}
    properties["tipo_classificado"] = _CAMPO_TIPO_CLASSIFICADO
    properties["alertas_inconsistencias"] = _CAMPO_ALERTAS
    properties["box12_items"] = {
        "type": "array",
        "description": (
            "Linhas da Caixa 12 (12a, 12b, 12c, 12d), cada uma com um código de letra e um valor. "
            "Preencher SOMENTE as linhas que aparecem no documento, na ordem em que aparecem (a primeira "
            "linha encontrada vira 12a, a segunda 12b, etc). Máximo 4 itens."
        ),
        "items": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Código da letra, ex: 'A', 'C'."},
                "amount": {"type": "string", "description": "Valor associado ao código, ex: '500.00'."},
            },
            "required": ["code"],
        },
    }

    return {
        "toolSpec": {
            "name": "estruturar_w2_tax_form",
            "description": (
                "Extrai todos os campos de um formulário W-2 (Wage and Tax Statement) a partir do markdown "
                "estruturado. Preencha com null o que não aparecer no documento — não invente valores."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": properties,
                    "required": ["tipo_classificado", "employee_last_name"],
                }
            },
        }
    }


def obter_especificacao_ferramenta_account_statement() -> dict:
    """
    Tool spec para account_statement — espelha TEMPLATE_ACCOUNT_STATEMENT 1:1, incluindo
    as duas listas de tamanho VARIÁVEL (your_account_valuation, your_insurance_details).
    Ao contrário do pay_stub, aqui não há um conjunto fixo de 'descriptions' esperadas —
    o extrato pode ter de 1 a N linhas de investimento — por isso o merge genérico
    SUBSTITUI a lista inteira pelo que a IA extraiu (ver mesclar_generico_por_template).
    """
    return {
        "toolSpec": {
            "name": "estruturar_account_statement",
            "description": (
                "Extrai todos os campos de um extrato de conta/investimento (account statement) a partir "
                "do markdown estruturado, incluindo a tabela completa de valuation de investimentos e a "
                "tabela de detalhes de seguro, se presentes. Preencha com null o que não aparecer."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "tipo_classificado": _CAMPO_TIPO_CLASSIFICADO,
                        "your_details": {
                            "type": "object",
                            "description": "Dados cadastrais do titular da conta.",
                            "properties": {
                                "account_holder_name": {"type": "string", "description": "Nome do titular."},
                                "account_holder_address": {"type": "string", "description": "Endereço do titular."},
                                "account_holder_phone_number": {"type": "string", "description": "Telefone do titular."},
                                "statement_period": {"type": "string", "description": "Período do extrato, ex: '1 MAY 2021 to 31 MAY 2021'."},
                                "account_number": {"type": "string", "description": "Número da conta."},
                                "account_name": {"type": "string", "description": "Nome da conta (pode repetir o nome do titular)."},
                                "email_address": {"type": "string", "description": "E-mail cadastrado, ou 'Not Recorded' se explicitamente assim indicado."},
                            },
                        },
                        "your_account_balance": {
                            "type": "object",
                            "description": "Saldo de abertura e fechamento do período.",
                            "properties": {
                                "opening_balance": {"type": "string", "description": "Saldo de abertura do período."},
                                "closing_balance": {"type": "string", "description": "Saldo de fechamento do período."},
                            },
                        },
                        "your_account_valuation": {
                            "type": "array",
                            "description": (
                                "TODAS as linhas da tabela de valuation de investimentos (uma por opção de "
                                "investimento). Preencher exatamente o número de linhas presentes no documento — "
                                "pode ser 1, pode ser 5, não há limite fixo. NÃO inventar linhas."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "investment_option_name": {"type": "string", "description": "Nome da opção de investimento."},
                                    "option_code": {"type": "string", "description": "Código da opção."},
                                    "units": {"type": "string", "description": "Quantidade de unidades (units)."},
                                    "unit_price_$": {"type": "string", "description": "Preço unitário em USD."},
                                    "value_$": {"type": "string", "description": "Valor total da linha em USD."},
                                    "percentage": {"type": "string", "description": "Percentual do total da carteira, ex: '40'."},
                                },
                            },
                        },
                        "account_value": {
                            "type": "object",
                            "description": "Linha de TOTAL da tabela de valuation (soma de todas as opções).",
                            "properties": {
                                "value": {"type": "string", "description": "Valor total da conta em USD."},
                                "percentage": {"type": "string", "description": "Deve ser '100' quando é a linha de total."},
                            },
                        },
                        "your_insurance_details": {
                            "type": "array",
                            "description": "Linhas da tabela 'Your insurance details', se o extrato tiver uma seção de seguro atrelada.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "benefit_type": {"type": "string", "description": "Tipo de benefício, ex: 'Amount paid on Death of Terminal illness'."},
                                    "insurance_cover_amount_$": {"type": "string", "description": "Valor de cobertura em USD."},
                                    "benefit_amount_$": {"type": "string", "description": "Valor do benefício em USD."},
                                },
                            },
                        },
                        "alertas_inconsistencias": _CAMPO_ALERTAS,
                    },
                    "required": ["tipo_classificado"],
                }
            },
        }
    }


def obter_especificacao_ferramenta_homeowners_insurance() -> dict:
    """Tool spec para homeowners_insurance_application — espelha TEMPLATE_HOMEOWNERS_INSURANCE 1:1."""
    props_topo_texto = {
        "named_insured": "Nome do segurado principal, como aparece no topo do documento.",
        "mailing_address": "Endereço de correspondência.",
        "primary_email": "E-mail principal.",
        "primary_phone": "Telefone principal.",
        "alternate_phone": "Telefone alternativo.",
        "insurance_company": "Nome da seguradora.",
        "insurance_company_address": "Endereço da seguradora.",
        "insured_property_address": "Endereço do imóvel segurado (se diferente do mailing_address).",
        "policy_number": "Número da apólice.",
        "purchase_date_time": "Data/hora de compra da apólice.",
        "effective_date": "Data de início de vigência.",
        "expiration_date": "Data de expiração da vigência.",
    }
    properties = {k: {"type": "string", "description": v} for k, v in props_topo_texto.items()}
    properties["tipo_classificado"] = _CAMPO_TIPO_CLASSIFICADO
    properties["alertas_inconsistencias"] = _CAMPO_ALERTAS

    props_applicant_texto = {
        "name": "Nome completo.",
        "date_of_birth": "Data de nascimento.",
        "gender": "Gênero (ex: 'M', 'F').",
        "marital_status": "Estado civil (ex: 'S' para solteiro, 'M' para casado).",
    }
    properties["primary_applicant"] = {
        "type": "object",
        "description": "Dados do requerente principal (Primary Applicant Information).",
        "properties": {
            **{k: {"type": "string", "description": v} for k, v in props_applicant_texto.items()},
            "education_level": {"type": "string", "description": "Nível de educação, ex: 'Graduate'."},
            "existing_policy": {"type": "string", "description": "Indicador de apólice Esurance existente, se houver."},
            "drivers_license_number": {"type": "string", "description": "Número da carteira de motorista."},
            "dl_state": {"type": "string", "description": "Estado emissor da carteira de motorista."},
            "currently_insured_auto": {"type": "string", "description": "Seguradora de auto atual."},
            "length_current_auto_carrier": {"type": "string", "description": "Tempo com a seguradora de auto atual, ex: '1 Year'."},
            "length_prior_auto_carrier": {"type": "string", "description": "Tempo com a seguradora de auto anterior."},
            "years_prior_property_company": {"type": "string", "description": "Anos com a seguradora de imóvel anterior."},
            "current_property_policy_type": {"type": "string", "description": "Tipo da apólice de imóvel atual, ex: 'Home'."},
        },
    }
    properties["co_applicant"] = {
        "type": "object",
        "description": "Dados do co-requerente (Co-Applicant Information), se houver.",
        "properties": {
            **{k: {"type": "string", "description": v} for k, v in props_applicant_texto.items()},
            "education_level": {"type": "string", "description": "Nível de educação, ex: 'Graduate'."},
            "relationship_to_primary_applicant": {"type": "string", "description": "Relação com o requerente principal, ex: 'Domestic Partner'."},
            "drivers_license_number": {"type": "string", "description": "Número da carteira de motorista do co-requerente."},
            "dl_state": {"type": "string", "description": "Estado emissor da carteira de motorista do co-requerente."},
            "currently_insured_auto": {"type": "string", "description": "Seguradora de auto atual do co-requerente."},
            "length_current_auto_carrier": {"type": "string", "description": "Tempo do co-requerente com a seguradora de auto atual, ex: '1 year'."},
            "length_prior_auto_carrier": {"type": "string", "description": "Tempo do co-requerente com a seguradora de auto anterior, ex: '6 months'."},
        },
    }

    return {
        "toolSpec": {
            "name": "estruturar_homeowners_insurance",
            "description": (
                "Extrai todos os campos de uma proposta de seguro residencial (homeowners insurance "
                "application) a partir do markdown estruturado, incluindo os blocos de requerente "
                "principal e co-requerente. Preencha com null o que não aparecer — não invente valores."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": properties,
                    "required": ["tipo_classificado", "named_insured"],
                }
            },
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# DISPATCHER: escolhe a tool spec certa a partir do subtipo já classificado
# (ver shared/classificador.py — a classificação acontece ANTES desta chamada,
# usando matched_blueprint do BDA + heurística de nome de arquivo).
# ─────────────────────────────────────────────────────────────────────────────

_FABRICA_POR_SUBTIPO = {
    "pay_stub": obter_especificacao_ferramenta_pay_stub,
    "payroll_check": obter_especificacao_ferramenta_payroll_check,
    "driver_license": obter_especificacao_ferramenta_driver_license,
    "w2_tax_form": obter_especificacao_ferramenta_w2_tax_form,
    "account_statement": obter_especificacao_ferramenta_account_statement,
    "homeowners_insurance_application": obter_especificacao_ferramenta_homeowners_insurance,
}


def obter_especificacao_ferramenta(subtipo: str) -> dict:
    """
    Dispatcher polimórfico: recebe o subtipo já classificado e devolve a tool spec certa.
    Cai para pay_stub como default se o subtipo não for reconhecido — mesmo comportamento
    conservador que o pipeline já tinha antes desta mudança (nunca ficar sem nenhuma tool).
    """
    fabrica = _FABRICA_POR_SUBTIPO.get((subtipo or "").lower(), obter_especificacao_ferramenta_pay_stub)
    return fabrica()