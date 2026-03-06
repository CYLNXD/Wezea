import { useEffect, useState } from 'react';
import { Shield, Clock, Globe, Trash2, ChevronRight, FileDown, Share2, Check, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from '../contexts/AuthContext';
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

export default function HistoryPage({ onBack, onLoadScan, onGoAdmin, onGoClientSpace, onGoContact }: Props) {
  const { authHeaders } = useAuth();
  const { lang } = useLanguage();

  const [scans,      setScans]      = useState<ScanSummary[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [error,      setError]      = useState('');
  const [deleting,   setDeleting]   = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState<string | null>(null);
  const [sharing,    setSharing]    = useState<string | null>(null);
  const [copied,     setCopied]     = useState<string | null>(null);

  useEffect(() => {
    fetchHistory();
  }, []);

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
      await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/scans/history/${uuid}`, {
        method:  'DELETE',
        headers: authHeaders(),
      });
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
      /* silently ignore — user already has the history */
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
      // Si le partage vient d'être activé, copier le lien
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

  return (
    <div className="relative min-h-screen flex flex-col">
      {/* Grille cyber — identique au hero Dashboard */}
      <div className="absolute inset-0 pointer-events-none" style={{ backgroundImage: 'linear-gradient(rgba(34,211,238,1) 1px, transparent 1px), linear-gradient(90deg, rgba(34,211,238,1) 1px, transparent 1px)', backgroundSize: '48px 48px', opacity: 0.025 }} />
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

        {/* List */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="w-8 h-8 border-2 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin" />
          </div>
        ) : error ? (
          <div className="text-center py-20 text-red-400 text-sm">{error}</div>
        ) : scans.length === 0 ? (
          <div className="text-center py-20">
            <Shield size={40} className="text-slate-700 mx-auto mb-3" />
            <p className="text-slate-500 text-sm">
              {lang === 'fr' ? 'Aucun scan enregistré' : 'No scans yet'}
            </p>
            <button onClick={onBack} className="mt-4 text-cyan-400 hover:text-cyan-300 text-sm font-medium transition">
              {lang === 'fr' ? '→ Lancer un scan' : '→ Run a scan'}
            </button>
          </div>
        ) : (
          <AnimatePresence>
            <div className="space-y-2">
              {scans.map(scan => (
                <motion.div
                  key={scan.scan_uuid}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  className={`group flex items-center gap-4 p-4 rounded-xl border ${scoreBg(scan.security_score)} cursor-pointer hover:border-opacity-50 transition-all`}
                  onClick={() => onLoadScan?.(scan.scan_uuid)}
                >
                  {/* Score */}
                  <div className={`text-2xl font-bold font-mono min-w-[3rem] text-center ${scoreColor(scan.security_score)}`}>
                    {scan.security_score}
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
                          day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'
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

                    <ChevronRight size={16} className="text-slate-600 group-hover:text-slate-400 transition ml-1" onClick={() => onLoadScan?.(scan.scan_uuid)} />
                  </div>
                </motion.div>
              ))}
            </div>
          </AnimatePresence>
        )}
      </div>
      </div>
    </div>
  );
}
