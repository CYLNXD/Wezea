import { useEffect, useState } from 'react';
import { Shield, Clock, Globe, Trash2, ChevronRight } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../i18n/LanguageContext';
import PageNavbar from '../components/PageNavbar';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface ScanSummary {
  id: number;
  scan_uuid: string;
  domain: string;
  security_score: number;
  risk_level: string;
  findings_count: number;
  scan_duration: number;
  created_at: string;
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

  const [scans,   setScans]   = useState<ScanSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState('');
  const [deleting, setDeleting] = useState<string | null>(null);

  useEffect(() => {
    fetchHistory();
  }, []);

  async function fetchHistory() {
    setLoading(true);
    try {
      const res = await fetch(`${API}/scans/history?limit=50`, {
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error('Erreur de chargement');
      const data = await res.json();
      setScans(data.scans);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function deleteScan(uuid: string) {
    setDeleting(uuid);
    try {
      await fetch(`${API}/scans/history/${uuid}`, {
        method:  'DELETE',
        headers: authHeaders(),
      });
      setScans(prev => prev.filter(s => s.scan_uuid !== uuid));
    } finally {
      setDeleting(null);
    }
  }

  return (
    <div className="min-h-screen flex flex-col" style={{ backgroundColor: 'var(--color-bg)' }}>
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
                  <div className="flex items-center gap-2">
                    <button
                      onClick={e => { e.stopPropagation(); deleteScan(scan.scan_uuid); }}
                      disabled={deleting === scan.scan_uuid}
                      className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-slate-600 hover:text-red-400 hover:bg-red-500/10 transition-all"
                    >
                      {deleting === scan.scan_uuid
                        ? <div className="w-3.5 h-3.5 border border-slate-500 border-t-transparent rounded-full animate-spin" />
                        : <Trash2 size={14} />}
                    </button>
                    <ChevronRight size={16} className="text-slate-600 group-hover:text-slate-400 transition" />
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
