import "./SuccessModal.css";

export default function SuccessModal({ score, showScore, onClose }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-card animate-fade-up"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-icon">🎉</div>
        <h3>Análise concluída com sucesso!</h3>
        <p>
          O dossiê do proponente foi processado pelo motor de inteligência
          artificial.
        </p>

        {showScore && (
          <div className="modal-meta">
            <strong>Score calculado:</strong> <span>{score} pontos</span>
          </div>
        )}

        <button className="modal-btn" onClick={onClose}>
          Visualizar relatório completo
        </button>
      </div>
    </div>
  );
}
