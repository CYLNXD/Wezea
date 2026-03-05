import { useState, FormEvent } from 'react';
import { Shield, Mail, Lock, Eye, EyeOff, ArrowRight, AlertCircle } from 'lucide-react';
import { motion } from 'framer-motion';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../i18n/LanguageContext';

interface Props {
  onBack: () => void;
}

export default function LoginPage({ onBack }: Props) {
  const { login, register } = useAuth();
  const { lang } = useLanguage();

  const [mode,     setMode]     = useState<'login' | 'register'>('login');
  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [showPwd,  setShowPwd]  = useState(false);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState('');

  const isLogin = mode === 'login';

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
    <div className="min-h-screen bg-slate-950 flex items-center justify-center px-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md"
      >
        {/* Logo */}
        <div className="flex items-center gap-2.5 justify-center mb-8">
          <div className="p-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
            <Shield size={20} className="text-cyan-400" />
          </div>
          <span className="font-bold text-white font-mono text-lg tracking-tight">
            We<span className="text-cyan-400">zea</span>
          </span>
          <span className="text-xs text-slate-600 font-mono">Scanner</span>
        </div>

        {/* Card */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8">
          {/* Tabs */}
          <div className="flex bg-slate-800/50 rounded-xl p-1 mb-6">
            {(['login', 'register'] as const).map(m => (
              <button
                key={m}
                onClick={() => { setMode(m); setError(''); }}
                className={`flex-1 py-2 text-sm font-medium rounded-lg transition-all ${
                  mode === m
                    ? 'bg-slate-700 text-white'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
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
              <label className="block text-xs text-slate-400 font-mono mb-1.5">
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
                  className="w-full bg-slate-800 border border-slate-700 rounded-xl pl-9 pr-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/30 transition"
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label className="block text-xs text-slate-400 font-mono mb-1.5">
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
                  className="w-full bg-slate-800 border border-slate-700 rounded-xl pl-9 pr-10 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/30 transition"
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
              className="w-full flex items-center justify-center gap-2 bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 text-slate-900 font-semibold py-2.5 rounded-xl transition-all text-sm"
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
              <p className="text-xs text-cyan-400/80 font-mono text-center">
                {lang === 'fr'
                  ? '✓ Gratuit — 5 scans/mois — historique illimité'
                  : '✓ Free — 5 scans/month — unlimited history'}
              </p>
            </div>
          )}
        </div>

        {/* Back */}
        <button
          onClick={onBack}
          className="mt-4 w-full text-slate-500 hover:text-slate-300 text-sm font-mono transition text-center"
        >
          ← {lang === 'fr' ? 'Retour au scanner' : 'Back to scanner'}
        </button>
      </motion.div>
    </div>
  );
}
