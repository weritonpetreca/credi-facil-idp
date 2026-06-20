import "./ResultPanel.css";

const RISK_META = {
  baixo: { label: "Risco baixo", color: "#A6FF00" },
  medio: { label: "Risco médio", color: "#FFB800" },
  alto: { label: "Risco alto", color: "#FF4D6D" },
};

const INCOME_KEYS = ["amount_numeric", "Gross Pay", "renda_bruta_informada"];
const BALANCE_KEYS = ["saldo_bancario_fechamento", "balance", "amount"];

function extractMaxValue(docs, keys) {
  let max = 0;
  (docs || []).forEach((doc) => {
    keys.forEach((key) => {
      const val = doc.campos_extraidos?.[key];
      if (val) {
        const numeric = parseFloat(String(val).replace(/[^0-9.]/g, "")) || 0;
        if (numeric > max) max = numeric;
      }
    });
  });
  return max;
}

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

export default function ResultPanel({ data }) {
  if (!data) return null;

  const cliente = data.cliente || {};
  const sistema = data.sistema || {};
  const validacao = data.validacao || {};
  const documentos = data.documentos_analisados || [];

  const risco = RISK_META[cliente.classificacao_risco?.categoria] || {
    label: (
      cliente.classificacao_risco?.categoria || "inconclusivo"
    ).toUpperCase(),
    color: "#8B93A8",
  };

  const renda = extractMaxValue(documentos, INCOME_KEYS);
  const saldo = extractMaxValue(documentos, BALANCE_KEYS);

  return (
    <div className="result-panel animate-fade-up">
      <div className="result-header">
        <div>
          <span className="result-eyebrow">Resultado da análise</span>
          <h3 className="result-title">{cliente.nome || "Não identificado"}</h3>
          <p className="result-doc">
            {cliente.documento_identificacao || "Documento não fornecido"}
          </p>
        </div>
        <div className="score-badge">
          <span className="score-value">
            {cliente.score_credito?.valor ?? 0}
          </span>
          <span className="score-label">pontos</span>
        </div>
      </div>

      <div className="result-stats">
        <div className="stat">
          <span className="stat-label">Classificação de risco</span>
          <span className="stat-value" style={{ color: risco.color }}>
            {risco.label}
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">Modelo utilizado</span>
          <span className="stat-value">
            {sistema.processamento?.modelo_utilizado || "Amazon Nova Pro"}
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">Renda identificada</span>
          <span className="stat-value">{formatUSD(renda)}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Saldo bancário</span>
          <span className="stat-value">{formatUSD(saldo)}</span>
        </div>
      </div>

      {cliente.classificacao_risco?.justificativa && (
        <div className="result-summary">
          <span className="result-block-label">Justificativa</span>
          <p>{cliente.classificacao_risco.justificativa}</p>
        </div>
      )}

      <div className="result-checks">
        <span className="result-block-label">Validação documental</span>
        <ul>
          <CheckItem
            label="Nome consistente entre documentos"
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

      {documentos.length > 0 && (
        <div className="result-docs">
          <span className="result-block-label">Documentos processados</span>
          <div className="doc-table">
            <div className="doc-table-head">
              <span>Tipo</span>
              <span>Arquivo</span>
              <span>Status</span>
              <span>Confiança</span>
            </div>
            {documentos.map((doc, i) => (
              <div key={i} className="doc-table-row">
                <span className="doc-type-cell">{doc.tipo_documento}</span>
                <span className="doc-name-cell">{doc.arquivo_original}</span>
                <span
                  className={`doc-status-cell ${doc.status_extracao === "sucesso" ? "ok" : "neutral"}`}
                >
                  {doc.status_extracao}
                </span>
                <span className="doc-conf-cell">
                  {doc.confianca_media != null
                    ? `${(doc.confianca_media * 100).toFixed(1)}%`
                    : "—"}
                </span>
              </div>
            ))}
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
