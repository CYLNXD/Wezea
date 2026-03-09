// ─── PublicScanPage.tsx — Rapport de scan partagé (sans authentification) ─────
import { useEffect, useState } from 'react';
import { Shield, Globe, Clock, AlertTriangle, CheckCircle, XCircle, Info } from 'lucide-react';

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface Finding {
  category:           string;
  severity:           string;
  title?:             string;
  message?:           string;
  plain_explanation?: string;
  recommendation?:    string;
  penalty?:           number;
}

interface PublicScan {
  scan_uuid:       string;
  domain:          string;
  scanned_at:      string;
  security_score:  number;
  risk_level:      string;
  findings_count:  number;
  findings:        Finding[];
  scan_duration:   number;
  dns_details:     Record<string, unknown>;
  ssl_details:     Record<string, unknown>;
  recommendations: string[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function scoreColor(score: number): string {
  if (score >= 80) return '#22c55e';
  if (score >= 60) return '#f59e0b';
  if (score >= 40) return '#f97316';
  return '#ef4444';
}

function riskLabel(level: string): { label: string; color: string } {
  const map: Record<string, { label: string; color: string }> = {
    low:      { label: 'Faible',    color: '#22c55e' },
    moderate: { label: 'Modéré',   color: '#f59e0b' },
    high:     { label: 'Élevé',    color: '#f97316' },
    critical: { label: 'Critique', color: '#ef4444' },
  };
  return map[level] ?? { label: level, color: '#94a3b8' };
}

function severityIcon(severity: string) {
  if (severity === 'critical' || severity === 'high') {
    return <XCircle size={14} className="text-red-400 shrink-0 mt-0.5" />;
  }
  if (severity === 'moderate') {
    return <AlertTriangle size={14} className="text-amber-400 shrink-0 mt-0.5" />;
  }
  if (severity === 'low') {
    return <Info size={14} className="text-blue-400 shrink-0 mt-0.5" />;
  }
  return <CheckCircle size={14} className="text-green-400 shrink-0 mt-0.5" />;
}

function severityBorder(severity: string): string {
  if (severity === 'critical' || severity === 'high') return 'border-red-500/30 bg-red-500/5';
  if (severity === 'moderate') return 'border-amber-500/30 bg-amber-500/5';
  if (severity === 'low') return 'border-blue-500/20 bg-blue-500/5';
  return 'border-green-500/20 bg-green-500/5';
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

interface Props {
  uuid:     string;
  onGoHome: () => void;
}

export default function PublicScanPage({ uuid, onGoHome }: Props) {
  const [scan,    setScan]    = useState<PublicScan | null>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  useEffect(() => {
    fetch(`${BASE_URL}/public/scan/${uuid}`)
      .then(r => {
        if (!r.ok) {
          if (r.status === 403) throw new Error('Ce rapport n\'est pas partagé publiquement.');
          if (r.status === 404) throw new Error('Rapport introuvable.');
          throw new Error('Erreur lors du chargement.');
        }
        return r.json();
      })
      .then(data => {
        setScan(data);
        setLoading(false);
        // Titre dynamique pour Googlebot et les navigateurs standards
        const rl = { low: 'Faible', moderate: 'Modéré', high: 'Élevé', critical: 'Critique' } as Record<string, string>;
        document.title = `Rapport de sécurité — ${data.domain} · ${data.security_score}% · ${rl[data.risk_level] ?? data.risk_level} | Wezea`;
      })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [uuid]);

  // ── Loading ──────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
          <p className="text-slate-400 text-sm font-mono">Chargement du rapport…</p>
        </div>
      </div>
    );
  }

  // ── Error ─────────────────────────────────────────────────────────────────
  if (error || !scan) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center p-6">
        <div className="max-w-md w-full text-center">
          <Shield size={48} className="text-slate-600 mx-auto mb-4" />
          <h1 className="text-white font-bold text-xl mb-2">Rapport indisponible</h1>
          <p className="text-slate-400 text-sm mb-6">{error ?? 'Ce rapport de sécurité n\'est pas accessible.'}</p>
          <button
            onClick={onGoHome}
            className="px-6 py-2.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-sm transition"
          >
            Scanner votre domaine gratuitement →
          </button>
        </div>
      </div>
    );
  }

  const { label: riskLabelText, color: riskColor } = riskLabel(scan.risk_level);
  const color = scoreColor(scan.security_score);

  // Group findings by severity order
  const severityOrder = ['critical', 'high', 'moderate', 'low', 'info'];
  const sorted = [...scan.findings].sort(
    (a, b) => severityOrder.indexOf(a.severity) - severityOrder.indexOf(b.severity)
  );

  return (
    <div className="min-h-screen bg-slate-950">
      {/* ── Navbar ───────────────────────────────────────────────────────── */}
      <nav className="border-b border-slate-800/60 bg-slate-950/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between">
          <button onClick={onGoHome} className="flex items-center gap-2 group">
            <Shield size={20} className="text-cyan-400" />
            <span className="text-white font-bold text-sm group-hover:text-cyan-400 transition">Wezea</span>
          </button>
          <button
            onClick={onGoHome}
            className="px-4 py-1.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs transition"
          >
            Scanner mon domaine →
          </button>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-4 py-10">

        {/* ── Header ──────────────────────────────────────────────────────── */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 mb-6">
          <div className="flex flex-col sm:flex-row sm:items-center gap-6">

            {/* Score gauge */}
            <div className="shrink-0 flex flex-col items-center gap-1">
              <div
                className="w-24 h-24 rounded-full border-4 flex items-center justify-center"
                style={{ borderColor: color }}
              >
                <span className="text-3xl font-black font-mono" style={{ color }}>
                  {scan.security_score}
                </span>
              </div>
              <span
                className="text-xs font-bold uppercase tracking-wider px-2 py-0.5 rounded-full"
                style={{ color: riskColor, backgroundColor: `${riskColor}22` }}
              >
                {riskLabelText}
              </span>
            </div>

            {/* Meta */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <Globe size={14} className="text-cyan-400 shrink-0" />
                <h1 className="text-white font-bold text-xl font-mono truncate">{scan.domain}</h1>
              </div>
              <p className="text-slate-400 text-sm mb-3">Rapport de sécurité partagé</p>
              <div className="flex flex-wrap gap-4 text-xs text-slate-500 font-mono">
                <span className="flex items-center gap-1.5">
                  <Clock size={11} />
                  {new Date(scan.scanned_at).toLocaleDateString('fr-FR', {
                    day: '2-digit', month: 'long', year: 'numeric',
                    hour: '2-digit', minute: '2-digit',
                  })}
                </span>
                <span>{scan.findings_count} finding{scan.findings_count !== 1 ? 's' : ''}</span>
                <span>{scan.scan_duration}s</span>
              </div>
            </div>
          </div>
        </div>

        {/* ── Score bar ─────────────────────────────────────────────────────── */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 mb-6">
          <div className="flex items-center justify-between mb-2">
            <span className="text-slate-400 text-xs font-mono uppercase tracking-wider">Security Score</span>
            <span className="font-black font-mono text-lg" style={{ color }}>{scan.security_score}/100</span>
          </div>
          <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{ width: `${scan.security_score}%`, backgroundColor: color }}
            />
          </div>
        </div>

        {/* ── Findings ─────────────────────────────────────────────────────── */}
        {sorted.length > 0 && (
          <div className="mb-6">
            <h2 className="text-white font-bold text-sm mb-3 flex items-center gap-2">
              <AlertTriangle size={14} className="text-amber-400" />
              Findings ({sorted.length})
            </h2>
            <div className="space-y-2">
              {sorted.map((f, i) => (
                <div
                  key={i}
                  className={`border rounded-xl p-4 ${severityBorder(f.severity)}`}
                >
                  <div className="flex items-start gap-2">
                    {severityIcon(f.severity)}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-white text-sm font-semibold leading-snug">
                          {f.title ?? f.message ?? f.category}
                        </span>
                        <span className="text-xs font-mono text-slate-500 uppercase shrink-0">
                          {f.category}
                        </span>
                      </div>
                      {f.plain_explanation && (
                        <p className="text-slate-400 text-xs leading-relaxed">
                          {f.plain_explanation}
                        </p>
                      )}
                      {f.recommendation && (
                        <p className="text-cyan-400/80 text-xs mt-1.5 leading-relaxed">
                          → {f.recommendation}
                        </p>
                      )}
                    </div>
                    {f.penalty != null && f.penalty > 0 && (
                      <span className="shrink-0 text-xs font-mono text-red-400">-{f.penalty}pt</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Recommendations ────────────────────────────────────────────────── */}
        {scan.recommendations.length > 0 && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 mb-6">
            <h2 className="text-white font-bold text-sm mb-3 flex items-center gap-2">
              <CheckCircle size={14} className="text-cyan-400" />
              Recommandations
            </h2>
            <ul className="space-y-2">
              {scan.recommendations.map((r, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                  <span className="text-cyan-400 font-mono text-xs mt-0.5 shrink-0">→</span>
                  {r}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* ── CTA ─────────────────────────────────────────────────────────── */}
        <div
          className="rounded-2xl p-6 text-center"
          style={{
            background: 'linear-gradient(135deg, rgba(6,182,212,0.08) 0%, rgba(139,92,246,0.08) 100%)',
            border: '1px solid rgba(6,182,212,0.15)',
          }}
        >
          <Shield size={28} className="text-cyan-400 mx-auto mb-3" />
          <h2 className="text-white font-bold text-lg mb-1">Scannez votre domaine gratuitement</h2>
          <p className="text-slate-400 text-sm mb-4">
            SPF, DMARC, SSL, ports ouverts, CVE — rapport complet en moins de 60 secondes.
          </p>
          <button
            onClick={onGoHome}
            className="px-7 py-2.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-sm transition"
          >
            Scanner maintenant →
          </button>
          <p className="text-slate-600 text-xs mt-3">Gratuit · Sans inscription · 5 scans/jour</p>
        </div>

        {/* ── Footer ─────────────────────────────────────────────────────── */}
        <p className="text-center text-slate-700 text-xs mt-8 font-mono">
          Rapport généré par{' '}
          <button onClick={onGoHome} className="text-slate-500 hover:text-cyan-400 transition">
            wezea.net
          </button>
        </p>
      </div>
    </div>
  );
}
