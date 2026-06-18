import json
import os
import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger

logger = Logger(service="notification")

# Inicialização do cliente SNS fora do handler para reaproveitamento de conexões
sns_client = boto3.client("sns")

# ARNs dos tópicos injetados dinamicamente pelo AWS SAM
TOPIC_CONCLUSAO = os.environ.get("SNS_COMPLETION_TOPIC_ARN", "arn:aws:sns:us-east-1:123456789012:credifacil-conclusao-dev")
TOPIC_ERROS = os.environ.get("SNS_ERROR_TOPIC_ARN", "arn:aws:sns:us-east-1:123456789012:credifacil-erros-dev")

def handler(event, context):
    try:
        logger.info(f"Evento bruto recebido na notificação: {json.dumps(event)}")
        
        # 🔍 DEFESA DE CONTRATO: Desembrulha o payload se vier do output do ResultWriter
        if "body" in event and isinstance(event["body"], str):
            try:
                corpo_interno = json.loads(event["body"])
                if isinstance(corpo_interno, dict):
                    event = {**event, **corpo_interno}
            except Exception:
                logger.warning("Falha ao tentar processar o sub-campo 'body' do evento.")

        package_id = event.get("package_id")
        
        # 🔄 MAPEAMENTO DINÂMICO DE STATUS: Aceita tanto 'execution_status' quanto 'status'
        status_bruto = event.get("execution_status") or event.get("status")
        
        tipo_evento = None
        if status_bruto:
            status_upper = str(status_bruto).upper()
            if status_upper in ["SUCCESS", "COMPLETED"]:
                tipo_evento = "SUCCESS"
            elif status_upper in ["FAILED", "ERROR"]:
                tipo_evento = "ERROR"

        # Validação do contrato higienizado
        if not package_id or not tipo_evento:
            raise ValueError(f"Contrato inválido. package_id ({package_id}) ou status ({status_bruto}) ilegíveis.")

        if tipo_evento == "SUCCESS":
            mensagem = {
                "default": f"Solicitação de crédito {package_id} processada com sucesso pela IA. Dados estruturados disponíveis para análise.",
                "package_id": package_id,
                "status": "COMPLETED"
            }
            topic_arn = TOPIC_CONCLUSAO
            assunto = f"✨ [CrediFácil IDP] Processamento Concluído - {package_id}"
            
        else:
            detalhe_erro = event.get("error_message", "Erro interno não mapeado no workflow.")
            mensagem = {
                "default": f"ALERTA CRÍTICO: O pipeline serverless falhou ao processar o pacote {package_id}.",
                "package_id": package_id,
                "status": "FAILED",
                "motivo": detalhe_erro
            }
            topic_arn = TOPIC_ERROS
            assunto = f"🚨 [ALERTA ADMIN] Falha no Pipeline IDP - {package_id}"

        logger.info(f"Publicando notificação de {tipo_evento} para o pacote {package_id} no SNS.")

        # Publicação no Amazon SNS aplicando formatação JSON estruturada
        sns_client.publish(
            TopicArn=topic_arn,
            Message=json.dumps(mensagem, ensure_ascii=False),
            Subject=assunto
        )
        
        return {
            "statusCode": 200,
            "body": json.dumps({"mensagem": f"Notificação de {tipo_evento} enviada com sucesso."})
        }

    except ClientError as e:
        logger.error(f"Erro do SDK ao publicar mensagem no Amazon SNS: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"erro": "Falha ao disparar o serviço de mensageria."})}
    except Exception as e:
        logger.error(f"Erro inesperado na Lambda de notificação: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"erro": "Erro interno de processamento."})}