import json
import os
import boto3
from datetime import datetime, timezone
from aws_lambda_powertools import Logger, Metrics

logger = Logger(service="nova-batch-aggregator")
metrics = Metrics(namespace="CrediFacilIDP", service="nova-batch-aggregator")
s3_client = boto3.client("s3", region_name="us-east-1")

def inicializar_estrutura_base_lote(package_id: str, intermediarios: list, metricas_tokens: dict) -> dict:
    timestamp_atual = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    documentos_analisados = []
    presenca = {"identificacao": False, "renda": False, "extrato": False, "imovel": False}

    for item in intermediarios:
        bp = item["blueprint"]
        tipo = bp["tipo_documento"]
        
        if tipo == "documento_identificacao": presenca["identificacao"] = True
        elif tipo == "comprovante_renda": presenca["renda"] = True
        elif tipo == "extrato_bancario": presenca["extrato"] = True
        elif tipo == "documento_imovel": presenca["imovel"] = True

        documentos_analisados.append({
            "tipo_documento": tipo.upper(),
            "subtipo_documento": bp.get("subtipo_documento", ""),
            "arquivo_original": bp["arquivo_original"],
            "s3_key_origem": bp["localizacao_documento_s3"]["s3_key_origem"],
            "s3_key_resultado_bda": bp["localizacao_documento_s3"]["s3_key_resultado_bda"],
            "s3_key_resultado": bp["localizacao_documento_s3"].get("s3_key_resultado"),
            "status_extracao": bp["confiabilidade_extracao"]["status_extracao"],
            "campos_extraidos": bp["dados_extraidos_do_documento"],
            "confianca_media": float(bp["confiabilidade_extracao"]["confianca_media"]),
            "observacoes": bp["confiabilidade_extracao"]["observacoes"]
        })

    return {
        "sistema": {
            "ultimo_package_vinculado": {
                "package_id": package_id,
                "client_folder": f"packages/{package_id}/",
                "data_recebimento": timestamp_atual
            },
            "processamento": {
                "status": "processado",
                "modelo_utilizado": "Amazon Nova Lite",
                "bda_project_arn": os.environ.get("BDA_PROJECT_ARN"),
                "quantidade_tokens": {
                    "input_tokens": metricas_tokens["input"],
                    "output_tokens": metricas_tokens["output"],
                    "total_tokens": metricas_tokens["input"] + metricas_tokens["output"]
                },
                "data_processamento": timestamp_atual
            },
            "tipos_documentos_analisados": [k for k, v in presenca.items() if v]
        },
        "documentos_analisados": documentos_analisados
    }

@metrics.log_metrics(capture_cold_start=True)
def handler(event, context):
    try:
        package_id = event.get("package_id")
        user_id = event.get("user_id", "sistema")
        execute_score = event.get("execute_score", False)
        bucket_saida = event.get("bda_output_bucket") or os.environ.get("BUCKET_SAIDA")
        map_results = event.get("map_results", [])

        logger.info(f"Agregando resultados do Map State para o pacote {package_id}")

        intermediarios_coletados = []
        total_input_tokens = 0
        total_output_tokens = 0

        for res in map_results:
            if not res or "blueprint" not in res: continue
            intermediarios_coletados.append({
                "blueprint": res["blueprint"],
                "raw_ia": res["raw_ia"]
            })
            total_input_tokens += res.get("input_tokens", 0)
            total_output_tokens += res.get("output_tokens", 0)

        metricas = {"input": total_input_tokens, "output": total_output_tokens}
        json_base_lote = inicializar_estrutura_base_lote(package_id, intermediarios_coletados, metricas)

        # 🚀 EMF METRICS CONSOLIDADAS
        metrics.add_metric(name="BedrockInputTokens", unit="Count", value=total_input_tokens)
        metrics.add_metric(name="BedrockOutputTokens", unit="Count", value=total_output_tokens)
        
        custo_estimado_usd = ((total_input_tokens * 0.06) + (total_output_tokens * 0.24)) / 1000000
        metrics.add_metric(name="EstimatedGenAiCostUSD", unit="None", value=custo_estimado_usd)
        metrics.add_metadata(key="package_id", value=package_id)

        if not execute_score:
            logger.info(f"Gate de Score inativo. Gravando output.json em results/packages/{package_id}/")
            s3_client.put_object(
                Bucket=bucket_saida, Key=f"results/packages/{package_id}/output.json",
                Body=json.dumps(json_base_lote, ensure_ascii=False), ContentType="application/json"
            )

        return {
            "package_id": package_id,
            "user_id": user_id,
            "execute_score": execute_score,
            "bda_output_bucket": bucket_saida,
            "confianca_general": round(1.0, 2),
            "json_estruturado": json_base_lote
        }
    except Exception as e:
        logger.error(f"Falha catastrófica na agregação final do lote: {str(e)}")
        raise e