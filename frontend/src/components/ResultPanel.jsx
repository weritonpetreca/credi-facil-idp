import "./ResultPanel.css";
import ScoreExplainPanel from "./ScoreExplainPanel";
import {
  calcularMaiorValorCampo,
  exportarArquivoParaExcel,
  buildDocumentRows,
  formatTipoDocumento,
} from "../utils/resultHelpers";

const RISK_META = {
  baixo: { label: "Risco baixo", color: "#A6FF00" },
  medio: { label: "Risco médio", color: "#FFB800" },
  alto: { label: "Risco alto", color: "#FF4D6D" },
};

const INCOME_KEYS = [
  "amount_numeric",
  "Gross Pay",
  "wages_tips_other_compensation",
];
const BALANCE_KEYS = [
  "saldo_bancario_fechamento",
  "closing_balance",
  "balance",
];

function formatUSD(value) {
  return `US$ ${value.toFixed(2)}`;
}

function CheckItem({ label, status }) {
  let icon = "○";
  let cls = "neutral";
  if (status === true) {
    icon = "✓";
    cls = "ok";
  }
  if (status === false) {
    icon = "✕";
    cls = "fail";
  }

  return (
    <li className={`check-item ${cls}`}>
      <span className="check-icon">{icon}</span>
      <span>
        {label}
        {status === null || status === undefined ? " (não avaliado)" : ""}
      </span>
    </li>
  );
}

export default function ResultPanel({ data, executeScore, outputBucket }) {
  if (!data) return null;

  const cliente = data.cliente || {};
  const sistema = data.sistema || {};
  const validacao = data.validacao || {};
  const documentosOriginais = data.documentos_analisados || [];

  const showScore = executeScore && !!cliente;

  const scoreVal = cliente.score_credito?.valor ?? cliente.score_atribuido ?? 0;
  const riscoCat = (
    cliente.classificacao_risco?.categoria || "inconclusivo"
  ).toLowerCase();
  const risco = RISK_META[riscoCat] || {
    label: riscoCat.toUpperCase(),
    color: "#8B93A8",
  };

  const renda = calcularMaiorValorCampo(documentosOriginais, INCOME_KEYS);
  const saldo = calcularMaiorValorCampo(documentosOriginais, BALANCE_KEYS);

  const docs = buildDocumentRows(data, showScore, scoreVal, riscoCat);

  const handleExcelClick = (doc) => {
    if (doc.s3_url_excel) {
      window.open(doc.s3_url_excel, "_blank");
    } else {
      exportarArquivoParaExcel(doc);
    }
  };

  return (
    <div className="result-panel animate-fade-up">
      <div className="thanks-banner">
        <span className="thanks-icon">✓</span>
        <div>
          <p className="thanks-title">Obrigado pela paciência!</p>
          <p className="thanks-sub">
            Este é o resultado da sua análise, gerado em tempo real pela nossa
            esteira de IA.
          </p>
        </div>
      </div>

      {showScore && (
        <>
          <div className="result-header">
            <div>
              <span className="result-eyebrow">
                Relatório consolidado de crédito
              </span>
              <h3 className="result-title">
                {cliente.nome || "Não identificado"}
              </h3>
              <p className="result-doc">
                {cliente.documento_identificacao || "Documento não fornecido"}
              </p>
            </div>
            <span className="model-badge">
              {sistema.processamento?.modelo_utilizado || "Amazon Nova Pro"}
            </span>
          </div>

          <div className="result-main-grid">
            <div className="result-facts">
              <div className="fact">
                <span className="fact-label">Renda bruta estimada</span>
                <span className="fact-value">{formatUSD(renda)}</span>
              </div>
              <div className="fact">
                <span className="fact-label">Saldo bancário de fechamento</span>
                <span className="fact-value">{formatUSD(saldo)}</span>
              </div>
            </div>

            <div className="score-box">
              <span className="score-box-label">
                Score de crédito atribuído
              </span>
              <div className="score-box-value-row">
                <span className="score-box-value">{scoreVal}</span>
                <ScoreExplainPanel />
              </div>
              <span
                className="risk-pill"
                style={{ color: risco.color, background: risco.color + "1A" }}
              >
                {risco.label}
              </span>
            </div>
          </div>

          {cliente.classificacao_risco?.justificativa && (
            <div className="result-summary">
              <span className="result-block-label">Parecer da análise</span>
              <p>{cliente.classificacao_risco.justificativa}</p>
            </div>
          )}

          <div className="result-checks">
            <span className="result-block-label">
              Checklist de consistência
            </span>
            <ul>
              <CheckItem
                label="Nome consistente entre todos os documentos"
                status={validacao.nome_consistente_entre_documentos}
              />
              <CheckItem
                label="Data de nascimento consistente"
                status={validacao.data_nascimento_consistente}
              />
              <CheckItem
                label="Documento de identidade presente"
                status={validacao.documento_identificacao_presente}
              />
              <CheckItem
                label="Comprovante de renda anexado"
                status={validacao.comprovante_renda_presente}
              />
              <CheckItem
                label="Extrato bancário de liquidez presente"
                status={validacao.extrato_bancario_presente}
              />
            </ul>
          </div>
        </>
      )}

      {docs.length > 0 && (
        <div className="result-docs">
          <span className="result-block-label">
            Linhagem física e metadados dos arquivos
          </span>
          <div className="doc-table">
            <div className="doc-table-head">
              <span>Tipo</span>
              <span>Arquivo</span>
              <span>Status</span>
              <span>Confiança</span>
              <span>Ação</span>
            </div>
            {docs.map((doc, i) => {
              const s3UrlJson =
                doc.s3_url_final ||
                (doc.s3_key_resultado
                  ? `https://${outputBucket || "credifacil-docs-saida-dev"}.s3.amazonaws.com/${doc.s3_key_resultado}`
                  : null);

              return (
                <div key={i} className="doc-table-row">
                  <span className="doc-type-cell">
                    {formatTipoDocumento(doc.tipo_documento)}
                  </span>
                  <span className="doc-name-cell">{doc.arquivo_original}</span>
                  <span
                    className={`doc-status-cell ${doc.status_extracao === "sucesso" ? "ok" : "neutral"}`}
                  >
                    {doc.status_extracao || "sucesso"}
                  </span>
                  <span className="doc-conf-cell">
                    {((doc.confianca_media ?? 1.0) * 100).toFixed(1)}%
                  </span>
                  <span className="doc-actions-cell">
                    {s3UrlJson && (
                      <a
                        href={s3UrlJson}
                        target="_blank"
                        rel="noreferrer"
                        className="doc-action-link"
                      >
                        Ver JSON
                      </a>
                    )}
                    <button
                      type="button"
                      className="doc-action-btn"
                      onClick={() => handleExcelClick(doc)}
                    >
                      Excel
                    </button>
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <details className="raw-json">
        <summary>Ver JSON completo</summary>
        <pre>{JSON.stringify(data, null, 2)}</pre>
      </details>
    </div>
  );
}
