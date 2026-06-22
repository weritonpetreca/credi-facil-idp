import { useEffect, useRef } from "react";
import ElapsedTimer from "./ElapsedTimer";
import "./StatusTerminal.css";

const LEVEL_COLOR = {
  info: "#8B93A8",
  success: "#A6FF00",
  error: "#FF4D6D",
};

const LEVEL_PREFIX = {
  info: "›",
  success: "✓",
  error: "✕",
};

export default function StatusTerminal({ logs, phase, startedAt, finishedAt }) {
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  const isActive = phase !== "idle" && phase !== "error" && phase !== "done";

  return (
    <div className="terminal">
      <div className="terminal-bar">
        <div className="terminal-dots">
          <span style={{ background: "#FF5F57" }} />
          <span style={{ background: "#FEBC2E" }} />
          <span style={{ background: "#28C840" }} />
        </div>
        <span className="terminal-title">credifacil-idp · monitor</span>

        <div className="terminal-bar-right">
          <ElapsedTimer
            startedAt={startedAt}
            finishedAt={finishedAt}
            running={isActive}
          />
          <span className={`terminal-status ${isActive ? "live" : ""}`}>
            {isActive
              ? "LIVE"
              : phase === "done"
                ? "CONCLUÍDO"
                : phase === "error"
                  ? "ERRO"
                  : "OCIOSO"}
          </span>
        </div>
      </div>

      <div className="terminal-body" ref={scrollRef}>
        {logs.length === 0 ? (
          <div className="terminal-idle">
            <div className="terminal-idle-icon">
              <svg
                width="22"
                height="22"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
              >
                <circle cx="12" cy="12" r="9" />
                <path
                  d="M12 7v5l3 3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <p className="terminal-idle-title">Nenhuma atividade ainda</p>
            <p className="terminal-idle-sub">
              Os eventos do processamento vão aparecer aqui em tempo real,
              conforme os documentos forem enviados e analisados.
            </p>
          </div>
        ) : (
          logs.map((log, i) => (
            <div key={i} className="terminal-line animate-fade-up">
              <span className="terminal-time">{log.time}</span>
              <span
                className="terminal-prefix"
                style={{ color: LEVEL_COLOR[log.level] || LEVEL_COLOR.info }}
              >
                {LEVEL_PREFIX[log.level] || LEVEL_PREFIX.info}
              </span>
              <span
                className="terminal-message"
                style={{
                  color: log.level === "error" ? LEVEL_COLOR.error : "#D4D8E5",
                }}
              >
                {log.message}
              </span>
            </div>
          ))
        )}
        {isActive && (
          <div className="terminal-line">
            <span className="terminal-time">&nbsp;</span>
            <span className="terminal-prefix-blink">▋</span>
          </div>
        )}
      </div>
    </div>
  );
}
