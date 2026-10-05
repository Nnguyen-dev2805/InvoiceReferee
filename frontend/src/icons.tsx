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
