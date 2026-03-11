import { useEffect, useState, useMemo } from 'react';
import { Shield, Clock, Globe, Trash2, ChevronRight, FileDown, Share2, Check, X, Search, TrendingUp, TrendingDown, Eye, Link2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useLanguage } from '../i18n/LanguageContext';
import { apiClient } from '../lib/api';
import PageNavbar from '../components/PageNavbar';
import SkuIcon from '../components/SkuIcon';

interface ScanSummary {
  id: number;
  scan_uuid: string;
  domain: string;
  security_score: number;
  risk_level: string;
  findings_count: number;
  scan_duration: number;
  created_at: string;
  public_share: boolean;
}

function scoreColor(score: number) {
  if (score >= 70) return 'text-emerald-400';
  if (score >= 40) return 'text-amber-400';
  return 'text-red-400';
}

function scoreBg(score: number) {
  if (score >= 70) return 'bg-emerald-500/10 border-emerald-500/20';
  if (score >= 40) return 'bg-amber-500/10 border-amber-500/20';
  return 'bg-red-500/10 border-red-500/20';
}

function scoreHex(score: number) {
  if (score >= 70) return '#10b981';
  if (score >= 40) return '#f59e0b';
  return '#ef4444';
}

function riskLabel(risk: string, lang: string) {
  if (lang === 'fr') {
    if (risk === 'CRITICAL') return 'Critique';
    if (risk === 'HIGH')     return 'Élevé';
    if (risk === 'MEDIUM')   return 'Modéré';
    return 'Faible';
  }
  if (risk === 'CRITICAL') return 'Critical';
  if (risk === 'HIGH')     return 'High';
  if (risk === 'MEDIUM')   return 'Medium';
  return 'Low';
}

interface Props {
  onBack: () => void;
  onLoadScan?: (scanUuid: string) => void;
  onGoAdmin?: () => void;
  onGoClientSpace?: () => void;
  onGoContact?: () => void;
}

// ── OG card image used by all platform previews ────────────────────────────

function OgPreviewImage({ scan, height = 130 }: { scan: ScanSummary; height?: number }) {
  const sc = scoreHex(scan.security_score);
  return (
    <div style={{
      height,
      background: 'linear-gradient(135deg, #0d1117 0%, #0f2235 55%, #0a1628 100%)',
      position: 'relative',
      display: 'flex',
      alignItems: 'center',
      padding: '0 16px',
      gap: '12px',
      overflow: 'hidden',
    }}>
      {/* Cyber grid */}
      <div style={{
        position: 'absolute', inset: 0, opacity: 0.04,
        backgroundImage: 'linear-gradient(rgba(34,211,238,1) 1px, transparent 1px), linear-gradient(90deg, rgba(34,211,238,1) 1px, transparent 1px)',
        backgroundSize: '18px 18px',
      }} />
      {/* Radial glow */}
      <div style={{
        position: 'absolute', inset: 0,
        background: 'radial-gradient(ellipse at 25% 50%, rgba(34,211,238,0.12) 0%, transparent 65%)',
      }} />
      {/* Score arc glow right side */}
      <div style={{
        position: 'absolute', right: -20, top: -20, width: 120, height: 120, borderRadius: '50%',
        background: `radial-gradient(circle, ${sc}22 0%, transparent 65%)`,
      }} />
      {/* Shield icon box */}
      <div style={{
        width: 42, height: 42, borderRadius: 11, flexShrink: 0,
        background: 'linear-gradient(150deg, rgba(34,211,238,0.18) 0%, rgba(34,211,238,0.05) 100%)',
        border: '1px solid rgba(34,211,238,0.3)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        position: 'relative',
        boxShadow: '0 4px 12px rgba(34,211,238,0.15)',
      }}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#22d3ee" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
        </svg>
      </div>
      {/* Text */}
      <div style={{ flex: 1, minWidth: 0, position: 'relative' }}>
        <div style={{ color: 'rgba(34,211,238,0.6)', fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.12em', fontFamily: 'monospace', marginBottom: 3 }}>
          wezea.net · Security Report
        </div>
        <div style={{ color: '#fff', fontSize: 14, fontWeight: 700, fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {scan.domain}
        </div>
        <div style={{ color: 'rgba(255,255,255,0.35)', fontSize: 10, fontFamily: 'monospace', marginTop: 3 }}>
          {scan.findings_count} {scan.findings_count === 1 ? 'finding' : 'findings'} detected
        </div>
      </div>
      {/* Score */}
      <div style={{ textAlign: 'right', flexShrink: 0, position: 'relative' }}>
        <div style={{ color: sc, fontSize: 32, fontWeight: 800, fontFamily: 'monospace', lineHeight: 1 }}>
          {scan.security_score}
        </div>
        <div style={{ color: 'rgba(100,116,139,0.8)', fontSize: 10, fontFamily: 'monospace', textAlign: 'right' }}>/100</div>
      </div>
    </div>
  );
}

// ── Platform-specific card mockups ─────────────────────────────────────────

function XCard({ scan, lang }: { scan: ScanSummary; lang: string }) {
  const title = lang === 'fr'
    ? `Rapport de sécurité — ${scan.domain}`
    : `Security report — ${scan.domain}`;
  const desc = lang === 'fr'
    ? `Score ${scan.security_score}/100 · Niveau ${riskLabel(scan.risk_level, lang)} · ${scan.findings_count} vulnérabilité(s) détectée(s). Plan d'action priorisé inclus.`
    : `Score ${scan.security_score}/100 · ${riskLabel(scan.risk_level, lang)} risk · ${scan.findings_count} vulnerability(ies) found. Prioritized action plan included.`;

  return (
    <div style={{ background: '#15202b', borderRadius: 14, overflow: 'hidden', border: '1px solid rgba(255,255,255,0.1)' }}>
      <OgPreviewImage scan={scan} height={130} />
      <div style={{ padding: '10px 14px 12px', background: '#15202b' }}>
        <div style={{ color: '#536471', fontSize: 11, marginBottom: 3 }}>wezea.net</div>
        <div style={{ color: '#e7e9ea', fontSize: 13, fontWeight: 600, lineHeight: 1.35, marginBottom: 4 }}>{title}</div>
        <div style={{
          color: '#536471', fontSize: 11, lineHeight: 1.5,
          overflow: 'hidden', display: '-webkit-box',
          WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
        }}>{desc}</div>
      </div>
    </div>
  );
}

function LinkedInCard({ scan, lang }: { scan: ScanSummary; lang: string }) {
  const title = lang === 'fr'
    ? `Rapport de sécurité — ${scan.domain}`
    : `Security report — ${scan.domain}`;
  const desc = lang === 'fr'
    ? `Score ${scan.security_score}/100 · ${riskLabel(scan.risk_level, lang)} · ${scan.findings_count} vulnérabilité(s) détectée(s).`
    : `Score ${scan.security_score}/100 · ${riskLabel(scan.risk_level, lang)} risk · ${scan.findings_count} vulnerability(ies) found.`;

  return (
    <div style={{ background: '#1d2226', borderRadius: 6, overflow: 'hidden', border: '1px solid rgba(255,255,255,0.1)' }}>
      <OgPreviewImage scan={scan} height={118} />
      <div style={{ padding: '10px 14px 12px', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
        <div style={{ color: '#e1e1e1', fontSize: 13, fontWeight: 700, lineHeight: 1.35, marginBottom: 3 }}>{title}</div>
        <div style={{ color: '#a8b3c0', fontSize: 11, lineHeight: 1.45, marginBottom: 6 }}>{desc}</div>
        <div style={{ color: '#70b5f9', fontSize: 11, fontWeight: 500 }}>wezea.net</div>
      </div>
    </div>
  );
}

function WhatsAppCard({ scan, lang }: { scan: ScanSummary; lang: string }) {
  const title = lang === 'fr'
    ? `Rapport de sécurité — ${scan.domain}`
    : `Security report — ${scan.domain}`;
  const desc = lang === 'fr'
    ? `Score ${scan.security_score}/100 · ${riskLabel(scan.risk_level, lang)} · ${scan.findings_count} vulnérabilité(s). Rapport complet gratuit.`
    : `Score ${scan.security_score}/100 · ${riskLabel(scan.risk_level, lang)} risk · ${scan.findings_count} vulnerability(ies). Free full report.`;

  return (
    /* WhatsApp dark theme — simulated mobile message bubble */
    <div style={{ display: 'flex', justifyContent: 'flex-end', padding: '0 4px' }}>
      <div style={{
        maxWidth: 320, width: '100%',
        background: '#1f2c34', borderRadius: '8px 0 8px 8px',
        overflow: 'hidden', boxShadow: '0 1px 4px rgba(0,0,0,0.4)',
      }}>
        {/* Link preview box inside bubble */}
        <div style={{ background: '#131c21', borderLeft: '3px solid #00a884', overflow: 'hidden' }}>
          <OgPreviewImage scan={scan} height={100} />
          <div style={{ padding: '8px 10px 10px' }}>
            <div style={{ color: '#e9edef', fontSize: 12, fontWeight: 600, lineHeight: 1.3, marginBottom: 2 }}>{title}</div>
            <div style={{ color: '#8696a0', fontSize: 11, lineHeight: 1.45 }}>{desc}</div>
            <div style={{ color: '#00a884', fontSize: 10, marginTop: 4 }}>wezea.net</div>
          </div>
        </div>
        {/* Message meta */}
        <div style={{ padding: '4px 8px 6px', display: 'flex', justifyContent: 'flex-end', gap: 4, alignItems: 'center' }}>
          <span style={{ color: '#8696a0', fontSize: 10 }}>maintenant</span>
          <svg width="14" height="10" viewBox="0 0 16 11" fill="#53bdeb">
            <path d="M11.071.653a.75.75 0 0 0-1.142.975L11.71 3.5H1.75a.75.75 0 0 0 0 1.5h9.96l-1.78 1.872a.75.75 0 1 0 1.142.975l2.75-2.894a.75.75 0 0 0 0-1.3L11.071.653z" transform="rotate(0)" />
            <path d="M5 5.5L1.5 9M1.5 9L5 12.5" stroke="#53bdeb" strokeWidth="1.2" fill="none"/>
          </svg>
        </div>
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────

export default function HistoryPage({ onBack, onLoadScan, onGoAdmin, onGoClientSpace, onGoContact }: Props) {
  const { lang } = useLanguage();

  const [scans,        setScans]        = useState<ScanSummary[]>([]);
  const [loading,      setLoading]      = useState(true);
  const [error,        setError]        = useState('');
  const [deleting,     setDeleting]     = useState<string | null>(null);
  const [pdfLoading,   setPdfLoading]   = useState<string | null>(null);
  const [sharing,      setSharing]      = useState<string | null>(null);
  const [copied,       setCopied]       = useState<string | null>(null);
  const [domainFilter, setDomainFilter] = useState('');
  const [previewUuid,  setPreviewUuid]  = useState<string | null>(null);
  const [previewTab,   setPreviewTab]   = useState<'x' | 'linkedin' | 'whatsapp'>('x');

  useEffect(() => { fetchHistory(); }, []);

  async function fetchHistory() {
    setLoading(true);
    try {
      const { data } = await apiClient.get<{ scans: ScanSummary[] }>('/scans/history?limit=50');
      setScans(data.scans);
    } catch (e: any) {
      setError(e.message ?? 'Erreur de chargement');
    } finally {
      setLoading(false);
    }
  }

  async function deleteScan(uuid: string) {
    setDeleting(uuid);
    try {
      await apiClient.delete(`/scans/history/${uuid}`);
      setScans(prev => prev.filter(s => s.scan_uuid !== uuid));
      if (previewUuid === uuid) setPreviewUuid(null);
    } finally {
      setDeleting(null);
    }
  }

  async function exportPdf(uuid: string, domain: string) {
    setPdfLoading(uuid);
    try {
      const { data, headers } = await apiClient.get(
        `/scans/history/${uuid}/export?format=pdf&lang=${lang}`,
        { responseType: 'blob' },
      );
      const cd       = (headers['content-disposition'] ?? '') as string;
      const match    = cd.match(/filename="([^"]+)"/);
      const filename = match ? match[1] : `rapport-${domain}-${new Date().toISOString().slice(0, 10)}.pdf`;
      const url      = URL.createObjectURL(new Blob([data as BlobPart], { type: 'application/pdf' }));
      const a        = document.createElement('a');
      a.href = url; a.download = filename; a.click();
      URL.revokeObjectURL(url);
    } catch {
      /* silently ignore */
    } finally {
      setPdfLoading(null);
    }
  }

  async function toggleShare(uuid: string) {
    setSharing(uuid);
    try {
      const { data } = await apiClient.patch<{ scan_uuid: string; public_share: boolean }>(
        `/scans/history/${uuid}/share`,
      );
      setScans(prev => prev.map(s =>
        s.scan_uuid === uuid ? { ...s, public_share: data.public_share } : s,
      ));
      if (data.public_share) {
        const link = `${window.location.origin}/r/${uuid}`;
        await navigator.clipboard.writeText(link).catch(() => {});
        setCopied(uuid);
        setTimeout(() => setCopied(null), 2500);
        // Auto-open preview when sharing is enabled
        setPreviewUuid(uuid);
      } else {
        // Close preview when sharing is disabled
        if (previewUuid === uuid) setPreviewUuid(null);
      }
    } catch {
      /* silently ignore */
    } finally {
      setSharing(null);
    }
  }

  function togglePreview(uuid: string) {
    setPreviewUuid(prev => prev === uuid ? null : uuid);
  }

  // ── Delta de score vs scan précédent pour le même domaine ─────────────────
  const scoreDelta = useMemo(() => {
    const lastScore = new Map<string, number>();
    const delta     = new Map<string, number | null>();
    const sorted    = [...scans].sort(
      (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    );
    for (const scan of sorted) {
      const prev = lastScore.get(scan.domain);
      delta.set(scan.scan_uuid, prev != null ? scan.security_score - prev : null);
      lastScore.set(scan.domain, scan.security_score);
    }
    return delta;
  }, [scans]);

  // ── Filtre par domaine ─────────────────────────────────────────────────────
  const filtered = useMemo(() => {
    if (!domainFilter.trim()) return scans;
    const q = domainFilter.trim().toLowerCase();
    return scans.filter(s => s.domain.toLowerCase().includes(q));
  }, [scans, domainFilter]);

  return (
    <div className="relative min-h-screen flex flex-col">
      {/* Grille cyber */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: 'linear-gradient(rgba(34,211,238,1) 1px, transparent 1px), linear-gradient(90deg, rgba(34,211,238,1) 1px, transparent 1px)',
          backgroundSize: '48px 48px',
          opacity: 0.025,
        }}
      />
      <PageNavbar
        onBack={onBack}
        title={lang === 'fr' ? 'Historique des scans' : 'Scan history'}
        onGoAdmin={onGoAdmin}
        onGoClientSpace={onGoClientSpace}
        onGoContact={onGoContact}
        icon={
          <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
        }
      />

      <div className="px-4 py-6 flex-1">
        <div className="max-w-3xl mx-auto">

          {/* Stats bar */}
          {scans.length > 0 && (
            <div className="grid grid-cols-3 gap-3 mb-6">
              <div className="sku-stat rounded-xl">
                <div className="text-2xl font-bold text-white font-mono">{scans.length}</div>
                <div className="text-xs text-slate-500 mt-0.5">{lang === 'fr' ? 'Scans total' : 'Total scans'}</div>
              </div>
              <div className="sku-stat rounded-xl">
                <div className={`text-2xl font-bold font-mono ${scoreColor(Math.round(scans.reduce((a, s) => a + s.security_score, 0) / scans.length))}`}>
                  {Math.round(scans.reduce((a, s) => a + s.security_score, 0) / scans.length)}
                </div>
                <div className="text-xs text-slate-500 mt-0.5">{lang === 'fr' ? 'Score moyen' : 'Avg score'}</div>
              </div>
              <div className="sku-stat rounded-xl">
                <div className="text-2xl font-bold text-white font-mono">
                  {new Set(scans.map(s => s.domain)).size}
                </div>
                <div className="text-xs text-slate-500 mt-0.5">{lang === 'fr' ? 'Domaines' : 'Domains'}</div>
              </div>
            </div>
          )}

          {/* Filtre domaine — visible dès 4+ scans */}
          {scans.length >= 4 && (
            <div className="relative mb-4">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-600 pointer-events-none" />
              <input
                type="text"
                value={domainFilter}
                onChange={e => setDomainFilter(e.target.value)}
                placeholder={lang === 'fr' ? 'Filtrer par domaine…' : 'Filter by domain…'}
                className="w-full pl-8 pr-8 py-2 text-xs text-slate-300 placeholder:text-slate-600 focus:outline-none transition rounded-xl sku-inset"
                style={domainFilter ? { borderColor: 'rgba(34,211,238,0.35)' } : {}}
              />
              {domainFilter && (
                <button
                  onClick={() => setDomainFilter('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-600 hover:text-slate-400 transition"
                >
                  <X size={12} />
                </button>
              )}
            </div>
          )}

          {/* List */}
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <div className="w-8 h-8 border-2 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin" />
            </div>
          ) : error ? (
            <div className="text-center py-20 text-red-400 text-sm">{error}</div>
          ) : scans.length === 0 ? (
            <div className="flex flex-col items-center py-20 gap-4">
              <SkuIcon color="#22d3ee" size={52}><Shield size={24} className="text-cyan-300" /></SkuIcon>
              <p className="text-slate-500 text-sm">
                {lang === 'fr' ? 'Aucun scan enregistré' : 'No scans yet'}
              </p>
              <button onClick={onBack} className="text-cyan-400 hover:text-cyan-300 text-sm font-medium transition">
                {lang === 'fr' ? '→ Lancer un scan' : '→ Run a scan'}
              </button>
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center py-16 gap-4">
              <SkuIcon color="#64748b" size={44}><Search size={20} className="text-slate-300" /></SkuIcon>
              <p className="text-slate-500 text-sm">
                {lang === 'fr' ? `Aucun scan pour « ${domainFilter} »` : `No scans for "${domainFilter}"`}
              </p>
              <button
                onClick={() => setDomainFilter('')}
                className="mt-3 text-cyan-400 hover:text-cyan-300 text-xs font-medium transition"
              >
                {lang === 'fr' ? 'Effacer le filtre' : 'Clear filter'}
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              {filtered.map(scan => {
                const delta      = scoreDelta.get(scan.scan_uuid) ?? null;
                const isPreviewing = previewUuid === scan.scan_uuid;
                return (
                  <div key={scan.scan_uuid}>
                    {/* ── Scan card ────────────────────────────────────── */}
                    <motion.div
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, x: -20 }}
                      className={`group flex items-center gap-4 p-4 rounded-xl border ${scoreBg(scan.security_score)} cursor-pointer hover:border-opacity-50 transition-all ${isPreviewing ? 'rounded-b-none border-b-0' : ''}`}
                      onClick={() => onLoadScan?.(scan.scan_uuid)}
                    >
                      {/* Score + delta tendance */}
                      <div className="flex flex-col items-center min-w-[3.5rem]">
                        <div className={`text-2xl font-bold font-mono leading-none ${scoreColor(scan.security_score)}`}>
                          {scan.security_score}
                        </div>
                        {delta !== null && delta !== 0 && (
                          <div className={`flex items-center gap-0.5 mt-0.5 text-[10px] font-bold leading-none ${delta > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            {delta > 0 ? <TrendingUp size={9} /> : <TrendingDown size={9} />}
                            {delta > 0 ? '+' : ''}{delta}
                          </div>
                        )}
                        {delta === 0 && (
                          <div className="text-[9px] text-slate-600 mt-0.5 leading-none">stable</div>
                        )}
                      </div>

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <Globe size={13} className="text-slate-500 shrink-0" />
                          <span className="text-white font-mono text-sm truncate">{scan.domain}</span>
                          {scan.public_share && (
                            <button
                              onClick={e => { e.stopPropagation(); togglePreview(scan.scan_uuid); }}
                              title={lang === 'fr' ? 'Voir l\'aperçu du partage' : 'View share preview'}
                              className={`shrink-0 flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full border font-medium transition-all ${
                                isPreviewing
                                  ? 'bg-cyan-400/20 text-cyan-300 border-cyan-400/40'
                                  : 'bg-cyan-500/15 text-cyan-400 border-cyan-500/25 hover:bg-cyan-500/25'
                              }`}
                            >
                              <Eye size={9} />
                              {lang === 'fr' ? 'public' : 'public'}
                            </button>
                          )}
                        </div>
                        <div className="flex items-center gap-3 mt-1">
                          <span className="text-xs text-slate-500 flex items-center gap-1">
                            <Clock size={11} />
                            {new Date(scan.created_at).toLocaleDateString(lang === 'fr' ? 'fr-FR' : 'en-US', {
                              day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
                            })}
                          </span>
                          <span className="text-xs text-slate-600">
                            {scan.findings_count} {lang === 'fr' ? 'finding(s)' : 'finding(s)'}
                          </span>
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex items-center gap-1" onClick={e => e.stopPropagation()}>

                        {/* Export PDF */}
                        <button
                          onClick={() => exportPdf(scan.scan_uuid, scan.domain)}
                          disabled={pdfLoading === scan.scan_uuid}
                          title={lang === 'fr' ? 'Télécharger le rapport PDF' : 'Download PDF report'}
                          className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-slate-600 hover:text-cyan-400 hover:bg-cyan-500/10 transition-all"
                        >
                          {pdfLoading === scan.scan_uuid
                            ? <div className="w-3.5 h-3.5 border border-cyan-500/40 border-t-cyan-400 rounded-full animate-spin" />
                            : <FileDown size={14} />}
                        </button>

                        {/* Toggle share */}
                        <button
                          onClick={() => toggleShare(scan.scan_uuid)}
                          disabled={sharing === scan.scan_uuid}
                          title={
                            scan.public_share
                              ? (lang === 'fr' ? 'Désactiver le lien public' : 'Disable public link')
                              : (lang === 'fr' ? 'Activer le lien public (lien copié)' : 'Enable public link (link copied)')
                          }
                          className={`opacity-0 group-hover:opacity-100 p-1.5 rounded-lg transition-all ${
                            scan.public_share
                              ? 'text-cyan-400 bg-cyan-500/10 hover:bg-cyan-500/20 opacity-100'
                              : 'text-slate-600 hover:text-cyan-400 hover:bg-cyan-500/10'
                          }`}
                        >
                          {sharing === scan.scan_uuid
                            ? <div className="w-3.5 h-3.5 border border-cyan-500/40 border-t-cyan-400 rounded-full animate-spin" />
                            : copied === scan.scan_uuid
                              ? <Check size={14} className="text-green-400" />
                              : scan.public_share
                                ? <X size={14} />
                                : <Share2 size={14} />}
                        </button>

                        {/* Delete */}
                        <button
                          onClick={() => deleteScan(scan.scan_uuid)}
                          disabled={deleting === scan.scan_uuid}
                          title={lang === 'fr' ? 'Supprimer ce scan' : 'Delete this scan'}
                          className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-slate-600 hover:text-red-400 hover:bg-red-500/10 transition-all"
                        >
                          {deleting === scan.scan_uuid
                            ? <div className="w-3.5 h-3.5 border border-slate-500 border-t-transparent rounded-full animate-spin" />
                            : <Trash2 size={14} />}
                        </button>

                        <ChevronRight
                          size={16}
                          className="text-slate-600 group-hover:text-slate-400 transition ml-1"
                          onClick={() => onLoadScan?.(scan.scan_uuid)}
                        />
                      </div>
                    </motion.div>

                    {/* ── Share preview panel ─────────────────────────── */}
                    <AnimatePresence>
                      {isPreviewing && scan.public_share && (
                        <motion.div
                          key={`preview-${scan.scan_uuid}`}
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          exit={{ opacity: 0, height: 0 }}
                          transition={{ duration: 0.22, ease: 'easeOut' }}
                          style={{ overflow: 'hidden' }}
                          onClick={e => e.stopPropagation()}
                        >
                          <div className="sku-card rounded-t-none rounded-b-xl px-4 pt-3 pb-4 border-t border-slate-700/40">

                            {/* Panel header + platform tabs */}
                            <div className="flex items-center justify-between mb-3">
                              <div className="flex items-center gap-1.5">
                                <Eye size={12} className="text-cyan-400" />
                                <span className="text-[11px] font-medium text-slate-400">
                                  {lang === 'fr' ? 'Aperçu du lien partagé' : 'Shared link preview'}
                                </span>
                              </div>
                              <div className="flex items-center gap-1">
                                {(['x', 'linkedin', 'whatsapp'] as const).map(p => (
                                  <button
                                    key={p}
                                    onClick={() => setPreviewTab(p)}
                                    className={`px-2 py-0.5 rounded text-[10px] font-medium transition-all ${
                                      previewTab === p
                                        ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                                        : 'text-slate-500 hover:text-slate-300 hover:bg-slate-700/50'
                                    }`}
                                  >
                                    {p === 'x' ? 'X / Twitter' : p === 'linkedin' ? 'LinkedIn' : 'WhatsApp'}
                                  </button>
                                ))}
                              </div>
                            </div>

                            {/* Card mockup */}
                            <div className="rounded-xl overflow-hidden">
                              <AnimatePresence mode="wait">
                                <motion.div
                                  key={previewTab}
                                  initial={{ opacity: 0, y: 4 }}
                                  animate={{ opacity: 1, y: 0 }}
                                  exit={{ opacity: 0, y: -4 }}
                                  transition={{ duration: 0.15 }}
                                >
                                  {previewTab === 'x'         && <XCard         scan={scan} lang={lang} />}
                                  {previewTab === 'linkedin'  && <LinkedInCard  scan={scan} lang={lang} />}
                                  {previewTab === 'whatsapp'  && <WhatsAppCard  scan={scan} lang={lang} />}
                                </motion.div>
                              </AnimatePresence>
                            </div>

                            {/* URL + copy row */}
                            <div className="flex items-center gap-2 mt-3">
                              <div className="flex items-center gap-1.5 flex-1 min-w-0 bg-slate-900/60 border border-slate-700/50 rounded-lg px-2.5 py-1.5">
                                <Link2 size={10} className="text-slate-600 shrink-0" />
                                <code className="text-[10px] text-slate-500 font-mono truncate">
                                  {`${window.location.origin}/r/${scan.scan_uuid}`}
                                </code>
                              </div>
                              <button
                                onClick={() => {
                                  navigator.clipboard.writeText(`${window.location.origin}/r/${scan.scan_uuid}`).catch(() => {});
                                  setCopied(scan.scan_uuid);
                                  setTimeout(() => setCopied(null), 2500);
                                }}
                                className={`shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-medium transition-all border ${
                                  copied === scan.scan_uuid
                                    ? 'bg-green-500/10 text-green-400 border-green-500/30'
                                    : 'text-slate-400 hover:text-cyan-400 hover:bg-cyan-500/10 border-slate-700/50 hover:border-cyan-500/30'
                                }`}
                              >
                                {copied === scan.scan_uuid
                                  ? <><Check size={11} />{lang === 'fr' ? 'Copié !' : 'Copied!'}</>
                                  : <><Share2 size={11} />{lang === 'fr' ? 'Copier le lien' : 'Copy link'}</>
                                }
                              </button>
                            </div>

                            {/* Disclaimer */}
                            <p className="text-[9px] text-slate-600 mt-2 text-center">
                              {lang === 'fr'
                                ? 'Aperçu simulé — le rendu réel peut légèrement varier selon les plateformes.'
                                : 'Simulated preview — actual rendering may slightly vary across platforms.'}
                            </p>

                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                );
              })}
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
