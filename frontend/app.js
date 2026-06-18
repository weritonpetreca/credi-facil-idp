const uploadForm = document.getElementById("uploadForm");
const documentsInput = document.getElementById("documents");
const fileList = document.getElementById("fileList");
const statusBox = document.getElementById("statusBox");
const submitButton = document.getElementById("submitButton");

// 🚀 LINKADO AO SEU API GATEWAY REAL
const API_BASE_URL = "https://zrky80ks0l.execute-api.us-east-1.amazonaws.com/dev/";
const MAX_FILES = 8;
let pollingInterval = null;

documentsInput.addEventListener("change", () => {
  const files = Array.from(documentsInput.files);
  renderFileList(files);
});

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const files = Array.from(documentsInput.files);

  if (files.length === 0) {
    updateStatus("Selecione pelo menos 1 documento.", "error");
    return;
  }
  if (files.length > MAX_FILES) {
    updateStatus(`Envie no máximo ${MAX_FILES} documentos por solicitação.`, "error");
    return;
  }

  // Monta a expectativa do lote baseada no nome real dos arquivos locais
  const payloadToLambda = {
    documentos: files.map(file => file.name)
  };

  try {
    setLoading(true);
    document.getElementById("analyticsDashboard").style.display = "none";
    updateStatus("Registrando lote e coletando links seguros do S3...", "processing");

    // 1. POST para obter chaves e URLs pré-assinadas da API Gateway
    const responseUrl = await fetch(`${API_BASE_URL}v1/packages/upload-urls`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payloadToLambda)
    });
    
    const urlData = await responseUrl.json();
    if (!responseUrl.ok) throw new Error(urlData.erro || "Falha ao registrar expectativa de lote.");

    const packageId = urlData.package_id;
    updateStatus(`Transmitindo binários diretamente para a nuvem AWS (Lote: ${packageId})...`, "processing");

    // 2. Upload paralelo nativo PUT para o S3 (Alinhado ao S3 Tracker reativo)
    const uploadPromises = files.map(async (file) => {
      const instruction = urlData.uploads[file.name];
      if (!instruction) throw new Error(`Instrução ausente para o arquivo: ${file.name}`);

      const uploadResponse = await fetch(instruction.uploadUrl, {
        method: "PUT",
        headers: { "Content-Type": "application/pdf" },
        body: file
      });

      if (!uploadResponse.ok) throw new Error(`Falha na transmissão do arquivo ${file.name}`);
    });

    await Promise.all(uploadPromises);

    updateStatus("Todos os binários foram salvos! A esteira serverless foi ativada de forma reativa. Monitorando progresso...", "processing");
    uploadForm.reset();
    renderFileList([]);

    // 3. Inicia o Polling Automático de Background para ler a rota GET
    iniciarMonitoramentoLote(packageId);

  } catch (error) {
    updateStatus(error.message || "Ocorreu um erro inesperado na carga do lote.", "error");
    setLoading(false);
  }
});

function iniciarMonitoramentoLote(packageId) {
  if (pollingInterval) clearInterval(pollingInterval);

  pollingInterval = setInterval(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}v1/packages/${packageId}`);
      if (!response.ok) return; // Aguarda até o registro estar maduro regionalmente

      const result = await response.json();
      
      if (result.status === "PROCESSING") {
        updateStatus(`Lote em processamento na AWS... Extraindo metadados estruturais via Bedrock BDA.`, "processing");
      } 
      else if (result.status === "COMPLETED") {
        clearInterval(pollingInterval);
        setLoading(false);
        updateStatus("Análise finalizada com sucesso! Relatório gerado.", "success");
        plotarDashboardAnalitico(result.dados_extraidos);
      } 
      else if (result.status === "FAILED") {
        clearInterval(pollingInterval);
        setLoading(false);
        updateStatus(`A esteira falhou: ${result.erro_processamento || "Erro desconhecido"}`, "error");
      }
    } catch (err) {
      console.error("Erro no polling do tracker:", err);
    }
  }, 4000); // Consulta a API Gateway a cada 4 segundos
}

function plotarDashboardAnalitico(dados) {
  if (!dados) return;

  const cliente = dados.cliente || {};
  const sistema = dados.sistema || {};
  const validacao = dados.validacao || {};
  const docs = dados.documentos_analisados || [];

  // Exibe o painel principal oculto
  document.getElementById("analyticsDashboard").style.display = "block";

  // Preenche dados gerais promocionais do CRM
  document.getElementById("resNome").textContent = cliente.nome || "Não Identificado";
  document.getElementById("resDoc").textContent = cliente.documento_identificacao || "Não Fornecido";
  document.getElementById("resRenda").textContent = cliente.score_credito?.valor > 0 ? `US$ ${procRendaMaxima(docs).toFixed(2)}` : "Não Identificada";
  document.getElementById("resSaldo").textContent = cliente.score_credito?.valor > 0 ? `US$ ${procSaldoMaximo(docs).toFixed(2)}` : "Não Identificado";
  document.getElementById("badgeModelo").textContent = sistema.processamento?.modelo_utilizado || "Amazon Nova";

  // Plota Score e Cor da Categoria de Risco
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

  // Plota Checklist de Validação Cruzada (Cross-Validation)
  renderCheckliItem("chkNome", "Nome consistente entre documentos", validacao.nome_consistente_entre_documentos);
  renderCheckliItem("chkNasc", "Data de nascimento consistente", validacao.data_nascimento_consistente);
  renderCheckliItem("chkId", "Documento de identidade presente", validacao.documento_identificacao_presente);
  renderCheckliItem("chkRenda", "Comprovante de renda anexado", validacao.comprovante_renda_presente);
  renderCheckliItem("chkExtrato", "Extrato bancário de liquidez presente", validacao.extrato_bancario_presente);

  // Plota Tabela de Linhagem e Herança de Arquivos
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

function procRendaMaxima(docs) {
  let max = 0;
  docs.forEach(d => {
    const val = d.campos_extraidos?.amount_numeric || d.campos_extraidos?.["Gross Pay"] || d.campos_extraidos?.renda_bruta_informada || 0;
    const numeric = parseFloat(String(val).replace(/[^0-9.]/g, '')) || 0;
    if (numeric > max) max = numeric;
  });
  return max;
}

function procSaldoMaximo(docs) {
  let max = 0;
  docs.forEach(d => {
    const val = d.campos_extraidos?.saldo_bancario_fechamento || d.campos_extraidos?.balance || d.campos_extraidos?.amount || 0;
    const numeric = parseFloat(String(val).replace(/[^0-9.]/g, '')) || 0;
    if (numeric > max) max = numeric;
  });
  return max;
}

function renderFileList(files) {
  fileList.innerHTML = "";
  if (files.length === 0) {
    fileList.textContent = "Nenhum arquivo selecionado."; return;
  }
  files.forEach((file, index) => {
    const item = document.createElement("div"); item.className = "file-item";
    item.innerHTML = `<span class="file-name">${index + 1}. ${file.name}</span><span class="file-size">${(file.size/1024).toFixed(2)} KB</span>`;
    fileList.appendChild(item);
  });
}

function updateStatus(message, type) {
  statusBox.textContent = message; statusBox.className = "status-box";
  if (type === "processing") statusBox.classList.add("status-processing");
  if (type === "success") statusBox.classList.add("status-success");
  if (type === "error") statusBox.classList.add("status-error");
}

function setLoading(isLoading) {
  submitButton.disabled = isLoading;
  submitButton.textContent = isLoading ? "Processando Esteira..." : "Iniciar Processamento Inteligente";
}