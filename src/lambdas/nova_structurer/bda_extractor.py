import json
from aws_lambda_powertools import Logger

logger = Logger(child=True)


class BdaExtractor:
    """
    Camada de I/O que lê e unifica os dois outputs do Amazon Bedrock Data Automation.

    O BDA gera DOIS arquivos para cada documento processado:
    ┌─ custom_output/0/result.json  → campos do blueprint com confidence por campo
    └─ standard_output/0/result.json → documento completo em Markdown estruturado

    Analogia Java: imagine dois ResultSets do mesmo banco.
    O custom_output é como uma query SELECT especializada (apenas os campos críticos).
    O standard_output é como SELECT * (tudo, incluindo as tabelas formatadas).

    CORREÇÃO CENTRAL (v2 — 03/07/2026):
    Versões anteriores usavam `extrair_texto_linear()` na standard_output, que
    destrói a estrutura de tabelas. Por exemplo, a linha da tabela:
      | Regular | 10.00 | 32.00 | 320.00 | 16,640.00 |
    virava o texto: "Regular 10.00 32.00 320.00 16640.00"

    O Nova Lite recebia esse texto e não conseguia saber qual número era rate,
    qual era hours, qual era this_period — e deixava tudo null.

    Com o markdown preservado, o Nova Lite lê a tabela completa e preenche
    corretamente cada coluna de cada linha.
    """

    def __init__(self, s3_client, bucket_saida: str):
        self.s3_client = s3_client
        self.bucket_saida = bucket_saida

    def extrair_texto_linear(self, dados: any) -> list:
        """
        Fallback: varre recursivamente nós textuais quando não há markdown disponível.
        Usado APENAS quando a standard_output não existe ou não tem páginas estruturadas.
        """
        textos = []
        if isinstance(dados, dict):
            for k, v in dados.items():
                if k in ["text", "textString", "value", "content"] and isinstance(v, str):
                    if v.strip():
                        textos.append(v.strip())
                elif k == "markdown" and isinstance(v, str):
                    if v.strip():
                        textos.append(v.strip())
                else:
                    textos.extend(self.extrair_texto_linear(v))
        elif isinstance(dados, list):
            for item in dados:
                textos.extend(self.extrair_texto_linear(item))
        return textos

    def executar(self, s3_key_custom: str) -> dict:
        """
        Carrega o custom_output (campos críticos + confidence) e o markdown completo
        da standard_output (tabelas de earnings, deductions, etc.) para o Nova Lite.

        Retorna um dicionário com:
        - inference_result: {campo: valor_string} — os 13 campos do blueprint
        - explainability_info: lista com confidence por campo
        - texto_integral: markdown completo do documento (com tabelas preservadas!)
        - json_custom_bruto: JSON completo do custom_output (para o SchemaTransformer)
        """
        logger.info(f"BdaExtractor carregando custom_output: {s3_key_custom}")

        # ── 1. Custom output: campos críticos com confidence ──────────────────
        resp_custom = self.s3_client.get_object(Bucket=self.bucket_saida, Key=s3_key_custom)
        json_custom = json.loads(resp_custom["Body"].read().decode("utf-8"))

        inference_result = json_custom.get("inference_result", {})
        explainability_info = json_custom.get("explainability_info", [])

        logger.info(
            f"inference_result carregado: {len(inference_result)} campos do blueprint. "
            f"Campos: {list(inference_result.keys())}"
        )

        # ── 2. Standard output: markdown completo com tabelas preservadas ─────
        # O path da standard_output é idêntico ao do custom_output,
        # apenas substituindo "custom_output" por "standard_output".
        # Exemplo:
        #   custom: bda-output/{pkg}/{doc}/{job_id}/custom_output/0/result.json
        #   standard: bda-output/{pkg}/{doc}/{job_id}/standard_output/0/result.json
        texto_integral = ""
        s3_key_standard = s3_key_custom.replace("custom_output", "standard_output")

        try:
            logger.info(f"BdaExtractor buscando markdown completo na standard_output: {s3_key_standard}")
            resp_standard = self.s3_client.get_object(Bucket=self.bucket_saida, Key=s3_key_standard)
            json_standard = json.loads(resp_standard["Body"].read().decode("utf-8"))

            # ╔══════════════════════════════════════════════════════════════════╗
            # ║  CORREÇÃO CENTRAL: ler o markdown das pages, NÃO linearizar!    ║
            # ║                                                                  ║
            # ║  json_standard["pages"][0]["representation"]["markdown"] contém  ║
            # ║  o documento inteiro formatado com tabelas Markdown, por ex.:   ║
            # ║                                                                  ║
            # ║  | Earnings | rate  | hours | this period | year to date |       ║
            # ║  |----------|-------|-------|-------------|--------------|        ║
            # ║  | Regular  | 10.00 | 32.00 | 320.00      | 16,640.00    |       ║
            # ║                                                                  ║
            # ║  O Nova Lite LÊ essa tabela e sabe que rate=10.00, hours=32.00  ║
            # ║  — elimina os nulls nas linhas de earnings e deductions.         ║
            # ╚══════════════════════════════════════════════════════════════════╝
            pages = json_standard.get("pages", [])
            if pages:
                texto_integral = pages[0].get("representation", {}).get("markdown", "")

            if texto_integral:
                logger.info(
                    f"Markdown estruturado carregado com sucesso: {len(texto_integral)} caracteres. "
                    f"Tabelas preservadas para o Nova Lite."
                )
            else:
                # Fallback: standard_output existe mas sem markdown nas pages
                logger.warning("Pages sem markdown na standard_output. Usando fallback de extração linear.")
                texto_integral = " ".join(self.extrair_texto_linear(json_standard))

        except self.s3_client.exceptions.NoSuchKey:
            # Standard_output não existe: usa o texto que o custom_output tem
            logger.warning(
                "standard_output não localizado no S3. "
                "Executando fallback para texto do custom_output. "
                "Campos de tabelas (earnings, deductions) podem ter nulls."
            )
            texto_integral = " ".join(self.extrair_texto_linear(json_custom))

        except Exception as e:
            logger.error(f"Falha inesperada ao carregar standard_output: {str(e)}. Usando fallback.")
            texto_integral = " ".join(self.extrair_texto_linear(json_custom))

        return {
            "inference_result": inference_result,
            "explainability_info": explainability_info,
            "texto_integral": texto_integral,
            "json_custom_bruto": json_custom,
        }