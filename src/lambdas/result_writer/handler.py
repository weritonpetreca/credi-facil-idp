import json
import os
import boto3
from datetime import datetime, timezone
from aws_lambda_powertools import Logger

logger = Logger(service="result-writer")
s3_client = boto3.client("s3")
db_client = boto3.client("dynamodb")

# Tabelas separadas injetadas via variáveis globais do template.yaml
TABLE_TRANSACOES = os.environ.get("DYNAMODB_TABLE", "credifacil-pacotes-dev")
TABLE_CLIENTES_MESTRE = os.environ.get("CLIENTS_DYNAMODB_TABLE", "credifacil-clientes-dev")

def handler(event, context):
    try:
        package_id = event.get("package_id")
        json_estruturado = event.get("json_estruturado", {})
        metricas = event.get("metricas_consumo", {})
        
        # 🚀 CONTINGÊNCIA ATIVADA: Se o evento vier vazio devido ao redrive, o os.environ salva o deploy!
        bucket_saida = event.get("bda_output_bucket") or os.environ.get("BUCKET_SAIDA")
        
        if not bucket_saida:
            raise ValueError("O nome do bucket de saída não pôde ser resolvido via payload ou ambiente.")
            
        s3_key_final = f"results/{package_id}/output.json"
        
        logger.info(f"Salvando artefato completo no S3: s3://{bucket_saida}/{s3_key_final}")
        s3_client.put_object(
            Bucket=bucket_saida,
            Key=s3_key_final,
            Body=json.dumps(json_estruturado, ensure_ascii=False),
            ContentType="application/json"
        )

        timestamp_atual = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        score_data = json_estruturado.get("score_global", {})
        confianca_real = str(event.get("confianca_geral", 0.90))
        
        # 1. ESCRITA NA TABELA DE WORKFLOW (Apenas metadados da execução)
        logger.info(f"Atualizando a tabela de transações do workflow: {TABLE_TRANSACOES}")
        db_client.update_item(
            TableName=TABLE_TRANSACOES,
            Key={
                "PK": {"S": package_id},
                "SK": {"S": "METADATA"}
            },
            UpdateExpression="SET #st = :comp, processedAt = :ts, resultS3Key = :s3, confidenceScore = :conf, humanReview = :hr, tokens_consumidos = :tok",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":comp": {"S": "COMPLETED"},
                ":ts": {"S": timestamp_atual},
                ":s3": {"S": s3_key_final},
                ":conf": {"N": confianca_real},
                ":hr": {"BOOL": event.get("revisao_humana", False)},
                ":tok": {"S": f"In: {metricas.get('input_tokens', 0)} | Out: {metricas.get('output_tokens', 0)}"}
            }
        )

        # 2. ESCRITA NA TABELA EXCLUSIVA DE CLIENTES MESTRE (Perene e Acumulativa)
        tabela_clientes = json_estruturado.get("tabela_clientes", {})
        for nome_cliente, payload_cliente in tabela_clientes.items():
            cadastro = payload_cliente.get("cadastro", {})
            doc_id = cadastro.get("documento_identificacao", "").strip()
            
            if not doc_id or "não localizado" in doc_id.lower():
                logger.warning(f"Ignorando atualização mestre para {nome_cliente}: Ausência de ID estável.")
                continue
                
            pk_cliente = f"CLIENT#{doc_id}"
            logger.info(f"Atualizando cadastro mestre isolado na tabela {TABLE_CLIENTES_MESTRE} para: {pk_cliente}")
            
            db_client.put_item(
                TableName=TABLE_CLIENTES_MESTRE,
                Item={
                    "PK": {"S": pk_cliente},
                    "nome_completo": {"S": cadastro.get("nome")},
                    "documento_identificacao": {"S": doc_id},
                    "data_nascimento": {"S": str(cadastro.get("data_nascimento") or "Não Informada")},
                    "score_atribuido": {"N": str(score_data.get("pontuacao", 0))},
                    "classificacao_risco": {"S": score_data.get("classificacao_risco", "UNKNOWN")},
                    "justificativa_analise": {"S": score_data.get("justificativa", "")},
                    "ultimo_package_vinculado": {"S": package_id},
                    "data_ultima_atualizacao": {"S": timestamp_atual},
                    "documentos_historico_json": {"S": json.dumps(payload_cliente.get("documentos_vinculados", []))}
                }
            )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "package_id": package_id,
                "status": "COMPLETED",
                "s3_path": f"s3://{bucket_saida}/{s3_key_final}"
            })
        }

    except Exception as e:
        logger.error(f"Falha ao persistir dados na camada de escrita: {str(e)}")
        raise e