import type { ReactNode } from 'react';

/**
 * SkuIcon — boîte d'icône skeuomorphique.
 *
 * @param color  hex de la couleur thématique (ex: "#22d3ee")
 * @param size   taille en px (32 | 36 | 44 | 52)
 *
 * Palette : cyan #22d3ee · indigo #818cf8 · violet #a78bfa
 *           red #f87171 · green #4ade80 · amber #fbbf24
 */
export default function SkuIcon({
  children,
  color,
  size = 36,
}: {
  children: ReactNode;
  color: string;
  size?: number;
}) {
  const r = Math.round(size * 0.28);
  return (
    <div
      className="shrink-0 flex items-center justify-center relative overflow-hidden"
      style={{
        width: size,
        height: size,
        borderRadius: r,
        background: `linear-gradient(150deg, ${color}30 0%, ${color}0d 100%)`,
        border: `1px solid ${color}40`,
        boxShadow: `0 4px 16px ${color}22, 0 1px 3px rgba(0,0,0,0.4), inset 0 1px 0 ${color}30, inset 0 -1px 0 rgba(0,0,0,0.3)`,
      }}
    >
      {/* Reflet supérieur — NE PAS OMETTRE */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          borderRadius: r,
          background: 'linear-gradient(180deg,rgba(255,255,255,0.07) 0%,transparent 50%)',
        }}
      />
      {children}
    </div>
  );
}
