// ─── Dashboard.tsx — Page principale de CyberHealth Scanner ──────────────────
//
// États :
//   idle     → Barre de recherche + hero
//   scanning → ScanConsole animée
//   success  → ScoreGauge + FindingCards + FinancialRisk
//   error    → Message d'erreur avec retry
//
import { useState, useEffect, useCallback, FormEvent, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Shield, Search, ArrowRight, RotateCcw,
  FileDown, Globe, AlertTriangle, Lock, X, UserPlus,
  CheckCircle, ChevronDown, Zap, Eye, Star, BookOpen, Bell, Building2,
} from 'lucide-react';

import { useLanguage } from '../i18n/LanguageContext';
import { useAuth } from '../contexts/AuthContext';
import { useScanner } from '../hooks/useScanner';
import { ScanConsole } from '../components/ScanConsole';
import { EmailCaptureModal } from '../components/EmailCaptureModal';
import PricingModal from '../components/PricingModal';
import NewsletterWidget from '../components/NewsletterWidget';
import OnboardingWizard from '../components/OnboardingWizard';
import DashboardResults from '../components/DashboardResults';
import DashboardNavbar from '../components/DashboardNavbar';
import { apiClient, getScanLimits } from '../lib/api';
import type { RateLimitInfo } from '../lib/api';
import {
  captureScanStarted, captureScanCompleted, captureScanFailed,
  captureRegisterCtaClicked, capturePricingModalOpened,
  capturePdfDownloaded, captureMonitoringDomainAdded,
} from '../lib/analytics';
import type { PricingSource, RegisterCtaSource } from '../lib/analytics';

// ─────────────────────────────────────────────────────────────────────────────

// CountUp — importé depuis DashboardHero (utilisé aussi dans les sections inférieures)
import DashboardHero, { CountUp } from '../components/DashboardHero';


// ─── SkuIcon — importé depuis le composant partagé ──────────────────────────
// (Voir src/components/SkuIcon.tsx pour l'implémentation)

export default function Dashboard() {
  const navigate = useNavigate();
  const location = useLocation();
  const locationState = location.state as { scanUuid?: string } | null;
  const [domain, setDomain]         = useState('');
  const [modalOpen, setModalOpen]   = useState(false);

  const [pwModalOpen, setPwModalOpen]       = useState(false);
  const [pricingModalOpen, setPricingModalOpen] = useState(false);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError,   setPdfError]   = useState<string | null>(null);
  // Monitoring
  const [monitoringOpen, setMonitoringOpen] = useState(false);
  const [monitoredDomains, setMonitoredDomains] = useState<Array<{domain:string;last_score:number|null;last_risk_level:string|null;last_scan_at:string|null;}>>([]);
  const [monitoringLoading, setMonitoringLoading] = useState(false);
  const [monitoringInput, setMonitoringInput] = useState('');
  const [pwCurrent, setPwCurrent]       = useState('');
  const [pwNew, setPwNew]               = useState('');
  const [pwConfirm, setPwConfirm]       = useState('');
  const [pwLoading, setPwLoading]       = useState(false);
  const [pwError, setPwError]           = useState('');
  const [pwSuccess, setPwSuccess]       = useState(false);
  const [scanLimits, setScanLimits]     = useState<RateLimitInfo | null>(null);
  const [publicStats, setPublicStats]   = useState<{ total_scans: number; industry_avg?: number } | null>(null);
  const [faqOpen, setFaqOpen]           = useState<number | null>(null);
  const [newsletterConfirmed, setNewsletterConfirmed] = useState(false);
  const [previousScore,  setPreviousScore]  = useState<number | null>(null);
  const [previousFindingsCount, setPreviousFindingsCount] = useState<number | null>(null);
  const [domainHistory,  setDomainHistory]  = useState<number[]>([]);
  const [blogLinks,      setBlogLinks]      = useState<Array<{ id: number; match_keyword: string; article_title: string; article_url: string }>>([]);
  const [stickyDismissed, setStickyDismissed] = useState(false);
  // Onboarding wizard — affiché une fois après l'inscription
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const inputRef                    = useRef<HTMLInputElement>(null);
  const resultsRef                  = useRef<HTMLDivElement>(null);

  const { lang, t } = useLanguage();
  const { user } = useAuth();
  const scanner = useScanner();

  // ── Helpers analytics ────────────────────────────────────────────────────────
  const openPricing = (source: PricingSource) => {
    capturePricingModalOpened(source);
    setPricingModalOpen(true);
  };
  const goRegister = (source: RegisterCtaSource) => {
    captureRegisterCtaClicked(source);
    navigate('/register');
  };
  const goLogin = (source: RegisterCtaSource) => {
    captureRegisterCtaClicked(source);
    navigate('/login');
  };

  // ── Charger le quota hebdomadaire ───────────────────────────────────────────
  const fetchScanLimits = useCallback(async () => {
    try {
      const limits = await getScanLimits();
      setScanLimits(limits);
    } catch {
      // silencieux — ne pas bloquer l'UX
    }
  }, []);

  useEffect(() => {
    fetchScanLimits();
  }, [fetchScanLimits]);

  useEffect(() => {
    apiClient.get('/public/stats').then(r => setPublicStats(r.data)).catch(() => {});
    apiClient.get('/public/blog-links').then(r => setBlogLinks(r.data)).catch(() => {});
  }, []);

  // ── Onboarding wizard — afficher une fois après l'inscription ──────────────
  useEffect(() => {
    if (!user) return;
    const key = `wezea_onboarding_done_${user.id}`;
    if (!localStorage.getItem(key)) {
      setOnboardingOpen(true);
    }
  }, [user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const closeOnboarding = () => {
    if (user) {
      localStorage.setItem(`wezea_onboarding_done_${user.id}`, '1');
    }
    setOnboardingOpen(false);
  };

  // ── Chargement d'un scan historique (depuis HistoryPage via location state) ─
  useEffect(() => {
    if (!locationState?.scanUuid) return;
    scanner.loadFromHistory(locationState.scanUuid);
    // Clear the state to prevent re-loading on re-render
    navigate('/', { replace: true, state: {} });
    setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 600);
  }, [locationState?.scanUuid]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Pré-remplir le champ domaine dès qu'un résultat est disponible ─────────
  // Permet de relancer un scan d'un seul clic après chargement depuis l'historique
  useEffect(() => {
    if (scanner.status === 'success' && scanner.result?.domain && !domain) {
      setDomain(scanner.result.domain);
    }
  }, [scanner.status, scanner.result?.domain]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Confirmation newsletter (retour depuis le lien email) ──────────────────
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('newsletter_confirmed') === '1') {
      setNewsletterConfirmed(true);
      window.history.replaceState({}, '', window.location.pathname);
      setTimeout(() => setNewsletterConfirmed(false), 6000);
    }
    const domainParam = params.get('domain');
    if (domainParam) {
      setDomain(domainParam);
      window.history.replaceState({}, '', window.location.pathname);
      setTimeout(() => inputRef.current?.focus(), 300);
    }
  }, []);

  // ── Téléchargement PDF direct (Starter / Pro) ──────────────────────────────
  const downloadPdf = useCallback(async () => {
    if (!scanner.result || pdfLoading) return;
    setPdfLoading(true);
    setPdfError(null);
    try {
      const { data } = await apiClient.post('/generate-pdf', { ...scanner.result, lang }, { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([data], { type: 'application/pdf' }));
      const a   = document.createElement('a');
      a.href    = url;
      a.download = `cyberhealth-${scanner.result.domain}-${new Date().toISOString().slice(0,10)}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      capturePdfDownloaded(scanner.result.domain, scanner.result.security_score, user?.plan ?? 'free');
    } catch (err: any) {
      // Quand responseType: 'blob', les erreurs HTTP arrivent aussi sous forme de Blob
      let msg = lang === 'fr' ? 'Erreur lors de la génération du PDF. Réessayez.' : 'Error generating PDF. Please try again.';
      if (err?.response?.data instanceof Blob) {
        try {
          const text = await err.response.data.text();
          const json = JSON.parse(text);
          msg = json?.detail?.message ?? json?.detail ?? json?.message ?? text;
        } catch { /* ignore parse error */ }
      } else {
        msg = err?.response?.data?.detail?.message ?? err?.response?.data?.message ?? err?.message ?? msg;
      }
      setPdfError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally { setPdfLoading(false); }
  }, [scanner.result, pdfLoading, user?.plan, lang]);

  // ── Monitoring ──────────────────────────────────────────────────────────────
  const isPremium = user?.plan === 'starter' || user?.plan === 'pro' || user?.plan === 'dev';

  const fetchMonitoredDomains = useCallback(async () => {
    if (!isPremium) return;
    setMonitoringLoading(true);
    try {
      const { data } = await apiClient.get('/monitoring/domains');
      setMonitoredDomains(data);
    } catch { /* silencieux */ }
    finally { setMonitoringLoading(false); }
  }, [isPremium]);

  useEffect(() => { if (isPremium) fetchMonitoredDomains(); }, [fetchMonitoredDomains, isPremium]);

  const addToMonitoring = useCallback(async (domain: string) => {
    try {
      await apiClient.post('/monitoring/domains', { domain });
      captureMonitoringDomainAdded(domain);
      await fetchMonitoredDomains();
    } catch { /* silencieux */ }
  }, [fetchMonitoredDomains]);

  const removeFromMonitoring = useCallback(async (domain: string) => {
    try {
      await apiClient.delete(`/monitoring/domains/${domain}`);
      await fetchMonitoredDomains();
    } catch { /* silencieux */ }
  }, [fetchMonitoredDomains]);

  // Rafraîchir après chaque scan (succès ou erreur) + événements analytics
  useEffect(() => {
    const timers: ReturnType<typeof setTimeout>[] = [];
    if (scanner.status === 'success' || scanner.status === 'error') {
      fetchScanLimits();
    }
    if (scanner.status === 'success' && scanner.result) {
      // Scroll vers les résultats une fois la transition AnimatePresence terminée.
      // Timeline : console exit (200ms) + results enter (400ms) + marge (100ms) = 700ms
      // behavior:'instant' — évite qu'une animation de scroll rate sa cible si la page
      // est déjà au bon endroit ou si le navigateur mobile interfère avec smooth scroll.
      timers.push(setTimeout(() => {
        resultsRef.current?.scrollIntoView({ behavior: 'instant', block: 'start' });
      }, 700));
      captureScanCompleted({
        domain:         scanner.result.domain,
        score:          scanner.result.security_score,
        risk_level:     scanner.result.risk_level,
        findings_count: scanner.result.findings?.length ?? 0,
        duration_ms:    scanner.result.scan_duration_ms ?? undefined,
      });
      // Comparaison avec le scan précédent du même domaine + sparkline historique
      if (user) {
        apiClient.get('/scans/history').then(res => {
          const scans: Array<{ domain: string; security_score: number; findings_count: number; created_at: string }> = res.data;
          // Tri newest-first : [0]=actuel, [1]=précédent
          const byNewest = scans
            .filter(s => s.domain === scanner.result!.domain)
            .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
          // Tri chronologique (oldest-first) pour la sparkline
          const byOldest = [...byNewest].reverse();
          setPreviousScore(byNewest.length >= 2 ? byNewest[1].security_score : null);
          setPreviousFindingsCount(byNewest.length >= 2 ? byNewest[1].findings_count : null);
          setDomainHistory(byOldest.map(s => s.security_score));
        }).catch(() => { setPreviousScore(null); setPreviousFindingsCount(null); setDomainHistory([]); });
      }
    }
    if (scanner.status === 'scanning') {
      setPreviousScore(null);   // reset à chaque nouveau scan
      setPreviousFindingsCount(null);
      setDomainHistory([]);
      // Délai 500ms : laisse le temps à AnimatePresence de terminer l'exit du panel
      // résultats (~150ms) + début de l'enter de ScanConsole (~400ms opacity+y anim)
      timers.push(setTimeout(() => {
        resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 500));
    }
    if (scanner.status === 'error') {
      timers.push(setTimeout(() => {
        resultsRef.current?.scrollIntoView({ behavior: 'instant', block: 'start' });
      }, 400));
      captureScanFailed(scanner.result?.domain ?? domain, scanner.error ?? undefined);
    }
    return () => timers.forEach(clearTimeout);
  }, [scanner.status, fetchScanLimits]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleChangePassword = async (e: FormEvent) => {
    e.preventDefault();
    setPwError('');
    if (pwNew !== pwConfirm) {
      setPwError(lang === 'fr' ? 'Les mots de passe ne correspondent pas' : 'Passwords do not match');
      return;
    }
    if (pwNew.length < 8) {
      setPwError(lang === 'fr' ? 'Minimum 8 caractères' : 'Minimum 8 characters');
      return;
    }
    setPwLoading(true);
    try {
      await apiClient.post('/auth/change-password', {
        current_password: pwCurrent,
        new_password: pwNew,
      });
      setPwSuccess(true);
      setTimeout(() => {
        setPwModalOpen(false);
        setPwSuccess(false);
        setPwCurrent(''); setPwNew(''); setPwConfirm('');
      }, 1800);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setPwError(detail || (lang === 'fr' ? 'Erreur lors du changement' : 'Change failed'));
    } finally {
      setPwLoading(false);
    }
  };

  // ── Réinitialisation + scroll vers le haut ─────────────────────────────────
  const handleReset = () => {
    scanner.reset();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleSubmit = async (e: FormEvent, overrideDomain?: string) => {
    e.preventDefault();
    const target = (overrideDomain ?? domain).trim();
    if (!target) return;
    setDomain(target);
    captureScanStarted(target);
    // Pré-position instantanée vers la zone de scan (pas de smooth — évite le conflit
    // avec AnimatePresence quand les résultats précédents sont en cours d'exit)
    resultsRef.current?.scrollIntoView({ behavior: 'instant', block: 'start' });
    await scanner.startScan(target, lang);
    // Note : le scroll vers ScanConsole est géré dans le useEffect sur scanner.status === 'scanning'
  };

  // ── Lancer un scan depuis l'onboarding wizard ──────────────────────────────
  const handleOnboardingScan = (d: string) => {
    closeOnboarding();
    setDomain(d);
    const fakeEvent = { preventDefault: () => {} } as FormEvent;
    // Délai 350ms : laisse l'animation d'exit de la modale onboarding se terminer
    // avant de démarrer le scan, sinon le scroll/ScanConsole se produisent derrière l'overlay.
    setTimeout(() => handleSubmit(fakeEvent, d), 350);
  };


  const isIdle     = scanner.status === 'idle';
  const isScanning = scanner.status === 'scanning';
  const isSuccess  = scanner.status === 'success';
  const isError    = scanner.status === 'error';

  return (
    <div className="min-h-screen flex flex-col text-slate-100">




      {/* ── Navigation ──────────────────────────────────────────────────────── */}
      <DashboardNavbar
        scannerStatus={scanner.status}
        scannerResult={scanner.result}
        onReset={handleReset}
        onOpenPdfModal={() => setModalOpen(true)}
        onOpenPricing={openPricing}
        onOpenPasswordModal={() => setPwModalOpen(true)}
        goLogin={goLogin}
        goRegister={goRegister}
      />

      {/* ── Hero + Barre de recherche ────────────────────────────────────────── */}
      <DashboardHero
        isIdle={isIdle}
        isScanning={isScanning}
        domain={domain}
        setDomain={setDomain}
        inputRef={inputRef}
        handleSubmit={handleSubmit}
        scanLimits={scanLimits}
        publicStats={publicStats}
        goRegister={goRegister}
        openPricing={openPricing}
      />

      {/* ── Corps principal ──────────────────────────────────────────────────── */}
      <main ref={resultsRef} className="flex-1 max-w-6xl w-full mx-auto px-4 pb-16">
        <AnimatePresence mode="wait">

          {/* ── Console de scan ───────────────────────────────────────── */}
          {isScanning && (
            <motion.div
              key="console"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="flex justify-center py-6"
            >
              <ScanConsole
                logs={scanner.consoleLogs}
                progress={scanner.progress}
                domain={domain}
              />
            </motion.div>
          )}

          {/* ── Erreur ────────────────────────────────────────────────── */}
          {isError && (
            <motion.div
              key="error"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="max-w-lg mx-auto py-12 text-center"
            >
              {scanner.rateLimitData ? (
                /* ── Erreur : limite de scans atteinte ─────────────────── */
                <>
                  <div className="p-4 rounded-full bg-orange-500/10 border border-orange-500/20 w-fit mx-auto mb-4">
                    <Lock size={28} className="text-orange-400" />
                  </div>
                  <h3 className="text-white font-bold text-lg mb-2">
                    {lang === 'fr' ? 'Limite journalière atteinte' : 'Daily limit reached'}
                  </h3>
                  <p className="text-slate-400 text-sm mb-4">{scanner.error}</p>

                  {/* Compteur utilisé */}
                  <div className="flex items-center justify-center mb-6">
                    <div className="flex items-center gap-2 px-4 py-2 rounded-xl bg-orange-500/10 border border-orange-500/20 text-orange-400 text-xs font-mono">
                      <span>{scanner.rateLimitData.used}/{scanner.rateLimitData.limit}</span>
                      <span className="text-orange-400/60">
                        {lang === 'fr' ? "scan(s) utilisé(s) aujourd'hui" : 'scan(s) used today'}
                      </span>
                    </div>
                  </div>

                  {/* CTA inscription — uniquement pour les anonymes */}
                  {!user && (
                    <div className="bg-gradient-to-b from-cyan-950/50 to-slate-900 border border-cyan-500/30 rounded-2xl p-5 mb-5 text-left">
                      <div className="flex items-center gap-2 mb-2">
                        <UserPlus size={15} className="text-cyan-400" />
                        <p className="text-cyan-400 font-bold text-sm">
                          {lang === 'fr' ? 'Compte gratuit — 5 scans/jour' : 'Free account — 5 scans/day'}
                        </p>
                      </div>
                      <p className="text-slate-400 text-xs mb-4 leading-relaxed">
                        {lang === 'fr'
                          ? 'Créez un compte en 30 secondes et obtenez 5 scans par jour, un historique de vos analyses et bien plus.'
                          : 'Sign up in 30 seconds and get 5 scans per day, analysis history, and more.'}
                      </p>
                      <button
                        onClick={() => { handleReset(); navigate('/register'); }}
                        className="w-full py-2.5 rounded-xl bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-bold text-sm transition-all shadow-lg shadow-cyan-900/30"
                      >
                        {lang === 'fr' ? 'Créer mon compte gratuit →' : 'Create my free account →'}
                      </button>
                    </div>
                  )}

                  {/* CTA upgrade — free connecté */}
                  {user && user.plan === 'free' && (
                    <div className="rounded-2xl overflow-hidden mb-5 text-left"
                      style={{ border: '1px solid rgba(34,211,238,0.2)', background: 'linear-gradient(135deg,rgba(8,60,80,0.6) 0%,rgba(15,21,30,0.95) 100%)' }}>
                      <div className="px-5 pt-5 pb-4">
                        <div className="flex items-center gap-2 mb-2">
                          <Zap size={14} className="text-cyan-400" />
                          <p className="text-cyan-400 font-bold text-sm">
                            {lang === 'fr' ? 'Passez Starter — scans illimités' : 'Go Starter — unlimited scans'}
                          </p>
                        </div>
                        <p className="text-slate-400 text-xs mb-4 leading-relaxed">
                          {lang === 'fr'
                            ? 'Votre quota de 5 scans/jour est épuisé. Passez Starter pour analyser sans limite, accéder au monitoring et aux rapports PDF complets.'
                            : 'Your 5 scans/day quota is up. Go Starter for unlimited scans, monitoring, and full PDF reports.'}
                        </p>
                        <button
                          onClick={() => openPricing('scan_limit_error')}
                          className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-bold transition-all"
                          style={{ background: 'linear-gradient(135deg,rgba(34,211,238,0.22),rgba(59,130,246,0.18))', border: '1px solid rgba(34,211,238,0.35)', color: '#a5f3fc' }}>
                          <Zap size={13} />
                          {lang === 'fr' ? 'Voir les offres →' : 'View plans →'}
                        </button>
                      </div>
                      <div className="px-5 pb-4 flex items-center justify-center gap-5">
                        {(lang === 'fr'
                          ? ['✓ Scans illimités', '✓ Monitoring', '✓ PDF complet']
                          : ['✓ Unlimited scans', '✓ Monitoring', '✓ Full PDF']
                        ).map(f => <span key={f} className="text-[10px] text-cyan-700 font-mono">{f}</span>)}
                      </div>
                    </div>
                  )}

                  <button
                    onClick={handleReset}
                    className="flex items-center gap-2 mx-auto px-5 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 font-medium text-sm transition-colors"
                  >
                    <RotateCcw size={15} />
                    {lang === 'fr' ? 'Retour' : 'Back'}
                  </button>
                </>
              ) : (
                /* ── Erreur générique ──────────────────────────────────── */
                <>
                  <div className="p-4 rounded-full bg-red-500/10 border border-red-500/20 w-fit mx-auto mb-4">
                    <AlertTriangle size={28} className="text-red-400" />
                  </div>
                  <h3 className="text-white font-bold text-lg mb-2">{t('scan_error')}</h3>
                  <p className="text-slate-400 text-sm mb-6">{scanner.error}</p>
                  <button
                    onClick={handleReset}
                    className="flex items-center gap-2 mx-auto px-5 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium text-sm transition-colors"
                  >
                    <RotateCcw size={15} />
                    {t('btn_retry')}
                  </button>
                </>
              )}
            </motion.div>
          )}

          {/* ── Résultats ─────────────────────────────────────────────── */}
          {isSuccess && scanner.result && (
            <DashboardResults
              scanResult={scanner.result}
              previousScore={previousScore}
              previousFindingsCount={previousFindingsCount}
              domainHistory={domainHistory}
              publicStats={publicStats}
              blogLinks={blogLinks}
              monitoringOpen={monitoringOpen}
              setMonitoringOpen={setMonitoringOpen}
              monitoredDomains={monitoredDomains}
              monitoringLoading={monitoringLoading}
              monitoringInput={monitoringInput}
              setMonitoringInput={setMonitoringInput}
              addToMonitoring={addToMonitoring}
              removeFromMonitoring={removeFromMonitoring}
              downloadPdf={downloadPdf}
              pdfLoading={pdfLoading}
              pdfError={pdfError}
              openEmailCaptureModal={() => setModalOpen(true)}
              openPricingModal={(source) => { capturePricingModalOpened(source); setPricingModalOpen(true); }}
            />
          )}

        </AnimatePresence>

        {/* ══════════════════════════════════════════════════════════════════════
            SECTIONS MARKETING — visibles uniquement en état idle
        ══════════════════════════════════════════════════════════════════════ */}
        {isIdle && (
          <div className="mt-16 flex flex-col gap-24 pb-8">

            {/* ── 1. RÉSULTATS TYPIQUES ─────────────────────────────────────── */}
            <section>
              <div className="text-center mb-10">
                <span className="text-xs font-semibold text-cyan-400 tracking-widest uppercase mb-3 block">
                  {lang === 'fr' ? 'Résultats typiques' : 'Typical findings'}
                </span>
                <h2 className="text-2xl md:text-3xl font-black text-white mb-3">
                  {lang === 'fr' ? 'Ce qu\'un audit révèle en 60\u00a0secondes' : 'What an audit reveals in 60\u00a0seconds'}
                </h2>
                <p className="text-slate-500 text-sm max-w-lg mx-auto">
                  {lang === 'fr'
                    ? 'Trois catégories de failles fréquemment détectées — credentials exposés, vulnérabilités applicatives, configuration email défaillante.'
                    : 'Three categories of frequently detected issues — exposed credentials, application vulnerabilities, misconfigured email.'}
                </p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl mx-auto">
                {/* Card 1 — Secret Scanner */}
                <div className="flex flex-col gap-4 rounded-2xl border border-red-500/20 bg-red-500/5 p-6">
                  <div className="flex items-start justify-between">
                    <div className="p-2.5 rounded-xl" style={{ background: '#f8717118', border: '1px solid #f8717130' }}>
                      <svg width="20" height="20" fill="none" stroke="#f87171" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                        <path d="M12 2a10 10 0 1 0 0 20A10 10 0 0 0 12 2z"/><path d="M12 8v4m0 4h.01"/>
                      </svg>
                    </div>
                    <span className="text-[10px] font-bold px-2 py-1 rounded-full bg-red-500/15 text-red-400 border border-red-500/25 uppercase tracking-wide">
                      CRITICAL
                    </span>
                  </div>
                  <div>
                    <p className="text-white font-bold text-sm mb-1.5">
                      {lang === 'fr' ? 'Secret Scanner' : 'Secret Scanner'}
                    </p>
                    <p className="text-slate-400 text-xs leading-relaxed mb-3">
                      {lang === 'fr'
                        ? 'Credential exposé dans le source HTML — clé API ou token d\'accès visible publiquement.'
                        : 'Credential exposed in HTML source — API key or access token publicly visible.'}
                    </p>
                    <div className="rounded-lg bg-slate-950/80 border border-slate-800 p-3 font-mono text-[10px] text-slate-500 leading-relaxed">
                      <span className="text-slate-600">{'// script.js:42'}</span>{'\n'}
                      <span className="text-red-400">{'access_token'}</span>
                      <span className="text-slate-500">{' = '}</span>
                      <span className="text-amber-400">{'"sk_live_••••••"'}</span>
                    </div>
                  </div>
                </div>

                {/* Card 2 — DAST */}
                <div className="flex flex-col gap-4 rounded-2xl border border-red-500/20 bg-red-500/5 p-6">
                  <div className="flex items-start justify-between">
                    <div className="p-2.5 rounded-xl" style={{ background: '#f8717118', border: '1px solid #f8717130' }}>
                      <svg width="20" height="20" fill="none" stroke="#f87171" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                      </svg>
                    </div>
                    <span className="text-[10px] font-bold px-2 py-1 rounded-full bg-red-500/15 text-red-400 border border-red-500/25 uppercase tracking-wide">
                      CRITICAL
                    </span>
                  </div>
                  <div>
                    <p className="text-white font-bold text-sm mb-1.5">
                      {lang === 'fr' ? 'DAST actif' : 'Active DAST'}
                    </p>
                    <p className="text-slate-400 text-xs leading-relaxed mb-3">
                      {lang === 'fr'
                        ? 'Panneau d\'administration accessible sans authentification — exposition directe à l\'attaque.'
                        : 'Administration panel accessible without authentication — direct attack surface.'}
                    </p>
                    <div className="rounded-lg bg-slate-950/80 border border-slate-800 p-3 font-mono text-[10px] leading-relaxed">
                      <span className="text-green-400">{'GET'}</span>
                      <span className="text-slate-400">{' /admin/dashboard'}</span>
                      <br/>
                      <span className="text-slate-600">{'→ '}</span>
                      <span className="text-red-400">{'200 OK'}</span>
                      <span className="text-slate-600">{' (no auth)'}</span>
                    </div>
                  </div>
                </div>

                {/* Card 3 — Email config */}
                <div className="flex flex-col gap-4 rounded-2xl border border-amber-500/20 bg-amber-500/5 p-6">
                  <div className="flex items-start justify-between">
                    <div className="p-2.5 rounded-xl" style={{ background: '#fbbf2418', border: '1px solid #fbbf2430' }}>
                      <svg width="20" height="20" fill="none" stroke="#fbbf24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                        <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/>
                      </svg>
                    </div>
                    <span className="text-[10px] font-bold px-2 py-1 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/25 uppercase tracking-wide">
                      HIGH
                    </span>
                  </div>
                  <div>
                    <p className="text-white font-bold text-sm mb-1.5">
                      {lang === 'fr' ? 'Configuration email' : 'Email configuration'}
                    </p>
                    <p className="text-slate-400 text-xs leading-relaxed mb-3">
                      {lang === 'fr'
                        ? 'Politique DMARC trop permissive — le domaine peut être usurpé pour envoyer des emails de phishing.'
                        : 'DMARC policy too permissive — domain can be spoofed to send phishing emails.'}
                    </p>
                    <div className="rounded-lg bg-slate-950/80 border border-slate-800 p-3 font-mono text-[10px] leading-relaxed">
                      <span className="text-slate-500">{'v=DMARC1; '}</span>
                      <span className="text-amber-400">{'p=none'}</span>
                      <span className="text-slate-600">{'; rua='}</span>
                      <br/>
                      <span className="text-slate-600">{'→ '}</span>
                      <span className="text-amber-400">{lang === 'fr' ? 'Aucune protection' : 'No enforcement'}</span>
                    </div>
                  </div>
                </div>
              </div>
            </section>

            {/* ── 2. FONCTIONNALITÉS ───────────────────────────────────────── */}
            <section>
              <div className="text-center mb-10">
                <span className="text-xs font-semibold text-cyan-400 tracking-widest uppercase mb-3 block">
                  {lang === 'fr' ? 'Couverture complète' : 'Full coverage'}
                </span>
                <h2 className="text-2xl md:text-3xl font-black text-white mb-3">
                  {lang === 'fr' ? '40+ points de contrôle sur 4\u00a0domaines' : '40+ checks across 4\u00a0security domains'}
                </h2>
                <p className="text-slate-500 text-sm max-w-md mx-auto">
                  {lang === 'fr'
                    ? 'Infrastructure passive, scan actif DAST, credentials exposés, conformité NIS2\u00a0& RGPD — un audit complet sans installation.'
                    : 'Passive infrastructure, active DAST scan, exposed credentials, NIS2\u00a0& GDPR compliance — full audit with no installation.'}
                </p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 max-w-4xl mx-auto">
                {([
                  { c:'#22d3ee', free:true,  title:'SSL / TLS',
                    desc: lang==='fr' ? 'Validité, expiration, version, cipher suites' : 'Validity, expiry, version, cipher suites',
                    paths: <><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></> },
                  { c:'#60a5fa', free:true,  title:'DNS',
                    desc: lang==='fr' ? 'SPF, DMARC, DNSSEC, configuration des zones' : 'SPF, DMARC, DNSSEC, zone configuration',
                    paths: <><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></> },
                  { c:'#c084fc', free:true,  title:'HTTP Headers',
                    desc: lang==='fr' ? 'CSP, HSTS, X-Frame-Options, permissions' : 'CSP, HSTS, X-Frame-Options, permissions',
                    paths: <><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></> },
                  { c:'#fb923c', free:true,  title: lang==='fr' ? 'Ports ouverts' : 'Open ports',
                    desc: lang==='fr' ? 'Scan des ports exposés, services détectés' : 'Exposed port scan, detected services',
                    paths: <><path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><circle cx="12" cy="20" r="1" fill="#fb923c"/></> },
                  { c:'#f87171', free:true,  title: lang==='fr' ? 'Réputation' : 'Reputation',
                    desc: lang==='fr' ? 'Blacklists email, DNSBL, signalements malware' : 'Email blacklists, DNSBL, malware reports',
                    paths: <><circle cx="12" cy="8" r="6"/><path d="M15.477 12.89L17 22l-5-3-5 3 1.523-9.11"/></> },
                  { c:'#4ade80', free:true,  title:'Technologies',
                    desc: lang==='fr' ? 'CMS, frameworks, versions exposées' : 'CMS, frameworks, exposed versions',
                    paths: <><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></> },
                  { c:'#2dd4bf', free:false, title: lang==='fr' ? 'Sécurité email' : 'Email security',
                    desc: lang==='fr' ? 'MX, SPF strict, DKIM, politique DMARC' : 'MX, strict SPF, DKIM, DMARC policy',
                    paths: <><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></> },
                  { c:'#f472b6', free:false, title: lang==='fr' ? 'Sous-domaines' : 'Subdomains',
                    desc: lang==='fr' ? 'Certificats, sous-domaines exposés' : 'Certificates, exposed subdomains',
                    paths: <><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></> },
                  { c:'#f87171', free:false, title:'CVE / Versions',
                    desc: lang==='fr' ? 'Versions avec vulnérabilités connues (CVE)' : 'Versions with known vulnerabilities (CVE)',
                    paths: <><ellipse cx="12" cy="13" rx="4" ry="5"/><path d="M10 8c0-1.1.9-2 2-2s2 .9 2 2"/><path d="M9 8 7 6M15 8l2-2"/><path d="M8 12H5M19 12h-3"/><path d="M8 16H5M19 16h-3"/></> },
                  { c:'#fb923c', free:false, title: lang==='fr' ? 'DAST actif' : 'Active DAST',
                    desc: lang==='fr' ? 'Scan dynamique des endpoints, panneaux admin, headers de sécurité' : 'Dynamic endpoint scanning, admin panels, security headers',
                    paths: <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></> },
                  { c:'#a78bfa', free:false, title: lang==='fr' ? 'Secret Scanner' : 'Secret Scanner',
                    desc: lang==='fr' ? 'Détection de credentials, tokens et clés API exposés dans le source' : 'Detection of credentials, tokens and API keys exposed in source',
                    paths: <><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/><path d="M11 8v3m0 3h.01"/></> },
                  { c:'#4ade80', free:false, title: lang==='fr' ? 'Conformité NIS2 / RGPD' : 'NIS2 / GDPR compliance',
                    desc: lang==='fr' ? 'Vérifications alignées sur les exigences réglementaires européennes' : 'Checks aligned with European regulatory requirements',
                    paths: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="15" x2="15" y2="15"/><line x1="9" y1="11" x2="11" y2="11"/></> },
                ] as Array<{c:string,free:boolean,title:string,desc:string,paths:React.ReactNode}>).map((f, i) => (
                  <div key={i} className={`flex items-start gap-3 rounded-xl border p-4 ${f.free ? 'border-slate-800 bg-slate-900/40' : 'border-cyan-500/15 bg-cyan-500/5'}`}>
                    <div style={{
                      width:38,height:38,borderRadius:10,flexShrink:0,
                      display:'flex',alignItems:'center',justifyContent:'center',
                      background:`linear-gradient(150deg,${f.c}30 0%,${f.c}0d 100%)`,
                      border:`1px solid ${f.c}33`,
                      boxShadow:`0 4px 16px ${f.c}20,0 1px 3px rgba(0,0,0,.4),inset 0 1px 0 ${f.c}33,inset 0 -1px 0 rgba(0,0,0,.3)`,
                      position:'relative',overflow:'hidden',
                    }}>
                      <div style={{position:'absolute',inset:0,borderRadius:9,background:'linear-gradient(180deg,rgba(255,255,255,0.07) 0%,transparent 50%)',pointerEvents:'none'}}/>
                      <svg width="18" height="18" fill="none" stroke={f.c} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                        {f.paths}
                      </svg>
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <p className="text-white font-semibold text-sm">{f.title}</p>
                        {!f.free && (
                          <span className="text-[10px] bg-cyan-500/15 text-cyan-400 border border-cyan-500/20 px-1.5 py-0.5 rounded font-semibold shrink-0">Pro</span>
                        )}
                      </div>
                      <p className="text-slate-500 text-xs leading-relaxed">{f.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {/* ── 2b. CONFORMITÉ NIS2 / RGPD ───────────────────────────────── */}
            <section>
              <div className="max-w-4xl mx-auto overflow-hidden rounded-2xl relative"
                style={{ background: 'linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%)', border: '1px solid rgba(129,140,248,0.25)' }}>
                {/* Glow blobs */}
                <div className="absolute -top-16 -left-16 w-64 h-64 rounded-full blur-3xl pointer-events-none" style={{ background: 'rgba(99,102,241,0.12)' }} />
                <div className="absolute -bottom-16 -right-16 w-64 h-64 rounded-full blur-3xl pointer-events-none" style={{ background: 'rgba(34,211,238,0.08)' }} />

                <div className="relative flex flex-col lg:flex-row items-center gap-8 p-8 md:p-10">
                  {/* Left — copy */}
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-4 flex-wrap">
                      <span className="text-[10px] font-bold px-2.5 py-1 rounded-full uppercase tracking-widest" style={{ background: 'rgba(99,102,241,0.15)', border: '1px solid rgba(99,102,241,0.3)', color: '#a5b4fc' }}>
                        Conformité réglementaire
                      </span>
                      <span className="text-[10px] font-bold px-2.5 py-1 rounded-full" style={{ background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.2)', color: '#818cf8' }}>NIS2</span>
                      <span className="text-[10px] font-bold px-2.5 py-1 rounded-full" style={{ background: 'rgba(167,139,250,0.1)', border: '1px solid rgba(167,139,250,0.2)', color: '#a78bfa' }}>RGPD</span>
                    </div>
                    <h2 className="text-2xl md:text-3xl font-black text-white mb-3 leading-tight">
                      {lang === 'fr' ? 'NIS2\u00a0& RGPD — score et plan\u00a0d\'action' : 'NIS2\u00a0& GDPR — score and action\u00a0plan'}
                    </h2>
                    <p className="text-slate-400 text-sm leading-relaxed mb-5 max-w-lg">
                      {lang === 'fr'
                        ? 'Chaque vulnérabilité technique est corrélée aux articles des directives en vigueur. Un rapport structuré, exportable pour vos auditeurs ou votre DPO.'
                        : 'Each technical vulnerability is mapped to the relevant regulatory articles. A structured report, exportable for your auditors or DPO.'}
                    </p>

                    {/* 3 compliance points */}
                    <div className="flex flex-col gap-2 mb-6">
                      {[
                        lang === 'fr' ? '12 critères techniques mappés sur Art. 21 NIS2 & Art. 32 RGPD' : '12 technical criteria mapped to NIS2 Art. 21 & GDPR Art. 32',
                        lang === 'fr' ? 'Score de conformité /100 avec statut pass / warn / fail par critère' : 'Compliance score /100 with pass / warn / fail per criterion',
                        lang === 'fr' ? 'Plan d\'action priorisé exportable PDF pour vos auditeurs' : 'Prioritised action plan exportable as PDF for your auditors',
                      ].map((point, i) => (
                        <div key={i} className="flex items-start gap-2.5 text-xs text-slate-300">
                          <span className="mt-0.5 shrink-0 w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold" style={{ background: 'rgba(99,102,241,0.2)', border: '1px solid rgba(99,102,241,0.35)', color: '#a5b4fc' }}>✓</span>
                          {point}
                        </div>
                      ))}
                    </div>

                    <button
                      onClick={() => navigate('/conformite-nis2')}
                      className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-bold text-white transition-all hover:opacity-90"
                      style={{ background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)' }}
                    >
                      {lang === 'fr' ? 'Tester ma conformité NIS2' : 'Test my NIS2 compliance'}
                      <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                    </button>
                  </div>

                  {/* Right — compliance mini-grid */}
                  <div className="shrink-0 w-full lg:w-64 flex flex-col gap-2">
                    {[
                      { label: 'HTTPS & TLS',           status: 'pass', reg: 'NIS2' },
                      { label: 'DMARC anti-usurpation', status: 'fail', reg: 'NIS2' },
                      { label: 'En-têtes sécurité',     status: 'warn', reg: 'RGPD' },
                      { label: 'SPF email',              status: 'pass', reg: 'NIS2' },
                      { label: 'Ports dangereux',        status: 'fail', reg: 'NIS2' },
                      { label: 'Credentials exposés',   status: 'blur', reg: 'RGPD' },
                      { label: 'DNSSEC + CAA',          status: 'blur', reg: 'NIS2' },
                    ].map((row, i) => {
                      const isBlur = row.status === 'blur';
                      const cfg = {
                        pass: { icon: '✓', color: '#4ade80', bg: 'rgba(74,222,128,0.1)',  border: 'rgba(74,222,128,0.2)'  },
                        fail: { icon: '✗', color: '#f87171', bg: 'rgba(248,113,113,0.1)', border: 'rgba(248,113,113,0.2)' },
                        warn: { icon: '⚠', color: '#fbbf24', bg: 'rgba(251,191,36,0.1)',  border: 'rgba(251,191,36,0.2)'  },
                        blur: { icon: '?', color: '#64748b', bg: 'rgba(100,116,139,0.1)', border: 'rgba(100,116,139,0.2)' },
                      }[row.status as 'pass'|'fail'|'warn'|'blur'];
                      return (
                        <div key={i} className={`flex items-center justify-between px-3 py-2 rounded-lg text-xs ${isBlur ? 'blur-[3px]' : ''}`}
                          style={{ background: cfg.bg, border: `1px solid ${cfg.border}` }}>
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-[11px]" style={{ color: cfg.color }}>{cfg.icon}</span>
                            <span className="text-slate-300 font-mono">{row.label}</span>
                          </div>
                          <span className="text-[9px] font-bold px-1.5 py-0.5 rounded" style={{ background: 'rgba(99,102,241,0.15)', color: '#a5b4fc', border: '1px solid rgba(99,102,241,0.2)' }}>{row.reg}</span>
                        </div>
                      );
                    })}
                    <p className="text-slate-600 text-[10px] text-center mt-1">
                      {lang === 'fr' ? '+ 5 critères supplémentaires avec un compte' : '+ 5 more criteria with an account'}
                    </p>
                  </div>
                </div>
              </div>
            </section>

            {/* ── 2b. RAPPORT EXEMPLE ──────────────────────────────────────── */}
            <section>
              <div className="text-center mb-10">
                <span className="text-xs font-semibold text-cyan-400 tracking-widest uppercase mb-3 block">
                  {lang === 'fr' ? 'Exemple de résultat' : 'Sample result'}
                </span>
                <h2 className="text-2xl md:text-3xl font-black text-white mb-3">
                  {lang === 'fr' ? 'Un rapport structuré, actionnable, partageable' : 'A structured, actionable, shareable report'}
                </h2>
                <p className="text-slate-500 text-sm max-w-md mx-auto">
                  {lang === 'fr'
                    ? 'Chaque problème est priorisé par criticité avec une explication et une marche à suivre.'
                    : 'Each issue is prioritised by severity with an explanation and clear next steps.'}
                </p>
              </div>

              <div className="max-w-4xl mx-auto flex flex-col lg:flex-row gap-6 items-start">
                {/* Mock report panel */}
                <div className="flex-1 rounded-2xl overflow-hidden border border-slate-700/60 bg-slate-900/80 shadow-2xl">
                  {/* Header */}
                  <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
                    <div>
                      <p className="text-white font-mono font-bold text-sm">exemple-agence.fr</p>
                      <p className="text-slate-500 text-xs mt-0.5">{lang === 'fr' ? 'Analysé il y a 2 minutes' : 'Analyzed 2 minutes ago'}</p>
                    </div>
                    <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-amber-500/10 border border-amber-500/25">
                      <span className="text-2xl font-black font-mono text-amber-400">74</span>
                      <span className="text-slate-500 text-xs font-mono">/100</span>
                    </div>
                  </div>
                  {/* Check rows */}
                  <div className="divide-y divide-slate-800/60">
                    {([
                      { label: lang === 'fr' ? 'Certificat SSL' : 'SSL certificate',  status: 'ok',   value: lang === 'fr' ? 'Valide · 89j' : 'Valid · 89d' },
                      { label: lang === 'fr' ? 'HTTPS forcé' : 'Forced HTTPS',        status: 'ok',   value: lang === 'fr' ? 'Actif' : 'Active' },
                      { label: 'DMARC',                                                status: 'warn', value: 'p=none' },
                      { label: 'SPF',                                                  status: 'warn', value: lang === 'fr' ? '+all détecté' : '+all detected' },
                      { label: lang === 'fr' ? 'Port 8080' : 'Port 8080',             status: 'err',  value: lang === 'fr' ? 'Exposé' : 'Exposed' },
                      { label: lang === 'fr' ? 'Listes noires' : 'Blacklists',        status: 'ok',   value: lang === 'fr' ? 'Propre (52)' : 'Clean (52)' },
                      { label: lang === 'fr' ? 'Domaine' : 'Domain',                  status: 'ok',   value: lang === 'fr' ? '187j restants' : '187d left' },
                    ] as Array<{ label: string; status: 'ok' | 'warn' | 'err'; value: string }>).map((row, i) => {
                      const cfg = {
                        ok:   { symbol: '✓', color: '#4ade80', bg: 'text-emerald-400' },
                        warn: { symbol: '⚠', color: '#fbbf24', bg: 'text-amber-400' },
                        err:  { symbol: '✗', color: '#f87171', bg: 'text-red-400' },
                      }[row.status];
                      return (
                        <div key={i} className="flex items-center justify-between px-5 py-3">
                          <span className="flex items-center gap-2 text-xs text-slate-300 font-mono">
                            <span className={cfg.bg}>{cfg.symbol}</span>
                            {row.label}
                          </span>
                          <span className={`text-xs font-mono font-semibold ${cfg.bg}`}>{row.value}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Feature points */}
                <div className="flex flex-col gap-4 lg:w-64 shrink-0">
                  {([
                    {
                      color: '#22d3ee',
                      icon: <CheckCircle size={14} className="text-cyan-300" />,
                      title: lang === 'fr' ? 'Score global /100' : 'Overall score /100',
                      desc:  lang === 'fr'
                        ? 'Un score unique pour mesurer et suivre l\'évolution de la sécurité de votre domaine.'
                        : 'A single score to measure and track your domain\'s security over time.',
                    },
                    {
                      color: '#818cf8',
                      icon: <Shield size={14} className="text-indigo-300" />,
                      title: lang === 'fr' ? 'Problèmes priorisés' : 'Prioritised issues',
                      desc:  lang === 'fr'
                        ? 'Critique, élevé, moyen, faible — traitez d\'abord ce qui compte vraiment.'
                        : 'Critical, high, medium, low — fix what matters most first.',
                    },
                    {
                      color: '#4ade80',
                      icon: <FileDown size={14} className="text-green-300" />,
                      title: lang === 'fr' ? 'Rapport PDF Pro' : 'Pro PDF report',
                      desc:  lang === 'fr'
                        ? 'Exportez un rapport complet à remettre à votre client, avec votre marque.'
                        : 'Export a full report to deliver to your client, with your own branding.',
                    },
                    {
                      color: '#fb923c',
                      icon: <Bell size={14} className="text-orange-300" />,
                      title: lang === 'fr' ? 'Monitoring continu' : 'Continuous monitoring',
                      desc:  lang === 'fr'
                        ? 'Soyez alerté dès qu\'un problème apparaît sur vos domaines clients.'
                        : 'Get alerted as soon as an issue appears on your client domains.',
                    },
                  ] as Array<{ color: string; icon: React.ReactNode; title: string; desc: string }>).map((pt, i) => (
                    <div key={i} className="flex items-start gap-3 p-4 rounded-xl"
                      style={{ border: `1px solid ${pt.color}20`, background: `${pt.color}08` }}>
                      <div className="p-1.5 rounded-lg shrink-0"
                        style={{ background: `${pt.color}18`, border: `1px solid ${pt.color}30` }}>
                        {pt.icon}
                      </div>
                      <div>
                        <p className="text-white text-xs font-bold mb-0.5">{pt.title}</p>
                        <p className="text-slate-500 text-[11px] leading-relaxed">{pt.desc}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </section>

            {/* ── 2c. FONCTIONNALITÉS PRO ──────────────────────────────────── */}
            <section>
              <div className="text-center mb-10">
                <span className="text-xs font-semibold text-cyan-400 tracking-widest uppercase mb-3 block">
                  {lang === 'fr' ? 'Scan dynamique' : 'Dynamic scanning'}
                </span>
                <h2 className="text-2xl md:text-3xl font-black text-white mb-3">
                  {lang === 'fr' ? 'Au-delà de l\'analyse passive' : 'Beyond passive analysis'}
                </h2>
                <p className="text-slate-500 text-sm max-w-lg mx-auto">
                  {lang === 'fr'
                    ? 'Automatisation, intégrations et personnalisation pour les équipes techniques et les agences digitales.'
                    : 'Automation, integrations and customisation for technical teams and digital agencies.'}
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 max-w-4xl mx-auto">
                {([
                  {
                    color: '#22d3ee',
                    icon: (
                      <svg width="20" height="20" fill="none" stroke="#22d3ee" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                        <path d="M18 8h1a4 4 0 0 1 0 8h-1"/><path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"/><line x1="6" y1="1" x2="6" y2="4"/><line x1="10" y1="1" x2="10" y2="4"/><line x1="14" y1="1" x2="14" y2="4"/>
                      </svg>
                    ),
                    title: lang === 'fr' ? 'Webhooks en temps réel' : 'Real-time webhooks',
                    desc: lang === 'fr'
                      ? 'Recevez les événements de scan (scan.completed, alert.triggered, score.dropped) directement dans Zapier, Slack ou votre CI/CD. Signature HMAC-SHA256 incluse.'
                      : 'Receive scan events (scan.completed, alert.triggered, score.dropped) directly in Zapier, Slack or your CI/CD. HMAC-SHA256 signing included.',
                    tags: ['Zapier', 'Slack', 'CI/CD', 'n8n'],
                  },
                  {
                    color: '#c084fc',
                    icon: (
                      <svg width="20" height="20" fill="none" stroke="#c084fc" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                        <path d="M20.24 12.24a6 6 0 0 0-8.49-8.49L5 10.5V19h8.5z"/><line x1="16" y1="8" x2="2" y2="22"/><line x1="17.5" y1="15" x2="9" y2="15"/>
                      </svg>
                    ),
                    title: lang === 'fr' ? 'Rapports en marque blanche' : 'White-label reports',
                    desc: lang === 'fr'
                      ? 'Personnalisez les rapports PDF avec votre logo, couleurs et nom d\'entreprise. Idéal pour facturer vos audits à vos clients sans mentionner Wezea.'
                      : 'Customise PDF reports with your logo, colours and company name. Perfect for reselling audits to clients without mentioning Wezea.',
                    tags: [lang === 'fr' ? 'Logo custom' : 'Custom logo', lang === 'fr' ? 'Couleurs' : 'Colours', 'PDF'],
                  },
                  {
                    color: '#4ade80',
                    icon: (
                      <svg width="20" height="20" fill="none" stroke="#4ade80" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                      </svg>
                    ),
                    title: lang === 'fr' ? 'Badge SVG dynamique' : 'Dynamic SVG badge',
                    desc: lang === 'fr'
                      ? 'Affichez votre score de sécurité en temps réel sur votre site, README GitHub ou signature d\'email. Le badge se met à jour automatiquement après chaque scan.'
                      : 'Show your real-time security score on your website, GitHub README or email signature. The badge updates automatically after each scan.',
                    tags: ['README', 'HTML', 'Markdown'],
                  },
                  {
                    color: '#fb923c',
                    icon: (
                      <svg width="20" height="20" fill="none" stroke="#fb923c" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                      </svg>
                    ),
                    title: lang === 'fr' ? 'Export & accès API' : 'Export & API access',
                    desc: lang === 'fr'
                      ? 'Exportez l\'historique de vos scans en JSON ou CSV. Intégrez Wezea dans vos scripts et outils via la clé API Bearer — sans dépendre du navigateur.'
                      : 'Export your scan history as JSON or CSV. Integrate Wezea into your scripts and tools via Bearer API key — without relying on a browser.',
                    tags: ['JSON', 'CSV', 'API key', 'Bearer'],
                  },
                ] as Array<{color:string;icon:React.ReactNode;title:string;desc:string;tags:string[]}>).map((f, i) => (
                  <div key={i} className="relative flex flex-col gap-4 rounded-2xl p-6 overflow-hidden"
                    style={{ border: `1px solid ${f.color}25`, background: `linear-gradient(135deg, ${f.color}08 0%, rgba(15,21,30,0.8) 100%)` }}>
                    <div className="absolute top-0 right-0 w-24 h-24 rounded-full blur-3xl pointer-events-none"
                      style={{ background: `${f.color}15` }} />
                    <div className="flex items-center gap-3">
                      <div className="p-2.5 rounded-xl shrink-0"
                        style={{ background: `${f.color}15`, border: `1px solid ${f.color}30` }}>
                        {f.icon}
                      </div>
                      <p className="text-white font-bold text-sm leading-snug">{f.title}</p>
                    </div>
                    <p className="text-slate-400 text-xs leading-relaxed">{f.desc}</p>
                    <div className="flex flex-wrap gap-1.5 mt-auto">
                      {f.tags.map(tag => (
                        <span key={tag} className="text-[10px] font-mono px-2 py-0.5 rounded-full"
                          style={{ background: `${f.color}12`, border: `1px solid ${f.color}25`, color: f.color }}>
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              <div className="text-center mt-8">
                <button
                  onClick={() => openPricing('pro_features_section')}
                  className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-sm font-bold transition-all"
                  style={{ background: 'linear-gradient(135deg,rgba(34,211,238,0.18),rgba(59,130,246,0.14))', border: '1px solid rgba(34,211,238,0.3)', color: '#a5f3fc' }}
                >
                  <Zap size={14} />
                  {lang === 'fr' ? 'Passer au plan Pro — 19,90€/mois' : 'Upgrade to Pro — €19.90/mo'}
                  <ArrowRight size={14} />
                </button>
              </div>
            </section>

            {/* ── 2c. POUR QUI ? ────────────────────────────────────────────── */}
            <section>
              <div className="text-center mb-10">
                <span className="text-xs font-semibold text-cyan-400 tracking-widest uppercase mb-3 block">
                  {lang === 'fr' ? 'Pour qui ?' : 'Who is it for?'}
                </span>
                <h2 className="text-2xl md:text-3xl font-black text-white mb-3">
                  {lang === 'fr' ? 'Fait pour les professionnels du web' : 'Built for web professionals'}
                </h2>
                <p className="text-slate-500 text-sm max-w-md mx-auto">
                  {lang === 'fr'
                    ? 'Wezea est utilisé par des agences, freelances et équipes IT pour surveiller la sécurité de leurs clients.'
                    : 'Wezea is used by agencies, freelancers and IT teams to monitor their clients\' security.'}
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 max-w-4xl mx-auto">
                {([
                  {
                    color: '#22d3ee',
                    icon: <Building2 size={20} className="text-cyan-300" />,
                    title: lang === 'fr' ? 'Agences web' : 'Web agencies',
                    desc:  lang === 'fr'
                      ? 'Auditez vos clients et livrez des rapports à votre marque en quelques clics.'
                      : 'Audit your clients and deliver branded reports in just a few clicks.',
                  },
                  {
                    color: '#818cf8',
                    icon: <UserPlus size={20} className="text-indigo-300" />,
                    title: lang === 'fr' ? 'Freelances IT' : 'IT freelancers',
                    desc:  lang === 'fr'
                      ? 'Proposez la sécurité comme service additionnel à haute valeur perçue.'
                      : 'Offer security as a high-value add-on service to your clients.',
                  },
                  {
                    color: '#4ade80',
                    icon: <Globe size={20} className="text-green-300" />,
                    title: lang === 'fr' ? 'MSP & infogérance' : 'MSP & managed IT',
                    desc:  lang === 'fr'
                      ? 'Monitoring continu de l\'ensemble de votre parc clients depuis un tableau de bord.'
                      : 'Continuous monitoring of your entire client portfolio from a single dashboard.',
                  },
                  {
                    color: '#fb923c',
                    icon: <BookOpen size={20} className="text-orange-300" />,
                    title: lang === 'fr' ? 'Développeurs' : 'Developers',
                    desc:  lang === 'fr'
                      ? 'Vérifiez la configuration sécurité de vos projets avant chaque mise en production.'
                      : 'Check your project\'s security configuration before every deployment.',
                  },
                ] as Array<{ color: string; icon: React.ReactNode; title: string; desc: string }>).map((a, i) => (
                  <div key={i}
                    className="flex flex-col gap-3 rounded-2xl p-5"
                    style={{ border: `1px solid ${a.color}22`, background: `linear-gradient(135deg, ${a.color}0a 0%, rgba(15,21,30,0.6) 100%)` }}
                  >
                    <div className="p-2.5 rounded-xl self-start"
                      style={{ background: `${a.color}15`, border: `1px solid ${a.color}30` }}>
                      {a.icon}
                    </div>
                    <p className="text-white font-bold text-sm">{a.title}</p>
                    <p className="text-slate-400 text-xs leading-relaxed">{a.desc}</p>
                  </div>
                ))}
              </div>
            </section>

            {/* ── 3. PREUVES SOCIALES ──────────────────────────────────────── */}
            <section>
              <div className="text-center mb-10">
                <span className="text-xs font-semibold text-cyan-400 tracking-widest uppercase mb-3 block">
                  {lang === 'fr' ? 'Ils nous font confiance' : 'Trusted by'}
                </span>
                <h2 className="text-2xl md:text-3xl font-black text-white mb-3">
                  {lang === 'fr' ? 'Ce que disent nos utilisateurs' : 'What our users say'}
                </h2>
                <p className="text-slate-500 text-sm max-w-md mx-auto">
                  {lang === 'fr'
                    ? 'Des développeurs, responsables IT et agences web qui font confiance à Wezea.'
                    : 'Developers, IT managers and web agencies who trust Wezea.'}
                </p>
              </div>

              {/* Stats */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-3xl mx-auto mb-12">
                {([
                  {
                    countTo: publicStats ? publicStats.total_scans + 500 : 500,
                    suffix: '+',
                    label: lang === 'fr' ? 'Domaines analysés' : 'Domains analyzed',
                    icon: <Search size={16} className="text-cyan-400" />,
                    iconBg: 'bg-cyan-500/10 border-cyan-500/20',
                  },
                  {
                    countTo: 20,
                    suffix: '+',
                    label: lang === 'fr' ? 'Points de contrôle' : 'Checkpoints',
                    icon: <CheckCircle size={16} className="text-green-400" />,
                    iconBg: 'bg-green-500/10 border-green-500/20',
                  },
                  {
                    value: '< 60s',
                    label: lang === 'fr' ? 'Durée d\'analyse' : 'Analysis time',
                    icon: <Zap size={16} className="text-yellow-400" />,
                    iconBg: 'bg-yellow-500/10 border-yellow-500/20',
                  },
                  {
                    value: '100%',
                    label: lang === 'fr' ? 'Sans installation' : 'No install needed',
                    icon: <Eye size={16} className="text-purple-400" />,
                    iconBg: 'bg-purple-500/10 border-purple-500/20',
                  },
                ] as Array<{ countTo?: number; suffix?: string; value?: string; label: string; icon: React.ReactNode; iconBg: string }>).map((s, i) => (
                  <div key={i} className="flex flex-col items-center gap-2 rounded-2xl border border-slate-800 bg-slate-900/50 p-5 text-center">
                    <div className={`p-2 rounded-lg border ${s.iconBg}`}>
                      {s.icon}
                    </div>
                    <p className="text-2xl font-black text-white font-mono">
                      {s.countTo !== undefined
                        ? <CountUp to={s.countTo} suffix={s.suffix ?? ''} />
                        : s.value}
                    </p>
                    <p className="text-slate-500 text-xs leading-tight">{s.label}</p>
                  </div>
                ))}
              </div>

              {/* Testimonials */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-5 max-w-4xl mx-auto">
                {([
                  {
                    name: 'Thomas D.',
                    initials: 'TD',
                    color: '#22d3ee',
                    role: lang === 'fr' ? 'Développeur freelance' : 'Freelance developer',
                    text: lang === 'fr'
                      ? 'J\'ai découvert que mon certificat SSL allait expirer dans 5 jours. Sans Wezea je l\'aurais raté.'
                      : 'I found out my SSL certificate was expiring in 5 days. Without Wezea I would have missed it.',
                  },
                  {
                    name: 'Marie L.',
                    initials: 'ML',
                    color: '#c084fc',
                    role: lang === 'fr' ? 'Responsable IT, PME' : 'IT Manager, SMB',
                    text: lang === 'fr'
                      ? 'Facile à utiliser, rapport clair. On l\'utilise chaque semaine pour surveiller les domaines de nos clients.'
                      : 'Easy to use, clear report. We use it every week to monitor our clients\' domains.',
                  },
                  {
                    name: 'Julien M.',
                    initials: 'JM',
                    color: '#34d399',
                    role: lang === 'fr' ? 'Fondateur SaaS' : 'SaaS Founder',
                    text: lang === 'fr'
                      ? 'Le plan Pro m\'alerte automatiquement dès qu\'une vulnérabilité critique est détectée. Indispensable.'
                      : 'The Pro plan alerts me automatically when a critical vulnerability is detected. Essential.',
                  },
                ] as Array<{ name: string; initials: string; color: string; role: string; text: string }>).map((t, i) => (
                  <div key={i} className="relative flex flex-col gap-3 rounded-2xl border border-slate-800 bg-slate-900/50 p-5 overflow-hidden">
                    {/* Accent ligne haut */}
                    <div className="absolute top-0 left-8 right-8 h-px" style={{ background: `linear-gradient(90deg, transparent, ${t.color}55, transparent)` }} />
                    <div className="flex gap-0.5">
                      {[...Array(5)].map((_, j) => (
                        <Star key={j} size={12} className="text-yellow-400 fill-yellow-400" />
                      ))}
                    </div>
                    <p className="text-slate-300 text-sm leading-relaxed flex-1">
                      <span className="text-slate-500 text-base mr-0.5">"</span>
                      {t.text}
                      <span className="text-slate-500 text-base ml-0.5">"</span>
                    </p>
                    <div className="pt-3 border-t border-slate-800 flex items-center gap-3">
                      <div
                        className="w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold shrink-0"
                        style={{ background: `${t.color}18`, border: `1px solid ${t.color}35`, color: t.color }}
                      >
                        {t.initials}
                      </div>
                      <div>
                        <p className="text-white font-semibold text-sm leading-tight">{t.name}</p>
                        <p className="text-slate-500 text-xs">{t.role}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {/* ── 3b. CAS D'USAGE CONCRETS ─────────────────────────────────── */}
            <section>
              <div className="text-center mb-10">
                <span className="text-xs font-semibold text-amber-400 tracking-widest uppercase mb-3 block">
                  {lang === 'fr' ? 'Situations réelles' : 'Real scenarios'}
                </span>
                <h2 className="text-2xl md:text-3xl font-black text-white mb-3">
                  {lang === 'fr' ? 'Ce que Wezea a découvert pour eux' : 'What Wezea found for them'}
                </h2>
                <p className="text-slate-500 text-sm max-w-md mx-auto">
                  {lang === 'fr'
                    ? 'Des vulnérabilités critiques détectées avant qu\'elles ne causent de vrais incidents.'
                    : 'Critical vulnerabilities detected before they caused real incidents.'}
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-5 max-w-4xl mx-auto">
                {/* Cas 1 — Port RDP exposé */}
                <div className="rounded-2xl border border-red-500/20 bg-gradient-to-br from-red-950/30 to-slate-900/80 p-5 flex flex-col gap-4">
                  <div className="flex items-start gap-3">
                    <div className="p-2 rounded-xl shrink-0" style={{ background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.25)' }}>
                      <AlertTriangle size={16} className="text-red-400" />
                    </div>
                    <div>
                      <p className="text-red-400 text-xs font-semibold uppercase tracking-wider">Critical</p>
                      <p className="text-white font-bold text-sm mt-0.5">
                        {lang === 'fr' ? 'Port RDP 3389 exposé' : 'RDP port 3389 exposed'}
                      </p>
                    </div>
                  </div>
                  {/* Mini scan result */}
                  <div className="rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-3 font-mono text-xs space-y-1.5">
                    <p><span className="text-red-400">●</span> <span className="text-slate-500">Port 3389 :</span> <span className="text-red-300 font-semibold">OUVERT</span></p>
                    <p><span className="text-amber-400">●</span> <span className="text-slate-500">Service :</span> <span className="text-amber-300">Remote Desktop</span></p>
                    <p><span className="text-slate-600">→</span> <span className="text-slate-500">Risque :</span> <span className="text-slate-400">ransomware / brute-force</span></p>
                  </div>
                  <div className="border-t border-slate-800/60 pt-3 flex-1 flex flex-col justify-between gap-3">
                    <p className="text-slate-400 text-xs leading-relaxed">
                      {lang === 'fr'
                        ? 'Un dev a scanné le serveur de son client. Le port était accessible depuis la mise en prod, 6 mois plus tôt. Fermé en 2h après le rapport.'
                        : 'A developer scanned their client\'s server. The port had been open since launch, 6 months earlier. Closed within 2 hours of the report.'}
                    </p>
                    <div className="flex items-center gap-2">
                      <CheckCircle size={12} className="text-green-400 shrink-0" />
                      <span className="text-green-400 text-xs font-medium">
                        {lang === 'fr' ? 'Incident évité' : 'Incident prevented'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Cas 2 — SPF / DMARC manquants */}
                <div className="rounded-2xl border border-amber-500/20 bg-gradient-to-br from-amber-950/25 to-slate-900/80 p-5 flex flex-col gap-4">
                  <div className="flex items-start gap-3">
                    <div className="p-2 rounded-xl shrink-0" style={{ background: 'rgba(251,191,36,0.10)', border: '1px solid rgba(251,191,36,0.22)' }}>
                      <Shield size={16} className="text-amber-400" />
                    </div>
                    <div>
                      <p className="text-amber-400 text-xs font-semibold uppercase tracking-wider">High</p>
                      <p className="text-white font-bold text-sm mt-0.5">
                        {lang === 'fr' ? 'SPF & DMARC manquants' : 'SPF & DMARC missing'}
                      </p>
                    </div>
                  </div>
                  <div className="rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-3 font-mono text-xs space-y-1.5">
                    <p><span className="text-amber-400">●</span> <span className="text-slate-500">SPF :</span> <span className="text-amber-300 font-semibold">ABSENT</span></p>
                    <p><span className="text-amber-400">●</span> <span className="text-slate-500">DMARC :</span> <span className="text-amber-300 font-semibold">ABSENT</span></p>
                    <p><span className="text-slate-600">→</span> <span className="text-slate-500">Risque :</span> <span className="text-slate-400">email spoofing / phishing</span></p>
                  </div>
                  <div className="border-t border-slate-800/60 pt-3 flex-1 flex flex-col justify-between gap-3">
                    <p className="text-slate-400 text-xs leading-relaxed">
                      {lang === 'fr'
                        ? 'Une PME recevait des plaintes de clients ayant reçu de faux emails en son nom. Wezea avait détecté la faille DNS 3 semaines avant les plaintes.'
                        : 'An SMB was getting complaints from clients receiving fake emails in their name. Wezea had flagged the DNS gap 3 weeks before the complaints arrived.'}
                    </p>
                    <div className="flex items-center gap-2">
                      <CheckCircle size={12} className="text-green-400 shrink-0" />
                      <span className="text-green-400 text-xs font-medium">
                        {lang === 'fr' ? 'Réputation préservée' : 'Reputation preserved'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Cas 3 — SSL expirant */}
                <div className="rounded-2xl border border-cyan-500/20 bg-gradient-to-br from-cyan-950/25 to-slate-900/80 p-5 flex flex-col gap-4">
                  <div className="flex items-start gap-3">
                    <div className="p-2 rounded-xl shrink-0" style={{ background: 'rgba(34,211,238,0.10)', border: '1px solid rgba(34,211,238,0.22)' }}>
                      <Lock size={16} className="text-cyan-400" />
                    </div>
                    <div>
                      <p className="text-cyan-400 text-xs font-semibold uppercase tracking-wider">High</p>
                      <p className="text-white font-bold text-sm mt-0.5">
                        {lang === 'fr' ? 'SSL expire dans 4 jours' : 'SSL expires in 4 days'}
                      </p>
                    </div>
                  </div>
                  <div className="rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-3 font-mono text-xs space-y-1.5">
                    <p><span className="text-green-400">●</span> <span className="text-slate-500">SSL :</span> <span className="text-green-300">valide</span></p>
                    <p><span className="text-amber-400">●</span> <span className="text-slate-500">Expiration :</span> <span className="text-amber-300 font-semibold">J&#8209;4</span></p>
                    <p><span className="text-slate-600">→</span> <span className="text-slate-500">Risque :</span> <span className="text-slate-400">site hors ligne / alerte Chrome</span></p>
                  </div>
                  <div className="border-t border-slate-800/60 pt-3 flex-1 flex flex-col justify-between gap-3">
                    <p className="text-slate-400 text-xs leading-relaxed">
                      {lang === 'fr'
                        ? 'L\'alerte monitoring Wezea a envoyé un email le lundi matin. Le certificat a été renouvelé avant que le moindre utilisateur ne voie une erreur.'
                        : 'Wezea\'s monitoring alert sent an email Monday morning. The certificate was renewed before any user encountered an error.'}
                    </p>
                    <div className="flex items-center gap-2">
                      <CheckCircle size={12} className="text-green-400 shrink-0" />
                      <span className="text-green-400 text-xs font-medium">
                        {lang === 'fr' ? 'Zéro interruption' : 'Zero downtime'}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* CTA inline */}
              <div className="text-center mt-8">
                <p className="text-slate-500 text-sm mb-4">
                  {lang === 'fr'
                    ? 'Et votre domaine, il cacherait quoi ?'
                    : 'What would your domain reveal?'}
                </p>
                <button
                  onClick={() => { window.scrollTo({ top: 0, behavior: 'smooth' }); }}
                  className="inline-flex items-center gap-2 text-sm font-semibold text-cyan-400 hover:text-cyan-300 transition-colors"
                >
                  <Search size={14} />
                  {lang === 'fr' ? 'Scanner mon domaine gratuitement →' : 'Scan my domain for free →'}
                </button>
              </div>
            </section>

            {/* ── 4. AGENCES & MSP ─────────────────────────────────────────── */}
            <section className="max-w-4xl mx-auto w-full">
              <div className="rounded-2xl border border-cyan-500/20 bg-gradient-to-br from-cyan-950/40 to-slate-900 p-8 md:p-10">
                <div className="flex flex-col md:flex-row md:items-center gap-8">
                  <div className="flex-1">
                    <span className="text-xs font-semibold text-cyan-400 tracking-widest uppercase mb-3 block">
                      {lang === 'fr' ? 'Pour les agences & MSP' : 'For agencies & MSPs'}
                    </span>
                    <h2 className="text-2xl md:text-3xl font-black text-white mb-3">
                      {lang === 'fr'
                        ? 'Offrez un audit de sécurité à vos clients en 60 secondes'
                        : 'Deliver a security audit to your clients in 60 seconds'}
                    </h2>
                    <p className="text-slate-400 text-sm leading-relaxed mb-6">
                      {lang === 'fr'
                        ? 'Utilisez Wezea comme outil de prospection, de fidélisation ou de service additionnel. Rapport PDF en marque blanche, webhooks vers votre CRM et badge SVG à intégrer sur le site de vos clients.'
                        : 'Use Wezea as a prospecting, retention, or add-on service tool. White-label PDF reports, webhooks to your CRM and SVG badge to embed on your clients\' sites.'}
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-6">
                      {[
                        { Icon: FileDown, bg: 'bg-blue-500/10',    border: 'border-blue-500/20',    color: 'text-blue-400',    fr: 'Rapports PDF en marque blanche',      en: 'White-label PDF reports' },
                        { Icon: Globe,    bg: 'bg-emerald-500/10', border: 'border-emerald-500/20', color: 'text-emerald-400', fr: 'Monitoring illimité (tous vos clients)', en: 'Unlimited monitoring (all your clients)' },
                        { Icon: Bell,     bg: 'bg-cyan-500/10',    border: 'border-cyan-500/20',    color: 'text-cyan-400',    fr: 'Webhooks vers votre CRM / Slack',     en: 'Webhooks to your CRM / Slack' },
                        { Icon: Shield,   bg: 'bg-violet-500/10',  border: 'border-violet-500/20',  color: 'text-violet-400',  fr: 'Badge SVG sur le site du client',     en: 'SVG badge on the client\'s site' },
                      ].map((item, i) => (
                        <div key={i} className="flex items-center gap-2.5 text-sm text-slate-300">
                          <div
                            className={`w-7 h-7 rounded-lg border flex items-center justify-center shrink-0 ${item.bg} ${item.border}`}
                            style={{ boxShadow: '0 1px 0 rgba(255,255,255,0.06) inset, 0 2px 4px rgba(0,0,0,0.25)' }}
                          >
                            <item.Icon size={13} className={item.color} />
                          </div>
                          <span>{lang === 'fr' ? item.fr : item.en}</span>
                        </div>
                      ))}
                    </div>
                    <button
                      onClick={() => openPricing('agences_block')}
                      className="inline-flex items-center gap-2 bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold px-5 py-2.5 rounded-xl text-sm transition"
                    >
                      {lang === 'fr' ? 'Voir les plans Pro' : 'See Pro plans'}
                    </button>
                  </div>
                  <div className="hidden md:flex flex-col gap-3 min-w-[200px]">
                    {[
                      { label: lang === 'fr' ? 'Agences web' : 'Web agencies', color: 'text-cyan-400' },
                      { label: lang === 'fr' ? 'MSP & infogérance' : 'MSP & managed IT', color: 'text-emerald-400' },
                      { label: lang === 'fr' ? 'Freelances IT' : 'IT freelancers', color: 'text-purple-400' },
                      { label: lang === 'fr' ? 'Intégrateurs & devs' : 'Integrators & devs', color: 'text-yellow-400' },
                    ].map((item, i) => (
                      <div key={i} className={`flex items-center gap-2 text-sm font-medium ${item.color}`}>
                        <div className="w-1.5 h-1.5 rounded-full bg-current" />
                        {item.label}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </section>

            {/* ── 5. TARIFS ────────────────────────────────────────────────── */}
            <section className="max-w-4xl mx-auto w-full">
              <div className="text-center mb-10">
                <span className="text-xs font-semibold text-cyan-400 tracking-widest uppercase mb-3 block">
                  {lang === 'fr' ? 'Tarifs' : 'Pricing'}
                </span>
                <h2 className="text-2xl md:text-3xl font-black text-white mb-3">
                  {lang === 'fr' ? 'Simple et transparent' : 'Simple and transparent'}
                </h2>
                <p className="text-slate-500 text-sm max-w-md mx-auto">
                  {lang === 'fr'
                    ? 'Commencez gratuitement. Passez à un plan payant quand vous êtes prêt.'
                    : 'Start for free. Upgrade to a paid plan when you\'re ready.'}
                </p>
              </div>
              {/* FREE — bande horizontale */}
              <div className="rounded-xl border border-slate-800 bg-slate-900/40 px-6 py-4 flex flex-wrap items-center gap-4 mb-6">
                <div className="flex items-baseline gap-2 shrink-0">
                  <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Free</span>
                  <span className="text-lg font-black text-slate-300">0€</span>
                  <span className="text-xs text-slate-600">/{lang === 'fr' ? 'mois' : 'month'}</span>
                </div>
                <div className="w-px h-5 bg-slate-800 shrink-0 hidden sm:block" />
                <ul className="flex flex-wrap gap-x-5 gap-y-1 flex-1">
                  {[
                    { fr: '5 scans / jour', en: '5 scans / day' },
                    { fr: 'Score de sécurité /100', en: 'Security score /100' },
                    { fr: 'Rapport PDF basique', en: 'Basic PDF report' },
                    { fr: 'Historique des scans', en: 'Scan history' },
                  ].map((f, i) => (
                    <li key={i} className="flex items-center gap-1.5 text-xs text-slate-500">
                      <svg width="11" height="11" fill="none" stroke="#475569" strokeWidth="2.5" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>
                      {lang === 'fr' ? f.fr : f.en}
                    </li>
                  ))}
                </ul>
                <button
                  onClick={() => document.getElementById('domain-input')?.focus()}
                  className="shrink-0 px-4 py-2 rounded-lg border border-slate-700/80 text-slate-500 text-xs font-semibold hover:border-slate-600 hover:text-slate-400 transition"
                >
                  {lang === 'fr' ? 'Commencer gratuitement' : 'Start for free'}
                </button>
              </div>

              {/* PLANS PAYANTS — grille 3 colonnes */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-5 items-start">
                {/* STARTER */}
                <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/5 p-6 flex flex-col">
                  <p className="text-sm font-semibold text-emerald-400 mb-1">Starter</p>
                  <div className="mb-1">
                    <span className="text-3xl font-black text-white">9,90€</span>
                    <span className="text-slate-400 text-sm ml-1">/{lang === 'fr' ? 'mois' : 'month'}</span>
                  </div>
                  <p className="text-xs text-slate-500 mb-4">{lang === 'fr' ? 'Idéal pour les PME' : 'Ideal for SMBs'}</p>
                  <ul className="space-y-2.5 flex-1 mb-6">
                    {[
                      { fr: 'Scans illimités', en: 'Unlimited scans' },
                      { fr: 'Rapport PDF avancé + recommandations', en: 'Advanced PDF report + recommendations' },
                      { fr: 'Monitoring continu + alertes email', en: 'Continuous monitoring + email alerts' },
                      { fr: 'Historique complet', en: 'Full history' },
                    ].map((f, i) => (
                      <li key={i} className="flex items-center gap-2.5 text-sm text-slate-300">
                        <svg width="14" height="14" fill="none" stroke="#34d399" strokeWidth="2.5" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>
                        {lang === 'fr' ? f.fr : f.en}
                      </li>
                    ))}
                  </ul>
                  <button
                    onClick={() => openPricing('pricing_section')}
                    className="w-full py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-900 text-sm font-bold transition"
                  >
                    {lang === 'fr' ? 'Choisir Starter' : 'Choose Starter'}
                  </button>
                </div>

                {/* PRO — carte centrale mise en avant */}
                <div className="relative rounded-2xl border-2 border-cyan-500/50 bg-cyan-500/5 p-6 flex flex-col shadow-[0_0_40px_-8px_rgba(34,211,238,0.15)] -mt-2 pb-8">
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <span className="text-[10px] bg-cyan-500 text-slate-900 px-3 py-1 rounded-full font-bold tracking-wide shadow-lg">
                      {lang === 'fr' ? 'Recommandé' : 'Recommended'}
                    </span>
                  </div>
                  <p className="text-sm font-semibold text-cyan-400 mb-1 mt-1">Pro</p>
                  <div className="mb-1">
                    <span className="text-3xl font-black text-white">19,90€</span>
                    <span className="text-slate-400 text-sm ml-1">/{lang === 'fr' ? 'mois' : 'month'}</span>
                  </div>
                  <p className="text-xs text-slate-500 mb-4">{lang === 'fr' ? 'Pour les agences & MSP' : 'For agencies & MSPs'}</p>
                  <ul className="space-y-2.5 flex-1 mb-6">
                    {[
                      { fr: 'Tout le plan Starter', en: 'Everything in Starter' },
                      { fr: 'Monitoring illimité (domaines)', en: 'Unlimited monitoring (domains)' },
                      { fr: 'Rapports en marque blanche', en: 'White-label reports' },
                      { fr: 'Webhooks sortants', en: 'Outbound webhooks' },
                      { fr: 'Badge SVG dynamique', en: 'Dynamic SVG badge' },
                      { fr: 'Export JSON / CSV', en: 'JSON / CSV export' },
                    ].map((f, i) => (
                      <li key={i} className="flex items-center gap-2.5 text-sm text-slate-200">
                        <svg width="14" height="14" fill="none" stroke="#22d3ee" strokeWidth="2.5" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>
                        {lang === 'fr' ? f.fr : f.en}
                      </li>
                    ))}
                  </ul>
                  <button
                    onClick={() => openPricing('pricing_section')}
                    className="w-full py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-900 text-sm font-bold transition"
                  >
                    {lang === 'fr' ? 'Choisir Pro' : 'Choose Pro'}
                  </button>
                </div>

                {/* DEV */}
                <div className="relative rounded-2xl border-2 border-violet-500/40 bg-violet-500/5 p-6 flex flex-col">
                  <p className="text-sm font-semibold text-violet-400 mb-1">Dev</p>
                  <div className="mb-1">
                    <span className="text-3xl font-black text-white">29,90€</span>
                    <span className="text-slate-400 text-sm ml-1">/{lang === 'fr' ? 'mois' : 'month'}</span>
                  </div>
                  <p className="text-xs text-slate-500 mb-4">{lang === 'fr' ? 'API + scan de vos apps' : 'API + scan your apps'}</p>
                  <ul className="space-y-2.5 flex-1 mb-6">
                    {[
                      { fr: 'Tout le plan Pro', en: 'Everything in Pro' },
                      { fr: 'Accès API (clé wsk_)', en: 'API access (wsk_ key)' },
                      { fr: 'Application Scanning', en: 'Application Scanning' },
                    ].map((f, i) => (
                      <li key={i} className="flex items-center gap-2.5 text-sm text-slate-200">
                        <svg width="14" height="14" fill="none" stroke="#a78bfa" strokeWidth="2.5" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>
                        {lang === 'fr' ? f.fr : f.en}
                      </li>
                    ))}
                  </ul>
                  <button
                    onClick={() => openPricing('pricing_section')}
                    className="w-full py-2.5 rounded-xl bg-violet-500 hover:bg-violet-400 text-white text-sm font-bold transition"
                  >
                    {lang === 'fr' ? 'Choisir Dev' : 'Choose Dev'}
                  </button>
                </div>
              </div>
              {/* ── Tableau comparatif ─────────────────────────────────────── */}
              <div className="mt-8 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr>
                      <th className="text-left text-slate-500 font-medium py-3 pr-4 text-xs w-2/5">{lang === 'fr' ? 'Fonctionnalité' : 'Feature'}</th>
                      <th className="text-center text-slate-400 font-semibold py-3 px-2 text-xs">Free</th>
                      <th className="text-center text-emerald-400 font-semibold py-3 px-2 text-xs">Starter</th>
                      <th className="text-center text-cyan-400 font-semibold py-3 px-2 text-xs">Pro</th>
                      <th className="text-center text-violet-400 font-semibold py-3 px-2 text-xs">Dev</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {([
                      { fr: 'Scans / jour',           en: 'Scans / day',                free: '5',            starter: '∞',          pro: '∞',   dev: '∞'   },
                      { fr: 'Rapport PDF',             en: 'PDF report',                 free: '—',            starter: '✓',          pro: '✓',   dev: '✓'   },
                      { fr: 'Historique',              en: 'History',                    free: '20',           starter: '∞',          pro: '∞',   dev: '∞'   },
                      { fr: 'Monitoring continu',      en: 'Continuous monitoring',      free: '—',            starter: '1 domaine',  pro: '∞',   dev: '∞'   },
                      { fr: 'Alertes email',           en: 'Email alerts',               free: '—',            starter: '✓',          pro: '✓',   dev: '✓'   },
                      { fr: 'Marque blanche',          en: 'White-label',                free: '—',            starter: '—',          pro: '✓',   dev: '✓'   },
                      { fr: 'Webhooks sortants',       en: 'Outbound webhooks',          free: '—',            starter: '—',          pro: '✓',   dev: '✓'   },
                      { fr: 'Badge SVG dynamique',     en: 'Dynamic SVG badge',          free: '—',            starter: '—',          pro: '✓',   dev: '✓'   },
                      { fr: 'Export JSON / CSV',       en: 'JSON / CSV export',          free: '—',            starter: '—',          pro: '✓',   dev: '✓'   },
                      { fr: 'Clé API (wsk_)',          en: 'API key (wsk_)',             free: '—',            starter: '—',          pro: '—',   dev: '✓'   },
                      { fr: 'Application Scanning',    en: 'Application Scanning',       free: '—',            starter: '—',          pro: '—',   dev: '✓'   },
                    ] as Array<{fr:string;en:string;free:string;starter:string;pro:string;dev:string}>).map((row, i) => (
                      <tr key={i} className="hover:bg-slate-900/40 transition-colors">
                        <td className="py-3 pr-4 text-slate-400 text-xs">{lang === 'fr' ? row.fr : row.en}</td>
                        <td className="py-3 px-2 text-center text-xs text-slate-500 font-mono">{row.free}</td>
                        <td className="py-3 px-2 text-center text-xs font-mono">
                          <span className={row.starter === '—' ? 'text-slate-700' : row.starter === '✓' ? 'text-emerald-400' : 'text-emerald-300 font-semibold'}>{row.starter}</span>
                        </td>
                        <td className="py-3 px-2 text-center text-xs font-mono">
                          <span className={row.pro === '—' ? 'text-slate-700' : row.pro === '✓' ? 'text-cyan-400' : 'text-cyan-300 font-semibold'}>{row.pro}</span>
                        </td>
                        <td className="py-3 px-2 text-center text-xs font-mono">
                          <span className={row.dev === '—' ? 'text-slate-700' : row.dev === '✓' ? 'text-violet-400' : 'text-violet-300 font-semibold'}>{row.dev}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            {/* ── 6. FAQ ───────────────────────────────────────────────────── */}
            <section className="max-w-2xl mx-auto w-full">
              <div className="text-center mb-10">
                <span className="text-xs font-semibold text-cyan-400 tracking-widest uppercase mb-3 block">FAQ</span>
                <h2 className="text-2xl md:text-3xl font-black text-white mb-3">
                  {lang === 'fr' ? 'Questions fréquentes' : 'Frequently asked questions'}
                </h2>
              </div>
              <div className="flex flex-col gap-2">
                {[
                  {
                    q: lang === 'fr' ? 'L\'analyse est-elle vraiment gratuite ?' : 'Is the analysis really free?',
                    a: lang === 'fr'
                      ? 'Oui, le scan de base est gratuit et sans inscription. Vous obtenez un score de sécurité et les principales vulnérabilités détectées. Les plans payants (Starter 9,90€, Pro 19,90€ et Dev 29,90€) débloquent les checks avancés, le monitoring continu, les rapports PDF détaillés et plus encore.'
                      : 'Yes, the basic scan is free and requires no registration. You get a security score and the main detected vulnerabilities. Paid plans (Starter €9.90, Pro €19.90 and Dev €29.90) unlock advanced checks, continuous monitoring, detailed PDF reports and more.',
                  },
                  {
                    q: lang === 'fr' ? 'Faut-il installer quelque chose sur mon serveur ?' : 'Do I need to install anything on my server?',
                    a: lang === 'fr'
                      ? 'Non. Wezea Security Scanner est entièrement externe : nous analysons votre domaine depuis l\'extérieur, exactement comme le ferait un attaquant. Aucun accès à votre serveur n\'est nécessaire.'
                      : 'No. Wezea Security Scanner is entirely external: we analyse your domain from the outside, exactly as an attacker would. No access to your server is required.',
                  },
                  {
                    q: lang === 'fr' ? 'Mes données sont-elles en sécurité ?' : 'Is my data safe?',
                    a: lang === 'fr'
                      ? 'Vos données sont stockées en Europe, chiffrées au repos et en transit. Nous ne revendons jamais vos informations. Vous pouvez supprimer votre compte et toutes vos données à tout moment depuis l\'espace client (conformité RGPD).'
                      : 'Your data is stored in Europe, encrypted at rest and in transit. We never sell your information. You can delete your account and all your data at any time from the client space (GDPR compliant).',
                  },
                  {
                    q: lang === 'fr' ? 'Puis-je annuler mon abonnement à tout moment ?' : 'Can I cancel my subscription at any time?',
                    a: lang === 'fr'
                      ? 'Oui, sans engagement ni frais. L\'annulation prend effet à la fin de la période en cours : vous gardez l\'accès jusqu\'à la dernière date payée. La gestion de l\'abonnement se fait directement depuis l\'espace client.'
                      : 'Yes, with no commitment or fees. Cancellation takes effect at the end of the current period: you keep access until the last paid date. Subscription management is done directly from the client space.',
                  },
                  {
                    q: lang === 'fr' ? 'Qu\'est-ce que le monitoring continu ?' : 'What is continuous monitoring?',
                    a: lang === 'fr'
                      ? 'Avec les plans Starter et Pro, vous pouvez ajouter vos domaines à la surveillance. Un scan automatique est effectué chaque semaine et vous recevez une alerte email si le score de sécurité baisse en dessous du seuil que vous définissez.'
                      : 'With Starter and Pro plans, you can add your domains to monitoring. An automatic scan is performed every week and you receive an email alert if the security score drops below the threshold you define.',
                  },
                ].map((item, i) => (
                  <div key={i} className="rounded-xl border border-slate-800 bg-slate-900/50 overflow-hidden">
                    <button
                      onClick={() => setFaqOpen(faqOpen === i ? null : i)}
                      className="w-full flex items-center justify-between px-5 py-4 text-left"
                    >
                      <span className="text-white font-semibold text-sm pr-4">{item.q}</span>
                      <ChevronDown
                        size={16}
                        className={`text-slate-500 shrink-0 transition-transform duration-200 ${faqOpen === i ? 'rotate-180' : ''}`}
                      />
                    </button>
                    {faqOpen === i && (
                      <div className="px-5 pb-4 border-t border-slate-800/60">
                        <p className="text-slate-400 text-sm leading-relaxed pt-3">{item.a}</p>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {/* Newsletter */}
              <div className="mt-10">
                <NewsletterWidget prefillEmail={user?.email ?? ''} variant="full" />
              </div>

              {/* CTA final */}
              <div className="mt-6 text-center rounded-2xl border border-cyan-500/20 bg-gradient-to-b from-cyan-950/30 to-slate-900 p-8">
                <Shield size={28} className="text-cyan-400 mx-auto mb-3" />
                <h3 className="text-white font-black text-xl mb-2">
                  {lang === 'fr' ? 'Prêt à sécuriser votre site ?' : 'Ready to secure your site?'}
                </h3>
                <p className="text-slate-500 text-sm mb-5">
                  {lang === 'fr'
                    ? 'Lancez votre premier scan gratuit maintenant — aucune inscription requise.'
                    : 'Run your first free scan now — no registration required.'}
                </p>
                <button
                  onClick={() => document.getElementById('domain-input')?.focus()}
                  className="inline-flex items-center gap-2 bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold px-6 py-3 rounded-xl text-sm transition"
                >
                  <Search size={15} />
                  {lang === 'fr' ? 'Analyser mon site' : 'Analyse my site'}
                </button>
              </div>
            </section>

          </div>
        )}

      </main>

      {/* ── Modaux & bandeaux ─────────────────────────────────────────────────── */}
      {isSuccess && scanner.result && (
        <>
          <EmailCaptureModal
            open={modalOpen}
            onClose={() => setModalOpen(false)}
            onGoLogin={() => { setModalOpen(false); navigate('/login'); }}
            domain={scanner.result.domain}
            score={scanner.result.security_score}
            scanResult={scanner.result}
            userEmail={user?.email}
          />
        </>
      )}

      {/* ── Modal : Pricing / Upgrade Pro ──────────────────────────────── */}
      <PricingModal
        open={pricingModalOpen}
        onClose={() => setPricingModalOpen(false)}
      />

      {/* ── Modal : Changer le mot de passe ─────────────────────────────── */}
      <AnimatePresence>
        {pwModalOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm px-4"
            onClick={() => { if (!pwLoading) { setPwModalOpen(false); setPwError(''); setPwSuccess(false); setPwCurrent(''); setPwNew(''); setPwConfirm(''); } }}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              onClick={e => e.stopPropagation()}
              className="w-full max-w-sm bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl p-6"
            >
              <div className="flex items-center justify-between mb-5">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
                    <Lock size={15} className="text-cyan-400" />
                  </div>
                  <h2 className="text-white font-bold text-sm">
                    {lang === 'fr' ? 'Changer le mot de passe' : 'Change password'}
                  </h2>
                </div>
                <button
                  onClick={() => { setPwModalOpen(false); setPwError(''); setPwSuccess(false); setPwCurrent(''); setPwNew(''); setPwConfirm(''); }}
                  className="text-slate-500 hover:text-white transition p-1 rounded"
                >
                  <X size={16} />
                </button>
              </div>
              {pwSuccess ? (
                <div className="text-center py-6">
                  <div className="text-3xl mb-2">✅</div>
                  <p className="text-emerald-400 font-medium text-sm">
                    {lang === 'fr' ? 'Mot de passe mis à jour !' : 'Password updated!'}
                  </p>
                </div>
              ) : (
                <form onSubmit={handleChangePassword} className="space-y-3">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1 font-medium">
                      {lang === 'fr' ? 'Mot de passe actuel' : 'Current password'}
                    </label>
                    <input
                      type="password"
                      value={pwCurrent}
                      onChange={e => setPwCurrent(e.target.value)}
                      required
                      autoComplete="current-password"
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-cyan-500 transition"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1 font-medium">
                      {lang === 'fr' ? 'Nouveau mot de passe' : 'New password'}
                    </label>
                    <input
                      type="password"
                      value={pwNew}
                      onChange={e => setPwNew(e.target.value)}
                      required
                      autoComplete="new-password"
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-cyan-500 transition"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1 font-medium">
                      {lang === 'fr' ? 'Confirmer le nouveau mot de passe' : 'Confirm new password'}
                    </label>
                    <input
                      type="password"
                      value={pwConfirm}
                      onChange={e => setPwConfirm(e.target.value)}
                      required
                      autoComplete="new-password"
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-cyan-500 transition"
                    />
                  </div>
                  {pwError && (
                    <p className="text-red-400 text-xs font-mono bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                      {pwError}
                    </p>
                  )}
                  <button
                    type="submit"
                    disabled={pwLoading}
                    className="w-full mt-1 py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 text-slate-950 font-bold text-sm transition flex items-center justify-center gap-2"
                  >
                    {pwLoading ? (
                      <div className="w-4 h-4 border-2 border-slate-950/30 border-t-slate-950 rounded-full animate-spin" />
                    ) : (
                      <>{lang === 'fr' ? 'Mettre à jour' : 'Update password'}</>
                    )}
                  </button>
                </form>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Toast — confirmation newsletter */}
      <AnimatePresence>
        {newsletterConfirmed && (
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 24 }}
            className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 bg-emerald-950 border border-emerald-500/40 text-emerald-300 text-sm font-semibold px-5 py-3 rounded-2xl shadow-2xl"
          >
            <CheckCircle size={16} className="shrink-0" />
            {lang === 'fr'
              ? '🎉 Abonnement confirmé — bienvenue dans la newsletter Wezea !'
              : '🎉 Subscription confirmed — welcome to the Wezea newsletter!'}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Footer légal */}
      <footer className="mt-auto border-t border-slate-800/60 bg-slate-950/80 py-4 px-6">
        <div className="max-w-5xl mx-auto flex flex-wrap items-center justify-center gap-x-5 gap-y-1.5 text-xs text-slate-600">
          <span>© {new Date().getFullYear()} WEZEA · BCE 0811.380.056</span>
          <span className="hidden sm:inline text-slate-800">|</span>
          <a href="/agences/" className="hover:text-slate-400 transition-colors">Agences</a>
          <a href="/blog/" className="hover:text-slate-400 transition-colors">Blog</a>
          <button onClick={() => navigate('/mentions-legales/mentions')}       className="hover:text-slate-400 transition-colors">Mentions légales</button>
          <button onClick={() => navigate('/mentions-legales/confidentialite')} className="hover:text-slate-400 transition-colors">Confidentialité & RGPD</button>
          <button onClick={() => navigate('/mentions-legales/cgv')}             className="hover:text-slate-400 transition-colors">CGV</button>
          <button onClick={() => navigate('/mentions-legales/cgu')}             className="hover:text-slate-400 transition-colors">CGU</button>
          <button onClick={() => navigate('/mentions-legales/cookies')}         className="hover:text-slate-400 transition-colors">Cookies</button>
          <span className="hidden sm:inline text-slate-800">|</span>
          <a href="mailto:contact@wezea.net" className="hover:text-slate-400 transition-colors">contact@wezea.net</a>
        </div>
      </footer>

      {/* ── Sticky bar post-scan (anonyme uniquement) ────────────────────── */}
      <AnimatePresence>
        {!user && scanner.status === 'success' && !stickyDismissed && (
          <motion.div
            initial={{ y: 80, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 80, opacity: 0 }}
            transition={{ delay: 1.8, duration: 0.4, ease: 'easeOut' }}
            className="fixed bottom-0 left-0 right-0 z-50"
            style={{
              background: 'linear-gradient(180deg, rgba(8,18,30,0.96), rgba(5,10,18,0.99))',
              borderTop: '1px solid rgba(34,211,238,0.18)',
              backdropFilter: 'blur(14px)',
            }}
          >
            <div className="max-w-4xl mx-auto px-4 py-3 flex items-center gap-4 flex-wrap">
              <div className="flex items-center gap-3 flex-1 min-w-0">
                <div
                  className="shrink-0 w-8 h-8 rounded-lg flex items-center justify-center"
                  style={{ background: 'rgba(34,211,238,0.1)', border: '1px solid rgba(34,211,238,0.2)' }}
                >
                  <FileDown size={15} className="text-cyan-400" />
                </div>
                <div className="min-w-0">
                  <p className="text-white text-sm font-semibold truncate">
                    {lang === 'fr' ? "Rapport PDF complet + sauvegarde de l'historique" : 'Full PDF report + history saving'}
                  </p>
                  <p className="text-slate-500 text-xs">
                    {lang === 'fr' ? 'Gratuit — sans carte bancaire' : 'Free — no credit card required'}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => goRegister('sticky_bar')}
                  className="sku-btn-primary text-sm px-4 py-2 rounded-xl flex items-center gap-2"
                >
                  <UserPlus size={14} />
                  {lang === 'fr' ? 'Créer mon compte →' : 'Create account →'}
                </button>
                <button
                  onClick={() => setStickyDismissed(true)}
                  className="text-slate-500 hover:text-slate-300 transition-colors p-1.5 rounded-lg hover:bg-slate-800/50"
                  aria-label="Fermer"
                >
                  <X size={16} />
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Onboarding wizard — affiché une fois après l'inscription ──────── */}
      <AnimatePresence>
        {onboardingOpen && user && (
          <OnboardingWizard
            user={user}
            onStartScan={handleOnboardingScan}
            onGoClientSpace={(tab) => { closeOnboarding(); navigate(tab ? `/espace-client/${tab}` : '/espace-client'); }}
            onClose={closeOnboarding}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

