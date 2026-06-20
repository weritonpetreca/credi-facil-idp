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
  
  if (!scoreSection) {
    console.error("Elemento 'scoreConsolidadoSection' não foi encontrado no HTML DOM.");
    return;
  }

  // 🚀 ESCOPO ELEVADO: Declara as variáveis no topo para estarem disponíveis em toda a função
  let scoreVal = 0;
  let riscoCat = "INCONCLUSIVO";
  
  if (deveCalcularScore && dados.cliente) {
    scoreSection.style.display = "block";
    
    document.getElementById("resNome").textContent = dados.cliente.nome || "Não Identificado";
    document.getElementById("resDoc").textContent = dados.cliente.documento_identificacao || "Não Informado";
    document.getElementById("badgeModelo").textContent = dados.sistema?.processamento?.modelo_utilizado || "Amazon Nova Pro";
    
    const docsOriginal = dados.documentos_analisados || [];
    document.getElementById("resRenda").textContent = `US$ ${calcularMaiorValorCampo(docsOriginal, ['amount_numeric', 'Gross Pay', 'wages_tips_other_compensation']).toFixed(2)}`;
    document.getElementById("resSaldo").textContent = `US$ ${calcularMaiorValorCampo(docsOriginal, ['saldo_bancario_fechamento', 'closing_balance', 'balance']).toFixed(2)}`;
    
    scoreVal = dados.cliente.score_credito?.valor ?? dados.cliente.score_atribuido ?? 0;
    riscoCat = (dados.cliente.classificacao_risco?.categoria || "INCONCLUSIVO").toLowerCase();
    
    const scoreValueContainer = document.getElementById("resScoreValue");
    scoreValueContainer.innerHTML = `${scoreVal} <span id="helpScoreTrigger" style="cursor: pointer; font-size: 16px; margin-left: 8px; color: #3b82f6; border: 1px solid #3b82f6; border-radius: 50%; padding: 0px 6px; display: inline-block; font-weight: bold;" title="Clique para ver a regra de cálculo">?</span>`;
    
    const painelAntigo = document.getElementById("scoreExplainPanel");
    if (painelAntigo) painelAntigo.remove();

    const explainPanel = document.createElement("div");
    explainPanel.id = "scoreExplainPanel";
    explainPanel.style.display = "none";
    explainPanel.style.marginTop = "15px";
    explainPanel.style.padding = "15px";
    explainPanel.style.background = "#f8fafc";
    explainPanel.style.borderLeft = "4px solid #3b82f6";
    explainPanel.style.borderRadius = "4px";
    explainPanel.style.fontSize = "13px";
    explainPanel.style.color = "#334155";
    explainPanel.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
        <strong style="color: #1e3a8a; font-size: 14px;">🧮 Regra de Cálculo do Application Scorecard:</strong>
        <span id="closeExplainPanel" style="cursor: pointer; font-weight: bold; color: #94a3b8;">[Recolher]</span>
      </div>
      <p style="margin: 4px 0;">O cálculo segue as diretrizes rígidas de governança de risco financeiro:</p>
      <ul style="margin: 5px 0; padding-left: 20px; line-height: 1.5;">
        <li><strong>Pontuação Base Incondicional:</strong> 300 Pontos (Mínimo de entrada).</li>
        <li><strong>Pilar KYC (Até 150 pts):</strong> +50 pts por consistência de Nome, +50 pts por Data de Nascimento e +50 pts por Documento Oficial verificado.</li>
        <li><strong>Capacidade de Renda (Até 450 pts):</strong> Baseado no maior contracheque/W2 (Ex: Renda &ge; US$ 5.000 garante o teto de +450 pts).</li>
        <li><strong>Colchão de Liquidez (Até 400 pts):</strong> Saldo de encerramento do extrato bancário (Ex: Saldo &ge; US$ 10.000 garante +400 pts).</li>
      </ul>
      <p style="margin-top: 5px; font-weight: 500; color: #0f172a;"><em>Fórmula: Pontuação Base (300) + Pontos KYC + Pontos Renda + Pontos Liquidez = Score Final (Máx 1000).</em></p>
    `;
    
    scoreValueContainer.parentNode.appendChild(explainPanel);

    document.getElementById("helpScoreTrigger").addEventListener("click", () => {
      explainPanel.style.display = explainPanel.style.display === "none" ? "block" : "none";
    });
    document.getElementById("closeExplainPanel").addEventListener("click", () => {
      explainPanel.style.display = "none";
    });
    
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
    
    const val = dados.validacao || {};
    renderChecklistItem("chkNome", "Nome consistente entre todos os documentos", val.nome_consistente_entre_documentos);
    renderChecklistItem("chkNasc", "Data de nascimento consistente", val.data_nascimento_consistente);
    renderChecklistItem("chkId", "Documento de identidade presente", val.documento_identificacao_presente);
    renderChecklistItem("chkRenda", "Comprovante de renda anexado", val.comprovante_renda_presente);
    renderChecklistItem("chkExtrato", "Extrato bancário de liquidez presente", val.extrato_bancario_presente);
  } else {
    scoreSection.style.display = "none";
  }

  document.getElementById("analyticsDashboard").style.display = "block";
  const tableBody = document.getElementById("tableDocsBody");
  tableBody.innerHTML = "";
  
  let docs = [...(dados.documentos_analisados || [])];
  if (deveCalcularScore && dados.cliente) {
    docs.push({
      tipo_documento: "CONSOLIDADO_CLIENTE",
      arquivo_original: "customer_consolidated.json",
      status_extracao: "sucesso",
      confianca_media: 1.0,
      s3_url_final: dados.s3_url_consolidado,
      s3_url_excel: dados.s3_url_excel_consolidado,
      campos_extraidos: {
        nome_completo_proponente: dados.cliente.nome,
        documento_identificacao: dados.cliente.documento_identificacao,
        score_atribuido: scoreVal,
        classificacao_risco: riscoCat.toUpperCase(),
        justificativa_analise: dados.cliente.classificacao_risco?.justificativa || "",
        validacao_nome: dados.validacao?.nome_consistente_entre_documentos ? "CONSISTENTE" : "DIVERGENTE",
        validacao_nascimento: dados.validacao?.data_nascimento_consistente ? "CONSISTENTE" : "DIVERGENTE",
        presenca_identidade: dados.validacao?.documento_identificacao_presente ? "PRESENTE" : "AUSENTE",
        presenca_renda: dados.validacao?.comprovante_renda_presente ? "PRESENTE" : "AUSENTE",
        presenca_extrato: dados.validacao?.extrato_bancario_presente ? "PRESENTE" : "AUSENTE"
      }
    });
  }

  docs.forEach((d, index) => {
    const row = document.createElement("tr");
    const s3UrlJson = d.s3_url_final || `https://${outputBucket || 'credifacil-docs-saida-dev'}.s3.amazonaws.com/${d.s3_key_resultado}`;

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
      if (d.s3_url_excel) {
        window.open(d.s3_url_excel, "_blank");
      } else {
        exportarArquivoParaExcel(d);
      }
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

function exportarArquivoParaExcel(doc) {
  let csvContent = "data:text/csv;charset=utf-8,\uFEFF";
  csvContent += "Propriedade;Valor Extraido;Confianca Campo\n";

  const campos = doc.campos_extraidos || {};
  Object.keys(campos).forEach(chave => {
    let campoDados = campos[chave];
    let valor = campoDados;
    let conf = "100%";
    
    if (campoDados && typeof campoDados === 'object') {
      valor = campoDados.value !== undefined ? campoDados.value : JSON.stringify(campoDados); // 🎯 CORREÇÃO EXCEL: Alterado de JSON.dumps para JSON.stringify
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