// ─── ComplianceDashboard — Dashboard interactif NIS2/RGPD ──────────────────
import { useState, useEffect, useCallback, type ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Shield, CheckCircle2, XCircle, AlertTriangle,
  ChevronDown, ChevronUp, FileText, Loader2, Download,
} from 'lucide-react';
import { apiClient } from '../lib/api';
import { useLanguage } from '../i18n/LanguageContext';

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

interface OrgItem {
  id: string;
  label: string;
  description: string;
  nis2_articles: string[];
  rgpd_articles: string[];
  checked: boolean;
  notes: string;
}

interface CriterionResult {
  id: string;
  label_fr: string;
  label_en: string;
  status: string;
  regulations: string[];
  article_fr: string;
  article_en: string;
  desc_fr: string;
  desc_en: string;
}

interface Progress {
  tech_total: number;
  tech_pass: number;
  org_total: number;
  org_pass: number;
  total: number;
  completed: number;
}

interface ComplianceReport {
  domain: string;
  has_scan: boolean;
  nis2_score: number;
  rgpd_score: number;
  overall_level: string;
  criteria: CriterionResult[];
  organizational_items: OrgItem[];
  progress: Progress;
}

interface Props {
  domain: string;
  userPlan: string;
}

const T = {
  fr: {
    title: 'Conformité NIS2 & RGPD',
    techTab: 'Critères techniques',
    orgTab: 'Mesures organisationnelles',
    progressLabel: 'Progression globale',
    nis2Score: 'Score NIS2',
    rgpdScore: 'Score RGPD',
    noScan: 'Aucun scan disponible pour ce domaine. Lancez un scan depuis le dashboard pour voir les résultats techniques.',
    compliant: 'Conforme',
    partial: 'Partiellement conforme',
    critical: 'Non conforme',
    checked: 'Validé',
    unchecked: 'À faire',
    notePlaceholder: 'Notes (optionnel)…',
    saving: 'Enregistrement…',
    saved: 'Enregistré',
    requiresPaid: 'La checklist organisationnelle est disponible avec un abonnement Starter ou supérieur.',
    exportPdf: 'Exporter PDF',
  },
  en: {
    title: 'NIS2 & GDPR Compliance',
    techTab: 'Technical criteria',
    orgTab: 'Organizational measures',
    progressLabel: 'Overall progress',
    nis2Score: 'NIS2 Score',
    rgpdScore: 'GDPR Score',
    noScan: 'No scan available for this domain. Run a scan from the dashboard to see technical results.',
    compliant: 'Compliant',
    partial: 'Partially compliant',
    critical: 'Non-compliant',
    checked: 'Done',
    unchecked: 'To do',
    notePlaceholder: 'Notes (optional)…',
    saving: 'Saving…',
    saved: 'Saved',
    requiresPaid: 'The organizational checklist is available with a Starter plan or above.',
    exportPdf: 'Export PDF',
  },
} as const;

const PAID_PLANS = new Set(['starter', 'pro', 'dev']);

function StatusIcon({ status }: { status: string }) {
  if (status === 'pass') return <CheckCircle2 size={16} className="text-green-400 shrink-0" />;
  if (status === 'fail') return <XCircle size={16} className="text-red-400 shrink-0" />;
  if (status === 'warn') return <AlertTriangle size={16} className="text-amber-400 shrink-0" />;
  return <div className="w-4 h-4 rounded-full bg-slate-700 shrink-0" />;
}

export default function ComplianceDashboard({ domain, userPlan }: Props) {
  const { lang } = useLanguage();
  const t = T[lang] ?? T.fr;
  const isPaid = PAID_PLANS.has(userPlan);

  const [report, setReport] = useState<ComplianceReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'tech' | 'org'>('tech');
  const [savingId, setSavingId] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);

  const fetchReport = useCallback(() => {
    setLoading(true);
    apiClient
      .get('/compliance/report', { params: { domain, lang } })
      .then(r => setReport(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [domain, lang]);

  useEffect(() => { fetchReport(); }, [fetchReport]);

  const toggleItem = async (itemId: string, checked: boolean, notes: string) => {
    if (!isPaid) return;
    setSavingId(itemId);
    try {
      await apiClient.patch('/compliance/checklist', { domain, item_id: itemId, checked, notes });
      // Update local state
      setReport(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          organizational_items: prev.organizational_items.map(i =>
            i.id === itemId ? { ...i, checked, notes } : i
          ),
          progress: {
            ...prev.progress,
            org_pass: prev.organizational_items.reduce(
              (sum, i) => sum + (i.id === itemId ? (checked ? 1 : 0) : (i.checked ? 1 : 0)), 0
            ),
            completed: prev.progress.tech_pass + prev.organizational_items.reduce(
              (sum, i) => sum + (i.id === itemId ? (checked ? 1 : 0) : (i.checked ? 1 : 0)), 0
            ),
          },
        };
      });
    } catch { /* silent */ }
    finally { setSavingId(null); }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 size={24} className="animate-spin text-cyan-400" />
      </div>
    );
  }

  if (!report) return null;

  const scoreColor = (score: number) =>
    score >= 80 ? '#4ade80' : score >= 50 ? '#fbbf24' : '#f87171';

  const levelLabel = report.overall_level === 'bon' ? t.compliant
    : report.overall_level === 'insuffisant' ? t.partial
    : t.critical;

  const pct = report.progress.total > 0
    ? Math.round((report.progress.completed / report.progress.total) * 100)
    : 0;

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <SkuIcon color="#818cf8" size={44}>
          <Shield size={22} className="text-indigo-300" />
        </SkuIcon>
        <div className="flex-1">
          <h2 className="text-lg font-bold text-white">{t.title}</h2>
          <p className="text-sm text-slate-500 font-mono">{domain}</p>
        </div>
        <div className="flex items-center gap-2">
          {isPaid && (
            <button
              onClick={async () => {
                setPdfLoading(true);
                try {
                  const res = await apiClient.get('/compliance/export', {
                    params: { domain, lang },
                    responseType: 'blob',
                  });
                  const url = URL.createObjectURL(res.data);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `compliance_${domain.replace(/\./g, '_')}_${lang}.pdf`;
                  a.click();
                  URL.revokeObjectURL(url);
                } catch { /* silencieux */ }
                setPdfLoading(false);
              }}
              disabled={pdfLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-indigo-500/15 text-indigo-300 border border-indigo-500/25 hover:bg-indigo-500/25 transition-all disabled:opacity-50"
            >
              {pdfLoading ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
              {t.exportPdf}
            </button>
          )}
          <span
            className="text-sm font-bold px-3 py-1 rounded-full"
            style={{
              color: scoreColor(Math.round((report.nis2_score + report.rgpd_score) / 2)),
              background: `${scoreColor(Math.round((report.nis2_score + report.rgpd_score) / 2))}15`,
            }}
          >
            {levelLabel}
          </span>
        </div>
      </div>

      {/* Progress bar */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-slate-500">{t.progressLabel}</span>
          <span className="text-xs font-mono text-slate-400">
            {report.progress.completed}/{report.progress.total} ({pct}%)
          </span>
        </div>
        <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
          <motion.div
            className="h-full rounded-full"
            style={{ background: 'linear-gradient(90deg, #22d3ee, #818cf8)' }}
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
          />
        </div>
      </div>

      {/* Score cards */}
      <div className="grid grid-cols-2 gap-4">
        {[
          { label: t.nis2Score, score: report.nis2_score, color: '#60a5fa' },
          { label: t.rgpdScore, score: report.rgpd_score, color: '#a78bfa' },
        ].map(s => (
          <div
            key={s.label}
            className="p-4 rounded-xl border"
            style={{ borderColor: `${s.color}25`, background: `${s.color}08` }}
          >
            <p className="text-xs text-slate-500 mb-1">{s.label}</p>
            <span className="text-2xl font-black font-mono" style={{ color: scoreColor(s.score) }}>
              {s.score}
            </span>
            <span className="text-slate-600 text-sm font-mono">/100</span>
          </div>
        ))}
      </div>

      {/* Tab bar */}
      <div
        className="flex gap-1 rounded-xl p-1"
        style={{ background: 'linear-gradient(180deg,#0f151e,#0b1018)', border: '1px solid rgba(255,255,255,0.07)' }}
      >
        {(['tech', 'org'] as const).map(id => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex-1 py-2 px-3 rounded-lg text-xs font-semibold transition-all ${
              tab === id
                ? 'bg-slate-800 text-white shadow-sm border border-slate-700'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            {id === 'tech' ? t.techTab : t.orgTab}
            {id === 'org' && (
              <span className="ml-1.5 text-[10px] font-mono text-slate-600">
                {report.progress.org_pass}/{report.progress.org_total}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <AnimatePresence mode="wait">
        {tab === 'tech' && (
          <motion.div key="tech" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            {!report.has_scan && (
              <div className="p-4 rounded-xl border border-amber-500/20 bg-amber-500/5 text-xs text-slate-400">
                <AlertTriangle size={14} className="text-amber-400 inline mr-2" />
                {t.noScan}
              </div>
            )}
            <div className="flex flex-col gap-3">
              {report.criteria.map(c => {
                const label = lang === 'en' ? c.label_en : c.label_fr;
                const desc = lang === 'en' ? c.desc_en : c.desc_fr;
                const article = lang === 'en' ? c.article_en : c.article_fr;
                const borderColor = c.status === 'fail' ? 'border-red-500/20' : c.status === 'warn' ? 'border-amber-500/20' : c.status === 'pass' ? 'border-green-500/15' : 'border-slate-800';
                const bg = c.status === 'fail' ? 'bg-red-500/5' : c.status === 'warn' ? 'bg-amber-500/5' : c.status === 'pass' ? 'bg-green-500/5' : 'bg-slate-900/30';
                return (
                  <div key={c.id} className={`flex items-start gap-3 p-4 rounded-xl border ${borderColor} ${bg}`}>
                    <StatusIcon status={c.status} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center flex-wrap gap-1.5 mb-1">
                        <span className="text-white text-sm font-semibold">{label}</span>
                        {c.regulations.map(r => (
                          <span key={r} className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wide ${
                            r === 'NIS2'
                              ? 'bg-blue-500/15 text-blue-400 border border-blue-500/25'
                              : 'bg-purple-500/15 text-purple-400 border border-purple-500/25'
                          }`}>{r}</span>
                        ))}
                      </div>
                      <p className="text-slate-500 text-xs leading-relaxed">{desc}</p>
                      <p className="text-slate-600 text-[10px] mt-1 font-mono">{article}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </motion.div>
        )}

        {tab === 'org' && (
          <motion.div key="org" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            {!isPaid ? (
              <div className="p-5 rounded-xl border border-violet-500/20 bg-violet-500/5 text-center">
                <SkuIcon color="#a78bfa" size={44}>
                  <FileText size={20} className="text-violet-300" />
                </SkuIcon>
                <p className="text-sm text-slate-400 mt-3">{t.requiresPaid}</p>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {report.organizational_items.map(item => (
                  <OrgChecklistItem
                    key={item.id}
                    item={item}
                    saving={savingId === item.id}
                    onToggle={(checked, notes) => toggleItem(item.id, checked, notes)}
                    t={t}
                  />
                ))}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── Checklist item component ────────────────────────────────────────────────

function OrgChecklistItem({
  item,
  saving,
  onToggle,
  t,
}: {
  item: OrgItem;
  saving: boolean;
  onToggle: (checked: boolean, notes: string) => void;
  t: typeof T.fr | typeof T.en;
}) {
  const [expanded, setExpanded] = useState(false);
  const [notes, setNotes] = useState(item.notes);

  return (
    <div
      className={`rounded-xl border transition-all ${
        item.checked ? 'border-green-500/20 bg-green-500/5' : 'border-slate-800 bg-slate-900/30'
      }`}
    >
      <div className="flex items-center gap-3 p-4">
        {/* Checkbox */}
        <button
          onClick={() => onToggle(!item.checked, notes)}
          disabled={saving}
          className="shrink-0"
        >
          {saving ? (
            <Loader2 size={18} className="animate-spin text-violet-400" />
          ) : item.checked ? (
            <CheckCircle2 size={18} className="text-green-400" />
          ) : (
            <div className="w-[18px] h-[18px] rounded-full border-2 border-slate-600 hover:border-violet-400 transition-colors" />
          )}
        </button>

        {/* Label */}
        <div className="flex-1 min-w-0 cursor-pointer" onClick={() => setExpanded(v => !v)}>
          <div className="flex items-center gap-2">
            <span className={`text-sm font-medium ${item.checked ? 'text-green-300' : 'text-slate-200'}`}>
              {item.label}
            </span>
            {item.nis2_articles.map(a => (
              <span key={a} className="text-[8px] font-bold px-1 py-0.5 rounded bg-blue-500/15 text-blue-400 border border-blue-500/25">
                {a}
              </span>
            ))}
            {item.rgpd_articles.map(a => (
              <span key={a} className="text-[8px] font-bold px-1 py-0.5 rounded bg-purple-500/15 text-purple-400 border border-purple-500/25">
                Art. {a}
              </span>
            ))}
          </div>
        </div>

        {/* Expand */}
        <button onClick={() => setExpanded(v => !v)} className="text-slate-600 hover:text-slate-400 shrink-0">
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 pt-0">
              <div className="h-px mb-3" style={{ background: 'rgba(255,255,255,0.05)' }} />
              <p className="text-xs text-slate-500 leading-relaxed mb-3">{item.description}</p>
              <textarea
                value={notes}
                onChange={e => setNotes(e.target.value)}
                onBlur={() => { if (notes !== item.notes && item.checked) onToggle(true, notes); }}
                placeholder={t.notePlaceholder}
                rows={2}
                className="w-full text-xs bg-slate-900/50 border border-slate-700 rounded-lg px-3 py-2 text-slate-300 placeholder-slate-600 focus:outline-none focus:border-violet-500/50 resize-none"
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
