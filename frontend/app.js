const uploadForm = document.getElementById("uploadForm");
const documentsInput = document.getElementById("documents");
const fileList = document.getElementById("fileList");
const statusBox = document.getElementById("statusBox");
const submitButton = document.getElementById("submitButton");

// 🚀 CONEXÃO UNIFICADA COM O SEU API GATEWAY REAL
const API_URL = "https://zrky80ks0l.execute-api.us-east-1.amazonaws.com/dev/";
const MIN_FILES = 1;
const MAX_FILES = 8;
let pollingInterval = null; 

documentsInput.addEventListener("change", () => {
  const files = Array.from(documentsInput.files);
  renderFileList(files);
});

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const files = Array.from(documentsInput.files);

  if (files.length < MIN_FILES) {
    updateStatus("Selecione pelo menos 1 documento.", "error");
    return;
  }
  if (files.length > MAX_FILES) {
    updateStatus("Envie no máximo 8 documentos por solicitação.", "error");
    return;
  }

  const invalidFiles = files.filter((file) => !isAllowedFileType(file));
  if (invalidFiles.length > 0) {
    updateStatus("Um ou mais arquivos possuem formato não permitido.", "error");
    return;
  }

  const payloadToLambda = {
    documentos: files.map((file) => file.name)
  };

  try {
    setLoading(true);
    document.getElementById("analyticsDashboard").style.display = "none";
    updateStatus("Registrando lote e coletando credenciais do S3...", "processing");

    const uploadInstructions = await getUploadInstructions(payloadToLambda);

    updateStatus("Enviando documentos diretamente para o Storage seguro...", "processing");

    await uploadFilesToS3(files, uploadInstructions);

    updateStatus(
      `Sucesso! Lote enviado. O processamento reativo foi iniciado em background. Monitorando...`,
      "processing"
    );

    uploadForm.reset();
    renderFileList([]);

    iniciarMonitoramentoLote(uploadInstructions.package_id);

  } catch (error) {
    updateStatus(
      error.message || "Não foi possível concluir o envio. Verifique os arquivos e tente novamente.",
      "error"
    );
    setLoading(false);
  }
});

function renderFileList(files) {
  fileList.innerHTML = "";
  if (files.length === 0) {
    fileList.textContent = "Nenhum arquivo selecionado.";
    return;
  }

  const summary = document.createElement("div");
  summary.className = "file-summary";
  summary.textContent = `${files.length} arquivo(s) seleccionado(s). Permitido: 1 a 8 arquivos.`;
  fileList.appendChild(summary);

  files.forEach((file, index) => {
    const item = document.createElement("div");
    item.className = "file-item";
    item.innerHTML = `
      <span class="file-name">${index + 1}. ${file.name}</span>
      <span class="file-size">${formatFileSize(file.size)}</span>
    `;
    fileList.appendChild(item);
  });
}

async function getUploadInstructions(payloadToLambda) {
  const response = await fetch(`${API_URL}v1/packages/upload-urls`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payloadToLambda)
  });

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.erro || "Erro ao solicitar autorização de upload.");
  }

  if (!data?.uploads || typeof data.uploads !== 'object') {
    throw new Error("Resposta inválida do servidor. Instruções de upload ausentes.");
  }

  return data;
}

async function uploadFilesToS3(files, uploadInstructions) {
  for (const file of files) {
    const instruction = uploadInstructions.uploads[file.name];

    if (!instruction) {
      throw new Error(`Instrução de upload não encontrada para o arquivo: ${file.name}`);
    }

    // 🚀 CORREÇÃO CRÍTICA: Envia o tipo real do arquivo (ex: image/png) para casar com a assinatura da AWS
    const uploadResponse = await fetch(instruction.uploadUrl, {
      method: "PUT",
      headers: { "Content-Type": file.type || "application/octet-stream" },
      body: file
    });

    if (!uploadResponse.ok) {
      throw new Error(`Erro ao transmitir o binário do arquivo: ${file.name}`);
    }
  }
}

function isAllowedFileType(file) {
  const allowedTypes = ["application/pdf", "image/png", "image/jpeg", "image/webp"];
  return allowedTypes.includes(file.type);
}

function formatFileSize(sizeInBytes) {
  const sizeInKb = sizeInBytes / 1024;
  return sizeInKb < 1024 ? `${sizeInKb.toFixed(2)} KB` : `${(sizeInKb / 1024).toFixed(2)} MB`;
}

function updateStatus(message, type) {
  statusBox.textContent = message;
  statusBox.className = "status-box";
  if (type === "processing") statusBox.classList.add("status-processing");
  if (type === "success") statusBox.classList.add("status-success");
  if (type === "error") statusBox.classList.add("status-error");
}

function setLoading(isLoading) {
  submitButton.disabled = isLoading;
  submitButton.textContent = isLoading ? "Enviando para a AWS..." : "Iniciar Processamento Inteligente";
}

document.addEventListener("DOMContentLoaded", () => {
  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission();
  }
});

function iniciarMonitoramentoLote(packageId) {
  if (pollingInterval) clearInterval(pollingInterval);

  pollingInterval = setInterval(async () => {
    try {
      const response = await fetch(`${API_URL}v1/packages/${packageId}`);
      if (!response.ok) return;

      const result = await response.json();
      
      if (result.status === "PROCESSING") {
        updateStatus(`Lote em processamento na AWS... Extraindo metadados estruturais via Bedrock BDA.`, "processing");
      } 
      else if (result.status === "COMPLETED") {
        clearInterval(pollingInterval);
        setLoading(false);
        updateStatus("Análise finalizada com sucesso! Relatório gerado.", "success");
        
        plotarDashboardAnalitico(result.dados_extraidos);
        
        const score = result.dados_extraidos?.cliente?.score_credito?.valor ?? 0;
        document.getElementById("modalScore").textContent = `${score} pontos`;
        document.getElementById("successModal").style.display = "flex";

        if ("Notification" in window && Notification.permission === "granted") {
          new Notification("CrediFácil IDP Engine", {
            body: `Análise concluída para o proponente! Score: ${score} pontos. Clique para ver.`,
          });
        }
      } 
      else if (result.status === "FAILED") {
        clearInterval(pollingInterval);
        setLoading(false);
        updateStatus(`A esteira falhou: ${result.erro_processamento || "Erro desconhecido"}`, "error");
      }
    } catch (err) {
      console.error("Erro no polling do tracker:", err);
    }
  }, 4000);
}

function fecharModalEVerResultado() {
  document.getElementById("successModal").style.display = "none";
  document.getElementById("analyticsDashboard").scrollIntoView({ behavior: "smooth" });
}

function plotarDashboardAnalitico(dados) {
  if (!dados) return;

  const cliente = dados.cliente || {};
  const sistema = dados.sistema || {};
  const validacao = dados.validacao || {};
  const docs = dados.documentos_analisados || [];

  document.getElementById("analyticsDashboard").style.display = "block";

  document.getElementById("resNome").textContent = cliente.nome || "Não Identificado";
  document.getElementById("resDoc").textContent = cliente.documento_identificacao || "Não Fornecido";
  document.getElementById("resRenda").textContent = `US$ ${procMaxValor(docs, ['amount_numeric', 'Gross Pay', 'renda_bruta_informada']).toFixed(2)}`;
  document.getElementById("resSaldo").textContent = `US$ ${procMaxValor(docs, ['saldo_bancario_fechamento', 'balance', 'amount']).toFixed(2)}`;
  document.getElementById("badgeModelo").textContent = sistema.processamento?.modelo_utilizado || "Amazon Nova Pro";

  const scoreElement = document.getElementById("resScoreValue");
  const catElement = document.getElementById("resRiscoCategoria");
  
  scoreElement.textContent = cliente.score_credito?.valor ?? 0;
  catElement.textContent = (cliente.classificacao_risco?.categoria || "INCONCLUSIVO").toUpperCase();

  if (cliente.classificacao_risco?.categoria === "baixo") {
    catElement.style.background = "#d1fae5"; catElement.style.color = "#065f46";
  } else if (cliente.classificacao_risco?.categoria === "medio") {
    catElement.style.background = "#fef3c7"; catElement.style.color = "#92400e";
  } else {
    catElement.style.background = "#fee2e2"; catElement.style.color = "#991b1b";
  }

  document.getElementById("resJustificativaBox").textContent = cliente.classificacao_risco?.justificativa || "Sem justificativa.";

  renderCheckliItem("chkNome", "Nome consistente entre documentos", validacao.nome_consistente_entre_documentos);
  renderCheckliItem("chkNasc", "Data de nascimento consistente", validacao.data_nascimento_consistente);
  renderCheckliItem("chkId", "Documento de identidade presente", validacao.documento_identificacao_presente);
  renderCheckliItem("chkRenda", "Comprovante de renda anexado", validacao.comprovante_renda_presente);
  renderCheckliItem("chkExtrato", "Extrato bancário de liquidez presente", validacao.extrato_bancario_presente);

  const tableBody = document.getElementById("tableDocsBody");
  tableBody.innerHTML = "";
  
  docs.forEach(d => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td style="padding: 10px; border: 1px solid #cbd5e1; font-weight: bold;">${d.tipo_documento}</td>
      <td style="padding: 10px; border: 1px solid #cbd5e1; color: #475569;">${d.arquivo_original}</td>
      <td style="padding: 10px; border: 1px solid #cbd5e1;"><span class="header-badge" style="background: ${d.status_extracao === 'sucesso' ? '#eff6ff' : '#f8fafc'}; color: ${d.status_extracao === 'sucesso' ? '#1e40af' : '#64748b'}; border: none; padding: 4px 10px;">${d.status_extracao}</span></td>
      <td style="padding: 10px; border: 1px solid #cbd5e1; font-weight: 500;">${(d.confianca_media * 100).toFixed(1)}%</td>
    `;
    tableBody.appendChild(row);
  });
}

function renderCheckliItem(elementId, text, status) {
  const el = document.getElementById(elementId);
  if (status === true) {
    el.textContent = `✅ ${text}`; el.style.color = "#166534";
  } else if (status === false) {
    el.textContent = `❌ ${text}`; el.style.color = "#991b1b";
  } else {
    el.textContent = `⚪ ${text} (Não Avaliado)`; el.style.color = "#64748b";
  }
}

function procMaxValor(docs, chaves) {
  let max = 0;
  docs.forEach(d => {
    chaves.forEach(c => {
      const val = d.campos_extraidos?.[c];
      if (val) {
        const numeric = parseFloat(String(val).replace(/[^0-9.]/g, '')) || 0;
        if (numeric > max) max = numeric;
      }
    });
  });
  return max;
}