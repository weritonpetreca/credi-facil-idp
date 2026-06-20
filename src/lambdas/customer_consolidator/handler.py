import json
import os
import boto3
from aws_lambda_powertools import Logger

logger = Logger(service="customer-consolidator")
s3_client = boto3.client("s3")
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")

def handler(event, context):
    """Handler AWS Lambda focado exclusivamente na consolidação e cálculo de Score do Proponente."""
    try:
        package_id = event.get("package_id")
        bucket = event.get("bda_output_bucket") or os.environ.get("BUCKET_SAIDA")
        
        logger.info(f"Iniciando consolidação analítica de score sob demanda para o pacote {package_id}")

        # 🚀 OTIMIZAÇÃO: Lê a malha de dados diretamente da memória do Step Functions (Zero I/O no S3)
        json_base_lote = event.get("json_estruturado")
        
        # Fallback de segurança caso a memória venha limpa por concorrência externa
        if not json_base_lote:
            logger.warning("Linha de base não localizada em memória. Recorrendo ao S3...")
            key_base = f"results/packages/{package_id}/output.json"
            s3_response = s3_client.get_object(Bucket=bucket, Key=key_base)
            json_base_lote = json.loads(s3_response["Body"].read().decode("utf-8"))

        # Reduz o consumo de tokens enviando apenas o array estruturado de documentos analisados
        docs_analisados = json_base_lote.get("documentos_analisados", [])
        dossie_textual = json.dumps(docs_analisados, ensure_ascii=False)

        # 2. Prompt corporativo sênior focado estritamente em cruzamento de dados e subscrição de risco
        prompt_consolidacao = f"""
        Você é um analista sênior de risco de crédito. Analise o dossiê de documentos estruturados abaixo para realizar a validação cadastral cruzada e calcular o score de crédito do proponente mestre.

        Dossiê de Documentos Estruturados:
        {dossie_textual}

        DIRETRIZES DE CRÉDITO OBRIGATÓRIAS:
        - Mapeie o nome completo e documento civil do proponente baseado nos documentos de identificação oficiais mais confiáveis (ex: Driver License).
        - Calcule o 'score_credito' consolidado variando estritamente entre 0 e 1000 com base na solidez financeira, estabilidade empregatícia e liquidez salarial evidenciadas nos extratos e holerites.
        - Classifique a categoria de risco em 'baixo', 'medio' ou 'alto', fornecendo uma justificativa técnica sucinta e fundamentada na saúde patrimonial e financeira demonstrada.
        - Valide os booleanos de consistência cadastral verificando correspondência exata de nomes e datas de nascimento entre todos os papéis fornecidos, além da presença de comprovantes essenciais.

        Retorne RIGOROSAMENTE o formato JSON plano abaixo, sem tags markdown (como ```json) ou qualquer texto complementar explicativo antes ou depois:
        {{
          "cliente": {{
            "nome": "NOME COMPLETO EM CAIXA ALTA",
            "documento_identificacao": "NUMERO",
            "score_credito": {{ "valor": 750 }},
            "classificacao_risco": {{ "categoria": "baixo", "justificativa": "Texto analítico base do parecer de crédito." }}
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

        body_request = json.dumps({
            "inferenceConfig": {"temperature": 0.0, "maxTokens": 1500},
            "messages": [{"role": "user", "content": [{"text": prompt_consolidacao}]}]
        })

        # 3. Invoca o Amazon Nova Pro para agregar inteligência aos metadados
        logger.info(f"Invocando o motor Amazon Nova Pro para o lote {package_id}")
        bedrock_response = bedrock_runtime.invoke_model(
            modelId="amazon.nova-pro-v1:0",
            contentType="application/json",
            accept="application/json",
            body=body_request
        )

        response_body = json.loads(bedrock_response["body"].read().decode("utf-8"))
        texto_resposta = response_body["output"]["message"]["content"][0]["text"].strip()
        
        if texto_resposta.startswith("```json"):
            texto_resposta = texto_resposta.split("```json")[1].split("```")[0].strip()
        elif texto_resposta.startswith("```"):
            texto_resposta = texto_resposta.split("```")[1].split("```")[0].strip()

        consolidado_json = json.loads(texto_resposta)

        # 4. Enriquecimento da malha de dados em memória
        json_base_lote["cliente"] = consolidado_json.get("cliente")
        json_base_lote["validacao"] = consolidado_json.get("validacao")

        # 🎯 5. GOVERNANÇA HIERÁRQUICA: Organiza a pasta de clientes para nascer dentro de results/
        s3_target_key = f"results/clientes/{package_id}/customer_consolidated.json"
        logger.info(f"Gravando arquivo mestre único do cliente em: {s3_target_key}")
        
        s3_client.put_object(
            Bucket=bucket,
            Key=s3_target_key,
            Body=json.dumps(json_base_lote, ensure_ascii=False),
            ContentType="application/json"
        )

        # ❌ INVOCACÃO DUPLICADA REMOVIDA DAQUI (Não sobrescreve mais o results/{package_id}/output.json)

        # 6. Retorna o payload enriquecido. Toda a persistência em Banco fica trancada no ResultWriter (DRY)
        return {
            **event,
            "cliente": consolidado_json.get("cliente"),
            "validacao": consolidado_json.get("validacao"),
            "json_estruturado": json_base_lote
        }

    except Exception as e:
        logger.error(f"Falha crítica na esteira de consolidação cadastral: {str(e)}")
        raise e