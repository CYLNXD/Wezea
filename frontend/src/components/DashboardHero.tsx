// ─── DashboardHero — Hero section + search bar extracted from Dashboard ──────
import { useState, useEffect, useRef, FormEvent, ReactNode } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Search, ArrowRight, Globe, UserPlus, Zap,
} from 'lucide-react';

import { useLanguage } from '../i18n/LanguageContext';
import type { RateLimitInfo } from '../lib/api';
import type { RegisterCtaSource, PricingSource } from '../lib/analytics';

// ─────────────────────────────────────────────────────────────────────────────

// CountUp — animation de comptage déclenchée au scroll (IntersectionObserver)
function CountUp({ to, suffix = '' }: { to: number; suffix?: string }) {
  const [val, setVal] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  const started = useRef(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && !started.current) {
        started.current = true;
        const duration = 1400;
        const t0 = performance.now();
        const tick = (now: number) => {
          const p = Math.min((now - t0) / duration, 1);
          const eased = 1 - Math.pow(1 - p, 3);
          setVal(Math.round(eased * to));
          if (p < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
        obs.disconnect();
      }
    }, { threshold: 0.5 });
    obs.observe(el);
    return () => obs.disconnect();
  }, [to]);
  return <span ref={ref}>{val.toLocaleString()}{suffix}</span>;
}

// ─────────────────────────────────────────────────────────────────────────────

export interface DashboardHeroProps {
  isIdle: boolean;
  isScanning: boolean;
  domain: string;
  setDomain: (v: string) => void;
  inputRef: React.RefObject<HTMLInputElement>;
  handleSubmit: (e: FormEvent, overrideDomain?: string) => void;
  scanLimits: RateLimitInfo | null;
  publicStats: { total_scans: number; industry_avg?: number } | null;
  goRegister: (source: RegisterCtaSource) => void;
  openPricing: (source: PricingSource) => void;
}

export default function DashboardHero({
  isIdle,
  isScanning,
  domain,
  setDomain,
  inputRef,
  handleSubmit,
  scanLimits,
  publicStats,
  goRegister,
  openPricing,
}: DashboardHeroProps) {
  const { lang, t } = useLanguage();

  return (
    <header className={`
      relative overflow-hidden transition-all duration-700
      ${isIdle ? 'py-12 md:py-18' : 'py-10 md:py-14'}
    `}>
      {/* Ambiance radiale */}
      <div className="absolute inset-0 pointer-events-none" style={{
        background: 'radial-gradient(ellipse at 50% -10%, rgba(34,211,238,0.06) 0%, transparent 60%)',
      }} />
      {/* Grille cyber decorative subtile */}
      <div
        className="absolute inset-0 opacity-[0.025] pointer-events-none"
        style={{
          backgroundImage: `linear-gradient(rgba(34,211,238,1) 1px, transparent 1px),
                            linear-gradient(90deg, rgba(34,211,238,1) 1px, transparent 1px)`,
          backgroundSize: '48px 48px',
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
              <div
                className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 mb-6 text-cyan-400 text-xs font-medium"
                style={{ background: 'rgba(34,211,238,0.07)', border: '1px solid rgba(34,211,238,0.15)', boxShadow: '0 0 20px rgba(34,211,238,0.05), 0 1px 0 rgba(255,255,255,0.05) inset' }}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
                {t('hero_badge')}
              </div>

              <h1 className="text-3xl sm:text-4xl md:text-5xl font-black leading-tight mb-4"
                style={{ background: 'linear-gradient(180deg,#f1f5f9 30%,#94a3b8 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}
              >
                {t('hero_title_1')}<br />
                <span style={{ background: 'linear-gradient(135deg,#22d3ee,#60a5fa)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                  {t('hero_title_2')}
                </span>
              </h1>
              <p className="text-slate-500 text-lg mb-8 max-w-xl mx-auto leading-relaxed">
                {t('hero_subtitle')}
              </p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Barre de recherche ──────────────────────────────────────── */}
        <form onSubmit={handleSubmit} className="relative max-w-2xl mx-auto flex flex-col gap-3">
          <div
            className="flex items-center gap-2 rounded-2xl p-2 transition-all duration-200"
            style={{
              background: 'linear-gradient(180deg,#0f151e,#0b1018)',
              border: '1px solid rgba(255,255,255,0.07)',
              boxShadow: '0 4px 24px rgba(0,0,0,0.6), 0 1px 0 rgba(255,255,255,0.05) inset',
            }}
          >
            <Globe size={18} className="ml-2 text-slate-600 shrink-0" />
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
            {/* Bouton inline — desktop uniquement */}
            <button
              type="submit"
              disabled={isScanning || !domain.trim()}
              className="sku-btn-primary hidden sm:flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm shrink-0 disabled:opacity-40 disabled:cursor-not-allowed disabled:transform-none"
            >
              <Search size={15} />
              {t('btn_scan')}
              <ArrowRight size={14} />
            </button>
          </div>

          {/* Bouton pleine largeur — mobile uniquement */}
          <button
            type="submit"
            disabled={isScanning || !domain.trim()}
            className="sku-btn-primary sm:hidden flex items-center justify-center gap-2 w-full py-3.5 rounded-2xl text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed disabled:transform-none"
          >
            <Search size={15} />
            {t('btn_scan')}
            <ArrowRight size={14} />
          </button>
        </form>

        {/* ── Reassurance sous le champ ─────────────────────────────── */}
        {isIdle && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4 }}
            className="flex flex-wrap items-center justify-center gap-x-5 gap-y-1.5 mt-3"
          >
            {[
              { label: lang === 'fr' ? '✓ 100% externe, sans risque' : '✓ 100% external, zero risk', hi: false },
              { label: lang === 'fr' ? '✓ Sans installation' : '✓ No installation', hi: false },
              { label: lang === 'fr' ? '✓ DAST actif inclus' : '✓ Active DAST included', hi: true },
              { label: lang === 'fr' ? '✓ Scan des credentials' : '✓ Credential scanning', hi: true },
              { label: lang === 'fr' ? '✓ Rapport PDF inclus' : '✓ PDF report included', hi: false },
            ].map(({ label, hi }, i) => (
              <span key={i} className={`text-[11px] font-medium ${hi ? 'text-cyan-600' : 'text-slate-600'}`}>{label}</span>
            ))}
            {publicStats && (
              <>
                <span className="text-slate-800 text-[10px] hidden sm:inline">&middot;</span>
                <span className="flex items-center gap-1 text-[11px] text-slate-600 font-medium">
                  <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse shrink-0" />
                  {(publicStats.total_scans + 500).toLocaleString()}
                  {lang === 'fr' ? ' domaines analysés' : ' domains analyzed'}
                </span>
              </>
            )}
          </motion.div>
        )}

        {/* ── Compteur de scans + CTAs contextuels ───────────────────── */}
        {scanLimits && scanLimits.type !== 'unlimited' && scanLimits.remaining !== null && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }} className="mt-4">
            {scanLimits.remaining > 0 ? (
              /* Pill normal */
              <div className="flex flex-wrap items-center justify-center gap-2">
                <div className={`flex items-center gap-1.5 text-xs px-3 py-1 rounded-full border ${
                  scanLimits.remaining === 1
                    ? 'border-orange-500/40 bg-orange-500/10 text-orange-400'
                    : 'border-slate-700/60 bg-slate-800/40 text-slate-500'
                }`}>
                  <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
                  {lang === 'fr'
                    ? `${scanLimits.remaining} scan${scanLimits.remaining > 1 ? 's' : ''} restant${scanLimits.remaining > 1 ? 's' : ''} aujourd'hui`
                    : `${scanLimits.remaining} scan${scanLimits.remaining > 1 ? 's' : ''} left today`}
                </div>
                {scanLimits.type === 'anonymous' && (
                  <button onClick={() => goRegister('scan_limit')} className="text-xs text-cyan-500 hover:text-cyan-400 transition-colors underline underline-offset-2 font-medium">
                    {lang === 'fr' ? 'Créer un compte gratuit →' : 'Create free account →'}
                  </button>
                )}
              </div>
            ) : scanLimits.type === 'anonymous' ? (
              /* 0 scan — visiteur : bandeau inline discret */
              <motion.div initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }}
                className="flex items-center gap-3 bg-sky-500/5 border border-sky-500/20 rounded-xl px-4 py-2.5">
                <span className="w-2 h-2 rounded-full bg-orange-400 shrink-0" />
                <p className="flex-1 text-xs text-slate-400 leading-snug">
                  <span className="text-slate-200 font-semibold">
                    {lang === 'fr' ? 'Scan anonyme utilisé.' : 'Anonymous scan used.'}
                  </span>
                  {' '}
                  {lang === 'fr'
                    ? 'Créez un compte gratuit pour 5 scans/jour et votre historique.'
                    : 'Create a free account for 5 scans/day and your history.'}
                </p>
                <button onClick={() => goRegister('scan_limit')}
                  className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-sky-500/15 border border-sky-500/30 text-sky-300 hover:bg-sky-500/25 transition-colors text-xs font-semibold whitespace-nowrap">
                  <UserPlus size={12} />
                  {lang === 'fr' ? 'Créer un compte →' : 'Create account →'}
                </button>
              </motion.div>
            ) : (
              /* 0 scan — free connecte : inciter a passer Starter */
              <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                className="max-w-sm mx-auto rounded-2xl overflow-hidden"
                style={{ border: '1px solid rgba(34,211,238,0.2)', background: 'linear-gradient(135deg,rgba(8,60,80,0.6) 0%,rgba(15,21,30,0.95) 100%)' }}>
                <div className="px-5 pt-5 pb-4 text-center">
                  <div className="w-8 h-8 rounded-full bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center mx-auto mb-3">
                    <Zap size={14} className="text-cyan-400" />
                  </div>
                  <p className="text-white font-bold text-sm mb-1">
                    {lang === 'fr' ? 'Limite journalière atteinte' : 'Daily limit reached'}
                  </p>
                  <p className="text-slate-400 text-xs mb-4 leading-relaxed">
                    {lang === 'fr'
                      ? 'Quota de 5 scans épuisé — réinitialisé demain. Passez Starter pour analyser sans limite.'
                      : '5-scan quota used up — resets tomorrow. Upgrade to Starter for unlimited scans.'}
                  </p>
                  <button onClick={() => openPricing('scan_limit')}
                    className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-bold transition-all"
                    style={{ background: 'linear-gradient(135deg,rgba(34,211,238,0.22),rgba(59,130,246,0.18))', border: '1px solid rgba(34,211,238,0.35)', color: '#a5f3fc' }}>
                    <Zap size={13} />
                    {lang === 'fr' ? 'Scans illimités — Starter 9,90€/mois' : 'Unlimited scans — Starter €9.90/mo'}
                    <ArrowRight size={13} />
                  </button>
                </div>
                <div className="px-5 pb-4 flex items-center justify-center gap-5">
                  {(lang === 'fr'
                    ? ['✓ Scans illimités', '✓ PDF complet', '✓ Monitoring']
                    : ['✓ Unlimited scans', '✓ Full PDF', '✓ Monitoring']
                  ).map(f => <span key={f} className="text-[10px] text-cyan-700 font-mono">{f}</span>)}
                </div>
              </motion.div>
            )}
          </motion.div>
        )}

        {/* Badges des verifications — informatifs, non cliquables */}
        {isIdle && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.35 }}
            className="flex flex-col items-center gap-2 mt-5"
          >
            <p className="text-[10px] text-slate-600 uppercase tracking-widest font-mono select-none">
              {lang === 'fr' ? 'Ce que nous analysons' : 'What we analyse'}
            </p>
            <div className="flex flex-wrap justify-center gap-2 text-xs select-none pointer-events-none">
              {([
                { c:'#c084fc', label: t('badge_headers'),
                  paths: <><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></> },
                { c:'#2dd4bf', label: t('badge_spf'),
                  paths: <><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></> },
                { c:'#22d3ee', label: t('badge_ssl'),
                  paths: <><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></> },
                { c:'#fb923c', label: t('badge_ports'),
                  paths: <><path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><circle cx="12" cy="20" r="1" fill="#fb923c"/></> },
                { c:'#4ade80', label: t('badge_tech'),
                  paths: <><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></> },
                { c:'#f87171', label: t('badge_dnsbl'),
                  paths: <><circle cx="12" cy="8" r="6"/><path d="M15.477 12.89L17 22l-5-3-5 3 1.523-9.11"/></> },
              ] as Array<{c:string,label:string,paths:ReactNode}>).map(({ c, label, paths }) => (
                <span key={label}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-slate-500 cursor-default"
                  style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}
                >
                  <svg width="11" height="11" fill="none" stroke={c} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24" style={{ opacity: 0.75, flexShrink: 0 }}>
                    {paths}
                  </svg>
                  {label}
                </span>
              ))}
            </div>
          </motion.div>
        )}

      </div>
    </header>
  );
}

export { CountUp };
