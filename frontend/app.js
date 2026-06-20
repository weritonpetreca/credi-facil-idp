const uploadForm = document.getElementById("uploadForm");
const documentsInput = document.getElementById("documents");
const fileList = document.getElementById("fileList");
const statusBox = document.getElementById("statusBox");
const submitButton = document.getElementById("submitButton");
const toggleScore = document.getElementById("toggleScore");

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

  if (files.length < MIN_FILES || files.length > MAX_FILES) {
    updateStatus(`Selecione entre ${MIN_FILES} e ${MAX_FILES} documentos.`, "error");
    return;
  }

  // 🚀 PASSO 1: Captura a escolha do checkbox para enviar para a API da AWS
  const deveCalcularScore = toggleScore.checked;

  const payloadToLambda = {
    documentos: files.map((file) => file.name),
    execute_score: deveCalcularScore // ⚗️ Flag injetada na esteira de dados
  };

  try {
    setLoading(true);
    document.getElementById("analyticsDashboard").style.display = "none";
    updateStatus("Registrando lote e coletando credenciais de storage do S3...", "processing");

    const uploadInstructions = await getUploadInstructions(payloadToLambda);
    updateStatus("Enviando documentos diretamente para o S3 de forma segura...", "processing");

    await uploadFilesToS3(files, uploadInstructions);
    updateStatus(`Sucesso! Lote enviado. Monitorando progresso do IDP...`, "processing");

    uploadForm.reset();
    renderFileList([]);

    iniciarMonitoramentoLote(uploadInstructions.package_id, deveCalcularScore);

  } catch (error) {
    updateStatus(error.message || "Erro no envio do lote.", "error");
    setLoading(false);
  }
});

function renderFileList(files) {
  fileList.innerHTML = "";
  if (files.length === 0) {
    fileList.textContent = "Nenhum arquivo selecionado.";
    return;
  }
  files.forEach((file, index) => {
    const item = document.createElement("div");
    item.className = "file-item";
    item.innerHTML = `<span>${index + 1}. ${file.name}</span>`;
    fileList.appendChild(item);
  });
}

async function getUploadInstructions(payloadToLambda) {
  const response = await fetch(`${API_URL}v1/packages/upload-urls`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payloadToLambda)
  });
  return await response.json();
}

async function uploadFilesToS3(files, uploadInstructions) {
  for (const file of files) {
    const instruction = uploadInstructions.uploads[file.name];
    if (instruction) {
      await fetch(instruction.uploadUrl, {
        method: "PUT",
        headers: { "Content-Type": file.type || "application/octet-stream" },
        body: file
      });
    }
  }
}

function updateStatus(message, type) {
  statusBox.textContent = message;
  statusBox.className = "status-box " + (type === "processing" ? "status-processing" : type === "success" ? "status-success" : "status-error");
}

function setLoading(isLoading) {
  submitButton.disabled = isLoading;
  submitButton.textContent = isLoading ? "Processando..." : "Iniciar Processamento Inteligente";
}

function iniciarMonitoramentoLote(packageId, deveCalcularScore) {
  if (pollingInterval) clearInterval(pollingInterval);

  pollingInterval = setInterval(async () => {
    try {
      const response = await fetch(`${API_URL}v1/packages/${packageId}`);
      if (!response.ok) return;

      const result = await response.json();
      
      if (result.status === "COMPLETED") {
        clearInterval(pollingInterval);
        setLoading(false);
        updateStatus("Análise estrutural finalizada!", "success");
        plotarDashboardAnalitico(result.dados_extraidos, deveCalcularScore, result.bda_output_bucket);
        
        if (deveCalcularScore) {
          document.getElementById("modalMetaScoreWrapper").style.display = "block";
          document.getElementById("modalScore").textContent = `${result.dados_extraidos?.cliente?.score_credito?.valor ?? 0} pontos`;
        } else {
          document.getElementById("modalMetaScoreWrapper").style.display = "none";
        }
        document.getElementById("successModal").style.display = "flex";
      }
    } catch (err) {
      console.error(err);
    }
  }, 4000);
}

function fecharModalEVerResultado() {
  document.getElementById("successModal").style.display = "none";
  document.getElementById("analyticsDashboard").scrollIntoView({ behavior: "smooth" });
}

function plotarDashboardAnalitico(dados, deveCalcularScore, outputBucket) {
  if (!dados) return;

  const scoreSection = document.getElementById("scoreConsolidadoSection");
  if (deveCalcularScore && dados.cliente) {
    scoreSection.style.display = "block";
    document.getElementById("resNome").textContent = dados.cliente.nome || "-";
    document.getElementById("resDoc").textContent = dados.cliente.documento_identificacao || "-";
    document.getElementById("resScoreValue").textContent = dados.cliente.score_credito?.valor ?? 0;
    document.getElementById("resJustificativaBox").textContent = dados.cliente.classificacao_risco?.justificativa || "-";
  } else {
    scoreSection.style.display = "none";
  }

  const tableBody = document.getElementById("tableDocsBody");
  tableBody.innerHTML = "";
  
  const docs = dados.documentos_analisados || [];
  docs.forEach((d, index) => {
    const row = document.createElement("tr");
    const s3UrlJson = `https://${outputBucket || 'credifacil-docs-saida-dev'}.s3.amazonaws.com/${d.s3_key_origem.replace('packages/', 'results/').replace('.pdf', '_structured.json')}`;

    row.innerHTML = `
      <td style="padding: 10px; border: 1px solid #cbd5e1; font-weight: bold;">${d.tipo_documento}</td>
      <td style="padding: 10px; border: 1px solid #cbd5e1; color: #475569;">${d.arquivo_original}</td>
      <td style="padding: 10px; border: 1px solid #cbd5e1;">${d.status_extracao}</td>
      <td style="padding: 10px; border: 1px solid #cbd5e1;">${(d.confianca_media * 100).toFixed(1)}%</td>
      <!-- 🚀 PASSO 2: Botões de ação individuais por arquivo com injeção de ID único -->
      <td style="padding: 10px; border: 1px solid #cbd5e1; text-align: center; display: flex; gap: 8px; justify-content: center;">
        <a href="${s3UrlJson}" target="_blank" style="color: #2563eb; font-weight: bold; font-size: 13px; text-decoration: none;">📄 Ver JSON</a>
        <button id="exp-${index}" class="modal-btn" style="padding: 4px 8px; background: #10b981; font-size: 12px; margin:0;">📊 Excel</button>
      </td>
    `;
    tableBody.appendChild(row);

    // Amarra a exportação individual exclusivamente para os metadados deste arquivo
    document.getElementById(`exp-${index}`).addEventListener("click", () => {
      exportarArquivoParaExcel(d);
    });
  });
}

// 🚀 PASSO 3: Exportador Individual Nativo de Arquivo para Excel
function exportarArquivoParaExcel(doc) {
  let csvContent = "data:text/csv;charset=utf-8,\uFEFF";
  csvContent += "Propriedade;Valor Extraido;Confianca Campo\n";

  const campos = doc.campos_extraidos || {};
  Object.keys(campos).forEach(chave => {
    let campoDados = campos[chave];
    let valor = typeof campoDados === 'object' ? campoDados?.value : campoDados;
    let conf = typeof campoDados === 'object' ? `${(campoDados?.confidence * 100).toFixed(1)}%` : "100%";
    
    csvContent += `${chave};${String(valor || 'null').replace(/;/g, ',')};${conf}\n`;
  });

  const encodedUri = encodeURI(csvContent);
  const downloadLink = document.createElement("a");
  downloadLink.setAttribute("href", encodedUri);
  downloadLink.setAttribute("download", `excel_metadados_${doc.arquivo_original}.csv`);
  document.body.appendChild(downloadLink);
  downloadLink.click();
  document.body.removeChild(downloadLink);
}