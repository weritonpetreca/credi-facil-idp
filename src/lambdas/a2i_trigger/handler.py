import json
import os
import uuid
import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger

logger = Logger(service="a2i-trigger")

# Inicialização do cliente de Runtime do SageMaker A2I
a2i_client = boto3.client("sagemaker-a2i-runtime")

# ARN do Flow Definition do A2I criado via console ou IaC
FLOW_DEFINITION_ARN = os.environ.get("A2I_FLOW_DEFINITION_ARN", "arn:aws:sagemaker:us-east-1:123456789012:flow-definition/credifacil-human-review")

def handler(event, context):
    try:
        package_id = event.get("package_id")
        user_id = event.get("user_id", "sistema")
        bda_output_bucket = event.get("bda_output_bucket")
        bda_output_key = event.get("bda_output_key")

        logger.info(f"Iniciando Loop de Revisão Humana no A2I para o pacote {package_id}")

        # Payload de entrada que o operador humano vai visualizar na tela (task_template.html)
        input_content = {
            "task": {
                "input": {
                    "package_id": package_id,
                    "uploaded_by": user_id,
                    "extractedFields": {
                        "nome": {"value": "Verificar no PDF"},
                        "cpf": {"value": "Verificar no PDF"},
                        "data_nascimento": {"value": "Verificar no PDF"}
                    }
                }
            }
        }

        # Criação do laço de auditoria humana de forma assíncrona
        human_loop_name = f"loop-{package_id}-{str(uuid.uuid4())[:8]}"
        response = a2i_client.start_human_loop(
            HumanLoopName=human_loop_name,
            FlowDefinitionArn=FLOW_DEFINITION_ARN,
            InputContent={"InputContent": json.dumps(input_content)},
            DataAttributes={"ContentClassifiers": ["FreeOfPersonallyIdentifiableInformation"]}
        )

        logger.info(f"Loop Humano {human_loop_name} criado com sucesso. ARN: {response['HumanLoopArn']}")

        # Repassa o estado atualizado para a próxima Lambda (Nova Structurer) saber que houve alteração humana
        event["revisao_humana"] = True
        event["human_loop_arn"] = response["HumanLoopArn"]
        return event

    except ClientError as e:
        logger.error(f"Falha ao acionar a API do SageMaker A2I: {str(e)}")
        raise e