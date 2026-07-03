import json

class SchemaTransformer:
    """
    Camada de Domínio e Transformação (Domain/Business Layer).
    Mescla de forma segura o esqueleto hierárquico da LLM com as confianças estáveis do BDA.
    """
    def __init__(self, templates: dict):
        self.templates = templates

    def extrair_confiancas_explainability(self, bda_json: dict) -> dict:
        """Lê as confianças reais por campo do nó explainability_info do BDA."""
        exp = bda_json.get("explainability_info", {})
        resultado = {}
        
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

    def mesclar_tabelas_ia_contextual(self, template: dict, raw_fields_ia: dict):
        """Mapeia arrays e subobjetos da IA para o template associando chaves de isolamento de colunas."""
        fields_ia = raw_fields_ia.get("campos_extraidos_brutos") or raw_fields_ia
        if isinstance(fields_ia, str):
            try: fields_ia = json.loads(fields_ia)
            except: return

        if not isinstance(fields_ia, dict): return

        # 1. Popula os campos planos na raiz do template
        for k, v in fields_ia.items():
            if v in (None, "") or isinstance(v, (dict, list)): continue
            k_norm = k.lower().replace("_", "")
            for tk in template.keys():
                if tk.lower().replace("_", "") == k_norm and not isinstance(template[tk], (dict, list)):
                    template[tk] = str(v)

        # 2. Mapeamento Estruturado de Earnings (Evita misturar regular com gross_pay)
        if "earnings" in fields_ia and isinstance(fields_ia["earnings"], list):
            for item_ia in fields_ia["earnings"]:
                if not isinstance(item_ia, dict): continue
                desc_ia = str(item_ia.get("description", "")).lower().strip()
                
                for row_t in template.get("earnings", []):
                    if str(row_t.get("description", "")).lower().strip() == desc_ia:
                        for m_key in ["rate", "hours", "this_period", "year_to_date"]:
                            val = item_ia.get(m_key)
                            # Blindagem: Impede que a descrição textual herde o campo de valor
                            if val not in (None, "") and str(val).lower().strip() != desc_ia:
                                row_t[m_key] = str(val)

        # 3. Mapeamento Estruturado de Deduções (Statutory e Outros)
        deductions_ia = fields_ia.get("statutory_deductions") or fields_ia.get("deductions")
        if deductions_ia and isinstance(deductions_ia, dict):
            stat_target = template.get("deductions", {}).get("statutory", [])
            other_target = template.get("deductions", {}).get("other", [])
            
            for k_ia, v_ia in deductions_ia.items():
                k_ia_norm = k_ia.lower().strip()
                
                if isinstance(v_ia, dict):
                    this_period_val = v_ia.get("this_period") or v_ia.get("amount")
                    ytd_val = v_ia.get("year_to_date")
                else:
                    this_period_val = v_ia
                    ytd_val = None

                val_str = str(this_period_val) if this_period_val not in (None, "") and str(this_period_val).lower().strip() != k_ia_norm else None
                ytd_str = str(ytd_val) if ytd_val not in (None, "") and str(ytd_val).lower().strip() != k_ia_norm else None

                for row in stat_target:
                    if row.get("description", "").lower().strip() in k_ia_norm or k_ia_norm in row.get("description", "").lower().strip():
                        if val_str: row["this_period"] = val_str
                        if ytd_str: row["year_to_date"] = ytd_str
                            
                for row in other_target:
                    if row.get("description", "").lower().strip() in k_ia_norm or k_ia_norm in row.get("description", "").lower().strip():
                        if val_str: row["this_period"] = val_str
                        if ytd_str: row["year_to_date"] = ytd_str

        if "net_pay" in fields_ia:
            np_val = fields_ia["net_pay"]
            val_str = str(np_val.get("this_period") or np_val) if isinstance(np_val, dict) else str(np_val)
            if isinstance(template.get("net_pay"), dict) and val_str.lower().strip() != "net_pay":
                template["net_pay"]["this_period"] = val_str

    def aplicar_overlay_bda_estrito(self, template: dict, ir: dict, subtipo: str):
        """Força a sobreposição dos 13 campos do Blueprint sobre as folhas da árvore."""
        subtipo_lower = subtipo.lower() if subtipo else ""
        
        for k, v in ir.items():
            if v in (None, ""): continue
            k_norm = k.lower().replace("_", "")
            for tk in template.keys():
                if tk.lower().replace("_", "") == k_norm and not isinstance(template[tk], (dict, list)):
                    template[tk] = str(v)

        if subtipo_lower == "pay_stub":
            val_gross_tp = ir.get("gross_pay_this_period")
            val_gross_ytd = ir.get("gross_pay_ytd")
            val_net_tp = ir.get("net_pay_this_period")
            
            for e in template.get("earnings", []):
                if "gross_pay" in e:
                    if val_gross_tp: e["gross_pay"]["this_period"] = str(val_gross_tp)
                    if val_gross_ytd: e["gross_pay"]["year_to_date"] = str(val_gross_ytd)
                    
            if val_net_tp and isinstance(template.get("net_pay"), dict):
                template["net_pay"]["this_period"] = str(val_net_tp)

            if "deductions" in template and isinstance(template["deductions"], dict):
                bda_mapeamentos = {
                    "federal income tax": ir.get("federal_income_tax"),
                    "social security tax": ir.get("social_security_tax"),
                    "medicare tax": ir.get("medicare_tax"),
                    "401(k)": ir.get("retirement_401k")
                }
                for row in template["deductions"].get("statutory", []):
                    desc = row.get("description", "").lower()
                    if desc in bda_mapeamentos and bda_mapeamentos[desc]:
                        row["this_period"] = str(bda_mapeamentos[desc])
                for row in template["deductions"].get("other", []):
                    desc = row.get("description", "").lower()
                    if desc in bda_mapeamentos and bda_mapeamentos[desc]:
                        row["this_period"] = str(bda_mapeamentos[desc])

    def executar(self, subtipo: str, arquivo: str, raw_fields_ia: dict, bda_json: dict, s3_inputs: dict, correcoes_humanas: dict = None) -> dict:
        template_base = self.templates.get(subtipo.lower(), {})
        template_final = json.loads(json.dumps(template_base))
        
        # 1. Mescla dados contextuais da IA isolando as colunas numéricas
        self.mesclar_tabelas_ia_contextual(template_final, raw_fields_ia)
        
        # 2. Sobrevisão com dados de alta fidelidade do Blueprint
        inference_result = (bda_json or {}).get("inference_result", {})
        self.aplicar_overlay_bda_estrito(template_final, inference_result, subtipo)

        is_human_override = False
        if correcoes_humanas:
            for composite_key, valor_corrigido in correcoes_humanas.items():
                if "__" in composite_key:
                    file_part, field_part = composite_key.split("__", 1)
                    if file_part == arquivo:
                        is_human_override = True

        confiancas_por_campo = self.extrair_confiancas_explainability(bda_json or {})
        campos_bda_preenchidos = set(inference_result.keys())
        
        if is_human_override:
            media_real = 1.0000
        elif confiancas_por_campo and campos_bda_preenchidos:
            confs = [confiancas_por_campo[c] for c in campos_bda_preenchidos if c in confiancas_por_campo]
            media_real = round(sum(confs) / len(confs), 4) if confs else 0.8850
        else:
            media_real = 0.8850

        campos_gabarito_plano = json.dumps(template_final)
        status_extracao = "sucesso"
        for critico in ["payee_name", "pay_date", "amount_numeric", "employee_name"]:
            if f'"{critico}": null' in campos_gabarito_plano or f'"{critico}": ""' in campos_gabarito_plano:
                status_extracao = "parcial"

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
                "s3_uri_resultado_bda": f"s3://{s3_inputs['bucket_saida']}/{s3_inputs['key_bda']}"
            },
            "confiabilidade_extracao": {
                "status_extracao": status_extracao,
                "confianca_media": f"{media_real:.4f}",
                "fonte_confiabilidade": "human_audit_override" if is_human_override else "amazon_bedrock_data_automation",
                "observacoes": []
            }
        }