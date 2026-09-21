/** Small inline icon set: no icon-font payload, and they inherit colour and stroke weight. */
type P = { className?: string; size?: number };

const base = (size = 16) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
});

export const EyeIcon = ({ size, className }: P) => (
  <svg {...base(size)} className={className}>
    <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);

export const ShareIcon = ({ size, className }: P) => (
  <svg {...base(size)} className={className}>
    <path d="m17 2 5 5-5 5" />
    <path d="M22 7H9a6 6 0 0 0-6 6v4" />
  </svg>
);

export const SearchIcon = ({ size, className }: P) => (
  <svg {...base(size)} className={className}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.5-3.5" />
  </svg>
);

export const ExternalIcon = ({ size, className }: P) => (
  <svg {...base(size)} className={className}>
    <path d="M14 4h6v6" />
    <path d="M20 4 10 14" />
    <path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
  </svg>
);

export const ArrowLeftIcon = ({ size, className }: P) => (
  <svg {...base(size)} className={className}>
    <path d="M19 12H5" />
    <path d="m11 18-6-6 6-6" />
  </svg>
);

export const ArrowRightIcon = ({ size, className }: P) => (
  <svg {...base(size)} className={className}>
    <path d="M5 12h14" />
    <path d="m13 6 6 6-6 6" />
  </svg>
);

export const SparkIcon = ({ size, className }: P) => (
  <svg {...base(size)} className={className}>
    <path d="M12 3v3M12 18v3M3 12h3M18 12h3" />
    <path d="M12 8.5 13.4 11l2.6 1-2.6 1-1.4 2.5-1.4-2.5L8 12l2.6-1L12 8.5Z" />
  </svg>
);

export const TagIcon = ({ size, className }: P) => (
  <svg {...base(size)} className={className}>
    <path d="M3 11V5a2 2 0 0 1 2-2h6l10 10-8 8L3 11Z" />
    <circle cx="7.5" cy="7.5" r="1.5" />
  </svg>
);

export const ChartIcon = ({ size, className }: P) => (
  <svg {...base(size)} className={className}>
    <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
  </svg>
);

export const FlameIcon = ({ size, className }: P) => (
  <svg {...base(size)} className={className}>
    <path d="M12 22c4 0 7-2.7 7-6.5 0-4-3-6-4.5-9.5-.4 2.5-1.6 3.6-2.8 4.6C10 8.2 9 6.6 9 4c-2 2.2-4 4.8-4 8.5C5 19.3 8 22 12 22Z" />
  </svg>
);

export const MenuIcon = ({ size, className }: P) => (
  <svg {...base(size)} className={className}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </svg>
);

export const CloseIcon = ({ size, className }: P) => (
  <svg {...base(size)} className={className}>
    <path d="m6 6 12 12M18 6 6 18" />
  </svg>
);
