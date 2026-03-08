// ─── PageNavbar.tsx — Barre de navigation partagée (sous-pages) ───────────────
//
// Inclut : bouton ← Retour, dropdown utilisateur complet, nav links optionnels
//
import { useState, useRef, useEffect, ReactNode } from 'react';
import { ChevronLeft, ChevronDown } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../i18n/LanguageContext';
import { apiClient } from '../lib/api';

interface PageNavbarProps {
  onBack:    () => void;
  title:     string;
  icon?:     ReactNode;
  actions?:  ReactNode;
  // Navigation optionnelle vers d'autres sous-pages
  onGoClientSpace?: (tab?: string, section?: string) => void;
  onGoHistory?:     () => void;   // accepté pour compatibilité, non utilisé dans le dropdown
  onGoAdmin?:       () => void;
  onGoContact?:     () => void;
}

export default function PageNavbar({
  onBack, title, icon, actions,
  onGoClientSpace, onGoAdmin, onGoContact,
}: PageNavbarProps) {
  const { user, logout } = useAuth();
  const { lang, setLang } = useLanguage();

  const [menuOpen,        setMenuOpen]        = useState(false);
  const [pwOpen,          setPwOpen]          = useState(false);
  const [pwCurrent,       setPwCurrent]       = useState('');
  const [pwNew,           setPwNew]           = useState('');
  const [pwConfirm,       setPwConfirm]       = useState('');
  const [pwLoading,       setPwLoading]       = useState(false);
  const [pwError,         setPwError]         = useState('');
  const [pwSuccess,       setPwSuccess]       = useState(false);

  const menuRef = useRef<HTMLDivElement>(null);

  const displayName = user?.first_name ?? user?.email?.split('@')[0] ?? '';
  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const closeAll = () => setMenuOpen(false);

  const handlePwSubmit = async () => {
    if (!pwNew || !pwCurrent) { setPwError('Remplissez tous les champs'); return; }
    if (pwNew !== pwConfirm)  { setPwError('Les mots de passe ne correspondent pas'); return; }
    if (pwNew.length < 8)     { setPwError('8 caractères minimum'); return; }
    setPwLoading(true);
    setPwError('');
    try {
      await apiClient.post('/auth/change-password', { current_password: pwCurrent, new_password: pwNew });
      setPwSuccess(true);
      setTimeout(() => { setPwOpen(false); setPwSuccess(false); setPwCurrent(''); setPwNew(''); setPwConfirm(''); }, 1500);
    } catch (e: any) {
      setPwError(e?.response?.data?.detail ?? 'Erreur');
    } finally {
      setPwLoading(false);
    }
  };

  return (
    <>
      <nav
        className="sticky top-0 z-20 backdrop-blur-sm"
        style={{
          background: 'linear-gradient(180deg, rgba(22,28,36,0.97) 0%, rgba(13,17,23,0.97) 100%)',
          borderBottom: '1px solid rgba(255,255,255,0.07)',
          boxShadow: '0 2px 16px rgba(0,0,0,0.5), 0 1px 0 rgba(255,255,255,0.03) inset',
        }}
      >
        <div className="max-w-6xl mx-auto px-4 h-[52px] flex items-center gap-3">

          {/* ← Retour */}
          <button
            onClick={onBack}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/5 border border-white/6 hover:border-white/12 transition-all shrink-0 group"
            aria-label={lang === 'fr' ? 'Retour' : 'Back'}
          >
            <ChevronLeft size={14} className="group-hover:-translate-x-0.5 transition-transform" />
            <span className="text-xs font-medium hidden sm:block">
              {lang === 'fr' ? 'Retour' : 'Back'}
            </span>
          </button>

          {/* Séparateur */}
          <div className="w-px h-4 bg-white/8 shrink-0" />

          {/* Logo */}
          <button onClick={onBack} className="flex items-center shrink-0 group" aria-label="Wezea">
            <div
              className="font-black text-white leading-none group-hover:text-cyan-50 transition-colors"
              style={{ fontSize: '18px', letterSpacing: '-0.03em', fontFamily: 'var(--font-display)' }}
            >
              We<span style={{ color: 'var(--color-accent)' }}>zea</span>
            </div>
          </button>

          {/* Séparateur + breadcrumb */}
          <div className="w-px h-4 bg-white/8 shrink-0" />
          <div className="flex items-center gap-2 min-w-0 flex-1">
            {icon && (
              <div className="p-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20 shrink-0 text-cyan-400">
                {icon}
              </div>
            )}
            <span className="text-sm font-semibold text-white truncate">{title}</span>
          </div>

          {/* RIGHT */}
          <div className="flex items-center gap-2 shrink-0">

            {/* Actions contextuelles */}
            {actions}

            {/* Lang toggle */}
            <div
              className="flex overflow-hidden rounded-lg"
              style={{
                background: 'linear-gradient(180deg,#0f151e,#0b1018)',
                border: '1px solid rgba(255,255,255,0.07)',
                boxShadow: '0 2px 5px rgba(0,0,0,0.4) inset',
              }}
            >
              {(['fr', 'en'] as const).map(l => (
                <button
                  key={l}
                  onClick={() => setLang(l)}
                  className="px-2.5 py-1.5 text-xs font-mono font-bold transition-all"
                  style={
                    lang === l
                      ? { color: 'var(--color-accent)', background: 'linear-gradient(180deg,#1e2d3d,#162433)', boxShadow: '0 1px 0 rgba(255,255,255,0.06) inset' }
                      : { color: '#475569' }
                  }
                >
                  {l.toUpperCase()}
                </button>
              ))}
            </div>

            {/* User dropdown */}
            {user && (
              <div className="relative" ref={menuRef}>
                <button
                  onClick={() => setMenuOpen(v => !v)}
                  className="flex items-center gap-2 pl-1 pr-2 py-1 rounded-lg border border-white/8 bg-white/3 hover:bg-white/7 hover:border-white/14 transition-all"
                >
                  {/* Avatar */}
                  <div
                    className="w-[24px] h-[24px] rounded-md flex items-center justify-center text-[11px] font-black shrink-0"
                    style={{
                      background: user.plan === 'dev'
                        ? 'linear-gradient(135deg,rgba(167,139,250,.3),rgba(139,92,246,.1))'
                        : user.plan === 'pro'
                        ? 'linear-gradient(135deg,rgba(34,211,238,.25),rgba(34,211,238,.1))'
                        : 'linear-gradient(135deg,rgba(34,211,238,.25),rgba(34,211,238,.1))',
                      border: user.plan === 'dev'
                        ? '1px solid rgba(167,139,250,.4)'
                        : user.plan === 'pro'
                        ? '1px solid rgba(34,211,238,.35)'
                        : '1px solid rgba(34,211,238,.35)',
                      color: user.plan === 'dev' ? '#c4b5fd' : user.plan === 'pro' ? '#67e8f9' : '#67e8f9',
                    }}
                  >
                    {(user.first_name ?? user.email)[0].toUpperCase()}
                  </div>
                  <span className="hidden sm:block text-[11px] font-semibold text-slate-200 max-w-[80px] truncate leading-none">
                    {displayName}
                  </span>
                  <ChevronDown size={10} className={`text-slate-500 transition-transform ${menuOpen ? 'rotate-180' : ''}`} />
                </button>

                {/* Dropdown */}
                {menuOpen && (
                  <div
                    className="absolute right-0 top-full mt-2 w-56 rounded-xl z-50 overflow-hidden"
                    style={{
                      background: 'linear-gradient(180deg,#1a2235,#121926)',
                      border: '1px solid rgba(255,255,255,0.08)',
                      boxShadow: '0 12px 40px rgba(0,0,0,0.8), 0 1px 0 rgba(255,255,255,0.05) inset',
                    }}
                  >
                    {/* Header */}
                    <div className="px-3 pt-3 pb-2.5 border-b border-white/6">
                      <p className="text-[11px] text-slate-500 font-mono truncate">{user.email}</p>
                      <span
                        className="text-[9px] font-bold font-mono px-1.5 py-0.5 rounded mt-1 inline-block"
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

                    {/* Navigation */}
                    <div className="pt-1.5 pb-1 border-b border-white/6">
                      <p className="px-3 pb-1 text-[9px] font-mono text-slate-600 uppercase tracking-widest">
                        {lang === 'fr' ? 'Navigation' : 'Navigate'}
                      </p>
                      {onGoClientSpace && (
                        <DropItem
                          icon={<svg width="10" height="10" fill="none" stroke="#22d3ee" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>}
                          iconBg="linear-gradient(150deg,rgba(34,211,238,.18),rgba(34,211,238,.05))"
                          iconBorder="1px solid rgba(34,211,238,.22)"
                          label={lang === 'fr' ? 'Mon espace' : 'My space'}
                          onClick={() => { closeAll(); onGoClientSpace(); }}
                        />
                      )}
                      {!user.google_id && (
                        <DropItem
                          icon={<svg width="10" height="10" fill="none" stroke="#22d3ee" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>}
                          iconBg="linear-gradient(150deg,rgba(34,211,238,.18),rgba(34,211,238,.05))"
                          iconBorder="1px solid rgba(34,211,238,.22)"
                          label={lang === 'fr' ? 'Changer le mot de passe' : 'Change password'}
                          onClick={() => { closeAll(); setPwOpen(true); }}
                        />
                      )}
                    </div>

                    {/* Aide + Admin */}
                    <div className="pt-1.5 pb-1 border-b border-white/6">
                      {onGoContact && (
                        <DropItem
                          icon={<svg width="10" height="10" fill="none" stroke="#60a5fa" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>}
                          iconBg="linear-gradient(150deg,rgba(96,165,250,.18),rgba(96,165,250,.05))"
                          iconBorder="1px solid rgba(96,165,250,.22)"
                          label={lang === 'fr' ? 'Contacter le support' : 'Contact support'}
                          onClick={() => { closeAll(); onGoContact(); }}
                        />
                      )}
                      {user.is_admin && onGoAdmin && (
                        <DropItem
                          icon={<svg width="10" height="10" fill="none" stroke="#94a3b8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>}
                          iconBg="linear-gradient(150deg,rgba(148,163,184,.18),rgba(148,163,184,.05))"
                          iconBorder="1px solid rgba(148,163,184,.22)"
                          label="Admin"
                          onClick={() => { closeAll(); onGoAdmin(); }}
                        />
                      )}
                    </div>

                    {/* Déconnexion */}
                    <div className="py-1">
                      <button
                        onClick={() => { closeAll(); logout(); }}
                        className="w-full text-left px-3 py-2 text-xs text-red-400 hover:bg-red-500/8 hover:text-red-300 transition flex items-center gap-2.5"
                      >
                        <span className="w-[18px] h-[18px] rounded-[5px] shrink-0 inline-flex items-center justify-center" style={{ background: 'linear-gradient(150deg,rgba(248,113,113,.15),rgba(248,113,113,.05))', border: '1px solid rgba(248,113,113,.22)' }}>
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
      </nav>

      {/* Modale changement de mot de passe */}
      {pwOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(6px)' }}
          onClick={e => { if (e.target === e.currentTarget) setPwOpen(false); }}
        >
          <div
            className="w-full max-w-sm rounded-2xl p-6"
            style={{ background: 'linear-gradient(180deg,#1a2235,#121926)', border: '1px solid rgba(255,255,255,0.08)' }}
          >
            <h2 className="text-white font-bold text-sm mb-4">
              {lang === 'fr' ? 'Changer le mot de passe' : 'Change password'}
            </h2>
            <div className="space-y-3">
              {[
                { label: lang === 'fr' ? 'Mot de passe actuel' : 'Current password', val: pwCurrent, set: setPwCurrent },
                { label: lang === 'fr' ? 'Nouveau mot de passe' : 'New password', val: pwNew, set: setPwNew },
                { label: lang === 'fr' ? 'Confirmer' : 'Confirm', val: pwConfirm, set: setPwConfirm },
              ].map(f => (
                <input
                  key={f.label}
                  type="password"
                  placeholder={f.label}
                  value={f.val}
                  onChange={e => f.set(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-cyan-500 transition"
                />
              ))}
              {pwError && <p className="text-red-400 text-xs">{pwError}</p>}
              {pwSuccess && <p className="text-emerald-400 text-xs">✓ {lang === 'fr' ? 'Mot de passe modifié' : 'Password changed'}</p>}
              <div className="flex gap-2 pt-1">
                <button
                  onClick={() => { setPwOpen(false); setPwError(''); setPwCurrent(''); setPwNew(''); setPwConfirm(''); }}
                  className="flex-1 py-2 rounded-lg text-xs text-slate-400 border border-slate-700 hover:bg-white/5 transition"
                >
                  {lang === 'fr' ? 'Annuler' : 'Cancel'}
                </button>
                <button
                  onClick={handlePwSubmit}
                  disabled={pwLoading}
                  className="flex-1 py-2 rounded-lg text-xs font-bold text-slate-900 bg-cyan-400 hover:bg-cyan-300 disabled:opacity-50 transition"
                >
                  {pwLoading ? '…' : (lang === 'fr' ? 'Modifier' : 'Save')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// ─── Helper : item de dropdown ─────────────────────────────────────────────────

function DropItem({
  icon, iconBg, iconBorder, label, onClick,
}: {
  icon: ReactNode;
  iconBg: string;
  iconBorder: string;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left px-3 py-2 text-xs text-slate-400 hover:bg-white/5 hover:text-slate-200 transition flex items-center gap-2.5"
    >
      <span
        className="w-[18px] h-[18px] rounded-[5px] shrink-0 inline-flex items-center justify-center"
        style={{ background: iconBg, border: iconBorder }}
      >
        {icon}
      </span>
      {label}
    </button>
  );
}
