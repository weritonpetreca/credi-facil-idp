import json
import os
import boto3
from datetime import datetime, timezone
from aws_lambda_powertools import Logger

logger = Logger(service="result-writer")
s3_client = boto3.client("s3")
db_client = boto3.client("dynamodb")

TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "credifacil-pacotes-dev")

def handler(event, context):
    try:
        logger.info(f"Gravando resultados consolidados no ecossistema de dados.")
        
        package_id = event.get("package_id")
        json_estruturado = event.get("json_estruturado", {})
        bucket_saida = event.get("bda_output_bucket")
        
        # Caminho definitivo do artefato analítico de negócio no S3
        s3_key_final = f"results/{package_id}/output.json"
        
        logger.info(f"Persistindo JSON estruturado global no S3: s3://{bucket_saida}/{s3_key_final}")
        s3_client.put_object(
            Bucket=bucket_saida,
            Key=s3_key_final,
            Body=json.dumps(json_estruturado, ensure_ascii=False),
            ContentType="application/json"
        )

        timestamp_atual = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        score_data = json_estruturado.get("score_global", {})
        
        # 1. Atualiza o status do processo transacional na tabela de workflows
        logger.info(f"Atualizando estado do workflow transacional para o pacote {package_id}")
        db_client.update_item(
            TableName=TABLE_NAME,
            Key={
                "PK": {"S": package_id},
                "SK": {"S": "METADATA"}
            },
            UpdateExpression="SET #st = :comp, processedAt = :ts, resultS3Key = :s3, confidenceScore = :conf, humanReview = :hr",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":comp": {"S": "COMPLETED"},
                ":ts": {"S": timestamp_atual},
                ":s3": {"S": s3_key_final},
                ":conf": {"N": "0.95"},
                ":hr": {"BOOL": event.get("revisao_humana", False)}
            }
        )

        # 🚀 2. A MAGIA DA TABELA MESTRE: Consolida e salva/atualiza os dados perenes de cada Cliente
        tabela_clientes = json_estruturado.get("tabela_clientes", {})
        
        for nome_cliente, payload_cliente in tabela_clientes.items():
            cadastro = payload_cliente.get("cadastro", {})
            doc_id = cadastro.get("documento_identificacao", "").strip()
            
            if not doc_id or "não localizado" in doc_id.lower():
                logger.warning(f"Ignorando gravação mestre para {nome_cliente} devido a ausência de documento estável.")
                continue
                
            pk_cliente = f"CLIENT#{doc_id}"
            logger.info(f"Persistindo/Atualizando registro perene na tabela mestre de clientes: {pk_cliente}")
            
            # Grava os dados do perfil unificado do cliente. Se ele já existia, atualiza os dados cadastrais
            # e anexa a referência do último pacote de empréstimo processado por ele.
            db_client.put_item(
                TableName=TABLE_NAME,
                Item={
                    "PK": {"S": pk_cliente},
                    "SK": {"S": "PROFILE"},
                    "nome_completo": {"S": cadastro.get("nome")},
                    "documento_identificacao": {"S": doc_id},
                    "data_nascimento": {"S": cadastro.get("data_nascimento") if cadastro.get("data_nascimento") else "Não Informada"},
                    "ultima_atualizacao": {"S": timestamp_atual},
                    "ultimo_package_id": {"S": package_id},
                    "historico_financeiro_sumarizado": {"S": json.dumps(payload_cliente.get("documentos_vinculados", []))}
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