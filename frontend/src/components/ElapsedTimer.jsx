import { useEffect, useState } from "react";
import "./ElapsedTimer.css";

function formatElapsed(ms) {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export default function ElapsedTimer({ startedAt, finishedAt, running }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!running) return;

    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [running]);

  if (!startedAt) return null;

  const endTime = finishedAt || now;
  const elapsedMs = Math.max(0, endTime - startedAt);
  const display = formatElapsed(elapsedMs);

  return (
    <span className={`elapsed-timer ${running ? "running" : "stopped"}`}>
      <span className="elapsed-dot" />
      <span className="elapsed-digits">{display}</span>
    </span>
  );
}
