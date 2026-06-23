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

  const isBusy = ["preparing", "uploading", "waiting"].includes(phase);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const success = await upload(files, scoreRequested);
    if (!success) return;
  };

  const handleReset = () => {
    reset();
    setFiles([]);
    setModalDismissed(false);
  };

  // Modal abre automaticamente quando a análise é concluída,
  // e fica fechado se o usuário já o dispensou ou resetou o fluxo.
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
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="white"
                strokeWidth="2"
              >
                <path
                  d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <polyline
                  points="9 22 9 12 15 12 15 22"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <span className="brand-name">CrediFácil</span>
          </div>
          <div className="header-actions">
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
          <span className="hero-eyebrow">
            Processamento Inteligente de Documentos
          </span>
          <h1 className="hero-title">
            Envie seus documentos.
            <br />
            <span className="hero-title-accent">A IA faz o resto.</span>
          </h1>
          <p className="hero-sub">
            Nossa IA analisa identidade, renda e documentação automaticamente —
            você acompanha cada etapa em tempo real e recebe o resultado
            completo na tela.
          </p>
        </section>

        <section className="grid">
          <div className="col-form">
            <div className="card">
              <form onSubmit={handleSubmit}>
                <FileDropZone
                  files={files}
                  onChange={setFiles}
                  disabled={isBusy}
                />

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
                    <svg
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <circle cx="12" cy="12" r="10" />
                      <line x1="12" y1="8" x2="12" y2="12" />
                      <line x1="12" y1="16" x2="12.01" y2="16" />
                    </svg>
                    {errorMessage}
                  </div>
                )}

                {phase === "done" ? (
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={handleReset}
                  >
                    Enviar novo pacote
                  </button>
                ) : (
                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={isBusy || files.length === 0}
                  >
                    {isBusy ? (
                      <>
                        <span className="spinner" />
                        {PHASE_LABEL[phase]}
                      </>
                    ) : (
                      <>
                        <svg
                          width="16"
                          height="16"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2.5"
                        >
                          <path
                            d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                        Iniciar processamento inteligente
                      </>
                    )}
                  </button>
                )}

                {phase === "error" && (
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={handleReset}
                  >
                    Tentar novamente
                  </button>
                )}
              </form>
            </div>

            {result && (
              <ResultPanel
                data={result}
                executeScore={executeScore}
                outputBucket={outputBucket}
              />
            )}
          </div>

          <div className="col-status">
            <StatusTerminal
              logs={logs}
              phase={phase}
              startedAt={startedAt}
              finishedAt={finishedAt}
            />

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
        <SuccessModal
          score={scoreVal}
          showScore={executeScore}
          onClose={() => setModalDismissed(true)}
        />
      )}
    </div>
  );
}
