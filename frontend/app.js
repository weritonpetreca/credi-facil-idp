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

  const deveCalcularScore = toggleScore.checked;

  const payloadToLambda = {
    documentos: files.map((file) => file.name),
    execute_score: deveCalcularScore 
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
          const score = result.dados_extraidos?.cliente?.score_credito?.valor ?? 
                        result.dados_extraidos?.cliente?.score_atribuido ?? 0;
          document.getElementById("modalMetaScoreWrapper").style.display = "block";
          document.getElementById("modalScore").textContent = `${score} pontos`;
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
  
  // 🏢 SEÇÃO 1: Renderização Condicional e Defensiva do Score do Cliente
  if (deveCalcularScore && dados.cliente) {
    scoreSection.style.display = "block";
    
    // Vinculação de metadados do proponente mestre
    document.getElementById("resNome").textContent = dados.cliente.nome || "Não Identificado";
    document.getElementById("resDoc").textContent = dados.cliente.documento_identificacao || "Não Informado";
    document.getElementById("badgeModelo").textContent = dados.sistema?.processamento?.modelo_utilizado || "Amazon Nova Pro";
    
    // Cálculo dinâmico e seguro de indicadores agregados promovidos
    const docs = dados.documentos_analisados || [];
    document.getElementById("resRenda").textContent = `US$ ${calcularMaiorValorCampo(docs, ['amount_numeric', 'Gross Pay', 'wages_tips_other_compensation']).toFixed(2)}`;
    document.getElementById("resSaldo").textContent = `US$ ${calcularMaiorValorCampo(docs, ['saldo_bancario_fechamento', 'closing_balance', 'balance']).toFixed(2)}`;
    
    // Atribuição de Score e Badges de Risco
    const scoreVal = dados.cliente.score_credito?.valor ?? dados.cliente.score_atribuido ?? 0;
    const riscoCat = (dados.cliente.classificacao_risco?.categoria || "INCONCLUSIVO").toLowerCase();
    
    document.getElementById("resScoreValue").textContent = scoreVal;
    
    const catElement = document.getElementById("resRiscoCategoria");
    catElement.textContent = riscoCat.toUpperCase();
    
    if (riscoCat === "baixo") {
      catElement.style.background = "#d1fae5"; catElement.style.color = "#065f46";
    } else if (riscoCat === "medio") {
      catElement.style.background = "#fef3c7"; catElement.style.color = "#92400e";
    } else {
      catElement.style.background = "#fee2e2"; catElement.style.color = "#991b1b";
    }
    
    document.getElementById("resJustificativaBox").textContent = dados.cliente.classificacao_risco?.justificativa || "Sem parecer cadastrado.";
    
    // População estruturada do Checklist de Regras de Negócio (KYC Cruzado)
    const val = dados.validacao || {};
    renderChecklistItem("chkNome", "Nome consistente entre todos os documentos", val.nome_consistente_entre_documentos);
    renderChecklistItem("chkNasc", "Data de nascimento consistente", val.data_nascimento_consistente);
    renderChecklistItem("chkId", "Documento de identidade presente", val.documento_identificacao_presente);
    renderChecklistItem("chkRenda", "Comprovante de renda anexado", val.comprovante_renda_presente);
    renderChecklistItem("chkExtrato", "Extrato bancário de liquidez presente", val.extrato_bancario_presente);
  } else {
    scoreSection.style.display = "none";
  }

  // 📂 SEÇÃO 2: Renderização Incondicional da Linhagem Física de Documentos
  document.getElementById("analyticsDashboard").style.display = "block";
  const tableBody = document.getElementById("tableDocsBody");
  tableBody.innerHTML = "";
  
  const docs = dados.documentos_analisados || [];
  docs.forEach((d, index) => {
    const row = document.createElement("tr");
    
    // 🎯 DESACOPLAMENTO ABSOLUTO: Consome a chave final estruturada vinda do contrato do Backend (Evita 404 por string hack)
    const bucketFinal = outputBucket || "credifacil-docs-saida-dev";
    const keyResultado = d.s3_key_resultado || `results/${String(d.tipo_documento).toLowerCase()}/${String(d.subtipo_documento || '').toLowerCase()}/${dados.sistema?.ultimo_package_vinculado?.package_id}/${d.arquivo_original.replace('.pdf', '')}_structured.json`;
    const s3UrlJson = `https://${bucketFinal}.s3.amazonaws.com/${keyResultado}`;

    row.innerHTML = `
      <td style="padding: 10px; border: 1px solid #cbd5e1; font-weight: bold;">${d.tipo_documento}</td>
      <td style="padding: 10px; border: 1px solid #cbd5e1; color: #475569;">${d.arquivo_original}</td>
      <td style="padding: 10px; border: 1px solid #cbd5e1;"><span class="header-badge" style="background: #eff6ff; color: #1e40af; border: none; padding: 4px 10px;">${d.status_extracao || 'sucesso'}</span></td>
      <td style="padding: 10px; border: 1px solid #cbd5e1; font-weight: 500;">${((d.confianca_media || 1.0) * 100).toFixed(1)}%</td>
      <td style="padding: 10px; border: 1px solid #cbd5e1; text-align: center; display: flex; gap: 8px; justify-content: center;">
        <a href="${s3UrlJson}" target="_blank" style="color: #2563eb; font-weight: bold; font-size: 13px; text-decoration: none; padding: 4px 8px; border: 1px solid #2563eb; border-radius: 6px; background: #fff;">📄 Ver JSON</a>
        <button id="exp-${index}" class="modal-btn" style="padding: 4px 8px; background: #10b981; font-size: 12px; margin:0; border-radius: 6px;">📊 Excel</button>
      </td>
    `;
    tableBody.appendChild(row);

    document.getElementById(`exp-${index}`).addEventListener("click", () => {
      exportarArquivoParaExcel(d);
    });
  });
}

function renderChecklistItem(elementId, text, status) {
  const el = document.getElementById(elementId);
  if (!el) return;
  if (status === true) {
    el.textContent = `✅ ${text}`; el.style.color = "#166534";
  } else if (status === false) {
    el.textContent = `❌ ${text}`; el.style.color = "#991b1b";
  } else {
    el.textContent = `⚪ ${text} (Não Avaliado)`; el.style.color = "#64748b";
  }
}

function calcularMaiorValorCampo(docs, chaves) {
  let max = 0.0;
  docs.forEach(d => {
    const campos = d.campos_extraidos || {};
    chaves.forEach(c => {
      const val = campos[c];
      if (val) {
        const num = parseFloat(String(val).replace(/[^0-9.]/g, '')) || 0.0;
        if (num > max) max = num;
      }
    });
  });
  return max;
}

// 🚀 EXPORTADOR INDIVIDUAL NATIVO DE METADADOS (Compatibilidade Regional Excel BR via Semicolon e BOM)
function exportarArquivoParaExcel(doc) {
  let csvContent = "data:text/csv;charset=utf-8,\uFEFF";
  csvContent += "Propriedade;Valor Extraido;Confianca Campo\n";

  const campos = doc.campos_extraidos || {};
  Object.keys(campos).forEach(chave => {
    let campoDados = campos[chave];
    let valor = campoDados;
    let conf = "100%";
    
    if (campoDados && typeof campoDados === 'object') {
      valor = campoDados.value !== undefined ? campoDados.value : JSON.dumps(campoDados);
      conf = campoDados.confidence !== undefined ? `${(campoDados.confidence * 100).toFixed(1)}%` : "100%";
    }
    
    csvContent += `${chave};${String(valor || 'null').replace(/;/g, ',')};${conf}\n`;
  });

  const encodedUri = encodeURI(csvContent);
  const downloadLink = document.createElement("a");
  downloadLink.setAttribute("href", encodedUri);
  downloadLink.setAttribute("download", `excel_metadados_${doc.arquivo_original.replace('.pdf', '')}.csv`);
  document.body.appendChild(downloadLink);
  
  downloadLink.click();
  document.body.removeChild(downloadLink);
}