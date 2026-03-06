// ─── ProfileModal — profil, sécurité, clé API, suppression de compte ──────────
import { useState, useEffect, useCallback, FormEvent, ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X, Trash2, Save, AlertTriangle, CheckCircle,
  Lock, Copy, RefreshCw, Eye, EyeOff, KeyRound,
  User, ShieldCheck, Mail,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../i18n/LanguageContext';
import { apiClient } from '../lib/api';

interface Props {
  open: boolean;
  onClose: () => void;
}

type Tab = 'profile' | 'security' | 'api' | 'danger';

// ─── SkuIcon — boîte d'icône skeuomorphique (pattern Dashboard) ───────────────
// Usage : <SkuIcon color="#22d3ee" size={36}><User size={16} /></SkuIcon>
// color  : couleur hex de l'icône (ex. '#22d3ee', '#a78bfa', '#f87171')
// size   : taille du carré (défaut 36 — pour 32 ajuster borderRadius si besoin)
function SkuIcon({
  children, color, size = 36,
}: { children: ReactNode; color: string; size?: number }) {
  const r = Math.round(size * 0.28); // border-radius proportionnel
  return (
    <div
      className="shrink-0 flex items-center justify-center relative overflow-hidden"
      style={{
        width: size, height: size, borderRadius: r,
        background: `linear-gradient(150deg, ${color}30 0%, ${color}0d 100%)`,
        border: `1px solid ${color}40`,
        boxShadow: `0 4px 16px ${color}22, 0 1px 3px rgba(0,0,0,0.4), inset 0 1px 0 ${color}30, inset 0 -1px 0 rgba(0,0,0,0.3)`,
      }}
    >
      {/* reflet supérieur */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{ borderRadius: r, background: 'linear-gradient(180deg,rgba(255,255,255,0.07) 0%,transparent 50%)' }}
      />
      {children}
    </div>
  );
}

// ─── SectionHeader — en-tête de section pour chaque onglet ───────────────────
function SectionHeader({ icon, title, sub }: { icon: ReactNode; title: string; sub?: string }) {
  return (
    <div className="flex items-center gap-3 pb-4" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
      {icon}
      <div>
        <p className="text-white font-semibold text-sm leading-tight"
          style={{ fontFamily: 'var(--font-display)', letterSpacing: '-0.01em' }}>
          {title}
        </p>
        {sub && <p className="text-slate-500 text-xs mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

// ─── Input helper ─────────────────────────────────────────────────────────────
function Input({
  type = 'text', value, onChange, placeholder, required, maxLength, readOnly,
}: {
  type?: string; value: string; onChange?: (v: string) => void;
  placeholder?: string; required?: boolean; maxLength?: number; readOnly?: boolean;
}) {
  return (
    <input
      type={type} value={value}
      onChange={onChange ? e => onChange(e.target.value) : undefined}
      placeholder={placeholder} required={required} maxLength={maxLength} readOnly={readOnly}
      className={`w-full rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-slate-600 focus:outline-none transition ${readOnly ? 'text-slate-400 cursor-default' : ''}`}
      style={{
        background: readOnly ? 'rgba(0,0,0,0.25)' : 'rgba(255,255,255,0.04)',
        border: `1px solid ${readOnly ? 'rgba(255,255,255,0.05)' : 'rgba(255,255,255,0.08)'}`,
        boxShadow: readOnly ? 'none' : '0 2px 6px rgba(0,0,0,0.3) inset',
      }}
      onFocus={readOnly ? undefined : e => (e.currentTarget.style.borderColor = 'rgba(34,211,238,0.4)')}
      onBlur={readOnly ? undefined : e => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)')}
    />
  );
}

// ─── PasswordInput — avec toggle visibilité ────────────────────────────────────
function PasswordInput({
  value, onChange, placeholder, required, focusColor = 'rgba(34,211,238,0.4)',
}: {
  value: string; onChange: (v: string) => void;
  placeholder?: string; required?: boolean; focusColor?: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <input
        type={show ? 'text' : 'password'} value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder ?? '••••••••'} required={required}
        className="w-full rounded-xl px-4 py-2.5 pr-10 text-sm text-white placeholder:text-slate-600 focus:outline-none transition"
        style={{
          background: 'rgba(255,255,255,0.04)',
          border: '1px solid rgba(255,255,255,0.08)',
          boxShadow: '0 2px 6px rgba(0,0,0,0.3) inset',
        }}
        onFocus={e => (e.currentTarget.style.borderColor = focusColor)}
        onBlur={e => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)')}
      />
      <button
        type="button" onClick={() => setShow(s => !s)}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-600 hover:text-slate-300 transition"
        tabIndex={-1}
      >
        {show ? <EyeOff size={14} /> : <Eye size={14} />}
      </button>
    </div>
  );
}

// ─── Feedback rows ────────────────────────────────────────────────────────────
function ErrMsg({ msg }: { msg: string }) {
  return (
    <p className="text-red-400 text-xs flex items-center gap-1.5">
      <AlertTriangle size={13} />{msg}
    </p>
  );
}
function OkMsg({ msg }: { msg: string }) {
  return (
    <p className="text-emerald-400 text-xs flex items-center gap-1.5">
      <CheckCircle size={13} />{msg}
    </p>
  );
}

// ─── Main component ────────────────────────────────────────────────────────────
export function ProfileModal({ open, onClose }: Props) {
  const { user, updateProfile, deleteAccount, refreshUser } = useAuth();
  const { lang } = useLanguage();
  const isGoogle = Boolean(user?.google_id);

  // ── Profile tab ─────────────────────────────────────────────────────────────
  const [firstName, setFirstName] = useState('');
  const [lastName,  setLastName]  = useState('');
  const [saving,    setSaving]    = useState(false);
  const [saveOk,    setSaveOk]    = useState(false);
  const [saveErr,   setSaveErr]   = useState('');

  // ── Security tab ────────────────────────────────────────────────────────────
  const [secMode,     setSecMode]     = useState<'password' | 'email'>('password');
  const [curPwd,      setCurPwd]      = useState('');
  const [newPwd,      setNewPwd]      = useState('');
  const [confirmPwd,  setConfirmPwd]  = useState('');
  const [pwdOk,       setPwdOk]       = useState(false);
  const [pwdErr,      setPwdErr]      = useState('');
  const [pwdSaving,   setPwdSaving]   = useState(false);
  const [newEmail,    setNewEmail]    = useState('');
  const [emailPwd,    setEmailPwd]    = useState('');
  const [emailOk,     setEmailOk]     = useState(false);
  const [emailErr,    setEmailErr]    = useState('');
  const [emailSaving, setEmailSaving] = useState(false);

  // ── API tab ──────────────────────────────────────────────────────────────────
  const [apiKey,       setApiKey]       = useState<string | null>(null);
  const [apiVisible,   setApiVisible]   = useState(false);
  const [apiCopied,    setApiCopied]    = useState(false);
  const [apiRegen,     setApiRegen]     = useState(false);
  const [apiRegenOk,   setApiRegenOk]   = useState(false);

  // ── Delete tab ───────────────────────────────────────────────────────────────
  const [delPassword, setDelPassword] = useState('');
  const [delConfirm,  setDelConfirm]  = useState('');
  const [deleting,    setDeleting]    = useState(false);
  const [delErr,      setDelErr]      = useState('');

  // ── Active tab ───────────────────────────────────────────────────────────────
  const [tab, setTab] = useState<Tab>('profile');

  const resetAll = useCallback(() => {
    if (!user) return;
    setFirstName(user.first_name ?? '');
    setLastName(user.last_name  ?? '');
    setSaveOk(false); setSaveErr('');
    setSecMode('password');
    setCurPwd(''); setNewPwd(''); setConfirmPwd('');
    setPwdOk(false); setPwdErr('');
    setNewEmail(''); setEmailPwd('');
    setEmailOk(false); setEmailErr('');
    setApiKey(user.api_key ?? null);
    setApiVisible(false); setApiCopied(false); setApiRegenOk(false);
    setDelPassword(''); setDelConfirm(''); setDelErr('');
    setTab('profile');
  }, [user]);

  useEffect(() => { if (open) resetAll(); }, [open, resetAll]);

  // ── Handlers ─────────────────────────────────────────────────────────────────

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    setSaving(true); setSaveErr(''); setSaveOk(false);
    try {
      await updateProfile(firstName.trim() || null, lastName.trim() || null);
      setSaveOk(true);
      setTimeout(() => setSaveOk(false), 3000);
    } catch (err: any) {
      setSaveErr(err?.response?.data?.detail || err?.message || 'Erreur');
    } finally { setSaving(false); }
  }

  async function handleChangePassword(e: FormEvent) {
    e.preventDefault();
    if (newPwd !== confirmPwd) {
      setPwdErr(lang === 'fr' ? 'Les mots de passe ne correspondent pas' : 'Passwords do not match');
      return;
    }
    setPwdSaving(true); setPwdErr(''); setPwdOk(false);
    try {
      await apiClient.post('/auth/change-password', { current_password: curPwd, new_password: newPwd });
      setPwdOk(true);
      setCurPwd(''); setNewPwd(''); setConfirmPwd('');
      setTimeout(() => setPwdOk(false), 3500);
    } catch (err: any) {
      setPwdErr(err?.response?.data?.detail || err?.message || 'Erreur');
    } finally { setPwdSaving(false); }
  }

  async function handleChangeEmail(e: FormEvent) {
    e.preventDefault();
    setEmailSaving(true); setEmailErr(''); setEmailOk(false);
    try {
      await apiClient.post('/auth/change-email', { new_email: newEmail, current_password: emailPwd });
      setEmailOk(true);
      if (refreshUser) await refreshUser();
      setNewEmail(''); setEmailPwd('');
      setTimeout(() => setEmailOk(false), 3500);
    } catch (err: any) {
      setEmailErr(err?.response?.data?.detail || err?.message || 'Erreur');
    } finally { setEmailSaving(false); }
  }

  async function handleCopyApiKey() {
    if (!apiKey) return;
    await navigator.clipboard.writeText(apiKey);
    setApiCopied(true);
    setTimeout(() => setApiCopied(false), 2500);
  }

  async function handleRegenApiKey() {
    setApiRegen(true); setApiRegenOk(false);
    try {
      const { data } = await apiClient.post<{ api_key: string }>('/auth/api-key/regenerate');
      setApiKey(data.api_key);
      setApiVisible(true);
      setApiRegenOk(true);
      setTimeout(() => setApiRegenOk(false), 3500);
    } catch { /* ignore */ } finally { setApiRegen(false); }
  }

  async function handleDelete(e: FormEvent) {
    e.preventDefault();
    if (delConfirm !== 'SUPPRIMER' && delConfirm !== 'DELETE') {
      setDelErr(lang === 'fr' ? 'Tapez SUPPRIMER pour confirmer' : 'Type DELETE to confirm');
      return;
    }
    setDeleting(true); setDelErr('');
    try {
      await deleteAccount(delPassword);
    } catch (err: any) {
      setDelErr(err?.response?.data?.detail || err?.message || 'Erreur');
      setDeleting(false);
    }
  }

  if (!open) return null;

  const isPro = user?.plan === 'pro';

  const tabs: Array<{ id: Tab; label: string; color: string; icon: ReactNode }> = [
    { id: 'profile',  color: '#22d3ee', icon: <User       size={12} className="text-cyan-300"   />, label: lang === 'fr' ? 'Infos'     : 'Info'     },
    { id: 'security', color: '#818cf8', icon: <ShieldCheck size={12} className="text-indigo-300"/>, label: lang === 'fr' ? 'Sécurité'  : 'Security' },
    { id: 'api',      color: '#a78bfa', icon: <KeyRound   size={12} className="text-violet-300" />, label: 'API'                                     },
    { id: 'danger',   color: '#f87171', icon: <Trash2     size={12} className="text-red-300"    />, label: lang === 'fr' ? 'Supprimer' : 'Delete'    },
  ];

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* Modal */}
          <motion.div
            key="modal"
            initial={{ opacity: 0, scale: 0.95, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 16 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none"
          >
            <div
              className="w-full max-w-md pointer-events-auto rounded-2xl overflow-hidden"
              style={{
                background: 'linear-gradient(180deg,#0f151e,#0b1018)',
                border: '1px solid rgba(255,255,255,0.08)',
                boxShadow: '0 24px 80px rgba(0,0,0,0.8), 0 1px 0 rgba(255,255,255,0.06) inset',
              }}
            >

              {/* ── Header ─────────────────────────────────────────────────── */}
              <div
                className="flex items-center justify-between px-6 py-4"
                style={{ borderBottom: '1px solid rgba(255,255,255,0.07)' }}
              >
                <div className="flex items-center gap-3">
                  {/* Avatar skeuomorphique — initiales + couleur selon plan */}
                  <div className="relative shrink-0">
                    <div
                      className="w-10 h-10 rounded-xl flex items-center justify-center text-sm font-black"
                      style={{
                        background: user?.plan === 'pro'
                          ? 'linear-gradient(145deg,rgba(167,139,250,0.35) 0%,rgba(139,92,246,0.15) 100%)'
                          : user?.plan === 'starter'
                          ? 'linear-gradient(145deg,rgba(34,211,238,0.3) 0%,rgba(6,182,212,0.12) 100%)'
                          : 'linear-gradient(145deg,rgba(100,116,139,0.25) 0%,rgba(71,85,105,0.1) 100%)',
                        border: user?.plan === 'pro'
                          ? '1px solid rgba(167,139,250,0.45)'
                          : user?.plan === 'starter'
                          ? '1px solid rgba(34,211,238,0.4)'
                          : '1px solid rgba(100,116,139,0.3)',
                        boxShadow: user?.plan === 'pro'
                          ? '0 2px 12px rgba(139,92,246,0.25), 0 1px 0 rgba(255,255,255,0.08) inset'
                          : user?.plan === 'starter'
                          ? '0 2px 12px rgba(34,211,238,0.2), 0 1px 0 rgba(255,255,255,0.08) inset'
                          : '0 2px 8px rgba(0,0,0,0.4), 0 1px 0 rgba(255,255,255,0.05) inset',
                        color: user?.plan === 'pro' ? '#c4b5fd' : user?.plan === 'starter' ? '#67e8f9' : '#94a3b8',
                      }}
                    >
                      {((user?.first_name ?? user?.email ?? '?')[0]).toUpperCase()}
                    </div>
                    {/* Badge plan */}
                    <div
                      className="absolute -bottom-1 -right-1 text-[8px] font-bold font-mono px-1 rounded leading-tight"
                      style={
                        user?.plan === 'pro'
                          ? { color: '#a78bfa', background: 'rgba(15,10,28,0.95)', border: '1px solid rgba(167,139,250,0.35)' }
                          : user?.plan === 'starter'
                          ? { color: '#22d3ee', background: 'rgba(10,18,28,0.95)', border: '1px solid rgba(34,211,238,0.3)' }
                          : { color: '#64748b', background: 'rgba(10,15,20,0.95)', border: '1px solid rgba(100,116,139,0.25)' }
                      }
                    >
                      {user?.plan === 'pro' ? 'PRO' : user?.plan === 'starter' ? 'STR' : 'FREE'}
                    </div>
                  </div>

                  <div>
                    <h2
                      className="text-white font-bold text-base leading-tight"
                      style={{ fontFamily: 'var(--font-display)', letterSpacing: '-0.02em' }}
                    >
                      {user?.first_name
                        ? `${user.first_name}${user.last_name ? ' ' + user.last_name : ''}`
                        : (lang === 'fr' ? 'Mon profil' : 'My profile')}
                    </h2>
                    <p className="text-slate-500 text-xs mt-0.5">{user?.email}</p>
                  </div>
                </div>

                <button
                  onClick={onClose}
                  className="text-slate-600 hover:text-slate-300 transition p-1 rounded-lg hover:bg-slate-800"
                >
                  <X size={18} />
                </button>
              </div>

              {/* ── Tabs ───────────────────────────────────────────────────── */}
              <div className="flex" style={{ borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
                {tabs.map(({ id, label, color, icon }) => (
                  <button
                    key={id}
                    onClick={() => setTab(id)}
                    className="flex-1 flex flex-col items-center gap-1.5 px-2 py-2.5 transition-all"
                    style={{
                      marginBottom: '-1px',
                      borderBottom: `2px solid ${tab === id ? color : 'transparent'}`,
                      opacity: tab === id ? 1 : 0.38,
                    }}
                  >
                    <SkuIcon color={color} size={22}>{icon}</SkuIcon>
                    <span className="text-[10px] font-medium" style={{ color: tab === id ? color : '#94a3b8' }}>
                      {label}
                    </span>
                  </button>
                ))}
              </div>

              {/* ── Body ───────────────────────────────────────────────────── */}
              <div className="p-6 max-h-[70vh] overflow-y-auto flex flex-col gap-5">

                {/* ── Profile Tab ─────────────────────────────────────────── */}
                {tab === 'profile' && (
                  <>
                    <SectionHeader
                      icon={<SkuIcon color="#22d3ee" size={36}><User size={16} className="text-cyan-300" /></SkuIcon>}
                      title={lang === 'fr' ? 'Informations du compte' : 'Account information'}
                      sub={lang === 'fr' ? 'Facultatif — stocké de façon sécurisée' : 'Optional — stored securely'}
                    />

                    <form onSubmit={handleSave} className="flex flex-col gap-4">
                      <div className="flex flex-col gap-1.5">
                        <label className="text-xs font-medium text-slate-400">
                          {lang === 'fr' ? 'Prénom' : 'First name'}
                        </label>
                        <Input value={firstName} onChange={setFirstName} maxLength={100}
                          placeholder={lang === 'fr' ? 'Votre prénom' : 'Your first name'} />
                      </div>

                      <div className="flex flex-col gap-1.5">
                        <label className="text-xs font-medium text-slate-400">
                          {lang === 'fr' ? 'Nom' : 'Last name'}
                        </label>
                        <Input value={lastName} onChange={setLastName} maxLength={100}
                          placeholder={lang === 'fr' ? 'Votre nom' : 'Your last name'} />
                      </div>

                      <div className="flex flex-col gap-1.5">
                        <label className="text-xs font-medium text-slate-400">Email</label>
                        <Input value={user?.email ?? ''} readOnly />
                      </div>

                      {saveErr && <ErrMsg msg={saveErr} />}
                      {saveOk  && <OkMsg msg={lang === 'fr' ? 'Profil mis à jour ✓' : 'Profile updated ✓'} />}

                      <button type="submit" disabled={saving}
                        className="sku-btn-primary flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm w-full disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none"
                      >
                        {saving
                          ? <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                          : <Save size={15} />}
                        {lang === 'fr' ? 'Enregistrer' : 'Save changes'}
                      </button>
                    </form>
                  </>
                )}

                {/* ── Security Tab ────────────────────────────────────────── */}
                {tab === 'security' && (
                  <>
                    <SectionHeader
                      icon={<SkuIcon color="#818cf8" size={36}><ShieldCheck size={16} className="text-indigo-300" /></SkuIcon>}
                      title={lang === 'fr' ? 'Sécurité du compte' : 'Account security'}
                      sub={lang === 'fr' ? 'Mot de passe et adresse email' : 'Password and email address'}
                    />

                    {isGoogle ? (
                      /* Compte Google — notice */
                      <div
                        className="rounded-xl p-4 flex gap-3 items-start"
                        style={{ background: 'rgba(99,102,241,0.07)', border: '1px solid rgba(99,102,241,0.2)' }}
                      >
                        <SkuIcon color="#818cf8" size={32}>
                          <Lock size={14} className="text-indigo-300" />
                        </SkuIcon>
                        <p className="text-slate-400 text-xs leading-relaxed pt-1">
                          {lang === 'fr'
                            ? 'Votre compte est lié à Google. La gestion du mot de passe et de l\'email se fait via votre compte Google.'
                            : 'Your account is linked to Google. Password and email are managed through your Google account.'}
                        </p>
                      </div>
                    ) : (
                      <>
                        {/* Sub-tabs password / email */}
                        <div className="flex gap-2">
                          {(['password', 'email'] as const).map(m => (
                            <button key={m} onClick={() => setSecMode(m)}
                              className={`flex-1 py-2 rounded-xl text-xs font-medium transition-all flex items-center justify-center gap-1.5 ${
                                secMode === m ? 'text-cyan-300' : 'text-slate-500 hover:text-slate-300'
                              }`}
                              style={{
                                background: secMode === m ? 'rgba(34,211,238,0.08)' : 'rgba(255,255,255,0.03)',
                                border: `1px solid ${secMode === m ? 'rgba(34,211,238,0.2)' : 'rgba(255,255,255,0.06)'}`,
                              }}
                            >
                              {m === 'password'
                                ? <><Lock size={11} />{lang === 'fr' ? 'Mot de passe' : 'Password'}</>
                                : <><Mail size={11} />{lang === 'fr' ? 'Adresse email' : 'Email address'}</>}
                            </button>
                          ))}
                        </div>

                        {/* ── Change password ── */}
                        {secMode === 'password' && (
                          <form onSubmit={handleChangePassword} className="flex flex-col gap-3">
                            <div className="flex flex-col gap-1.5">
                              <label className="text-xs font-medium text-slate-400">
                                {lang === 'fr' ? 'Mot de passe actuel' : 'Current password'}
                              </label>
                              <PasswordInput value={curPwd} onChange={setCurPwd} required />
                            </div>
                            <div className="flex flex-col gap-1.5">
                              <label className="text-xs font-medium text-slate-400">
                                {lang === 'fr' ? 'Nouveau mot de passe' : 'New password'}
                              </label>
                              <PasswordInput value={newPwd} onChange={setNewPwd} required
                                placeholder={lang === 'fr' ? 'Min. 8 caractères' : 'Min. 8 characters'} />
                            </div>
                            <div className="flex flex-col gap-1.5">
                              <label className="text-xs font-medium text-slate-400">
                                {lang === 'fr' ? 'Confirmer' : 'Confirm'}
                              </label>
                              <PasswordInput value={confirmPwd} onChange={setConfirmPwd} required />
                            </div>

                            {pwdErr && <ErrMsg msg={pwdErr} />}
                            {pwdOk  && <OkMsg msg={lang === 'fr' ? 'Mot de passe modifié ✓' : 'Password updated ✓'} />}

                            <button type="submit"
                              disabled={pwdSaving || !curPwd || !newPwd || !confirmPwd}
                              className="sku-btn-primary flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm w-full disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none"
                            >
                              {pwdSaving
                                ? <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                                : <Lock size={15} />}
                              {lang === 'fr' ? 'Modifier le mot de passe' : 'Update password'}
                            </button>
                          </form>
                        )}

                        {/* ── Change email ── */}
                        {secMode === 'email' && (
                          <form onSubmit={handleChangeEmail} className="flex flex-col gap-3">
                            <div className="flex flex-col gap-1.5">
                              <label className="text-xs font-medium text-slate-400">
                                {lang === 'fr' ? 'Email actuel' : 'Current email'}
                              </label>
                              <Input value={user?.email ?? ''} readOnly />
                            </div>
                            <div className="flex flex-col gap-1.5">
                              <label className="text-xs font-medium text-slate-400">
                                {lang === 'fr' ? 'Nouvel email' : 'New email'}
                              </label>
                              <Input type="email" value={newEmail} onChange={setNewEmail}
                                required placeholder="new@example.com" />
                            </div>
                            <div className="flex flex-col gap-1.5">
                              <label className="text-xs font-medium text-slate-400">
                                {lang === 'fr' ? 'Mot de passe actuel' : 'Current password'}
                              </label>
                              <PasswordInput value={emailPwd} onChange={setEmailPwd} required />
                            </div>

                            {emailErr && <ErrMsg msg={emailErr} />}
                            {emailOk  && <OkMsg msg={lang === 'fr' ? 'Email modifié ✓' : 'Email updated ✓'} />}

                            <button type="submit"
                              disabled={emailSaving || !newEmail || !emailPwd}
                              className="sku-btn-primary flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm w-full disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none"
                            >
                              {emailSaving
                                ? <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                                : <Save size={15} />}
                              {lang === 'fr' ? 'Modifier l\'email' : 'Update email'}
                            </button>
                          </form>
                        )}
                      </>
                    )}
                  </>
                )}

                {/* ── API Tab ─────────────────────────────────────────────── */}
                {tab === 'api' && (
                  <>
                    <SectionHeader
                      icon={<SkuIcon color="#a78bfa" size={36}><KeyRound size={16} className="text-violet-300" /></SkuIcon>}
                      title={lang === 'fr' ? 'Clé API' : 'API key'}
                      sub={lang === 'fr' ? 'Intégration & automatisation' : 'Integration & automation'}
                    />

                    {!isPro ? (
                      /* Paywall — Pro only */
                      <div
                        className="rounded-xl p-5 flex flex-col items-center gap-4 text-center"
                        style={{ background: 'rgba(167,139,250,0.05)', border: '1px solid rgba(167,139,250,0.15)' }}
                      >
                        <SkuIcon color="#a78bfa" size={52}>
                          <KeyRound size={22} className="text-violet-300" />
                        </SkuIcon>
                        <div>
                          <p className="text-white font-semibold text-sm mb-1">
                            {lang === 'fr' ? 'Réservé au plan Pro' : 'Pro plan required'}
                          </p>
                          <p className="text-slate-400 text-xs leading-relaxed">
                            {lang === 'fr'
                              ? 'Automatisez vos scans et intégrez les rapports de sécurité dans vos outils et workflows.'
                              : 'Automate scans and integrate security reports into your tools and workflows.'}
                          </p>
                        </div>
                        <span
                          className="text-[10px] font-bold font-mono px-2.5 py-1 rounded"
                          style={{ color: '#a78bfa', background: 'rgba(139,92,246,0.12)', border: '1px solid rgba(167,139,250,0.25)' }}
                        >
                          PRO
                        </span>
                      </div>
                    ) : (
                      <>
                        <p className="text-slate-500 text-xs leading-relaxed -mt-2">
                          {lang === 'fr'
                            ? 'Utilisez cette clé pour authentifier vos requêtes API. Ne la partagez pas — régénérez-la si elle est compromise.'
                            : 'Use this key to authenticate API requests. Do not share it — regenerate if compromised.'}
                        </p>

                        {/* Key display */}
                        <div className="flex flex-col gap-1.5">
                          <label className="text-xs font-medium text-slate-400">
                            {lang === 'fr' ? 'Votre clé API' : 'Your API key'}
                          </label>
                          <div className="flex gap-2">
                            <div
                              className="flex-1 rounded-xl px-4 py-2.5 text-xs font-mono text-slate-300 overflow-hidden text-ellipsis whitespace-nowrap"
                              style={{
                                background: 'rgba(0,0,0,0.3)',
                                border: '1px solid rgba(255,255,255,0.07)',
                                boxShadow: '0 2px 6px rgba(0,0,0,0.3) inset',
                                letterSpacing: '0.04em',
                              }}
                            >
                              {apiVisible ? (apiKey ?? '—') : '••••••••••••••••••••••••••••••••'}
                            </div>
                            {/* Toggle visibility */}
                            <button type="button" onClick={() => setApiVisible(v => !v)}
                              className="shrink-0 px-3 rounded-xl text-slate-400 hover:text-slate-200 transition"
                              style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', boxShadow: '0 1px 0 rgba(255,255,255,0.05) inset, 0 2px 4px rgba(0,0,0,0.25)' }}
                              title={apiVisible ? (lang === 'fr' ? 'Masquer' : 'Hide') : (lang === 'fr' ? 'Afficher' : 'Show')}
                            >
                              {apiVisible ? <EyeOff size={14} /> : <Eye size={14} />}
                            </button>
                            {/* Copy */}
                            <button type="button" onClick={handleCopyApiKey}
                              className="shrink-0 px-3 rounded-xl transition"
                              style={{
                                background: apiCopied ? 'rgba(52,211,153,0.1)' : 'rgba(255,255,255,0.04)',
                                border: `1px solid ${apiCopied ? 'rgba(52,211,153,0.25)' : 'rgba(255,255,255,0.08)'}`,
                                color: apiCopied ? '#34d399' : '#94a3b8',
                                boxShadow: '0 1px 0 rgba(255,255,255,0.05) inset, 0 2px 4px rgba(0,0,0,0.25)',
                              }}
                              title={lang === 'fr' ? 'Copier' : 'Copy'}
                            >
                              {apiCopied ? <CheckCircle size={14} /> : <Copy size={14} />}
                            </button>
                          </div>
                        </div>

                        {apiRegenOk && <OkMsg msg={lang === 'fr' ? 'Nouvelle clé générée ✓' : 'New key generated ✓'} />}

                        {/* Regen */}
                        <button type="button" onClick={handleRegenApiKey} disabled={apiRegen}
                          className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm w-full font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                          style={{
                            background: 'rgba(245,158,11,0.08)',
                            border: '1px solid rgba(245,158,11,0.2)',
                            color: '#fbbf24',
                            boxShadow: '0 1px 0 rgba(255,255,255,0.04) inset, 0 2px 8px rgba(0,0,0,0.3)',
                          }}
                        >
                          {apiRegen
                            ? <div className="w-4 h-4 border-2 border-amber-400/30 border-t-amber-400 rounded-full animate-spin" />
                            : <RefreshCw size={14} />}
                          {lang === 'fr' ? 'Régénérer la clé' : 'Regenerate key'}
                        </button>

                        <p className="text-slate-600 text-xs -mt-2">
                          {lang === 'fr'
                            ? '⚠️ La régénération invalide immédiatement l\'ancienne clé.'
                            : '⚠️ Regenerating immediately invalidates the current key.'}
                        </p>
                      </>
                    )}
                  </>
                )}

                {/* ── Danger Tab ──────────────────────────────────────────── */}
                {tab === 'danger' && (
                  <>
                    <SectionHeader
                      icon={<SkuIcon color="#f87171" size={36}><Trash2 size={15} className="text-red-300" /></SkuIcon>}
                      title={lang === 'fr' ? 'Suppression du compte' : 'Account deletion'}
                      sub={lang === 'fr' ? 'Action irréversible' : 'Irreversible action'}
                    />

                    <form onSubmit={handleDelete} className="flex flex-col gap-4">
                      {/* Warning notice */}
                      <div
                        className="rounded-xl p-4 flex gap-3 items-start"
                        style={{ background: 'rgba(239,68,68,0.07)', border: '1px solid rgba(239,68,68,0.2)' }}
                      >
                        <SkuIcon color="#f87171" size={32}>
                          <AlertTriangle size={14} className="text-red-300" />
                        </SkuIcon>
                        <p className="text-slate-400 text-xs leading-relaxed pt-1">
                          {lang === 'fr'
                            ? 'La suppression effacera définitivement toutes vos données, y compris l\'historique de scans. Cette action ne peut pas être annulée.'
                            : 'Deletion will permanently erase all your data, including scan history. This action cannot be undone.'}
                        </p>
                      </div>

                      <div className="flex flex-col gap-1.5">
                        <label className="text-xs font-medium text-slate-400">
                          {lang === 'fr' ? 'Mot de passe actuel' : 'Current password'}
                        </label>
                        <PasswordInput value={delPassword} onChange={setDelPassword}
                          required focusColor="rgba(239,68,68,0.4)" />
                      </div>

                      <div className="flex flex-col gap-1.5">
                        <label className="text-xs font-medium text-slate-400">
                          {lang === 'fr' ? 'Tapez SUPPRIMER pour confirmer' : 'Type DELETE to confirm'}
                        </label>
                        <input
                          type="text" value={delConfirm}
                          onChange={e => setDelConfirm(e.target.value)}
                          required placeholder={lang === 'fr' ? 'SUPPRIMER' : 'DELETE'}
                          className="w-full rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-slate-600 focus:outline-none transition font-mono tracking-wider"
                          style={{
                            background: 'rgba(255,255,255,0.04)',
                            border: '1px solid rgba(255,255,255,0.08)',
                            boxShadow: '0 2px 6px rgba(0,0,0,0.3) inset',
                          }}
                          onFocus={e => (e.currentTarget.style.borderColor = 'rgba(239,68,68,0.4)')}
                          onBlur={e => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)')}
                        />
                      </div>

                      {delErr && <ErrMsg msg={delErr} />}

                      <button
                        type="submit"
                        disabled={deleting || !delPassword || (delConfirm !== 'SUPPRIMER' && delConfirm !== 'DELETE')}
                        className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm w-full font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                        style={{
                          background: deleting ? 'rgba(239,68,68,0.3)' : 'rgba(239,68,68,0.15)',
                          border: '1px solid rgba(239,68,68,0.3)',
                          color: '#f87171',
                          boxShadow: '0 1px 0 rgba(255,255,255,0.04) inset, 0 2px 8px rgba(0,0,0,0.3)',
                        }}
                      >
                        {deleting
                          ? <div className="w-4 h-4 border-2 border-red-400/30 border-t-red-400 rounded-full animate-spin" />
                          : <Trash2 size={15} />}
                        {lang === 'fr' ? 'Supprimer mon compte' : 'Delete my account'}
                      </button>
                    </form>
                  </>
                )}

              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
