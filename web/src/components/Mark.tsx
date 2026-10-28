/** The product mark: a spine, a top step and two parallel steps joined by a bridge, on the app's tile. */
export function Mark({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <rect width="24" height="24" rx="5.5" fill="var(--accent)" />
      {/* The drawing is the 24px original scaled to 70% and centred on the tile. */}
      <g transform="translate(3.6 3.6) scale(0.7)" fill="none" stroke="#fff" strokeWidth="2.2">
        <line x1="12" y1="3" x2="12" y2="21" />
        <rect x="9" y="3" width="6" height="5" />
        <rect x="3" y="10" width="6" height="5" />
        <rect x="15" y="10" width="6" height="5" />
        <line x1="9" y1="12.5" x2="15" y2="12.5" />
      </g>
    </svg>
  );
}
