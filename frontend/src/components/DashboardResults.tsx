// ─── DashboardResults.tsx — Results section extracted from Dashboard ─────────
//
// Renders the full results view after a successful scan:
//   - Score panel with gauge, stats, port summary, monitoring widget
//   - Security maturity widget (industry comparison)
//   - Results-not-saved notice (anonymous users)
//   - Tab navigation (actions/vulns/surveillance/compliance) with 4 tab contents
//   - Disclaimer text
//
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import SkuIcon from './SkuIcon';
import {
  Shield, ArrowRight, FileDown, Globe, AlertTriangle, Info, Lock, X, UserPlus, MessageSquare,
  CheckCircle, Zap, Eye, Star, BookOpen,
  TrendingUp, TrendingDown, Database, FileText, Scale, Award, ListChecks,
} from 'lucide-react';

import { useLanguage } from '../i18n/LanguageContext';
import { useAuth } from '../contexts/AuthContext';
import { ScoreGauge } from './ScoreGauge';
import { FindingCard, FindingGroup } from './FindingCard';
import type { Finding, ScanResult, ComplianceArticle } from '../types/scanner';
import { SEVERITY_CONFIG } from '../types/scanner';
import {
  captureRegisterCtaClicked, capturePricingModalOpened,
} from '../lib/analytics';
import type { PricingSource, RegisterCtaSource } from '../lib/analytics';

// ─── MiniSparkline — historique des scores ────────────────────────────────────
function MiniSparkline({ scores }: { scores: number[] }) {
  if (scores.length < 2) return null;
  const W = 130, H = 30, PAD = 3;
  const min = Math.min(...scores), max = Math.max(...scores);
  const range = max - min || 10; // évite division par 0
  const pts = scores.map((v, i) => ({
    x: PAD + (i / (scores.length - 1)) * (W - PAD * 2),
    y: PAD + (1 - (v - min) / range) * (H - PAD * 2),
  }));
  const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  const last = scores[scores.length - 1];
  const color = last >= 70 ? '#4ade80' : last >= 40 ? '#fb923c' : '#f87171';
  return (
    <svg width={W} height={H} className="shrink-0 overflow-visible">
      <path d={line} stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" opacity="0.8" />
      <circle cx={pts[pts.length - 1].x} cy={pts[pts.length - 1].y} r="2.5" fill={color} />
    </svg>
  );
}

// ─── StatCard ─────────────────────────────────────────────────────────────────
function StatCard({
  label, value, highlight, small,
}: {
  label: string; value: string | number; highlight?: boolean; small?: boolean;
}) {
  return (
    <div className={`
      rounded-xl border p-3 text-center
      ${highlight
        ? 'border-red-500/40 bg-red-500/5'
        : 'border-slate-800 bg-slate-900'}
    `}>
      <p className={`font-black ${small ? 'text-lg' : 'text-2xl'} font-mono ${highlight ? 'text-red-400' : 'text-white'}`}>
        {value}
      </p>
      <p className="text-slate-500 text-[10px] font-mono mt-0.5">{label}</p>
    </div>
  );
}

// ─── PortSummary ──────────────────────────────────────────────────────────────
function PortSummary({ portDetails }: { portDetails: Record<string, { service: string; open: boolean; severity: string }> }) {
  const { t } = useLanguage();
  const entries = Object.entries(portDetails)
    .map(([port, v]) => ({ port: parseInt(port), ...v }))
    .sort((a, b) => a.port - b.port);

  const openPorts  = entries.filter(p => p.open);
  const closedCount = entries.filter(p => !p.open).length;

  if (entries.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.3 }}
      className="bg-slate-900/60 border border-slate-800 rounded-xl p-4"
    >
      <h4 className="text-xs font-mono text-slate-500 uppercase tracking-widest mb-3 flex items-center gap-2">
        <Globe size={12} />
        {t('ports_map')}
        <span className="ml-auto text-slate-700 font-normal normal-case">
          {openPorts.length} {t('ports_open', { closed: closedCount })}
        </span>
      </h4>
      <div className="flex flex-wrap gap-2">
        {entries.map(({ port, service, open, severity }) => (
          <div
            key={port}
            className={`
              flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono border
              ${open
                ? severity === 'CRITICAL'
                  ? 'bg-red-500/15 border-red-500/40 text-red-300'
                  : severity === 'HIGH'
                  ? 'bg-orange-500/15 border-orange-500/40 text-orange-300'
                  : 'bg-blue-500/10 border-blue-500/30 text-blue-300'
                : 'bg-slate-800/60 border-slate-700/50 text-slate-600'}
            `}
          >
            <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${open ? (severity === 'CRITICAL' ? 'bg-red-500' : 'bg-orange-400') : 'bg-slate-700'}`} />
            {port}
            <span className="text-[10px] opacity-70">{service}</span>
          </div>
        ))}
      </div>
    </motion.div>
  );
}

// ─── groupFindings ────────────────────────────────────────────────────────────
function groupFindings(findings: Finding[]) {
  return {
    dns:        findings.filter(f => f.category === 'DNS & Mail'),
    ssl:        findings.filter(f => f.category === 'SSL / HTTPS'),
    ports:      findings.filter(f => f.category === 'Exposition des Ports'),
    headers:    findings.filter(f => f.category === 'En-têtes HTTP'),
    emailSec:   findings.filter(f => f.category === 'Sécurité Email'),
    tech:       findings.filter(f => f.category === 'Exposition Technologique'),
    reputation: findings.filter(f => f.category === 'Réputation du Domaine' && f.severity !== 'INFO'),
    subdomains: findings.filter(f => f.category === 'Sous-domaines & Certificats'),
    vulns:      findings.filter(f => f.category === 'Versions Vulnérables'),
    info:       findings.filter(f => f.severity === 'INFO'),
  };
}

// ─── Props ────────────────────────────────────────────────────────────────────
export interface DashboardResultsProps {
  scanResult: ScanResult;
  // Score comparison
  previousScore:   number | null;
  domainHistory:   number[];
  // Public stats for maturity widget
  publicStats:     { total_scans: number; industry_avg?: number } | null;
  // Blog links for recommendations
  blogLinks:       Array<{ id: number; match_keyword: string; article_title: string; article_url: string }>;
  // Monitoring
  monitoringOpen:      boolean;
  setMonitoringOpen:   (v: boolean | ((prev: boolean) => boolean)) => void;
  monitoredDomains:    Array<{ domain: string; last_score: number | null; last_risk_level: string | null; last_scan_at: string | null }>;
  monitoringLoading:   boolean;
  monitoringInput:     string;
  setMonitoringInput:  (v: string) => void;
  addToMonitoring:     (domain: string) => void;
  removeFromMonitoring:(domain: string) => void;
  // PDF
  downloadPdf:   () => void;
  pdfLoading:    boolean;
  pdfError:      string | null;
  // Modals
  openEmailCaptureModal: () => void;
  openPricingModal:      (source: PricingSource) => void;
}

// ─── Component ────────────────────────────────────────────────────────────────
export default function DashboardResults({
  scanResult: r,
  previousScore,
  domainHistory,
  publicStats,
  blogLinks,
  monitoringOpen,
  setMonitoringOpen,
  monitoredDomains,
  monitoringLoading,
  monitoringInput,
  setMonitoringInput,
  addToMonitoring,
  removeFromMonitoring,
  downloadPdf,
  pdfLoading,
  pdfError,
  openEmailCaptureModal,
  openPricingModal,
}: DashboardResultsProps) {
  const navigate = useNavigate();
  const { lang, t } = useLanguage();
  const { user } = useAuth();

  const [activeTab, setActiveTab] = useState<'actions' | 'vulnerabilities' | 'surveillance' | 'conformite'>('actions');
  const [severityFilter, setSeverityFilter] = useState<'all' | 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'>('all');

  const isPremium = user?.plan === 'starter' || user?.plan === 'pro' || user?.plan === 'dev';
  const isAnon = !user;

  // ── Helpers analytics ──────────────────────────────────────────────────────
  const openPricing = (source: PricingSource) => {
    capturePricingModalOpened(source);
    openPricingModal(source);
  };
  const goRegister = (source: RegisterCtaSource) => {
    captureRegisterCtaClicked(source);
    navigate('/register');
  };

  // Anonymes : exclure les LOW des groups visibles (affichés dans un gate séparé)
  const visibleForGroups = isAnon
    ? r.findings.filter(f => f.severity !== 'LOW' && f.severity !== 'INFO')
    : r.findings.filter(f => f.severity !== 'INFO');
  const infoFindings = r.findings.filter(f => f.severity === 'INFO');
  const groups = groupFindings(visibleForGroups);
  const nonInfoCount = r.findings.filter(f => f.severity !== 'INFO').length;
  const breachCount = r.breach_details?.breach_count ?? 0;
  const isPremiumPlan = user && user.plan !== 'free';

  return (
    <>
      <motion.div
        key="results"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.15 }}
        className="flex flex-col gap-6 py-8"
      >
        {/* ── Bande supérieure : Score + Stats + PDF ─────────────── */}
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="sku-panel rounded-2xl overflow-hidden"
        >
          <div className="flex flex-col lg:flex-row">
            {/* Score gauge */}
            <div className="flex flex-col items-center justify-center gap-3 p-6 lg:border-r border-b lg:border-b-0 border-slate-800 shrink-0">
              <ScoreGauge
                score={r.security_score}
                riskLevel={r.risk_level}
                domain={r.domain}
              />
              {/* Delta vs scan précédent */}
              {previousScore !== null && (() => {
                const delta = r.security_score - previousScore;
                if (delta === 0) return (
                  <span className="text-[11px] text-slate-500 font-mono">
                    = stable vs scan précédent
                  </span>
                );
                const up = delta > 0;
                return (
                  <span className={`flex items-center gap-1 text-[11px] font-mono font-semibold px-2.5 py-1 rounded-full border ${
                    up
                      ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/25'
                      : 'text-red-400 bg-red-500/10 border-red-500/25'
                  }`}>
                    {up ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
                    {up ? '+' : ''}{delta} pts vs scan précédent
                  </span>
                );
              })()}
            </div>
            {/* Stats + PDF + meta */}
            <div className="flex-1 flex flex-col justify-between gap-4 p-6">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <StatCard
                  label={t('stat_vulns')}
                  value={nonInfoCount}
                  highlight={r.findings.some(f => f.severity === 'CRITICAL')}
                />
                <StatCard
                  label={t('stat_ports')}
                  value={Object.values(r.port_details).filter(p => p.open && p.severity === 'CRITICAL').length}
                  highlight={Object.values(r.port_details).some(p => p.open && p.severity === 'CRITICAL')}
                />
                <StatCard
                  label={t('stat_dns')}
                  value={`−${groups.dns.reduce((s, f) => s + (f.penalty ?? 0), 0)} pts`}
                  highlight={groups.dns.some(f => (f.penalty ?? 0) > 0)}
                  small
                />
                <StatCard
                  label={t('stat_ssl')}
                  value={`−${groups.ssl.reduce((s, f) => s + (f.penalty ?? 0), 0)} pts`}
                  highlight={groups.ssl.some(f => (f.penalty ?? 0) > 0)}
                  small
                />
              </div>
              <PortSummary portDetails={r.port_details} />
              {/* Mini sparkline — historique des scores du domaine */}
              {domainHistory.length >= 2 && (
                <div className="flex items-center gap-3 px-3 py-2 rounded-xl bg-slate-800/40 border border-slate-700/50">
                  <div className="flex flex-col shrink-0">
                    <span className="text-[10px] text-slate-500 font-mono leading-tight">historique</span>
                    <span className="text-xs text-slate-400 font-mono font-bold leading-tight">{domainHistory.length} scans</span>
                  </div>
                  <MiniSparkline scores={domainHistory} />
                  <div className="flex flex-col items-end shrink-0 ml-auto">
                    <span className="text-[10px] text-slate-500 font-mono leading-tight">
                      {Math.min(...domainHistory)} → {Math.max(...domainHistory)}
                    </span>
                    <span className="text-[10px] text-slate-600 font-mono leading-tight">min / max</span>
                  </div>
                </div>
              )}
              {isPremium && (
                <div className="rounded-xl border border-slate-700/60 bg-slate-800/30 overflow-hidden">
                  <button
                    onClick={() => setMonitoringOpen(v => !v)}
                    className="w-full flex items-center justify-between px-5 py-3 text-sm font-semibold text-slate-300 hover:bg-slate-700/30 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <Globe size={14} className="text-cyan-400" />
                      <span>Monitoring hebdomadaire</span>
                      {monitoredDomains.length > 0 && (
                        <span className="text-xs bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 px-1.5 py-0.5 rounded-full">
                          {monitoredDomains.length} domaine{monitoredDomains.length > 1 ? 's' : ''}
                        </span>
                      )}
                    </div>
                    <span className={`text-slate-500 transition-transform ${monitoringOpen ? 'rotate-90' : ''}`}>▶</span>
                  </button>
                  {monitoringOpen && (
                    <div className="px-5 pb-5 flex flex-col gap-4">
                      <div className="flex gap-2 flex-wrap">
                        <input
                          type="text"
                          placeholder="exemple.com"
                          value={monitoringInput}
                          onChange={e => setMonitoringInput(e.target.value)}
                          onKeyDown={e => { if (e.key === 'Enter' && monitoringInput.trim()) { addToMonitoring(monitoringInput.trim()); setMonitoringInput(''); } }}
                          className="flex-1 min-w-0 sm:min-w-[180px] bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-cyan-500 transition placeholder:text-slate-600"
                        />
                        <button
                          onClick={() => { if (monitoringInput.trim()) { addToMonitoring(monitoringInput.trim()); setMonitoringInput(''); } }}
                          className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 hover:bg-cyan-500/30 transition-colors text-xs font-semibold"
                        >
                          <UserPlus size={13} />
                          Ajouter
                        </button>
                        {!monitoredDomains.find(d => d.domain === r.domain) && (
                          <button
                            onClick={() => addToMonitoring(r.domain)}
                            className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-700/60 text-slate-300 border border-slate-600/40 hover:bg-slate-700 transition-colors text-xs font-semibold"
                          >
                            <Globe size={13} />
                            + {r.domain}
                          </button>
                        )}
                      </div>
                      {monitoringLoading ? (
                        <p className="text-xs text-slate-500">Chargement…</p>
                      ) : monitoredDomains.length === 0 ? (
                        <p className="text-xs text-slate-500">Aucun domaine sous surveillance. Saisissez un domaine ci-dessus pour commencer.</p>
                      ) : (
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                          {monitoredDomains.map(d => (
                            <div key={d.domain} className="flex items-center justify-between bg-slate-900/60 border border-slate-800 rounded-lg px-3 py-2.5">
                              <div className="flex items-center gap-2 min-w-0">
                                <Globe size={11} className="text-slate-500 shrink-0" />
                                <span className="text-slate-200 font-mono text-xs truncate">{d.domain}</span>
                                {d.last_score !== null && (
                                  <span className={`text-xs font-bold shrink-0 ${d.last_score >= 70 ? 'text-green-400' : d.last_score >= 40 ? 'text-orange-400' : 'text-red-400'}`}>
                                    {d.last_score}/100
                                  </span>
                                )}
                              </div>
                              <button onClick={() => removeFromMonitoring(d.domain)} className="text-slate-600 hover:text-red-400 transition-colors ml-2 shrink-0" title="Retirer du monitoring">
                                <X size={12} />
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
                      <p className="text-[10px] text-slate-600 font-mono">
                        {lang === 'fr'
                          ? 'Scan automatique selon la fréquence configurée · Alerte email si baisse ≥ 10 pts'
                          : 'Automatic scan at configured frequency · Email alert on score drop ≥ 10 pts'}
                      </p>
                    </div>
                  )}
                </div>
              )}
              <button
                onClick={() => user ? downloadPdf() : openEmailCaptureModal()}
                disabled={!!user && pdfLoading}
                className={`
                  flex items-center justify-center gap-2
                  w-full py-3 rounded-xl font-bold text-sm
                  transition-all duration-200
                  ${user
                    ? 'bg-gradient-to-r from-cyan-700/60 to-blue-700/60 hover:from-cyan-600/70 hover:to-blue-600/70 border border-cyan-500/40 text-cyan-200 disabled:opacity-50'
                    : r.security_score < 40
                      ? 'bg-gradient-to-r from-red-700/60 to-orange-700/60 hover:from-red-600/70 hover:to-orange-600/70 border border-red-500/40 text-red-200'
                      : r.security_score < 70
                      ? 'bg-gradient-to-r from-orange-700/50 to-yellow-700/50 hover:from-orange-600/60 hover:to-yellow-600/60 border border-orange-500/30 text-orange-200'
                      : 'bg-gradient-to-r from-cyan-700/50 to-blue-700/50 hover:from-cyan-600/60 hover:to-blue-600/60 border border-cyan-500/30 text-cyan-300'}
                `}
              >
                <FileDown size={15} />
                {user
                  ? (pdfLoading
                      ? (lang === 'fr' ? 'Génération…' : 'Generating…')
                      : (lang === 'fr' ? 'Télécharger le rapport PDF complet' : 'Download full PDF report'))
                  : r.security_score < 40
                    ? (lang === 'fr' ? 'Site en danger — Obtenir le plan de remédiation' : 'Site at risk — Get remediation plan')
                    : r.security_score < 70
                      ? (lang === 'fr'
                          ? `${nonInfoCount} risque(s) détecté(s) — Voir le plan de correction`
                          : `${nonInfoCount} risk(s) found — See correction plan`)
                      : (lang === 'fr' ? 'Télécharger le rapport complet' : 'Download full report')}
              </button>
              {pdfError && (
                <p className="text-center text-red-400 text-[10px] font-mono px-2 py-1 bg-red-500/10 rounded-lg border border-red-500/20">
                  ⚠ {pdfError}
                </p>
              )}
              <p className="text-center text-slate-700 text-[10px] font-mono">
                {t('scan_duration', { ms: (r.scan_duration_ms / 1000).toFixed(1), date: new Date(r.scanned_at).toLocaleString(lang === 'fr' ? 'fr-FR' : 'en-US') })}
              </p>
            </div>
          </div>
        </motion.div>

        {/* ── Maturité de sécurité — benchmark industrie ────────── */}
        {publicStats?.industry_avg !== undefined && (() => {
          const userScore = r.security_score;
          const avg       = publicStats.industry_avg!;
          const gap       = avg - userScore;
          const worse     = gap > 0;
          // Estimation du percentile : linéaire autour de la moyenne (±30 pts = ±45%)
          const rawPct    = 50 + Math.round(gap * 1.5);
          const pctBelowYou = Math.max(5, Math.min(95, rawPct));
          const scoreColor = userScore >= 70 ? '#4ade80' : userScore >= 40 ? '#fbbf24' : '#f87171';
          return (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.25 }}
              className="sku-panel rounded-2xl p-5"
            >
              {/* Titre */}
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
                    style={{ background: 'linear-gradient(135deg,#a78bfa30,#a78bfa0d)', border: '1px solid #a78bfa40' }}>
                    <TrendingUp size={14} className="text-violet-300" />
                  </div>
                  <span className="text-sm font-bold text-slate-200">
                    {lang === 'fr' ? 'Maturité de sécurité' : 'Security Maturity'}
                  </span>
                </div>
                <span className="text-[10px] font-mono text-slate-500 bg-slate-800/60 px-2 py-0.5 rounded-full border border-slate-700/50">
                  {lang === 'fr' ? 'vs moyenne PME' : 'vs SMB average'}
                </span>
              </div>

              {/* Barres comparatives */}
              <div className="flex flex-col gap-3 mb-4">
                {/* Barre utilisateur */}
                <div>
                  <div className="flex justify-between mb-1.5">
                    <span className="text-[11px] font-semibold text-slate-300 font-mono">
                      {lang === 'fr' ? 'Votre score' : 'Your score'}
                    </span>
                    <span className="text-[11px] font-bold font-mono" style={{ color: scoreColor }}>
                      {userScore}/100
                    </span>
                  </div>
                  <div className="w-full h-3 bg-slate-800 rounded-full overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${userScore}%` }}
                      transition={{ duration: 0.8, ease: 'easeOut', delay: 0.3 }}
                      className="h-full rounded-full"
                      style={{ background: `linear-gradient(90deg, ${scoreColor}cc, ${scoreColor})` }}
                    />
                  </div>
                </div>
                {/* Barre moyenne */}
                <div>
                  <div className="flex justify-between mb-1.5">
                    <span className="text-[11px] font-semibold text-slate-400 font-mono">
                      {lang === 'fr' ? 'Moyenne des entreprises' : 'Industry average'}
                    </span>
                    <span className="text-[11px] font-bold text-slate-400 font-mono">{avg}/100</span>
                  </div>
                  <div className="w-full h-3 bg-slate-800 rounded-full overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${avg}%` }}
                      transition={{ duration: 0.8, ease: 'easeOut', delay: 0.45 }}
                      className="h-full rounded-full bg-slate-600"
                    />
                  </div>
                </div>
              </div>

              {/* Message psychologique */}
              <div className={`rounded-xl px-4 py-3 border text-sm leading-snug ${
                worse
                  ? 'bg-red-500/8 border-red-500/25 text-red-300'
                  : 'bg-emerald-500/8 border-emerald-500/25 text-emerald-300'
              }`}>
                {worse ? (
                  lang === 'fr'
                    ? <><span className="font-bold">{pctBelowYou}% des entreprises analysées</span> ont un meilleur score que vous. Votre infrastructure est <span className="font-bold">{gap} points en dessous</span> de la moyenne.</>
                    : <><span className="font-bold">{pctBelowYou}% of analyzed companies</span> score higher than you. Your infrastructure is <span className="font-bold">{gap} points below</span> average.</>
                ) : (
                  lang === 'fr'
                    ? <>Votre score est <span className="font-bold">{Math.abs(gap)} points au-dessus</span> de la moyenne. Vous faites partie des <span className="font-bold">{100 - pctBelowYou}% d'entreprises</span> les mieux protégées.</>
                    : <>Your score is <span className="font-bold">{Math.abs(gap)} points above</span> average. You're among the <span className="font-bold">top {100 - pctBelowYou}%</span> of protected companies.</>
                )}
              </div>

              {/* CTA pour anonymes */}
              {!user && worse && (
                <button
                  onClick={() => { captureRegisterCtaClicked('maturity_widget'); navigate('/register'); }}
                  className="mt-3 w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-bold bg-violet-500/15 border border-violet-500/35 text-violet-300 hover:bg-violet-500/25 transition-colors"
                >
                  <UserPlus size={14} />
                  {lang === 'fr'
                    ? `Corriger ces ${gap} points — Créer un compte gratuit`
                    : `Fix this ${gap}-point gap — Create a free account`}
                </button>
              )}
            </motion.div>
          );
        })()}

        {/* ── Notice "Résultats non sauvegardés" (anonyme uniquement) ── */}
        {!user && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="flex items-center gap-3 rounded-xl border border-amber-500/25 bg-amber-500/5 px-4 py-3 mb-2"
          >
            <SkuIcon color="#fbbf24" size={32}>
              <AlertTriangle size={15} className="text-amber-300" />
            </SkuIcon>
            <div className="flex-1 min-w-0">
              <p className="text-amber-200 text-sm font-semibold">
                {lang === 'fr' ? 'Résultats non sauvegardés' : 'Results not saved'}
              </p>
              <p className="text-slate-400 text-xs mt-0.5 leading-snug">
                {lang === 'fr'
                  ? 'Créez un compte gratuit pour retrouver ces résultats à tout moment.'
                  : 'Create a free account to access these results at any time.'}
              </p>
            </div>
            <button
              onClick={() => goRegister('results_save')}
              className="shrink-0 sku-btn-primary text-xs px-3 py-1.5 rounded-lg whitespace-nowrap"
            >
              {lang === 'fr' ? 'Sauvegarder →' : 'Save →'}
            </button>
          </motion.div>
        )}

        {/* ── Onglets ─────────────────────────────────────────────── */}
        <div>
          {/* Barre de navigation */}
          <div className="flex items-center gap-0 border-b border-slate-800 mb-6 overflow-x-auto scrollbar-hide">
            {([
              { id: 'actions'         as const,
                label:      lang === 'fr' ? `Actions${r.findings.some(f => f.severity === 'CRITICAL') ? ' 🔴' : ''}` : `Actions${r.findings.some(f => f.severity === 'CRITICAL') ? ' 🔴' : ''}`,
                shortLabel: 'Actions',
                icon: <Zap size={13} />,
                dot: r.findings.some(f => f.severity === 'CRITICAL'),
              },
              { id: 'vulnerabilities' as const,
                label:      lang === 'fr' ? `Vulnérabilités (${nonInfoCount})` : `Vulns (${nonInfoCount})`,
                shortLabel: lang === 'fr' ? `Vulnés (${nonInfoCount})` : `Vulns (${nonInfoCount})`,
                icon: <AlertTriangle size={13} />,
                dot: false,
              },
              { id: 'surveillance'    as const,
                label:      lang === 'fr' ? `Surveillance${breachCount > 0 ? ` (${breachCount})` : ''}` : `Threat Intel${breachCount > 0 ? ` (${breachCount})` : ''}`,
                shortLabel: lang === 'fr' ? 'Veille' : 'Intel',
                icon: <Globe size={13} />,
                dot: breachCount > 0,
              },
              { id: 'conformite'      as const,
                label:      lang === 'fr' ? 'Conformité' : 'Compliance',
                shortLabel: lang === 'fr' ? 'NIS2/RGPD' : 'Compliance',
                icon: <Scale size={13} />,
                dot: false,
              },
            ]).map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`
                  relative flex items-center gap-1.5 px-3 sm:px-4 py-3 text-xs sm:text-sm font-semibold transition-all whitespace-nowrap shrink-0 min-h-[44px]
                  ${activeTab === tab.id ? 'text-white' : 'text-slate-500 hover:text-slate-300'}
                `}
              >
                <span className={activeTab === tab.id ? 'text-cyan-400' : 'text-slate-600'}>{tab.icon}</span>
                <span className="hidden sm:inline">{tab.label}</span>
                <span className="sm:hidden">{tab.shortLabel}</span>
                {tab.dot && <span className="w-1.5 h-1.5 rounded-full bg-red-500 absolute top-2 right-1" />}
                {activeTab === tab.id && (
                  <motion.span
                    layoutId="tab-underline"
                    className="absolute bottom-0 left-0 right-0 h-0.5 bg-cyan-400 rounded-full"
                  />
                )}
              </button>
            ))}
          </div>

          {/* Contenu des onglets */}
          <AnimatePresence mode="wait">

            {/* ── Onglet Actions (plan d'action + recommandations) ──── */}
            {activeTab === 'actions' && (
              <motion.div
                key="tab-actions"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.18 }}
                className="flex flex-col gap-5"
              >
                {/* Cas : aucune vulnérabilité */}
                {nonInfoCount === 0 && (
                  <div className="flex flex-col items-center gap-3 py-12 text-center bg-slate-900/50 rounded-2xl border border-slate-800">
                    <div className="p-3 rounded-full bg-green-500/10 border border-green-500/20">
                      <Shield size={24} className="text-green-400" />
                    </div>
                    <p className="text-green-400 font-bold">{t('vulns_none')}</p>
                    <p className="text-slate-500 text-sm max-w-sm">{t('vulns_none_sub')}</p>
                  </div>
                )}

                {/* Plan d'action prioritaire */}
                {(() => {
                  type WithEffort = Finding & { effort: 'quick' | 'medium' | 'complex' };
                  const getEffort = (f: Finding): 'quick' | 'medium' | 'complex' => {
                    if (f.severity === 'CRITICAL') return 'complex';
                    const cat = (f.category ?? '').toLowerCase();
                    if (cat.includes('port') || cat.includes('cve') || cat.includes('vuln')) return 'complex';
                    if (cat.includes('ssl') || cat.includes('tls') || cat.includes('cert')) return 'medium';
                    if ((f.penalty ?? 0) >= 20) return 'medium';
                    return 'quick';
                  };
                  const allActionable = r.findings
                    .filter(f => f.severity !== 'INFO' && (f.penalty ?? 0) > 0);
                  const premiumLockedCount = isPremiumPlan ? 0 : allActionable.filter(f => f.is_premium).length;
                  const actionFindings: WithEffort[] = allActionable
                    .filter(f => isPremiumPlan || !f.is_premium)
                    .map(f => ({ ...f, effort: getEffort(f) }));
                  if (actionFindings.length === 0 && premiumLockedCount === 0) return null;

                  const quickWins = actionFindings
                    .filter(f => f.effort === 'quick' && (f.penalty ?? 0) >= 8)
                    .sort((a, b) => (b.penalty ?? 0) - (a.penalty ?? 0))
                    .slice(0, 3);

                  const effortCfg = {
                    quick:   { label: lang === 'fr' ? '⚡ Rapide  < 2h'  : '⚡ Quick  < 2h',   cls: 'bg-green-500/10 text-green-400 border border-green-500/25' },
                    medium:  { label: lang === 'fr' ? '🔧 Moyen  2–8h'   : '🔧 Medium  2–8h', cls: 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/25' },
                    complex: { label: lang === 'fr' ? '🏗️ Complexe > 1j' : '🏗️ Complex > 1d', cls: 'bg-red-500/10 text-red-400 border border-red-500/25' },
                  };

                  const prioGroups = [
                    { key: 'p1', label: lang === 'fr' ? '🔴 Maintenant (Critique)'   : '🔴 Now (Critical)',      dot: 'bg-red-500',    text: 'text-red-400',    border: 'border-red-500/20',    items: actionFindings.filter(f => f.severity === 'CRITICAL') },
                    { key: 'p2', label: lang === 'fr' ? '🟠 Cette semaine (Élevé)'   : '🟠 This week (High)',    dot: 'bg-orange-500', text: 'text-orange-400', border: 'border-orange-500/20', items: actionFindings.filter(f => f.severity === 'HIGH') },
                    { key: 'p3', label: lang === 'fr' ? '🟡 Ce mois (Modéré / Faible)' : '🟡 This month (Med/Low)', dot: 'bg-yellow-500', text: 'text-yellow-400', border: 'border-yellow-500/20', items: actionFindings.filter(f => f.severity === 'MEDIUM' || f.severity === 'LOW') },
                  ].filter(g => g.items.length > 0);

                  return (
                    <div className="rounded-2xl border border-slate-800 bg-slate-900/40 overflow-hidden">
                      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800 bg-slate-900/60">
                        <div className="flex items-center gap-2.5">
                          <div className="p-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
                            <ListChecks size={14} className="text-cyan-400" />
                          </div>
                          <h3 className="text-white font-bold text-sm">
                            {lang === 'fr' ? "Plan d'action prioritaire" : 'Priority action plan'}
                          </h3>
                        </div>
                        <span className="text-xs font-mono text-slate-500">
                          {actionFindings.length} {lang === 'fr' ? 'actions' : 'actions'}
                        </span>
                      </div>
                      <div className="p-5 flex flex-col gap-5">
                        {quickWins.length > 0 && (
                          <div className="bg-green-500/5 border border-green-500/20 rounded-xl p-4">
                            <p className="text-xs font-bold text-green-400 mb-3 flex items-center gap-1.5">
                              <Zap size={12} />
                              {lang === 'fr' ? 'Quick wins — Corrections rapides à fort impact' : 'Quick wins — Fast fixes with high impact'}
                            </p>
                            <div className="flex flex-col gap-3">
                              {quickWins.map((f, i) => (
                                <div key={i} className="flex items-start gap-2.5">
                                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded shrink-0 mt-0.5 ${SEVERITY_CONFIG[f.severity].badge}`}>{f.severity}</span>
                                  <div className="flex-1 min-w-0">
                                    <p className="text-slate-200 text-xs font-medium">{f.title ?? f.message}</p>
                                    <p className="text-slate-400 text-xs mt-0.5 leading-relaxed">{f.recommendation}</p>
                                  </div>
                                  <span className={`text-[10px] px-2 py-0.5 rounded-full whitespace-nowrap shrink-0 ${effortCfg[f.effort].cls}`}>{effortCfg[f.effort].label}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                          {prioGroups.map(group => (
                            <div key={group.key}>
                              <div className="flex items-center gap-2 mb-3">
                                <span className={`w-2 h-2 rounded-full shrink-0 ${group.dot}`} />
                                <p className={`text-xs font-semibold ${group.text}`}>{group.label}</p>
                                <span className="text-xs text-slate-600 font-mono ml-auto">{group.items.length}</span>
                              </div>
                              <div className="flex flex-col gap-2">
                                {group.items.map((f, i) => (
                                  <div key={i} className={`rounded-xl border ${group.border} bg-slate-800/40 p-3`}>
                                    <div className="flex items-start justify-between gap-2 mb-1.5">
                                      <p className="text-slate-200 text-xs font-medium leading-snug">{f.title ?? f.message}</p>
                                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full whitespace-nowrap shrink-0 ${effortCfg[f.effort].cls}`}>{effortCfg[f.effort].label}</span>
                                    </div>
                                    <p className="text-slate-500 text-xs leading-relaxed">{f.recommendation}</p>
                                  </div>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                        {/* Actions premium verrouillées */}
                        {premiumLockedCount > 0 && (
                          <div className="mt-4 rounded-xl border border-violet-500/20 bg-violet-500/5 p-4 flex items-center gap-3">
                            <SkuIcon color="#a78bfa" size={32}>
                              <Lock size={16} className="text-violet-300" />
                            </SkuIcon>
                            <div className="flex-1">
                              <p className="text-white text-xs font-semibold">
                                {lang === 'fr'
                                  ? `+ ${premiumLockedCount} action${premiumLockedCount > 1 ? 's' : ''} avancée${premiumLockedCount > 1 ? 's' : ''} (analyse approfondie)`
                                  : `+ ${premiumLockedCount} advanced action${premiumLockedCount > 1 ? 's' : ''} (deep analysis)`}
                              </p>
                              <p className="text-slate-400 text-[11px] mt-0.5">
                                {lang === 'fr'
                                  ? 'Sous-domaines, fuites de données, versions vulnérables...'
                                  : 'Subdomains, data breaches, vulnerable versions...'}
                              </p>
                            </div>
                            <button
                              onClick={() => {
                                if (!user) { goRegister('premium_actions_gate'); }
                                else { window.location.href = '/espace-client?tab=billing'; }
                              }}
                              className="sku-btn-primary text-xs px-3 py-1.5 rounded-lg shrink-0"
                            >
                              {lang === 'fr' ? 'Débloquer' : 'Unlock'}
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })()}

                {/* Recommandations */}
                {r.recommendations && r.recommendations.length > 0 && (
                  <div className="rounded-2xl border border-slate-800 bg-slate-900/40 overflow-hidden">
                    <div className="flex items-center gap-2.5 px-5 py-4 border-b border-slate-800 bg-slate-900/60">
                      <div className="p-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20">
                        <Star size={14} className="text-amber-400" />
                      </div>
                      <h3 className="text-white font-bold text-sm">
                        {lang === 'fr' ? 'Recommandations' : 'Recommendations'}
                      </h3>
                      <span className="text-xs font-mono text-slate-500 ml-auto">{r.recommendations.length}</span>
                    </div>
                    <div className="p-5 flex flex-col gap-2">
                      <p className="text-slate-500 text-xs mb-1">
                        {lang === 'fr'
                          ? "Actions correctives classées par ordre de priorité, issues de l'analyse complète du domaine."
                          : 'Corrective actions ranked by priority, derived from the full domain analysis.'}
                      </p>
                      {r.recommendations.map((rec, i) => {
                        const recLower = rec.toLowerCase();
                        const matchedLink = blogLinks.find(l =>
                          l.match_keyword.split(',').some(kw =>
                            recLower.includes(kw.trim().toLowerCase())
                          )
                        );
                        return (
                          <div key={i} className="flex items-start gap-4 px-4 py-3.5 rounded-xl bg-slate-900/50 border border-slate-800 hover:border-slate-700 transition-colors">
                            <span className="shrink-0 mt-0.5 w-6 h-6 rounded-full bg-amber-500/15 border border-amber-500/30 text-amber-400 text-[10px] font-bold flex items-center justify-center">
                              {i + 1}
                            </span>
                            <div className="flex-1 min-w-0">
                              <p className="text-slate-200 text-sm leading-relaxed">{rec}</p>
                              {matchedLink && (
                                <a
                                  href={matchedLink.article_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1.5 mt-2 text-[11px] text-cyan-400 hover:text-cyan-300 transition-colors font-medium"
                                >
                                  <BookOpen size={11} />
                                  {lang === 'fr' ? "Lire l'article : " : 'Read article: '}{matchedLink.article_title}
                                </a>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* CTA contextuel */}
                {nonInfoCount >= 2 && (
                  <div className="bg-gradient-to-r from-cyan-950/50 to-slate-900 border border-cyan-500/25 rounded-2xl p-4">
                    <div className="flex items-start gap-3">
                      <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/20 shrink-0 mt-0.5">
                        <MessageSquare size={15} className="text-cyan-400" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-white font-bold text-sm mb-1">
                          {nonInfoCount}{' '}
                          {lang === 'fr'
                            ? `vulnérabilité${nonInfoCount > 1 ? 's' : ''} identifiée${nonInfoCount > 1 ? 's' : ''} sur ${r.domain}`
                            : `vulnerabilit${nonInfoCount > 1 ? 'ies' : 'y'} found on ${r.domain}`}
                        </p>
                        <p className="text-slate-400 text-xs leading-relaxed mb-3">
                          {lang === 'fr'
                            ? 'Notre équipe peut vous aider à corriger ces vulnérabilités. Contactez-nous pour obtenir un accompagnement personnalisé.'
                            : 'Our team can help you fix these vulnerabilities. Contact us for personalised support.'}
                        </p>
                        <button onClick={() => navigate('/contact')} className="flex items-center gap-1.5 text-xs font-bold text-cyan-400 hover:text-cyan-300 transition-colors">
                          {lang === 'fr' ? 'Contactez-nous →' : 'Contact us →'}
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </motion.div>
            )}

            {/* ── Onglet Vulnérabilités (liste filtrée par sévérité) ─── */}
            {activeTab === 'vulnerabilities' && (
              <motion.div
                key="tab-vulnerabilities"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.18 }}
                className="flex flex-col gap-5"
              >
                {r.findings.length === 0 ? (
                  <div className="flex flex-col items-center gap-3 py-12 text-center bg-slate-900/50 rounded-2xl border border-slate-800">
                    <div className="p-3 rounded-full bg-green-500/10 border border-green-500/20">
                      <Shield size={24} className="text-green-400" />
                    </div>
                    <p className="text-green-400 font-bold">{t('vulns_none')}</p>
                    <p className="text-slate-500 text-sm max-w-sm">{t('vulns_none_sub')}</p>
                  </div>
                ) : (
                  <>
                    {/* Pills de filtres */}
                    {(() => {
                      const countBySev = (sev: string) => r.findings.filter(f => f.severity === sev).length;
                      return (
                        <div className="flex items-center gap-2 flex-wrap">
                          {([
                            { key: 'all',      label: lang === 'fr' ? `Tous (${nonInfoCount})` : `All (${nonInfoCount})`,           active: 'bg-slate-700 text-white border-slate-600',               inactive: 'text-slate-400 border-slate-700 hover:border-slate-600' },
                            { key: 'CRITICAL', label: lang === 'fr' ? `Critique (${countBySev('CRITICAL')})` : `Critical (${countBySev('CRITICAL')})`, active: 'bg-red-500/20 text-red-300 border-red-500/40',           inactive: 'text-red-400/60 border-red-500/20 hover:border-red-500/40' },
                            { key: 'HIGH',     label: lang === 'fr' ? `Élevé (${countBySev('HIGH')})` : `High (${countBySev('HIGH')})`,             active: 'bg-orange-500/20 text-orange-300 border-orange-500/40', inactive: 'text-orange-400/60 border-orange-500/20 hover:border-orange-500/40' },
                            { key: 'MEDIUM',   label: lang === 'fr' ? `Moyen (${countBySev('MEDIUM')})` : `Medium (${countBySev('MEDIUM')})`,         active: 'bg-amber-500/20 text-amber-300 border-amber-500/40',   inactive: 'text-amber-400/60 border-amber-500/20 hover:border-amber-500/40' },
                            { key: 'LOW',      label: lang === 'fr' ? `Faible (${countBySev('LOW')})` : `Low (${countBySev('LOW')})`,               active: 'bg-slate-600/40 text-slate-300 border-slate-500/40',   inactive: 'text-slate-500/70 border-slate-700 hover:border-slate-600' },
                          ] as Array<{key: string; label: string; active: string; inactive: string}>).map(pill => (
                            <button
                              key={pill.key}
                              onClick={() => setSeverityFilter(pill.key as typeof severityFilter)}
                              className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition-all ${severityFilter === pill.key ? pill.active : `bg-transparent ${pill.inactive}`}`}
                            >
                              {pill.label}
                            </button>
                          ))}
                        </div>
                      );
                    })()}

                    {/* Liste de findings filtrée */}
                    {(() => {
                      const sevOrder: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
                      const sorted = r.findings
                        .filter(f => f.severity !== 'INFO')
                        .sort((a, b) => (sevOrder[a.severity] ?? 4) - (sevOrder[b.severity] ?? 4));
                      const toShow = severityFilter === 'all' ? sorted : sorted.filter(f => f.severity === severityFilter);
                      // Séparer : normaux, gated LOW (anonymes), et premium verrouillés
                      const normalItems   = toShow.filter(f => !f.is_premium && (isPremiumPlan || isAnon ? true : f.severity !== 'LOW'));
                      const visibleItems  = isAnon ? normalItems.filter(f => f.severity !== 'LOW') : normalItems;
                      const gatedItems    = isAnon ? toShow.filter(f => f.severity === 'LOW' && !f.is_premium)  : [];
                      const premiumLocked = !isPremiumPlan ? toShow.filter(f => f.is_premium) : [];

                      const borderCls = (sev: string) =>
                        sev === 'CRITICAL' ? 'bg-red-500/5 border-red-500/20 hover:border-red-500/35' :
                        sev === 'HIGH'     ? 'bg-orange-500/5 border-orange-500/20 hover:border-orange-500/35' :
                        sev === 'MEDIUM'   ? 'bg-amber-500/5 border-amber-500/20 hover:border-amber-500/35' :
                                            'bg-slate-900/50 border-slate-800 hover:border-slate-700';
                      return (
                        <>
                          {visibleItems.length === 0 && gatedItems.length === 0 && premiumLocked.length === 0 && (
                            <div className="flex flex-col items-center gap-2 py-8 text-center bg-slate-900/50 rounded-xl border border-slate-800">
                              <CheckCircle size={20} className="text-green-400" />
                              <p className="text-green-400 font-semibold text-sm">
                                {lang === 'fr' ? 'Aucun problème dans cette catégorie' : 'No issues in this category'}
                              </p>
                            </div>
                          )}
                          <div className="flex flex-col gap-3">
                            {visibleItems.map((f, i) => (
                              <div key={(f.title ?? f.message ?? '') + i}
                                className={`rounded-xl border p-4 transition-colors ${borderCls(f.severity)}`}
                              >
                                <div className="flex items-start gap-3">
                                  <span className={`shrink-0 mt-0.5 text-[10px] font-bold px-1.5 py-0.5 rounded ${SEVERITY_CONFIG[f.severity]?.badge ?? 'bg-slate-700 text-slate-300'}`}>
                                    {f.severity}
                                  </span>
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-start justify-between gap-2 mb-1">
                                      <p className="text-slate-100 text-sm font-semibold leading-snug">{f.title ?? f.message}</p>
                                      {f.category && (
                                        <span className="shrink-0 text-[10px] text-slate-500 bg-slate-800 border border-slate-700 px-2 py-0.5 rounded font-mono">
                                          {f.category}
                                        </span>
                                      )}
                                    </div>
                                    {f.plain_explanation && (
                                      <p className="text-slate-400 text-xs leading-relaxed mt-1">{f.plain_explanation}</p>
                                    )}
                                    {f.recommendation && (
                                      <p className="text-slate-500 text-xs leading-relaxed mt-1.5 pl-2 border-l border-slate-700">
                                        <span className="text-cyan-500/70 font-medium">→ </span>{f.recommendation}
                                      </p>
                                    )}
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>

                          {/* Gate premium findings verrouillés */}
                          {premiumLocked.length > 0 && (
                            <motion.div
                              initial={{ opacity: 0, y: 6 }}
                              animate={{ opacity: 1, y: 0 }}
                              transition={{ delay: 0.15 }}
                              className="rounded-xl border border-violet-500/20 py-8 px-6 flex flex-col items-center gap-4 text-center"
                              style={{
                                background: 'linear-gradient(180deg, rgba(139,92,246,0.06) 0%, rgba(15,23,42,0.6) 100%)',
                                boxShadow: '0 4px 20px rgba(0,0,0,0.3), inset 0 1px 0 rgba(139,92,246,0.1)',
                              }}
                            >
                              <SkuIcon color="#a78bfa" size={44}>
                                <Lock size={22} className="text-violet-300" />
                              </SkuIcon>
                              <div>
                                <p className="text-white font-bold text-sm">
                                  {lang === 'fr'
                                    ? `${premiumLocked.length} vulnérabilité${premiumLocked.length > 1 ? 's' : ''} avancée${premiumLocked.length > 1 ? 's' : ''} détectée${premiumLocked.length > 1 ? 's' : ''}`
                                    : `${premiumLocked.length} advanced vulnerabilit${premiumLocked.length > 1 ? 'ies' : 'y'} detected`}
                                </p>
                                <p className="text-slate-400 text-xs mt-1.5 max-w-sm leading-relaxed">
                                  {lang === 'fr'
                                    ? 'Sous-domaines, fuites de données, versions vulnérables, typosquatting… Passez à Starter pour débloquer les détails.'
                                    : 'Subdomains, data breaches, vulnerable versions, typosquatting… Upgrade to Starter to unlock details.'}
                                </p>
                              </div>
                              <button
                                onClick={() => {
                                  if (!user) { goRegister('premium_findings_gate'); }
                                  else { window.location.href = '/espace-client?tab=billing'; }
                                }}
                                className="sku-btn-primary text-sm px-5 py-2.5 rounded-xl flex items-center gap-2"
                              >
                                <Lock size={14} />
                                {!user
                                  ? (lang === 'fr' ? 'Créer un compte' : 'Create account')
                                  : (lang === 'fr' ? 'Voir les plans' : 'View plans')}
                              </button>
                            </motion.div>
                          )}

                          {/* Gate LOW findings pour anonymes */}
                          {gatedItems.length > 0 && (
                            <motion.div
                              initial={{ opacity: 0, y: 6 }}
                              animate={{ opacity: 1, y: 0 }}
                              transition={{ delay: 0.2 }}
                              className="rounded-xl border border-slate-700/50 py-8 px-6 flex flex-col items-center gap-4 text-center"
                              style={{
                                background: 'linear-gradient(180deg, rgba(251,191,36,0.04) 0%, rgba(15,23,42,0.6) 100%)',
                                boxShadow: '0 4px 20px rgba(0,0,0,0.3), inset 0 1px 0 rgba(251,191,36,0.08)',
                              }}
                            >
                              <SkuIcon color="#fbbf24" size={40}>
                                <Lock size={20} className="text-amber-300" />
                              </SkuIcon>
                              <div>
                                <p className="text-white font-bold text-sm">
                                  {lang === 'fr'
                                    ? `${gatedItems.length} recommandation${gatedItems.length > 1 ? 's' : ''} LOW masquée${gatedItems.length > 1 ? 's' : ''}`
                                    : `${gatedItems.length} LOW recommendation${gatedItems.length > 1 ? 's' : ''} hidden`}
                                </p>
                                <p className="text-slate-400 text-xs mt-1.5 leading-relaxed">
                                  {lang === 'fr'
                                    ? 'Créez un compte gratuit pour accéder au plan de correction complet.'
                                    : 'Create a free account to access the full remediation plan.'}
                                </p>
                              </div>
                              <button
                                onClick={() => goRegister('low_findings_gate')}
                                className="sku-btn-primary text-sm px-4 py-2 rounded-xl flex items-center gap-2"
                              >
                                <UserPlus size={14} />
                                {lang === 'fr' ? 'Créer un compte gratuit' : 'Create free account'}
                              </button>
                            </motion.div>
                          )}
                        </>
                      );
                    })()}

                    {/* Infos — collapsible */}
                    {infoFindings.length > 0 && (
                      <details className="group">
                        <summary className="flex items-center gap-2 text-xs font-mono text-slate-600 cursor-pointer hover:text-slate-400 transition-colors list-none">
                          <Info size={12} />
                          {infoFindings.length} {t('findings_info')}
                          <span className="text-slate-700 group-open:rotate-90 transition-transform">▶</span>
                        </summary>
                        <div className="mt-3 flex flex-col gap-3">
                          {infoFindings.map((f, i) => (
                            <FindingCard key={(f.title ?? f.message ?? '') + i} finding={f} index={i} />
                          ))}
                        </div>
                      </details>
                    )}
                  </>
                )}
              </motion.div>
            )}

            {/* ── Onglet Surveillance (Sous-domaines + Typo + CT + Fuites) */}
            {activeTab === 'surveillance' && (
              <motion.div
                key="tab-surveillance"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.18 }}
                className="flex flex-col gap-6"
              >
                {/* Analyses avancées — Sous-domaines + CVE */}
                {isPremiumPlan ? (
                  <div className="flex flex-col gap-4">
                    <div className="flex items-center gap-2">
                      <div className="p-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
                        <Shield size={14} className="text-cyan-400" />
                      </div>
                      <h3 className="text-white font-bold text-sm">
                        {lang === 'fr' ? 'Sous-domaines & Versions vulnérables' : 'Subdomains & Vulnerable versions'}
                      </h3>
                      <span className="text-xs bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 px-1.5 py-0.5 rounded-full">Starter, Pro & Dev</span>
                    </div>
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                      {groups.subdomains.length > 0 && <FindingGroup title="🌐 Sous-domaines & Certificats" findings={groups.subdomains} startIdx={0} />}
                      {groups.vulns.length > 0 && <FindingGroup title="🔬 Versions Vulnérables" findings={groups.vulns} startIdx={groups.subdomains.length} />}
                      {groups.subdomains.length === 0 && groups.vulns.length === 0 && (
                        <div className="lg:col-span-2 flex items-center gap-3 py-5 px-4 bg-slate-900/50 rounded-xl border border-slate-800">
                          <div className="p-2 rounded-full bg-green-500/10 border border-green-500/20">
                            <Shield size={16} className="text-green-400" />
                          </div>
                          <div>
                            <p className="text-green-400 font-bold text-sm">
                              {lang === 'fr' ? 'Aucune vulnérabilité avancée détectée' : 'No advanced vulnerability detected'}
                            </p>
                            <p className="text-slate-500 text-xs">
                              {lang === 'fr'
                                ? 'Sous-domaines et versions logicielles vérifiés — aucun problème critique trouvé.'
                                : 'Subdomains and software versions checked — no critical issue found.'}
                            </p>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="rounded-lg border border-dashed border-slate-600/60 bg-slate-800/30 p-5 flex flex-col gap-3">
                    <div className="flex items-center gap-2 text-slate-400 text-sm font-semibold">
                      <Lock size={14} className="text-cyan-500" />
                      <span className="text-slate-300">
                        {lang === 'fr' ? 'Analyses avancées — Starter, Pro & Dev' : 'Advanced analysis — Starter, Pro & Dev'}
                      </span>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div className="rounded-md bg-slate-700/40 border border-slate-600/40 p-3 flex flex-col gap-1">
                        <span className="text-xs font-mono text-cyan-400">🌐 Fuites de sous-domaines</span>
                        <span className="text-xs text-slate-500">
                          {lang === 'fr'
                            ? 'Certificats expirés, sous-domaines orphelins et risques de takeover via Certificate Transparency.'
                            : 'Expired certs, orphan subdomains, and takeover risks via Certificate Transparency.'}
                        </span>
                      </div>
                      <div className="rounded-md bg-slate-700/40 border border-slate-600/40 p-3 flex flex-col gap-1">
                        <span className="text-xs font-mono text-cyan-400">🔬 Versions vulnérables</span>
                        <span className="text-xs text-slate-500">
                          {lang === 'fr'
                            ? 'Détection de PHP, Apache, nginx, IIS exposés avec des failles connues (CVE critiques).'
                            : 'Detection of exposed PHP, Apache, nginx, IIS with known vulnerabilities (critical CVEs).'}
                        </span>
                      </div>
                    </div>
                    <button onClick={() => openPricing('upgrade_banner')} className="self-start mt-1 text-xs font-semibold px-3 py-1.5 rounded-md bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 hover:bg-cyan-500/30 transition-colors flex items-center gap-1.5">
                      <Lock size={11} />
                      {lang === 'fr' ? 'Débloquer avec Starter — 9,90€/mois' : 'Unlock with Starter — €9.90/month'}
                      <ArrowRight size={11} />
                    </button>
                  </div>
                )}

                {/* Typosquatting */}
                {isPremiumPlan ? (() => {
                  const ts = r.typosquat_details;
                  return (
                    <div className="flex flex-col gap-4">
                      <div className="flex items-center gap-2">
                        <div className="p-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20">
                          <Globe size={14} className="text-amber-400" />
                        </div>
                        <h3 className="text-white font-bold text-sm">
                          {lang === 'fr' ? 'Domaines sosies (typosquatting)' : 'Lookalike domains (typosquatting)'}
                        </h3>
                        <span className="text-xs bg-amber-500/20 text-amber-300 border border-amber-500/30 px-1.5 py-0.5 rounded-full">Starter, Pro & Dev</span>
                      </div>

                      {!ts ? (
                        <div className="flex items-center gap-3 py-4 px-4 bg-slate-900/50 rounded-xl border border-slate-800">
                          <div className="p-2 rounded-full bg-blue-500/10 border border-blue-500/20">
                            <Globe size={16} className="text-blue-400" />
                          </div>
                          <p className="text-slate-400 text-xs">
                            {lang === 'fr' ? 'Données non disponibles — relancez une analyse.' : 'Data unavailable — re-run the scan.'}
                          </p>
                        </div>
                      ) : ts.status === 'clean' ? (
                        <div className="flex items-center gap-3 py-4 px-4 bg-green-500/5 rounded-xl border border-green-500/20">
                          <div className="p-2 rounded-full bg-green-500/10 border border-green-500/20">
                            <Shield size={16} className="text-green-400" />
                          </div>
                          <div>
                            <p className="text-green-400 font-bold text-sm">
                              {lang === 'fr' ? 'Aucun domaine sosie détecté' : 'No lookalike domains detected'}
                            </p>
                            <p className="text-slate-500 text-xs">
                              {lang === 'fr'
                                ? `${ts.checked} variantes vérifiées par résolution DNS — votre domaine ne semble pas ciblé.`
                                : `${ts.checked} variants checked via DNS — your domain does not appear to be targeted.`}
                            </p>
                          </div>
                        </div>
                      ) : (
                        <div className="flex flex-col gap-3">
                          <div className="flex items-center gap-3 py-3 px-4 bg-orange-500/5 rounded-xl border border-orange-500/20">
                            <div className="p-2 rounded-full bg-orange-500/10 border border-orange-500/20">
                              <Globe size={16} className="text-orange-400" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className="text-orange-400 font-bold text-sm">
                                {lang === 'fr'
                                  ? `${ts.hit_count} domaine${ts.hit_count > 1 ? 's sosies' : ' sosie'} enregistré${ts.hit_count > 1 ? 's' : ''}`
                                  : `${ts.hit_count} lookalike domain${ts.hit_count > 1 ? 's' : ''} registered`}
                              </p>
                              <p className="text-slate-500 text-xs">
                                {lang === 'fr'
                                  ? `Sur ${ts.checked} variantes vérifiées — ces domaines peuvent être utilisés pour du phishing.`
                                  : `Out of ${ts.checked} variants checked — these domains may be used for phishing.`}
                              </p>
                            </div>
                          </div>

                          <div className="flex flex-col gap-2">
                            {ts.hits.map((hit, i) => (
                              <div key={i} className="flex items-center gap-3 px-4 py-2.5 bg-slate-900/60 rounded-lg border border-slate-800">
                                <div className="flex-1 min-w-0">
                                  <span className="font-mono text-sm text-orange-300">{hit.domain}</span>
                                  <span className="ml-2 text-xs text-slate-600">→ {hit.ip}</span>
                                </div>
                                <span className="shrink-0 text-xs px-2 py-0.5 rounded-full border font-mono bg-slate-800 border-slate-700 text-slate-400">
                                  {hit.variant_type}
                                </span>
                              </div>
                            ))}
                          </div>

                          <div className="rounded-lg bg-amber-500/5 border border-amber-500/20 p-3 text-xs text-amber-300/80">
                            <span className="font-semibold">
                              {lang === 'fr' ? '💡 Recommandation : ' : '💡 Recommendation: '}
                            </span>
                            {lang === 'fr'
                              ? 'Enregistrez les TLDs principaux (.com, .fr, .org) et signalez les domaines abusifs à votre registrar. Activez DMARC p=reject.'
                              : 'Register the main TLDs (.com, .fr, .org) and report abusive domains to your registrar. Enable DMARC p=reject.'}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })() : (
                  <div className="rounded-lg border border-dashed border-slate-600/60 bg-slate-800/30 p-5 flex flex-col gap-3">
                    <div className="flex items-center gap-2 text-slate-400 text-sm font-semibold">
                      <Globe size={14} className="text-amber-500" />
                      <span className="text-slate-300">
                        {lang === 'fr' ? 'Domaines sosies — Starter, Pro & Dev' : 'Lookalike domains — Starter, Pro & Dev'}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500">
                      {lang === 'fr'
                        ? 'Détecte les domaines typosquattés enregistrés par des tiers (variantes de TLD, fautes de frappe, homoglyphes) via résolution DNS.'
                        : 'Detects typosquatted domains registered by third parties (TLD variants, typos, homoglyphs) via DNS resolution.'}
                    </p>
                    <button onClick={() => openPricing('upgrade_banner')} className="self-start mt-1 text-xs font-semibold px-3 py-1.5 rounded-md bg-amber-500/20 text-amber-300 border border-amber-500/40 hover:bg-amber-500/30 transition-colors flex items-center gap-1.5">
                      <Lock size={11} />
                      {lang === 'fr' ? 'Débloquer avec Starter — 9,90€/mois' : 'Unlock with Starter — €9.90/month'}
                      <ArrowRight size={11} />
                    </button>
                  </div>
                )}

                {/* Certificate Transparency Monitor */}
                {isPremiumPlan ? (() => {
                  const ct = r.ct_details;
                  return (
                    <div className="flex flex-col gap-4">
                      <div className="flex items-center gap-2">
                        <div className="p-1.5 rounded-lg bg-violet-500/10 border border-violet-500/20">
                          <Award size={14} className="text-violet-400" />
                        </div>
                        <h3 className="text-white font-bold text-sm">
                          {lang === 'fr' ? 'Certificate Transparency (CT logs)' : 'Certificate Transparency (CT logs)'}
                        </h3>
                        <span className="text-xs bg-violet-500/20 text-violet-300 border border-violet-500/30 px-1.5 py-0.5 rounded-full">Starter, Pro & Dev</span>
                      </div>

                      {!ct || ct.status === 'no_data' ? (
                        <div className="flex items-center gap-3 py-4 px-4 bg-slate-900/50 rounded-xl border border-slate-800">
                          <div className="p-2 rounded-full bg-blue-500/10 border border-blue-500/20">
                            <Award size={16} className="text-blue-400" />
                          </div>
                          <p className="text-slate-400 text-xs">
                            {lang === 'fr' ? 'Données CT non disponibles pour ce scan.' : 'CT data not available for this scan.'}
                          </p>
                        </div>
                      ) : (
                        <div className="flex flex-col gap-3">
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                            {[
                              { label: lang === 'fr' ? 'Total certs' : 'Total certs', value: ct.total_found, color: 'text-cyan-300' },
                              { label: lang === 'fr' ? '7 derniers jours' : 'Last 7 days', value: ct.recent_7days, color: ct.recent_7days > 0 ? 'text-amber-300' : 'text-green-300' },
                              { label: lang === 'fr' ? '30 derniers jours' : 'Last 30 days', value: ct.recent_30days, color: 'text-slate-300' },
                              { label: lang === 'fr' ? 'Wildcards' : 'Wildcards', value: ct.wildcard_count, color: ct.wildcard_count > 0 ? 'text-orange-300' : 'text-green-300' },
                            ].map((s, i) => (
                              <div key={i} className="flex flex-col gap-0.5 px-3 py-2.5 bg-slate-900/60 rounded-lg border border-slate-800 text-center">
                                <span className={`text-xl font-bold font-mono ${s.color}`}>{s.value}</span>
                                <span className="text-xs text-slate-500">{s.label}</span>
                              </div>
                            ))}
                          </div>

                          {(ct.issuers?.length ?? 0) > 0 && (
                            <div className="flex flex-wrap gap-1.5 px-3 py-2.5 bg-slate-900/40 rounded-lg border border-slate-800">
                              <span className="text-xs text-slate-500 w-full mb-0.5">
                                {lang === 'fr' ? 'Autorités de certification détectées :' : 'Detected certificate authorities:'}
                              </span>
                              {(ct.issuers ?? []).slice(0, 8).map((issuer, i) => (
                                <span key={i} className="text-xs px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-400 font-mono">
                                  {issuer}
                                </span>
                              ))}
                            </div>
                          )}

                          {(ct.recent_certs?.length ?? 0) > 0 && (
                            <div className="flex flex-col gap-1">
                              <p className="text-xs text-slate-500 px-1">
                                {lang === 'fr' ? `Certificats émis dans les 7 derniers jours (${ct.recent_certs?.length ?? 0}) :` : `Certificates issued in the last 7 days (${ct.recent_certs?.length ?? 0}):`}
                              </p>
                              {(ct.recent_certs ?? []).slice(0, 5).map((cert, i) => (
                                <div key={i} className="flex items-center gap-3 px-3 py-2 bg-amber-500/5 rounded-lg border border-amber-500/15">
                                  <div className="flex-1 min-w-0">
                                    <span className="font-mono text-xs text-amber-300">{cert.common_name}</span>
                                  </div>
                                  <span className="shrink-0 text-xs text-slate-500">{cert.issuer}</span>
                                  <span className="shrink-0 text-xs text-slate-600">{cert.logged_at}</span>
                                </div>
                              ))}
                            </div>
                          )}

                          {ct.wildcard_count > 0 && (
                            <div className="rounded-lg bg-orange-500/5 border border-orange-500/20 p-3 text-xs text-orange-300/80">
                              <span className="font-semibold">⚠️ {ct.wildcard_count} certificat{ct.wildcard_count > 1 ? 's' : ''} wildcard</span>
                              {' '}
                              {lang === 'fr'
                                ? 'trouvé(s) dans les logs CT. Les wildcards (*.domain.com) couvrent tous les sous-domaines.'
                                : 'found in CT logs. Wildcards (*.domain.com) cover all subdomains.'}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })() : (
                  <div className="rounded-lg border border-dashed border-slate-600/60 bg-slate-800/30 p-5 flex flex-col gap-3">
                    <div className="flex items-center gap-2 text-slate-400 text-sm font-semibold">
                      <Award size={14} className="text-violet-500" />
                      <span className="text-slate-300">
                        {lang === 'fr' ? 'CT logs — Starter, Pro & Dev' : 'CT logs — Starter, Pro & Dev'}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500">
                      {lang === 'fr'
                        ? 'Surveille les logs Certificate Transparency (crt.sh) pour détecter tout certificat récent, wildcard ou suspect émis pour votre domaine.'
                        : 'Monitors Certificate Transparency logs (crt.sh) to detect recent, wildcard, or suspicious certificates issued for your domain.'}
                    </p>
                    <button onClick={() => openPricing('upgrade_banner')} className="self-start mt-1 text-xs font-semibold px-3 py-1.5 rounded-md bg-violet-500/20 text-violet-300 border border-violet-500/40 hover:bg-violet-500/30 transition-colors flex items-center gap-1.5">
                      <Lock size={11} />
                      {lang === 'fr' ? 'Débloquer avec Starter — 9,90€/mois' : 'Unlock with Starter — €9.90/month'}
                      <ArrowRight size={11} />
                    </button>
                  </div>
                )}

                {/* Fuites de données (HIBP) */}
                {!isPremiumPlan ? (
                  <div className="flex flex-col items-center gap-4 py-12 text-center bg-slate-900/50 rounded-2xl border border-slate-800">
                    <SkuIcon color="#f87171" size={52}>
                      <Database size={24} className="text-red-300" />
                    </SkuIcon>
                    <div>
                      <p className="text-slate-200 font-bold text-base">
                        {lang === 'fr' ? 'Détection de fuites de données' : 'Data Breach Detection'}
                      </p>
                      <p className="text-slate-500 text-sm mt-1 max-w-sm mx-auto">
                        {lang === 'fr'
                          ? 'Vérifiez si votre domaine a été compromis dans des bases de données piratées.'
                          : 'Check if your domain has been compromised in breached databases.'}
                      </p>
                    </div>
                    <div className="flex flex-col items-center gap-2">
                      <span className="text-xs font-semibold px-3 py-1 rounded-full bg-violet-500/20 text-violet-300 border border-violet-500/30">
                        {lang === 'fr' ? 'Disponible dès le plan Starter' : 'Available from Starter plan'}
                      </span>
                      {!user && (
                        <button
                          onClick={() => navigate('/register')}
                          className="sku-btn-primary mt-2 flex items-center gap-2 px-4 py-2 text-sm rounded-xl"
                        >
                          <UserPlus size={14} />
                          {lang === 'fr' ? 'Créer un compte gratuit' : 'Create a free account'}
                        </button>
                      )}
                    </div>
                  </div>
                ) : r.breach_details?.status === 'clean' ? (
                  <div className="flex flex-col items-center gap-4 py-12 text-center bg-slate-900/50 rounded-2xl border border-green-500/20">
                    <SkuIcon color="#4ade80" size={52}>
                      <CheckCircle size={24} className="text-green-300" />
                    </SkuIcon>
                    <div>
                      <p className="text-green-400 font-bold text-base">
                        {lang === 'fr' ? 'Aucune fuite détectée' : 'No breach detected'}
                      </p>
                      <p className="text-slate-500 text-sm mt-1 max-w-sm mx-auto">
                        {lang === 'fr'
                          ? `Le domaine ${r.domain} n'apparaît dans aucune base de données piratée connue.`
                          : `The domain ${r.domain} does not appear in any known breached database.`}
                      </p>
                    </div>
                    <p className="text-slate-600 text-xs">
                      {lang === 'fr' ? 'Source : HaveIBeenPwned' : 'Source: HaveIBeenPwned'}
                    </p>
                  </div>
                ) : r.breach_details?.status === 'breached' ? (
                  <div className="flex flex-col gap-4">
                    <div className="flex items-start gap-4 p-5 rounded-2xl bg-red-500/10 border border-red-500/30">
                      <SkuIcon color="#f87171" size={44}>
                        <Database size={22} className="text-red-300" />
                      </SkuIcon>
                      <div className="flex-1 min-w-0">
                        <p className="text-red-300 font-bold text-base">
                          {lang === 'fr'
                            ? `Domaine trouvé dans ${breachCount} fuite${breachCount > 1 ? 's' : ''} de données`
                            : `Domain found in ${breachCount} data breach${breachCount > 1 ? 'es' : ''}`}
                        </p>
                        <p className="text-slate-400 text-sm mt-1">
                          {lang === 'fr'
                            ? 'Des identifiants liés à votre domaine ont été retrouvés dans des bases de données piratées. Ces credentials peuvent être utilisés pour du credential stuffing ou du phishing ciblé.'
                            : 'Credentials linked to your domain were found in breached databases. These can be used for credential stuffing or targeted phishing attacks.'}
                        </p>
                      </div>
                    </div>
                    {(r.breach_details.breach_names?.length ?? 0) > 0 && (
                      <div className="flex flex-col gap-2 p-4 rounded-xl bg-slate-900/50 border border-slate-800">
                        <p className="text-slate-400 text-xs font-semibold uppercase tracking-wider mb-1">
                          {lang === 'fr' ? 'Sources identifiées' : 'Identified sources'}
                        </p>
                        <div className="flex flex-wrap gap-2">
                          {r.breach_details.breach_names!.map(name => (
                            <span key={name} className="px-2.5 py-1 rounded-full text-xs font-medium bg-red-500/15 text-red-300 border border-red-500/30">
                              {name}
                            </span>
                          ))}
                        </div>
                        <p className="text-slate-600 text-xs mt-1">
                          {lang === 'fr' ? 'Source : HaveIBeenPwned' : 'Source: HaveIBeenPwned'}
                        </p>
                      </div>
                    )}
                    <div className="flex flex-col gap-2 p-4 rounded-xl bg-slate-900/50 border border-slate-800">
                      <p className="text-slate-400 text-xs font-semibold uppercase tracking-wider mb-1">
                        {lang === 'fr' ? 'Actions recommandées' : 'Recommended actions'}
                      </p>
                      {[
                        { icon: <Lock size={14} className="text-amber-400" />, text: lang === 'fr' ? 'Demandez à vos équipes de changer immédiatement leurs mots de passe.' : 'Ask your team to immediately change their passwords.' },
                        { icon: <Shield size={14} className="text-cyan-400" />, text: lang === 'fr' ? "Activez l'authentification à deux facteurs (2FA) sur tous les comptes professionnels." : 'Enable two-factor authentication (2FA) on all business accounts.' },
                        { icon: <Eye size={14} className="text-violet-400" />, text: lang === 'fr' ? "Vérifiez les accès suspects dans vos logs et journaux d'activité." : 'Review suspicious access in your logs and activity journals.' },
                      ].map((action, i) => (
                        <div key={i} className="flex items-start gap-3 py-2">
                          <span className="mt-0.5 shrink-0">{action.icon}</span>
                          <p className="text-slate-300 text-sm">{action.text}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : r.breach_details?.status === 'no_api_key' ? (
                  <div className="flex flex-col items-center gap-4 py-12 text-center bg-slate-900/50 rounded-2xl border border-slate-800">
                    <SkuIcon color="#a78bfa" size={44}>
                      <Database size={20} className="text-violet-300" />
                    </SkuIcon>
                    <div>
                      <p className="text-slate-300 font-semibold text-sm">
                        {lang === 'fr' ? 'Bientôt disponible' : 'Coming soon'}
                      </p>
                      <p className="text-slate-500 text-xs mt-1.5 max-w-sm mx-auto leading-relaxed">
                        {lang === 'fr'
                          ? 'La détection de fuites de données via HaveIBeenPwned sera disponible prochainement.'
                          : 'Breach detection via HaveIBeenPwned will be available soon.'}
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-3 py-12 text-center bg-slate-900/50 rounded-2xl border border-slate-800">
                    <SkuIcon color="#22d3ee" size={44}>
                      <Database size={20} className="text-cyan-300" />
                    </SkuIcon>
                    <p className="text-slate-400 text-sm max-w-xs">
                      {lang === 'fr'
                        ? 'Données de fuites non disponibles pour ce scan. Relancez une analyse pour obtenir les résultats.'
                        : 'Breach data not available for this scan. Re-run the analysis to get results.'}
                    </p>
                  </div>
                )}
              </motion.div>
            )}

            {/* ── Onglet Conformité NIS2 / RGPD ────────────────────── */}
            {activeTab === 'conformite' && (() => {
              const c = r.compliance;
              if (!c || !c.nis2) {
                return (
                  <motion.div key="tab-conformite-empty"
                    initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.18 }}>
                    <div className="flex flex-col items-center gap-3 py-12 text-center bg-slate-900/50 rounded-2xl border border-slate-800">
                      <SkuIcon color="#22d3ee" size={44}><Scale size={20} className="text-cyan-300" /></SkuIcon>
                      <p className="text-slate-400 text-sm max-w-xs">
                        {lang === 'fr' ? 'Relancez une analyse pour obtenir le rapport de conformité.' : 'Re-run the analysis to get the compliance report.'}
                      </p>
                    </div>
                  </motion.div>
                );
              }

              const levelCfg = {
                bon:           { label: lang === 'fr' ? 'Bon'            : 'Good',          bg: 'bg-green-500/15',  border: 'border-green-500/30',  text: 'text-green-300' },
                insuffisant:   { label: lang === 'fr' ? 'Insuffisant'    : 'Insufficient',  bg: 'bg-amber-500/15',  border: 'border-amber-500/30',  text: 'text-amber-300' },
                critique:      { label: lang === 'fr' ? 'Critique'       : 'Critical',      bg: 'bg-red-500/15',    border: 'border-red-500/30',    text: 'text-red-300'   },
              }[c.overall_level] ?? { label: '—', bg: 'bg-slate-800', border: 'border-slate-700', text: 'text-slate-400' };

              const scoreBar = (score: number) => {
                const color = score >= 80 ? '#4ade80' : score >= 50 ? '#fbbf24' : '#f87171';
                return (
                  <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
                    <div className="h-full rounded-full transition-all duration-700"
                      style={{ width: `${score}%`, background: color }} />
                  </div>
                );
              };

              const ArticleRow = ({ art }: { art: ComplianceArticle }) => {
                const statusCfg = art.status === 'not_assessable'
                  ? { rowBg: 'bg-slate-900/20 border-slate-700/50', iconBg: 'bg-slate-600/20 text-slate-500', icon: '—', titleText: 'text-slate-400' }
                  : art.status === 'pass'
                    ? { rowBg: 'bg-slate-900/30 border-slate-800', iconBg: 'bg-green-500/20 text-green-400', icon: '✓', titleText: 'text-slate-300' }
                    : art.status === 'warn'
                      ? { rowBg: 'bg-amber-500/5 border-amber-500/20', iconBg: 'bg-amber-500/20 text-amber-400', icon: '!', titleText: 'text-slate-200' }
                      : { rowBg: 'bg-red-500/5 border-red-500/20', iconBg: 'bg-red-500/20 text-red-400', icon: '✗', titleText: 'text-slate-200' };
                return (
                  <div className={`flex items-start gap-3 px-4 py-3 rounded-xl border transition-colors ${statusCfg.rowBg}`}>
                    <div className={`mt-0.5 shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${statusCfg.iconBg}`}>
                      {statusCfg.icon}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-[10px] font-mono text-slate-500">Art. {art.code}</span>
                        <span className={`text-sm font-medium ${statusCfg.titleText}`}>
                          {lang === 'fr' ? art.title : art.title_en}
                        </span>
                        {art.status === 'not_assessable' && (
                          <span className="text-[9px] px-1.5 py-0.5 rounded bg-slate-700/50 text-slate-500 border border-slate-600/30">
                            {lang === 'fr' ? 'Non vérifiable' : 'Not assessable'}
                          </span>
                        )}
                      </div>
                      <p className="text-slate-500 text-xs mt-0.5 leading-relaxed">
                        {lang === 'fr' ? art.description : art.description_en}
                      </p>
                      {art.status !== 'pass' && art.status !== 'not_assessable' && art.triggered_by.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 mt-2">
                          {art.triggered_by.slice(0, 3).map((tb, i) => (
                            <span key={i} className={`px-2 py-0.5 rounded text-[10px] border ${
                              art.status === 'warn'
                                ? 'bg-amber-500/10 text-amber-300 border-amber-500/20'
                                : 'bg-red-500/10 text-red-300 border-red-500/20'
                            }`}>
                              {tb}
                            </span>
                          ))}
                          {art.triggered_by.length > 3 && (
                            <span className="text-[10px] text-slate-600">+{art.triggered_by.length - 3}</span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              };

              return (
                <motion.div key="tab-conformite"
                  initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.18 }}
                  className="flex flex-col gap-5">

                  {/* Badges scores + niveau global */}
                  <div className="flex flex-col sm:flex-row items-stretch gap-3">
                    <div className="flex-1 p-4 rounded-xl bg-slate-900/50 border border-slate-800">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <SkuIcon color="#818cf8" size={28}><FileText size={14} className="text-indigo-300" /></SkuIcon>
                          <span className="text-slate-300 text-sm font-semibold">NIS2</span>
                          <span className="text-slate-600 text-xs">Directive EU 2022/2555</span>
                        </div>
                        <span className={`text-lg font-bold ${c.nis2_score >= 80 ? 'text-green-400' : c.nis2_score >= 50 ? 'text-amber-400' : 'text-red-400'}`}>
                          {c.nis2_score}%
                        </span>
                      </div>
                      {scoreBar(c.nis2_score)}
                    </div>
                    <div className="flex-1 p-4 rounded-xl bg-slate-900/50 border border-slate-800">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <SkuIcon color="#a78bfa" size={28}><Scale size={14} className="text-violet-300" /></SkuIcon>
                          <span className="text-slate-300 text-sm font-semibold">RGPD</span>
                          <span className="text-slate-600 text-xs">Règlement EU 2016/679</span>
                        </div>
                        <span className={`text-lg font-bold ${c.rgpd_score >= 80 ? 'text-green-400' : c.rgpd_score >= 50 ? 'text-amber-400' : 'text-red-400'}`}>
                          {c.rgpd_score}%
                        </span>
                      </div>
                      {scoreBar(c.rgpd_score)}
                    </div>
                    <div className={`flex flex-col items-center justify-center px-5 py-4 rounded-xl border ${levelCfg.bg} ${levelCfg.border} min-w-[110px]`}>
                      <span className="text-slate-500 text-[10px] uppercase tracking-wider mb-1">
                        {lang === 'fr' ? 'Niveau' : 'Level'}
                      </span>
                      <span className={`text-sm font-bold ${levelCfg.text}`}>{levelCfg.label}</span>
                    </div>
                  </div>

                  <p className="text-slate-600 text-xs px-1">
                    {c.disclaimer_fr && c.disclaimer_en
                      ? (lang === 'fr' ? c.disclaimer_fr : c.disclaimer_en)
                      : (lang === 'fr'
                        ? 'Ce rapport est basé sur les checks techniques automatisés. Il ne constitue pas un audit de conformité légal. Consultez un DPO ou expert NIS2 pour une évaluation complète.'
                        : 'This report is based on automated technical checks. It does not constitute a legal compliance audit. Consult a DPO or NIS2 expert for a full assessment.')}
                  </p>

                  <div className="flex flex-col gap-2">
                    <p className="text-slate-400 text-xs font-semibold uppercase tracking-wider px-1">
                      NIS2 — Art. 21 §2 ({c.nis2.filter(a => a.status === 'pass').length}/{c.nis2.filter(a => a.status !== 'not_assessable').length} {lang === 'fr' ? 'conformes' : 'compliant'})
                    </p>
                    {c.nis2.map(art => <ArticleRow key={art.code} art={art} />)}
                  </div>

                  <div className="flex flex-col gap-2">
                    <p className="text-slate-400 text-xs font-semibold uppercase tracking-wider px-1">
                      RGPD ({c.rgpd.filter(a => a.status === 'pass').length}/{c.rgpd.filter(a => a.status !== 'not_assessable').length} {lang === 'fr' ? 'conformes' : 'compliant'})
                    </p>
                    {c.rgpd.map(art => <ArticleRow key={art.code} art={art} />)}
                  </div>

                  {/* PDF download */}
                  <div className="pt-2 border-t border-slate-800">
                    <button
                      onClick={() => user ? downloadPdf() : openEmailCaptureModal()}
                      disabled={!!user && pdfLoading}
                      className="w-full flex items-center justify-center gap-2 py-3 rounded-xl font-bold text-sm bg-gradient-to-r from-cyan-700/60 to-blue-700/60 hover:from-cyan-600/70 hover:to-blue-600/70 border border-cyan-500/40 text-cyan-200 disabled:opacity-50 transition-all"
                    >
                      <FileDown size={15} />
                      {pdfLoading
                        ? (lang === 'fr' ? 'Génération…' : 'Generating…')
                        : (lang === 'fr' ? 'Télécharger le rapport PDF complet' : 'Download full PDF report')}
                    </button>
                  </div>

                </motion.div>
              );
            })()}

          </AnimatePresence>
        </div>


      </motion.div>

      {/* ── Disclaimer — visible après les résultats ─────────────────────── */}
      <p className="text-slate-600 text-[11px] leading-relaxed mt-6 text-center max-w-2xl mx-auto">
        {lang === 'fr'
          ? 'Ce diagnostic est généré automatiquement par un scan passif. Il est fourni à titre informatif et ne constitue pas un audit de sécurité complet. Il ne saurait remplacer l\'intervention d\'un professionnel agréé en cybersécurité.'
          : 'This report is generated automatically via a passive scan. It is provided for informational purposes only and does not constitute a comprehensive security audit. It cannot replace the services of a certified cybersecurity professional.'}
      </p>
    </>
  );
}
