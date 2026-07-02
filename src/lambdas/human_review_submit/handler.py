import json
import os
import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger

logger = Logger(service="human-review-submit")

db_client = boto3.client("dynamodb", region_name="us-east-1")
sfn_client = boto3.client("stepfunctions", region_name="us-east-1")

TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "credifacil-pacotes-dev")

def handler(event, context):
    try:
        logger.info(f"Requisição de revisão recebida do front-end: {json.dumps(event)}")
        
        # Extrai o package_id do path parameters do API Gateway
        path_params = event.get("pathParameters", {}) or {}
        package_id = path_params.get("packageId")
        
        body = json.loads(event.get("body", "{}") or "{}")
        correcoes = body.get("correcoes", {}) # Dados corrigidos pelo operador humano
        
        if not package_id:
            return {"statusCode": 400, "body": json.dumps({"erro": "Parâmetro packageId obrigatório no path."})}

        db_res = db_client.get_item(
            TableName=TABLE_NAME,
            Key={"PK": {"S": package_id}, "SK": {"S": "REVISION"}}
        )
        item = db_res.get("Item")
        
        if not item:
            return {"statusCode": 404, "body": json.dumps({"erro": "Nenhuma revisão pendente localizada para este pacote."})}
            
        task_token = item["task_token"]["S"]

        logger.info(f"Task Token localizado para o pacote {package_id}. Acordando a State Machine.")

        db_client.update_item(
            TableName=TABLE_NAME,
            Key={"PK": {"S": package_id}, "SK": {"S": "REVISION"}},
            UpdateExpression="SET status_revisao = :s, #st = :c, correcoes_humanas = :ch",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":s": {"S": "RESOLVIDO"},
                ":c": {"S": "PROCESSING"},
                ":ch": {"S": json.dumps(correcoes, ensure_ascii=False)}
            }
        )

        output_payload = {
            "status_revisao": "RESOLVIDO",
            "dados_corrigidos": correcoes
        }
        sfn_client.send_task_success(
            taskToken=task_token,
            output=json.dumps(output_payload)
        )        

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"mensagem": "Revisão humana processada. Pipeline reativado com sucesso."})
        }

    except ClientError as e:
        codigo_erro = e.response.get("Error", {}).get("Code")
        if codigo_erro == "TaskDoesNotExist":
            return {"statusCode": 410, "body": json.dumps({"erro": "O tempo limite de revisão expirou ou o token já foi processado."})}
        logger.exception("Erro de comunicação com serviços AWS")
        return {"statusCode": 500, "body": json.dumps({"erro": "Erro de integração na infraestrutura."})}
    except Exception as e:
        logger.exception("Erro não tratado no envio da revisão")
        return {"statusCode": 500, "body": json.dumps({"erro": "Erro interno do servidor."})}