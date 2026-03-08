// ─── Dashboard.tsx — Page principale de CyberHealth Scanner ──────────────────
//
// États :
//   idle     → Barre de recherche + hero
//   scanning → ScanConsole animée
//   success  → ScoreGauge + FindingCards + FinancialRisk
//   error    → Message d'erreur avec retry
//
import { useState, useEffect, useCallback, FormEvent, useRef, ReactNode } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Shield, Search, ArrowRight, RotateCcw,
  FileDown, Globe, AlertTriangle, Info, Lock, X, UserPlus, MessageSquare,
  CheckCircle, ChevronDown, Zap, Eye, Star, ListChecks, BookOpen, Building2, Bell,
  TrendingUp, TrendingDown,
} from 'lucide-react';

import { useLanguage } from '../i18n/LanguageContext';
import { useAuth } from '../contexts/AuthContext';
import { useScanner } from '../hooks/useScanner';
import { ScanConsole } from '../components/ScanConsole';
import { ScoreGauge } from '../components/ScoreGauge';
import { FindingCard, FindingGroup } from '../components/FindingCard';
import { EmailCaptureModal } from '../components/EmailCaptureModal';
import { ProfileModal } from '../components/ProfileModal';
import PricingModal from '../components/PricingModal';
import NewsletterWidget from '../components/NewsletterWidget';
import type { Finding } from '../types/scanner';
import { SEVERITY_CONFIG } from '../types/scanner';
import { apiClient, getScanLimits } from '../lib/api';
import type { RateLimitInfo } from '../lib/api';
import {
  captureScanStarted, captureScanCompleted, captureScanFailed,
  captureRegisterCtaClicked, capturePricingModalOpened,
  capturePdfDownloaded, captureMonitoringDomainAdded,
} from '../lib/analytics';
import type { PricingSource, RegisterCtaSource } from '../lib/analytics';

// ─────────────────────────────────────────────────────────────────────────────

// CountUp — animation de comptage déclenchée au scroll (IntersectionObserver)
function CountUp({ to, suffix = '' }: { to: number; suffix?: string }) {
  const [val, setVal] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  const started = useRef(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && !started.current) {
        started.current = true;
        const duration = 1400;
        const t0 = performance.now();
        const tick = (now: number) => {
          const p = Math.min((now - t0) / duration, 1);
          const eased = 1 - Math.pow(1 - p, 3);
          setVal(Math.round(eased * to));
          if (p < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
        obs.disconnect();
      }
    }, { threshold: 0.5 });
    obs.observe(el);
    return () => obs.disconnect();
  }, [to]);
  return <span ref={ref}>{val.toLocaleString()}{suffix}</span>;
}

// ─── MiniSparkline — historique des scores ────────────────────────────────────
function MiniSparkline({ scores }: { scores: number[] }) {
  if (scores.length < 2) return null;
  const W = 130, H = 30, PAD = 3;
  const min = Math.min(...scores), max = Math.max(...scores);
  const range = max - min || 10; // évite division par 0
  const pts = scores.map((v, i) => ({
    x: PAD + (i / (scores.length - 1)) * (W - PAD * 2),
    y: PAD + (1 - (v - min) / range) * (H - PAD * 2),
  }));
  const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  const last = scores[scores.length - 1];
  const color = last >= 70 ? '#4ade80' : last >= 40 ? '#fb923c' : '#f87171';
  return (
    <svg width={W} height={H} className="shrink-0 overflow-visible">
      <path d={line} stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" opacity="0.8" />
      <circle cx={pts[pts.length - 1].x} cy={pts[pts.length - 1].y} r="2.5" fill={color} />
    </svg>
  );
}

interface Props {
  onGoLogin?:      () => void;
  onGoRegister?:   () => void;
  onGoHistory?:    () => void;
  onGoAdmin?:      () => void;
  onGoClientSpace?:() => void;
  onGoContact?:    () => void;
  onGoLegal?:      (section?: string) => void;
  /** UUID d'un scan historique à charger directement (depuis HistoryPage) */
  initialScanUuid?: string | null;
  /** Appelé une fois le scan historique chargé — pour réinitialiser le prop côté App */
  onScanUuidConsumed?: () => void;
}

// ─── SkuIcon — boîte d'icône skeuomorphique ───────────────────────────────────
function SkuIcon({ children, color, size = 36 }: { children: ReactNode; color: string; size?: number }) {
  const r = Math.round(size * 0.28);
  return (
    <div className="shrink-0 flex items-center justify-center relative overflow-hidden"
      style={{
        width: size, height: size, borderRadius: r,
        background: `linear-gradient(150deg, ${color}30 0%, ${color}0d 100%)`,
        border: `1px solid ${color}40`,
        boxShadow: `0 4px 16px ${color}22, 0 1px 3px rgba(0,0,0,0.4), inset 0 1px 0 ${color}30, inset 0 -1px 0 rgba(0,0,0,0.3)`,
      }}
    >
      <div className="absolute inset-0 pointer-events-none"
        style={{ borderRadius: r, background: 'linear-gradient(180deg,rgba(255,255,255,0.07) 0%,transparent 50%)' }} />
      {children}
    </div>
  );
}

export default function Dashboard({ onGoLogin, onGoRegister, onGoHistory, onGoAdmin, onGoClientSpace, onGoContact, onGoLegal, initialScanUuid, onScanUuidConsumed }: Props) {
  const [domain, setDomain]         = useState('');
  const [modalOpen, setModalOpen]   = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [pwModalOpen, setPwModalOpen]       = useState(false);
  const [profileModalOpen, setProfileModalOpen] = useState(false);
  const [pricingModalOpen, setPricingModalOpen] = useState(false);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError,   setPdfError]   = useState<string | null>(null);
  // Monitoring
  const [monitoringOpen, setMonitoringOpen] = useState(false);
  const [monitoredDomains, setMonitoredDomains] = useState<Array<{domain:string;last_score:number|null;last_risk_level:string|null;last_scan_at:string|null;}>>([]);
  const [monitoringLoading, setMonitoringLoading] = useState(false);
  const [monitoringInput, setMonitoringInput] = useState('');
  // Onglets de résultats
  const [activeTab, setActiveTab] = useState<'summary' | 'findings' | 'advanced' | 'reco'>('summary');
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
  const [domainHistory,  setDomainHistory]  = useState<number[]>([]);
  const [blogLinks,      setBlogLinks]      = useState<Array<{ id: number; match_keyword: string; article_title: string; article_url: string }>>([]);
  const [stickyDismissed, setStickyDismissed] = useState(false);
  const inputRef                    = useRef<HTMLInputElement>(null);
  const resultsRef                  = useRef<HTMLDivElement>(null);

  const { lang, setLang, t } = useLanguage();
  const { user, logout } = useAuth();
  const scanner = useScanner();

  // ── Helpers analytics ────────────────────────────────────────────────────────
  const openPricing = (source: PricingSource) => {
    capturePricingModalOpened(source);
    setPricingModalOpen(true);
  };
  const goRegister = (source: RegisterCtaSource) => {
    captureRegisterCtaClicked(source);
    if (onGoRegister) { onGoRegister(); } else { onGoLogin?.(); }
  };
  const goLogin = (source: RegisterCtaSource) => {
    captureRegisterCtaClicked(source);
    onGoLogin?.();
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

  // ── Chargement d'un scan historique (depuis HistoryPage) ───────────────────
  useEffect(() => {
    if (!initialScanUuid) return;
    scanner.loadFromHistory(initialScanUuid);
    onScanUuidConsumed?.();
    setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 600);
  }, [initialScanUuid]); // eslint-disable-line react-hooks/exhaustive-deps

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
    if (scanner.status === 'success' || scanner.status === 'error') {
      fetchScanLimits();
    }
    if (scanner.status === 'success' && scanner.result) {
      setActiveTab('summary');
      // Scroll vers les résultats une fois la transition AnimatePresence terminée.
      // Timeline : console exit (200ms) + results enter (400ms) + marge (100ms) = 700ms
      // behavior:'instant' — évite qu'une animation de scroll rate sa cible si la page
      // est déjà au bon endroit ou si le navigateur mobile interfère avec smooth scroll.
      setTimeout(() => {
        resultsRef.current?.scrollIntoView({ behavior: 'instant', block: 'start' });
      }, 700);
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
          const scans: Array<{ domain: string; security_score: number; created_at: string }> = res.data;
          // Tri newest-first : [0]=actuel, [1]=précédent
          const byNewest = scans
            .filter(s => s.domain === scanner.result!.domain)
            .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
          // Tri chronologique (oldest-first) pour la sparkline
          const byOldest = [...byNewest].reverse();
          setPreviousScore(byNewest.length >= 2 ? byNewest[1].security_score : null);
          setDomainHistory(byOldest.map(s => s.security_score));
        }).catch(() => { setPreviousScore(null); setDomainHistory([]); });
      }
    }
    if (scanner.status === 'scanning') {
      setPreviousScore(null);   // reset à chaque nouveau scan
      setDomainHistory([]);
    }
    if (scanner.status === 'error') {
      // Scroll vers la zone d'erreur — sans ça, la page peut rester sur le hero
      // (le ScanConsole qui disparaît réduit la page, causant un saut vers le haut)
      setTimeout(() => {
        resultsRef.current?.scrollIntoView({ behavior: 'instant', block: 'start' });
      }, 400);
      captureScanFailed(scanner.result?.domain ?? domain, scanner.error ?? undefined);
    }
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

  const handleSubmit = async (e: FormEvent, overrideDomain?: string) => {
    e.preventDefault();
    const target = (overrideDomain ?? domain).trim();
    if (!target) return;
    setDomain(target);
    captureScanStarted(target);
    // Scroll vers la zone de scan avant de démarrer — l'animation est visible
    // même si l'utilisateur était scrollé dans les résultats d'un scan précédent
    resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    await scanner.startScan(target, lang);
    // Note : le scroll post-scan est géré dans le useEffect sur scanner.status === 'success'
    // pour éviter de scroller pendant la transition AnimatePresence (zone vide visible)
  };

  // Grouper les findings par catégorie
  const groupFindings = (findings: Finding[]) => ({
    dns:        findings.filter(f => f.category === 'DNS & Mail'),
    ssl:        findings.filter(f => f.category === 'SSL / HTTPS'),
    ports:      findings.filter(f => f.category === 'Exposition des Ports'),
    headers:    findings.filter(f => f.category === 'En-têtes HTTP'),
    emailSec:   findings.filter(f => f.category === 'Sécurité Email'),
    tech:       findings.filter(f => f.category === 'Exposition Technologique'),
    reputation: findings.filter(f => f.category === 'Réputation du Domaine' && f.severity !== 'INFO'),
    subdomains: findings.filter(f => f.category === 'Sous-domaines & Certificats'),
    vulns:      findings.filter(f => f.category === 'Versions Vulnérables'),
    info:       findings.filter(f => f.severity === 'INFO'),
  });

  const isIdle     = scanner.status === 'idle';
  const isScanning = scanner.status === 'scanning';
  const isSuccess  = scanner.status === 'success';
  const isError    = scanner.status === 'error';

  return (
    <div className="min-h-screen flex flex-col text-slate-100">




      {/* ── Navigation ──────────────────────────────────────────────────────── */}
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
            onClick={() => scanner.reset()}
            className="flex items-center gap-2 shrink-0 group"
            aria-label="Retour à l'accueil"
          >
            <div className="text-left">
              <div className="font-black text-white leading-none group-hover:text-cyan-50 transition-colors" style={{ fontSize: '20px', letterSpacing: '-0.03em', fontFamily: 'var(--font-display)' }}>
                We<span style={{ color: 'var(--color-accent)' }}>zea</span>
              </div>
              <div className="text-slate-500 uppercase hidden sm:block group-hover:text-slate-400 transition-colors" style={{ fontSize: '9px', letterSpacing: '0.12em', marginTop: '2px', fontFamily: 'var(--font-sans)', fontWeight: 500 }}>
                Security Scanner
              </div>
            </div>
          </button>

          {/* CENTER — Navigation principale */}
          <div className="hidden md:flex items-center gap-1 justify-start ml-6">

            {/* Espace Client (Starter/Pro) ou Historique (Free connecté) */}
            {user && (
              isPremium ? (
                <button
                  onClick={onGoClientSpace}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-cyan-300 bg-cyan-500/8 border border-cyan-500/22 hover:bg-cyan-500/15 hover:border-cyan-500/40 transition-all"
                >
                  <Shield size={11} />
                  {lang === 'fr' ? 'Mon espace' : 'My space'}
                  <svg width="10" height="10" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"/></svg>
                </button>
              ) : (
                <button
                  onClick={onGoHistory}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-white/4 transition-all"
                >
                  <ListChecks size={11} />
                  {lang === 'fr' ? 'Historique' : 'History'}
                </button>
              )
            )}

            {/* CTA upgrade — Free connecté uniquement */}
            {user && user.plan === 'free' && (
              <button
                onClick={() => openPricing('nav')}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-cyan-300 bg-cyan-500/8 border border-cyan-500/20 hover:bg-cyan-500/15 hover:border-cyan-500/35 transition-all"
              >
                <Zap size={11} />
                {lang === 'fr' ? 'Passer Starter' : 'Upgrade'}
              </button>
            )}

            {/* Agences — visible uniquement si non-client (non connecté ou plan free) */}
            {(!user || user.plan === 'free') && (
              <a
                href="/agences/"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-white/4 transition-all"
              >
                <Building2 size={11} />
                {lang === 'fr' ? 'Agences' : 'Agencies'}
              </a>
            )}

            {/* Blog — toujours visible */}
            <a
              href="/blog/"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-white/4 transition-all"
            >
              <BookOpen size={11} />
              Blog
            </a>

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

                    {/* Section Compte */}
                    <div className="pt-1.5 pb-1">
                      <p className="px-3 pb-1 text-[9px] font-mono text-slate-600 uppercase tracking-widest">{lang === 'fr' ? 'Compte' : 'Account'}</p>
                      <button
                        onClick={() => { setUserMenuOpen(false); setProfileModalOpen(true); }}
                        className="w-full text-left px-3 py-2 text-xs text-slate-400 hover:bg-white/5 hover:text-slate-200 transition flex items-center gap-2.5"
                      >
                        <span className="w-[18px] h-[18px] rounded-[5px] shrink-0 inline-flex items-center justify-center" style={{background:'linear-gradient(150deg,rgba(192,132,252,.18),rgba(192,132,252,.05))',border:'1px solid rgba(192,132,252,.22)'}}>
                          <svg width="10" height="10" fill="none" stroke="#c084fc" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                        </span>
                        {lang === 'fr' ? 'Mon profil' : 'My profile'}
                      </button>
                      {!user.google_id && (
                        <button
                          onClick={() => { setUserMenuOpen(false); setPwModalOpen(true); }}
                          className="w-full text-left px-3 py-2 text-xs text-slate-400 hover:bg-white/5 hover:text-slate-200 transition flex items-center gap-2.5"
                        >
                          <span className="w-[18px] h-[18px] rounded-[5px] shrink-0 inline-flex items-center justify-center" style={{background:'linear-gradient(150deg,rgba(34,211,238,.18),rgba(34,211,238,.05))',border:'1px solid rgba(34,211,238,.22)'}}>
                            <svg width="10" height="10" fill="none" stroke="#22d3ee" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                          </span>
                          {lang === 'fr' ? 'Changer le mot de passe' : 'Change password'}
                        </button>
                      )}
                      <button
                        onClick={() => { setUserMenuOpen(false); openPricing('user_menu'); }}
                        className="w-full text-left px-3 py-2 text-xs text-slate-400 hover:bg-white/5 hover:text-slate-200 transition flex items-center gap-2.5"
                      >
                        <span className="w-[18px] h-[18px] rounded-[5px] shrink-0 inline-flex items-center justify-center" style={{background:'linear-gradient(150deg,rgba(34,211,238,.18),rgba(34,211,238,.05))',border:'1px solid rgba(34,211,238,.22)'}}>
                          <svg width="10" height="10" fill="none" stroke="#22d3ee" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                        </span>
                        {user.plan === 'free' ? (lang === 'fr' ? 'Voir les plans' : 'View plans') : (lang === 'fr' ? "Gérer l'abonnement" : 'Manage subscription')}
                      </button>
                    </div>

                    {/* Section Aide */}
                    <div className="border-t border-white/6 pt-1.5 pb-1">
                      <p className="px-3 pb-1 text-[9px] font-mono text-slate-600 uppercase tracking-widest">{lang === 'fr' ? 'Aide' : 'Help'}</p>
                      <button
                        onClick={() => { setUserMenuOpen(false); onGoContact?.(); }}
                        className="w-full text-left px-3 py-2 text-xs text-slate-400 hover:bg-white/5 hover:text-slate-200 transition flex items-center gap-2.5"
                      >
                        <span className="w-[18px] h-[18px] rounded-[5px] shrink-0 inline-flex items-center justify-center" style={{background:'linear-gradient(150deg,rgba(96,165,250,.18),rgba(96,165,250,.05))',border:'1px solid rgba(96,165,250,.22)'}}>
                          <svg width="10" height="10" fill="none" stroke="#60a5fa" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                        </span>
                        {lang === 'fr' ? 'Contacter le support' : 'Contact support'}
                      </button>
                      {user?.is_admin && (
                        <button
                          onClick={() => { setUserMenuOpen(false); onGoAdmin?.(); }}
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
              {isSuccess && scanner.result
                ? scanner.result.domain
                : isScanning
                ? (lang === 'fr' ? 'Scan en cours…' : 'Scanning…')
                : (lang === 'fr' ? 'Erreur de scan' : 'Scan error')}
            </span>
            <button
              onClick={scanner.reset}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium text-slate-500 hover:text-slate-300 hover:bg-white/5 border border-white/6 transition-all"
            >
              <RotateCcw size={10} />
              {lang === 'fr' ? 'Nouveau scan' : 'New scan'}
            </button>
            {isSuccess && scanner.result && (
              <motion.button
                initial={{ opacity: 0, x: 6 }}
                animate={{ opacity: 1, x: 0 }}
                onClick={() => setModalOpen(true)}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-semibold text-cyan-300 bg-cyan-500/10 border border-cyan-500/25 hover:bg-cyan-500/18 transition-all"
              >
                <FileDown size={10} />
                {lang === 'fr' ? 'Télécharger PDF' : 'Download PDF'}
              </motion.button>
            )}
          </div>
        )}
      </nav>

      {/* ── Hero + Barre de recherche ────────────────────────────────────────── */}
      <header className={`
        relative overflow-hidden transition-all duration-700
        ${isIdle ? 'py-12 md:py-18' : 'py-10 md:py-14'}
      `}>
        {/* Ambiance radiale */}
        <div className="absolute inset-0 pointer-events-none" style={{
          background: 'radial-gradient(ellipse at 50% -10%, rgba(34,211,238,0.06) 0%, transparent 60%)',
        }} />
        {/* Grille cyber décorative subtile */}
        <div
          className="absolute inset-0 opacity-[0.025] pointer-events-none"
          style={{
            backgroundImage: `linear-gradient(rgba(34,211,238,1) 1px, transparent 1px),
                              linear-gradient(90deg, rgba(34,211,238,1) 1px, transparent 1px)`,
            backgroundSize: '48px 48px',
          }}
        />

        <div className="relative max-w-3xl mx-auto px-4 text-center">
          <AnimatePresence>
            {isIdle && (
              <motion.div
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -16 }}
                transition={{ duration: 0.4 }}
              >
                {/* Badge */}
                <div
                  className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 mb-6 text-cyan-400 text-xs font-medium"
                  style={{ background: 'rgba(34,211,238,0.07)', border: '1px solid rgba(34,211,238,0.15)', boxShadow: '0 0 20px rgba(34,211,238,0.05), 0 1px 0 rgba(255,255,255,0.05) inset' }}
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
                  {t('hero_badge')}
                </div>

                <h1 className="text-4xl md:text-5xl font-black leading-tight mb-4"
                  style={{ background: 'linear-gradient(180deg,#f1f5f9 30%,#94a3b8 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}
                >
                  {t('hero_title_1')}<br />
                  <span style={{ background: 'linear-gradient(135deg,#22d3ee,#60a5fa)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                    {t('hero_title_2')}
                  </span>
                </h1>
                <p className="text-slate-500 text-lg mb-8 max-w-xl mx-auto leading-relaxed">
                  {t('hero_subtitle')}
                </p>
              </motion.div>
            )}
          </AnimatePresence>

          {/* ── Barre de recherche ──────────────────────────────────────── */}
          <form onSubmit={handleSubmit} className="relative max-w-2xl mx-auto flex flex-col gap-3">
            <div
              className="flex items-center gap-2 rounded-2xl p-2 transition-all duration-200"
              style={{
                background: 'linear-gradient(180deg,#0f151e,#0b1018)',
                border: '1px solid rgba(255,255,255,0.07)',
                boxShadow: '0 4px 24px rgba(0,0,0,0.6), 0 1px 0 rgba(255,255,255,0.05) inset',
              }}
            >
              <Globe size={18} className="ml-2 text-slate-600 shrink-0" />
              <input
                ref={inputRef}
                id="domain-input"
                name="domain"
                type="text"
                value={domain}
                onChange={e => setDomain(e.target.value)}
                disabled={isScanning}
                className="
                  flex-1 bg-transparent text-white placeholder:text-slate-600
                  font-mono text-sm focus:outline-none px-2 py-2
                  disabled:cursor-not-allowed
                "
                aria-label="Nom de domaine à analyser"
                autoComplete="url"
                spellCheck={false}
                placeholder={t('placeholder')}
              />
              {/* Bouton inline — desktop uniquement */}
              <button
                type="submit"
                disabled={isScanning || !domain.trim()}
                className="sku-btn-primary hidden sm:flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm shrink-0 disabled:opacity-40 disabled:cursor-not-allowed disabled:transform-none"
              >
                <Search size={15} />
                {t('btn_scan')}
                <ArrowRight size={14} />
              </button>
            </div>

            {/* Bouton pleine largeur — mobile uniquement */}
            <button
              type="submit"
              disabled={isScanning || !domain.trim()}
              className="sku-btn-primary sm:hidden flex items-center justify-center gap-2 w-full py-3.5 rounded-2xl text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed disabled:transform-none"
            >
              <Search size={15} />
              {t('btn_scan')}
              <ArrowRight size={14} />
            </button>
          </form>

          {/* ── Réassurance sous le champ ─────────────────────────────── */}
          {isIdle && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.4 }}
              className="flex flex-wrap items-center justify-center gap-x-5 gap-y-1.5 mt-3"
            >
              {[
                lang === 'fr' ? '✓ 100% passif, sans risque' : '✓ 100% passive, zero risk',
                lang === 'fr' ? '✓ Données non stockées' : '✓ No data stored',
                lang === 'fr' ? '✓ Rapport PDF inclus' : '✓ PDF report included',
              ].map((item, i) => (
                <span key={i} className="text-[11px] text-slate-600 font-medium">{item}</span>
              ))}
              {publicStats && (
                <>
                  <span className="text-slate-800 text-[10px] hidden sm:inline">·</span>
                  <span className="flex items-center gap-1 text-[11px] text-slate-600 font-medium">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse shrink-0" />
                    {(publicStats.total_scans + 500).toLocaleString()}
                    {lang === 'fr' ? ' domaines analysés' : ' domains analyzed'}
                  </span>
                </>
              )}
            </motion.div>
          )}

          {/* ── Compteur de scans + CTAs contextuels ───────────────────── */}
          {scanLimits && scanLimits.type !== 'unlimited' && scanLimits.remaining !== null && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }} className="mt-4">
              {scanLimits.remaining > 0 ? (
                /* Pill normal */
                <div className="flex flex-wrap items-center justify-center gap-2">
                  <div className={`flex items-center gap-1.5 text-xs px-3 py-1 rounded-full border ${
                    scanLimits.remaining === 1
                      ? 'border-orange-500/40 bg-orange-500/10 text-orange-400'
                      : 'border-slate-700/60 bg-slate-800/40 text-slate-500'
                  }`}>
                    <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
                    {lang === 'fr'
                      ? `${scanLimits.remaining} scan${scanLimits.remaining > 1 ? 's' : ''} restant${scanLimits.remaining > 1 ? 's' : ''} aujourd'hui`
                      : `${scanLimits.remaining} scan${scanLimits.remaining > 1 ? 's' : ''} left today`}
                  </div>
                  {scanLimits.type === 'anonymous' && (
                    <button onClick={() => goRegister('scan_limit')} className="text-xs text-cyan-500 hover:text-cyan-400 transition-colors underline underline-offset-2 font-medium">
                      {lang === 'fr' ? 'Créer un compte gratuit →' : 'Create free account →'}
                    </button>
                  )}
                </div>
              ) : scanLimits.type === 'anonymous' ? (
                /* 0 scan — visiteur : bandeau inline discret */
                <motion.div initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }}
                  className="flex items-center gap-3 bg-sky-500/5 border border-sky-500/20 rounded-xl px-4 py-2.5">
                  <span className="w-2 h-2 rounded-full bg-orange-400 shrink-0" />
                  <p className="flex-1 text-xs text-slate-400 leading-snug">
                    <span className="text-slate-200 font-semibold">
                      {lang === 'fr' ? 'Scan anonyme utilisé.' : 'Anonymous scan used.'}
                    </span>
                    {' '}
                    {lang === 'fr'
                      ? 'Créez un compte gratuit pour 5 scans/jour et votre historique.'
                      : 'Create a free account for 5 scans/day and your history.'}
                  </p>
                  <button onClick={() => goRegister('scan_limit')}
                    className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-sky-500/15 border border-sky-500/30 text-sky-300 hover:bg-sky-500/25 transition-colors text-xs font-semibold whitespace-nowrap">
                    <UserPlus size={12} />
                    {lang === 'fr' ? 'Créer un compte →' : 'Create account →'}
                  </button>
                </motion.div>
              ) : (
                /* 0 scan — free connecté : inciter à passer Starter */
                <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                  className="max-w-sm mx-auto rounded-2xl overflow-hidden"
                  style={{ border: '1px solid rgba(34,211,238,0.2)', background: 'linear-gradient(135deg,rgba(8,60,80,0.6) 0%,rgba(15,21,30,0.95) 100%)' }}>
                  <div className="px-5 pt-5 pb-4 text-center">
                    <div className="w-8 h-8 rounded-full bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center mx-auto mb-3">
                      <Zap size={14} className="text-cyan-400" />
                    </div>
                    <p className="text-white font-bold text-sm mb-1">
                      {lang === 'fr' ? 'Limite journalière atteinte' : 'Daily limit reached'}
                    </p>
                    <p className="text-slate-400 text-xs mb-4 leading-relaxed">
                      {lang === 'fr'
                        ? 'Quota de 5 scans épuisé — réinitialisé demain. Passez Starter pour analyser sans limite.'
                        : '5-scan quota used up — resets tomorrow. Upgrade to Starter for unlimited scans.'}
                    </p>
                    <button onClick={() => openPricing('scan_limit')}
                      className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-bold transition-all"
                      style={{ background: 'linear-gradient(135deg,rgba(34,211,238,0.22),rgba(59,130,246,0.18))', border: '1px solid rgba(34,211,238,0.35)', color: '#a5f3fc' }}>
                      <Zap size={13} />
                      {lang === 'fr' ? 'Scans illimités — Starter 9,90€/mois' : 'Unlimited scans — Starter €9.90/mo'}
                      <ArrowRight size={13} />
                    </button>
                  </div>
                  <div className="px-5 pb-4 flex items-center justify-center gap-5">
                    {(lang === 'fr'
                      ? ['✓ Scans illimités', '✓ PDF complet', '✓ Monitoring']
                      : ['✓ Unlimited scans', '✓ Full PDF', '✓ Monitoring']
                    ).map(f => <span key={f} className="text-[10px] text-cyan-700 font-mono">{f}</span>)}
                  </div>
                </motion.div>
              )}
            </motion.div>
          )}

          {/* Badges des vérifications — informatifs, non cliquables */}
          {isIdle && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.35 }}
              className="flex flex-col items-center gap-2 mt-5"
            >
              <p className="text-[10px] text-slate-600 uppercase tracking-widest font-mono select-none">
                {lang === 'fr' ? 'Ce que nous analysons' : 'What we analyse'}
              </p>
              <div className="flex flex-wrap justify-center gap-2 text-xs select-none pointer-events-none">
                {([
                  { c:'#c084fc', label: t('badge_headers'),
                    paths: <><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></> },
                  { c:'#2dd4bf', label: t('badge_spf'),
                    paths: <><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></> },
                  { c:'#22d3ee', label: t('badge_ssl'),
                    paths: <><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></> },
                  { c:'#fb923c', label: t('badge_ports'),
                    paths: <><path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><circle cx="12" cy="20" r="1" fill="#fb923c"/></> },
                  { c:'#4ade80', label: t('badge_tech'),
                    paths: <><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></> },
                  { c:'#f87171', label: t('badge_dnsbl'),
                    paths: <><circle cx="12" cy="8" r="6"/><path d="M15.477 12.89L17 22l-5-3-5 3 1.523-9.11"/></> },
                ] as Array<{c:string,label:string,paths:React.ReactNode}>).map(({ c, label, paths }) => (
                  <span key={label}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-slate-500 cursor-default"
                    style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}
                  >
                    <svg width="11" height="11" fill="none" stroke={c} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24" style={{ opacity: 0.75, flexShrink: 0 }}>
                      {paths}
                    </svg>
                    {label}
                  </span>
                ))}
              </div>
            </motion.div>
          )}

        </div>
      </header>

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
                        onClick={() => { scanner.reset(); if (onGoRegister) { onGoRegister(); } else { onGoLogin?.(); } }}
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
                    onClick={scanner.reset}
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
                    onClick={scanner.reset}
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
          {isSuccess && scanner.result && (() => {
            const r = scanner.result;
            const isAnon = !user;
            // Anonymes : exclure les LOW des groups visibles (affichés dans un gate séparé)
            const visibleForGroups = isAnon
              ? r.findings.filter(f => f.severity !== 'LOW' && f.severity !== 'INFO')
              : r.findings.filter(f => f.severity !== 'INFO');
            const hiddenLow = isAnon ? r.findings.filter(f => f.severity === 'LOW') : [];
            const infoFindings = r.findings.filter(f => f.severity === 'INFO');
            const groups = groupFindings(visibleForGroups);
            const nonInfoCount = r.findings.filter(f => f.severity !== 'INFO').length;

            return (
              <motion.div
                key="results"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.4 }}
                className="flex flex-col gap-6 py-8"
              >
                {/* ── Bande supérieure : Score + Stats + PDF ─────────────── */}
                <motion.div
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.1 }}
                  className="sku-panel rounded-2xl overflow-hidden"
                >
                  <div className="flex flex-col lg:flex-row">
                    {/* Score gauge */}
                    <div className="flex flex-col items-center justify-center gap-3 p-6 lg:border-r border-b lg:border-b-0 border-slate-800 shrink-0">
                      <ScoreGauge
                        score={r.security_score}
                        riskLevel={r.risk_level}
                        domain={r.domain}
                      />
                      {/* Delta vs scan précédent */}
                      {previousScore !== null && (() => {
                        const delta = r.security_score - previousScore;
                        if (delta === 0) return (
                          <span className="text-[11px] text-slate-500 font-mono">
                            = stable vs scan précédent
                          </span>
                        );
                        const up = delta > 0;
                        return (
                          <span className={`flex items-center gap-1 text-[11px] font-mono font-semibold px-2.5 py-1 rounded-full border ${
                            up
                              ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/25'
                              : 'text-red-400 bg-red-500/10 border-red-500/25'
                          }`}>
                            {up ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
                            {up ? '+' : ''}{delta} pts vs scan précédent
                          </span>
                        );
                      })()}
                    </div>
                    {/* Stats + PDF + meta */}
                    <div className="flex-1 flex flex-col justify-between gap-4 p-6">
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        <StatCard
                          label={t('stat_vulns')}
                          value={nonInfoCount}
                          highlight={r.findings.some(f => f.severity === 'CRITICAL')}
                        />
                        <StatCard
                          label={t('stat_ports')}
                          value={Object.values(r.port_details).filter(p => p.open && p.severity === 'CRITICAL').length}
                          highlight={Object.values(r.port_details).some(p => p.open && p.severity === 'CRITICAL')}
                        />
                        <StatCard
                          label={t('stat_dns')}
                          value={`−${groups.dns.reduce((s, f) => s + (f.penalty ?? 0), 0)} pts`}
                          highlight={groups.dns.some(f => (f.penalty ?? 0) > 0)}
                          small
                        />
                        <StatCard
                          label={t('stat_ssl')}
                          value={`−${groups.ssl.reduce((s, f) => s + (f.penalty ?? 0), 0)} pts`}
                          highlight={groups.ssl.some(f => (f.penalty ?? 0) > 0)}
                          small
                        />
                      </div>
                      <PortSummary portDetails={r.port_details} />
                      {/* Mini sparkline — historique des scores du domaine */}
                      {domainHistory.length >= 2 && (
                        <div className="flex items-center gap-3 px-3 py-2 rounded-xl bg-slate-800/40 border border-slate-700/50">
                          <div className="flex flex-col shrink-0">
                            <span className="text-[10px] text-slate-500 font-mono leading-tight">historique</span>
                            <span className="text-xs text-slate-400 font-mono font-bold leading-tight">{domainHistory.length} scans</span>
                          </div>
                          <MiniSparkline scores={domainHistory} />
                          <div className="flex flex-col items-end shrink-0 ml-auto">
                            <span className="text-[10px] text-slate-500 font-mono leading-tight">
                              {Math.min(...domainHistory)} → {Math.max(...domainHistory)}
                            </span>
                            <span className="text-[10px] text-slate-600 font-mono leading-tight">min / max</span>
                          </div>
                        </div>
                      )}
                      {isPremium && (
                        <div className="rounded-xl border border-slate-700/60 bg-slate-800/30 overflow-hidden">
                          <button
                            onClick={() => setMonitoringOpen(v => !v)}
                            className="w-full flex items-center justify-between px-5 py-3 text-sm font-semibold text-slate-300 hover:bg-slate-700/30 transition-colors"
                          >
                            <div className="flex items-center gap-2">
                              <Globe size={14} className="text-cyan-400" />
                              <span>Monitoring hebdomadaire</span>
                              {monitoredDomains.length > 0 && (
                                <span className="text-xs bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 px-1.5 py-0.5 rounded-full">
                                  {monitoredDomains.length} domaine{monitoredDomains.length > 1 ? 's' : ''}
                                </span>
                              )}
                            </div>
                            <span className={`text-slate-500 transition-transform ${monitoringOpen ? 'rotate-90' : ''}`}>▶</span>
                          </button>
                          {monitoringOpen && (
                            <div className="px-5 pb-5 flex flex-col gap-4">
                              <div className="flex gap-2 flex-wrap">
                                <input
                                  type="text"
                                  placeholder="exemple.com"
                                  value={monitoringInput}
                                  onChange={e => setMonitoringInput(e.target.value)}
                                  onKeyDown={e => { if (e.key === 'Enter' && monitoringInput.trim()) { addToMonitoring(monitoringInput.trim()); setMonitoringInput(''); } }}
                                  className="flex-1 min-w-[180px] bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-cyan-500 transition placeholder:text-slate-600"
                                />
                                <button
                                  onClick={() => { if (monitoringInput.trim()) { addToMonitoring(monitoringInput.trim()); setMonitoringInput(''); } }}
                                  className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 hover:bg-cyan-500/30 transition-colors text-xs font-semibold"
                                >
                                  <UserPlus size={13} />
                                  Ajouter
                                </button>
                                {scanner.result && !monitoredDomains.find(d => d.domain === scanner.result!.domain) && (
                                  <button
                                    onClick={() => addToMonitoring(scanner.result!.domain)}
                                    className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-700/60 text-slate-300 border border-slate-600/40 hover:bg-slate-700 transition-colors text-xs font-semibold"
                                  >
                                    <Globe size={13} />
                                    + {scanner.result.domain}
                                  </button>
                                )}
                              </div>
                              {monitoringLoading ? (
                                <p className="text-xs text-slate-500">Chargement…</p>
                              ) : monitoredDomains.length === 0 ? (
                                <p className="text-xs text-slate-500">Aucun domaine sous surveillance. Saisissez un domaine ci-dessus pour commencer.</p>
                              ) : (
                                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                                  {monitoredDomains.map(d => (
                                    <div key={d.domain} className="flex items-center justify-between bg-slate-900/60 border border-slate-800 rounded-lg px-3 py-2.5">
                                      <div className="flex items-center gap-2 min-w-0">
                                        <Globe size={11} className="text-slate-500 shrink-0" />
                                        <span className="text-slate-200 font-mono text-xs truncate">{d.domain}</span>
                                        {d.last_score !== null && (
                                          <span className={`text-xs font-bold shrink-0 ${d.last_score >= 70 ? 'text-green-400' : d.last_score >= 40 ? 'text-orange-400' : 'text-red-400'}`}>
                                            {d.last_score}/100
                                          </span>
                                        )}
                                      </div>
                                      <button onClick={() => removeFromMonitoring(d.domain)} className="text-slate-600 hover:text-red-400 transition-colors ml-2 shrink-0" title="Retirer du monitoring">
                                        <X size={12} />
                                      </button>
                                    </div>
                                  ))}
                                </div>
                              )}
                              <p className="text-[10px] text-slate-600 font-mono">
                                {lang === 'fr'
                                  ? 'Scan automatique selon la fréquence configurée · Alerte email si baisse ≥ 10 pts'
                                  : 'Automatic scan at configured frequency · Email alert on score drop ≥ 10 pts'}
                              </p>
                            </div>
                          )}
                        </div>
                      )}
                      <button
                        onClick={() => user ? downloadPdf() : setModalOpen(true)}
                        disabled={!!user && pdfLoading}
                        className={`
                          flex items-center justify-center gap-2
                          w-full py-3 rounded-xl font-bold text-sm
                          transition-all duration-200
                          ${user
                            ? 'bg-gradient-to-r from-cyan-700/60 to-blue-700/60 hover:from-cyan-600/70 hover:to-blue-600/70 border border-cyan-500/40 text-cyan-200 disabled:opacity-50'
                            : r.security_score < 40
                              ? 'bg-gradient-to-r from-red-700/60 to-orange-700/60 hover:from-red-600/70 hover:to-orange-600/70 border border-red-500/40 text-red-200'
                              : r.security_score < 70
                              ? 'bg-gradient-to-r from-orange-700/50 to-yellow-700/50 hover:from-orange-600/60 hover:to-yellow-600/60 border border-orange-500/30 text-orange-200'
                              : 'bg-gradient-to-r from-cyan-700/50 to-blue-700/50 hover:from-cyan-600/60 hover:to-blue-600/60 border border-cyan-500/30 text-cyan-300'}
                        `}
                      >
                        <FileDown size={15} />
                        {user
                          ? (pdfLoading
                              ? (lang === 'fr' ? 'Génération…' : 'Generating…')
                              : (lang === 'fr' ? 'Télécharger le rapport PDF complet' : 'Download full PDF report'))
                          : r.security_score < 40
                            ? (lang === 'fr' ? 'Site en danger — Obtenir le plan de remédiation' : 'Site at risk — Get remediation plan')
                            : r.security_score < 70
                              ? (lang === 'fr'
                                  ? `${nonInfoCount} risque(s) détecté(s) — Voir le plan de correction`
                                  : `${nonInfoCount} risk(s) found — See correction plan`)
                              : (lang === 'fr' ? 'Télécharger le rapport complet' : 'Download full report')}
                      </button>
                      {pdfError && (
                        <p className="text-center text-red-400 text-[10px] font-mono px-2 py-1 bg-red-500/10 rounded-lg border border-red-500/20">
                          ⚠ {pdfError}
                        </p>
                      )}
                      <p className="text-center text-slate-700 text-[10px] font-mono">
                        {t('scan_duration', { ms: (r.scan_duration_ms / 1000).toFixed(1), date: new Date(r.scanned_at).toLocaleString(lang === 'fr' ? 'fr-FR' : 'en-US') })}
                      </p>
                    </div>
                  </div>
                </motion.div>

                {/* ── Maturité de sécurité — benchmark industrie ────────── */}
                {publicStats?.industry_avg !== undefined && (() => {
                  const userScore = r.security_score;
                  const avg       = publicStats.industry_avg!;
                  const gap       = avg - userScore;
                  const worse     = gap > 0;
                  // Estimation du percentile : linéaire autour de la moyenne (±30 pts = ±45%)
                  const rawPct    = 50 + Math.round(gap * 1.5);
                  const pctBelowYou = Math.max(5, Math.min(95, rawPct));
                  const scoreColor = userScore >= 70 ? '#4ade80' : userScore >= 40 ? '#fbbf24' : '#f87171';
                  return (
                    <motion.div
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.25 }}
                      className="sku-panel rounded-2xl p-5"
                    >
                      {/* Titre */}
                      <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-2">
                          <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
                            style={{ background: 'linear-gradient(135deg,#a78bfa30,#a78bfa0d)', border: '1px solid #a78bfa40' }}>
                            <TrendingUp size={14} className="text-violet-300" />
                          </div>
                          <span className="text-sm font-bold text-slate-200">
                            {lang === 'fr' ? 'Maturité de sécurité' : 'Security Maturity'}
                          </span>
                        </div>
                        <span className="text-[10px] font-mono text-slate-500 bg-slate-800/60 px-2 py-0.5 rounded-full border border-slate-700/50">
                          {lang === 'fr' ? 'vs moyenne PME' : 'vs SMB average'}
                        </span>
                      </div>

                      {/* Barres comparatives */}
                      <div className="flex flex-col gap-3 mb-4">
                        {/* Barre utilisateur */}
                        <div>
                          <div className="flex justify-between mb-1.5">
                            <span className="text-[11px] font-semibold text-slate-300 font-mono">
                              {lang === 'fr' ? 'Votre score' : 'Your score'}
                            </span>
                            <span className="text-[11px] font-bold font-mono" style={{ color: scoreColor }}>
                              {userScore}/100
                            </span>
                          </div>
                          <div className="w-full h-3 bg-slate-800 rounded-full overflow-hidden">
                            <motion.div
                              initial={{ width: 0 }}
                              animate={{ width: `${userScore}%` }}
                              transition={{ duration: 0.8, ease: 'easeOut', delay: 0.3 }}
                              className="h-full rounded-full"
                              style={{ background: `linear-gradient(90deg, ${scoreColor}cc, ${scoreColor})` }}
                            />
                          </div>
                        </div>
                        {/* Barre moyenne */}
                        <div>
                          <div className="flex justify-between mb-1.5">
                            <span className="text-[11px] font-semibold text-slate-400 font-mono">
                              {lang === 'fr' ? 'Moyenne des entreprises' : 'Industry average'}
                            </span>
                            <span className="text-[11px] font-bold text-slate-400 font-mono">{avg}/100</span>
                          </div>
                          <div className="w-full h-3 bg-slate-800 rounded-full overflow-hidden">
                            <motion.div
                              initial={{ width: 0 }}
                              animate={{ width: `${avg}%` }}
                              transition={{ duration: 0.8, ease: 'easeOut', delay: 0.45 }}
                              className="h-full rounded-full bg-slate-600"
                            />
                          </div>
                        </div>
                      </div>

                      {/* Message psychologique */}
                      <div className={`rounded-xl px-4 py-3 border text-sm leading-snug ${
                        worse
                          ? 'bg-red-500/8 border-red-500/25 text-red-300'
                          : 'bg-emerald-500/8 border-emerald-500/25 text-emerald-300'
                      }`}>
                        {worse ? (
                          lang === 'fr'
                            ? <><span className="font-bold">{pctBelowYou}% des entreprises analysées</span> ont un meilleur score que vous. Votre infrastructure est <span className="font-bold">{gap} points en dessous</span> de la moyenne.</>
                            : <><span className="font-bold">{pctBelowYou}% of analyzed companies</span> score higher than you. Your infrastructure is <span className="font-bold">{gap} points below</span> average.</>
                        ) : (
                          lang === 'fr'
                            ? <>Votre score est <span className="font-bold">{Math.abs(gap)} points au-dessus</span> de la moyenne. Vous faites partie des <span className="font-bold">{100 - pctBelowYou}% d'entreprises</span> les mieux protégées.</>
                            : <>Your score is <span className="font-bold">{Math.abs(gap)} points above</span> average. You're among the <span className="font-bold">top {100 - pctBelowYou}%</span> of protected companies.</>
                        )}
                      </div>

                      {/* CTA pour anonymes */}
                      {!user && worse && (
                        <button
                          onClick={() => { captureRegisterCtaClicked('maturity_widget'); onGoRegister?.(); }}
                          className="mt-3 w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-bold bg-violet-500/15 border border-violet-500/35 text-violet-300 hover:bg-violet-500/25 transition-colors"
                        >
                          <UserPlus size={14} />
                          {lang === 'fr'
                            ? `Corriger ces ${gap} points — Créer un compte gratuit`
                            : `Fix this ${gap}-point gap — Create a free account`}
                        </button>
                      )}
                    </motion.div>
                  );
                })()}

                {/* ── Notice "Résultats non sauvegardés" (anonyme uniquement) ── */}
                {!user && (
                  <motion.div
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.4 }}
                    className="flex items-center gap-3 rounded-xl border border-amber-500/25 bg-amber-500/5 px-4 py-3 mb-2"
                  >
                    <SkuIcon color="#fbbf24" size={32}>
                      <AlertTriangle size={15} className="text-amber-300" />
                    </SkuIcon>
                    <div className="flex-1 min-w-0">
                      <p className="text-amber-200 text-sm font-semibold">
                        {lang === 'fr' ? 'Résultats non sauvegardés' : 'Results not saved'}
                      </p>
                      <p className="text-slate-400 text-xs mt-0.5 leading-snug">
                        {lang === 'fr'
                          ? 'Créez un compte gratuit pour retrouver ces résultats à tout moment.'
                          : 'Create a free account to access these results at any time.'}
                      </p>
                    </div>
                    <button
                      onClick={() => goRegister('results_save')}
                      className="shrink-0 sku-btn-primary text-xs px-3 py-1.5 rounded-lg whitespace-nowrap"
                    >
                      {lang === 'fr' ? 'Sauvegarder →' : 'Save →'}
                    </button>
                  </motion.div>
                )}

                {/* ── Onglets ─────────────────────────────────────────────── */}
                <div>
                  {/* Barre de navigation */}
                  <div className="flex items-center gap-0 border-b border-slate-800 mb-6 overflow-x-auto scrollbar-hide">
                    {([
                      { id: 'summary'  as const, label: lang === 'fr' ? 'Résumé'            : 'Summary',         shortLabel: lang === 'fr' ? 'Résumé'   : 'Summary', icon: <ListChecks size={13} />,    dot: r.findings.some(f => f.severity === 'CRITICAL') },
                      { id: 'findings' as const, label: lang === 'fr' ? `Vulnérabilités (${nonInfoCount})` : `Vulns (${nonInfoCount})`, shortLabel: lang === 'fr' ? `Vulnés (${nonInfoCount})` : `Vulns (${nonInfoCount})`, icon: <AlertTriangle size={13} />, dot: false },
                      { id: 'reco'     as const, label: lang === 'fr' ? 'Recommandations'   : 'Recommendations', shortLabel: lang === 'fr' ? 'Reco.'  : 'Reco.',   icon: <Zap size={13} />,           dot: (r.recommendations?.length ?? 0) > 0 },
                      { id: 'advanced' as const, label: lang === 'fr' ? 'Avancé'            : 'Advanced',        shortLabel: lang === 'fr' ? 'Avancé' : 'Advanced', icon: <Shield size={13} />,        dot: false },
                    ]).map(tab => (
                      <button
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id)}
                        className={`
                          relative flex items-center gap-1.5 px-2 sm:px-4 py-2.5 text-xs sm:text-sm font-semibold transition-all whitespace-nowrap shrink-0
                          ${activeTab === tab.id ? 'text-white' : 'text-slate-500 hover:text-slate-300'}
                        `}
                      >
                        <span className={activeTab === tab.id ? 'text-cyan-400' : 'text-slate-600'}>{tab.icon}</span>
                        <span className="hidden sm:inline">{tab.label}</span>
                        <span className="sm:hidden">{tab.shortLabel}</span>
                        {tab.dot && <span className="w-1.5 h-1.5 rounded-full bg-red-500 absolute top-2 right-1" />}
                        {activeTab === tab.id && (
                          <motion.span
                            layoutId="tab-underline"
                            className="absolute bottom-0 left-0 right-0 h-0.5 bg-cyan-400 rounded-full"
                          />
                        )}
                      </button>
                    ))}
                  </div>

                  {/* Contenu des onglets */}
                  <AnimatePresence mode="wait">

                    {/* ── Onglet Résumé ─────────────────────────────────── */}
                    {activeTab === 'summary' && (
                      <motion.div
                        key="tab-summary"
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        transition={{ duration: 0.18 }}
                        className="flex flex-col gap-5"
                      >
                        {/* Cas : aucune vulnérabilité */}
                        {nonInfoCount === 0 && (
                          <div className="flex flex-col items-center gap-3 py-12 text-center bg-slate-900/50 rounded-2xl border border-slate-800">
                            <div className="p-3 rounded-full bg-green-500/10 border border-green-500/20">
                              <Shield size={24} className="text-green-400" />
                            </div>
                            <p className="text-green-400 font-bold">{t('vulns_none')}</p>
                            <p className="text-slate-500 text-sm max-w-sm">{t('vulns_none_sub')}</p>
                          </div>
                        )}

                        {/* Plan d'action prioritaire */}
                        {(() => {
                          type WithEffort = Finding & { effort: 'quick' | 'medium' | 'complex' };
                          const getEffort = (f: Finding): 'quick' | 'medium' | 'complex' => {
                            if (f.severity === 'CRITICAL') return 'complex';
                            const cat = (f.category ?? '').toLowerCase();
                            if (cat.includes('port') || cat.includes('cve') || cat.includes('vuln')) return 'complex';
                            if (cat.includes('ssl') || cat.includes('tls') || cat.includes('cert')) return 'medium';
                            if ((f.penalty ?? 0) >= 20) return 'medium';
                            return 'quick';
                          };
                          const actionFindings: WithEffort[] = r.findings
                            .filter(f => f.severity !== 'INFO' && (f.penalty ?? 0) > 0)
                            .map(f => ({ ...f, effort: getEffort(f) }));
                          if (actionFindings.length === 0) return null;

                          const quickWins = actionFindings
                            .filter(f => f.effort === 'quick' && (f.penalty ?? 0) >= 8)
                            .sort((a, b) => (b.penalty ?? 0) - (a.penalty ?? 0))
                            .slice(0, 3);

                          const effortCfg = {
                            quick:   { label: lang === 'fr' ? '⚡ Rapide  < 2h'  : '⚡ Quick  < 2h',   cls: 'bg-green-500/10 text-green-400 border border-green-500/25' },
                            medium:  { label: lang === 'fr' ? '🔧 Moyen  2–8h'   : '🔧 Medium  2–8h', cls: 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/25' },
                            complex: { label: lang === 'fr' ? '🏗️ Complexe > 1j' : '🏗️ Complex > 1d', cls: 'bg-red-500/10 text-red-400 border border-red-500/25' },
                          };

                          const prioGroups = [
                            { key: 'p1', label: lang === 'fr' ? 'Priorité 1 — Maintenant'   : 'Priority 1 — Now',        dot: 'bg-red-500',    text: 'text-red-400',    border: 'border-red-500/20',    items: actionFindings.filter(f => f.severity === 'CRITICAL') },
                            { key: 'p2', label: lang === 'fr' ? 'Priorité 2 — Cette semaine': 'Priority 2 — This week',  dot: 'bg-orange-500', text: 'text-orange-400', border: 'border-orange-500/20', items: actionFindings.filter(f => f.severity === 'HIGH') },
                            { key: 'p3', label: lang === 'fr' ? 'Priorité 3 — Ce mois-ci'   : 'Priority 3 — This month', dot: 'bg-yellow-500', text: 'text-yellow-400', border: 'border-yellow-500/20', items: actionFindings.filter(f => f.severity === 'MEDIUM' || f.severity === 'LOW') },
                          ].filter(g => g.items.length > 0);

                          return (
                            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 overflow-hidden">
                              <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800 bg-slate-900/60">
                                <div className="flex items-center gap-2.5">
                                  <div className="p-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
                                    <ListChecks size={14} className="text-cyan-400" />
                                  </div>
                                  <h3 className="text-white font-bold text-sm">
                                    {lang === 'fr' ? "Plan d'action prioritaire" : 'Priority action plan'}
                                  </h3>
                                </div>
                                <span className="text-xs font-mono text-slate-500">
                                  {actionFindings.length} {lang === 'fr' ? 'actions' : 'actions'}
                                </span>
                              </div>
                              <div className="p-5 flex flex-col gap-5">
                                {quickWins.length > 0 && (
                                  <div className="bg-green-500/5 border border-green-500/20 rounded-xl p-4">
                                    <p className="text-xs font-bold text-green-400 mb-3 flex items-center gap-1.5">
                                      <Zap size={12} />
                                      {lang === 'fr' ? 'Quick wins — Corrections rapides à fort impact' : 'Quick wins — Fast fixes with high impact'}
                                    </p>
                                    <div className="flex flex-col gap-3">
                                      {quickWins.map((f, i) => (
                                        <div key={i} className="flex items-start gap-2.5">
                                          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded shrink-0 mt-0.5 ${SEVERITY_CONFIG[f.severity].badge}`}>{f.severity}</span>
                                          <div className="flex-1 min-w-0">
                                            <p className="text-slate-200 text-xs font-medium">{f.title ?? f.message}</p>
                                            <p className="text-slate-400 text-xs mt-0.5 leading-relaxed">{f.recommendation}</p>
                                          </div>
                                          <span className={`text-[10px] px-2 py-0.5 rounded-full whitespace-nowrap shrink-0 ${effortCfg[f.effort].cls}`}>{effortCfg[f.effort].label}</span>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                  {prioGroups.map(group => (
                                    <div key={group.key}>
                                      <div className="flex items-center gap-2 mb-3">
                                        <span className={`w-2 h-2 rounded-full shrink-0 ${group.dot}`} />
                                        <p className={`text-xs font-semibold ${group.text}`}>{group.label}</p>
                                        <span className="text-xs text-slate-600 font-mono ml-auto">{group.items.length}</span>
                                      </div>
                                      <div className="flex flex-col gap-2">
                                        {group.items.map((f, i) => (
                                          <div key={i} className={`rounded-xl border ${group.border} bg-slate-800/40 p-3`}>
                                            <div className="flex items-start justify-between gap-2 mb-1.5">
                                              <p className="text-slate-200 text-xs font-medium leading-snug">{f.title ?? f.message}</p>
                                              <span className={`text-[10px] px-1.5 py-0.5 rounded-full whitespace-nowrap shrink-0 ${effortCfg[f.effort].cls}`}>{effortCfg[f.effort].label}</span>
                                            </div>
                                            <p className="text-slate-500 text-xs leading-relaxed">{f.recommendation}</p>
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            </div>
                          );
                        })()}

                        {/* CTA contextuel */}
                        {nonInfoCount >= 2 && (
                          <div className="bg-gradient-to-r from-cyan-950/50 to-slate-900 border border-cyan-500/25 rounded-2xl p-4">
                            <div className="flex items-start gap-3">
                              <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/20 shrink-0 mt-0.5">
                                <MessageSquare size={15} className="text-cyan-400" />
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className="text-white font-bold text-sm mb-1">
                                  {nonInfoCount}{' '}
                                  {lang === 'fr'
                                    ? `vulnérabilité${nonInfoCount > 1 ? 's' : ''} identifiée${nonInfoCount > 1 ? 's' : ''} sur ${r.domain}`
                                    : `vulnerabilit${nonInfoCount > 1 ? 'ies' : 'y'} found on ${r.domain}`}
                                </p>
                                <p className="text-slate-400 text-xs leading-relaxed mb-3">
                                  {lang === 'fr'
                                    ? 'Notre équipe peut vous aider à corriger ces vulnérabilités. Contactez-nous pour obtenir un accompagnement personnalisé.'
                                    : 'Our team can help you fix these vulnerabilities. Contact us for personalised support.'}
                                </p>
                                <button onClick={onGoContact} className="flex items-center gap-1.5 text-xs font-bold text-cyan-400 hover:text-cyan-300 transition-colors">
                                  {lang === 'fr' ? 'Contactez-nous →' : 'Contact us →'}
                                </button>
                              </div>
                            </div>
                          </div>
                        )}
                      </motion.div>
                    )}

                    {/* ── Onglet Findings ───────────────────────────────── */}
                    {activeTab === 'findings' && (
                      <motion.div
                        key="tab-findings"
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        transition={{ duration: 0.18 }}
                        className="flex flex-col gap-6"
                      >
                        {r.findings.length === 0 ? (
                          <div className="flex flex-col items-center gap-3 py-12 text-center bg-slate-900/50 rounded-2xl border border-slate-800">
                            <div className="p-3 rounded-full bg-green-500/10 border border-green-500/20">
                              <Shield size={24} className="text-green-400" />
                            </div>
                            <p className="text-green-400 font-bold">{t('vulns_none')}</p>
                            <p className="text-slate-500 text-sm max-w-sm">{t('vulns_none_sub')}</p>
                          </div>
                        ) : (
                          <>
                            {/* 2 colonnes de findings */}
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                              {/* Colonne 1 — Infrastructure */}
                              <div className="flex flex-col gap-5">
                                <FindingGroup title={t('group_dns')}   findings={groups.dns}   startIdx={0} />
                                <FindingGroup title={t('group_ssl')}   findings={groups.ssl}   startIdx={groups.dns.length} />
                                <FindingGroup title={t('group_ports')} findings={groups.ports} startIdx={groups.dns.length + groups.ssl.length} />
                                {groups.reputation.length > 0
                                  ? <FindingGroup title={t('group_reputation')} findings={groups.reputation} startIdx={groups.dns.length + groups.ssl.length + groups.ports.length} />
                                  : (
                                    <div className="rounded-xl border border-green-500/20 bg-green-500/5 p-4 flex items-center gap-3">
                                      <div className="p-1.5 rounded-full bg-green-500/15 border border-green-500/25 shrink-0">
                                        <CheckCircle size={14} className="text-green-400" />
                                      </div>
                                      <div>
                                        <p className="text-green-400 font-semibold text-xs">{lang === 'fr' ? 'Réputation saine' : 'Clean reputation'}</p>
                                        <p className="text-slate-500 text-xs mt-0.5">{lang === 'fr' ? 'Domaine absent des blacklists et DNSBL vérifiées.' : 'Domain not found on any checked blacklists or DNSBL.'}</p>
                                      </div>
                                    </div>
                                  )
                                }
                              </div>
                              {/* Colonne 2 — Configuration & exposition */}
                              <div className="flex flex-col gap-5">
                                <FindingGroup title={t('group_headers')}    findings={groups.headers}    startIdx={groups.dns.length + groups.ssl.length + groups.ports.length + groups.reputation.length} />
                                <FindingGroup title={t('group_email')}      findings={groups.emailSec}   startIdx={groups.dns.length + groups.ssl.length + groups.ports.length + groups.reputation.length + groups.headers.length} />
                                <FindingGroup title={t('group_tech')}       findings={groups.tech}       startIdx={groups.dns.length + groups.ssl.length + groups.ports.length + groups.reputation.length + groups.headers.length + groups.emailSec.length} />
                              </div>
                            </div>

                            {/* Gate LOW findings — anonymes uniquement */}
                            {isAnon && hiddenLow.length > 0 && (
                              <motion.div
                                initial={{ opacity: 0, y: 6 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: 0.2 }}
                                className="relative rounded-xl overflow-hidden border border-slate-700/50 bg-slate-900/40"
                                style={{ boxShadow: '0 4px 20px rgba(0,0,0,0.3)' }}
                              >
                                {/* Faux aperçu flou */}
                                <div className="blur-sm opacity-40 pointer-events-none px-5 py-4 flex flex-col gap-3 select-none">
                                  {[...Array(Math.min(hiddenLow.length, 3))].map((_, i) => (
                                    <div key={i} className="h-12 rounded-lg bg-slate-800/60 border border-slate-700/40" />
                                  ))}
                                </div>
                                {/* Overlay CTA */}
                                <div
                                  className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-6 text-center"
                                  style={{ background: 'linear-gradient(180deg, rgba(15,21,30,0.3) 0%, rgba(15,21,30,0.85) 60%, rgba(15,21,30,0.95) 100%)' }}
                                >
                                  <SkuIcon color="#fbbf24" size={40}>
                                    <Lock size={20} className="text-amber-300" />
                                  </SkuIcon>
                                  <div>
                                    <p className="text-white font-bold text-sm">
                                      {lang === 'fr'
                                        ? `${hiddenLow.length} recommandation${hiddenLow.length > 1 ? 's' : ''} LOW masquée${hiddenLow.length > 1 ? 's' : ''}`
                                        : `${hiddenLow.length} LOW recommendation${hiddenLow.length > 1 ? 's' : ''} hidden`}
                                    </p>
                                    <p className="text-slate-400 text-xs mt-1">
                                      {lang === 'fr'
                                        ? 'Créez un compte gratuit pour accéder au plan de correction complet.'
                                        : 'Create a free account to access the full remediation plan.'}
                                    </p>
                                  </div>
                                  <button
                                    onClick={() => goRegister('low_findings_gate')}
                                    className="sku-btn-primary text-sm px-4 py-2 rounded-xl flex items-center gap-2"
                                  >
                                    <UserPlus size={14} />
                                    {lang === 'fr' ? 'Créer un compte gratuit' : 'Create free account'}
                                  </button>
                                </div>
                              </motion.div>
                            )}

                            {/* Infos — collapsible */}
                            {infoFindings.length > 0 && (
                              <details className="group">
                                <summary className="flex items-center gap-2 text-xs font-mono text-slate-600 cursor-pointer hover:text-slate-400 transition-colors list-none">
                                  <Info size={12} />
                                  {infoFindings.length} {t('findings_info')}
                                  <span className="text-slate-700 group-open:rotate-90 transition-transform">▶</span>
                                </summary>
                                <div className="mt-3 flex flex-col gap-3">
                                  {infoFindings.map((f, i) => (
                                    <FindingCard key={(f.title ?? f.message ?? '') + i} finding={f} index={i} />
                                  ))}
                                </div>
                              </details>
                            )}


                          </>
                        )}
                      </motion.div>
                    )}

                    {/* ── Onglet Avancé ─────────────────────────────────── */}
                    {activeTab === 'advanced' && (
                      <motion.div
                        key="tab-advanced"
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        transition={{ duration: 0.18 }}
                        className="flex flex-col gap-6"
                      >
                        {/* Analyses avancées */}
                        {(user?.plan === 'starter' || user?.plan === 'pro' || user?.plan === 'dev') ? (
                          <div className="flex flex-col gap-4">
                            <div className="flex items-center gap-2">
                              <div className="p-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
                                <Shield size={14} className="text-cyan-400" />
                              </div>
                              <h3 className="text-white font-bold text-sm">Analyses avancées</h3>
                              <span className="text-xs bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 px-1.5 py-0.5 rounded-full">Starter & Pro</span>
                            </div>
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                              {groups.subdomains.length > 0 && <FindingGroup title="🌐 Sous-domaines & Certificats" findings={groups.subdomains} startIdx={0} />}
                              {groups.vulns.length > 0 && <FindingGroup title="🔬 Versions Vulnérables" findings={groups.vulns} startIdx={groups.subdomains.length} />}
                              {groups.subdomains.length === 0 && groups.vulns.length === 0 && (
                                <div className="lg:col-span-2 flex items-center gap-3 py-5 px-4 bg-slate-900/50 rounded-xl border border-slate-800">
                                  <div className="p-2 rounded-full bg-green-500/10 border border-green-500/20">
                                    <Shield size={16} className="text-green-400" />
                                  </div>
                                  <div>
                                    <p className="text-green-400 font-bold text-sm">Aucune vulnérabilité avancée détectée</p>
                                    <p className="text-slate-500 text-xs">Sous-domaines et versions logicielles vérifiés — aucun problème critique trouvé.</p>
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>
                        ) : (
                          <div className="rounded-lg border border-dashed border-slate-600/60 bg-slate-800/30 p-5 flex flex-col gap-3">
                            <div className="flex items-center gap-2 text-slate-400 text-sm font-semibold">
                              <Lock size={14} className="text-cyan-500" />
                              <span className="text-slate-300">Analyses avancées — Starter & Pro</span>
                            </div>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                              <div className="rounded-md bg-slate-700/40 border border-slate-600/40 p-3 flex flex-col gap-1">
                                <span className="text-xs font-mono text-cyan-400">🌐 Fuites de sous-domaines</span>
                                <span className="text-xs text-slate-500">Certificats expirés, sous-domaines orphelins et risques de takeover via Certificate Transparency.</span>
                              </div>
                              <div className="rounded-md bg-slate-700/40 border border-slate-600/40 p-3 flex flex-col gap-1">
                                <span className="text-xs font-mono text-cyan-400">🔬 Versions vulnérables</span>
                                <span className="text-xs text-slate-500">Détection de PHP, Apache, nginx, IIS exposés avec des failles connues (CVE critiques).</span>
                              </div>
                            </div>
                            <button onClick={() => openPricing('upgrade_banner')} className="self-start mt-1 text-xs font-semibold px-3 py-1.5 rounded-md bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 hover:bg-cyan-500/30 transition-colors flex items-center gap-1.5">
                              <Lock size={11} />
                              Débloquer avec Starter — 9,90€/mois
                              <ArrowRight size={11} />
                            </button>
                          </div>
                        )}


                      </motion.div>
                    )}

                    {/* ── Onglet Recommandations ────────────────────────── */}
                    {activeTab === 'reco' && (
                      <motion.div
                        key="tab-reco"
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        transition={{ duration: 0.18 }}
                        className="flex flex-col gap-4"
                      >
                        {r.recommendations && r.recommendations.length > 0 ? (
                          <>
                            <p className="text-slate-500 text-xs px-1">
                              {lang === 'fr'
                                ? 'Actions correctives classées par ordre de priorité, issues de l\'analyse complète du domaine.'
                                : 'Corrective actions ranked by priority, derived from the full domain analysis.'}
                            </p>
                            {r.recommendations.map((rec, i) => {
                              const recLower = rec.toLowerCase();
                              const matchedLink = blogLinks.find(l =>
                                l.match_keyword.split(',').some(kw =>
                                  recLower.includes(kw.trim().toLowerCase())
                                )
                              );
                              return (
                                <div key={i} className="flex items-start gap-4 px-4 py-3.5 rounded-xl bg-slate-900/50 border border-slate-800 hover:border-slate-700 transition-colors">
                                  <span className="shrink-0 mt-0.5 w-6 h-6 rounded-full bg-amber-500/15 border border-amber-500/30 text-amber-400 text-[10px] font-bold flex items-center justify-center">
                                    {i + 1}
                                  </span>
                                  <div className="flex-1 min-w-0">
                                    <p className="text-slate-200 text-sm leading-relaxed">{rec}</p>
                                    {matchedLink && (
                                      <a
                                        href={matchedLink.article_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="inline-flex items-center gap-1.5 mt-2 text-[11px] text-cyan-400 hover:text-cyan-300 transition-colors font-medium"
                                      >
                                        <BookOpen size={11} />
                                        {lang === 'fr' ? 'Lire l\'article : ' : 'Read article: '}{matchedLink.article_title}
                                      </a>
                                    )}
                                  </div>
                                </div>
                              );
                            })}
                          </>
                        ) : (
                          <div className="flex flex-col items-center gap-3 py-12 text-center bg-slate-900/50 rounded-2xl border border-slate-800">
                            <div className="p-3 rounded-full bg-green-500/10 border border-green-500/20">
                              <Shield size={24} className="text-green-400" />
                            </div>
                            <p className="text-green-400 font-bold text-sm">
                              {lang === 'fr' ? 'Aucune recommandation — excellent score !' : 'No recommendations — excellent score!'}
                            </p>
                            <p className="text-slate-500 text-xs max-w-sm">
                              {lang === 'fr'
                                ? 'Le domaine ne présente aucune anomalie nécessitant une action corrective.'
                                : 'The domain shows no anomalies requiring corrective action.'}
                            </p>
                          </div>
                        )}
                      </motion.div>
                    )}

                  </AnimatePresence>
                </div>

              </motion.div>
            );
          })()}

        </AnimatePresence>

        {/* ══════════════════════════════════════════════════════════════════════
            SECTIONS MARKETING — visibles uniquement en état idle
        ══════════════════════════════════════════════════════════════════════ */}
        {isIdle && (
          <div className="mt-16 flex flex-col gap-24 pb-8">

            {/* ── 1. COMMENT ÇA MARCHE ─────────────────────────────────────── */}
            <section>
              <div className="text-center mb-10">
                <span className="text-xs font-semibold text-cyan-400 tracking-widest uppercase mb-3 block">
                  {lang === 'fr' ? 'Simple & rapide' : 'Simple & fast'}
                </span>
                <h2 className="text-2xl md:text-3xl font-black text-white mb-3">
                  {lang === 'fr' ? 'Comment ça marche ?' : 'How does it work?'}
                </h2>
                <p className="text-slate-500 text-sm max-w-md mx-auto">
                  {lang === 'fr'
                    ? 'En moins de 60 secondes, obtenez un rapport complet sur la sécurité de votre site.'
                    : 'In under 60 seconds, get a full security report for your website.'}
                </p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl mx-auto">
                {[
                  {
                    step: '01',
                    icon: <Globe size={20} className="text-cyan-400" />,
                    title: lang === 'fr' ? 'Entrez votre domaine' : 'Enter your domain',
                    desc: lang === 'fr'
                      ? 'Saisissez n\'importe quel nom de domaine (sans https://). L\'analyse démarre immédiatement.'
                      : 'Enter any domain name (without https://). Analysis starts immediately.',
                  },
                  {
                    step: '02',
                    icon: <Zap size={20} className="text-yellow-400" />,
                    title: lang === 'fr' ? 'Analyse automatique' : 'Automatic analysis',
                    desc: lang === 'fr'
                      ? 'Notre moteur inspecte SSL, DNS, ports ouverts, headers, réputation, technologies exposées et plus encore.'
                      : 'Our engine inspects SSL, DNS, open ports, headers, reputation, exposed technologies and more.',
                  },
                  {
                    step: '03',
                    icon: <CheckCircle size={20} className="text-green-400" />,
                    title: lang === 'fr' ? 'Recevez votre score' : 'Get your score',
                    desc: lang === 'fr'
                      ? 'Un score sur 100, les vulnérabilités classées par sévérité et un plan d\'action concret.'
                      : 'A score out of 100, vulnerabilities ranked by severity and a concrete action plan.',
                  },
                ].map((s, i) => (
                  <div key={i} className="relative flex flex-col gap-4 rounded-2xl border border-slate-800 bg-slate-900/50 p-6">
                    <div className="flex items-start justify-between">
                      <div className="p-2.5 rounded-xl bg-slate-800 border border-slate-700">
                        {s.icon}
                      </div>
                      <span className="text-4xl font-black text-slate-800 font-mono">{s.step}</span>
                    </div>
                    <div>
                      <p className="text-white font-bold text-sm mb-1.5">{s.title}</p>
                      <p className="text-slate-500 text-xs leading-relaxed">{s.desc}</p>
                    </div>
                    {i < 2 && (
                      <div className="hidden md:block absolute -right-3 top-1/2 -translate-y-1/2 z-10">
                        <ArrowRight size={16} className="text-slate-700" />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>

            {/* ── 2. FONCTIONNALITÉS ───────────────────────────────────────── */}
            <section>
              <div className="text-center mb-10">
                <span className="text-xs font-semibold text-cyan-400 tracking-widest uppercase mb-3 block">
                  {lang === 'fr' ? 'Ce que nous analysons' : 'What we analyse'}
                </span>
                <h2 className="text-2xl md:text-3xl font-black text-white mb-3">
                  {lang === 'fr' ? '20+ points de contrôle de sécurité' : '20+ security checkpoints'}
                </h2>
                <p className="text-slate-500 text-sm max-w-md mx-auto">
                  {lang === 'fr'
                    ? 'Un audit complet en une seule analyse, sans installation ni configuration.'
                    : 'A complete audit in a single scan, no installation or configuration required.'}
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

            {/* ── 2b. RAPPORT EXEMPLE ──────────────────────────────────────── */}
            <section>
              <div className="text-center mb-10">
                <span className="text-xs font-semibold text-cyan-400 tracking-widest uppercase mb-3 block">
                  {lang === 'fr' ? 'Exemple de résultat' : 'Sample result'}
                </span>
                <h2 className="text-2xl md:text-3xl font-black text-white mb-3">
                  {lang === 'fr' ? 'Un rapport clair et actionnable' : 'A clear and actionable report'}
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
                  {lang === 'fr' ? 'Plan Pro' : 'Pro plan'}
                </span>
                <h2 className="text-2xl md:text-3xl font-black text-white mb-3">
                  {lang === 'fr' ? 'Intégrez la sécurité dans votre stack' : 'Integrate security into your stack'}
                </h2>
                <p className="text-slate-500 text-sm max-w-lg mx-auto">
                  {lang === 'fr'
                    ? 'Le plan Pro va au-delà du scan : automatisation, intégrations et personnalisation pour les équipes et agences.'
                    : 'The Pro plan goes beyond scanning: automation, integrations and customisation for teams and agencies.'}
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
            onGoLogin={() => { setModalOpen(false); onGoLogin?.(); }}
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

      {/* ── Modal : Profil RGPD ─────────────────────────────────────────── */}
      <ProfileModal
        open={profileModalOpen}
        onClose={() => setProfileModalOpen(false)}
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
          <button onClick={() => onGoLegal?.('mentions')}       className="hover:text-slate-400 transition-colors">Mentions légales</button>
          <button onClick={() => onGoLegal?.('confidentialite')} className="hover:text-slate-400 transition-colors">Confidentialité & RGPD</button>
          <button onClick={() => onGoLegal?.('cgv')}             className="hover:text-slate-400 transition-colors">CGV</button>
          <button onClick={() => onGoLegal?.('cgu')}             className="hover:text-slate-400 transition-colors">CGU</button>
          <button onClick={() => onGoLegal?.('cookies')}         className="hover:text-slate-400 transition-colors">Cookies</button>
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
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-composants internes
// ─────────────────────────────────────────────────────────────────────────────

function StatCard({
  label, value, highlight, small,
}: {
  label: string; value: string | number; highlight?: boolean; small?: boolean;
}) {
  return (
    <div className={`
      rounded-xl border p-3 text-center
      ${highlight
        ? 'border-red-500/40 bg-red-500/5'
        : 'border-slate-800 bg-slate-900'}
    `}>
      <p className={`font-black ${small ? 'text-lg' : 'text-2xl'} font-mono ${highlight ? 'text-red-400' : 'text-white'}`}>
        {value}
      </p>
      <p className="text-slate-500 text-[10px] font-mono mt-0.5">{label}</p>
    </div>
  );
}

function PortSummary({ portDetails }: { portDetails: Record<string, { service: string; open: boolean; severity: string }> }) {
  const { t } = useLanguage();
  const entries = Object.entries(portDetails)
    .map(([port, v]) => ({ port: parseInt(port), ...v }))
    .sort((a, b) => a.port - b.port);

  const openPorts  = entries.filter(p => p.open);
  const closedCount = entries.filter(p => !p.open).length;

  if (entries.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.3 }}
      className="bg-slate-900/60 border border-slate-800 rounded-xl p-4"
    >
      <h4 className="text-xs font-mono text-slate-500 uppercase tracking-widest mb-3 flex items-center gap-2">
        <Globe size={12} />
        {t('ports_map')}
        <span className="ml-auto text-slate-700 font-normal normal-case">
          {openPorts.length} {t('ports_open', { closed: closedCount })}
        </span>
      </h4>
      <div className="flex flex-wrap gap-2">
        {entries.map(({ port, service, open, severity }) => (
          <div
            key={port}
            className={`
              flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono border
              ${open
                ? severity === 'CRITICAL'
                  ? 'bg-red-500/15 border-red-500/40 text-red-300'
                  : severity === 'HIGH'
                  ? 'bg-orange-500/15 border-orange-500/40 text-orange-300'
                  : 'bg-blue-500/10 border-blue-500/30 text-blue-300'
                : 'bg-slate-800/60 border-slate-700/50 text-slate-600'}
            `}
          >
            <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${open ? (severity === 'CRITICAL' ? 'bg-red-500' : 'bg-orange-400') : 'bg-slate-700'}`} />
            {port}
            <span className="text-[10px] opacity-70">{service}</span>
          </div>
        ))}
      </div>
    </motion.div>
  );
}
