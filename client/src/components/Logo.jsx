export function LogoMark({ size = 32, className = "" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="ig-grad" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop stopColor="#4F46E5" />
          <stop offset="1" stopColor="#22D3EE" />
        </linearGradient>
      </defs>
      <rect width="48" height="48" rx="13" fill="url(#ig-grad)" />
      <g stroke="#ffffff" strokeWidth="2.6" strokeLinecap="round" opacity="0.95">
        <path d="M11 15 L22.5 23" />
        <path d="M11 24 H22.5" />
        <path d="M11 33 L22.5 25" />
      </g>
      <circle cx="31" cy="24" r="6.5" fill="#ffffff" />
      <circle cx="31" cy="24" r="3" fill="#4F46E5" />
      <path d="M35.5 24 H41" stroke="#ffffff" strokeWidth="2.6" strokeLinecap="round" />
    </svg>
  );
}

export function Logo({ collapsed = false }) {
  return (
    <div className="flex items-center gap-2.5">
      <LogoMark size={34} />
      {!collapsed && (
        <div className="leading-tight">
          <div className="text-[15px] font-bold text-white">Ingress AI</div>
          <div className="text-[11px] font-medium text-slate-400">Gateway Console</div>
        </div>
      )}
    </div>
  );
}
