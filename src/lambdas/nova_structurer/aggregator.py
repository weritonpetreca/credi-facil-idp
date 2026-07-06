"""
nova_structurer/aggregator.py

Responsabilidade: consolidar os resultados de TODAS as invocações do worker
(handler.py — 1 por documento) num único JSON de lote.

Analogia Java:
  O worker é como um thread que processa 1 documento.
  O aggregator é como o Collector no final de um Stream.parallelStream() —
  ele recebe os N resultados e os combina num único objeto.

  List<FutureResult> workerResults = ... // Map state do Step Functions
  BatchResult lote = aggregator.collect(workerResults);

Também é responsável por:
- Acumular os tokens consumidos por cada worker (para rastreamento de custo)
- Calcular o custo estimado total de BDA + Nova Lite
- Gravar o output.json de rascunho no S3 (o customer_consolidator sobrescreve depois)
"""
import json
import os
import datetime
import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.metrics import MetricUnit

logger = Logger(service="nova-structurer-aggregator")
s3_client = boto3.client("s3")
db_client = boto3.client("dynamodb")

# Preços Amazon Bedrock us-east-1 (confirmar em aws.amazon.com/bedrock/pricing)
PRECO_NOVA_LITE_INPUT_PER_1K = 0.00006    # USD por 1.000 tokens de input
PRECO_NOVA_LITE_OUTPUT_PER_1K = 0.00024   # USD por 1.000 tokens de output
PRECO_BDA_POR_PAGINA = 0.040              # USD por página (blueprint ≤30 campos)


# ─────────────────────────────────────────────────────────────────────────────
# ESTRUTURA DO WORKER OUTPUT
# Cada chamada ao worker (handler.py) retorna este contrato:
# {
#   "blueprint": { ...blueprint_json completo... },
#   "raw_ia": { ...campos que o Nova Lite retornou... },
#   "input_tokens": 1240,   <- tokens enviados ao Nova Lite
#   "output_tokens": 88,    <- tokens que o Nova Lite gerou
# }
# ─────────────────────────────────────────────────────────────────────────────

def inicializar_estrutura_base_lote(package_id: str) -> dict:
    """
    Cria o esqueleto do JSON do lote antes de preenchê-lo com os resultados.

    A estrutura "sistema" segue o contrato do SRS v3.0 para rastreabilidade:
    - versao_pipeline: versionamento semântico do pipeline
    - quantidade_tokens: totais por categoria (para o dashboard de FinOps)
    - custo_estimado_usd: calculado por categoria de serviço

    Analogia Java: é como criar um novo objeto Builder antes de chamar os setters.
    """
    return {
        "package_id": package_id,
        "status": "PROCESSING",
        "documentos_analisados": [],
        "tipos_documentos_analisados": [],
        "sistema": {
            "versao_pipeline": "1.2.0",
            "processamento": {
                "bda_project_arn": os.environ.get("BDA_PROJECT_ARN", ""),
                "quantidade_tokens": {
                    "input_tokens": 0,      # acumulado de todos os workers
                    "output_tokens": 0,     # acumulado de todos os workers
                    "total_tokens": 0,
                },
                "custo_estimado_usd": {
                    "bda_extracao": 0.0,
                    "nova_lite_estruturacao": 0.0,
                    "total_parcial": 0.0,   # "parcial" porque o consolidador soma depois
                },
                "documentos_processados": 0,
            },
            "ultimo_package_vinculado": {
                "package_id": package_id,
                "data_recebimento": datetime.datetime.utcnow().isoformat() + "Z",
            },
        },
    }


def processar_resultado_worker(resultado: dict, json_base_lote: dict):
    """
    Processa o resultado de UM worker e o adiciona ao JSON do lote.

    Esta função é chamada em loop — uma vez para cada documento do pacote.

    Parâmetros:
      resultado: o que o handler.py retornou para aquele documento
      json_base_lote: o JSON acumulado que está sendo montado

    Analogia Java: é como o método accept() num Consumer<WorkerResult>
    dentro de um forEach que monta o relatório final.
    """
    blueprint = resultado.get("blueprint")
    if not blueprint:
        logger.warning(f"Worker retornou resultado sem 'blueprint'. Resultado ignorado: {str(resultado)[:200]}")
        return

    arquivo_original = blueprint.get("arquivo_original", "arquivo_desconhecido.pdf")
    subtipo = blueprint.get("subtipo_documento", "desconhecido")
    tipo = blueprint.get("tipo_documento", "desconhecido")
    confianca_raw = blueprint.get("confiabilidade_extracao", {}).get("confianca_media", "0.0")

    logger.info(
        f"Agregando: {arquivo_original} | "
        f"tipo={tipo}/{subtipo} | "
        f"confianca={confianca_raw}"
    )

    # ── Adiciona o documento à lista do lote ──────────────────────────────────
    json_base_lote["documentos_analisados"].append({
        "arquivo_original": arquivo_original,
        "tipo_documento": tipo.upper(),
        "subtipo_documento": subtipo,
        # O campo abaixo mantém o blueprint completo para o customer_consolidator
        # poder ler os dados_extraidos_do_documento com a renda/saldo
        "dados_extraidos_do_documento": blueprint.get("dados_extraidos_do_documento", {}),
        "localizacao_documento_s3": blueprint.get("localizacao_documento_s3", {}),
        "confiabilidade_extracao": blueprint.get("confiabilidade_extracao", {}),
        # Mantém o blueprint completo como referência
        "blueprint": blueprint,
    })

    # ── Rastreia os tipos de documentos do pacote ─────────────────────────────
    tipo_label = subtipo or tipo
    if tipo_label not in json_base_lote.get("tipos_documentos_analisados", []):
        json_base_lote.setdefault("tipos_documentos_analisados", []).append(tipo_label)

    # ── Acumula os tokens do worker ───────────────────────────────────────────
    # Cada worker registra quantos tokens o Nova Lite consumiu para aquele documento.
    # Somamos aqui para ter o total do lote.
    input_tokens = int(resultado.get("input_tokens", 0))
    output_tokens = int(resultado.get("output_tokens", 0))

    sys_proc = json_base_lote["sistema"]["processamento"]
    sys_proc["quantidade_tokens"]["input_tokens"] += input_tokens
    sys_proc["quantidade_tokens"]["output_tokens"] += output_tokens
    sys_proc["quantidade_tokens"]["total_tokens"] += (input_tokens + output_tokens)
    sys_proc["documentos_processados"] += 1


def calcular_custos(json_base_lote: dict):
    """
    Calcula o custo estimado em USD ao final da agregação.

    Os preços são fixados no topo deste arquivo e devem ser revisados
    mensalmente contra a tabela oficial da AWS em:
    https://aws.amazon.com/bedrock/pricing/

    Analogia Java: é como um método calcularTotal() no carrinho de compras
    que faz o loop em todos os itens e soma os preços com impostos.
    """
    sys_proc = json_base_lote["sistema"]["processamento"]
    qtd = sys_proc["quantidade_tokens"]
    n_docs = sys_proc["documentos_processados"]

    custo_nova_lite = (
        (qtd["input_tokens"] / 1000 * PRECO_NOVA_LITE_INPUT_PER_1K)
        + (qtd["output_tokens"] / 1000 * PRECO_NOVA_LITE_OUTPUT_PER_1K)
    )
    # Estimativa conservadora: 1 documento ≈ 1 página
    custo_bda = n_docs * PRECO_BDA_POR_PAGINA

    custo = sys_proc["custo_estimado_usd"]
    custo["bda_extracao"] = round(custo_bda, 5)
    custo["nova_lite_estruturacao"] = round(custo_nova_lite, 5)
    custo["total_parcial"] = round(custo_bda + custo_nova_lite, 5)

    logger.info(
        f"Custo estimado do lote: "
        f"BDA=${custo_bda:.4f} | "
        f"Nova Lite=${custo_nova_lite:.5f} | "
        f"Total parcial=${custo['total_parcial']:.4f}"
    )


def emitir_metrica_custo(custo_total: float, package_id: str):
    """
    Emite a métrica de custo estimado via EMF (Embedded Metric Format).

    O CloudWatch entende automaticamente este formato como uma métrica
    customizada, que pode ser monitorada e alarmiada via AWS Budgets.

    Analogia Java: é como publicar um evento num EventBus do monitoramento.
    Em vez de logs, você faz graphing e alertas diretamente.
    """
    try:
        from aws_lambda_powertools.metrics import Metrics
        metrics = Metrics(namespace="CrediFacil/Pipeline")
        metrics.add_dimension(name="PackageId", value=package_id)
        metrics.add_metric(name="EstimatedCostUSD", unit=MetricUnit.Count, value=custo_total)
    except Exception as e:
        # Falha na métrica não deve derrubar o pipeline
        logger.warning(f"Não foi possível emitir métrica de custo: {e}")


def atualizar_dynamo(package_id: str, table_name: str):
    """
    Atualiza o item do DynamoDB para indicar que a estruturação do lote concluiu.

    O s3_upload_tracker gravou o item originalmente com status PROCESSING.
    O aggregator atualiza para indicar que a fase de estruturação está completa.

    Analogia Java: é como atualizar o status de uma entidade via JPA Repository.
    """
    try:
        db_client.update_item(
            TableName=table_name,
            Key={"PK": {"S": package_id}, "SK": {"S": "STATUS"}},
            UpdateExpression="SET #st = :s, updatedAt = :t",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":s": {"S": "CONSOLIDATING"},
                ":t": {"S": datetime.datetime.utcnow().isoformat() + "Z"},
            },
        )
    except Exception as e:
        logger.warning(f"Falha ao atualizar DynamoDB: {e}")


def handler(event, context):
    """
    Ponto de entrada da Lambda aggregator.

    Recebe do Step Functions Map state a lista de resultados de todos os workers.
    Cada item da lista é o output do handler.py para um documento.

    event esperado:
    {
      "package_id": "...",
      "bda_output_bucket": "...",
      "execute_score": false,
      "user_id": "analista@credifacil.com",
      "resultados": [     <- lista montada pelo Map state
        { "blueprint": {...}, "input_tokens": 1240, "output_tokens": 88 },
        { "blueprint": {...}, "input_tokens": 2100, "output_tokens": 110 }
      ]
    }
    """
    try:
        package_id = event.get("package_id")
        bucket = event.get("bda_output_bucket") or os.environ.get("BUCKET_SAIDA")
        execute_score = event.get("execute_score", False)
        user_id = event.get("user_id", "sistema")
        table_name = os.environ.get("DYNAMODB_TABLE", "credifacil-pacotes-dev")

        logger.info(f"Aggregator iniciado para pacote {package_id}. Score: {execute_score}")

        # ── Inicializa o JSON do lote ─────────────────────────────────────────
        json_base_lote = inicializar_estrutura_base_lote(package_id)

        # ── Processa cada resultado do Map state ──────────────────────────────
        # O Step Functions passa os resultados em uma lista chamada "resultados"
        # ou como o próprio corpo do evento quando o Map usa ItemProcessor.
        resultados = event.get("resultados", [])

        # Normaliza: às vezes o Step Functions embute os resultados diretamente
        if not resultados and isinstance(event, list):
            resultados = event

        if not resultados:
            logger.warning(f"Nenhum resultado de worker recebido para o pacote {package_id}.")

        for resultado in resultados:
            # Resultado pode estar embrulhado num dict com chave "blueprint" ou diretamente
            if isinstance(resultado, dict):
                processar_resultado_worker(resultado, json_base_lote)

        # ── Calcula os custos totais ──────────────────────────────────────────
        calcular_custos(json_base_lote)

        custo_total = json_base_lote["sistema"]["processamento"]["custo_estimado_usd"]["total_parcial"]
        emitir_metrica_custo(custo_total, package_id)

        # ── Atualiza o DynamoDB ───────────────────────────────────────────────
        atualizar_dynamo(package_id, table_name)

        # ── Grava o rascunho do output.json no S3 ────────────────────────────
        # O customer_consolidator vai sobrescrever este arquivo com a versão final.
        key_output = f"results/packages/{package_id}/output.json"
        s3_client.put_object(
            Bucket=bucket,
            Key=key_output,
            Body=json.dumps(json_base_lote, ensure_ascii=False, default=str),
            ContentType="application/json",
        )

        n_docs = json_base_lote["sistema"]["processamento"]["documentos_processados"]
        total_tokens = json_base_lote["sistema"]["processamento"]["quantidade_tokens"]["total_tokens"]
        logger.info(
            f"Aggregator concluído: {n_docs} documentos | "
            f"{total_tokens} tokens | "
            f"custo parcial=${custo_total:.4f} USD"
        )

        # ── Retorna o payload para o próximo estado do Step Functions ─────────
        return {
            "package_id": package_id,
            "bda_output_bucket": bucket,
            "execute_score": execute_score,
            "user_id": user_id,
            "json_estruturado": json_base_lote,
        }

    except Exception as e:
        logger.error(f"Falha crítica no aggregator do pacote {event.get('package_id')}: {str(e)}")
        raise e