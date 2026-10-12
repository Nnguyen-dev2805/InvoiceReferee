// Small inline SVG icon set (stroke, currentColor) so no emoji is used as a
// structural icon. Kept local — the app needs only a handful of glyphs.
interface IconProps {
  size?: number;
  'aria-hidden'?: boolean;
}

function svgProps(size: number, hidden: boolean) {
  return {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.75,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': hidden,
    focusable: false,
  };
}

export function CheckCircleIcon({ size = 18, 'aria-hidden': hidden = true }: IconProps) {
  return (
    <svg {...svgProps(size, hidden)}>
      <circle cx="12" cy="12" r="9" />
      <path d="m8.5 12.5 2.5 2.5 4.5-5" />
    </svg>
  );
}

export function AlertIcon({ size = 18, 'aria-hidden': hidden = true }: IconProps) {
  return (
    <svg {...svgProps(size, hidden)}>
      <path d="M12 3.5 21 20H3z" />
      <path d="M12 10v4" />
      <path d="M12 17.5h.01" />
    </svg>
  );
}

export function QuestionIcon({ size = 18, 'aria-hidden': hidden = true }: IconProps) {
  return (
    <svg {...svgProps(size, hidden)}>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.5 9.5a2.5 2.5 0 1 1 3.2 2.4c-.7.3-1.2.9-1.2 1.6v.5" />
      <path d="M12 17h.01" />
    </svg>
  );
}

export function StopIcon({ size = 16, 'aria-hidden': hidden = true }: IconProps) {
  return (
    <svg {...svgProps(size, hidden)}>
      <rect x="7" y="7" width="10" height="10" rx="1.5" />
    </svg>
  );
}

export function MoneyIcon({ size = 18, 'aria-hidden': hidden = true }: IconProps) {
  return (
    <svg {...svgProps(size, hidden)}>
      <rect x="3" y="6" width="18" height="12" rx="2" />
      <circle cx="12" cy="12" r="2.5" />
    </svg>
  );
}

export function UploadCloudIcon({ size = 28, 'aria-hidden': hidden = true }: IconProps) {
  return (
    <svg {...svgProps(size, hidden)}>
      <path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242" />
      <path d="M12 12v9" />
      <path d="m16 16-4-4-4 4" />
    </svg>
  );
}

export function SpinnerIcon({ size = 16, 'aria-hidden': hidden = true }: IconProps) {
  return (
    <svg
      {...svgProps(size, hidden)}
      className="spin-animation"
      strokeWidth={2}
    >
      <circle cx="12" cy="12" r="9" strokeOpacity="0.25" />
      <path d="M12 3a9 9 0 0 1 9 9" />
    </svg>
  );
}

export function EyeIcon({ size = 15, 'aria-hidden': hidden = true }: IconProps) {
  return (
    <svg {...svgProps(size, hidden)}>
      <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

export function DownloadIcon({ size = 15, 'aria-hidden': hidden = true }: IconProps) {
  return (
    <svg {...svgProps(size, hidden)}>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}

