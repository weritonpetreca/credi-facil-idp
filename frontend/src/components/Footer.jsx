import "./Footer.css";

const STACK = [
  { label: "Amazon Bedrock" },
  { label: "Amazon Nova" },
  { label: "AWS Lambda" },
  { label: "Amazon S3" },
  { label: "Step Functions" },
  { label: "EventBridge" },
];

export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="footer-inner">
        <p className="footer-tagline">
          Tecnologia que entende seus documentos, decide com agilidade e
          constrói confiança em cada análise.
        </p>

        <div className="footer-top">
          <div className="footer-brand">
            <div className="footer-logo">
              <svg
                width="18"
                height="18"
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
            <div>
              <p className="footer-brand-name">CrediFácil</p>
              <p className="footer-brand-sub">
                Intelligent Document Processing
              </p>
            </div>
          </div>

          <div className="footer-stack">
            {STACK.map((item) => (
              <span key={item.label} className="stack-pill">
                {item.label}
              </span>
            ))}
          </div>
        </div>

        <div className="footer-divider" />

        <div className="footer-bottom">
          <p className="footer-credit">
            Desenvolvido para o <strong>Hack2Hire</strong> · Escola da Nuvem
          </p>
          <p
            className="footer-meta"
            title="Mesmo aquela carteirinha do Havaí com nome de espião não passaria pela nossa validação."
          >
            Processamento via IA generativa · AWS
          </p>
        </div>
      </div>
    </footer>
  );
}
