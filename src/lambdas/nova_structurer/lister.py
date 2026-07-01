import json
import os
import boto3
from aws_lambda_powertools import Logger

logger = Logger(service="nova-document-lister")
s3_client = boto3.client("s3", region_name="us-east-1")
db_client = boto3.client("dynamodb", region_name="us-east-1")

TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "credifacil-pacotes-dev")

def handler(event, context):
    try:
        package_id = event.get("package_id")
        bucket_saida = event.get("bda_output_bucket") or os.environ.get("BUCKET_SAIDA")
        prefix_busca = f"bda-output/{package_id}/"

        logger.info(f"Listando outputs do BDA para mapeamento do MAP State no lote: {package_id}")

        # Sincronização offline de metadados para evitar spam de GetItem no Map
        execute_score = False
        user_id = "sistema"
        try:
            db_res = db_client.get_item(
                TableName=TABLE_NAME,
                Key={"PK": {"S": package_id}, "SK": {"S": "METADATA"}}
            )
            item_db = db_res.get("Item", {})
            execute_score = item_db.get("execute_score", {}).get("BOOL", False)
            user_id = item_db.get("uploadedBy", {}).get("S", "sistema")
        except Exception as db_err:
            logger.warning(f"Falha de barreira ao ler DynamoDB, usando defaults: {str(db_err)}")
            execute_score = event.get("execute_score", False)
            user_id = event.get("user_id", "sistema")

        s3_objects = s3_client.list_objects_v2(Bucket=bucket_saida, Prefix=prefix_busca)
        if "Contents" not in s3_objects or len(s3_objects["Contents"]) == 0:
            raise FileNotFoundError(f"Nenhum arquivo BDA localizado sob o prefixo {prefix_busca}")

        mapa_documentos = {}
        for obj in s3_objects["Contents"]:
            key = obj["Key"]
            if not key.endswith(".json") or "manifest" in key.lower() or "job_metadata" in key.lower():
                continue
            partes = key.split("/")
            if len(partes) < 3: continue
            nome_pdf_original = partes[2]
            
            if nome_pdf_original not in mapa_documentos: 
                mapa_documentos[nome_pdf_original] = []
            mapa_documentos[nome_pdf_original].append(obj)

        documentos_para_estruturar = []
        for nome_pdf_original, lista_objetos in mapa_documentos.items():
            obj_selecionado = next((o for o in lista_objetos if "custom_output" in o["Key"]), None)
            if not obj_selecionado:
                obj_selecionado = next((o for o in lista_objetos if "standard_output" in o["Key"]), lista_objetos[0])

            documentos_para_estruturar.append({
                "package_id": package_id,
                "bda_output_bucket": bucket_saida,
                "nome_pdf_original": nome_pdf_original,
                "s3_key_bda": obj_selecionado["Key"]
            })

        return {
            "package_id": package_id,
            "user_id": user_id,
            "execute_score": execute_score,
            "bda_output_bucket": bucket_saida,
            "documentos_para_estruturar": documentos_para_estruturar
        }
    except Exception as e:
        logger.error(f"Falha na listagem preparatória do Map: {str(e)}")
        raise e