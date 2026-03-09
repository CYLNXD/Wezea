// ─── CompliancePage.tsx — Funnel NIS2 / RGPD ─────────────────────────────────
import { useState, useRef, FormEvent } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Shield, Lock, Mail, Globe, Server, CheckCircle2,
  XCircle, AlertTriangle, ChevronRight, ArrowLeft,
  FileCheck, Eye, EyeOff,
} from 'lucide-react';
import { scanDomain, extractApiError, extractRateLimitDetail } from '../lib/api';
import type { ScanResult } from '../types/scanner';

// ─── Types ────────────────────────────────────────────────────────────────────

interface Finding {
  category: string;
  severity: string;
  title: string;
  technical_detail?: string;
  plain_explanation?: string;
  penalty: number;
  recommendation?: string;
}

type ComplianceStatus = 'pass' | 'warn' | 'fail' | 'unknown';

interface Criterion {
  id: string;
  label: string;
  regulations: string[];
  article: string;
  desc: string;
  blurred: boolean;
  icon: React.ReactNode;
  check: (findings: Finding[]) => ComplianceStatus;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const SEV_RANK: Record<string, number> = { LOW: 1, MEDIUM: 2, HIGH: 3, CRITICAL: 4 };

function findingsMatch(
  findings: Finding[],
  opts: { categories?: string[]; titleWords?: string[]; minSev?: number },
): Finding[] {
  return findings.filter(f => {
    const catOk  = !opts.categories || opts.categories.includes(f.category);
    const sevOk  = (SEV_RANK[f.severity] ?? 0) >= (opts.minSev ?? 1);
    const wordOk = !opts.titleWords || opts.titleWords.some(w =>
      f.title.toLowerCase().includes(w) ||
      (f.technical_detail ?? '').toLowerCase().includes(w),
    );
    return catOk && sevOk && wordOk;
  });
}

// ─── Compliance criteria (5 visible + 7 blurred) ─────────────────────────────

const CRITERIA: Criterion[] = [
  // ── Visible ──
  {
    id: 'https',
    label: 'HTTPS & Chiffrement actif',
    regulations: ['NIS2', 'RGPD'],
    article: 'Art. 21 NIS2 · Art. 32 RGPD',
    desc: 'Tout le trafic doit être chiffré via HTTPS. Le certificat SSL doit être valide et la redirection HTTP → HTTPS active.',
    blurred: false,
    icon: <Lock size={16} />,
    check: (findings) => {
      const critical = findingsMatch(findings, { categories: ['ssl'], minSev: 4 });
      const high = findingsMatch(findings, { categories: ['ssl'], minSev: 3 });
      const redirect = findingsMatch(findings, { titleWords: ['http', 'redirect', 'https'], minSev: 3 });
      if (critical.length > 0 || redirect.length > 0) return 'fail';
      if (high.length > 0) return 'warn';
      return 'pass';
    },
  },
  {
    id: 'tls',
    label: 'Protocole TLS à jour',
    regulations: ['NIS2'],
    article: 'Art. 21 NIS2',
    desc: 'TLS 1.2 minimum requis. TLS 1.0 et 1.1 sont officiellement dépréciés depuis 2021 et ne doivent plus être utilisés.',
    blurred: false,
    icon: <Shield size={16} />,
    check: (findings) => {
      const deprecated = findingsMatch(findings, {
        titleWords: ['tls 1.0', 'tls 1.1', 'tlsv1.0', 'tlsv1.1', 'deprecated', 'cipher faible', 'weak cipher'],
        minSev: 2,
      });
      const pfs = findingsMatch(findings, { titleWords: ['perfect forward', 'pfs'], minSev: 2 });
      if (deprecated.length > 0) return 'fail';
      if (pfs.length > 0) return 'warn';
      return 'pass';
    },
  },
  {
    id: 'dmarc',
    label: 'Protection anti-usurpation (DMARC)',
    regulations: ['NIS2'],
    article: 'Art. 21 NIS2',
    desc: 'DMARC avec p=quarantine ou p=reject protège votre domaine contre le phishing par usurpation d\'identité.',
    blurred: false,
    icon: <Mail size={16} />,
    check: (findings) => {
      const missing = findingsMatch(findings, { titleWords: ['dmarc'], minSev: 3 });
      const permissive = findingsMatch(findings, { titleWords: ['dmarc', 'p=none'], minSev: 2 });
      if (missing.some(f => f.severity === 'CRITICAL' || f.severity === 'HIGH')) return 'fail';
      if (permissive.length > 0) return 'warn';
      return 'pass';
    },
  },
  {
    id: 'headers',
    label: 'En-têtes de sécurité HTTP',
    regulations: ['RGPD'],
    article: 'Art. 25 RGPD',
    desc: 'HSTS, CSP et X-Frame-Options réduisent la surface d\'attaque XSS/clickjacking et protègent vos visiteurs.',
    blurred: false,
    icon: <FileCheck size={16} />,
    check: (findings) => {
      const critical = findingsMatch(findings, { categories: ['headers'], minSev: 3 });
      const medium = findingsMatch(findings, { categories: ['headers'], minSev: 2 });
      if (critical.length > 0) return 'fail';
      if (medium.length > 0) return 'warn';
      return 'pass';
    },
  },
  {
    id: 'spf',
    label: 'Authentification email (SPF)',
    regulations: ['NIS2'],
    article: 'Art. 21 NIS2',
    desc: 'SPF strict (-all) empêche les tiers d\'envoyer des emails en usurpant votre domaine. +all est inacceptable.',
    blurred: false,
    icon: <Mail size={16} />,
    check: (findings) => {
      const spfFail = findingsMatch(findings, { titleWords: ['spf'], minSev: 3 });
      const spfWarn = findingsMatch(findings, { titleWords: ['spf', '+all'], minSev: 2 });
      if (spfFail.length > 0) return 'fail';
      if (spfWarn.length > 0) return 'warn';
      return 'pass';
    },
  },
  // ── Blurred ──
  {
    id: 'dkim',
    label: 'Signature DKIM des emails',
    regulations: ['NIS2'],
    article: 'Art. 21 NIS2',
    desc: 'DKIM garantit l\'intégrité et l\'authenticité des emails sortants.',
    blurred: true,
    icon: <Lock size={16} />,
    check: (findings) => {
      const dkim = findingsMatch(findings, { titleWords: ['dkim'], minSev: 2 });
      return dkim.length > 0 ? 'fail' : 'pass';
    },
  },
  {
    id: 'dnssec',
    label: 'Sécurité DNS (DNSSEC + CAA)',
    regulations: ['NIS2'],
    article: 'Art. 21 NIS2',
    desc: 'DNSSEC protège contre la falsification DNS. CAA limite les autorités autorisées à émettre des certificats.',
    blurred: true,
    icon: <Globe size={16} />,
    check: (findings) => {
      const dns = findingsMatch(findings, { titleWords: ['dnssec', 'caa'], minSev: 1 });
      if (dns.some(f => f.severity === 'MEDIUM' || f.severity === 'HIGH' || f.severity === 'CRITICAL')) return 'warn';
      return dns.length > 0 ? 'warn' : 'pass';
    },
  },
  {
    id: 'ports',
    label: 'Ports dangereux exposés',
    regulations: ['NIS2'],
    article: 'Art. 21 NIS2',
    desc: 'RDP, SMB, MySQL, Redis, Elasticsearch ne doivent jamais être accessibles depuis internet.',
    blurred: true,
    icon: <Server size={16} />,
    check: (findings) => {
      const ports = findingsMatch(findings, {
        categories: ['ports'],
        titleWords: ['rdp', 'smb', 'mysql', 'redis', 'mongo', 'elastic', '3389', '445'],
        minSev: 3,
      });
      return ports.length > 0 ? 'fail' : 'pass';
    },
  },
  {
    id: 'reputation',
    label: 'Réputation et blacklists',
    regulations: ['RGPD'],
    article: 'Art. 32 RGPD',
    desc: 'Votre domaine/IP ne doit pas figurer sur les listes noires email ou malware.',
    blurred: true,
    icon: <Shield size={16} />,
    check: (findings) => {
      const rep = findingsMatch(findings, { categories: ['reputation'], minSev: 3 });
      return rep.length > 0 ? 'fail' : 'pass';
    },
  },
  {
    id: 'credentials',
    label: 'Credentials exposés dans le code',
    regulations: ['RGPD'],
    article: 'Art. 32 RGPD',
    desc: 'Aucune clé API, token ou secret ne doit être visible dans le source HTML ou JavaScript public.',
    blurred: true,
    icon: <EyeOff size={16} />,
    check: (findings) => {
      const creds = findingsMatch(findings, {
        titleWords: ['credential', 'secret', 'token', 'api key', 'clé', 'exposed'],
        minSev: 3,
      });
      return creds.length > 0 ? 'fail' : 'pass';
    },
  },
  {
    id: 'expiry',
    label: 'Expiration du domaine',
    regulations: ['NIS2'],
    article: 'Art. 21 NIS2',
    desc: 'Un domaine expiré rend votre infrastructure inaccessible et peut être récupéré par un acteur malveillant.',
    blurred: true,
    icon: <Globe size={16} />,
    check: (findings) => {
      const exp = findingsMatch(findings, { titleWords: ['domain', 'expir', 'renouvell'], minSev: 2 });
      if (exp.some(f => f.severity === 'CRITICAL')) return 'fail';
      if (exp.length > 0) return 'warn';
      return 'pass';
    },
  },
  {
    id: 'versions',
    label: 'Logiciels et versions vulnérables',
    regulations: ['NIS2'],
    article: 'Art. 21 NIS2',
    desc: 'CMS, serveurs et frameworks doivent être à jour. Les versions connues avec CVE doivent être mises à jour.',
    blurred: true,
    icon: <AlertTriangle size={16} />,
    check: (findings) => {
      const cve = findingsMatch(findings, { categories: ['technologies'], minSev: 3 });
      if (cve.some(f => f.severity === 'CRITICAL')) return 'fail';
      if (cve.length > 0) return 'warn';
      return 'pass';
    },
  },
];

// ─── Score calculation ────────────────────────────────────────────────────────

function computeComplianceResults(findings: Finding[]): { criteria: (Criterion & { status: ComplianceStatus })[]; score: number; fails: number; warns: number } {
  const withStatus = CRITERIA.map(c => ({ ...c, status: c.check(findings) }));
  const passes = withStatus.filter(c => c.status === 'pass').length;
  const fails = withStatus.filter(c => c.status === 'fail').length;
  const warns = withStatus.filter(c => c.status === 'warn').length;
  return {
    criteria: withStatus,
    score: Math.round((passes / CRITERIA.length) * 100),
    fails,
    warns,
  };
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatusIcon({ status }: { status: ComplianceStatus }) {
  if (status === 'pass') return <CheckCircle2 size={18} className="text-green-400 shrink-0" />;
  if (status === 'fail') return <XCircle size={18} className="text-red-400 shrink-0" />;
  if (status === 'warn') return <AlertTriangle size={18} className="text-amber-400 shrink-0" />;
  return <div className="w-[18px] h-[18px] rounded-full bg-slate-700 shrink-0" />;
}

function RegBadge({ label }: { label: string }) {
  const isNIS2 = label === 'NIS2';
  return (
    <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wide ${
      isNIS2
        ? 'bg-blue-500/15 text-blue-400 border border-blue-500/25'
        : 'bg-purple-500/15 text-purple-400 border border-purple-500/25'
    }`}>{label}</span>
  );
}

function CriterionRow({ c }: { c: Criterion & { status: ComplianceStatus } }) {
  const borderColor = c.status === 'fail' ? 'border-red-500/20' : c.status === 'warn' ? 'border-amber-500/20' : c.status === 'pass' ? 'border-green-500/15' : 'border-slate-800';
  const bg = c.status === 'fail' ? 'bg-red-500/5' : c.status === 'warn' ? 'bg-amber-500/5' : c.status === 'pass' ? 'bg-green-500/5' : 'bg-slate-900/30';
  return (
    <div className={`flex items-start gap-3 p-4 rounded-xl border ${borderColor} ${bg}`}>
      <StatusIcon status={c.status} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center flex-wrap gap-1.5 mb-1">
          <span className="text-white text-sm font-semibold">{c.label}</span>
          {c.regulations.map(r => <RegBadge key={r} label={r} />)}
        </div>
        <p className="text-slate-500 text-xs leading-relaxed">{c.desc}</p>
        <p className="text-slate-600 text-[10px] mt-1 font-mono">{c.article}</p>
      </div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

interface Props {
  onGoBack:     () => void;
  onGoRegister: () => void;
  onGoLogin:    () => void;
}

export default function CompliancePage({ onGoBack, onGoRegister, onGoLogin }: Props) {
  const [domain, setDomain]   = useState('');
  const [scanning, setScanning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [result, setResult]   = useState<ScanResult | null>(null);
  const [error, setError]     = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  const cleanDomain = (v: string) =>
    v.trim().replace(/^https?:\/\//i, '').replace(/^www\./i, '').split('/')[0].toLowerCase();

  async function handleScan(e: FormEvent) {
    e.preventDefault();
    const d = cleanDomain(domain);
    if (!d) return;
    setError(null);
    setResult(null);
    setScanning(true);
    setProgress(0);

    // Progress animation
    const steps = [10, 25, 40, 60, 75, 88];
    let si = 0;
    const tick = setInterval(() => {
      if (si < steps.length) { setProgress(steps[si++]); }
    }, 600);

    try {
      const res = await scanDomain(d, 'fr');
      clearInterval(tick);
      setProgress(100);
      await new Promise(r => setTimeout(r, 300));
      setResult(res);
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
    } catch (err) {
      clearInterval(tick);
      const rl = extractRateLimitDetail(err);
      if (rl) {
        setError(`Quota atteint — réessayez dans quelques minutes.`);
      } else {
        setError(extractApiError(err) ?? 'Erreur lors de l\'analyse. Vérifiez le domaine et réessayez.');
      }
    } finally {
      setScanning(false);
    }
  }

  // Compliance results
  const compliance = result ? computeComplianceResults(result.findings as Finding[]) : null;
  const visibleCriteria  = compliance?.criteria.filter(c => !c.blurred) ?? [];
  const blurredCriteria  = compliance?.criteria.filter(c => c.blurred)  ?? [];
  const passCount        = compliance?.criteria.filter(c => c.status === 'pass').length ?? 0;

  const scoreColor = !compliance ? '#94a3b8'
    : compliance.score >= 80 ? '#4ade80'
    : compliance.score >= 50 ? '#fbbf24'
    : '#f87171';

  const scoreLabel = !compliance ? ''
    : compliance.score >= 80 ? 'Conforme'
    : compliance.score >= 50 ? 'Partiellement conforme'
    : 'Non conforme';

  return (
    <div className="min-h-screen text-white" style={{ fontFamily: "'Inter', system-ui, sans-serif" }}>

      {/* ── Navbar ──────────────────────────────────────────────────────────── */}
      <nav className="sticky top-0 z-50 border-b border-slate-800/60 bg-slate-950/80 backdrop-blur-xl">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
          <button onClick={onGoBack} className="flex items-center gap-1.5 text-slate-400 hover:text-white transition-colors text-sm">
            <ArrowLeft size={15} /> Retour
          </button>
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-lg bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center">
              <Shield size={12} className="text-cyan-400" />
            </div>
            <span className="font-black text-sm tracking-tight text-white">Wezea</span>
            <span className="text-slate-600 text-sm">/</span>
            <span className="text-slate-400 text-sm">Conformité NIS2 & RGPD</span>
          </div>
          <button onClick={onGoLogin} className="text-sm text-slate-400 hover:text-white transition-colors">
            Connexion
          </button>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-4 pb-20">

        {/* ── Hero ──────────────────────────────────────────────────────────── */}
        <div className="pt-14 pb-10 text-center">
          {/* Regulation badges */}
          <div className="flex items-center justify-center gap-2 mb-6">
            <span className="flex items-center gap-1.5 text-[11px] font-bold px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/25 text-blue-400">
              <Shield size={10} /> Directive NIS2
            </span>
            <span className="text-slate-700 text-xs">+</span>
            <span className="flex items-center gap-1.5 text-[11px] font-bold px-3 py-1 rounded-full bg-purple-500/10 border border-purple-500/25 text-purple-400">
              <Lock size={10} /> Règlement RGPD
            </span>
          </div>

          <h1 className="text-3xl md:text-4xl font-black text-white mb-4 leading-tight">
            Votre site respecte-t-il<br />
            <span className="text-transparent bg-clip-text" style={{ backgroundImage: 'linear-gradient(90deg, #22d3ee, #818cf8)' }}>
              NIS2 et le RGPD ?
            </span>
          </h1>
          <p className="text-slate-400 text-base max-w-xl mx-auto mb-3 leading-relaxed">
            Vérifiez en 60 secondes les 12 points de conformité techniques exigés par la directive NIS2
            et le RGPD — sans installation, sans accès serveur.
          </p>
          <p className="text-slate-600 text-xs max-w-sm mx-auto">
            NIS2 est en vigueur depuis octobre 2024. Les entreprises non conformes s'exposent à des amendes pouvant atteindre <span className="text-slate-500 font-semibold">10 M€ ou 2% du CA mondial</span>.
          </p>
        </div>

        {/* ── Scan form ──────────────────────────────────────────────────────── */}
        <form onSubmit={handleScan} className="mb-10">
          <div className="flex flex-col sm:flex-row gap-3 max-w-xl mx-auto">
            <input
              ref={inputRef}
              type="text"
              value={domain}
              onChange={e => setDomain(e.target.value)}
              placeholder="exemple.fr"
              disabled={scanning}
              className="flex-1 px-4 py-3 rounded-xl bg-slate-900 border border-slate-700 text-white placeholder-slate-600 text-sm focus:outline-none focus:border-cyan-500/60 focus:ring-1 focus:ring-cyan-500/30 disabled:opacity-50 font-mono"
            />
            <button
              type="submit"
              disabled={scanning || !domain.trim()}
              className="px-6 py-3 rounded-xl font-bold text-sm text-white disabled:opacity-40 disabled:cursor-not-allowed transition-all whitespace-nowrap"
              style={{ background: 'linear-gradient(135deg, #22d3ee 0%, #818cf8 100%)' }}
            >
              {scanning ? 'Analyse en cours…' : 'Lancer le diagnostic'}
            </button>
          </div>

          {/* Progress bar */}
          <AnimatePresence>
            {scanning && (
              <motion.div className="mt-4 max-w-xl mx-auto" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs text-slate-500">Analyse des critères NIS2 / RGPD…</span>
                  <span className="text-xs text-slate-500 font-mono">{progress}%</span>
                </div>
                <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                  <motion.div className="h-full rounded-full"
                    style={{ background: 'linear-gradient(90deg, #22d3ee, #818cf8)' }}
                    animate={{ width: `${progress}%` }}
                    transition={{ duration: 0.5, ease: 'easeOut' }}
                  />
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Error */}
          <AnimatePresence>
            {error && (
              <motion.p className="mt-3 text-center text-sm text-red-400" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                {error}
              </motion.p>
            )}
          </AnimatePresence>
        </form>

        {/* ── Results ─────────────────────────────────────────────────────── */}
        <AnimatePresence>
          {compliance && (
            <motion.div ref={resultsRef} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>

              {/* Score header */}
              <div className="flex flex-col sm:flex-row items-center justify-between gap-4 mb-8 p-5 rounded-2xl border border-slate-800 bg-slate-900/50">
                <div>
                  <p className="text-slate-400 text-sm mb-1">Résultat pour <span className="text-white font-mono font-bold">{cleanDomain(domain)}</span></p>
                  <h2 className="text-2xl font-black text-white">{scoreLabel}</h2>
                  <p className="text-slate-500 text-sm mt-0.5">{passCount} / {CRITERIA.length} critères conformes</p>
                </div>
                <div className="flex items-baseline gap-1 shrink-0">
                  <span className="text-5xl font-black font-mono" style={{ color: scoreColor }}>{compliance.score}</span>
                  <span className="text-slate-500 text-lg font-mono">/100</span>
                </div>
              </div>

              {/* Visible criteria */}
              <div className="mb-6">
                <div className="flex items-center gap-2 mb-4">
                  <Eye size={14} className="text-slate-500" />
                  <span className="text-xs font-semibold text-slate-500 uppercase tracking-widest">
                    Critères analysés — résultats gratuits
                  </span>
                </div>
                <div className="grid grid-cols-1 gap-3">
                  {visibleCriteria.map(c => (
                    <CriterionRow key={c.id} c={c} />
                  ))}
                </div>
              </div>

              {/* Blurred section */}
              <div className="relative">
                {/* Blurred cards */}
                <div className="grid grid-cols-1 gap-3 blur-sm pointer-events-none select-none" aria-hidden>
                  {blurredCriteria.map(c => (
                    <div key={c.id} className="flex items-start gap-3 p-4 rounded-xl border border-slate-800 bg-slate-900/30">
                      <div className="w-[18px] h-[18px] rounded-full bg-slate-700 shrink-0 mt-0.5" />
                      <div className="flex-1">
                        <div className="flex items-center flex-wrap gap-1.5 mb-1">
                          <span className="text-white text-sm font-semibold">{c.label}</span>
                          {c.regulations.map(r => <RegBadge key={r} label={r} />)}
                        </div>
                        <p className="text-slate-500 text-xs">{c.desc}</p>
                      </div>
                    </div>
                  ))}
                </div>

                {/* CTA overlay */}
                <div className="absolute inset-0 flex flex-col items-center justify-center rounded-2xl px-6 py-8"
                  style={{ background: 'linear-gradient(180deg, rgba(2,8,18,0) 0%, rgba(2,8,18,0.85) 20%, rgba(2,8,18,0.97) 60%)' }}>
                  <div className="text-center max-w-sm">
                    <div className="w-12 h-12 rounded-2xl flex items-center justify-center mx-auto mb-4"
                      style={{ background: 'linear-gradient(135deg, #22d3ee20, #818cf820)', border: '1px solid rgba(130,140,248,0.3)' }}>
                      <Lock size={20} className="text-indigo-400" />
                    </div>
                    <h3 className="text-white font-black text-lg mb-2">
                      {blurredCriteria.length} critères supplémentaires
                    </h3>
                    <p className="text-slate-400 text-sm mb-1 leading-relaxed">
                      Créez un compte gratuit pour accéder à l'analyse complète — ports, DNS avancé,
                      credentials exposés, versions vulnérables et rapport NIS2 exportable.
                    </p>
                    <p className="text-slate-600 text-xs mb-5">
                      Sans carte bancaire · Résultats en 60 secondes
                    </p>
                    <button
                      onClick={onGoRegister}
                      className="w-full py-3 rounded-xl font-bold text-sm text-white mb-3 flex items-center justify-center gap-2"
                      style={{ background: 'linear-gradient(135deg, #22d3ee 0%, #818cf8 100%)' }}
                    >
                      Voir les {blurredCriteria.length} critères restants
                      <ChevronRight size={16} />
                    </button>
                    <button
                      onClick={onGoLogin}
                      className="text-sm text-slate-500 hover:text-slate-300 transition-colors"
                    >
                      Déjà un compte ? Se connecter
                    </button>
                  </div>
                </div>
              </div>

              {/* Info footer */}
              <div className="mt-10 p-5 rounded-2xl border border-slate-800 bg-slate-900/30">
                <h4 className="text-white font-bold text-sm mb-3">À propos de ce diagnostic</h4>
                <p className="text-slate-500 text-xs leading-relaxed">
                  Ce diagnostic effectue une analyse technique externe de votre domaine — sans installation ni accès serveur.
                  Les vérifications couvrent les exigences de l'article 21 de la directive NIS2 (mesures de sécurité techniques)
                  et de l'article 32 du RGPD (sécurité du traitement). Ce diagnostic est indicatif et ne constitue
                  pas un audit de conformité juridique.
                </p>
              </div>

            </motion.div>
          )}
        </AnimatePresence>

        {/* ── NIS2/RGPD info (idle) ─────────────────────────────────────────── */}
        {!result && !scanning && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 mt-4">
            {[
              {
                color: '#60a5fa',
                title: 'Directive NIS2',
                subtitle: 'En vigueur depuis oct. 2024',
                desc: 'La directive européenne NIS2 impose des mesures techniques de cybersécurité à des milliers d\'entreprises françaises (article 21). Les sanctions peuvent atteindre 10 M€ ou 2% du CA mondial.',
              },
              {
                color: '#a78bfa',
                title: 'Règlement RGPD',
                subtitle: 'Applicable depuis mai 2018',
                desc: 'Le RGPD (articles 25 et 32) exige la mise en place de mesures techniques pour protéger les données personnelles. Un manque de sécurité peut constituer une violation de données à notifier à la CNIL.',
              },
            ].map((item, i) => (
              <div key={i} className="p-5 rounded-2xl border border-slate-800 bg-slate-900/30">
                <div className="flex items-start gap-3 mb-3">
                  <div className="p-2 rounded-lg shrink-0" style={{ background: `${item.color}18`, border: `1px solid ${item.color}30` }}>
                    <Shield size={16} style={{ color: item.color }} />
                  </div>
                  <div>
                    <p className="text-white font-bold text-sm">{item.title}</p>
                    <p className="text-slate-600 text-xs">{item.subtitle}</p>
                  </div>
                </div>
                <p className="text-slate-500 text-xs leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        )}

      </div>
    </div>
  );
}
