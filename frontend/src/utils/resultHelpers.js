export function calcularMaiorValorCampo(docs, chaves) {
  let max = 0.0;
  (docs || []).forEach((doc) => {
    const campos = doc.campos_extraidos || {};
    chaves.forEach((chave) => {
      const val = campos[chave];
      if (val) {
        const num = parseFloat(String(val).replace(/[^0-9.]/g, "")) || 0.0;
        if (num > max) max = num;
      }
    });
  });
  return max;
}

export function exportarArquivoParaExcel(doc) {
  let csvContent = "data:text/csv;charset=utf-8,\uFEFF";
  csvContent += "Propriedade;Valor Extraido;Confianca Campo\n";

  const campos = doc.campos_extraidos || {};
  Object.keys(campos).forEach((chave) => {
    const campoDados = campos[chave];
    let valor = campoDados;
    let conf = "100%";

    if (campoDados && typeof campoDados === "object") {
      valor =
        campoDados.value !== undefined
          ? campoDados.value
          : JSON.stringify(campoDados);
      conf =
        campoDados.confidence !== undefined
          ? `${(campoDados.confidence * 100).toFixed(1)}%`
          : "100%";
    }

    csvContent += `${chave};${String(valor || "null").replace(/;/g, ",")};${conf}\n`;
  });

  const encodedUri = encodeURI(csvContent);
  const downloadLink = document.createElement("a");
  downloadLink.setAttribute("href", encodedUri);
  downloadLink.setAttribute(
    "download",
    `excel_metadados_${(doc.arquivo_original || "documento").replace(".pdf", "")}.csv`,
  );
  document.body.appendChild(downloadLink);
  downloadLink.click();
  document.body.removeChild(downloadLink);
}

export function buildDocumentRows(dados, executeScore, scoreVal, riscoCat) {
  const docs = [...(dados.documentos_analisados || [])];

  if (executeScore && dados.cliente) {
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
        classificacao_risco: (riscoCat || "").toUpperCase(),
        justificativa_analise:
          dados.cliente.classificacao_risco?.justificativa || "",
        validacao_nome: dados.validacao?.nome_consistente_entre_documentos
          ? "CONSISTENTE"
          : "DIVERGENTE",
        validacao_nascimento: dados.validacao?.data_nascimento_consistente
          ? "CONSISTENTE"
          : "DIVERGENTE",
        presenca_identidade: dados.validacao?.documento_identificacao_presente
          ? "PRESENTE"
          : "AUSENTE",
        presenca_renda: dados.validacao?.comprovante_renda_presente
          ? "PRESENTE"
          : "AUSENTE",
        presenca_extrato: dados.validacao?.extrato_bancario_presente
          ? "PRESENTE"
          : "AUSENTE",
      },
    });
  }

  return docs;
}

const TIPO_DOCUMENTO_LABELS = {
  documento_identificacao: "Documento de Identificação",
  comprovante_renda: "Comprovante de Renda",
  extrato_bancario: "Extrato Bancário",
  documento_imovel: "Documento do Imóvel",
  comprovante_complementar: "Comprovante Complementar",
  consolidado_cliente: "Consolidado do Cliente",
  pay_stub: "Holerite",
};

export function formatTipoDocumento(tipo) {
  if (!tipo) return "Documento não identificado";

  const normalized = String(tipo).toLowerCase();
  if (TIPO_DOCUMENTO_LABELS[normalized]) {
    return TIPO_DOCUMENTO_LABELS[normalized];
  }

  // Fallback: transforma snake_case/UPPER_CASE em "Texto Capitalizado"
  return normalized
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
