import { useState, useEffect, FormEvent } from 'react';
import { Shield, Mail, Lock, Eye, EyeOff, ArrowRight, AlertCircle, CheckCircle, KeyRound, Tag } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../i18n/LanguageContext';
import { apiClient } from '../lib/api';

interface Props {
  onBack:       () => void;
  initialMode?: 'login' | 'register';
  resetToken?:  string | null;
  referralCode?: string | null;
}

export default function LoginPage({ onBack, initialMode, resetToken, referralCode }: Props) {
  const { register, googleLogin, loginWithToken } = useAuth();
  const { lang } = useLanguage();

  const [mode,     setMode]     = useState<'login' | 'register'>(initialMode ?? 'login');
  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [showPwd,  setShowPwd]  = useState(false);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState('');
  const [refCode,  setRefCode]  = useState(referralCode || '');

  // ── Sous-vues mot de passe oublié / réinitialisation ─────────────────────
  type SubView = 'form' | 'forgot' | 'forgot-sent' | 'reset' | 'reset-done' | 'mfa';
  const [subView,      setSubView]      = useState<SubView>('form');
  const [forgotEmail,  setForgotEmail]  = useState('');
  const [newPassword,  setNewPassword]  = useState('');
  const [newPassword2, setNewPassword2] = useState('');
  const [showNewPwd,   setShowNewPwd]   = useState(false);
  const [subError,     setSubError]     = useState('');
  const [subLoading,   setSubLoading]   = useState(false);
  // 2FA state
  const [mfaToken,     setMfaToken]     = useState('');
  const [totpCode,     setTotpCode]     = useState('');

  // Si un reset_token est passé en prop → afficher directement la vue reset
  useEffect(() => {
    if (resetToken) setSubView('reset');
  }, [resetToken]);

  const isLogin = mode === 'login';

  const [gsiReady, setGsiReady] = useState(false);

  // ── Google Identity Services init ────────────────────────────────────────
  useEffect(() => {
    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
    if (!clientId) return;

    let done = false;

    const init = () => {
      if (done) return false;
      const gsi = window.google?.accounts?.id;
      if (!gsi) return false;
      done = true;

      gsi.initialize({
        client_id: clientId,
        cancel_on_tap_outside: false,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        ...(({ use_fedcm_for_prompt: true }) as any),
        callback: async (resp: { credential: string }) => {
          setError('');
          setLoading(true);
          try {
            const result = await googleLogin(resp.credential, refCode || undefined);
            if (result?.mfa_required) {
              setMfaToken(result.mfa_token ?? '');
              setTotpCode('');
              setSubView('mfa');
              setLoading(false);
              return;
            }
            onBack();
          } catch (err: any) {
            setError(err?.response?.data?.detail || err?.message || 'Erreur Google');
          } finally {
            setLoading(false);
          }
        },
      });

      // Rendre le bouton Google officiel visible — FedCM + Chrome compatible
      // Le div est rendu après gsiReady=true, donc un léger délai est nécessaire
      setTimeout(() => {
        const btnDiv = document.getElementById('google-signin-hidden');
        if (btnDiv) {
          (gsi as any).renderButton(btnDiv, {
            type: 'standard',
            theme: 'filled_black',
            size: 'large',
            text: 'continue_with',
            shape: 'rectangular',
            width: 360,
          });
        }
      }, 50);

      setGsiReady(true);
      return true;
    };

    // Méthode 1 — callback officiel Google (appelé quand la lib est prête)
    (window as any).onGoogleLibraryLoad = init;

    // Méthode 2 — déjà chargé (navigation SPA, cache navigateur)
    if (!init()) {
      // Méthode 3 — polling de secours toutes les 500ms pendant 10s
      let attempts = 0;
      const interval = setInterval(() => {
        attempts++;
        if (init() || attempts > 20) clearInterval(interval);
      }, 500);
      return () => {
        clearInterval(interval);
        delete (window as any).onGoogleLibraryLoad;
      };
    }

    return () => { delete (window as any).onGoogleLibraryLoad; };
  }, []);

  // handleGoogleClick supprimé — le clic passe directement par l'overlay #google-signin-hidden

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      if (isLogin) {
        // Appel direct pour détecter mfa_required avant de passer au contexte
        const { data } = await apiClient.post('/auth/login', { email, password });
        if (data.mfa_required) {
          setMfaToken(data.mfa_token);
          setTotpCode('');
          setSubView('mfa');
          setLoading(false);
          return;
        }
        // Login normal — réutiliser la réponse (évite un double appel /auth/login)
        loginWithToken(data.access_token, data.user);
      } else {
        await register(email, password, refCode || undefined);
      }
      onBack();
    } catch (err: any) {
      setError(err.message || 'Une erreur est survenue');
    } finally {
      setLoading(false);
    }
  }

  // ── Handler : confirmation code TOTP ────────────────────────────────────
  async function handleTotpSubmit(e: FormEvent) {
    e.preventDefault();
    setSubError('');
    setSubLoading(true);
    try {
      const { data } = await apiClient.post('/auth/2fa/confirm-login', {
        code: totpCode.trim(),
        mfa_token: mfaToken,
      });
      loginWithToken(data.access_token, data.user);
      onBack();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setSubError(detail || (lang === 'fr' ? 'Code invalide.' : 'Invalid code.'));
    } finally {
      setSubLoading(false);
    }
  }

  // ── Handler : demande de réinitialisation ────────────────────────────────
  async function handleForgotSubmit(e: FormEvent) {
    e.preventDefault();
    setSubError('');
    setSubLoading(true);
    try {
      await apiClient.post('/auth/forgot-password', { email: forgotEmail });
      setSubView('forgot-sent');
    } catch {
      setSubError(lang === 'fr'
        ? 'Une erreur est survenue. Réessayez dans quelques instants.'
        : 'An error occurred. Please try again.');
    } finally {
      setSubLoading(false);
    }
  }

  // ── Handler : nouveau mot de passe ───────────────────────────────────────
  async function handleResetSubmit(e: FormEvent) {
    e.preventDefault();
    setSubError('');
    if (newPassword !== newPassword2) {
      setSubError(lang === 'fr' ? 'Les mots de passe ne correspondent pas.' : 'Passwords do not match.');
      return;
    }
    setSubLoading(true);
    try {
      await apiClient.post('/auth/reset-password', { token: resetToken, new_password: newPassword });
      setSubView('reset-done');
    } catch (err: any) {
      setSubError(
        err?.response?.data?.detail ||
        (lang === 'fr' ? 'Lien invalide ou expiré.' : 'Invalid or expired link.')
      );
    } finally {
      setSubLoading(false);
    }
  }

  return (
    <div className="relative min-h-screen flex items-center justify-center px-4">
      {/* Grille cyber — identique au hero Dashboard */}
      <div className="absolute inset-0 pointer-events-none" style={{ backgroundImage: 'linear-gradient(rgba(34,211,238,1) 1px, transparent 1px), linear-gradient(90deg, rgba(34,211,238,1) 1px, transparent 1px)', backgroundSize: '48px 48px', opacity: 0.025 }} />
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md"
      >
        {/* Logo */}
        <div className="flex items-center gap-2.5 justify-center mb-8">
          <div className="p-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20" style={{ boxShadow: '0 2px 8px rgba(34,211,238,0.08)' }}>
            <Shield size={20} className="text-cyan-400" />
          </div>
          <span className="font-black text-white text-lg" style={{ fontFamily: 'var(--font-display)', letterSpacing: '-0.03em' }}>
            We<span style={{ color: 'var(--color-accent)' }}>zea</span>
          </span>
          <span className="text-xs font-mono font-bold px-1.5 py-0.5 rounded" style={{ color: '#22d3ee', background: 'rgba(34,211,238,0.08)', border: '1px solid rgba(34,211,238,0.15)' }}>Scanner</span>
        </div>

        {/* Card */}
        <div className="sku-panel rounded-2xl p-8">

          {/* ── Sous-vue : Mot de passe oublié ──────────────────────────── */}
          <AnimatePresence mode="wait">
          {subView === 'forgot' && (
            <motion.div key="forgot" initial={{ opacity:0, y:8 }} animate={{ opacity:1, y:0 }} exit={{ opacity:0, y:-8 }}>
              <div className="flex items-center gap-3 mb-5">
                <div className="shrink-0 flex items-center justify-center relative overflow-hidden"
                  style={{ width:36, height:36, borderRadius:10,
                    background:'linear-gradient(150deg,#22d3ee30 0%,#22d3ee0d 100%)',
                    border:'1px solid #22d3ee40',
                    boxShadow:'0 4px 16px #22d3ee22,0 1px 3px rgba(0,0,0,0.4),inset 0 1px 0 #22d3ee30,inset 0 -1px 0 rgba(0,0,0,0.3)' }}>
                  <div className="absolute inset-0 pointer-events-none" style={{ borderRadius:10, background:'linear-gradient(180deg,rgba(255,255,255,0.07) 0%,transparent 50%)' }} />
                  <KeyRound size={16} className="text-cyan-300" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-white">{lang === 'fr' ? 'Mot de passe oublié' : 'Forgot password'}</p>
                  <p className="text-xs text-slate-400">{lang === 'fr' ? 'Nous vous enverrons un lien par email' : "We'll send you a reset link"}</p>
                </div>
              </div>
              <form onSubmit={handleForgotSubmit} className="space-y-4">
                <div>
                  <label className="block text-xs text-slate-400 font-medium mb-1.5">
                    {lang === 'fr' ? 'Adresse email' : 'Email address'}
                  </label>
                  <div className="relative">
                    <Mail size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                    <input
                      type="email" value={forgotEmail} onChange={e => setForgotEmail(e.target.value)}
                      required placeholder="vous@exemple.com"
                      className="w-full rounded-xl pl-9 pr-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/30 transition sku-inset"
                      style={{ border:'1px solid rgba(255,255,255,0.08)' }}
                    />
                  </div>
                </div>
                {subError && (
                  <div className="flex items-center gap-2 text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-xl px-3 py-2">
                    <AlertCircle size={14} />{subError}
                  </div>
                )}
                <button type="submit" disabled={subLoading}
                  className="w-full flex items-center justify-center gap-2 sku-btn-primary disabled:opacity-50 py-2.5 rounded-xl transition-all text-sm">
                  {subLoading
                    ? <div className="w-4 h-4 border-2 border-slate-900/30 border-t-slate-900 rounded-full animate-spin" />
                    : <>{lang === 'fr' ? 'Envoyer le lien' : 'Send reset link'}<ArrowRight size={15}/></>}
                </button>
                <button type="button" onClick={() => { setSubView('form'); setSubError(''); }}
                  className="w-full text-slate-500 hover:text-slate-300 text-sm font-medium transition text-center">
                  ← {lang === 'fr' ? 'Retour à la connexion' : 'Back to sign in'}
                </button>
              </form>
            </motion.div>
          )}

          {/* ── Sous-vue : Email envoyé ──────────────────────────────────── */}
          {subView === 'forgot-sent' && (
            <motion.div key="forgot-sent" initial={{ opacity:0, y:8 }} animate={{ opacity:1, y:0 }} exit={{ opacity:0, y:-8 }}
              className="text-center py-4">
              <div className="flex justify-center mb-4">
                <div className="shrink-0 flex items-center justify-center relative overflow-hidden"
                  style={{ width:52, height:52, borderRadius:14,
                    background:'linear-gradient(150deg,#4ade8030 0%,#4ade800d 100%)',
                    border:'1px solid #4ade8040',
                    boxShadow:'0 4px 16px #4ade8022,0 1px 3px rgba(0,0,0,0.4),inset 0 1px 0 #4ade8030,inset 0 -1px 0 rgba(0,0,0,0.3)' }}>
                  <div className="absolute inset-0 pointer-events-none" style={{ borderRadius:14, background:'linear-gradient(180deg,rgba(255,255,255,0.07) 0%,transparent 50%)' }} />
                  <CheckCircle size={24} className="text-green-300" />
                </div>
              </div>
              <p className="text-white font-semibold text-base mb-2">
                {lang === 'fr' ? 'Email envoyé !' : 'Email sent!'}
              </p>
              <p className="text-slate-400 text-sm mb-5">
                {lang === 'fr'
                  ? `Si l'adresse ${forgotEmail} est enregistrée, vous recevrez un lien dans quelques minutes. Vérifiez aussi vos spams.`
                  : `If ${forgotEmail} is registered, you'll receive a link shortly. Check your spam folder too.`}
              </p>
              <button onClick={() => { setSubView('form'); setForgotEmail(''); }}
                className="text-slate-500 hover:text-slate-300 text-sm font-medium transition">
                ← {lang === 'fr' ? 'Retour à la connexion' : 'Back to sign in'}
              </button>
            </motion.div>
          )}

          {/* ── Sous-vue : Nouveau mot de passe ─────────────────────────── */}
          {subView === 'reset' && (
            <motion.div key="reset" initial={{ opacity:0, y:8 }} animate={{ opacity:1, y:0 }} exit={{ opacity:0, y:-8 }}>
              <div className="flex items-center gap-3 mb-5">
                <div className="shrink-0 flex items-center justify-center relative overflow-hidden"
                  style={{ width:36, height:36, borderRadius:10,
                    background:'linear-gradient(150deg,#818cf830 0%,#818cf80d 100%)',
                    border:'1px solid #818cf840',
                    boxShadow:'0 4px 16px #818cf822,0 1px 3px rgba(0,0,0,0.4),inset 0 1px 0 #818cf830,inset 0 -1px 0 rgba(0,0,0,0.3)' }}>
                  <div className="absolute inset-0 pointer-events-none" style={{ borderRadius:10, background:'linear-gradient(180deg,rgba(255,255,255,0.07) 0%,transparent 50%)' }} />
                  <Lock size={16} className="text-indigo-300" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-white">{lang === 'fr' ? 'Nouveau mot de passe' : 'New password'}</p>
                  <p className="text-xs text-slate-400">{lang === 'fr' ? 'Choisissez un mot de passe sécurisé' : 'Choose a strong password'}</p>
                </div>
              </div>
              <form onSubmit={handleResetSubmit} className="space-y-4">
                <div>
                  <label className="block text-xs text-slate-400 font-medium mb-1.5">
                    {lang === 'fr' ? 'Nouveau mot de passe' : 'New password'}
                  </label>
                  <div className="relative">
                    <Lock size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                    <input
                      type={showNewPwd ? 'text' : 'password'} value={newPassword}
                      onChange={e => setNewPassword(e.target.value)}
                      required minLength={8}
                      placeholder={lang === 'fr' ? 'Minimum 8 caractères' : 'Minimum 8 characters'}
                      className="w-full rounded-xl pl-9 pr-10 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/30 transition sku-inset"
                      style={{ border:'1px solid rgba(255,255,255,0.08)' }}
                    />
                    <button type="button" onClick={() => setShowNewPwd(v => !v)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
                      {showNewPwd ? <EyeOff size={15}/> : <Eye size={15}/>}
                    </button>
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-slate-400 font-medium mb-1.5">
                    {lang === 'fr' ? 'Confirmer le mot de passe' : 'Confirm password'}
                  </label>
                  <div className="relative">
                    <Lock size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                    <input
                      type={showNewPwd ? 'text' : 'password'} value={newPassword2}
                      onChange={e => setNewPassword2(e.target.value)}
                      required minLength={8}
                      placeholder={lang === 'fr' ? 'Répétez votre mot de passe' : 'Repeat your password'}
                      className="w-full rounded-xl pl-9 pr-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/30 transition sku-inset"
                      style={{ border:'1px solid rgba(255,255,255,0.08)' }}
                    />
                  </div>
                </div>
                {subError && (
                  <div className="flex items-center gap-2 text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-xl px-3 py-2">
                    <AlertCircle size={14}/>{subError}
                  </div>
                )}
                <button type="submit" disabled={subLoading}
                  className="w-full flex items-center justify-center gap-2 sku-btn-primary disabled:opacity-50 py-2.5 rounded-xl transition-all text-sm">
                  {subLoading
                    ? <div className="w-4 h-4 border-2 border-slate-900/30 border-t-slate-900 rounded-full animate-spin" />
                    : <>{lang === 'fr' ? 'Enregistrer le mot de passe' : 'Save new password'}<ArrowRight size={15}/></>}
                </button>
              </form>
            </motion.div>
          )}

          {/* ── Sous-vue : Réinitialisation réussie ─────────────────────── */}
          {subView === 'reset-done' && (
            <motion.div key="reset-done" initial={{ opacity:0, y:8 }} animate={{ opacity:1, y:0 }} exit={{ opacity:0, y:-8 }}
              className="text-center py-4">
              <div className="flex justify-center mb-4">
                <div className="shrink-0 flex items-center justify-center relative overflow-hidden"
                  style={{ width:52, height:52, borderRadius:14,
                    background:'linear-gradient(150deg,#4ade8030 0%,#4ade800d 100%)',
                    border:'1px solid #4ade8040',
                    boxShadow:'0 4px 16px #4ade8022,0 1px 3px rgba(0,0,0,0.4),inset 0 1px 0 #4ade8030,inset 0 -1px 0 rgba(0,0,0,0.3)' }}>
                  <div className="absolute inset-0 pointer-events-none" style={{ borderRadius:14, background:'linear-gradient(180deg,rgba(255,255,255,0.07) 0%,transparent 50%)' }} />
                  <CheckCircle size={24} className="text-green-300" />
                </div>
              </div>
              <p className="text-white font-semibold text-base mb-2">
                {lang === 'fr' ? 'Mot de passe mis à jour !' : 'Password updated!'}
              </p>
              <p className="text-slate-400 text-sm mb-5">
                {lang === 'fr'
                  ? 'Votre nouveau mot de passe est actif. Vous pouvez maintenant vous connecter.'
                  : 'Your new password is active. You can now sign in.'}
              </p>
              <button onClick={() => { setSubView('form'); setNewPassword(''); setNewPassword2(''); setMode('login'); }}
                className="w-full flex items-center justify-center gap-2 sku-btn-primary py-2.5 rounded-xl transition-all text-sm">
                {lang === 'fr' ? 'Se connecter' : 'Sign in'}<ArrowRight size={15}/>
              </button>
            </motion.div>
          )}
          {/* ── Sous-vue : Code 2FA ──────────────────────────────────────── */}
          {subView === 'mfa' && (
            <motion.div key="mfa" initial={{ opacity:0, y:8 }} animate={{ opacity:1, y:0 }} exit={{ opacity:0, y:-8 }}>
              <div className="flex items-center gap-3 mb-5">
                <div className="shrink-0 flex items-center justify-center relative overflow-hidden"
                  style={{ width:36, height:36, borderRadius:10,
                    background:'linear-gradient(150deg,#818cf830 0%,#818cf80d 100%)',
                    border:'1px solid #818cf840',
                    boxShadow:'0 4px 16px #818cf822,0 1px 3px rgba(0,0,0,0.4),inset 0 1px 0 #818cf830,inset 0 -1px 0 rgba(0,0,0,0.3)' }}>
                  <div className="absolute inset-0 pointer-events-none" style={{ borderRadius:10, background:'linear-gradient(180deg,rgba(255,255,255,0.07) 0%,transparent 50%)' }} />
                  <KeyRound size={16} className="text-indigo-300 relative z-10" />
                </div>
                <div>
                  <h3 className="font-semibold text-slate-100 text-sm">
                    {lang === 'fr' ? 'Vérification en deux étapes' : 'Two-factor verification'}
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {lang === 'fr' ? 'Entrez le code de votre application d\'authentification.' : 'Enter the code from your authenticator app.'}
                  </p>
                </div>
              </div>
              <form onSubmit={handleTotpSubmit} className="space-y-4">
                {subError && (
                  <div className="flex items-center gap-2 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2 text-red-400 text-xs">
                    <AlertCircle size={13} className="shrink-0" />{subError}
                  </div>
                )}
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1.5">
                    {lang === 'fr' ? 'Code à 6 chiffres' : '6-digit code'}
                  </label>
                  <input
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]{6}"
                    maxLength={6}
                    value={totpCode}
                    onChange={e => setTotpCode(e.target.value.replace(/\D/g, ''))}
                    placeholder="000000"
                    className="sku-inset w-full rounded-xl px-4 py-3 text-slate-100 placeholder-slate-600 outline-none focus:ring-1 focus:ring-indigo-500/40 text-center text-2xl font-mono tracking-widest"
                    autoFocus
                    autoComplete="one-time-code"
                  />
                </div>
                <button type="submit" disabled={subLoading || totpCode.length !== 6}
                  className="w-full flex items-center justify-center gap-2 sku-btn-primary py-2.5 rounded-xl transition-all text-sm disabled:opacity-40">
                  {subLoading
                    ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    : <>{lang === 'fr' ? 'Vérifier' : 'Verify'}<ArrowRight size={15}/></>}
                </button>
                <button type="button" onClick={() => { setSubView('form'); setSubError(''); setTotpCode(''); }}
                  className="w-full text-xs text-slate-500 hover:text-slate-300 transition py-1">
                  {lang === 'fr' ? '← Retour à la connexion' : '← Back to sign in'}
                </button>
              </form>
            </motion.div>
          )}
          </AnimatePresence>

          {/* ── Vue principale : Tabs + formulaire login/register ────────── */}
          {subView === 'form' && (<>
          {/* Tabs */}
          <div className="flex rounded-xl p-1 mb-6 sku-inset">
            {(['login', 'register'] as const).map(m => (
              <button
                key={m}
                onClick={() => { setMode(m); setError(''); }}
                className={`flex-1 py-2 text-sm font-medium rounded-lg transition-all ${
                  mode === m
                    ? 'text-white'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                style={mode === m ? {
                  background: 'linear-gradient(180deg,#1e2d3d,#162433)',
                  boxShadow: '0 1px 0 rgba(255,255,255,0.06) inset, 0 2px 6px rgba(0,0,0,0.3)',
                } : {}}
              >
                {m === 'login'
                  ? (lang === 'fr' ? 'Connexion' : 'Sign in')
                  : (lang === 'fr' ? 'Inscription' : 'Register')}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Email */}
            <div>
              <label className="block text-xs text-slate-400 font-medium mb-1.5">
                {lang === 'fr' ? 'Adresse email' : 'Email address'}
              </label>
              <div className="relative">
                <Mail size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  required
                  placeholder="vous@exemple.com"
                  className="w-full rounded-xl pl-9 pr-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/30 transition sku-inset"
                  style={{ border: '1px solid rgba(255,255,255,0.08)' }}
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label className="block text-xs text-slate-400 font-medium mb-1.5">
                {lang === 'fr' ? 'Mot de passe' : 'Password'}
              </label>
              <div className="relative">
                <Lock size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                <input
                  type={showPwd ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  required
                  minLength={8}
                  placeholder={lang === 'fr' ? 'Minimum 8 caractères' : 'Minimum 8 characters'}
                  className="w-full rounded-xl pl-9 pr-10 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/30 transition sku-inset"
                  style={{ border: '1px solid rgba(255,255,255,0.08)' }}
                />
                <button
                  type="button"
                  onClick={() => setShowPwd(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                >
                  {showPwd ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            {/* Code partenaire — inscription uniquement */}
            {!isLogin && (
              <div>
                <label className="block text-xs text-slate-400 font-medium mb-1.5">
                  {lang === 'fr' ? 'Code partenaire (optionnel)' : 'Partner code (optional)'}
                </label>
                <div className="relative">
                  <Tag size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                  <input
                    type="text"
                    value={refCode}
                    onChange={e => setRefCode(e.target.value.toUpperCase())}
                    placeholder="wza_XXXXXX"
                    className="w-full rounded-xl pl-9 pr-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/30 transition sku-inset font-mono"
                    style={{ border: '1px solid rgba(255,255,255,0.08)' }}
                  />
                </div>
                {refCode && /^wza_[A-Z0-9]{6}$/i.test(refCode) && (
                  <div className="mt-1.5 flex items-center gap-1.5">
                    <CheckCircle size={12} className="text-green-400" />
                    <span className="text-xs text-green-400 font-medium">
                      {lang === 'fr' ? '-20 % sur le premier mois' : '-20% on your first month'}
                    </span>
                  </div>
                )}
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="flex items-center gap-2 text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-xl px-3 py-2">
                <AlertCircle size={14} />
                {error}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 sku-btn-primary disabled:opacity-50 py-2.5 rounded-xl transition-all text-sm"
            >
              {loading ? (
                <div className="w-4 h-4 border-2 border-slate-900/30 border-t-slate-900 rounded-full animate-spin" />
              ) : (
                <>
                  {isLogin
                    ? (lang === 'fr' ? 'Se connecter' : 'Sign in')
                    : (lang === 'fr' ? 'Créer mon compte' : 'Create account')}
                  <ArrowRight size={15} />
                </>
              )}
            </button>
          </form>

          {/* Plan info for register */}
          {!isLogin && (
            <div className="mt-4 p-3 bg-cyan-500/5 border border-cyan-500/20 rounded-xl">
              <p className="text-xs text-cyan-400/80 font-medium text-center">
                {lang === 'fr'
                  ? '✓ Gratuit — 5 scans/semaine — historique illimité'
                  : '✓ Free — 5 scans/week — unlimited history'}
              </p>
            </div>
          )}

          {/* Lien Mot de passe oublié — uniquement en mode login */}
          {isLogin && (
            <div className="mt-3 text-center">
              <button
                type="button"
                onClick={() => { setSubError(''); setSubView('forgot'); }}
                className="text-slate-500 hover:text-cyan-400 text-xs font-medium transition"
              >
                {lang === 'fr' ? 'Mot de passe oublié ?' : 'Forgot your password?'}
              </button>
            </div>
          )}

          {/* ── Séparateur ── */}
          <div className="flex items-center gap-3 mt-5">
            <div className="flex-1 h-px" style={{ background: 'var(--color-border)' }} />
            <span className="text-slate-600 text-xs font-mono font-medium">
              {lang === 'fr' ? 'ou' : 'or'}
            </span>
            <div className="flex-1 h-px" style={{ background: 'var(--color-border)' }} />
          </div>

          {/* ── Bouton Google ── rendu officiel visible (FedCM + Chrome) ── */}
          <div className="mt-4">
            {!gsiReady ? (
              <div className="w-full flex items-center justify-center gap-3 sku-btn-ghost rounded-xl py-2.5 text-sm font-medium text-white opacity-60 cursor-not-allowed">
                <div className="w-3.5 h-3.5 border-2 border-slate-600 border-t-slate-400 rounded-full animate-spin" />
                {lang === 'fr' ? 'Chargement Google…' : 'Loading Google…'}
              </div>
            ) : (
              <div
                id="google-signin-hidden"
                className="flex justify-center overflow-hidden rounded-xl"
                style={{ border: '1px solid rgba(255,255,255,0.08)', minHeight: 44 }}
              />
            )}
          </div>
          </>)}
          {/* ── fin subView === 'form' ── */}
        </div>

        {/* Back */}
        <button
          onClick={onBack}
          className="mt-4 w-full text-slate-500 hover:text-slate-300 text-sm font-medium transition text-center"
        >
          ← {lang === 'fr' ? 'Retour au scanner' : 'Back to scanner'}
        </button>
      </motion.div>
    </div>
  );
}
