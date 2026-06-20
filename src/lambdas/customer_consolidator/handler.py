import json
import os
import boto3
from aws_lambda_powertools import Logger

logger = Logger(service="customer-consolidator")
s3_client = boto3.client("s3")
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")

def handler(event, context):
    try:
        package_id = event.get("package_id")
        bucket = event.get("bda_output_bucket")
        prefix = f"results/{package_id}/"

        logger.info(f"Iniciando consolidação de score sob demanda para o pacote {package_id}")

        # 1. Lista e agrupa todos os JSONs já estruturados pela Lambda anterior
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        if "Contents" not in response:
            return event

        dossie_textual = ""
        for obj in response["Contents"]:
            if not obj["Key"].endswith("_structured.json"): continue
            raw_data = s3_client.get_object(Bucket=bucket, Key=obj["Key"])["Body"].read().decode("utf-8")
            dossie_textual += f"\n--- DOCUMENTO ---\n{raw_data}\n"

        # 2. Prompt focado exclusivamente em score e validação cruzada
        prompt_consolidacao = f"""
        Você é um analista de risco de crédito sênior. Analise o dossiê de documentos estruturados abaixo e gere um JSON contendo a avaliação do cliente.

        {dossie_textual}

        Retorne EXATAMENTE este formato JSON, sem marcações markdown adicionais:
        {{
          "cliente": {{
            "nome": "NOME COMPLETO EM CAIXA ALTA",
            "documento_identificacao": "NUMERO",
            "score_credito": {{ "valor": 850 }},
            "classificacao_risco": {{ "categoria": "baixo", "justificativa": "Texto" }}
          }},
          "validacao": {{
            "nome_consistente_entre_documentos": true,
            "data_nascimento_consistente": true,
            "documento_identificacao_presente": true,
            "comprovante_renda_presente": true,
            "extrato_bancario_presente": true
          }}
        }}
        """

        # 3. Invoca o Amazon Nova Pro para consolidar a inteligência
        body_request = json.dumps({
            "inferenceConfig": {"temperature": 0.0, "maxTokens": 1000},
            "messages": [{"role": "user", "content": [{"text": prompt_consolidacao}]}]
        })

        bedrock_response = bedrock_runtime.invoke_model(
            modelId="amazon.nova-pro-v1:0",
            contentType="application/json",
            accept="application/json",
            body=body_request
        )

        response_body = json.loads(bedrock_response["body"].read().decode("utf-8"))
        texto_resposta = response_body["output"]["message"]["content"][0]["text"]
        consolidado_json = json.loads(texto_resposta.strip())

        # 4. Salva o arquivo consolidado do cliente no S3 de forma isolada
        s3_client.put_object(
            Bucket=bucket,
            Key=f"results/{package_id}/customer_consolidated.json",
            Body=json.dumps(consolidado_json, ensure_ascii=False),
            ContentType="application/json"
        )

        return event
    except Exception as e:
        logger.error(f"Erro na consolidação: {str(e)}")
        raise e