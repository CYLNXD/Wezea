// ─── NewsletterWidget.tsx — Bloc d'abonnement à la newsletter ────────────────
import { useState, FormEvent } from 'react';
import { Mail, ArrowRight, CheckCircle, Loader, Newspaper, ShieldCheck, CalendarDays, X } from 'lucide-react';
import { apiClient } from '../lib/api';
import { useLanguage } from '../i18n/LanguageContext';

type Status = 'idle' | 'loading' | 'success' | 'error';

interface Props {
  /** Pré-remplir avec l'email de l'utilisateur connecté */
  prefillEmail?: string;
  /** Variante compacte (inline) ou étendue (avec description) */
  variant?: 'compact' | 'full';
}

export default function NewsletterWidget({ prefillEmail = '', variant = 'full' }: Props) {
  const { lang } = useLanguage();
  const [email, setEmail]         = useState(prefillEmail);
  const [status, setStatus]       = useState<Status>('idle');
  const [error, setError]         = useState('');
  const [showUnsub, setShowUnsub] = useState(false);
  const [unsubStatus, setUnsubStatus] = useState<'idle' | 'loading' | 'done' | 'error'>('idle');

  async function handleUnsubscribe() {
    if (!email.trim()) return;
    setUnsubStatus('loading');
    try {
      await apiClient.post('/newsletter/unsubscribe', { email: email.trim().toLowerCase() });
      setUnsubStatus('done');
    } catch {
      setUnsubStatus('error');
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setStatus('loading');
    setError('');
    try {
      await apiClient.post('/newsletter/subscribe', { email: email.trim().toLowerCase() });
      setStatus('success');
    } catch (err: unknown) {
      const msg = (err as { detail?: string })?.detail ?? '';
      setError(
        lang === 'fr'
          ? 'Une erreur est survenue. Veuillez réessayer.'
          : 'Something went wrong. Please try again.'
      );
      console.error('Newsletter subscribe error:', msg);
      setStatus('error');
    }
  }

  // ── État succès ──────────────────────────────────────────────────────────
  if (status === 'success') {
    return (
      <div className="rounded-2xl border border-emerald-500/25 bg-emerald-500/5 px-5 py-4 flex items-start gap-3">
        <CheckCircle size={18} className="text-emerald-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-white text-sm font-semibold">
            {lang === 'fr' ? 'Vérifiez votre boîte mail !' : 'Check your inbox!'}
          </p>
          <p className="text-slate-400 text-xs mt-0.5">
            {lang === 'fr'
              ? 'Un email de confirmation vous a été envoyé. Cliquez sur le lien pour finaliser votre inscription.'
              : 'A confirmation email has been sent. Click the link to complete your subscription.'}
          </p>
        </div>
      </div>
    );
  }

  // ── Variante compacte ────────────────────────────────────────────────────
  if (variant === 'compact') {
    return (
      <form onSubmit={handleSubmit} className="flex gap-2 flex-wrap">
        <input
          type="email"
          required
          value={email}
          onChange={e => setEmail(e.target.value)}
          placeholder={lang === 'fr' ? 'votre@email.com' : 'your@email.com'}
          className="flex-1 min-w-0 bg-slate-800/60 border border-slate-700/60 rounded-xl px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500/50 transition"
        />
        <button
          type="submit"
          disabled={status === 'loading'}
          className="flex items-center gap-1.5 bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 text-slate-950 font-bold px-4 py-2 rounded-xl text-sm transition shrink-0"
        >
          {status === 'loading'
            ? <Loader size={14} className="animate-spin" />
            : <ArrowRight size={14} />}
          {lang === 'fr' ? "S'abonner" : 'Subscribe'}
        </button>
        {status === 'error' && (
          <p className="w-full text-xs text-red-400 mt-0.5">{error}</p>
        )}
      </form>
    );
  }

  // ── Variante complète ────────────────────────────────────────────────────
  return (
    <div className="rounded-2xl border border-slate-700/50 bg-gradient-to-b from-slate-800/40 to-slate-900/60 p-6">
      {/* En-tête */}
      <div className="flex items-center gap-2.5 mb-3">
        <div className="p-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
          <Mail size={15} className="text-cyan-400" />
        </div>
        <h3 className="text-white font-bold text-sm">
          {lang === 'fr' ? 'Newsletter sécurité' : 'Security newsletter'}
        </h3>
      </div>

      {/* Description */}
      <p className="text-slate-400 text-sm leading-relaxed mb-4">
        {lang === 'fr'
          ? 'Recevez nos conseils en cybersécurité et les nouveaux articles de blog directement dans votre boîte mail. Pas de spam — désabonnement en un clic.'
          : 'Get our cybersecurity tips and new blog articles straight to your inbox. No spam — unsubscribe in one click.'}
      </p>

      {/* Badges */}
      <div className="flex flex-wrap gap-3 mb-4">
        {([
          {
            Icon: Newspaper,
            bg: 'bg-cyan-500/10', border: 'border-cyan-500/20', color: 'text-cyan-400',
            fr: 'Nouveaux articles', en: 'New articles',
          },
          {
            Icon: ShieldCheck,
            bg: 'bg-violet-500/10', border: 'border-violet-500/20', color: 'text-violet-400',
            fr: 'Conseils sécurité', en: 'Security tips',
          },
          {
            Icon: CalendarDays,
            bg: 'bg-emerald-500/10', border: 'border-emerald-500/20', color: 'text-emerald-400',
            fr: 'Mensuel', en: 'Monthly',
          },
        ] as const).map((item) => (
          <div key={item.fr} className="flex items-center gap-2 text-xs text-slate-300">
            <div
              className={`w-6 h-6 rounded-lg border flex items-center justify-center shrink-0 ${item.bg} ${item.border}`}
              style={{ boxShadow: '0 1px 0 rgba(255,255,255,0.06) inset, 0 2px 4px rgba(0,0,0,0.25)' }}
            >
              <item.Icon size={11} className={item.color} />
            </div>
            <span>{lang === 'fr' ? item.fr : item.en}</span>
          </div>
        ))}
      </div>

      {/* Formulaire */}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="email"
          required
          value={email}
          onChange={e => setEmail(e.target.value)}
          placeholder={lang === 'fr' ? 'votre@email.com' : 'your@email.com'}
          className="flex-1 min-w-0 bg-slate-900/80 border border-slate-700/60 rounded-xl px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500/50 transition"
        />
        <button
          type="submit"
          disabled={status === 'loading'}
          className="flex items-center gap-1.5 bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 text-slate-950 font-bold px-4 py-2.5 rounded-xl text-sm transition shrink-0"
        >
          {status === 'loading'
            ? <Loader size={14} className="animate-spin" />
            : <ArrowRight size={14} />}
          {lang === 'fr' ? "S'abonner" : 'Subscribe'}
        </button>
      </form>

      {status === 'error' && (
        <p className="text-xs text-red-400 mt-2">{error}</p>
      )}

      <div className="flex items-center justify-between mt-3">
        <p className="text-slate-600 text-xs">
          {lang === 'fr'
            ? 'Double opt-in — confirmation par email requise.'
            : 'Double opt-in — email confirmation required.'}
        </p>
        {!showUnsub && unsubStatus === 'idle' && (
          <button
            type="button"
            onClick={() => setShowUnsub(true)}
            className="text-slate-600 hover:text-slate-400 text-xs transition flex items-center gap-1"
          >
            <X size={10} />
            {lang === 'fr' ? 'Se désabonner' : 'Unsubscribe'}
          </button>
        )}
      </div>

      {/* Confirmation désabonnement */}
      {showUnsub && unsubStatus === 'idle' && (
        <div className="mt-3 flex items-center gap-2 p-2.5 rounded-xl bg-slate-800/60 border border-slate-700/50">
          <p className="text-slate-400 text-xs flex-1">
            {lang === 'fr'
              ? `Se désabonner avec ${email || 'cet email'} ?`
              : `Unsubscribe ${email || 'this email'} ?`}
          </p>
          <button
            type="button"
            onClick={handleUnsubscribe}
            className="text-xs text-red-400 hover:text-red-300 font-medium transition shrink-0"
          >
            {lang === 'fr' ? 'Confirmer' : 'Confirm'}
          </button>
          <button
            type="button"
            onClick={() => setShowUnsub(false)}
            className="text-xs text-slate-500 hover:text-slate-300 transition shrink-0"
          >
            {lang === 'fr' ? 'Annuler' : 'Cancel'}
          </button>
        </div>
      )}
      {unsubStatus === 'loading' && (
        <p className="text-xs text-slate-500 mt-2 flex items-center gap-1.5">
          <Loader size={11} className="animate-spin" />
          {lang === 'fr' ? 'Désabonnement…' : 'Unsubscribing…'}
        </p>
      )}
      {unsubStatus === 'done' && (
        <p className="text-xs text-slate-400 mt-2">
          {lang === 'fr' ? '✓ Vous avez été désabonné.' : '✓ You have been unsubscribed.'}
        </p>
      )}
      {unsubStatus === 'error' && (
        <p className="text-xs text-red-400 mt-2">
          {lang === 'fr' ? 'Erreur lors du désabonnement.' : 'Error while unsubscribing.'}
        </p>
      )}
    </div>
  );
}
