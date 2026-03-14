// ─── PartnerPage — Programme partenaire Wezea ────────────────────────────────
import { useState, type ReactNode, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Shield, Handshake, FileText, Activity, Percent,
  CheckCircle, Loader, ArrowRight, Building2, Mail, User, Globe, Users,
} from 'lucide-react';
import { useLanguage } from '../i18n/LanguageContext';
import { apiClient } from '../lib/api';
import WezeaLogo from '../components/WezeaLogo';

// ── SkuIcon (local) ──────────────────────────────────────────────────────────
function SkuIcon({ children, color, size = 36 }: { children: ReactNode; color: string; size?: number }) {
  const r = Math.round(size * 0.28);
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
      <div
        className="absolute inset-0 pointer-events-none"
        style={{ borderRadius: r, background: 'linear-gradient(180deg,rgba(255,255,255,0.07) 0%,transparent 50%)' }}
      />
      {children}
    </div>
  );
}

type Status = 'idle' | 'loading' | 'success' | 'error';

export default function PartnerPage() {
  const navigate = useNavigate();
  const { lang } = useLanguage();

  const [form, setForm] = useState({
    first_name: '',
    email: '',
    company: '',
    website: '',
    client_count: '',
  });
  const [status, setStatus] = useState<Status>('idle');
  const [errorMsg, setErrorMsg] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.first_name.trim() || !form.email.trim() || !form.company.trim()) return;

    setStatus('loading');
    setErrorMsg('');
    try {
      await apiClient.post('/partners', {
        first_name: form.first_name.trim(),
        email: form.email.trim().toLowerCase(),
        company: form.company.trim(),
        website: form.website.trim() || undefined,
        client_count: form.client_count || undefined,
      });
      setStatus('success');
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setErrorMsg(
        typeof detail === 'string'
          ? detail
          : lang === 'fr'
            ? 'Une erreur est survenue. Veuillez réessayer.'
            : 'Something went wrong. Please try again.'
      );
      setStatus('error');
    }
  };

  const benefits = [
    {
      icon: <FileText size={18} className="text-cyan-300" />,
      color: '#22d3ee',
      title: lang === 'fr' ? 'Rapports PDF experts' : 'Expert PDF reports',
      desc: lang === 'fr'
        ? 'Offrez des rapports de sécurité PDF complets à vos clients, brandés avec votre logo.'
        : 'Deliver comprehensive security PDF reports to your clients, branded with your logo.',
    },
    {
      icon: <Activity size={18} className="text-violet-300" />,
      color: '#a78bfa',
      title: lang === 'fr' ? 'Surveillance continue' : 'Continuous monitoring',
      desc: lang === 'fr'
        ? 'Surveillez les domaines de vos clients en continu. Alertes automatiques en cas de vulnérabilité.'
        : 'Monitor your clients\' domains continuously. Automatic alerts on vulnerabilities.',
    },
    {
      icon: <Percent size={18} className="text-emerald-300" />,
      color: '#4ade80',
      title: lang === 'fr' ? '-30% à vie' : '-30% lifetime',
      desc: lang === 'fr'
        ? 'Profitez de 30% de réduction sur tous les plans Wezea, à vie, en tant que partenaire actif.'
        : 'Enjoy 30% off all Wezea plans, for life, as an active partner.',
    },
  ];

  return (
    <div className="relative min-h-screen text-slate-100 flex flex-col">
      {/* ── Navbar ── */}
      <nav className="sticky top-0 z-40 border-b border-slate-800/60 bg-slate-950/80 backdrop-blur-xl px-4 py-3">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <button onClick={() => navigate('/')} className="flex items-center gap-2 group">
            <WezeaLogo size="md" showSub />
          </button>
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/login')}
              className="text-sm text-slate-400 hover:text-white transition"
            >
              {lang === 'fr' ? 'Connexion' : 'Login'}
            </button>
            <button
              onClick={() => navigate('/register')}
              className="sku-btn-primary text-xs px-4 py-2 rounded-xl"
            >
              {lang === 'fr' ? 'Créer un compte' : 'Sign up'}
            </button>
          </div>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section className="pt-16 pb-12 px-4 text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <div className="flex justify-center mb-6">
            <SkuIcon color="#a78bfa" size={52}>
              <Handshake size={24} className="text-violet-300 relative z-10" />
            </SkuIcon>
          </div>
          <h1 className="text-3xl sm:text-4xl font-black text-white mb-4">
            {lang === 'fr' ? 'Programme Partenaire' : 'Partner Program'}
          </h1>
          <p className="text-slate-400 text-lg max-w-2xl mx-auto leading-relaxed">
            {lang === 'fr'
              ? 'Vous êtes un professionnel IT, MSP, ou agence web ? Rejoignez notre programme partenaire et proposez des audits de sécurité à vos clients.'
              : 'Are you an IT professional, MSP, or web agency? Join our partner program and offer security audits to your clients.'}
          </p>
        </motion.div>
      </section>

      {/* ── Benefits grid ── */}
      <section className="px-4 pb-12">
        <div className="max-w-4xl mx-auto grid sm:grid-cols-3 gap-5">
          {benefits.map((b, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 + i * 0.1, duration: 0.4 }}
              className="sku-card p-5 flex flex-col items-start gap-3"
            >
              <SkuIcon color={b.color} size={36}>{b.icon}</SkuIcon>
              <h3 className="text-white font-bold text-sm">{b.title}</h3>
              <p className="text-slate-400 text-sm leading-relaxed">{b.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── How it works ── */}
      <section className="px-4 pb-12">
        <div className="max-w-2xl mx-auto">
          <h2 className="text-xl font-bold text-white text-center mb-8">
            {lang === 'fr' ? 'Comment ça marche ?' : 'How does it work?'}
          </h2>
          <div className="space-y-4">
            {([
              {
                step: '1',
                title: lang === 'fr' ? 'Postulez' : 'Apply',
                desc: lang === 'fr'
                  ? 'Remplissez le formulaire ci-dessous avec les informations de votre entreprise.'
                  : 'Fill out the form below with your company information.',
              },
              {
                step: '2',
                title: lang === 'fr' ? 'Validation' : 'Review',
                desc: lang === 'fr'
                  ? 'Notre équipe valide votre candidature sous 48h et active votre essai Pro gratuit de 30 jours.'
                  : 'Our team reviews your application within 48h and activates your free 30-day Pro trial.',
              },
              {
                step: '3',
                title: lang === 'fr' ? 'Scannez et facturez' : 'Scan & bill',
                desc: lang === 'fr'
                  ? 'Utilisez Wezea pour auditer vos clients. Recevez votre code referral et 30% de réduction à vie.'
                  : 'Use Wezea to audit your clients. Get your referral code and 30% lifetime discount.',
              },
            ] as const).map((item, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.3 + i * 0.1, duration: 0.4 }}
                className="flex items-start gap-4"
              >
                <div
                  className="shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold"
                  style={{
                    background: 'linear-gradient(150deg, rgba(167,139,250,0.25) 0%, rgba(167,139,250,0.08) 100%)',
                    border: '1px solid rgba(167,139,250,0.3)',
                    color: '#c4b5fd',
                  }}
                >
                  {item.step}
                </div>
                <div>
                  <h3 className="text-white font-semibold text-sm">{item.title}</h3>
                  <p className="text-slate-400 text-sm mt-0.5">{item.desc}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Registration form ── */}
      <section className="px-4 pb-16" id="partner-form">
        <div className="max-w-lg mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5, duration: 0.4 }}
            className="sku-panel p-6 sm:p-8"
          >
            <div className="flex items-center gap-3 mb-6">
              <SkuIcon color="#a78bfa" size={36}>
                <Shield size={16} className="text-violet-300 relative z-10" />
              </SkuIcon>
              <h2 className="text-white font-bold text-lg">
                {lang === 'fr' ? 'Devenir partenaire' : 'Become a partner'}
              </h2>
            </div>

            <AnimatePresence mode="wait">
              {status === 'success' ? (
                <motion.div
                  key="success"
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="text-center py-6"
                >
                  <div className="flex justify-center mb-4">
                    <SkuIcon color="#4ade80" size={44}>
                      <CheckCircle size={20} className="text-green-300 relative z-10" />
                    </SkuIcon>
                  </div>
                  <h3 className="text-white font-bold text-lg mb-2">
                    {lang === 'fr' ? 'Candidature envoyée !' : 'Application sent!'}
                  </h3>
                  <p className="text-slate-400 text-sm">
                    {lang === 'fr'
                      ? 'Merci pour votre candidature. Notre équipe vous recontactera sous 48h pour activer votre compte partenaire.'
                      : 'Thank you for your application. Our team will contact you within 48h to activate your partner account.'}
                  </p>
                </motion.div>
              ) : (
                <motion.form key="form" onSubmit={handleSubmit} className="space-y-4">
                  {/* Prénom */}
                  <div>
                    <label className="text-xs text-slate-400 mb-1 block flex items-center gap-1.5">
                      <User size={12} />
                      {lang === 'fr' ? 'Prénom *' : 'First name *'}
                    </label>
                    <input
                      type="text"
                      required
                      value={form.first_name}
                      onChange={e => setForm(f => ({ ...f, first_name: e.target.value }))}
                      className="sku-inset w-full px-3 py-2.5 text-sm text-white"
                      placeholder={lang === 'fr' ? 'Jean' : 'John'}
                    />
                  </div>

                  {/* Email */}
                  <div>
                    <label className="text-xs text-slate-400 mb-1 block flex items-center gap-1.5">
                      <Mail size={12} />
                      {lang === 'fr' ? 'Email professionnel *' : 'Professional email *'}
                    </label>
                    <input
                      type="email"
                      required
                      value={form.email}
                      onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                      className="sku-inset w-full px-3 py-2.5 text-sm text-white"
                      placeholder="jean@agence.fr"
                    />
                  </div>

                  {/* Entreprise */}
                  <div>
                    <label className="text-xs text-slate-400 mb-1 block flex items-center gap-1.5">
                      <Building2 size={12} />
                      {lang === 'fr' ? 'Entreprise *' : 'Company *'}
                    </label>
                    <input
                      type="text"
                      required
                      value={form.company}
                      onChange={e => setForm(f => ({ ...f, company: e.target.value }))}
                      className="sku-inset w-full px-3 py-2.5 text-sm text-white"
                      placeholder={lang === 'fr' ? 'Mon Agence Web' : 'My Web Agency'}
                    />
                  </div>

                  {/* Site web */}
                  <div>
                    <label className="text-xs text-slate-400 mb-1 block flex items-center gap-1.5">
                      <Globe size={12} />
                      {lang === 'fr' ? 'Site web' : 'Website'}
                    </label>
                    <input
                      type="url"
                      value={form.website}
                      onChange={e => setForm(f => ({ ...f, website: e.target.value }))}
                      className="sku-inset w-full px-3 py-2.5 text-sm text-white"
                      placeholder="https://agence.fr"
                    />
                  </div>

                  {/* Nombre de clients */}
                  <div>
                    <label className="text-xs text-slate-400 mb-1 block flex items-center gap-1.5">
                      <Users size={12} />
                      {lang === 'fr' ? 'Nombre de clients' : 'Number of clients'}
                    </label>
                    <select
                      value={form.client_count}
                      onChange={e => setForm(f => ({ ...f, client_count: e.target.value }))}
                      className="sku-inset w-full px-3 py-2.5 text-sm text-white"
                    >
                      <option value="">{lang === 'fr' ? 'Sélectionner...' : 'Select...'}</option>
                      <option value="1-10">1 – 10</option>
                      <option value="11-50">11 – 50</option>
                      <option value="50+">50+</option>
                    </select>
                  </div>

                  {/* Error message */}
                  {status === 'error' && errorMsg && (
                    <p className="text-xs text-red-400">{errorMsg}</p>
                  )}

                  {/* Submit */}
                  <button
                    type="submit"
                    disabled={status === 'loading'}
                    className="sku-btn-primary w-full flex items-center justify-center gap-2 py-3 text-sm font-bold rounded-xl"
                  >
                    {status === 'loading'
                      ? <Loader size={16} className="animate-spin" />
                      : <ArrowRight size={16} />
                    }
                    {lang === 'fr' ? 'Envoyer ma candidature' : 'Submit application'}
                  </button>
                </motion.form>
              )}
            </AnimatePresence>
          </motion.div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="mt-auto border-t border-slate-800/60 bg-slate-950/80 py-4 px-6">
        <div className="max-w-5xl mx-auto flex items-center justify-center text-xs text-slate-600">
          &copy; {new Date().getFullYear()} Wezea &mdash; {lang === 'fr' ? 'Tous droits réservés' : 'All rights reserved'}
        </div>
      </footer>
    </div>
  );
}
