const uploadForm = document.getElementById("uploadForm");
const documentsInput = document.getElementById("documents");
const fileList = document.getElementById("fileList");
const statusBox = document.getElementById("statusBox");
const submitButton = document.getElementById("submitButton");

// 🚀 CONEXÃO COM O SEU API GATEWAY REAL
const API_URL = "https://zrky80ks0l.execute-api.us-east-1.amazonaws.com/dev/";
const MIN_FILES = 1;
const MAX_FILES = 8;

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

  // Prepara o payload no contrato esperado pela rota v1/packages/upload-urls
  const payloadToLambda = {
    documentos: files.map((file) => file.name)
  };

  try {
    setLoading(true);
    updateStatus("Registrando lote e coletando credenciais do S3...", "processing");

    // 1. Coleta as URLs pré-assinadas da AWS via API Gateway
    const uploadInstructions = await getUploadInstructions(payloadToLambda);

    updateStatus("Enviando documentos diretamente para o Storage seguro...", "processing");

    // 2. Transmite os arquivos em paralelo para o S3 (Ativando o Tracker Reativo)
    await uploadFilesToS3(files, uploadInstructions);

    updateStatus(
      `Sucesso! Lote ${uploadInstructions.package_id} recebido. O processamento reativo foi iniciado em background.`,
      "success"
    );

    uploadForm.reset();
    renderFileList([]);
  } catch (error) {
    updateStatus(
      error.message || "Não foi possível concluir o envio. Verifique os arquivos e tente novamente.",
      "error"
    );
  } finally {
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
  summary.textContent = `${files.length} arquivo(s) selecionado(s). Permitido: 1 a 8 arquivos.`;
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

  // Validação corrigida para aceitar o Objeto/Dicionário mapeado por arquivos
  if (!data?.uploads || typeof data.uploads !== 'object') {
    throw new Error("Resposta inválida do servidor. Instruções de upload ausentes.");
  }

  return data;
}

async function uploadFilesToS3(files, uploadInstructions) {
  for (const file of files) {
    // Busca direta por chave no dicionário (Rápido e sem loops desnecessários)
    const instruction = uploadInstructions.uploads[file.name];

    if (!instruction) {
      throw new Error(`Instrução de upload não encontrada para o arquivo: ${file.name}`);
    }

    const uploadResponse = await fetch(instruction.uploadUrl, {
      method: "PUT",
      headers: { "Content-Type": "application/pdf" },
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
  submitButton.textContent = isLoading ? "Enviando para a AWS..." : "Enviar documentos";
}