import { useState, useRef, useCallback } from "react";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:3000/";

const MIN_FILES = 1;
const MAX_FILES = 8;
const POLL_INTERVAL_MS = 5000;
const POLL_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutos

const ALLOWED_TYPES = [
  "application/pdf",
  "image/png",
  "image/jpeg",
  "image/webp",
];

function isAllowedFileType(file) {
  return ALLOWED_TYPES.includes(file.type);
}

function formatFileSize(bytes) {
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(2)} KB`;
  return `${(kb / 1024).toFixed(2)} MB`;
}

export function useDocumentPipeline() {
  const [phase, setPhase] = useState("idle");
  const [logs, setLogs] = useState([]);
  const [result, setResult] = useState(null);
  const [executeScore, setExecuteScoreFlag] = useState(false);
  const [outputBucket, setOutputBucket] = useState(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [startedAt, setStartedAt] = useState(null);
  const [finishedAt, setFinishedAt] = useState(null);
  
  // 🚀 NOVOS ESTADOS: Gerenciamento do ciclo de vida da Revisão Humana (RF-16)
  const [currentPackageId, setCurrentPackageId] = useState(null);
  const [revisionFields, setRevisionFields] = useState([]);

  const pollTimer = useRef(null);
  const pollDeadline = useRef(null);

  const pushLog = useCallback((message, level = "info") => {
    setLogs((prev) => [
      ...prev,
      { message, level, time: new Date().toLocaleTimeString("pt-BR") },
    ]);
  }, []);

  const stopPolling = useCallback(() => {
    if (pollTimer.current) {
      clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    stopPolling();
    setPhase("idle");
    setLogs([]);
    setResult(null);
    setOutputBucket(null);
    setErrorMessage("");
    setStartedAt(null);
    setFinishedAt(null);
    setCurrentPackageId(null);
    setRevisionFields([]);
  }, [stopPolling]);

  const pollUntilDone = useCallback(
    (packageId, scoreRequested, token) => {
      pollDeadline.current = Date.now() + POLL_TIMEOUT_MS;

      const tick = async () => {
        if (Date.now() > pollDeadline.current) {
          setPhase("error");
          setErrorMessage(
            "O processamento está demorando mais que o esperado. Tente novamente em alguns minutos.",
          );
          pushLog("Tempo limite de espera atingido.", "error");
          setFinishedAt(Date.now());
          return;
        }

        try {
          const response = await fetch(`${API_URL}v1/packages/${packageId}`, {
            headers: {
              "Authorization": `Bearer ${token}`
            }
          });

          if (!response.ok) {
            pollTimer.current = setTimeout(tick, POLL_INTERVAL_MS);
            return;
          }

          const data = await response.json();

          // 🚀 INTERCEPTAÇÃO REATIVA [RF-16]: Trava o pooling se a IA acusar baixa acurácia
          if (data.status === "NEEDS_REVISION") {
            pushLog("⚠️ Atenção: Baixa confiança detectada em campos críticos. Retendo para revisão manual.", "warn");
            const fields = data.failed_fields_metadata || data.confidence_results?.failed_fields_metadata || [];
            setRevisionFields(fields);
            setPhase("revision");
            stopPolling();
            return;
          }

          if (data.status === "PROCESSING") {
            pushLog("Em processamento na AWS. Extraindo metadados via Bedrock BDA...");
            pollTimer.current = setTimeout(tick, POLL_INTERVAL_MS);
            return;
          }

          if (data.status === "COMPLETED") {
            pushLog("Análise estrutural finalizada.", "success");
            setResult(data.dados_extraidos || null);
            setOutputBucket(data.bda_output_bucket || null);
            setFinishedAt(Date.now());
            setPhase("done");
            return;
          }

          if (data.status === "FAILED") {
            setPhase("error");
            setErrorMessage(data.erro_processamento || "A esteira de processamento falhou.");
            pushLog(data.erro_processamento || "Falha no processamento.", "error");
            setFinishedAt(Date.now());
            return;
          }

          pollTimer.current = setTimeout(tick, POLL_INTERVAL_MS);
        } catch {
          pushLog("Erro ao consultar status, tentando novamente...", "error");
          pollTimer.current = setTimeout(tick, POLL_INTERVAL_MS);
        }
      };

      tick();
    },
    [pushLog, stopPolling],
  );

  // 🚀 NOVO MÉTODO [RF-20]: Submete as correções manuais do operador para a nossa API Gateway
  const submitReview = useCallback(async (correcoes, token) => {
    if (!currentPackageId) return false;
    
    try {
      setPhase("preparing");
      pushLog("Transmitindo correções analíticas para reativar o pipeline...");

      const response = await fetch(`${API_URL}v1/packages/${currentPackageId}/review`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({ correcoes })
      });

      const responseData = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(responseData?.erro || "Falha ao registrar correções manuais.");
      }

      pushLog("Revisão aceita pelo motor da AWS! Retomando pooling reativo.", "success");
      setPhase("waiting");
      setRevisionFields([]);
      
      // Acorda o polling na mesma hora para aguardar a finalização do Nova Lite
      pollUntilDone(currentPackageId, executeScore, token);
      return true;
    } catch (err) {
      setPhase("revision");
      setErrorMessage(err.message || "Não foi possível processar a revisão manual.");
      pushLog(err.message || "Erro no transbordo humano.", "error");
      return false;
    }
  }, [currentPackageId, executeScore, pollUntilDone, pushLog]);

  const upload = useCallback(
    async (files, scoreRequested, token) => {
      stopPolling();
      setResult(null);
      setOutputBucket(null);
      setErrorMessage("");
      setLogs([]);
      setFinishedAt(null);
      setCurrentPackageId(null);
      setRevisionFields([]);
      setExecuteScoreFlag(scoreRequested);

      if (!files || files.length < MIN_FILES) {
        setPhase("error");
        setErrorMessage("Selecione pelo menos 1 documento.");
        return false;
      }

      if (files.length > MAX_FILES) {
        setPhase("error");
        setErrorMessage(`Envie no máximo ${MAX_FILES} documentos por solicitação.`);
        return false;
      }

      const invalidFiles = files.filter((f) => !isAllowedFileType(f));
      if (invalidFiles.length > 0) {
        setPhase("error");
        setErrorMessage("Um ou mais arquivos possuem formato não permitido.");
        return false;
      }

      try {
        setPhase("preparing");
        setStartedAt(Date.now());
        pushLog("Registrando lote e coletando credenciais de storage do S3...");

        const prepResponse = await fetch(`${API_URL}v1/packages/upload-urls`, {
          method: "POST",
          headers: { 
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
          },
          body: JSON.stringify({
            documentos: files.map((f) => ({
              nome: f.name,
              tamanho: f.size
            })),
            execute_score: scoreRequested,
          }),
        });

        const prepData = await prepResponse.json().catch(() => null);

        if (!prepResponse.ok) {
          throw new Error(prepData?.erro || "Erro ao solicitar autorização de upload.");
        }

        if (!prepData?.uploads || typeof prepData.uploads !== "object") {
          throw new Error("Resposta inválida do servidor. Instruções de upload ausentes.");
        }

        pushLog(`Lote registrado: ${prepData.package_id}`);
        setCurrentPackageId(prepData.package_id);

        setPhase("uploading");
        pushLog(`Enviando ${files.length} documento(s) para o storage seguro...`);

        for (const file of files) {
          const instruction = prepData.uploads[file.name];

          if (!instruction) {
            throw new Error(`Instrução de upload não encontrada para o arquivo: ${file.name}`);
          }

          const formData = new FormData();
          Object.entries(instruction.fields).forEach(([key, value]) => {
            formData.append(key, value);
          });
          formData.append("file", file);

          const postResponse = await fetch(instruction.url, {
            method: "POST",
            body: formData, 
          });

          if (!postResponse.ok) {
            throw new Error(`Erro ao transmitir o binário do arquivo via POST: ${file.name}`);
          }

          pushLog(`${file.name} (${formatFileSize(file.size)}) enviado via canal seguro POST.`, "success");
        }

        pushLog("Lote enviado. Monitorando progresso do IDP...", "success");
        setPhase("waiting");

        pollUntilDone(prepData.package_id, scoreRequested, token);
        return true;
      } catch (err) {
        setPhase("error");
        setErrorMessage(err.message || "Não foi possível concluir o envio. Verifique os arquivos e tente novamente.");
        pushLog(err.message || "Erro inesperado.", "error");
        setFinishedAt(Date.now());
        return false;
      }
    },
    [pollUntilDone, pushLog, stopPolling],
  );

  return {
    phase,
    logs,
    result,
    executeScore,
    outputBucket,
    errorMessage,
    startedAt,
    finishedAt,
    currentPackageId,
    revisionFields,
    upload,
    submitReview,
    reset,
  };
}