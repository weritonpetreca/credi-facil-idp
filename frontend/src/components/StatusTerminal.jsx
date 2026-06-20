import { useEffect, useRef } from "react";
import "../hooks/useDocumentPipeline";

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

export default function StatusTerminal({ logs, phase }) {
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
        <span className={`terminal-status ${isActive ? "live" : ""}`}>
          {isActive
            ? "● LIVE"
            : phase === "done"
              ? "● CONCLUÍDO"
              : phase === "error"
                ? "● ERRO"
                : "○ OCIOSO"}
        </span>
      </div>

      <div className="terminal-body" ref={scrollRef}>
        {logs.length === 0 ? (
          <p className="terminal-placeholder">
            <span className="terminal-cursor">_</span> aguardando envio de
            documentos...
          </p>
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
