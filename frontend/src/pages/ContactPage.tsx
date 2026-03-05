// ─── ContactPage — Formulaire de support ──────────────────────────────────────
import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, CheckCircle, AlertCircle, MessageSquare, Mail, User, Tag } from 'lucide-react';
import { apiClient } from '../lib/api';
import { useLanguage } from '../i18n/LanguageContext';
import PageNavbar from '../components/PageNavbar';

interface Props {
  onBack: () => void;
  onGoClientSpace?: () => void;
  onGoHistory?: () => void;
  onGoAdmin?: () => void;
}

export default function ContactPage({ onBack, onGoClientSpace, onGoHistory, onGoAdmin }: Props) {
  const { lang, t } = useLanguage();

  const SUBJECTS = [
    t('contact_subject_0'),
    t('contact_subject_1'),
    t('contact_subject_2'),
    t('contact_subject_3'),
    t('contact_subject_4'),
    t('contact_subject_5'),
  ];

  const [form, setForm]       = useState({ name: '', email: '', subject: SUBJECTS[0], message: '' });
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [errors, setErrors]   = useState<Record<string, string>>({});

  // Pré-remplir depuis le localStorage si connecté
  useEffect(() => {
    try {
      const raw = localStorage.getItem('user');
      if (raw) {
        const u = JSON.parse(raw);
        setForm(f => ({
          ...f,
          email: u.email ?? f.email,
          name:  u.first_name ? `${u.first_name} ${u.last_name ?? ''}`.trim() : f.name,
        }));
      }
    } catch { /* ignore */ }
  }, []);

  const validate = () => {
    const e: Record<string, string> = {};
    if (!form.name.trim() || form.name.trim().length < 2) e.name = t('contact_err_name');
    if (!form.email.trim() || !form.email.includes('@'))  e.email = t('contact_err_email');
    if (!form.message.trim() || form.message.trim().length < 10) e.message = t('contact_err_message');
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setLoading(true);
    setError(null);
    try {
      await apiClient.post('/contact', form);
      setSuccess(true);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      const msg = Array.isArray(detail)
        ? detail.map((d: any) => d.msg).join(', ')
        : (typeof detail === 'string' ? detail : t('contact_err_generic'));
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen text-slate-100">
      {/* Grille cyber — identique au hero Dashboard */}
      <div className="absolute inset-0 pointer-events-none" style={{ backgroundImage: 'linear-gradient(rgba(34,211,238,1) 1px, transparent 1px), linear-gradient(90deg, rgba(34,211,238,1) 1px, transparent 1px)', backgroundSize: '48px 48px', opacity: 0.025 }} />

      {/* Nav */}
      <PageNavbar
        onBack={onBack}
        title={lang === 'fr' ? 'Contacter le support' : 'Contact support'}
        icon={<MessageSquare size={14} />}
        onGoClientSpace={onGoClientSpace}
        onGoHistory={onGoHistory}
        onGoAdmin={onGoAdmin}
      />

      <div className="max-w-2xl mx-auto px-4 py-12">

        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-10 text-center"
        >
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 mb-5">
            <MessageSquare size={26} className="text-cyan-400" />
          </div>
          <h1 className="text-2xl font-black text-white mb-2" style={{ letterSpacing: '-0.03em' }}>
            {t('contact_heading')}
          </h1>
          <p className="text-slate-400 text-sm leading-relaxed">
            {t('contact_subheading')} <span className="text-slate-200 font-medium">{t('contact_subheading_time')}</span>.
          </p>
        </motion.div>

        {/* Succès */}
        <AnimatePresence>
          {success && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              className="rounded-2xl border border-green-500/25 bg-green-500/8 p-8 text-center"
            >
              <div className="flex justify-center mb-4">
                <div className="p-3 rounded-full bg-green-500/15 border border-green-500/25">
                  <CheckCircle size={28} className="text-green-400" />
                </div>
              </div>
              <h2 className="text-lg font-bold text-green-300 mb-2">{t('contact_success_title')}</h2>
              <p className="text-slate-400 text-sm leading-relaxed mb-6">
                {t('contact_success_body')}
              </p>
              <button
                onClick={onBack}
                className="sku-btn-ghost text-sm px-5 py-2 rounded-xl border border-slate-600/50 hover:border-slate-500 transition-all"
              >
                {t('contact_success_back')}
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Formulaire */}
        {!success && (
          <motion.form
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            onSubmit={handleSubmit}
            className="sku-panel rounded-2xl p-6 sm:p-8 flex flex-col gap-5"
          >
            {/* Nom + Email */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-slate-400 flex items-center gap-1.5 uppercase tracking-wide">
                  <User size={11} />
                  {t('contact_label_name')} *
                </label>
                <input
                  type="text"
                  placeholder={t('contact_placeholder_name')}
                  value={form.name}
                  onChange={e => { setForm(f => ({ ...f, name: e.target.value })); setErrors(x => ({ ...x, name: '' })); }}
                  className={`rounded-xl px-4 py-2.5 text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 transition-all sku-inset ${errors.name ? 'border-red-500/60' : ''}`}
              style={{ border: errors.name ? '1px solid rgba(239,68,68,0.5)' : '1px solid rgba(255,255,255,0.07)' }}
                />
                {errors.name && <span className="text-xs text-red-400">{errors.name}</span>}
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-slate-400 flex items-center gap-1.5 uppercase tracking-wide">
                  <Mail size={11} />
                  {t('contact_label_email')} *
                </label>
                <input
                  type="email"
                  placeholder={t('contact_placeholder_email')}
                  value={form.email}
                  onChange={e => { setForm(f => ({ ...f, email: e.target.value })); setErrors(x => ({ ...x, email: '' })); }}
                  className={`rounded-xl px-4 py-2.5 text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 transition-all sku-inset`}
                  style={{ border: errors.email ? '1px solid rgba(239,68,68,0.5)' : '1px solid rgba(255,255,255,0.07)' }}
                />
                {errors.email && <span className="text-xs text-red-400">{errors.email}</span>}
              </div>
            </div>

            {/* Sujet */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-400 flex items-center gap-1.5 uppercase tracking-wide">
                <Tag size={11} />
                {t('contact_label_subject')}
              </label>
              <select
                value={form.subject}
                onChange={e => setForm(f => ({ ...f, subject: e.target.value }))}
                className="rounded-xl px-4 py-2.5 text-sm text-slate-100 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 transition-all appearance-none cursor-pointer sku-inset"
                style={{ border: '1px solid rgba(255,255,255,0.07)', backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='%2364748b' viewBox='0 0 16 16'%3E%3Cpath d='M7.247 11.14L2.451 5.658C1.885 5.013 2.345 4 3.204 4h9.592a1 1 0 0 1 .753 1.659l-4.796 5.48a1 1 0 0 1-1.506 0z'/%3E%3C/svg%3E")`, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 14px center' }}
              >
                {SUBJECTS.map(s => (
                  <option key={s} value={s} style={{ background: '#1e293b' }}>{s}</option>
                ))}
              </select>
            </div>

            {/* Message */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-400 flex items-center gap-1.5 uppercase tracking-wide">
                <MessageSquare size={11} />
                {t('contact_label_message')} *
              </label>
              <textarea
                rows={6}
                placeholder={t('contact_placeholder_message')}
                value={form.message}
                onChange={e => { setForm(f => ({ ...f, message: e.target.value })); setErrors(x => ({ ...x, message: '' })); }}
                className="rounded-xl px-4 py-2.5 text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 transition-all resize-none sku-inset"
                style={{ border: errors.message ? '1px solid rgba(239,68,68,0.5)' : '1px solid rgba(255,255,255,0.07)' }}
              />
              <div className="flex justify-between items-center">
                {errors.message
                  ? <span className="text-xs text-red-400">{errors.message}</span>
                  : <span />
                }
                <span className={`text-xs ml-auto ${form.message.length > 4500 ? 'text-orange-400' : 'text-slate-600'}`}>
                  {form.message.length}/5000
                </span>
              </div>
            </div>

            {/* Erreur globale */}
            {error && (
              <div className="flex items-start gap-2.5 rounded-xl border border-red-500/25 bg-red-500/8 px-4 py-3 text-sm text-red-300">
                <AlertCircle size={15} className="shrink-0 mt-0.5" />
                {error}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="flex items-center justify-center gap-2 px-6 py-3 rounded-xl font-semibold text-sm transition-all disabled:opacity-60 disabled:cursor-not-allowed"
              style={{
                background: loading ? 'rgba(34,211,238,0.15)' : 'linear-gradient(135deg, #22d3ee, #3b82f6)',
                color: loading ? '#22d3ee' : '#0d1117',
                border: loading ? '1px solid rgba(34,211,238,0.3)' : 'none',
              }}
            >
              {loading ? (
                <>
                  <div className="w-4 h-4 border-2 border-cyan-400/40 border-t-cyan-400 rounded-full animate-spin" />
                  {t('contact_sending')}
                </>
              ) : (
                <>
                  <Send size={14} />
                  {t('contact_submit')}
                </>
              )}
            </button>
          </motion.form>
        )}

        {/* Infos complémentaires */}
        {!success && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.3 }}
            className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-3"
          >
            <div className="sku-card rounded-xl px-4 py-3 flex items-start gap-3">
              <Mail size={15} className="text-cyan-400 shrink-0 mt-0.5" />
              <div>
                <div className="text-xs font-semibold text-slate-300 mb-0.5">{t('contact_info_email_title')}</div>
                <div className="text-xs text-slate-500">{t('contact_info_email_delay')}</div>
              </div>
            </div>
            <div className="sku-card rounded-xl px-4 py-3 flex items-start gap-3">
              <CheckCircle size={15} className="text-green-400 shrink-0 mt-0.5" />
              <div>
                <div className="text-xs font-semibold text-slate-300 mb-0.5">{t('contact_info_ack_title')}</div>
                <div className="text-xs text-slate-500">{t('contact_info_ack_body')}</div>
              </div>
            </div>
          </motion.div>
        )}

      </div>
    </div>
  );
}
