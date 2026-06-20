const uploadForm = document.getElementById("uploadForm");
const documentsInput = document.getElementById("documents");
const fileList = document.getElementById("fileList");
const statusBox = document.getElementById("statusBox");
const submitButton = document.getElementById("submitButton");
const toggleScore = document.getElementById("toggleScore");
const exportExcelBtn = document.getElementById("exportExcelBtn");

const API_URL = "https://zrky80ks0l.execute-api.us-east-1.amazonaws.com/dev/";
const MIN_FILES = 1;
const MAX_FILES = 8;
let pollingInterval = null; 
let cacheDadosAtuais = null; // Armazena o JSON na memória para exportar para o Excel

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
    updateStatus("Envie no máximo 8 documentos por classificação.", "error");
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
    updateStatus("Registrando lote e coletando credenciais de storage do S3...", "processing");

    const uploadInstructions = await getUploadInstructions(payloadToLambda);

    updateStatus("Enviando documentos diretamente para o S3 de forma segura...", "processing");

    await uploadFilesToS3(files, uploadInstructions);

    updateStatus(
      `Sucesso! Lote enviado. O processamento reativo foi iniciado na AWS. Monitorando progresso...`,
      "processing"
    );

    uploadForm.reset();
    renderFileList([]);

    // Dispara o monitoramento passando a intenção do analista sobre calcular o score ou não
    iniciarMonitoramentoLote(uploadInstructions.package_id, toggleScore.checked);

  } catch (error) {
    updateStatus(
      error.message || "Não foi possível concluir o envio. Verifique as permissões e tente novamente.",
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
  summary.textContent = `${files.length} arquivo(s) selecionado(s).`;
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
  return data;
}

async function uploadFilesToS3(files, uploadInstructions) {
  for (const file of files) {
    const instruction = uploadInstructions.uploads[file.name];
    if (!instruction) {
      throw new Error(`Instrução de upload não encontrada para o arquivo: ${file.name}`);
    }

    await fetch(instruction.uploadUrl, {
      method: "PUT",
      headers: { "Content-Type": file.type || "application/octet-stream" },
      body: file
    });
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

function iniciarMonitoramentoLote(packageId, deveCalcularScore) {
  if (pollingInterval) clearInterval(pollingInterval);

  pollingInterval = setInterval(async () => {
    try {
      const response = await fetch(`${API_URL}v1/packages/${packageId}`);
      if (!response.ok) return;

      const result = await response.json();
      
      if (result.status === "PROCESSING") {
        updateStatus(`Lote em processamento na AWS... Extraindo tabelas estruturais via Bedrock BDA.`, "processing");
      } 
      else if (result.status === "COMPLETED") {
        clearInterval(pollingInterval);
        setLoading(false);
        updateStatus("Análise estrutural finalizada com sucesso!", "success");
        
        cacheDadosAtuais = result.dados_extraidos;
        
        // Renderiza o painel aplicando a regra de negócio condicional informada
        plotarDashboardAnalitico(result.dados_extraidos, deveCalcularScore, packageId, result.bda_output_bucket);
        
        if (deveCalcularScore) {
          const score = result.dados_extraidos?.cliente?.score_credito?.valor ?? 0;
          document.getElementById("modalMetaScoreWrapper").style.display = "block";
          document.getElementById("modalScore").textContent = `${score} pontos`;
        } else {
          document.getElementById("modalMetaScoreWrapper").style.display = "none";
        }
        
        document.getElementById("successModal").style.display = "flex";
      } 
      else if (result.status === "FAILED") {
        clearInterval(pollingInterval);
        setLoading(false);
        updateStatus(`A esteira falhou: ${result.erro_processamento || "Erro interno BDA"}`, "error");
      }
    } catch (err) {
      console.error("Erro no polling de sincronia:", err);
    }
  }, 4000);
}

function fecharModalEVerResultado() {
  document.getElementById("successModal").style.display = "none";
  document.getElementById("analyticsDashboard").scrollIntoView({ behavior: "smooth" });
}

function plotarDashboardAnalitico(dados, deveCalcularScore, packageId, outputBucket) {
  if (!dados) return;

  const cliente = dados.cliente || {};
  const sistema = dados.sistema || {};
  const validacao = dados.validacao || {};
  const docs = dados.documentos_analisados || [];

  document.getElementById("analyticsDashboard").style.display = "block";

  // 🚀 CONTROLE CONDICIONAL SÊNIOR: Exibe ou esconde o Score Cadastral na Tela
  const scoreSection = document.getElementById("scoreConsolidadoSection");
  if (deveCalcularScore) {
    scoreSection.style.display = "block";
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
  } else {
    scoreSection.style.display = "none";
  }

  // 🚀 MONTAGEM DOS HIPERLINKS DE INSPEÇÃO DO S3
  const tableBody = document.getElementById("tableDocsBody");
  tableBody.innerHTML = "";
  
  docs.forEach(d => {
    const row = document.createElement("tr");
    
    // Constrói dinamicamente a URL física pública do S3 do JSON estruturado individual
    const s3UrlJson = `https://${outputBucket || 'credifacil-docs-saida-dev'}.s3.amazonaws.com/${d.s3_key_origem.replace('packages/', 'results/').replace('.pdf', '_structured.json')}`;

    row.innerHTML = `
      <td style="padding: 10px; border: 1px solid #cbd5e1; font-weight: bold;">${d.tipo_documento}</td>
      <td style="padding: 10px; border: 1px solid #cbd5e1; color: #475569;">${d.arquivo_original}</td>
      <td style="padding: 10px; border: 1px solid #cbd5e1;"><span class="header-badge" style="background: ${d.status_extracao === 'sucesso' ? '#eff6ff' : '#f8fafc'}; color: ${d.status_extracao === 'sucesso' ? '#1e40af' : '#64748b'}; border: none; padding: 4px 10px;">${d.status_extracao}</span></td>
      <td style="padding: 10px; border: 1px solid #cbd5e1; font-weight: 500;">${(d.confianca_media * 100).toFixed(1)}%</td>
      <td style="padding: 10px; border: 1px solid #cbd5e1; text-align: center;">
        <a href="${s3UrlJson}" target="_blank" style="color: #2563eb; font-weight: bold; text-decoration: none;">📄 Inspecionar JSON</a>
      </td>
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

// 🚀 ENGENHARIA DE MATRIZ: EXPORTAÇÃO COMPLETA DOS METADADOS DE NEGÓCIO PARA EXCEL (CSV)
exportExcelBtn.addEventListener("click", () => {
  if (!cacheDadosAtuais || !cacheDadosAtuais.documentos_analisados) {
    alert("Nenhum dado localizado para exportação.");
    return;
  }

  let csvContent = "data:text/csv;charset=utf-8,\uFEFF";
  
  // Cabeçalho estrutural da planilha
  csvContent += "Tipo Documento;Arquivo Original;Status Extracao;Confianca OCR;Chave Extraida;Valor Extraido\n";

  // Varre a árvore de documentos e achata os dicionários JSON complexos em linhas planas
  cacheDadosAtuais.documentos_analisados.forEach(doc => {
    const tipo = doc.tipo_documento;
    const arquivo = doc.arquivo_original;
    const status = doc.status_extracao;
    const confianca = `${(doc.confianca_media * 100).toFixed(1)}%`;
    const campos = doc.campos_extraidos || {};

    // Se o documento tiver chaves internas extraídas pela IA, achata uma por uma na tabela
    const chavesCampos = Object.keys(campos);
    if (chavesCampos.length > 0) {
      chavesCampos.forEach(chave => {
        let valor = campos[chave];
        if (typeof valor === 'object') valor = JSON.stringify(valor).replace(/;/g, ',');
        csvContent += `${tipo};${arquivo};${status};${confianca};${chave};${String(valor).replace(/;/g, ',')}\n`;
      });
    } else {
      csvContent += `${tipo};${arquivo};${status};${confianca};N/A;N/A\n`;
    }
  });

  // Dispara o download nativo do arquivo no client do navegador mapeado para Excel
  const encodedUri = encodeURI(csvContent);
  const downloadLink = document.createElement("a");
  downloadLink.setAttribute("href", encodedUri);
  downloadLink.setAttribute("download", `metadados_idp_lote_${cacheDadosAtuais.sistema?.ultimo_package_vinculado?.package_id || 'analise'}.csv`);
  document.body.appendChild(downloadLink);
  
  downloadLink.click();
  document.body.removeChild(downloadLink);
});