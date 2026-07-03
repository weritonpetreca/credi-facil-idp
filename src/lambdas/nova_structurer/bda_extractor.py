import json
from aws_lambda_powertools import Logger

logger = Logger(child=True)

class BdaExtractor:
    """
    Camada de infraestrutura de I/O especialista em extrair e unificar as saídas do Amazon BDA.
    Resolve o problema de perda de contexto mapeando simultaneamente a 'standard_output'
    (texto completo e tabelas em markdown) e a 'custom_output' (chaves planas do blueprint).
    """
    def __init__(self, s3_client, bucket_saida: str):
        self.s3_client = s3_client
        self.bucket_saida = bucket_saida

    def extrair_texto_linear(self, dados: any) -> list:
        """Varre recursivamente os nós textuais e tabelas estruturadas do BDA."""
        textos = []
        if isinstance(dados, dict):
            for k, v in dados.items():
                if k in ["text", "textString", "value", "content", "representation"] and isinstance(v, str):
                    if v.strip(): textos.append(v.strip())
                elif k == "markdown" and isinstance(v, str):
                    if v.strip(): textos.append(v.strip())
                else:
                    textos.extend(self.extrair_texto_linear(v))
        elif isinstance(dados, list):
            for item in dados:
                textos.extend(self.extrair_texto_linear(item))
        return textos

    def executar(self, s3_key_custom: str) -> dict:
        """
        Executa a leitura paralela e unifica o contexto do documento.
        Garante que chaves e texto integral coexistam no mesmo payload de domínio.
        """
        logger.info(f"BdaExtractor carregando custom_output: {s3_key_custom}")
        
        # 1. Carrega o payload customizado (Chaves críticas + Metadados de OCR)
        resp_custom = self.s3_client.get_object(Bucket=self.bucket_saida, Key=s3_key_custom)
        json_custom = json.loads(resp_custom["Body"].read().decode("utf-8"))
        
        inference_result = json_custom.get("inference_result", {})
        explainability_info = json_custom.get("explainability_info", {})
        
        # 2. Modula dinamicamente o ponteiro para recuperar a transcrição completa
        texto_integral = ""
        s3_key_standard = s3_key_custom.replace("custom_output", "standard_output")
        
        try:
            logger.info(f"BdaExtractor buscando texto completo na standard_output: {s3_key_standard}")
            resp_standard = self.s3_client.get_object(Bucket=self.bucket_saida, Key=s3_key_standard)
            json_standard = json.loads(resp_standard["Body"].read().decode("utf-8"))
            texto_integral = " ".join(self.extrair_texto_linear(json_standard))
            logger.info("Sucesso: Texto integral e tabelas em Markdown recuperados da standard_output.")
        except self.s3_client.exceptions.NoSuchKey:
            logger.warning("Aviso: standard_output não localizado. Executando fallback para o texto contido no custom_output.")
            texto_integral = " ".join(self.extrair_texto_linear(json_custom))
        except Exception as e:
            logger.error(f"Falha inesperada ao tentar ler a standard_output: {str(e)}")
            texto_integral = " ".join(self.extrair_texto_linear(json_custom))
            
        return {
            "inference_result": inference_result,
            "explainability_info": explainability_info,
            "texto_integral": texto_integral,
            "json_custom_bruto": json_custom
        }