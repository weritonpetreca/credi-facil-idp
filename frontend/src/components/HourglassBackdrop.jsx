import "./HourglassBackdrop.css";

export default function HourglassBackdrop({ active }) {
  return (
    <div
      className="hourglass-backdrop"
      style={{ opacity: active ? 0.12 : 0 }}
      aria-hidden="true"
    >
      <svg viewBox="0 0 200 320" className="hourglass-svg">
        <defs>
          <linearGradient id="hgGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#7C5CFF" />
            <stop offset="100%" stopColor="#4C8DFF" />
          </linearGradient>
        </defs>

        <rect
          x="30"
          y="10"
          width="140"
          height="14"
          rx="4"
          fill="url(#hgGradient)"
        />
        <rect
          x="30"
          y="296"
          width="140"
          height="14"
          rx="4"
          fill="url(#hgGradient)"
        />

        <path
          d="M 44 24 L 156 24 L 110 150 L 110 170 L 156 296 L 44 296 L 90 170 L 90 150 Z"
          fill="none"
          stroke="url(#hgGradient)"
          strokeWidth="5"
          strokeLinejoin="round"
        />

        <clipPath id="topClip">
          <path d="M 50 30 L 150 30 L 108 150 L 92 150 Z" />
        </clipPath>
        <rect
          className={active ? "hg-sand-top hg-animated" : "hg-sand-top"}
          x="50"
          y="30"
          width="100"
          height="120"
          clipPath="url(#topClip)"
          fill="url(#hgGradient)"
        />

        <rect
          className={active ? "hg-sand-stream hg-animated" : "hg-sand-stream"}
          x="98"
          y="150"
          width="4"
          height="20"
          fill="url(#hgGradient)"
        />

        <clipPath id="bottomClip">
          <path d="M 92 170 L 108 170 L 150 290 L 50 290 Z" />
        </clipPath>
        <rect
          className={active ? "hg-sand-bottom hg-animated" : "hg-sand-bottom"}
          x="50"
          y="170"
          width="100"
          height="120"
          clipPath="url(#bottomClip)"
          fill="url(#hgGradient)"
        />
      </svg>
    </div>
  );
}
