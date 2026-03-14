// ─── DashboardNavbar.tsx — Navigation bar extracted from Dashboard ────────────
//
// Main nav bar: logo, navigation links, language toggle, login/register/account dropdown
// Sub-bar: domain display, "New scan" button, "Download PDF" button
//
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Zap, BookOpen, ShieldCheck, RotateCcw, FileDown } from 'lucide-react';
import WezeaLogo from './WezeaLogo';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../i18n/LanguageContext';
import type { ScanStatus } from '../types/scanner';
import type { ScanResult } from '../types/scanner';

// ── Props ────────────────────────────────────────────────────────────────────

export interface DashboardNavbarProps {
  /** Current scanner status — controls sub-bar visibility */
  scannerStatus: ScanStatus;
  /** Current scan result — controls PDF download button visibility */
  scannerResult: ScanResult | null;

  /** Reset scan — logo click + "New scan" button */
  onReset: () => void;
  /** Open the email-capture / PDF download modal */
  onOpenPdfModal: () => void;
  /** Open pricing modal (called with analytics source) */
  onOpenPricing: (source: 'nav') => void;
  /** Open the change-password modal */
  onOpenPasswordModal: () => void;

  // Analytics-wrapped navigation helpers
  goLogin:    (source: 'nav') => void;
  goRegister: (source: 'nav') => void;
}

// ── Component ────────────────────────────────────────────────────────────────

export default function DashboardNavbar({
  scannerStatus,
  scannerResult,
  onReset,
  onOpenPdfModal,
  onOpenPricing,
  onOpenPasswordModal,
  goLogin,
  goRegister,
}: DashboardNavbarProps) {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { lang, setLang } = useLanguage();

  const [userMenuOpen, setUserMenuOpen] = useState(false);

  const isIdle     = scannerStatus === 'idle';
  const isScanning = scannerStatus === 'scanning';
  const isSuccess  = scannerStatus === 'success';

  return (
    <nav
      className="sticky top-0 z-20 backdrop-blur-sm"
      style={{
        background: 'linear-gradient(180deg, rgba(22,28,36,0.97) 0%, rgba(13,17,23,0.97) 100%)',
        borderBottom: '1px solid rgba(255,255,255,0.07)',
        boxShadow: '0 4px 24px rgba(0,0,0,0.6), 0 1px 0 rgba(255,255,255,0.03) inset',
      }}
    >
      {/* ── Main bar ── */}
      <div className="max-w-6xl mx-auto px-4 h-[52px] flex items-center gap-4">

        {/* LEFT — Logo (cliquable → retour accueil) */}
        <button
          onClick={onReset}
          className="shrink-0 group"
          aria-label="Retour à l'accueil"
        >
          <WezeaLogo size="md" showSub className="group-hover:opacity-90 transition-opacity" />
        </button>

        {/* CENTER — Navigation principale */}
        <div className="hidden md:flex items-center gap-1 justify-start ml-6">

          {/* CTA upgrade — Free connecté uniquement */}
          {user && user.plan === 'free' && (
            <button
              onClick={() => onOpenPricing('nav')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-cyan-300 bg-cyan-500/8 border border-cyan-500/20 hover:bg-cyan-500/15 hover:border-cyan-500/35 transition-all"
            >
              <Zap size={11} />
              {lang === 'fr' ? 'Passer Starter' : 'Upgrade'}
            </button>
          )}

          {/* Blog — toujours visible, traitement légèrement plus visible */}
          <a
            href="/blog/"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:text-white hover:bg-white/5 border border-transparent hover:border-white/8 transition-all"
          >
            <BookOpen size={12} />
            Blog
          </a>

          {/* Conformité NIS2 — lien vers la landing page */}
          <button
            onClick={() => navigate('/conformite-nis2')}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-white/4 transition-all"
          >
            <ShieldCheck size={12} />
            {lang === 'fr' ? 'NIS2 & RGPD' : 'NIS2 & GDPR'}
          </button>

        </div>

        {/* RIGHT — Lang + compte */}
        <div className="flex items-center gap-2.5 shrink-0 ml-auto">

          {/* Lang toggle */}
          <div
            className="flex overflow-hidden rounded-lg"
            style={{ background: 'linear-gradient(180deg,#0f151e,#0b1018)', border: '1px solid rgba(255,255,255,0.07)', boxShadow: '0 2px 5px rgba(0,0,0,0.4) inset' }}
          >
            <button
              onClick={() => setLang('fr')}
              className="px-2.5 py-1.5 text-xs font-mono font-bold transition-all"
              style={lang === 'fr'
                ? { color: 'var(--color-accent)', background: 'linear-gradient(180deg,#1e2d3d,#162433)', boxShadow: '0 1px 0 rgba(255,255,255,0.06) inset' }
                : { color: '#475569' }
              }
            >FR</button>
            <button
              onClick={() => setLang('en')}
              className="px-2.5 py-1.5 text-xs font-mono font-bold transition-all"
              style={lang === 'en'
                ? { color: 'var(--color-accent)', background: 'linear-gradient(180deg,#1e2d3d,#162433)', boxShadow: '0 1px 0 rgba(255,255,255,0.06) inset' }
                : { color: '#475569' }
              }
            >EN</button>
          </div>

          {/* Séparateur */}
          <div className="w-px h-4 bg-white/7 shrink-0" />

          {/* Compte — visiteur */}
          {!user && (
            <>
              <button
                onClick={() => goLogin('nav')}
                className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 border border-white/8 hover:text-slate-200 hover:bg-white/5 transition-all"
              >
                {lang === 'fr' ? 'Connexion' : 'Sign in'}
              </button>
              <button
                onClick={() => goRegister('nav')}
                className="sku-btn-primary px-3 py-1.5 rounded-lg text-xs hidden sm:block"
              >
                {lang === 'fr' ? 'Créer un compte' : 'Sign up'}
              </button>
            </>
          )}

          {/* Compte — connecté : avatar + dropdown */}
          {user && (
            <div className="relative">
              <button
                onClick={() => setUserMenuOpen(v => !v)}
                className="flex items-center gap-2 pl-1 pr-2.5 py-1 rounded-lg border border-white/8 bg-white/3 hover:bg-white/7 hover:border-white/14 transition-all"
              >
                <div
                  className="w-[26px] h-[26px] rounded-md flex items-center justify-center text-[11px] font-black shrink-0"
                  style={{
                    background: user.plan === 'dev'
                      ? 'linear-gradient(135deg,rgba(167,139,250,.3),rgba(139,92,246,.1))'
                      : user.plan === 'pro'
                      ? 'linear-gradient(135deg,rgba(34,211,238,.25),rgba(34,211,238,.1))'
                      : 'linear-gradient(135deg,rgba(34,211,238,.25),rgba(34,211,238,.1))',
                    border: user.plan === 'dev'
                      ? '1px solid rgba(167,139,250,.4)'
                      : '1px solid rgba(34,211,238,.35)',
                    color: user.plan === 'dev' ? '#c4b5fd' : '#67e8f9',
                  }}
                >
                  {(user.first_name ?? user.email)[0].toUpperCase()}
                </div>
                <div className="hidden sm:flex items-center gap-1.5">
                  <span className="text-[11.5px] font-semibold text-slate-200 leading-none max-w-[80px] truncate">
                    {user.first_name ?? user.email.split('@')[0]}
                  </span>
                  <span
                    className="text-[9px] font-bold font-mono px-1.5 py-0.5 rounded shrink-0"
                    style={
                      user.plan === 'dev'
                        ? { color: '#a78bfa', background: 'rgba(167,139,250,.12)', border: '1px solid rgba(167,139,250,.25)' }
                        : user.plan === 'pro'
                        ? { color: '#22d3ee', background: 'rgba(34,211,238,.1)', border: '1px solid rgba(34,211,238,.25)' }
                        : user.plan === 'starter'
                        ? { color: '#22d3ee', background: 'rgba(34,211,238,.1)', border: '1px solid rgba(34,211,238,.25)' }
                        : { color: '#64748b', background: 'rgba(100,116,139,.1)', border: '1px solid rgba(100,116,139,.2)' }
                    }
                  >
                    {user.plan === 'dev' ? 'DEV' : user.plan === 'pro' ? 'PRO' : user.plan === 'starter' ? 'STARTER' : (lang === 'fr' ? 'GRATUIT' : 'FREE')}
                  </span>
                </div>
                <svg width="10" height="10" fill="none" stroke="#475569" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24" className="ml-0.5"><polyline points="6 9 12 15 18 9"/></svg>
              </button>

              {/* Dropdown */}
              {userMenuOpen && (
                <div
                  className="absolute right-0 top-full mt-2 w-52 rounded-xl z-50 overflow-hidden"
                  style={{ background: 'linear-gradient(180deg,#1a2235,#121926)', border: '1px solid rgba(255,255,255,0.08)', boxShadow: '0 12px 40px rgba(0,0,0,0.8), 0 1px 0 rgba(255,255,255,0.05) inset' }}
                >
                  {/* Header */}
                  <div className="px-3 pt-3 pb-2.5 border-b border-white/6">
                    <p className="text-[11px] text-slate-500 font-mono truncate">{user.email}</p>
                  </div>

                  {/* Section Navigation */}
                  <div className="pt-1.5 pb-1">
                    <p className="px-3 pb-1 text-[9px] font-mono text-slate-600 uppercase tracking-widest">{lang === 'fr' ? 'Navigation' : 'Navigate'}</p>
                    <button
                      onClick={() => { setUserMenuOpen(false); navigate('/history'); }}
                      className="w-full text-left px-3 py-2 text-xs text-slate-400 hover:bg-white/5 hover:text-slate-200 transition flex items-center gap-2.5"
                    >
                      <span className="w-[18px] h-[18px] rounded-[5px] shrink-0 inline-flex items-center justify-center" style={{background:'linear-gradient(150deg,rgba(34,211,238,.18),rgba(34,211,238,.05))',border:'1px solid rgba(34,211,238,.22)'}}>
                        <svg width="10" height="10" fill="none" stroke="#22d3ee" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><polyline points="12 8 12 12 14 14"/><circle cx="12" cy="12" r="9"/></svg>
                      </span>
                      {lang === 'fr' ? 'Historique' : 'History'}
                    </button>
                    <button
                      onClick={() => { setUserMenuOpen(false); navigate('/espace-client'); }}
                      className="w-full text-left px-3 py-2 text-xs text-slate-400 hover:bg-white/5 hover:text-slate-200 transition flex items-center gap-2.5"
                    >
                      <span className="w-[18px] h-[18px] rounded-[5px] shrink-0 inline-flex items-center justify-center" style={{background:'linear-gradient(150deg,rgba(34,211,238,.18),rgba(34,211,238,.05))',border:'1px solid rgba(34,211,238,.22)'}}>
                        <svg width="10" height="10" fill="none" stroke="#22d3ee" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
                      </span>
                      {lang === 'fr' ? 'Mon espace' : 'My space'}
                    </button>
                    {!user.google_id && (
                      <button
                        onClick={() => { setUserMenuOpen(false); onOpenPasswordModal(); }}
                        className="w-full text-left px-3 py-2 text-xs text-slate-400 hover:bg-white/5 hover:text-slate-200 transition flex items-center gap-2.5"
                      >
                        <span className="w-[18px] h-[18px] rounded-[5px] shrink-0 inline-flex items-center justify-center" style={{background:'linear-gradient(150deg,rgba(34,211,238,.18),rgba(34,211,238,.05))',border:'1px solid rgba(34,211,238,.22)'}}>
                          <svg width="10" height="10" fill="none" stroke="#22d3ee" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                        </span>
                        {lang === 'fr' ? 'Changer le mot de passe' : 'Change password'}
                      </button>
                    )}
                  </div>

                  {/* Section Aide */}
                  <div className="border-t border-white/6 pt-1.5 pb-1">
                    <p className="px-3 pb-1 text-[9px] font-mono text-slate-600 uppercase tracking-widest">{lang === 'fr' ? 'Aide' : 'Help'}</p>
                    <button
                      onClick={() => { setUserMenuOpen(false); navigate('/contact'); }}
                      className="w-full text-left px-3 py-2 text-xs text-slate-400 hover:bg-white/5 hover:text-slate-200 transition flex items-center gap-2.5"
                    >
                      <span className="w-[18px] h-[18px] rounded-[5px] shrink-0 inline-flex items-center justify-center" style={{background:'linear-gradient(150deg,rgba(96,165,250,.18),rgba(96,165,250,.05))',border:'1px solid rgba(96,165,250,.22)'}}>
                        <svg width="10" height="10" fill="none" stroke="#60a5fa" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                      </span>
                      {lang === 'fr' ? 'Contacter le support' : 'Contact support'}
                    </button>
                    {user?.is_admin && (
                      <button
                        onClick={() => { setUserMenuOpen(false); navigate('/admin'); }}
                        className="w-full text-left px-3 py-2 text-xs text-slate-400 hover:bg-white/5 hover:text-slate-200 transition flex items-center gap-2.5"
                      >
                        <span className="w-[18px] h-[18px] rounded-[5px] shrink-0 inline-flex items-center justify-center" style={{background:'linear-gradient(150deg,rgba(148,163,184,.18),rgba(148,163,184,.05))',border:'1px solid rgba(148,163,184,.22)'}}>
                          <svg width="10" height="10" fill="none" stroke="#94a3b8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                        </span>
                        Admin
                      </button>
                    )}
                  </div>

                  {/* Déconnexion */}
                  <div className="border-t border-white/6 py-1">
                    <button
                      onClick={() => { setUserMenuOpen(false); logout(); }}
                      className="w-full text-left px-3 py-2 text-xs text-red-400 hover:bg-red-500/8 hover:text-red-300 transition flex items-center gap-2.5"
                    >
                      <span className="w-[18px] h-[18px] rounded-[5px] shrink-0 inline-flex items-center justify-center" style={{background:'linear-gradient(150deg,rgba(248,113,113,.15),rgba(248,113,113,.05))',border:'1px solid rgba(248,113,113,.22)'}}>
                        <svg width="10" height="10" fill="none" stroke="#f87171" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
                      </span>
                      {lang === 'fr' ? 'Déconnexion' : 'Sign out'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Sous-barre contextuelle (actions scan) — visible après scan seulement ── */}
      {!isIdle && (
        <div
          className="border-t flex items-center gap-2 px-4 py-1.5 max-w-6xl mx-auto"
          style={{ borderColor: 'rgba(255,255,255,0.05)' }}
        >
          <span className="flex-1 text-[11px] text-slate-600 font-mono truncate">
            {isSuccess && scannerResult
              ? scannerResult.domain
              : isScanning
              ? (lang === 'fr' ? 'Scan en cours…' : 'Scanning…')
              : (lang === 'fr' ? 'Erreur de scan' : 'Scan error')}
          </span>
          <button
            onClick={onReset}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium text-slate-500 hover:text-slate-300 hover:bg-white/5 border border-white/6 transition-all"
          >
            <RotateCcw size={10} />
            {lang === 'fr' ? 'Nouveau scan' : 'New scan'}
          </button>
          {isSuccess && scannerResult && (
            <motion.button
              initial={{ opacity: 0, x: 6 }}
              animate={{ opacity: 1, x: 0 }}
              onClick={() => onOpenPdfModal()}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-semibold text-cyan-300 bg-cyan-500/10 border border-cyan-500/25 hover:bg-cyan-500/18 transition-all"
            >
              <FileDown size={10} />
              {lang === 'fr' ? 'Télécharger PDF' : 'Download PDF'}
            </motion.button>
          )}
        </div>
      )}
    </nav>
  );
}
