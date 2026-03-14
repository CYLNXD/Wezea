// ─── Helpers visuels pour ClientSpace ──────────────────────────────────────────
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { ScanHistoryItem } from './types';

export const scoreColor = (s: number | null) =>
  s === null ? 'text-slate-500'
  : s >= 70   ? 'text-green-400'
  : s >= 40   ? 'text-orange-400'
  : 'text-red-400';

export const scoreBorder = (s: number | null) =>
  s === null ? 'border-slate-700 bg-slate-900'
  : s >= 70   ? 'border-green-500/30 bg-green-500/5'
  : s >= 40   ? 'border-orange-500/30 bg-orange-500/5'
  : 'border-red-500/30 bg-red-500/5';

export function RiskBadge({ level }: { level: string | null }) {
  if (!level) return <span className="text-slate-600 text-xs font-mono">—</span>;
  const cfg: Record<string, string> = {
    CRITICAL: 'bg-red-500/15 text-red-400 border-red-500/30',
    HIGH:     'bg-orange-500/15 text-orange-400 border-orange-500/30',
    MEDIUM:   'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
    LOW:      'bg-blue-500/15 text-blue-400 border-blue-500/30',
    MINIMAL:  'bg-green-500/15 text-green-400 border-green-500/30',
  };
  return (
    <span className={`text-xs font-bold px-1.5 py-0.5 rounded border ${cfg[level] ?? 'text-slate-400 border-slate-700'}`}>
      {level}
    </span>
  );
}

// Sparkline SVG simple (0–100, pas d'axe)
export function Sparkline({ scores, width = 80, height = 32 }: { scores: number[]; width?: number; height?: number }) {
  if (scores.length < 2) return <span className="text-slate-700 text-xs font-mono">—</span>;

  const pts = scores.map((v, i) => {
    const x = (i / (scores.length - 1)) * width;
    const y = height - (Math.max(0, Math.min(100, v)) / 100) * height;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');

  const last  = scores[scores.length - 1];
  const first = scores[0];
  const c = last >= 70 ? '#34d399' : last >= 40 ? '#fb923c' : '#f87171';
  const lastX = width;
  const lastY = height - (Math.max(0, Math.min(100, last)) / 100) * height;

  const trend = last > first + 2 ? 'up' : last < first - 2 ? 'down' : 'stable';
  const TrendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus;
  const trendColor = trend === 'up' ? 'text-green-400' : trend === 'down' ? 'text-red-400' : 'text-slate-500';

  return (
    <div className="flex items-center gap-2">
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width, height }} className="shrink-0 overflow-visible">
        <polyline
          points={pts}
          fill="none"
          stroke={c}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx={lastX.toFixed(1)} cy={lastY.toFixed(1)} r="2.5" fill={c} />
      </svg>
      <TrendIcon size={12} className={trendColor} />
    </div>
  );
}

// Graphique pleine largeur pour l'onglet Historique
export function ScoreLineChart({ scans, lang }: { scans: ScanHistoryItem[]; lang: 'fr' | 'en' }) {
  if (scans.length < 2) return null;
  const W = 600, H = 100, PAD = 16;
  const sorted = [...scans].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
  const pts = sorted.map((s, i) => {
    const x = PAD + (i / (sorted.length - 1)) * (W - PAD * 2);
    const y = PAD + (1 - s.security_score / 100) * (H - PAD * 2);
    return { x, y, score: s.security_score, date: s.created_at };
  });
  const polyline = pts.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  const last = pts[pts.length - 1].score;
  const c = last >= 70 ? '#34d399' : last >= 40 ? '#fb923c' : '#f87171';

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: H }}>
        {/* Grid lignes horizontales */}
        {[25, 50, 75].map(v => {
          const y = PAD + (1 - v / 100) * (H - PAD * 2);
          return (
            <g key={v}>
              <line x1={PAD} y1={y} x2={W - PAD} y2={y} stroke="rgba(255,255,255,0.04)" strokeWidth="1" />
              <text x={PAD - 4} y={y + 3} fill="#475569" fontSize="8" textAnchor="end">{v}</text>
            </g>
          );
        })}
        {/* Ligne */}
        <polyline points={polyline} fill="none" stroke={c} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        {/* Points */}
        {pts.map((p, i) => (
          <circle key={i} cx={p.x.toFixed(1)} cy={p.y.toFixed(1)} r="3.5" fill={c} stroke="#0f1520" strokeWidth="1.5" />
        ))}
      </svg>
      <div className="flex justify-between mt-1">
        <span className="text-slate-700 text-[10px] font-mono">{new Date(sorted[0].created_at).toLocaleDateString(lang === 'fr' ? 'fr-FR' : 'en-GB')}</span>
        <span className="text-slate-700 text-[10px] font-mono">{new Date(sorted[sorted.length - 1].created_at).toLocaleDateString(lang === 'fr' ? 'fr-FR' : 'en-GB')}</span>
      </div>
    </div>
  );
}
