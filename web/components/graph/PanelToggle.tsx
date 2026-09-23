"use client";

/** The button that shows or hides a floating control panel: three sliders, the usual sign for it. */
export function PanelToggle({
  open,
  onToggle,
  controls,
  showLabel,
  hideLabel,
}: {
  open: boolean;
  onToggle: (next: boolean) => void;
  /** id of the panel, for assistive technology. */
  controls: string;
  showLabel: string;
  hideLabel: string;
}) {
  const label = open ? hideLabel : showLabel;
  return (
    <button
      type="button"
      className="graph-toggle"
      data-open={open}
      onClick={() => onToggle(!open)}
      aria-expanded={open}
      aria-controls={controls}
      aria-label={label}
      title={label}
    >
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
        <path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0" />
        <circle cx="16" cy="6" r="2" />
        <circle cx="10" cy="12" r="2" />
        <circle cx="18" cy="18" r="2" />
      </svg>
    </button>
  );
}
