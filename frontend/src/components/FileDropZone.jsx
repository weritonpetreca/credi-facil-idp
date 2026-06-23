import { useRef, useState } from "react";
import "./FileDropZone.css";

function formatFileSize(bytes) {
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  return `${(kb / 1024).toFixed(2)} MB`;
}

function getFileMeta(type) {
  if (type === "application/pdf") return { label: "PDF", color: "#FF4D6D" };
  if (type.startsWith("image/")) return { label: "IMG", color: "#4C8DFF" };
  return { label: "DOC", color: "#8B93A8" };
}

export default function FileDropZone({ files, onChange, disabled }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    if (disabled) return;
    onChange(Array.from(e.dataTransfer.files));
  };

  const handleChange = (e) => {
    if (!e.target.files) return;
    onChange(Array.from(e.target.files));
  };

  const removeFile = (index) => {
    onChange(files.filter((_, i) => i !== index));
  };

  return (
    <div className="dz-wrapper">
      <div
        className={`dz ${dragging ? "dragging" : ""} ${disabled ? "disabled" : ""}`}
        onClick={() => !disabled && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.webp"
          multiple
          onChange={handleChange}
          style={{ display: "none" }}
          disabled={disabled}
        />
        <div className="dz-glow" />
        <div className="dz-inner">
          <div className="dz-icon">
            <svg
              width="30"
              height="30"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
            >
              <path
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <p className="dz-label">
            {dragging
              ? "Solte para enviar"
              : "Arraste os documentos ou clique para selecionar"}
          </p>
          <p className="dz-hint">PDF · PNG · JPG · JPEG · WEBP</p>
        </div>
      </div>

      {files.length > 0 && (
        <div className="dz-file-list">
          {files.map((file, i) => {
            const meta = getFileMeta(file.type);
            return (
              <div
                key={`${file.name}-${i}`}
                className="dz-file-item animate-fade-up"
              >
                <span
                  className="dz-badge"
                  style={{ background: meta.color + "1A", color: meta.color }}
                >
                  {meta.label}
                </span>
                <span className="dz-name">{file.name}</span>
                <span className="dz-size">{formatFileSize(file.size)}</span>
                {!disabled && (
                  <button
                    className="dz-remove"
                    onClick={() => removeFile(i)}
                    type="button"
                    aria-label="Remover"
                  >
                    <svg
                      width="13"
                      height="13"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2.5"
                    >
                      <line x1="18" y1="6" x2="6" y2="18" />
                      <line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
