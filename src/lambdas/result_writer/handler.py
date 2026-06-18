import json
import os
import boto3
from datetime import datetime
from aws_lambda_powertools import Logger

logger = Logger(service="result-writer")
db_client = boto3.client("dynamodb", region_name="us-east-1")

TABLE_PACOTES = os.environ.get("DYNAMODB_TABLE", "credifacil-pacotes-dev")
TABLE_CLIENTES = os.environ.get("CLIENTS_DYNAMODB_TABLE", "credifacil-clientes-dev")

def handler(event, context):
    try:
        logger.info(f"Payload de escrita recebido: {json.dumps(event)}")
        
        package_id = event.get("package_id")
        json_estruturado = event.get("json_estruturado", {})
        score_global = json_estruturado.get("score_global", {})
        tabela_clientes = json_estruturado.get("tabela_clientes", {})
        
        timestamp_atual = datetime.utcnow().isoformat() + "Z"
        
        # 1. Atualização do log transacional do Pacote
        # 🚀 CORREÇÃO CIRÚRGICA: Devolvido "SK": "METADATA" para casar com o schema composto do template.yaml
        db_client.update_item(
            TableName=TABLE_PACOTES,
            Key={
                "PK": {"S": package_id},
                "SK": {"S": "METADATA"}
            },
            UpdateExpression="SET #st = :comp, processedAt = :ts",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":comp": {"S": "COMPLETED"},
                ":ts": {"S": timestamp_atual}
            }
        )
        
        # 2. Persistência Isolada por Proponente (Multi-entity Architecture)
        logger.info(f"Iniciando gravação de {len(tabela_clientes)} proponentes de forma segregada.")
        
        for nome_cliente, dados in tabela_clientes.items():
            cadastro = dados.get("cadastro", {})
            doc_id = str(cadastro.get("documento_identificacao", "")).strip()
            
            # Fallback de PK dinâmica para garantir a criação da linha mesmo sem ID
            if not doc_id or "não localizado" in doc_id.lower():
                pk_cliente = f"CLIENT#{nome_cliente.replace(' ', '_')}"
                doc_id_salvar = "Não Informado"
            else:
                pk_cliente = f"CLIENT#{doc_id}"
                doc_id_salvar = doc_id

            # Mapeamento dinâmico de scores isolados gerados pelo estruturador
            score_individuo = dados.get("score_atribuido", score_global.get("pontuacao", 0))
            justificativa_individuo = dados.get("justificativa_individual", score_global.get("justificativa", ""))
            risco_individuo = "LOW_RISK" if score_individuo >= 80 else ("MEDIUM_RISK" if score_individuo >= 50 else "HIGH_RISK")

            logger.info(f"Gravando proponente mestre: {nome_cliente} com a PK: {pk_cliente}")
            
            db_client.put_item(
                TableName=TABLE_CLIENTES,
                Item={
                    "PK": {"S": pk_cliente}, # Tabela de clientes usa chave simples PK apenas
                    "nome_completo": {"S": nome_cliente},
                    "documento_identificacao": {"S": doc_id_salvar},
                    "data_nascimento": {"S": cadastro.get("data_nascimento") or "Não Informada"},
                    "score_atribuido": {"N": str(score_individuo)},
                    "classificacao_risco": {"S": risco_individuo},
                    "justificativa_analise": {"S": justificativa_individuo},
                    "documentos_historico_json": {"S": json.dumps(dados.get("documentos_vinculados", []), default=str)},
                    "ultimo_package_vinculado": {"S": package_id},
                    "data_ultima_atualizacao": {"S": timestamp_atual}
                }
            )
            
        return {
            "statusCode": 200,
            "body": json.dumps({
                "package_id": package_id,
                "status": "COMPLETED",
                "total_proponentes": len(tabela_clientes)
            })
        }
        
    except Exception as e:
        logger.error(f"Erro ao persistir na camada de escrita: {str(e)}")
        raise e