import { useEffect, useState, useMemo, type ReactNode } from 'react';
import { Shield, Clock, Globe, Trash2, ChevronRight, FileDown, Share2, Check, X, Search, TrendingUp, TrendingDown } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useLanguage } from '../i18n/LanguageContext';
import { apiClient } from '../lib/api';
import PageNavbar from '../components/PageNavbar';

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

interface Props {
  onBack: () => void;
  onLoadScan?: (scanUuid: string) => void;
  onGoAdmin?: () => void;
  onGoClientSpace?: () => void;
  onGoContact?: () => void;
}

function SkuIcon({ children, color, size = 36 }: { children: ReactNode; color: string; size?: number }) {
  const r = Math.round(size * 0.28);
  return (
    <div className="shrink-0 flex items-center justify-center relative overflow-hidden"
      style={{
        width: size, height: size, borderRadius: r,
        background: `linear-gradient(150deg, ${color}30 0%, ${color}0d 100%)`,
        border: `1px solid ${color}40`,
        boxShadow: `0 4px 16px ${color}22, 0 1px 3px rgba(0,0,0,0.4), inset 0 1px 0 ${color}30, inset 0 -1px 0 rgba(0,0,0,0.3)`,
      }}
    >
      <div className="absolute inset-0 pointer-events-none"
        style={{ borderRadius: r, background: 'linear-gradient(180deg,rgba(255,255,255,0.07) 0%,transparent 50%)' }} />
      {children}
    </div>
  );
}

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

  // ── fix : utilise apiClient (auth header automatique) ──────────────────────
  async function deleteScan(uuid: string) {
    setDeleting(uuid);
    try {
      await apiClient.delete(`/scans/history/${uuid}`);
      setScans(prev => prev.filter(s => s.scan_uuid !== uuid));
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
      }
    } catch {
      /* silently ignore */
    } finally {
      setSharing(null);
    }
  }

  // ── Delta de score vs scan précédent pour le même domaine ─────────────────
  // Parcours chronologique → pour chaque scan, delta = score − score_précédent_même_domaine
  const scoreDelta = useMemo(() => {
    const lastScore = new Map<string, number>();   // domain → dernier score vu
    const delta     = new Map<string, number | null>(); // scan_uuid → delta
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
            <AnimatePresence>
              <div className="space-y-2">
                {filtered.map(scan => {
                  const delta = scoreDelta.get(scan.scan_uuid) ?? null;
                  return (
                    <motion.div
                      key={scan.scan_uuid}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, x: -20 }}
                      className={`group flex items-center gap-4 p-4 rounded-xl border ${scoreBg(scan.security_score)} cursor-pointer hover:border-opacity-50 transition-all`}
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
                          <div className="text-[9px] text-slate-600 mt-0.5 leading-none">
                            {lang === 'fr' ? 'stable' : 'stable'}
                          </div>
                        )}
                      </div>

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <Globe size={13} className="text-slate-500 shrink-0" />
                          <span className="text-white font-mono text-sm truncate">{scan.domain}</span>
                          {scan.public_share && (
                            <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded-full bg-cyan-500/15 text-cyan-400 border border-cyan-500/25 font-medium">
                              {lang === 'fr' ? 'public' : 'public'}
                            </span>
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
                  );
                })}
              </div>
            </AnimatePresence>
          )}

        </div>
      </div>
    </div>
  );
}
