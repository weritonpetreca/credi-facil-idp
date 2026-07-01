import { useState, useEffect } from "react";
import FileDropZone from "./components/FileDropZone";
import StatusTerminal from "./components/StatusTerminal";
import ResultPanel from "./components/ResultPanel";
import SuccessModal from "./components/SuccessModal";
import Footer from "./components/Footer";
import HourglassBackdrop from "./components/HourglassBackdrop";
import ThemeToggle from "./components/ThemeToggle";
import { useDocumentPipeline } from "./hooks/useDocumentPipeline";
import { useTheme } from "./hooks/useTheme";
import "./App.css";

const PHASE_LABEL = {
  idle: "Pronto para receber documentos",
  preparing: "Registrando lote...",
  uploading: "Enviando documentos...",
  waiting: "Processando com IA...",
  revision: "Aguardando revisão manual de dados",
  done: "Concluído",
  error: "Erro no processamento",
};

export default function App() {
  const [files, setFiles] = useState([]);
  const [scoreRequested, setScoreRequested] = useState(true);
  const [modalDismissed, setModalDismissed] = useState(false);
  const { theme, toggleTheme } = useTheme();

  const [token, setToken] = useState(sessionStorage.getItem("auth_token") || null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [authLoading, setAuthLoading] = useState(false);

  // 🚀 ESTADO LOCAL PARA CAPTURAR AS CORREÇÕES EM TEMPO REAL
  const [correctionsForm, setCorrectionsForm] = useState({});

  const {
    phase,
    logs,
    result,
    executeScore,
    outputBucket,
    errorMessage,
    startedAt,
    finishedAt,
    currentPackageId,
    revisionFields,
    upload,
    submitReview,
    reset,
  } = useDocumentPipeline();

  const isBusy = ["preparing", "uploading", "waiting"].includes(phase) || authLoading;

  // Popula o formulário com os valores padrões de baixa confiança para facilitar a digitação
  useEffect(() => {
    if (phase === "revision" && revisionFields.length > 0) {
      const initialValues = {};
      revisionFields.forEach((field) => {
        initialValues[field.campo_afetado] = field.valor_bruto || "";
      });
      setCorrectionsForm(initialValues);
    }
  }, [phase, revisionFields]);

  const handleLogin = async (e) => {
    e.preventDefault();
    setAuthLoading(true);
    setAuthError("");

    try {
      const response = await fetch("https://cognito-idp.us-east-1.amazonaws.com/", {
        method: "POST",
        headers: {
          "Content-Type": "application/x-amz-json-1.1",
          "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
        },
        body: JSON.stringify({
          AuthFlow: "USER_PASSWORD_AUTH",
          ClientId: import.meta.env.VITE_USER_POOL_CLIENT_ID,
          AuthParameters: { USERNAME: email, PASSWORD: password },
        }),
      });

      const data = await response.json();
      if (!response.ok) throw new Error(data.message || "Credenciais inválidas.");

      const idToken = data.AuthenticationResult.IdToken;
      setToken(idToken);
      sessionStorage.setItem("auth_token", idToken);
    } catch (err) {
      setAuthError(err.message);
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = () => {
    setToken(null);
    sessionStorage.removeItem("auth_token");
    handleReset();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    await upload(files, scoreRequested, token);
  };

  // 🚀 MANIPULADOR DE SUBMISSÃO DA REVISÃO MANUAL (POST DIRETO DA API)
  const handleReviewSubmit = async (e) => {
    e.preventDefault();
    const success = await submitReview(correctionsForm, token);
    if (success) {
      setCorrectionsForm({});
    }
  };

  const handleReset = () => {
    reset();
    setFiles([]);
    setModalDismissed(false);
    setCorrectionsForm({});
  };

  const modalOpen = phase === "done" && !!result && !modalDismissed;
  const scoreVal = result?.cliente?.score_credito?.valor ?? result?.cliente?.score_atribuido ?? 0;

  return (
    <div className="page">
      <HourglassBackdrop active={isBusy} />
      <header className="header">
        <div className="header-inner">
          <div className="brand">
            <div className="logo-mark">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
                <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z" strokeLinecap="round" strokeLinejoin="round" />
                <polyline points="9 22 9 12 15 12 15 22" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <span className="brand-name">CrediFácil</span>
          </div>
          <div className="header-actions">
            {token && (
              <button onClick={handleLogout} className="btn-ghost" style={{ padding: "6px 12px", fontSize: "13px", marginRight: "8px" }}>
                🚪 Encerrar Sessão
              </button>
            )}
            <span className="header-pill"><span className="pill-dot" />Análise por IA generativa</span>
            <ThemeToggle theme={theme} onToggle={toggleTheme} />
          </div>
        </div>
      </header>

      <main className="main">
        <section className="hero">
          <span className="hero-eyebrow">Processamento Inteligente de Documentos</span>
          <h1 className="hero-title">Envie seus documentos.<br /><span className="hero-title-accent">A IA faz o resto.</span></h1>
          <p className="hero-sub">Nossa IA analisa identidade, renda e documentação automaticamente — você acompanha cada etapa em tempo real.</p>
        </section>

        <section className="grid">
          <div className="col-form">
            <div className="card">
              {!token ? (
                <form onSubmit={handleLogin} className="animate-fade-up">
                  <div style={{ marginBottom: "16px" }}>
                    <h2 style={{ fontSize: "18px", fontWeight: "600", marginBottom: "4px" }}>🔒 Área Restrita</h2>
                    <p style={{ fontSize: "13px", color: "var(--text-muted)" }}>Autentique-se para liberar a esteira de crédito.</p>
                  </div>
                  <div style={{ marginBottom: "12px" }}>
                    <label style={{ display: "block", fontSize: "12px", marginBottom: "6px", fontWeight: "500" }}>E-mail do analista</label>
                    <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} disabled={authLoading} placeholder="analista@credifacil.com" style={{ width: "100%", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)", background: "var(--bg-input)", color: "var(--text-main)" }} />
                  </div>
                  <div style={{ marginBottom: "16px" }}>
                    <label style={{ display: "block", fontSize: "12px", marginBottom: "6px", fontWeight: "500" }}>Senha de acesso</label>
                    <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} disabled={authLoading} placeholder="••••••••" style={{ width: "100%", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)", background: "var(--bg-input)", color: "var(--text-main)" }} />
                  </div>
                  {authError && <div className="inline-error" style={{ marginBottom: "16px" }}>{authError}</div>}
                  <button type="submit" className="btn-primary" disabled={authLoading}>
                    {authLoading ? "Validando credenciais..." : "Acessar Esteira de Processamento"}
                  </button>
                </form>
              ) : phase === "revision" ? (
                
                /* 🚀 RELATÓRIO DINÂMICO DE REVISÃO MANUAL (RF-16 / RF-14) */
                <form onSubmit={handleReviewSubmit} className="animate-fade-up">
                  <div style={{ marginBottom: "16px" }}>
                    <h2 style={{ fontSize: "18px", fontWeight: "600", color: "#e65100", display: "flex", alignItems: "center", gap: "8px" }}>
                      ⚠️ Auditoria de Acurácia Necessária
                    </h2>
                    <p style={{ fontSize: "13px", color: "var(--text-muted)" }}>
                      O Bedrock identificou desvios de acurácia no lote <strong>{currentPackageId}</strong>. Corrija os campos para reativar o pipeline.
                    </p>
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: "14px", marginBottom: "20px" }}>
                    {revisionFields.map((field, idx) => (
                      <div key={idx} style={{ padding: "12px", borderRadius: "8px", border: "1px solid #ffe0b2", background: "rgba(255, 224, 178, 0.15)" }}>
                        <div style={{ display: "flex", justifyContent: "between", fontSize: "11px", color: "var(--text-muted)", marginBottom: "6px" }}>
                          <span>📄 {field.arquivo} ({field.subtipo})</span>
                          <span style={{ color: "#d84315", fontWeight: "600" }}>Confiança: {(field.confidence_score * 100).toFixed(0)}%</span>
                        </div>
                        <label style={{ display: "block", fontSize: "13px", fontWeight: "600", marginBottom: "6px", textTransform: "capitalize" }}>
                          {field.campo_afetado.replace(/_/g, " ")}
                        </label>
                        <input
                          type="text"
                          required
                          value={correctionsForm[field.campo_afetado] || ""}
                          onChange={(e) => setCorrectionsForm({ ...correctionsForm, [field.campo_afetado]: e.target.value })}
                          style={{ width: "100%", padding: "8px 12px", borderRadius: "6px", border: "1px solid #b26a00", background: "var(--bg-input)", color: "var(--text-main)" }}
                        />
                      </div>
                    ))}
                  </div>

                  <button type="submit" className="btn-primary" style={{ background: "#e65100" }}>
                    💾 Confirmar Dados e Destravar Esteira
                  </button>
                  <button type="button" className="btn-ghost" onClick={handleReset} style={{ marginTop: "8px" }}>
                    Cancelar Lote
                  </button>
                </form>
              ) : (
                <form onSubmit={handleSubmit}>
                  <FileDropZone files={files} onChange={setFiles} disabled={isBusy} />
                  <label className="score-toggle">
                    <input type="checkbox" checked={scoreRequested} onChange={(e) => setScoreRequested(e.target.checked)} disabled={isBusy} />
                    <span className="score-toggle-text">🎯 Executar análise de score de crédito consolidado <span className="score-toggle-tag">bônus</span></span>
                  </label>

                  {errorMessage && phase === "error" && (
                    <div className="inline-error animate-fade-up">{errorMessage}</div>
                  )}

                  {phase === "done" ? (
                    <button type="button" className="btn-secondary" onClick={handleReset}>Enviar novo pacote</button>
                  ) : (
                    <button type="submit" className="btn-primary" disabled={isBusy || files.length === 0}>
                      {isBusy ? <><span className="spinner" />{PHASE_LABEL[phase]}</> : <>Iniciar processamento inteligente</>}
                    </button>
                  )}
                </form>
              )}
            </div>

            {result && <ResultPanel data={result} executeScore={executeScore} outputBucket={outputBucket} />}
          </div>

          <div className="col-status">
            <StatusTerminal logs={logs} phase={phase} startedAt={startedAt} finishedAt={finishedAt} />
            <div className="card info-card">
              <span className="info-label">Mecanismo cross-validation</span>
              <ol className="info-steps">
                <li>Consistência nominal e KYC entre documentos</li>
                <li>Saúde financeira e renda bruta estimada</li>
                <li>Liquidez e colchão de amortização</li>
                <li>Score consolidado, quando solicitado</li>
              </ol>
            </div>
          </div>
        </section>
      </main>
      <Footer />
      {modalOpen && <SuccessModal score={scoreVal} showScore={executeScore} onClose={() => setModalDismissed(true)} />}
    </div>
  );
}