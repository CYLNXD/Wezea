// ─── Dashboard.tsx — Page principale de CyberHealth Scanner ──────────────────
//
// États :
//   idle     → Barre de recherche + hero
//   scanning → ScanConsole animée
//   success  → ScoreGauge + FindingCards + FinancialRisk + CTABanner
//   error    → Message d'erreur avec retry
//
import { useState, FormEvent, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Shield, Search, ArrowRight, RotateCcw,
  FileDown, Globe, AlertTriangle, Info, Lock, X,
} from 'lucide-react';
import { apiClient } from '../lib/api';

import { useLanguage } from '../i18n/LanguageContext';
import { useAuth } from '../contexts/AuthContext';
import { useScanner } from '../hooks/useScanner';
import { ScanConsole } from '../components/ScanConsole';
import { ScoreGauge } from '../components/ScoreGauge';
import { FindingCard, FindingGroup } from '../components/FindingCard';
import { CTABanner } from '../components/CTABanner';
import { EmailCaptureModal } from '../components/EmailCaptureModal';
import type { Finding } from '../types/scanner';

// ─────────────────────────────────────────────────────────────────────────────

const EXAMPLE_DOMAINS = ['votreentreprise.fr', 'mapmeshop.com', 'cabinetdurand.fr'];

interface Props {
  onGoLogin?:   () => void;
  onGoHistory?: () => void;
}

export default function Dashboard({ onGoLogin, onGoHistory }: Props) {
  const [domain, setDomain]         = useState('');
  const [modalOpen, setModalOpen]   = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [pwModalOpen, setPwModalOpen]   = useState(false);
  const [pwCurrent, setPwCurrent]       = useState('');
  const [pwNew, setPwNew]               = useState('');
  const [pwConfirm, setPwConfirm]       = useState('');
  const [pwLoading, setPwLoading]       = useState(false);
  const [pwError, setPwError]           = useState('');
  const [pwSuccess, setPwSuccess]       = useState(false);
  const inputRef                    = useRef<HTMLInputElement>(null);
  const resultsRef                  = useRef<HTMLDivElement>(null);

  const { lang, setLang, t } = useLanguage();
  const { user, logout } = useAuth();
  const scanner = useScanner();

  const handleChangePassword = async (e: FormEvent) => {
    e.preventDefault();
    setPwError('');
    if (pwNew !== pwConfirm) {
      setPwError(lang === 'fr' ? 'Les mots de passe ne correspondent pas' : 'Passwords do not match');
      return;
    }
    if (pwNew.length < 8) {
      setPwError(lang === 'fr' ? 'Minimum 8 caractères' : 'Minimum 8 characters');
      return;
    }
    setPwLoading(true);
    try {
      await apiClient.post('/auth/change-password', {
        current_password: pwCurrent,
        new_password: pwNew,
      });
      setPwSuccess(true);
      setTimeout(() => {
        setPwModalOpen(false);
        setPwSuccess(false);
        setPwCurrent(''); setPwNew(''); setPwConfirm('');
      }, 1800);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setPwError(detail || (lang === 'fr' ? 'Erreur lors du changement' : 'Change failed'));
    } finally {
      setPwLoading(false);
    }
  };

  const handleSubmit = async (e: FormEvent, overrideDomain?: string) => {
    e.preventDefault();
    const target = (overrideDomain ?? domain).trim();
    if (!target) return;
    setDomain(target);
    await scanner.startScan(target);
    // Scroll vers les résultats après un court délai
    setTimeout(() => {
      resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 300);
  };

  // Grouper les findings par catégorie
  const groupFindings = (findings: Finding[]) => ({
    dns:        findings.filter(f => f.category === 'DNS & Mail'),
    ssl:        findings.filter(f => f.category === 'SSL / HTTPS'),
    ports:      findings.filter(f => f.category === 'Exposition des Ports'),
    headers:    findings.filter(f => f.category === 'En-têtes HTTP'),
    emailSec:   findings.filter(f => f.category === 'Sécurité Email'),
    tech:       findings.filter(f => f.category === 'Exposition Technologique'),
    reputation: findings.filter(f => f.category === 'Réputation du Domaine' && f.severity !== 'INFO'),
    info:       findings.filter(f => f.severity === 'INFO'),
  });

  const isIdle     = scanner.status === 'idle';
  const isScanning = scanner.status === 'scanning';
  const isSuccess  = scanner.status === 'success';
  const isError    = scanner.status === 'error';

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">



      {/* ── Navigation ──────────────────────────────────────────────────────── */}
      <nav className="border-b border-slate-800/70 bg-slate-950/80 backdrop-blur-sm sticky top-0 z-20">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
              <Shield size={18} className="text-cyan-400" />
            </div>
            <span className="font-bold text-white font-mono tracking-tight">
              We<span className="text-cyan-400">zea</span>
            </span>
            <span className="text-xs text-slate-600 font-mono hidden sm:block">Scanner</span>
          </div>
          <div className="flex items-center gap-2">
            {isSuccess && scanner.result && (
              <motion.button
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                onClick={() => setModalOpen(true)}
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/20 transition-colors font-mono"
              >
                <FileDown size={13} />
                {t('btn_report')}
              </motion.button>
            )}
            {!isIdle && (
              <button
                onClick={scanner.reset}
                className="text-xs text-slate-500 hover:text-slate-300 transition-colors font-mono flex items-center gap-1.5 px-3 py-1.5 rounded-lg hover:bg-slate-800"
              >
                <RotateCcw size={12} />
                {t('btn_new_scan')}
              </button>
            )}

            {/* User menu */}
            {user ? (
              <div className="relative">
                <button
                  onClick={() => setUserMenuOpen(v => !v)}
                  className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:text-white hover:border-slate-600 transition font-mono"
                >
                  <div className="w-5 h-5 rounded-full bg-cyan-500/20 flex items-center justify-center text-cyan-400 text-xs font-bold">
                    {user.email[0].toUpperCase()}
                  </div>
                  <span className="hidden sm:block max-w-[100px] truncate">{user.email.split('@')[0]}</span>
                </button>
                {userMenuOpen && (
                  <div className="absolute right-0 top-full mt-1.5 w-48 bg-slate-900 border border-slate-700 rounded-xl shadow-xl z-50 overflow-hidden">
                    <div className="px-3 py-2 border-b border-slate-800">
                      <p className="text-xs text-slate-400 truncate">{user.email}</p>
                      <span className={`text-xs font-mono ${user.plan !== 'free' ? 'text-cyan-400' : 'text-slate-500'}`}>
                        {user.plan === 'free' ? (lang === 'fr' ? 'Gratuit' : 'Free') : user.plan.charAt(0).toUpperCase() + user.plan.slice(1)}
                      </span>
                    </div>
                    <button
                      onClick={() => { setUserMenuOpen(false); onGoHistory?.(); }}
                      className="w-full text-left px-3 py-2 text-xs text-slate-300 hover:bg-slate-800 hover:text-white transition font-mono flex items-center gap-2"
                    >
                      📋 {lang === 'fr' ? 'Historique des scans' : 'Scan history'}
                    </button>
                    <button
                      onClick={() => { setUserMenuOpen(false); setPwModalOpen(true); }}
                      className="w-full text-left px-3 py-2 text-xs text-slate-300 hover:bg-slate-800 hover:text-white transition font-mono flex items-center gap-2"
                    >
                      🔒 {lang === 'fr' ? 'Changer le mot de passe' : 'Change password'}
                    </button>
                    <button
                      onClick={() => { setUserMenuOpen(false); logout(); }}
                      className="w-full text-left px-3 py-2 text-xs text-red-400 hover:bg-red-500/10 transition font-mono flex items-center gap-2"
                    >
                      ↩ {lang === 'fr' ? 'Déconnexion' : 'Sign out'}
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <button
                onClick={onGoLogin}
                className="text-xs px-3 py-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/20 transition font-mono"
              >
                {lang === 'fr' ? 'Connexion' : 'Sign in'}
              </button>
            )}

            {/* Lang toggle */}
            <button
              onClick={() => setLang(lang === 'fr' ? 'en' : 'fr')}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-800 border border-slate-700 hover:border-cyan-500/50 text-slate-400 hover:text-cyan-400 text-xs font-mono font-semibold transition-all"
            >
              <span className={lang === 'fr' ? 'text-cyan-400' : 'text-slate-500'}>FR</span>
              <span className="text-slate-600">|</span>
              <span className={lang === 'en' ? 'text-cyan-400' : 'text-slate-500'}>EN</span>
            </button>
          </div>
        </div>
      </nav>

      {/* ── Hero + Barre de recherche ────────────────────────────────────────── */}
      <header className={`
        relative overflow-hidden transition-all duration-700
        ${isIdle ? 'py-24 md:py-36' : 'py-10 md:py-14'}
      `}>
        {/* Fond dégradé */}
        <div className="absolute inset-0 bg-gradient-to-b from-cyan-950/20 via-slate-950 to-slate-950 pointer-events-none" />
        {/* Grille cyber décorative */}
        <div
          className="absolute inset-0 opacity-[0.03] pointer-events-none"
          style={{
            backgroundImage: `linear-gradient(rgba(14,165,233,1) 1px, transparent 1px),
                              linear-gradient(90deg, rgba(14,165,233,1) 1px, transparent 1px)`,
            backgroundSize: '40px 40px',
          }}
        />

        <div className="relative max-w-3xl mx-auto px-4 text-center">
          <AnimatePresence>
            {isIdle && (
              <motion.div
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -16 }}
                transition={{ duration: 0.4 }}
              >
                {/* Badge */}
                <div className="inline-flex items-center gap-2 bg-cyan-500/10 border border-cyan-500/20 rounded-full px-4 py-1.5 mb-6 text-cyan-400 text-xs font-mono">
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
                  {t('hero_badge')}
                </div>

                <h1 className="text-4xl md:text-5xl font-black text-white leading-tight mb-4">
                  {t('hero_title_1')}<br />
                  <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-500">
                    {t('hero_title_2')}
                  </span>
                </h1>
                <p className="text-slate-400 text-lg mb-8 max-w-xl mx-auto leading-relaxed">
                  {t('hero_subtitle')}
                </p>
                {/* Badges des vérifications */}
                <div className="flex flex-wrap justify-center gap-2 mb-6 text-xs font-mono">
                  {[
                    { icon: '🛡️', label: t('badge_headers') },
                    { icon: '📨', label: t('badge_spf') },
                    { icon: '🔒', label: t('badge_ssl') },
                    { icon: '🌐', label: t('badge_ports') },
                    { icon: '🔍', label: t('badge_tech') },
                    { icon: '⚫', label: t('badge_dnsbl') },
                  ].map(({ icon, label }) => (
                    <span key={label} className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-800/80 border border-slate-700/60 text-slate-400">
                      {icon} {label}
                    </span>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* ── Barre de recherche ──────────────────────────────────────── */}
          <form onSubmit={handleSubmit} className="relative max-w-2xl mx-auto">
            <div className="flex items-center gap-2 bg-slate-900 border border-slate-700 rounded-2xl p-2 focus-within:border-cyan-500/60 focus-within:shadow-lg focus-within:shadow-cyan-900/20 transition-all duration-200">
              <Globe size={18} className="ml-2 text-slate-500 shrink-0" />
              <input
                ref={inputRef}
                id="domain-input"
                name="domain"
                type="text"
                value={domain}
                onChange={e => setDomain(e.target.value)}
                disabled={isScanning}
                className="
                  flex-1 bg-transparent text-white placeholder:text-slate-600
                  font-mono text-sm focus:outline-none px-2 py-2
                  disabled:cursor-not-allowed
                "
                aria-label="Nom de domaine à analyser"
                autoComplete="url"
                spellCheck={false}
                placeholder={t('placeholder')}
              />
              <button
                type="submit"
                disabled={isScanning || !domain.trim()}
                className="
                  flex items-center gap-2 px-5 py-2.5 rounded-xl
                  bg-gradient-to-r from-cyan-600 to-blue-600
                  hover:from-cyan-500 hover:to-blue-500
                  text-white font-bold text-sm
                  disabled:opacity-50 disabled:cursor-not-allowed
                  transition-all duration-200 shadow-lg shadow-cyan-900/30
                  shrink-0
                "
              >
                <Search size={15} />
                <span className="hidden sm:inline">{t('btn_scan')}</span>
                <ArrowRight size={14} />
              </button>
            </div>
          </form>

          {/* Domaines exemple */}
          {isIdle && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.3 }}
              className="flex flex-wrap items-center justify-center gap-2 mt-4"
            >
              <span className="text-slate-600 text-xs font-mono">{t('hero_try')}:</span>
              {EXAMPLE_DOMAINS.map(d => (
                <button
                  key={d}
                  onClick={e => handleSubmit(e as unknown as FormEvent, d)}
                  className="text-xs font-mono text-slate-500 hover:text-cyan-400 transition-colors px-2 py-1 rounded border border-slate-800 hover:border-cyan-500/30 bg-slate-900/50"
                >
                  {d}
                </button>
              ))}
            </motion.div>
          )}
        </div>
      </header>

      {/* ── Corps principal ──────────────────────────────────────────────────── */}
      <main ref={resultsRef} className="max-w-6xl mx-auto px-4 pb-32">
        <AnimatePresence mode="wait">

          {/* ── Console de scan ───────────────────────────────────────── */}
          {isScanning && (
            <motion.div
              key="console"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex justify-center py-6"
            >
              <ScanConsole
                logs={scanner.consoleLogs}
                progress={scanner.progress}
                domain={domain}
              />
            </motion.div>
          )}

          {/* ── Erreur ────────────────────────────────────────────────── */}
          {isError && (
            <motion.div
              key="error"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="max-w-lg mx-auto py-12 text-center"
            >
              <div className="p-4 rounded-full bg-red-500/10 border border-red-500/20 w-fit mx-auto mb-4">
                <AlertTriangle size={28} className="text-red-400" />
              </div>
              <h3 className="text-white font-bold text-lg mb-2">{t('scan_error')}</h3>
              <p className="text-slate-400 text-sm mb-6">{scanner.error}</p>
              <button
                onClick={scanner.reset}
                className="flex items-center gap-2 mx-auto px-5 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium text-sm transition-colors"
              >
                <RotateCcw size={15} />
                {t('btn_retry')}
              </button>
            </motion.div>
          )}

          {/* ── Résultats ─────────────────────────────────────────────── */}
          {isSuccess && scanner.result && (() => {
            const r = scanner.result;
            const groups = groupFindings(r.findings);

            return (
              <motion.div
                key="results"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.4 }}
                className="grid grid-cols-1 lg:grid-cols-3 gap-6 py-8"
              >
                {/* ── Colonne gauche : Score + Risk ─────────────────── */}
                <div className="lg:col-span-1 flex flex-col gap-5">

                  {/* Score Gauge */}
                  <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.1 }}
                    className="bg-slate-900 border border-slate-800 rounded-2xl p-6 flex flex-col items-center"
                  >
                    <ScoreGauge
                      score={r.security_score}
                      riskLevel={r.risk_level}
                      domain={r.domain}
                    />
                  </motion.div>

                  {/* Stats résumées */}
                  <motion.div
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.2 }}
                    className="grid grid-cols-2 gap-3"
                  >
                    <StatCard
                      label={t('stat_vulns')}
                      value={r.findings.filter(f => f.severity !== 'INFO').length}
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
                  </motion.div>

                  {/* Bouton rapport */}
                  <motion.button
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.5 }}
                    onClick={() => setModalOpen(true)}
                    className="
                      flex items-center justify-center gap-2
                      w-full py-3 rounded-xl font-bold text-sm
                      bg-gradient-to-r from-cyan-700/50 to-blue-700/50
                      hover:from-cyan-600/60 hover:to-blue-600/60
                      border border-cyan-500/30 text-cyan-300
                      transition-all duration-200
                    "
                  >
                    <FileDown size={15} />
                    {t('cta_audit')}
                  </motion.button>

                  {/* Meta scan */}
                  <p className="text-center text-slate-700 text-[10px] font-mono">
                    {t('scan_duration', { ms: (r.scan_duration_ms / 1000).toFixed(1), date: new Date(r.scanned_at).toLocaleString(lang === 'fr' ? 'fr-FR' : 'en-US') })}
                  </p>
                </div>

                {/* ── Colonne droite : Findings ─────────────────────── */}
                <div className="lg:col-span-2 flex flex-col gap-5">

                  {/* En-tête findings */}
                  <div className="flex items-center justify-between">
                    <h2 className="text-white font-bold text-lg">
                      {r.findings.length === 0 ? t('vulns_none') : t('vulns_found')}
                    </h2>
                    <span className="text-slate-500 text-xs font-mono">
                      {r.findings.length} finding(s)
                    </span>
                  </div>

                  {/* Cas : aucune vulnérabilité */}
                  {r.findings.length === 0 && (
                    <div className="flex flex-col items-center gap-3 py-12 text-center bg-slate-900/50 rounded-2xl border border-slate-800">
                      <div className="p-3 rounded-full bg-green-500/10 border border-green-500/20">
                        <Shield size={24} className="text-green-400" />
                      </div>
                      <p className="text-green-400 font-bold">{t('vulns_none')}</p>
                      <p className="text-slate-500 text-sm max-w-sm">
                        {t('vulns_none_sub')}
                      </p>
                    </div>
                  )}

                  {/* Groupes de findings — originaux */}
                  <FindingGroup title={t('group_dns')}        findings={groups.dns}   startIdx={0} />
                  <FindingGroup title={t('group_ssl')}       findings={groups.ssl}   startIdx={groups.dns.length} />
                  <FindingGroup title={t('group_ports')} findings={groups.ports} startIdx={groups.dns.length + groups.ssl.length} />
                  {/* Groupes de findings — nouveaux checks */}
                  <FindingGroup title={t('group_headers')}    findings={groups.headers}    startIdx={groups.dns.length + groups.ssl.length + groups.ports.length} />
                  <FindingGroup title={t('group_email')}        findings={groups.emailSec}   startIdx={groups.dns.length + groups.ssl.length + groups.ports.length + groups.headers.length} />
                  <FindingGroup title={t('group_tech')}      findings={groups.tech}       startIdx={groups.dns.length + groups.ssl.length + groups.ports.length + groups.headers.length + groups.emailSec.length} />
                  <FindingGroup title={t('group_reputation')}         findings={groups.reputation} startIdx={groups.dns.length + groups.ssl.length + groups.ports.length + groups.headers.length + groups.emailSec.length + groups.tech.length} />

                  {/* Infos */}
                  {groups.info.length > 0 && (
                    <details className="group">
                      <summary className="flex items-center gap-2 text-xs font-mono text-slate-600 cursor-pointer hover:text-slate-400 transition-colors list-none">
                        <Info size={12} />
                        {groups.info.length} {t('findings_info')}
                        <span className="text-slate-700 group-open:rotate-90 transition-transform">▶</span>
                      </summary>
                      <div className="mt-3 flex flex-col gap-3">
                        {groups.info.map((f, i) => (
                          <FindingCard key={(f.title ?? f.message ?? '') + i} finding={f} index={i} />
                        ))}
                      </div>
                    </details>
                  )}

                  {/* Résumé des ports */}
                  <PortSummary portDetails={r.port_details} />
                </div>
              </motion.div>
            );
          })()}

        </AnimatePresence>
      </main>

      {/* ── Modaux & bandeaux ─────────────────────────────────────────────────── */}
      {isSuccess && scanner.result && (
        <>
          <CTABanner
            score={scanner.result.security_score}
            domain={scanner.result.domain}
            onOpenReport={() => setModalOpen(true)}
          />
          <EmailCaptureModal
            open={modalOpen}
            onClose={() => setModalOpen(false)}
            domain={scanner.result.domain}
            score={scanner.result.security_score}
            scanResult={scanner.result}
          />
        </>
      )}

      {/* ── Modal : Changer le mot de passe ─────────────────────────────── */}
      <AnimatePresence>
        {pwModalOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm px-4"
            onClick={() => { if (!pwLoading) { setPwModalOpen(false); setPwError(''); setPwSuccess(false); setPwCurrent(''); setPwNew(''); setPwConfirm(''); } }}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              onClick={e => e.stopPropagation()}
              className="w-full max-w-sm bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl p-6"
            >
              <div className="flex items-center justify-between mb-5">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
                    <Lock size={15} className="text-cyan-400" />
                  </div>
                  <h2 className="text-white font-mono font-bold text-sm">
                    {lang === 'fr' ? 'Changer le mot de passe' : 'Change password'}
                  </h2>
                </div>
                <button
                  onClick={() => { setPwModalOpen(false); setPwError(''); setPwSuccess(false); setPwCurrent(''); setPwNew(''); setPwConfirm(''); }}
                  className="text-slate-500 hover:text-white transition p-1 rounded"
                >
                  <X size={16} />
                </button>
              </div>

              {pwSuccess ? (
                <div className="text-center py-6">
                  <div className="text-3xl mb-2">✅</div>
                  <p className="text-emerald-400 font-mono text-sm">
                    {lang === 'fr' ? 'Mot de passe mis à jour !' : 'Password updated!'}
                  </p>
                </div>
              ) : (
                <form onSubmit={handleChangePassword} className="space-y-3">
                  <div>
                    <label className="block text-xs text-slate-400 font-mono mb-1">
                      {lang === 'fr' ? 'Mot de passe actuel' : 'Current password'}
                    </label>
                    <input
                      type="password"
                      value={pwCurrent}
                      onChange={e => setPwCurrent(e.target.value)}
                      required
                      autoComplete="current-password"
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-cyan-500 transition"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 font-mono mb-1">
                      {lang === 'fr' ? 'Nouveau mot de passe' : 'New password'}
                    </label>
                    <input
                      type="password"
                      value={pwNew}
                      onChange={e => setPwNew(e.target.value)}
                      required
                      autoComplete="new-password"
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-cyan-500 transition"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 font-mono mb-1">
                      {lang === 'fr' ? 'Confirmer le nouveau mot de passe' : 'Confirm new password'}
                    </label>
                    <input
                      type="password"
                      value={pwConfirm}
                      onChange={e => setPwConfirm(e.target.value)}
                      required
                      autoComplete="new-password"
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-cyan-500 transition"
                    />
                  </div>

                  {pwError && (
                    <p className="text-red-400 text-xs font-mono bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                      {pwError}
                    </p>
                  )}

                  <button
                    type="submit"
                    disabled={pwLoading}
                    className="w-full mt-1 py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 text-slate-950 font-bold text-sm font-mono transition flex items-center justify-center gap-2"
                  >
                    {pwLoading ? (
                      <div className="w-4 h-4 border-2 border-slate-950/30 border-t-slate-950 rounded-full animate-spin" />
                    ) : (
                      <>{lang === 'fr' ? 'Mettre à jour' : 'Update password'}</>
                    )}
                  </button>
                </form>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-composants internes
// ─────────────────────────────────────────────────────────────────────────────

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
