import { useState } from "react";
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
  done: "Concluído",
  error: "Erro no processamento",
};

export default function App() {
  const [files, setFiles] = useState([]);
  const [scoreRequested, setScoreRequested] = useState(true);
  const [modalDismissed, setModalDismissed] = useState(false);
  const { theme, toggleTheme } = useTheme();

  // 🔒 ESTADOS DE GERENCIAMENTO DE IDENTIDADE (COGNITO B2B)
  const [token, setToken] = useState(sessionStorage.getItem("auth_token") || null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [authLoading, setAuthLoading] = useState(false);

  const {
    phase,
    logs,
    result,
    executeScore,
    outputBucket,
    errorMessage,
    startedAt,
    finishedAt,
    upload,
    reset,
  } = useDocumentPipeline();

  const isBusy = ["preparing", "uploading", "waiting"].includes(phase) || authLoading;

  // 🔐 AUTENTICAÇÃO DIRETA VIA API GLOBAL DA AWS (COMPACTA E SEGURA)
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
          ClientId: import.meta.env.VITE_USER_POOL_CLIENT_ID, // Consome o env injetado pelo seu deploy.yml
          AuthParameters: {
            USERNAME: email,
            PASSWORD: password,
          },
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.message || "Credenciais inválidas. Verifique usuário e senha.");
      }

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
    // Passa o token obtido pelo estado para blindar a chamada
    const success = await upload(files, scoreRequested, token);
    if (!success) return;
  };

  const handleReset = () => {
    reset();
    setFiles([]);
    setModalDismissed(false);
  };

  const modalOpen = phase === "done" && !!result && !modalDismissed;

  const scoreVal =
    result?.cliente?.score_credito?.valor ??
    result?.cliente?.score_atribuido ??
    0;

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
            <span className="header-pill">
              <span className="pill-dot" />
              Análise por IA generativa
            </span>
            <ThemeToggle theme={theme} onToggle={toggleTheme} />
          </div>
        </div>
      </header>

      <main className="main">
        <section className="hero">
          <span className="hero-eyebrow">Processamento Inteligente de Documentos</span>
          <h1 className="hero-title">
            Envie seus documentos.<br />
            <span className="hero-title-accent">A IA faz o resto.</span>
          </h1>
          <p className="hero-sub">
            Nossa IA analisa identidade, renda e documentação automaticamente — você acompanha cada etapa em tempo real e recebe o resultado completo na tela.
          </p>
        </section>

        <section className="grid">
          <div className="col-form">
            <div className="card">
              
              {/* 📊 INTERFACE CONDICIONAL DE AUTH EM NÍVEL DE CARD */}
              {!token ? (
                <form onSubmit={handleLogin} className="animate-fade-up">
                  <div style={{ marginBottom: "16px" }}>
                    <h2 style={{ fontSize: "18px", fontWeight: "600", marginBottom: "4px" }}>🔒 Área Restrita</h2>
                    <p style={{ fontSize: "13px", color: "var(--text-muted)" }}>Autentique-se para liberar a esteira de crédito.</p>
                  </div>

                  <div style={{ marginBottom: "12px" }}>
                    <label style={{ display: "block", fontSize: "12px", marginBottom: "6px", fontWeight: "500" }}>E-mail do analista</label>
                    <input 
                      type="email" 
                      required 
                      value={email} 
                      onChange={(e) => setEmail(e.target.value)}
                      disabled={authLoading}
                      placeholder="analista@credifacil.com"
                      style={{ width: "100%", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)", background: "var(--bg-input)", color: "var(--text-main)" }}
                    />
                  </div>

                  <div style={{ marginBottom: "16px" }}>
                    <label style={{ display: "block", fontSize: "12px", marginBottom: "6px", fontWeight: "500" }}>Senha de acesso</label>
                    <input 
                      type="password" 
                      required 
                      value={password} 
                      onChange={(e) => setPassword(e.target.value)}
                      disabled={authLoading}
                      placeholder="••••••••"
                      style={{ width: "100%", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-color)", background: "var(--bg-input)", color: "var(--text-main)" }}
                    />
                  </div>

                  {authError && (
                    <div className="inline-error" style={{ marginBottom: "16px" }}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                      </svg>
                      {authError}
                    </div>
                  )}

                  <button type="submit" className="btn-primary" disabled={authLoading}>
                    {authLoading ? "Validando credenciais..." : "Acessar Esteira de Processamento"}
                  </button>
                </form>
              ) : (
                
                /* 🚀 PAINEL DE UPLOAD LIBERADO PÓS-AUTH CORRETO */
                <form onSubmit={handleSubmit}>
                  <FileDropZone files={files} onChange={setFiles} disabled={isBusy} />

                  <label className="score-toggle">
                    <input
                      type="checkbox"
                      checked={scoreRequested}
                      onChange={(e) => setScoreRequested(e.target.checked)}
                      disabled={isBusy}
                    />
                    <span className="score-toggle-text">
                      🎯 Executar análise de score de crédito consolidado
                      <span className="score-toggle-tag">bônus</span>
                    </span>
                  </label>

                  {errorMessage && phase === "error" && (
                    <div className="inline-error animate-fade-up">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
                      </svg>
                      {errorMessage}
                    </div>
                  )}

                  {phase === "done" ? (
                    <button type="button" className="btn-secondary" onClick={handleReset}>
                      Enviar novo pacote
                    </button>
                  ) : (
                    <button type="submit" className="btn-primary" disabled={isBusy || files.length === 0}>
                      {isBusy ? (
                        <><span className="spinner" />{PHASE_LABEL[phase]}</>
                      ) : (
                        <>
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                            <path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                          Iniciar processamento inteligente
                        </>
                      )}
                    </button>
                  )}

                  {phase === "error" && (
                    <button type="button" className="btn-ghost" onClick={handleReset}>
                      Tentar novamente
                    </button>
                  )}
                </form>
              )}
            </div>

            {result && (
              <ResultPanel data={result} executeScore={executeScore} outputBucket={outputBucket} />
            )}
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

      {modalOpen && (
        <SuccessModal score={scoreVal} showScore={executeScore} onClose={() => setModalDismissed(true)} />
      )}
    </div>
  );
}