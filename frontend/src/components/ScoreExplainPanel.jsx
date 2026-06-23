import { useState } from "react";
import "./ScoreExplainPanel.css";

export default function ScoreExplainPanel() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        className="score-help-trigger"
        onClick={() => setOpen(true)}
        title="Clique para ver a regra de cálculo"
        aria-label="Ver regra de cálculo do score"
      >
        ?
      </button>

      {open && (
        <div className="score-explain-overlay" onClick={() => setOpen(false)}>
          <div
            className="score-explain-panel animate-fade-up"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="score-explain-header">
              <strong>Regra de cálculo do Application Scorecard</strong>
              <button
                type="button"
                className="score-explain-close"
                onClick={() => setOpen(false)}
              >
                ✕
              </button>
            </div>
            <p>
              O cálculo segue as diretrizes de governança de risco financeiro:
            </p>
            <ul>
              <li>
                <strong>Pontuação base incondicional:</strong> 300 pontos
                (mínimo de entrada)
              </li>
              <li>
                <strong>Pilar KYC (até 150 pts):</strong> +50 por nome
                consistente, +50 por data de nascimento, +50 por documento
                oficial verificado
              </li>
              <li>
                <strong>Capacidade de renda (até 450 pts):</strong> baseado no
                maior contracheque/W2 (renda ≥ US$ 5.000 garante o teto)
              </li>
              <li>
                <strong>Colchão de liquidez (até 400 pts):</strong> saldo de
                encerramento do extrato bancário (saldo ≥ US$ 10.000 garante o
                teto)
              </li>
            </ul>
            <p className="score-explain-formula">
              Fórmula: Base (300) + KYC + Renda + Liquidez = Score Final (máx.
              1000)
            </p>
          </div>
        </div>
      )}
    </>
  );
}
