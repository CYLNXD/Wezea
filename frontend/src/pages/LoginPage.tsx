import { useState, useEffect, FormEvent } from 'react';
import { Shield, Mail, Lock, Eye, EyeOff, ArrowRight, AlertCircle } from 'lucide-react';
import { motion } from 'framer-motion';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../i18n/LanguageContext';

interface Props {
  onBack:       () => void;
  initialMode?: 'login' | 'register';
}

export default function LoginPage({ onBack, initialMode }: Props) {
  const { login, register, googleLogin } = useAuth();
  const { lang } = useLanguage();

  const [mode,     setMode]     = useState<'login' | 'register'>(initialMode ?? 'login');
  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [showPwd,  setShowPwd]  = useState(false);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState('');

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
        callback: async (resp: { credential: string }) => {
          setError('');
          setLoading(true);
          try {
            await googleLogin(resp.credential);
            onBack();
          } catch (err: any) {
            setError(err?.response?.data?.detail || err?.message || 'Erreur Google');
          } finally {
            setLoading(false);
          }
        },
      });

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

  const handleGoogleClick = () => {
    const gsi = window.google?.accounts?.id;
    if (!gsi) return;
    (gsi.prompt as any)((notification: any) => {
      if (notification.isNotDisplayed() || notification.isSkippedMoment()) {
        setError(
          lang === 'fr'
            ? 'Connexion Google indisponible. Réessayez dans quelques secondes.'
            : 'Google sign-in unavailable. Please try again in a few seconds.'
        );
      }
    });
  };

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      if (isLogin) {
        await login(email, password);
      } else {
        await register(email, password);
      }
      onBack();
    } catch (err: any) {
      setError(err.message || 'Une erreur est survenue');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4" style={{ backgroundColor: 'var(--color-bg)' }}>
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

          {/* ── Séparateur ── */}
          <div className="flex items-center gap-3 mt-5">
            <div className="flex-1 h-px" style={{ background: 'var(--color-border)' }} />
            <span className="text-slate-600 text-xs font-mono font-medium">
              {lang === 'fr' ? 'ou' : 'or'}
            </span>
            <div className="flex-1 h-px" style={{ background: 'var(--color-border)' }} />
          </div>

          {/* ── Bouton Google ── */}
          <div className="mt-4">
            <button
              type="button"
              onClick={handleGoogleClick}
              disabled={!gsiReady || loading}
              className="w-full flex items-center justify-center gap-3 sku-btn-ghost disabled:opacity-50 disabled:cursor-not-allowed rounded-xl py-2.5 text-sm font-medium text-white transition-all"
            >
              {!gsiReady ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-slate-600 border-t-slate-400 rounded-full animate-spin" />
                  {lang === 'fr' ? 'Chargement Google…' : 'Loading Google…'}
                </>
              ) : (
                <>
                  {/* Logo Google SVG */}
                  <svg width="16" height="16" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">
                    <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"/>
                    <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z"/>
                    <path fill="#FBBC05" d="M3.964 10.71c-.18-.54-.282-1.117-.282-1.71s.102-1.17.282-1.71V4.958H.957C.347 6.173 0 7.548 0 9s.348 2.827.957 4.042l3.007-2.332z"/>
                    <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"/>
                  </svg>
                  {lang === 'fr' ? 'Continuer avec Google' : 'Continue with Google'}
                </>
              )}
            </button>
          </div>
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
