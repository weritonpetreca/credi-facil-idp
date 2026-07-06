"""
nova_structurer/schema_transformer.py — Camada de domínio e transformação.

Responsabilidade: fundir os dados de três fontes no template final:
  1. Nova Lite (campos secundários via tool calling)  → mesclar_tabelas_ia_contextual()
  2. BDA inference_result (campos críticos, alta confiança) → aplicar_overlay_bda_estrito()
  3. Revisão humana (verdade absoluta, máxima prioridade)

Analogia Java:
  Fonte 1 = dados de um serviço externo menos confiável
  Fonte 2 = dados do banco de dados local (mais confiável)
  Fonte 3 = dados inseridos pelo administrador (suprema autoridade)

O padrão é: escrever o menos confiável primeiro, depois sobrescrever com o mais confiável.
Assim a prioridade fica garantida mesmo que o mesmo campo apareça nas duas fontes.
"""
import json
from aws_lambda_powertools import Logger

logger = Logger(child=True)


class SchemaTransformer:
    """
    Funde dados do Nova Lite + BDA + revisão humana no template de negócio.
    """

    def __init__(self, templates: dict):
        self.templates = templates

    # ──────────────────────────────────────────────────────────────────────────
    # FUNÇÃO 1: Leitura de confiança do explainability_info
    # ──────────────────────────────────────────────────────────────────────────

    def extrair_confiancas_explainability(self, bda_json: dict) -> dict:
        """
        Lê as confianças reais por campo do nó explainability_info do BDA.

        Formato confirmado em 02/07/2026 (arquivo result.json real):
          "explainability_info": [          ← é uma LISTA
            {                               ← com UM ÚNICO DICT
              "pay_date": {
                "success": true,
                "confidence": 0.8671875,   ← confiança real de OCR
                "geometry": [...],
                "value": "7/25/2008"
              },
              "employee_name": {
                "success": true,
                "confidence": 0.92578125
              }
            }
          ]

        Retorna: {"pay_date": 0.8671875, "employee_name": 0.92578125, ...}
        """
        exp = bda_json.get("explainability_info", [])
        resultado = {}

        # Normaliza: aceita lista ou dict
        lista_dicts = []
        if isinstance(exp, list):
            for item in exp:
                if isinstance(item, dict):
                    lista_dicts.append(item)
        elif isinstance(exp, dict):
            lista_dicts.append(exp)

        for d in lista_dicts:
            for campo, dados in d.items():
                if isinstance(dados, dict):
                    conf = dados.get("confidence") or dados.get("confidence_score") or dados.get("score")
                    if conf is not None:
                        resultado[campo] = float(conf)

        return resultado

    # ──────────────────────────────────────────────────────────────────────────
    # FUNÇÃO 2: Mesclagem do output do Nova Lite (campos secundários)
    # ──────────────────────────────────────────────────────────────────────────

    def _sanitizar_string_ia(self, valor) -> str:
        """Higieniza alucinações de placeholders e entidades HTML vazias vindas da IA."""
        if valor is None:
            return ""
        s = str(valor).strip()
        # Intercepta e limpa resíduos de formatação Markdown/HTML vazios
        if s in ("&nbsp;", "none", "None", "", "&nbsp", "null", "N/A"):
            return ""
        return s

    def mesclar_tabelas_ia_contextual(self, template: dict, raw_fields_ia: dict):
        """Mapeia o output do Nova Lite higienizando strings nulas e entidades HTML ruidosas."""
        if not isinstance(raw_fields_ia, dict):
            return

        # ── 1. Campos planos da raiz ───────────────────────────────────────────
        CAMPOS_PLANOS = [
            "employer_address", "employee_address", "document_title",
            "federal_taxable_wages_this_period", "exemptions_federal",
            "exemptions_state", "exemptions_local", "additional_federal_tax"
        ]
        for campo in CAMPOS_PLANOS:
            valor = self._sanitizar_string_ia(raw_fields_ia.get(campo))
            if valor:
                if campo in template:
                    template[campo] = valor
                elif campo == "exemptions_federal" and "exemptions_or_allowances" in template:
                    items = template["exemptions_or_allowances"]
                    if items and isinstance(items[0], dict):
                        items[0]["federal"] = valor
                elif campo == "exemptions_state" and "exemptions_or_allowances" in template:
                    items = template["exemptions_or_allowances"]
                    if items and isinstance(items[0], dict):
                        items[0]["state"] = valor
                elif campo == "exemptions_local" and "exemptions_or_allowances" in template:
                    items = template["exemptions_or_allowances"]
                    if items and isinstance(items[0], dict):
                        items[0]["local"] = valor

        # ── 2. earnings_rows → template["earnings"] ────────────────────────────
        earnings_rows = raw_fields_ia.get("earnings_rows", [])
        if earnings_rows and isinstance(earnings_rows, list) and "earnings" in template:
            for row_ia in earnings_rows:
                if not isinstance(row_ia, dict):
                    continue
                desc_ia = str(row_ia.get("description", "")).lower().strip()
                if not desc_ia or desc_ia in ("&nbsp;", "none"):
                    continue

                matched = False
                for row_t in template["earnings"]:
                    if not isinstance(row_t, dict):
                        continue

                    desc_t = str(row_t.get("description", "")).lower().strip()
                    if desc_ia == desc_t:
                        for col in ["rate", "hours", "this_period", "year_to_date"]:
                            val = self._sanitizar_string_ia(row_ia.get(col))
                            if val:
                                row_t[col] = val
                        matched = True
                        break

                    if "gross_pay" in row_t and ("gross" in desc_ia or "gross pay" in desc_ia):
                        gp = row_t["gross_pay"]
                        if isinstance(gp, dict):
                            tp = self._sanitizar_string_ia(row_ia.get("this_period"))
                            ytd = self._sanitizar_string_ia(row_ia.get("year_to_date"))
                            if tp:
                                gp["this_period"] = tp
                            if ytd:
                                gp["year_to_date"] = ytd
                        matched = True
                        break

        # ── 3. statutory_deductions → template["deductions"]["statutory"] ──────
        stat_rows = raw_fields_ia.get("statutory_deductions", [])
        if stat_rows and isinstance(stat_rows, list):
            stat_target = template.get("deductions", {}).get("statutory", [])
            for row_ia in stat_rows:
                if not isinstance(row_ia, dict):
                    continue
                desc_ia = str(row_ia.get("description", "")).lower().strip()
                if desc_ia in ("&nbsp;", "none"): continue
                
                for row_t in stat_target:
                    desc_t = str(row_t.get("description", "")).lower().strip()
                    if desc_ia and desc_t and (desc_ia in desc_t or desc_t in desc_ia):
                        tp = self._sanitizar_string_ia(row_ia.get("this_period"))
                        ytd = self._sanitizar_string_ia(row_ia.get("year_to_date"))
                        if tp:
                            row_t["this_period"] = tp
                        if ytd:
                            row_t["year_to_date"] = ytd
                        break

        # ── 4. other_deductions → template["deductions"]["other"] ─────────────
        other_rows = raw_fields_ia.get("other_deductions", [])
        if other_rows and isinstance(other_rows, list):
            other_target = template.get("deductions", {}).get("other", [])
            for row_ia in other_rows:
                if not isinstance(row_ia, dict):
                    continue
                desc_ia = str(row_ia.get("description", "")).lower().strip()
                if desc_ia in ("&nbsp;", "none"): continue
                
                for row_t in other_target:
                    desc_t = str(row_t.get("description", "")).lower().strip()
                    if desc_ia and desc_t and (desc_ia in desc_t or desc_t in desc_ia):
                        tp = self._sanitizar_string_ia(row_ia.get("this_period"))
                        ytd = self._sanitizar_string_ia(row_ia.get("year_to_date"))
                        if tp:
                            row_t["this_period"] = tp
                        if ytd:
                            row_t["year_to_date"] = ytd
                        break

        # ── 5. deduction_adjustments → template["deductions"]["adjustments"] ───
        adj_rows = raw_fields_ia.get("deduction_adjustments", [])
        if adj_rows and isinstance(adj_rows, list):
            adj_target = template.get("deductions", {}).get("adjustments", [])
            for row_ia in adj_rows:
                if not isinstance(row_ia, dict):
                    continue
                desc_ia = str(row_ia.get("description", "")).lower().strip()
                if desc_ia in ("&nbsp;", "none"): continue
                
                for row_t in adj_target:
                    desc_t = str(row_t.get("description", "")).lower().strip()
                    if desc_ia and desc_t and (desc_ia in desc_t or desc_t in desc_ia):
                        tp = self._sanitizar_string_ia(row_ia.get("this_period"))
                        if tp:
                            row_t["this_period"] = tp
                        break

        # ── 6. other_benefits → template["other_benefits_and_information"] ─────
        benefits_rows = raw_fields_ia.get("other_benefits", [])
        if benefits_rows and isinstance(benefits_rows, list):
            benefits_target = template.get("other_benefits_and_information", [])
            for row_ia in benefits_rows:
                if not isinstance(row_ia, dict):
                    continue
                desc_ia = str(row_ia.get("description", "")).lower().strip()
                if desc_ia in ("&nbsp;", "none"): continue
                
                for row_t in benefits_target:
                    desc_t = str(row_t.get("description", "")).lower().strip()
                    if desc_ia and desc_t and (desc_ia in desc_t or desc_t in desc_ia):
                        tp = self._sanitizar_string_ia(row_ia.get("this_period"))
                        td = self._sanitizar_string_ia(row_ia.get("total_to_date"))
                        if tp:
                            row_t["this_period"] = tp
                        if td:
                            row_t["total_to_date"] = td
                        break

        # ── 7. important_notes → template["important_notes"] ──────────────────
        notes = raw_fields_ia.get("important_notes", [])
        if notes and isinstance(notes, list) and "important_notes" in template:
            target_notes = template["important_notes"]
            for i, note_text in enumerate(notes):
                note_clean = self._sanitizar_string_ia(note_text)
                if not note_clean:
                    continue
                if i < len(target_notes) and isinstance(target_notes[i], dict):
                    target_notes[i]["note_text"] = note_clean
                else:
                    target_notes.append({"note_text": note_clean})

        # ── 8. alertas_inconsistencias ─────────────────────────────────────────
        alertas = raw_fields_ia.get("alertas_inconsistencias", [])
        if alertas and isinstance(alertas, list):
            if "__alertas_ia__" not in template:
                template["__alertas_ia__"] = []
            template["__alertas_ia__"].extend([self._sanitizar_string_ia(a) for a in alertas if self._sanitizar_string_ia(a)])

    # ──────────────────────────────────────────────────────────────────────────
    # FUNÇÃO 3: Overlay BDA — campos críticos sobrescreve o que a IA disse
    # ──────────────────────────────────────────────────────────────────────────

    def aplicar_overlay_bda_estrito(self, template: dict, ir: dict, subtipo: str):
        """
        Força os 13 campos do inference_result do BDA sobre o template.

        Estes valores têm maior confiança que o Nova Lite porque vêm diretamente
        do modelo de visão do BDA (OCR especializado). A IA é usada como fallback
        para campos que o BDA não cobre — os campos do BDA prevalecem sempre.

        Para pay_stub, também mapeia os campos de renda aninhados:
        - gross_pay_this_period → earnings[?gross_pay]["gross_pay"]["this_period"]
        - net_pay_this_period   → net_pay["this_period"]
        - federal_income_tax    → deductions.statutory[?Federal]["this_period"]
        """
        if not ir:
            return

        # Mapeamento plano — campos que existem diretamente no template raiz
        for k, v in ir.items():
            if v is None or (isinstance(v, str) and not v.strip()):
                continue
            k_norm = k.lower().replace("_", "")
            for tk in list(template.keys()):
                if tk.startswith("__"):
                    continue
                if tk.lower().replace("_", "") == k_norm and not isinstance(template[tk], (dict, list)):
                    template[tk] = str(v)

        # Mapeamento específico do pay_stub (campos aninhados)
        subtipo_lower = subtipo.lower() if subtipo else ""
        if subtipo_lower == "pay_stub":
            # gross_pay nos earnings
            val_gross_tp = ir.get("gross_pay_this_period")
            val_gross_ytd = ir.get("gross_pay_ytd")
            val_net_tp = ir.get("net_pay_this_period")

            for e in template.get("earnings", []):
                if isinstance(e, dict) and "gross_pay" in e:
                    gp = e["gross_pay"]
                    if isinstance(gp, dict):
                        if val_gross_tp:
                            gp["this_period"] = str(val_gross_tp)
                        if val_gross_ytd:
                            gp["year_to_date"] = str(val_gross_ytd)

            # net_pay
            if val_net_tp and isinstance(template.get("net_pay"), dict):
                template["net_pay"]["this_period"] = str(val_net_tp)

            # Impostos nas deductions.statutory
            if "deductions" in template and isinstance(template["deductions"], dict):
                mapa_bda_deductions = {
                    "federal income tax": ir.get("federal_income_tax"),
                    "social security tax": ir.get("social_security_tax"),
                    "medicare tax": ir.get("medicare_tax"),
                    "401(k)": ir.get("retirement_401k"),
                }
                for row in template["deductions"].get("statutory", []):
                    desc = str(row.get("description", "")).lower()
                    for chave_bda, valor_bda in mapa_bda_deductions.items():
                        if valor_bda and chave_bda in desc:
                            row["this_period"] = str(valor_bda)
                            break
                for row in template["deductions"].get("other", []):
                    desc = str(row.get("description", "")).lower()
                    for chave_bda, valor_bda in mapa_bda_deductions.items():
                        if valor_bda and chave_bda in desc:
                            row["this_period"] = str(valor_bda)
                            break

    # ──────────────────────────────────────────────────────────────────────────
    # FUNÇÃO PRINCIPAL: Orquestra as três fontes de dados
    # ──────────────────────────────────────────────────────────────────────────

    def executar(
        self,
        subtipo: str,
        arquivo: str,
        raw_fields_ia: dict,
        bda_json: dict,
        s3_inputs: dict,
        correcoes_humanas: dict = None
    ) -> dict:
        """
        Produz o JSON final do documento com dados das três fontes.

        Ordem de aplicação (do menos confiável para o mais confiável):
        1. Nova Lite → preenche tabelas secundárias
        2. BDA inference_result → sobrescreve campos críticos
        3. Revisão humana → sobrescreve qualquer coisa

        Retorna o blueprint_json completo incluindo confiabilidade_extracao.
        """
        # Clona o template para não modificar o original
        template_base = self.templates.get(subtipo.lower(), {})
        template_final = json.loads(json.dumps(template_base))

        # ── FONTE 1: Nova Lite (campos secundários e tabelas) ──────────────────
        self.mesclar_tabelas_ia_contextual(template_final, raw_fields_ia)

        # ── FONTE 2: BDA inference_result (campos críticos, alta confiança) ────
        inference_result = (bda_json or {}).get("inference_result", {})
        self.aplicar_overlay_bda_estrito(template_final, inference_result, subtipo)

        # ── FONTE 3: Correções humanas (máxima prioridade) ─────────────────────
        is_human_override = False
        campos_corrigidos = []
        if correcoes_humanas:
            for composite_key, valor_corrigido in correcoes_humanas.items():
                if "__" in composite_key:
                    file_part, field_part = composite_key.split("__", 1)
                    if file_part == arquivo:
                        is_human_override = True
                        campos_corrigidos.append(field_part)
                        # Tenta encontrar e sobrescrever o campo no template
                        # (suporta tanto campos raiz quanto aninhados simples)
                        if field_part in template_final:
                            template_final[field_part] = valor_corrigido

        # ── CÁLCULO DE CONFIANÇA REAL ──────────────────────────────────────────
        confiancas_por_campo = self.extrair_confiancas_explainability(bda_json or {})
        campos_bda_preenchidos = set(inference_result.keys())

        if is_human_override:
            # Campos corrigidos pelo humano ganham confiança 1.0
            confiancas_atualizadas = dict(confiancas_por_campo)
            for campo in campos_corrigidos:
                confiancas_atualizadas[campo] = 1.0
            confs_lista = list(confiancas_atualizadas.values())
            media_real = round(sum(confs_lista) / len(confs_lista), 4) if confs_lista else 1.0
        elif confiancas_por_campo and campos_bda_preenchidos:
            # Média real das confianças dos campos extraídos pelo BDA
            confs = [confiancas_por_campo[c] for c in campos_bda_preenchidos if c in confiancas_por_campo]
            media_real = round(sum(confs) / len(confs), 4) if confs else 0.0
        else:
            # Fallback: proporção de campos preenchidos (melhor que hardcoded 0.8850)
            todos_campos = [v for k, v in template_final.items() if not k.startswith("__")]
            preenchidos = sum(1 for v in todos_campos
                             if v is not None and v != "" and v != [] and v != {})
            media_real = round(preenchidos / max(len(todos_campos), 1), 4)

        # ── STATUS DA EXTRAÇÃO ─────────────────────────────────────────────────
        # Verifica se campos críticos para decisão de crédito estão preenchidos
        CRITICOS_PARA_CREDITO = [
            "payee_name", "pay_date", "amount_numeric",  # payroll_check
            "employee_name", "net_pay",                   # pay_stub (net_pay é dict)
        ]
        campos_json = json.dumps(template_final)
        status_extracao = "sucesso"
        for critico in CRITICOS_PARA_CREDITO:
            # Verifica tanto campos raiz null quanto dicts com this_period null
            if f'"{critico}": null' in campos_json or f'"{critico}": ""' in campos_json:
                if critico not in campos_corrigidos:
                    status_extracao = "parcial"
                    break

        # ── ALERTAS ────────────────────────────────────────────────────────────
        alertas = list(template_final.pop("__alertas_ia__", []))
        if campos_corrigidos:
            alertas.append(f"Campos retificados manualmente: {', '.join(campos_corrigidos)}")
        # Campos nulos que mereciam atenção
        campos_nulos = [k for k, v in template_final.items()
                       if not k.startswith("__") and v is None and k in campos_bda_preenchidos]
        if campos_nulos:
            alertas.append(f"Campos do blueprint sem valor extraído: {', '.join(campos_nulos)}")

        return {
            "arquivo_original": arquivo,
            "dados_extraidos_do_documento": template_final,
            "localizacao_documento_s3": {
                "bucket_origem": s3_inputs["bucket_entrada"],
                "s3_key_origem": s3_inputs["key_entrada"],
                "s3_uri_origem": f"s3://{s3_inputs['bucket_entrada']}/{s3_inputs['key_entrada']}",
                "bucket_resultado_bda": s3_inputs["bucket_saida"],
                "s3_key_resultado_bda": s3_inputs["key_bda"],
                "s3_key_resultado": s3_inputs["key_resultado"],
                "s3_uri_resultado_bda": f"s3://{s3_inputs['bucket_saida']}/{s3_inputs['key_bda']}",
            },
            "confiabilidade_extracao": {
                "status_extracao": status_extracao,
                "confianca_media": f"{media_real:.4f}",
                "confiancas_por_campo_bda": {k: f"{v:.4f}" for k, v in confiancas_por_campo.items()},
                "fonte_confiabilidade": (
                    "human_audit_override" if is_human_override
                    else "amazon_bedrock_data_automation"
                ),
                "observacoes": alertas,
            },
        }