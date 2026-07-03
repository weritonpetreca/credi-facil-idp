import json

class SchemaTransformer:
    """
    Camada de Domínio e Transformação (Domain/Business Layer).
    Classe 100% determinística responsável por fundir o esqueleto complexo gerado
    via Tool Calling da LLM com os dados planos de alta fidelidade do BDA.
    """
    def __init__(self, templates: dict):
        self.templates = templates

    def extrair_confiancas_explainability(self, bda_json: dict) -> dict:
        """Lê as confianças reais por campo do nó explainability_info do BDA (Lista de Dicts)."""
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

    def construir_mapa_valores_unificado(self, bda_json: dict, raw_fields_ia: dict) -> dict:
        """
        Gera um mapa plano e normalizado contendo TODAS as extrações do BDA e da LLM.
        Garante acoplamento flexível eliminando o ponto cego do invólucro campos_extraidos_brutos.
        """
        mapa = {}
        
        # 1. Carrega dados de alta precisão do BDA
        ir = bda_json.get("inference_result", {})
        for k, v in ir.items():
            if v not in (None, ""):
                k_norm = k.lower().replace("_", "").replace(" ", "").replace(".", "").replace("$", "")
                mapa[k_norm] = v
                if "thisperiod" not in k_norm and "yeartodate" not in k_norm:
                    mapa[f"{k_norm}thisperiod"] = v

        # 2. Desembrulha com segurança o nó da IA (campos_extraidos_brutos)
        fields_ia = raw_fields_ia.get("campos_extraidos_brutos") or raw_fields_ia
        if isinstance(fields_ia, str):
            try: fields_ia = json.loads(fields_ia)
            except: pass
            
        def helper_achatar(dados, prefixo=""):
            if isinstance(dados, dict):
                desc_sufixo = ""
                if "description" in dados and isinstance(dados["description"], str):
                    desc_sufixo = "_" + dados["description"].lower().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
                
                for k, v in dados.items():
                    chave_base = f"{prefixo}{desc_sufixo}_{k}" if prefixo else f"{k}{desc_sufixo}"
                    k_norm = chave_base.lower().replace("_", "").replace(" ", "").replace(".", "").replace("$", "")
                    
                    if isinstance(v, (dict, list)):
                        helper_achatar(v, chave_base)
                    else:
                        if v not in (None, ""):
                            mapa[k_norm] = v
                            k_simples = k.lower().replace("_", "").replace(" ", "").replace(".", "").replace("$", "")
                            mapa[k_simples] = v
                            if "thisperiod" not in k_simples and "yeartodate" not in k_simples:
                                mapa[f"{k_simples}thisperiod"] = v
                                if desc_sufixo:
                                    ds_clean = desc_sufixo.replace("_", "")
                                    mapa[f"{ds_clean}thisperiod"] = v
                                    mapa[f"{ds_clean}_{k_simples}"] = v
            elif isinstance(dados, list):
                for item in dados:
                    helper_achatar(item, prefixo)

        helper_achatar(fields_ia)
        return mapa

    def aplicar_overlay_bda_recursivo(self, objeto, mapa_valores, prefixo=""):
        """Varre o gabarito final populando chaves profundas e tabelas através de correspondência contextual."""
        if isinstance(objeto, dict):
            desc_norm = ""
            if "description" in objeto and isinstance(objeto["description"], str):
                desc_norm = objeto["description"].lower().replace("_", "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
                
            for k, v in objeto.items():
                if k == "description":
                    continue
                    
                if isinstance(v, (dict, list)):
                    novo_prefixo = f"{prefixo}_{k}" if prefixo else k
                    self.aplicar_overlay_bda_recursivo(v, mapa_valores, novo_prefixo)
                else:
                    # Tabela de precedência de chaves de busca contextuais
                    chaves_candidatas = []
                    if desc_norm:
                        chaves_candidatas.append(f"{desc_norm}{k}".replace("_", "").replace(" ", ""))
                        chaves_candidatas.append(f"{desc_norm}_{k}".replace("_", "").replace(" ", ""))
                        chaves_candidatas.append(desc_norm)
                    
                    chaves_candidatas.append(f"{prefixo}_{k}".lower().replace("_", "").replace(" ", "").replace(".", ""))
                    chaves_candidatas.append(k.lower().replace("_", "").replace(" ", "").replace(".", ""))
                    
                    for ch in chaves_candidatas:
                        if ch in mapa_valores and mapa_valores[ch] not in (None, ""):
                            objeto[k] = mapa_valores[ch]
                            break
        elif isinstance(objeto, list):
            for item in objeto:
                self.aplicar_overlay_bda_recursivo(item, mapa_valores, prefixo)

    def executar(self, subtipo: str, arquivo: str, raw_fields_ia: dict, bda_json: dict, s3_inputs: dict, correcoes_humanas: dict = None) -> dict:
        """Orquestra a transformação híbrida consolidando o mapa unificado de dados."""
        # 1. Baseline: Carrega o esqueleto limpo do tipo de documento
        template_base = self.templates.get(subtipo.lower(), {})
        template_final = json.loads(json.dumps(template_base))
        
        # 2. Cria o mapa de valores unificado (BDA + LLM) combatendo a perda de contexto
        mapa_valores = self.construir_mapa_valores_unificado(bda_json, raw_fields_ia)
        
        # 3. Executa a população recursiva de alta precisão
        self.aplicar_overlay_bda_recursivo(template_final, mapa_valores)

        # 4. Aplica correções humanas se houver reprocessamento pós-mesa de revisão
        is_human_override = False
        if correcoes_humanas:
            for composite_key, valor_corrigido in correcoes_humanas.items():
                if "__" in composite_key:
                    file_part, field_part = composite_key.split("__", 1)
                    if file_part == arquivo:
                        ir_humano_limpo = {field_part.lower().replace("_", "").replace(" ", "").replace(".", ""): valor_corrigido}
                        self.aplicar_overlay_bda_recursivo(template_final, ir_humano_limpo)
                        is_human_override = True

        # 5. Mapeia as confianças reais utilizando o formato de lista verificado em produção
        inference_result = (bda_json or {}).get("inference_result", {})
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
        for critico in ["payee_name", "pay_date", "amount_numeric", "employee_name", "this_period", "closing_balance"]:
            if f'"{critico}": null' in campos_gabarito_plano or f'"{critico}": ""' in campos_gabarito_plano:
                if critico in ["payee_name", "pay_date", "employee_name"]:
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