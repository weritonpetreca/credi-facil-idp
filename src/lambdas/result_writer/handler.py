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
        
        timestamp_atual = datetime.utcnow().isoformat() + "Z"
        s3_key_final = f"results/{package_id}/output.json"
        
        try:
            confianca_lote = str(float(event.get("confianca_geral", 1.0)))
        except (ValueError, TypeError):
            confianca_lote = "1.0"
            
        decisao_lote = str(event.get("decisao_sugerida") or "revisar")
        
        # 🚀 CORREÇÃO CIRÚRGICA: Mapeamento de tokens ajustado para ler o nó interno em conformidade com o novo JSON mestre
        proc_data = json_estruturado.get("sistema", {}).get("processamento", {})
        tokens_data = proc_data.get("quantidade_tokens", {})
        total_tokens = tokens_data.get("total_tokens", 0)
        tokens_uso = f"{total_tokens} tokens"
        
        # 1. Atualização mestre da tabela de Pacotes contendo volumetria real calculada
        db_client.update_item(
            TableName=TABLE_PACOTES,
            Key={
                "PK": {"S": package_id},
                "SK": {"S": "METADATA"}
            },
            UpdateExpression="SET #st = :comp, processedAt = :ts, resultS3Key = :s3k, confidenceScore = :cs, tokens_consumidos = :tk, decisaoSugerida = :ds",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":comp": {"S": "COMPLETED"},
                ":ts": {"S": timestamp_atual},
                ":s3k": {"S": s3_key_final},
                ":cs": {"N": confianca_lote},
                ":tk": {"S": tokens_uso}, # Persistindo volumetria real com sucesso!
                ":ds": {"S": decisao_lote}
            }
        )
        
        # 2. Persistência Alinhada ao Novo Schema de Cliente Único
        cliente_data = json_estruturado.get("cliente", {})
        sistema_data = json_estruturado.get("sistema", {})
        
        nome_cliente = cliente_data.get("nome", "Não Identificado")
        pk_cliente = sistema_data.get("chave_cliente")
        
        if not pk_cliente or "UNKNOWN" in pk_cliente:
            pk_cliente = f"CLIENT#{nome_cliente.replace(' ', '_')}"
            
        doc_id_salvar = "Não Informado"
        docs_id_list = cliente_data.get("documentos_identificacao", [])
        if docs_id_list and isinstance(docs_id_list, list):
            doc_id_salvar = docs_id_list[0].get("numero_documento") or "Não Informado"

        score_individuo = cliente_data.get("score_credito", {}).get("valor", 0)
        risco_data = cliente_data.get("classificacao_risco", {})
        risco_individuo = risco_data.get("categoria", "inconclusivo")
        justificativa_individuo = risco_data.get("justificativa", "Sem justificativa cadastrada.")
        
        logger.info(f"Gravando cliente único no banco: {nome_cliente} com a PK: {pk_cliente}")
        
        db_client.put_item(
            TableName=TABLE_CLIENTES,
            Item={
                "PK": {"S": pk_cliente},
                "nome_completo": {"S": nome_cliente},
                "documento_identificacao": {"S": str(doc_id_salvar)},
                "data_nascimento": {"S": cliente_data.get("data_nascimento") or "Não Informada"},
                "score_atribuido": {"N": str(score_individuo)},
                "classificacao_risco": {"S": str(risco_individuo).upper() + "_RISK" if risco_individuo in ["baixo", "medio", "alto"] else "UNKNOWN_RISK"},
                "justificativa_analise": {"S": justificativa_individuo},
                "documentos_historico_json": {"S": json.dumps(json_estruturado.get("documentos_analisados", []), default=str)},
                "ultimo_package_vinculado": {"S": package_id},
                "data_ultima_atualizacao": {"S": timestamp_atual}
            }
        )
            
        return {
            "statusCode": 200,
            "body": json.dumps({
                "package_id": package_id,
                "status": "COMPLETED",
                "total_proponentes": 1
            })
        }
        
    except Exception as e:
        logger.error(f"Erro ao persistir na camada de escrita: {str(e)}")
        raise e