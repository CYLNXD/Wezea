// ─── ClientSpace.tsx — Espace Client Pro ──────────────────────────────────────
//
// 4 onglets :
//   overview    → KPIs globaux + cartes domaines avec sparklines
//   monitoring  → CRUD domaines + seuil d'alerte éditable inline
//   history     → Historique des scans avec graphique + filtres par domaine
//   settings    → Profil & Sécurité, Facturation, Zone dangereuse
//
import { useState, useEffect, useCallback, type ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Globe, Shield, FileDown, Bell,
  BarChart2, Plus, Trash2, RefreshCw, X, Check,
  AlertTriangle, Clock, TrendingUp, TrendingDown, Minus,
  Settings, Mail, Key, CreditCard, Code, Webhook, Copy, ExternalLink,
  AppWindow, ScanSearch, CheckCircle2, FileText, ChevronDown, ChevronUp, BookOpen,
  Link2, MessageSquare,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { apiClient, getWhiteLabel, updateWhiteLabel, uploadWhiteLabelLogo, deleteWhiteLabelLogo } from '../lib/api';
import type { WhiteLabelSettings } from '../lib/api';
import { useLanguage } from '../i18n/LanguageContext';
import PricingModal from '../components/PricingModal';
import PageNavbar from '../components/PageNavbar';

// ─── SkuIcon ──────────────────────────────────────────────────────────────────

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
      <div className="absolute inset-0 pointer-events-none"
        style={{ borderRadius: r, background: 'linear-gradient(180deg,rgba(255,255,255,0.07) 0%,transparent 50%)' }} />
      {children}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface MonitoredDomain {
  domain:               string;
  last_score:           number | null;
  last_risk_level:      string | null;
  last_scan_at:         string | null;
  alert_threshold:      number;
  is_active:            boolean;
  checks_config:        Record<string, boolean>;
  created_at:           string;
  // Feature 2 — Surveillance élargie
  last_ssl_expiry_days: number | null;
  last_open_ports:      string[] | null;
  last_technologies:    Record<string, string> | null;
  // Feature 3 — Scan programmé
  scan_frequency:       'weekly' | 'biweekly' | 'monthly';
  email_report:         boolean;
  // Feature 4 — Alertes configurables
  ssl_alert_days:       number;
  alert_config_parsed:  {
    score_drop:        boolean;
    critical_findings: boolean;
    ssl_expiry:        boolean;
    port_changes:      boolean;
    tech_changes:      boolean;
  };
}

const CHECK_LABELS: { key: string; label: string }[] = [
  { key: 'ssl',        label: 'SSL' },
  { key: 'dns',        label: 'DNS' },
  { key: 'ports',      label: 'Ports' },
  { key: 'headers',    label: 'Headers' },
  { key: 'email',      label: 'Email' },
  { key: 'tech',       label: 'Tech' },
  { key: 'reputation', label: 'Réput.' },
];

interface ScanHistoryItem {
  id:              number;
  scan_uuid:       string;
  domain:          string;
  security_score:  number;
  risk_level:      string;
  findings_count:  number;
  scan_duration:   number;
  public_share:    boolean;
  created_at:      string;
}

interface ScanFinding {
  category:         string;
  severity:         string;
  title?:           string;
  message?:         string;
  plain_explanation?: string;
  technical_detail?:  string;
  recommendation?:    string;
  penalty?:           number;
}

interface ScanDetail {
  scan_uuid:       string;
  domain:          string;
  security_score:  number;
  risk_level:      string;
  findings:        ScanFinding[];
  created_at:      string;
  scan_duration:   number;
}

type Tab = 'overview' | 'monitoring' | 'apps' | 'history' | 'settings' | 'developer';

interface WebhookItem {
  id:            number;
  url:           string;
  events:        string[];
  is_active:     boolean;
  created_at:    string;
  last_fired_at: string | null;
  last_status:   number | null;
}

interface VerifiedApp {
  id: number;
  name: string;
  url: string;
  domain: string;
  verification_method: 'dns' | 'file';
  verification_token: string;
  is_verified: boolean;
  verified_at: string | null;
  last_scan_at: string | null;
  last_score: number | null;
  last_risk_level: string | null;
  created_at: string;
}

interface AppScanFinding {
  category: string;
  severity: string;
  title?: string;
  technical_detail?: string;
  plain_explanation?: string;
  recommendation?: string;
  penalty?: number;
}

interface DastFindingDetail {
  test_type: 'xss' | 'sqli' | 'csrf';
  severity: string;
  penalty: number;
  title: string;
  detail: string;
  evidence?: string | null;
  form_action?: string | null;
  field_name?: string | null;
}

interface DastDetails {
  forms_found: number;
  forms_tested: number;
  error?: string | null;
  findings: DastFindingDetail[];
}

interface SecretFindingDetail {
  pattern_name:   string;
  severity:       string;
  penalty:        number;
  description:    string;
  recommendation: string;
  matched_value:  string;
  source_url:     string;
  context:        string;
}

interface SecretDetails {
  scripts_found:   number;
  scripts_scanned: number;
  error?:          string | null;
  findings:        SecretFindingDetail[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers visuels
// ─────────────────────────────────────────────────────────────────────────────

const scoreColor = (s: number | null) =>
  s === null ? 'text-slate-500'
  : s >= 70   ? 'text-green-400'
  : s >= 40   ? 'text-orange-400'
  : 'text-red-400';

const scoreBorder = (s: number | null) =>
  s === null ? 'border-slate-700 bg-slate-900'
  : s >= 70   ? 'border-green-500/30 bg-green-500/5'
  : s >= 40   ? 'border-orange-500/30 bg-orange-500/5'
  : 'border-red-500/30 bg-red-500/5';

function RiskBadge({ level }: { level: string | null }) {
  if (!level) return <span className="text-slate-600 text-xs font-mono">—</span>;
  const cfg: Record<string, string> = {
    CRITICAL: 'bg-red-500/15 text-red-400 border-red-500/30',
    HIGH:     'bg-orange-500/15 text-orange-400 border-orange-500/30',
    MEDIUM:   'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
    LOW:      'bg-blue-500/15 text-blue-400 border-blue-500/30',
    MINIMAL:  'bg-green-500/15 text-green-400 border-green-500/30',
  };
  return (
    <span className={`text-xs font-bold px-1.5 py-0.5 rounded border ${cfg[level] ?? 'text-slate-400 border-slate-700'}`}>
      {level}
    </span>
  );
}

// Sparkline SVG simple (0–100, pas d'axe)
function Sparkline({ scores, width = 80, height = 32 }: { scores: number[]; width?: number; height?: number }) {
  if (scores.length < 2) return <span className="text-slate-700 text-xs font-mono">—</span>;

  const pts = scores.map((v, i) => {
    const x = (i / (scores.length - 1)) * width;
    const y = height - (Math.max(0, Math.min(100, v)) / 100) * height;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');

  const last  = scores[scores.length - 1];
  const first = scores[0];
  const c = last >= 70 ? '#34d399' : last >= 40 ? '#fb923c' : '#f87171';
  const lastX = width;
  const lastY = height - (Math.max(0, Math.min(100, last)) / 100) * height;

  const trend = last > first + 2 ? 'up' : last < first - 2 ? 'down' : 'stable';
  const TrendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus;
  const trendColor = trend === 'up' ? 'text-green-400' : trend === 'down' ? 'text-red-400' : 'text-slate-500';

  return (
    <div className="flex items-center gap-2">
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width, height }} className="shrink-0 overflow-visible">
        <polyline
          points={pts}
          fill="none"
          stroke={c}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx={lastX.toFixed(1)} cy={lastY.toFixed(1)} r="2.5" fill={c} />
      </svg>
      <TrendIcon size={12} className={trendColor} />
    </div>
  );
}

// Graphique pleine largeur pour l'onglet Historique
function ScoreLineChart({ scans, lang }: { scans: ScanHistoryItem[]; lang: 'fr' | 'en' }) {
  if (scans.length < 2) return null;
  const W = 600, H = 100, PAD = 16;
  const sorted = [...scans].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
  const pts = sorted.map((s, i) => {
    const x = PAD + (i / (sorted.length - 1)) * (W - PAD * 2);
    const y = PAD + (1 - s.security_score / 100) * (H - PAD * 2);
    return { x, y, score: s.security_score, date: s.created_at };
  });
  const polyline = pts.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  const last = pts[pts.length - 1].score;
  const c = last >= 70 ? '#34d399' : last >= 40 ? '#fb923c' : '#f87171';

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: H }}>
        {/* Grid lignes horizontales */}
        {[25, 50, 75].map(v => {
          const y = PAD + (1 - v / 100) * (H - PAD * 2);
          return (
            <g key={v}>
              <line x1={PAD} y1={y} x2={W - PAD} y2={y} stroke="rgba(255,255,255,0.04)" strokeWidth="1" />
              <text x={PAD - 4} y={y + 3} fill="#475569" fontSize="8" textAnchor="end">{v}</text>
            </g>
          );
        })}
        {/* Ligne */}
        <polyline points={polyline} fill="none" stroke={c} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        {/* Points */}
        {pts.map((p, i) => (
          <circle key={i} cx={p.x.toFixed(1)} cy={p.y.toFixed(1)} r="3.5" fill={c} stroke="#0f1520" strokeWidth="1.5" />
        ))}
      </svg>
      <div className="flex justify-between mt-1">
        <span className="text-slate-700 text-[10px] font-mono">{new Date(sorted[0].created_at).toLocaleDateString(lang === 'fr' ? 'fr-FR' : 'en-GB')}</span>
        <span className="text-slate-700 text-[10px] font-mono">{new Date(sorted[sorted.length - 1].created_at).toLocaleDateString(lang === 'fr' ? 'fr-FR' : 'en-GB')}</span>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Composant principal
// ─────────────────────────────────────────────────────────────────────────────

interface Props {
  onBack: () => void;
  onGoHistory?: () => void;
  onGoAdmin?: () => void;
  onGoContact?: () => void;
  initialTab?: Tab;
  initialSettingsSection?: 'profile' | 'billing' | 'whitelabel' | 'danger';
}

export default function ClientSpace({ onBack, onGoHistory, onGoAdmin, onGoContact, initialTab, initialSettingsSection }: Props) {
  const { user, deleteAccount, getPortalUrl, logout, refreshUser } = useAuth();
  const { lang } = useLanguage();

  const [tab, setTab]                   = useState<Tab>(initialTab ?? 'overview');
  const [domains, setDomains]           = useState<MonitoredDomain[]>([]);
  const [history, setHistory]           = useState<ScanHistoryItem[]>([]);
  const [loading, setLoading]           = useState(true);

  // Monitoring form
  const [newDomain, setNewDomain]       = useState('');
  const [addError, setAddError]         = useState('');
  const [addLoading, setAddLoading]     = useState(false);
  // Add-domain form config
  const [newDomainChecks, setNewDomainChecks] = useState<Record<string, boolean>>(
    Object.fromEntries(CHECK_LABELS.map(({ key }) => [key, true]))
  );
  const [newDomainFrequency, setNewDomainFrequency] = useState<'weekly' | 'biweekly' | 'monthly'>('weekly');
  const [newDomainEmailReport, setNewDomainEmailReport] = useState(false);

  // Threshold inline edit
  const [editingThreshold, setEditingThreshold] = useState<string | null>(null);
  const [thresholdValue, setThresholdValue]     = useState(10);

  // PDF
  const [pdfLoading, setPdfLoading]     = useState<string | null>(null);
  const [_pdfError, setPdfError]        = useState<string | null>(null);

  // Export JSON/CSV
  const [exportLoading, setExportLoading] = useState<string | null>(null); // "uuid-format"

  // Share public link
  const [shareLoading, setShareLoading] = useState<string | null>(null);
  const [shareCopied,  setShareCopied]  = useState<string | null>(null);

  // Scan result modal
  const [scanModal, setScanModal]       = useState<ScanDetail | null>(null);
  const [scanModalLoading, setScanModalLoading] = useState<string | null>(null);

  // Blog links (article recommendations)
  const [blogLinks, setBlogLinks] = useState<Array<{ id: number; match_keyword: string; article_title: string; article_url: string }>>([]);

  // Checks config editing (per domain)
  const [pendingChecks, setPendingChecks] = useState<Record<string, Record<string, boolean>>>({});
  const [checksLoading, setChecksLoading] = useState<string | null>(null);

  // History filter
  const [historyDomain, setHistoryDomain] = useState<string>('all');

  // Settings sub-section
  const [settingsSection, setSettingsSection] = useState<'profile' | 'billing' | 'whitelabel' | 'danger'>(initialSettingsSection ?? 'profile');

  // White-label state
  const [wb, setWb]                     = useState<WhiteLabelSettings | null>(null);
  const [wbLoading, setWbLoading]       = useState(false);
  const [wbSaving, setWbSaving]         = useState(false);
  const [wbMsg, setWbMsg]               = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  const [wbName, setWbName]             = useState('');
  const [wbColor, setWbColor]           = useState('#22d3ee');
  const [wbEnabled, setWbEnabled]       = useState(false);
  const [wbLogoUploading, setWbLogoUploading] = useState(false);
  // Change email form
  const [newEmail, setNewEmail]           = useState('');
  const [emailPassword, setEmailPassword] = useState('');
  const [emailLoading, setEmailLoading]   = useState(false);
  const [emailMsg, setEmailMsg]           = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  // Change password form
  const [currentPwd, setCurrentPwd]       = useState('');
  const [newPwd, setNewPwd]               = useState('');
  const [confirmPwd, setConfirmPwd]       = useState('');
  const [pwdLoading, setPwdLoading]       = useState(false);
  const [pwdMsg, setPwdMsg]               = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  // Billing
  const [portalLoading, setPortalLoading] = useState(false);
  // Delete account modal
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deletePassword, setDeletePassword]   = useState('');
  const [deleteLoading, setDeleteLoading]     = useState(false);
  const [deleteError, setDeleteError]         = useState('');

  // Integrations tab state (Slack / Teams)
  const [slackUrl, setSlackUrl]               = useState('');
  const [teamsUrl, setTeamsUrl]               = useState('');
  const [integrLoading, setIntegrLoading]     = useState(false);
  const [integrMsg, setIntegrMsg]             = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  const [integrConfigured, setIntegrConfigured] = useState<{ slack: boolean; teams: boolean }>({ slack: false, teams: false });

  // 2FA state
  const [mfaStep, setMfaStep]                 = useState<null | 'setup' | 'disabling'>(null);
  const [mfaQrCode, setMfaQrCode]             = useState('');        // base64 PNG
  const [mfaSecret, setMfaSecret]             = useState('');        // backup secret
  const [mfaCode, setMfaCode]                 = useState('');        // 6-digit input
  const [mfaDisablePwd, setMfaDisablePwd]     = useState('');
  const [mfaLoading, setMfaLoading]           = useState(false);
  const [mfaMsg, setMfaMsg]                   = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  // Developer tab state
  const [webhooks, setWebhooks]               = useState<WebhookItem[]>([]);
  const [whLoading, setWhLoading]             = useState(false);
  const [whNewUrl, setWhNewUrl]               = useState('');
  const [whNewEvents, setWhNewEvents]         = useState<string[]>(['scan.completed', 'alert.triggered']);
  const [whNewSecret, setWhNewSecret]         = useState('');
  const [whAddLoading, setWhAddLoading]       = useState(false);
  const [whAddError, setWhAddError]           = useState('');
  const [whCreatedSecret, setWhCreatedSecret] = useState<string | null>(null);
  const [whTestLoading, setWhTestLoading]     = useState<number | null>(null);
  const [whTestResult, setWhTestResult]       = useState<Record<number, { ok: boolean; status: number }>>({});
  const [apiKeyVisible, setApiKeyVisible]     = useState(false);
  const [apiKeyLoading, setApiKeyLoading]     = useState(false);
  const [apiKeyCopied, setApiKeyCopied]       = useState(false);
  const [apiKeyMsg, setApiKeyMsg]             = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  // Applications tab state
  const [apps, setApps]                         = useState<VerifiedApp[]>([]);
  const [appNewName, setAppNewName]             = useState('');
  const [appNewUrl, setAppNewUrl]               = useState('');
  const [appNewMethod, setAppNewMethod]         = useState<'dns' | 'file'>('dns');
  const [appAddLoading, setAppAddLoading]       = useState(false);
  const [appAddError, setAppAddError]           = useState('');
  const [appVerifyLoading, setAppVerifyLoading] = useState<number | null>(null);
  const [appVerifyMsg, setAppVerifyMsg]         = useState<Record<number, { ok: boolean; msg: string }>>({});
  const [appScanLoading, setAppScanLoading]     = useState<number | null>(null);
  const [appScanResults, setAppScanResults]     = useState<Record<number, AppScanFinding[]>>({});
  const [appScanDetails, setAppScanDetails]     = useState<Record<number, { dast?: DastDetails; secrets?: SecretDetails }>>({});
  const [appExpandedId, setAppExpandedId]       = useState<number | null>(null);
  const [appVerifyInfo, setAppVerifyInfo]       = useState<Record<number, boolean>>({});

  const [pricingModalOpen, setPricingModalOpen] = useState(false);
  const isPremium = user?.plan === 'starter' || user?.plan === 'pro' || user?.plan === 'dev';
  const planLimit = user?.plan === 'starter' ? 1 : null; // null = illimité (pro/dev)

  // ── Data fetching ──────────────────────────────────────────────────────────

  const fetchDomains = useCallback(async () => {
    if (!isPremium) return;
    try {
      const { data } = await apiClient.get('/monitoring/domains');
      setDomains(data);
    } catch { /* silencieux */ }
  }, [isPremium]);

  const fetchHistory = useCallback(async () => {
    try {
      const { data } = await apiClient.get('/scans/history?limit=100');
      setHistory(data.scans ?? []);
    } catch { /* silencieux */ }
  }, []);

  useEffect(() => {
    setLoading(true);
    Promise.all([fetchDomains(), fetchHistory()]).finally(() => setLoading(false));
    apiClient.get('/public/blog-links').then(r => setBlogLinks(r.data)).catch(() => {});
  }, [fetchDomains, fetchHistory]);

  // Charger les settings white-label si plan Pro
  useEffect(() => {
    if (!user || user.plan !== 'pro') return;
    setWbLoading(true);
    getWhiteLabel()
      .then(data => {
        setWb(data);
        setWbEnabled(data.enabled);
        setWbName(data.company_name ?? '');
        setWbColor(data.primary_color ?? '#22d3ee');
      })
      .catch(() => {})
      .finally(() => setWbLoading(false));
  }, [user]);

  // ── Applications actions ───────────────────────────────────────────────────

  const handleAddApp = async () => {
    const name = appNewName.trim();
    const url  = appNewUrl.trim();
    if (!name || !url) return;
    setAppAddLoading(true);
    setAppAddError('');
    try {
      await apiClient.post('/apps', { name, url, verification_method: appNewMethod });
      setAppNewName('');
      setAppNewUrl('');
      await fetchApps();
    } catch (e: any) {
      setAppAddError(e?.response?.data?.detail ?? (lang === 'fr' ? 'Erreur lors de l\'ajout.' : 'Error adding application.'));
    } finally {
      setAppAddLoading(false);
    }
  };

  const handleDeleteApp = async (appId: number) => {
    try {
      await apiClient.delete(`/apps/${appId}`);
      await fetchApps();
      setAppScanResults(prev => { const n = { ...prev }; delete n[appId]; return n; });
      setAppScanDetails(prev => { const n = { ...prev }; delete n[appId]; return n; });
    } catch { /* silencieux */ }
  };

  const handleVerifyApp = async (appId: number) => {
    setAppVerifyLoading(appId);
    setAppVerifyMsg(prev => { const n = { ...prev }; delete n[appId]; return n; });
    try {
      const { data } = await apiClient.post(`/apps/${appId}/verify`);
      setAppVerifyMsg(prev => ({ ...prev, [appId]: { ok: data.verified, msg: data.message } }));
      if (data.verified) await fetchApps();
    } catch {
      setAppVerifyMsg(prev => ({ ...prev, [appId]: { ok: false, msg: lang === 'fr' ? 'Erreur de vérification.' : 'Verification error.' } }));
    } finally {
      setAppVerifyLoading(null);
    }
  };

  const handleScanApp = async (appId: number) => {
    setAppScanLoading(appId);
    try {
      const { data } = await apiClient.post(`/apps/${appId}/scan`);
      setAppScanResults(prev => ({ ...prev, [appId]: data.findings ?? [] }));
      setAppScanDetails(prev => ({ ...prev, [appId]: { dast: data.details?.dast, secrets: data.details?.secrets } }));
      setAppExpandedId(appId);
      await fetchApps();
    } catch (e: any) {
      const msg = e?.response?.data?.detail ?? (lang === 'fr' ? 'Erreur pendant le scan.' : 'Scan error.');
      setAppScanResults(prev => ({ ...prev, [appId]: [] }));
      alert(msg);
    } finally {
      setAppScanLoading(null);
    }
  };

  // ── Monitoring actions ─────────────────────────────────────────────────────

  const addDomain = async () => {
    const d = newDomain.trim().toLowerCase().replace(/^https?:\/\//, '').replace(/\/.*$/, '');
    if (!d) return;
    setAddLoading(true);
    setAddError('');
    try {
      await apiClient.post('/monitoring/domains', { domain: d });
      // Apply non-default config immediately after creation
      const allEnabled = CHECK_LABELS.every(({ key }) => newDomainChecks[key] !== false);
      const isDefaultFreq = newDomainFrequency === 'weekly';
      const isDefaultEmail = !newDomainEmailReport;
      if (!allEnabled || !isDefaultFreq || !isDefaultEmail) {
        await apiClient.patch(`/monitoring/domains/${d}`, {
          checks_config:  newDomainChecks,
          scan_frequency: newDomainFrequency,
          email_report:   newDomainEmailReport,
        });
      }
      setNewDomain('');
      setNewDomainChecks(Object.fromEntries(CHECK_LABELS.map(({ key }) => [key, true])));
      setNewDomainFrequency('weekly');
      setNewDomainEmailReport(false);
      await fetchDomains();
    } catch (err: any) {
      setAddError(err?.response?.data?.detail?.error ?? (lang === 'fr' ? 'Erreur lors de l\'ajout' : 'Error adding domain'));
    } finally {
      setAddLoading(false);
    }
  };

  const removeDomain = async (domain: string) => {
    try {
      await apiClient.delete(`/monitoring/domains/${domain}`);
      await fetchDomains();
    } catch { /* silencieux */ }
  };

  const [scanningDomain, setScanningDomain] = useState<string | null>(null);
  const [scanDoneMap, setScanDoneMap]       = useState<Record<string, boolean>>({});

  const scanDomainNow = async (domain: string) => {
    if (scanningDomain) return;
    setScanningDomain(domain);
    setScanDoneMap(prev => ({ ...prev, [domain]: false }));
    try {
      await apiClient.post(`/monitoring/domains/${domain}/scan`);
      await fetchDomains();
      await fetchHistory();
      setScanDoneMap(prev => ({ ...prev, [domain]: true }));
      setTimeout(() => setScanDoneMap(prev => { const n = { ...prev }; delete n[domain]; return n; }), 3000);
    } catch { /* silencieux */ }
    finally { setScanningDomain(null); }
  };

  const saveThreshold = async (domain: string) => {
    try {
      await apiClient.patch(`/monitoring/domains/${domain}`, { alert_threshold: thresholdValue });
      setEditingThreshold(null);
      await fetchDomains();
    } catch { /* silencieux */ }
  };

  const toggleCheck = async (d: MonitoredDomain, key: string) => {
    const current = pendingChecks[d.domain] ?? d.checks_config;
    const updated = { ...current, [key]: !current[key] };
    // Mise à jour optimiste
    setPendingChecks(prev => ({ ...prev, [d.domain]: updated }));
    setChecksLoading(d.domain + ':' + key);
    try {
      await apiClient.patch(`/monitoring/domains/${d.domain}`, { checks_config: updated });
      await fetchDomains();
      // Nettoyer l'état pending après refresh
      setPendingChecks(prev => { const n = { ...prev }; delete n[d.domain]; return n; });
    } catch {
      // Rollback
      setPendingChecks(prev => ({ ...prev, [d.domain]: current }));
    } finally {
      setChecksLoading(null);
    }
  };

  // ── PDF ────────────────────────────────────────────────────────────────────

  const generatePdf = async (scanUuid: string, domain: string) => {
    setPdfLoading(scanUuid);
    setPdfError(null);
    try {
      // Un seul appel — le backend construit le PDF directement depuis la DB
      const { data, headers } = await apiClient.get(
        `/scans/history/${scanUuid}/export?format=pdf&lang=${lang}`,
        { responseType: 'blob' },
      );
      const cd = (headers['content-disposition'] ?? '') as string;
      const match = cd.match(/filename="([^"]+)"/);
      const filename = match ? match[1] : `wezea-report-${domain}-${new Date().toISOString().slice(0, 10)}.pdf`;
      const url = URL.createObjectURL(new Blob([data], { type: 'application/pdf' }));
      const a   = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      // Quand responseType: 'blob', les erreurs HTTP arrivent aussi en Blob → on lit le texte
      let msg = lang === 'fr' ? 'Erreur lors de la génération du PDF. Réessayez.' : 'Error generating PDF. Please try again.';
      if (err?.response?.data instanceof Blob) {
        try {
          const text = await (err.response.data as Blob).text();
          const json = JSON.parse(text);
          msg = json?.detail?.message ?? json?.detail ?? json?.message ?? text;
        } catch { /* ignore parse errors */ }
      } else {
        msg = err?.response?.data?.detail?.message ?? err?.response?.data?.message ?? err?.message ?? msg;
      }
      setPdfError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setPdfLoading(null);
    }
  };

  // ── Export scan JSON / CSV ─────────────────────────────────────────────────

  const exportScan = useCallback(async (scanUuid: string, domain: string, format: 'json' | 'csv') => {
    const key = `${scanUuid}-${format}`;
    setExportLoading(key);
    try {
      const { data, headers } = await apiClient.get(
        `/scans/history/${scanUuid}/export?format=${format}`,
        { responseType: 'blob' }
      );
      const cd = (headers['content-disposition'] ?? '') as string;
      const match = cd.match(/filename="([^"]+)"/);
      const filename = match ? match[1] : `wezea-scan-${domain}.${format}`;
      const url = URL.createObjectURL(new Blob([data]));
      const a   = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch { /* silent */ }
    finally { setExportLoading(null); }
  }, []);

  // ── Toggle public share link ───────────────────────────────────────────────

  const toggleShare = useCallback(async (scanUuid: string) => {
    setShareLoading(scanUuid);
    try {
      const { data } = await apiClient.patch(`/scans/history/${scanUuid}/share`);
      // Update local state
      setHistory(prev => prev.map(s =>
        s.scan_uuid === scanUuid ? { ...s, public_share: data.public_share } : s
      ));
      // If now shared, copy link to clipboard
      if (data.public_share) {
        const link = `${window.location.origin}/r/${scanUuid}`;
        try { await navigator.clipboard.writeText(link); } catch { /* ignore */ }
        setShareCopied(scanUuid);
        setTimeout(() => setShareCopied(c => c === scanUuid ? null : c), 3000);
      }
    } catch { /* silent */ }
    finally { setShareLoading(null); }
  }, []);

  // ── Open scan result modal ─────────────────────────────────────────────────

  const openScanModal = async (scanUuid: string) => {
    setScanModalLoading(scanUuid);
    try {
      const { data } = await apiClient.get(`/scans/history/${scanUuid}`);
      setScanModal(data as ScanDetail);
    } catch { /* silencieux */ }
    finally { setScanModalLoading(null); }
  };

  // ── Données dérivées ───────────────────────────────────────────────────────

  const historyByDomain = history.reduce<Record<string, ScanHistoryItem[]>>((acc, s) => {
    if (!acc[s.domain]) acc[s.domain] = [];
    acc[s.domain].push(s);
    return acc;
  }, {});

  const avgScore = (() => {
    const scored = domains.filter(d => d.last_score !== null);
    if (!scored.length) return null;
    return Math.round(scored.reduce((s, d) => s + (d.last_score ?? 0), 0) / scored.length);
  })();

  const criticalDomains = domains.filter(d => d.last_score !== null && d.last_score < 40).length;

  // Total findings du dernier scan connu par domaine surveillé
  const totalOpenFindings = domains.reduce((sum, d) => {
    const latest = historyByDomain[d.domain]?.[0]; // tri newest-first côté API
    return sum + (latest?.findings_count ?? 0);
  }, 0);

  const filteredHistory = historyDomain === 'all' ? history : history.filter(s => s.domain === historyDomain);

  // ── Settings handlers ──────────────────────────────────────────────────────

  const handleChangeEmail = async () => {
    setEmailLoading(true);
    setEmailMsg(null);
    try {
      await apiClient.post('/auth/change-email', { new_email: newEmail, current_password: emailPassword });
      setEmailMsg({ type: 'ok', text: lang === 'fr' ? 'Email mis à jour avec succès.' : 'Email updated successfully.' });
      setNewEmail('');
      setEmailPassword('');
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setEmailMsg({ type: 'err', text: msg ?? (lang === 'fr' ? 'Erreur lors de la mise à jour.' : 'Update failed.') });
    } finally {
      setEmailLoading(false);
    }
  };

  const handleChangePassword = async () => {
    if (newPwd !== confirmPwd) {
      setPwdMsg({ type: 'err', text: lang === 'fr' ? 'Les mots de passe ne correspondent pas.' : 'Passwords do not match.' });
      return;
    }
    setPwdLoading(true);
    setPwdMsg(null);
    try {
      await apiClient.post('/auth/change-password', { current_password: currentPwd, new_password: newPwd });
      setPwdMsg({ type: 'ok', text: lang === 'fr' ? 'Mot de passe mis à jour avec succès.' : 'Password updated successfully.' });
      setCurrentPwd(''); setNewPwd(''); setConfirmPwd('');
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setPwdMsg({ type: 'err', text: msg ?? (lang === 'fr' ? 'Erreur lors de la mise à jour.' : 'Update failed.') });
    } finally {
      setPwdLoading(false);
    }
  };

  const handlePortal = async () => {
    setPortalLoading(true);
    try {
      const url = await getPortalUrl();
      window.open(url, '_blank');
    } catch { /* silencieux */ }
    finally { setPortalLoading(false); }
  };

  // ── 2FA handlers ──
  const handleMfaSetup = async () => {
    setMfaLoading(true);
    setMfaMsg(null);
    try {
      const { data } = await apiClient.post('/auth/2fa/setup');
      setMfaQrCode(data.qr_base64);
      setMfaSecret(data.secret);
      setMfaCode('');
      setMfaStep('setup');
    } catch {
      setMfaMsg({ type: 'err', text: lang === 'fr' ? 'Erreur lors de la configuration.' : 'Setup error.' });
    } finally {
      setMfaLoading(false);
    }
  };

  const handleMfaVerify = async () => {
    setMfaLoading(true);
    setMfaMsg(null);
    try {
      await apiClient.post('/auth/2fa/verify', { code: mfaCode });
      await refreshUser();
      setMfaStep(null);
      setMfaCode('');
      setMfaMsg({ type: 'ok', text: lang === 'fr' ? 'Double authentification activée ✓' : 'Two-factor authentication enabled ✓' });
    } catch {
      setMfaMsg({ type: 'err', text: lang === 'fr' ? 'Code invalide. Réessayez.' : 'Invalid code. Please try again.' });
    } finally {
      setMfaLoading(false);
    }
  };

  const handleMfaDisable = async () => {
    setMfaLoading(true);
    setMfaMsg(null);
    try {
      await apiClient.delete('/auth/2fa/disable', { data: { password: mfaDisablePwd, code: mfaCode } });
      await refreshUser();
      setMfaStep(null);
      setMfaCode('');
      setMfaDisablePwd('');
      setMfaMsg({ type: 'ok', text: lang === 'fr' ? 'Double authentification désactivée.' : 'Two-factor authentication disabled.' });
    } catch {
      setMfaMsg({ type: 'err', text: lang === 'fr' ? 'Code ou mot de passe incorrect.' : 'Invalid code or password.' });
    } finally {
      setMfaLoading(false);
    }
  };

  const handleDeleteAccount = async () => {
    setDeleteLoading(true);
    setDeleteError('');
    try {
      await deleteAccount(deletePassword);
      logout();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setDeleteError(msg ?? (lang === 'fr' ? 'Mot de passe incorrect.' : 'Incorrect password.'));
      setDeleteLoading(false);
    }
  };

  // ── Developer tab helpers ──────────────────────────────────────────────────

  const fetchWebhooks = useCallback(async () => {
    if (!user || user.plan !== 'pro') return;
    setWhLoading(true);
    try {
      const { data } = await apiClient.get('/webhooks');
      setWebhooks(data);
    } catch { /* silencieux */ }
    finally { setWhLoading(false); }
  }, [user]);

  const addWebhook = async () => {
    setWhAddError('');
    setWhAddLoading(true);
    setWhCreatedSecret(null);
    try {
      const { data } = await apiClient.post('/webhooks', {
        url: whNewUrl.trim(),
        events: whNewEvents,
        secret: whNewSecret.trim() || undefined,
      });
      setWhCreatedSecret(data.secret);
      setWhNewUrl('');
      setWhNewSecret('');
      await fetchWebhooks();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setWhAddError(typeof detail === 'string' ? detail : (lang === 'fr' ? 'Erreur lors de la création.' : 'Creation failed.'));
    } finally { setWhAddLoading(false); }
  };

  const deleteWebhook = async (id: number) => {
    try {
      await apiClient.delete(`/webhooks/${id}`);
      setWebhooks(w => w.filter(h => h.id !== id));
    } catch { /* silencieux */ }
  };

  const testWebhook = async (id: number) => {
    setWhTestLoading(id);
    try {
      const { data } = await apiClient.post(`/webhooks/${id}/test`);
      setWhTestResult(r => ({ ...r, [id]: { ok: data.delivered, status: data.status } }));
    } catch { setWhTestResult(r => ({ ...r, [id]: { ok: false, status: 0 } })); }
    finally { setWhTestLoading(null); }
  };

  const regenerateApiKey = async () => {
    setApiKeyLoading(true);
    setApiKeyMsg(null);
    try {
      await apiClient.post('/auth/api-key/regenerate');
      setApiKeyMsg({ type: 'ok', text: lang === 'fr' ? 'Clé API régénérée. Rechargez la page pour la voir.' : 'API key regenerated. Reload the page to view it.' });
    } catch {
      setApiKeyMsg({ type: 'err', text: lang === 'fr' ? 'Erreur lors de la régénération.' : 'Regeneration failed.' });
    } finally { setApiKeyLoading(false); }
  };

  const copyApiKey = async () => {
    if (!user?.api_key) return;
    await navigator.clipboard.writeText(user.api_key);
    setApiKeyCopied(true);
    setTimeout(() => setApiKeyCopied(false), 2000);
  };

  // Load webhooks when switching to developer tab
  const fetchApps = useCallback(async () => {
    if (user?.plan !== 'dev' && !user?.is_admin) return;
    try {
      const { data } = await apiClient.get('/apps');
      setApps(data);
    } catch { /* silencieux */ }
  }, [user?.plan, user?.is_admin]);

  useEffect(() => {
    if (tab === 'developer') {
      fetchWebhooks();
      // Charger l'état actuel des intégrations
      if (user?.plan === 'pro' || user?.plan === 'dev' || user?.is_admin) {
        apiClient.get('/auth/integrations').then(({ data }) => {
          setIntegrConfigured({ slack: data.slack_configured, teams: data.teams_configured });
        }).catch(() => {});
      }
    }
    if (tab === 'apps') fetchApps();
  }, [tab, fetchWebhooks, fetchApps, user?.plan, user?.is_admin]);

  const ALLOWED_EVENTS = ['scan.completed', 'alert.triggered', 'score.dropped'];

  const tabs: { id: Tab; label: string; icon: JSX.Element }[] = [
    { id: 'overview',   label: lang === 'fr' ? 'Vue d\'ensemble' : 'Overview', icon: <BarChart2 size={14} /> },
    { id: 'monitoring', label: lang === 'fr' ? 'Monitoring' : 'Monitoring',    icon: <Globe size={14} /> },
    ...(user?.plan && (user.plan === 'dev') || user?.is_admin ? [{
      id: 'apps' as const,
      label: lang === 'fr' ? 'Applications' : 'Applications',
      icon: <AppWindow size={14} />,
    }] : []),
    { id: 'history',    label: lang === 'fr' ? 'Historique' : 'History',       icon: <RefreshCw size={14} /> },
    { id: 'settings',   label: lang === 'fr' ? 'Paramètres' : 'Settings',      icon: <Settings size={14} /> },
    ...(user?.plan && (user.plan === 'pro' || user.plan === 'dev') ? [{
      id: 'developer' as const,
      label: lang === 'fr' ? 'Développeur' : 'Developer',
      icon: <Code size={14} />,
    }] : []),
  ];

  // ─────────────────────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────────────────────

  return (
    <div className="relative min-h-screen text-slate-100">
      {/* Grille cyber — identique au hero Dashboard */}
      <div className="absolute inset-0 pointer-events-none" style={{ backgroundImage: 'linear-gradient(rgba(34,211,238,1) 1px, transparent 1px), linear-gradient(90deg, rgba(34,211,238,1) 1px, transparent 1px)', backgroundSize: '48px 48px', opacity: 0.025 }} />

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <PageNavbar
        onBack={onBack}
        title={lang === 'fr' ? 'Mon espace' : 'My space'}
        icon={<Shield size={14} />}
        onGoHistory={onGoHistory}
        onGoAdmin={onGoAdmin}
        onGoContact={onGoContact}
      />

      <main className="max-w-6xl mx-auto px-4 py-6">

        {/* ── Tab bar ─────────────────────────────────────────────────────── */}
        <div
          className="flex gap-1 mb-6 rounded-xl p-1 overflow-x-auto"
          style={{ background: 'linear-gradient(180deg,#0f151e,#0b1018)', border: '1px solid rgba(255,255,255,0.07)' }}
        >
          {tabs.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`
                flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium
                transition-all whitespace-nowrap flex-1 justify-center
                ${tab === t.id
                  ? 'bg-slate-800 text-white shadow-sm border border-slate-700'
                  : 'text-slate-500 hover:text-slate-300'}
              `}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </div>

        {/* ── Content ─────────────────────────────────────────────────────── */}
        {loading ? (
          <div className="flex items-center justify-center py-24">
            <div className="w-6 h-6 border-2 border-cyan-500/30 border-t-cyan-400 rounded-full animate-spin" />
          </div>
        ) : (
          <AnimatePresence mode="wait">
            <motion.div
              key={tab}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
            >

              {/* ══════════════════════════════════════════════════════════════
                  TAB 1 — VUE D'ENSEMBLE
              ══════════════════════════════════════════════════════════════ */}
              {tab === 'overview' && (
                <div className="flex flex-col gap-6">

                  {/* KPI cards */}
                  <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">

                    {/* Domaines surveillés */}
                    <div className="sku-card rounded-xl p-4">
                      <p className="text-slate-500 text-xs font-mono uppercase tracking-wider mb-2">{lang === 'fr' ? 'Domaines surveillés' : 'Monitored domains'}</p>
                      <p className="text-3xl font-black font-mono text-white">
                        {domains.length}
                        <span className="text-slate-600 text-base">
                          /{planLimit !== null ? planLimit : '∞'}
                        </span>
                      </p>
                      <div className="mt-3 h-1 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
                        <div
                          className="h-1 bg-cyan-500 rounded-full transition-all"
                          style={{ width: planLimit !== null ? `${Math.min((domains.length / planLimit) * 100, 100)}%` : '100%' }}
                        />
                      </div>
                    </div>

                    {/* Score moyen */}
                    <div className="sku-card rounded-xl p-4" style={avgScore !== null ? {
                      borderColor: avgScore >= 70 ? 'rgba(52,211,153,0.2)' : avgScore >= 40 ? 'rgba(251,191,36,0.2)' : 'rgba(248,113,113,0.2)',
                    } : {}}>
                      <p className="text-slate-500 text-xs font-mono uppercase tracking-wider mb-2">{lang === 'fr' ? 'Score moyen' : 'Average score'}</p>
                      <p className={`text-3xl font-black font-mono ${scoreColor(avgScore)}`}>
                        {avgScore !== null ? avgScore : '—'}
                        {avgScore !== null && <span className="text-base opacity-60">/100</span>}
                      </p>
                    </div>

                    {/* Domaines critiques */}
                    <div className="sku-card rounded-xl p-4" style={criticalDomains > 0 ? {
                      borderColor: 'rgba(248,113,113,0.25)',
                      background: 'linear-gradient(180deg,rgba(30,10,10,0.9) 0%,rgba(20,5,5,0.95) 100%)',
                    } : {}}>
                      <p className="text-slate-500 text-xs font-mono uppercase tracking-wider mb-2">{lang === 'fr' ? 'Domaines critiques' : 'Critical domains'}</p>
                      <div className="flex items-end gap-2">
                        <p className={`text-3xl font-black font-mono ${criticalDomains > 0 ? 'text-red-400' : 'text-slate-500'}`}>
                          {criticalDomains}
                        </p>
                        {criticalDomains > 0 && <AlertTriangle size={16} className="text-red-400 mb-1" />}
                      </div>
                    </div>

                    {/* Findings ouverts — remplace le "Lundi 06:00 UTC" hardcodé */}
                    <div className="sku-card rounded-xl p-4" style={totalOpenFindings > 0 ? {
                      borderColor: 'rgba(251,191,36,0.2)',
                    } : {}}>
                      <p className="text-slate-500 text-xs font-mono uppercase tracking-wider mb-2">{lang === 'fr' ? 'Findings ouverts' : 'Open findings'}</p>
                      <p className={`text-3xl font-black font-mono ${totalOpenFindings > 0 ? 'text-amber-400' : 'text-slate-500'}`}>
                        {totalOpenFindings}
                      </p>
                      <p className="text-slate-600 text-xs font-mono mt-1">
                        {lang === 'fr' ? 'tous domaines' : 'all domains'}
                      </p>
                    </div>
                  </div>

                  {/* Domain cards */}
                  {domains.length === 0 ? (
                    <div className="flex flex-col items-center gap-4 py-20 text-center">
                      <SkuIcon color="#22d3ee" size={52}><Globe size={24} className="text-cyan-300" /></SkuIcon>
                      <p className="text-slate-300 font-bold text-lg">{lang === 'fr' ? 'Aucun domaine sous surveillance' : 'No domain monitored'}</p>
                      <p className="text-slate-600 text-sm max-w-sm">
                        {lang === 'fr' ? 'Activez le monitoring pour recevoir des alertes automatiques chaque semaine.' : 'Enable monitoring to receive automatic alerts every week.'}
                      </p>
                      <button
                        onClick={() => setTab('monitoring')}
                        className="flex items-center gap-2 px-4 py-2 rounded-xl bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 hover:bg-cyan-500/30 transition text-sm font-semibold"
                      >
                        <Plus size={14} /> {lang === 'fr' ? 'Ajouter un domaine' : 'Add a domain'}
                      </button>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                      {domains.map(d => {
                        const domainScans = [...(historyByDomain[d.domain] ?? [])].reverse();
                        const scores = domainScans.map(h => h.security_score);
                        const scanCount = historyByDomain[d.domain]?.length ?? 0;

                        return (
                          <div key={d.domain} className={`rounded-xl border p-5 flex flex-col gap-3 ${scoreBorder(d.last_score)}`}>
                            {/* Domain + risk */}
                            <div className="flex items-start justify-between gap-2">
                              <div className="flex items-center gap-2 min-w-0">
                                <Globe size={13} className="text-slate-500 shrink-0 mt-0.5" />
                                <span className="text-white font-mono text-sm font-bold truncate">{d.domain}</span>
                              </div>
                              <RiskBadge level={d.last_risk_level} />
                            </div>

                            {/* Score + sparkline */}
                            <div className="flex items-end justify-between">
                              <div>
                                <p className={`text-4xl font-black font-mono leading-none ${scoreColor(d.last_score)}`}>
                                  {d.last_score ?? '—'}
                                </p>
                                <p className="text-slate-600 text-xs font-mono mt-0.5">/100</p>
                              </div>
                              <Sparkline scores={scores} width={90} height={36} />
                            </div>

                            {/* Footer */}
                            <div className="flex items-center justify-between text-[10px] font-mono text-slate-600 border-t border-slate-800/80 pt-2">
                              <span>
                                {d.last_scan_at
                                  ? `${lang === 'fr' ? 'Dernier scan' : 'Last scan'} ${new Date(d.last_scan_at).toLocaleDateString(lang === 'fr' ? 'fr-FR' : 'en-GB')}`
                                  : lang === 'fr' ? 'Aucun scan' : 'No scan'}
                              </span>
                              <span>{scanCount} scan{scanCount !== 1 ? 's' : ''}</span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* ══════════════════════════════════════════════════════════════
                  TAB — APPLICATIONS (Application Scanning)
              ══════════════════════════════════════════════════════════════ */}
              {tab === 'apps' && (
                <div className="flex flex-col gap-5">

                  {/* ── Add application ──────────────────────────────────── */}
                  <div className="sku-card rounded-xl p-5">
                    <div className="flex items-center gap-3 mb-4">
                      <SkuIcon color="#a78bfa" size={36}>
                        <AppWindow size={16} className="text-violet-300" />
                      </SkuIcon>
                      <div>
                        <p className="text-white font-bold text-sm">
                          {lang === 'fr' ? 'Ajouter une application' : 'Add an application'}
                        </p>
                        <p className="text-slate-500 text-xs">
                          {lang === 'fr'
                            ? 'Scannez vos applications web custom pour détecter les vulnérabilités'
                            : 'Scan your custom web apps to detect vulnerabilities'}
                        </p>
                      </div>
                    </div>

                    <div className="flex flex-col gap-3">
                      <div className="flex gap-2 flex-wrap">
                        <input
                          type="text"
                          placeholder={lang === 'fr' ? 'Nom (ex: Mon App)' : 'Name (e.g. My App)'}
                          value={appNewName}
                          onChange={e => setAppNewName(e.target.value)}
                          className="flex-1 min-w-[160px] sku-inset rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-violet-500 transition placeholder:text-slate-600"
                        />
                        <input
                          type="text"
                          placeholder="https://monapp.exemple.com"
                          value={appNewUrl}
                          onChange={e => { setAppNewUrl(e.target.value); setAppAddError(''); }}
                          onKeyDown={e => e.key === 'Enter' && handleAddApp()}
                          className="flex-1 min-w-[220px] sku-inset rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-violet-500 transition placeholder:text-slate-600"
                        />
                      </div>
                      {/* Méthode de vérification */}
                      <div className="flex gap-2 items-center flex-wrap">
                        <span className="text-slate-500 text-xs">{lang === 'fr' ? 'Vérification :' : 'Ownership check:'}</span>
                        {(['dns', 'file'] as const).map(m => (
                          <button
                            key={m}
                            type="button"
                            onClick={() => setAppNewMethod(m)}
                            className={`text-xs font-mono px-3 py-1 rounded-md border transition-all ${
                              appNewMethod === m
                                ? 'bg-violet-500/15 text-violet-300 border-violet-500/30'
                                : 'bg-slate-900 text-slate-500 border-slate-700 hover:border-slate-600'
                            }`}
                          >
                            {m === 'dns' ? '📡 DNS TXT' : '📄 Fichier .well-known'}
                          </button>
                        ))}
                        <button
                          onClick={handleAddApp}
                          disabled={appAddLoading || !appNewName.trim() || !appNewUrl.trim()}
                          className="ml-auto flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-violet-500/20 text-violet-300 border border-violet-500/30 hover:bg-violet-500/30 transition text-sm font-semibold disabled:opacity-40"
                        >
                          {appAddLoading
                            ? <div className="w-3.5 h-3.5 border-2 border-violet-400/30 border-t-violet-400 rounded-full animate-spin" />
                            : <Plus size={14} />
                          }
                          {lang === 'fr' ? 'Ajouter' : 'Add'}
                        </button>
                      </div>
                      {appAddError && <p className="text-red-400 text-xs">{appAddError}</p>}
                    </div>
                  </div>

                  {/* ── Liste des applications ────────────────────────────── */}
                  {apps.length === 0 ? (
                    <div className="sku-card rounded-xl p-10 text-center">
                      <AppWindow size={32} className="text-slate-700 mx-auto mb-3" />
                      <p className="text-slate-500 text-sm">
                        {lang === 'fr'
                          ? 'Aucune application enregistrée. Ajoutez votre première application web pour commencer le scan.'
                          : 'No application registered. Add your first web app to start scanning.'}
                      </p>
                    </div>
                  ) : (
                    <div className="flex flex-col gap-4">
                      {apps.map(app => {
                        const isExpanded = appExpandedId === app.id;
                        const scanResult = appScanResults[app.id];
                        const scanDetails = appScanDetails[app.id];
                        const verifyMsg  = appVerifyMsg[app.id];
                        const showVerifyInfo = appVerifyInfo[app.id];

                        return (
                          <div key={app.id} className="sku-card rounded-xl overflow-hidden">
                            {/* ── Header row ─────────────────────────────── */}
                            <div className="flex items-center gap-3 p-4">
                              <SkuIcon color={app.is_verified ? '#4ade80' : '#fbbf24'} size={36}>
                                {app.is_verified
                                  ? <CheckCircle2 size={16} className="text-green-300" />
                                  : <AlertTriangle size={16} className="text-amber-300" />
                                }
                              </SkuIcon>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <p className="text-white font-semibold text-sm">{app.name}</p>
                                  {app.is_verified
                                    ? <span className="text-[10px] font-bold text-green-400 bg-green-500/10 border border-green-500/20 px-1.5 py-0.5 rounded">✓ VÉRIFIÉ</span>
                                    : <span className="text-[10px] font-bold text-amber-400 bg-amber-500/10 border border-amber-500/20 px-1.5 py-0.5 rounded">EN ATTENTE</span>
                                  }
                                </div>
                                <p className="text-slate-500 text-xs font-mono truncate">{app.url}</p>
                              </div>
                              {/* Score badge */}
                              {app.last_score !== null && (
                                <div className={`text-center shrink-0 ${scoreColor(app.last_score)}`}>
                                  <p className="text-2xl font-black font-mono">{app.last_score}</p>
                                  <p className="text-[10px] text-slate-600">/100</p>
                                </div>
                              )}
                              {/* Actions */}
                              <div className="flex items-center gap-1.5 shrink-0">
                                {/* Vérifier */}
                                {!app.is_verified && (
                                  <button
                                    title={lang === 'fr' ? 'Vérifier l\'ownership' : 'Verify ownership'}
                                    onClick={() => handleVerifyApp(app.id)}
                                    disabled={appVerifyLoading === app.id}
                                    className="p-2 rounded-lg text-amber-400 hover:bg-amber-500/10 border border-transparent hover:border-amber-500/20 transition disabled:opacity-40"
                                  >
                                    {appVerifyLoading === app.id
                                      ? <div className="w-3.5 h-3.5 border-2 border-amber-400/30 border-t-amber-400 rounded-full animate-spin" />
                                      : <CheckCircle2 size={14} />
                                    }
                                  </button>
                                )}
                                {/* Info vérification */}
                                {!app.is_verified && (
                                  <button
                                    title={lang === 'fr' ? 'Instructions de vérification' : 'Verification instructions'}
                                    onClick={() => setAppVerifyInfo(prev => ({ ...prev, [app.id]: !prev[app.id] }))}
                                    className="p-2 rounded-lg text-slate-400 hover:bg-slate-700 border border-transparent hover:border-slate-600 transition"
                                  >
                                    <FileText size={14} />
                                  </button>
                                )}
                                {/* Lancer scan */}
                                {app.is_verified && (
                                  <button
                                    title={lang === 'fr' ? 'Lancer un scan' : 'Run scan'}
                                    onClick={() => handleScanApp(app.id)}
                                    disabled={appScanLoading === app.id}
                                    className="p-2 rounded-lg text-violet-400 hover:bg-violet-500/10 border border-transparent hover:border-violet-500/20 transition disabled:opacity-40"
                                  >
                                    {appScanLoading === app.id
                                      ? <div className="w-3.5 h-3.5 border-2 border-violet-400/30 border-t-violet-400 rounded-full animate-spin" />
                                      : <ScanSearch size={14} />
                                    }
                                  </button>
                                )}
                                {/* Toggle findings */}
                                {scanResult && (
                                  <button
                                    onClick={() => setAppExpandedId(isExpanded ? null : app.id)}
                                    className="p-2 rounded-lg text-slate-400 hover:bg-slate-700 border border-transparent hover:border-slate-600 transition"
                                  >
                                    {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                                  </button>
                                )}
                                {/* Supprimer */}
                                <button
                                  title={lang === 'fr' ? 'Supprimer' : 'Delete'}
                                  onClick={() => handleDeleteApp(app.id)}
                                  className="p-2 rounded-lg text-slate-600 hover:bg-red-500/10 hover:text-red-400 border border-transparent hover:border-red-500/20 transition"
                                >
                                  <Trash2 size={14} />
                                </button>
                              </div>
                            </div>

                            {/* ── Instructions de vérification ────────────── */}
                            {showVerifyInfo && (
                              <div className="mx-4 mb-4 p-4 rounded-xl border border-amber-500/20 bg-amber-500/5">
                                <p className="text-amber-300 text-xs font-semibold mb-2 flex items-center gap-1.5">
                                  <FileText size={12} />
                                  {lang === 'fr'
                                    ? `Vérification par ${app.verification_method === 'dns' ? 'DNS TXT' : 'fichier .well-known'}`
                                    : `Verify via ${app.verification_method === 'dns' ? 'DNS TXT' : '.well-known file'}`}
                                </p>
                                {app.verification_method === 'dns' ? (
                                  <div className="flex flex-col gap-1.5 text-xs font-mono">
                                    <p className="text-slate-400">{lang === 'fr' ? 'Ajoutez cet enregistrement DNS :' : 'Add this DNS record:'}</p>
                                    <div className="bg-slate-900 rounded-lg p-3 flex flex-col gap-1">
                                      <span><span className="text-slate-600">Type :</span> <span className="text-cyan-300">TXT</span></span>
                                      <span><span className="text-slate-600">Nom  :</span> <span className="text-cyan-300">_cyberhealth-verify.{app.domain}</span></span>
                                      <span><span className="text-slate-600">Valeur :</span> <span className="text-green-300">cyberhealth-verify={app.verification_token}</span></span>
                                    </div>
                                  </div>
                                ) : (
                                  <div className="flex flex-col gap-1.5 text-xs font-mono">
                                    <p className="text-slate-400">{lang === 'fr' ? 'Créez ce fichier sur votre serveur :' : 'Create this file on your server:'}</p>
                                    <div className="bg-slate-900 rounded-lg p-3 flex flex-col gap-1">
                                      <span><span className="text-slate-600">Chemin :</span> <span className="text-cyan-300">/.well-known/cyberhealth-verify.txt</span></span>
                                      <span><span className="text-slate-600">Contenu :</span> <span className="text-green-300">cyberhealth-verify={app.verification_token}</span></span>
                                    </div>
                                  </div>
                                )}
                                {verifyMsg && (
                                  <p className={`mt-2 text-xs font-medium ${verifyMsg.ok ? 'text-green-400' : 'text-red-400'}`}>
                                    {verifyMsg.ok ? '✓ ' : '✗ '}{verifyMsg.msg}
                                  </p>
                                )}
                              </div>
                            )}

                            {/* ── Verify message (even without expanded info) ── */}
                            {verifyMsg && !showVerifyInfo && (
                              <div className="mx-4 mb-4">
                                <p className={`text-xs font-medium ${verifyMsg.ok ? 'text-green-400' : 'text-amber-400'}`}>
                                  {verifyMsg.ok ? '✓ ' : '⚠ '}{verifyMsg.msg}
                                </p>
                              </div>
                            )}

                            {/* ── Findings ─────────────────────────────────── */}
                            {isExpanded && scanResult && (() => {
                              const sevColors: Record<string, string> = {
                                CRITICAL: 'border-l-red-500 bg-red-500/5',
                                HIGH:     'border-l-orange-500 bg-orange-500/5',
                                MEDIUM:   'border-l-yellow-500 bg-yellow-500/5',
                                LOW:      'border-l-blue-500 bg-blue-500/5',
                                INFO:     'border-l-slate-500 bg-slate-800/30',
                              };
                              const sevText: Record<string, string> = {
                                CRITICAL: 'text-red-400', HIGH: 'text-orange-400',
                                MEDIUM: 'text-yellow-400', LOW: 'text-blue-400', INFO: 'text-slate-400',
                              };
                              // Séparer findings App Scan / Secrets / DAST
                              const appFindings     = scanResult.filter(f => !f.category?.startsWith('DAST') && f.category !== 'Secrets exposés');
                              const dastFindings    = scanResult.filter(f => f.category?.startsWith('DAST'));
                              const secretFindings  = scanResult.filter(f => f.category === 'Secrets exposés');
                              const dast    = scanDetails?.dast;
                              const secrets = scanDetails?.secrets;
                              return (
                                <div className="border-t border-slate-800 px-4 py-4 flex flex-col gap-4">

                                  {/* App Scan findings */}
                                  <div className="flex flex-col gap-2">
                                    <p className="text-slate-500 text-xs font-mono uppercase tracking-wider">
                                      {lang === 'fr' ? 'Scan applicatif passif' : 'Passive app scan'}
                                      {' — '}
                                      {appFindings.length === 0
                                        ? (lang === 'fr' ? 'aucune vulnérabilité' : 'no vulnerability')
                                        : `${appFindings.length} finding${appFindings.length > 1 ? 's' : ''}`
                                      }
                                    </p>
                                    {appFindings.map((f, i) => (
                                      <div key={i} className={`border-l-2 rounded-r-lg p-3 ${sevColors[f.severity] ?? sevColors.INFO}`}>
                                        <div className="flex items-start justify-between gap-2">
                                          <p className="text-white text-sm font-semibold leading-snug">{f.title}</p>
                                          <span className={`text-xs font-bold font-mono shrink-0 ${sevText[f.severity] ?? sevText.INFO}`}>
                                            {f.severity}
                                            {(f.penalty ?? 0) > 0 && <span className="text-slate-500 font-normal ml-1">−{f.penalty}pt</span>}
                                          </span>
                                        </div>
                                        {f.plain_explanation && (
                                          <p className="text-slate-400 text-xs mt-1 leading-relaxed">{f.plain_explanation}</p>
                                        )}
                                        {f.recommendation && (
                                          <p className="text-cyan-400/70 text-xs mt-1.5 font-mono">{f.recommendation}</p>
                                        )}
                                      </div>
                                    ))}
                                  </div>

                                  {/* DAST section */}
                                  <div className="flex flex-col gap-2">
                                    <div className="flex items-center gap-2">
                                      <p className="text-violet-400 text-xs font-mono uppercase tracking-wider">
                                        DAST — {lang === 'fr' ? 'Tests actifs sur formulaires' : 'Active form tests'}
                                      </p>
                                      {dast && (
                                        <span className="text-[10px] font-mono text-slate-600">
                                          {lang === 'fr'
                                            ? `${dast.forms_found} form${dast.forms_found > 1 ? 's' : ''} trouvé${dast.forms_found > 1 ? 's' : ''}, ${dast.forms_tested} testé${dast.forms_tested > 1 ? 's' : ''}`
                                            : `${dast.forms_found} form${dast.forms_found !== 1 ? 's' : ''} found, ${dast.forms_tested} tested`
                                          }
                                        </span>
                                      )}
                                    </div>

                                    {/* Error / no forms */}
                                    {dast?.error && (
                                      <p className="text-amber-400/70 text-xs font-mono">{dast.error}</p>
                                    )}
                                    {dast && !dast.error && dast.forms_found === 0 && (
                                      <p className="text-slate-600 text-xs italic">
                                        {lang === 'fr' ? 'Aucun formulaire HTML découvert.' : 'No HTML form discovered.'}
                                      </p>
                                    )}
                                    {dast && !dast.error && dast.forms_found > 0 && dastFindings.length === 0 && (
                                      <p className="text-green-400/70 text-xs flex items-center gap-1">
                                        <Check size={11} />
                                        {lang === 'fr' ? 'Aucune vulnérabilité détectée (XSS, SQLi, CSRF)' : 'No vulnerability detected (XSS, SQLi, CSRF)'}
                                      </p>
                                    )}

                                    {/* DAST findings avec evidence */}
                                    {dast?.findings?.filter(df => df.severity !== 'INFO').map((df, i) => (
                                      <div key={i} className={`border-l-2 rounded-r-lg p-3 ${sevColors[df.severity] ?? sevColors.INFO}`}>
                                        <div className="flex items-start justify-between gap-2 mb-1">
                                          <p className="text-white text-sm font-semibold leading-snug">{df.title}</p>
                                          <div className="flex items-center gap-1.5 shrink-0">
                                            <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border ${
                                              df.test_type === 'xss'  ? 'text-orange-300 border-orange-500/30 bg-orange-500/10' :
                                              df.test_type === 'sqli' ? 'text-red-300 border-red-500/30 bg-red-500/10' :
                                              'text-yellow-300 border-yellow-500/30 bg-yellow-500/10'
                                            }`}>
                                              {df.test_type.toUpperCase()}
                                            </span>
                                            <span className={`text-xs font-bold font-mono ${sevText[df.severity] ?? sevText.INFO}`}>
                                              {df.severity}
                                              {df.penalty > 0 && <span className="text-slate-500 font-normal ml-1">−{df.penalty}pt</span>}
                                            </span>
                                          </div>
                                        </div>
                                        {/* Champ + URL action */}
                                        {(df.field_name || df.form_action) && (
                                          <div className="flex items-center gap-3 text-[10px] font-mono text-slate-500 mb-1.5">
                                            {df.field_name && (
                                              <span>
                                                <span className="text-slate-600">{lang === 'fr' ? 'Champ :' : 'Field:'} </span>
                                                <span className="text-cyan-400/70">{df.field_name}</span>
                                              </span>
                                            )}
                                            {df.form_action && (
                                              <span className="truncate max-w-[200px]">
                                                <span className="text-slate-600">{lang === 'fr' ? 'Action :' : 'Action:'} </span>
                                                <span className="text-slate-400">{df.form_action}</span>
                                              </span>
                                            )}
                                          </div>
                                        )}
                                        {/* Evidence */}
                                        {df.evidence && (
                                          <div className="bg-slate-900 rounded px-2.5 py-1.5 font-mono text-[10px] text-amber-300/80 break-all mb-1.5">
                                            {df.evidence}
                                          </div>
                                        )}
                                        <p className="text-slate-400 text-xs leading-relaxed">{df.detail}</p>
                                      </div>
                                    ))}
                                  </div>

                                  {/* Secrets section */}
                                  <div className="flex flex-col gap-2">
                                    <div className="flex items-center gap-2">
                                      <p className="text-red-400 text-xs font-mono uppercase tracking-wider">
                                        {lang === 'fr' ? 'Secrets exposés dans le bundle' : 'Secrets exposed in bundle'}
                                      </p>
                                      {secrets && (
                                        <span className="text-[10px] font-mono text-slate-600">
                                          {lang === 'fr'
                                            ? `${secrets.scripts_found} script${secrets.scripts_found > 1 ? 's' : ''} trouvé${secrets.scripts_found > 1 ? 's' : ''}, ${secrets.scripts_scanned} analysé${secrets.scripts_scanned > 1 ? 's' : ''}`
                                            : `${secrets.scripts_found} script${secrets.scripts_found !== 1 ? 's' : ''} found, ${secrets.scripts_scanned} scanned`
                                          }
                                        </span>
                                      )}
                                    </div>

                                    {secrets?.error && (
                                      <p className="text-amber-400/70 text-xs font-mono">{secrets.error}</p>
                                    )}
                                    {secrets && !secrets.error && secrets.scripts_scanned === 0 && secrets.scripts_found === 0 && (
                                      <p className="text-slate-600 text-xs italic">
                                        {lang === 'fr' ? 'Aucun bundle JS externe découvert.' : 'No external JS bundle discovered.'}
                                      </p>
                                    )}
                                    {secrets && !secrets.error && secrets.scripts_scanned > 0 && secretFindings.length === 0 && (
                                      <p className="text-green-400/70 text-xs flex items-center gap-1">
                                        <Check size={11} />
                                        {lang === 'fr' ? 'Aucun secret détecté dans les bundles analysés' : 'No secret detected in scanned bundles'}
                                      </p>
                                    )}

                                    {/* Secret findings */}
                                    {secrets?.findings?.map((sf, i) => (
                                      <div key={i} className={`border-l-2 rounded-r-lg p-3 ${sevColors[sf.severity] ?? sevColors.INFO}`}>
                                        <div className="flex items-start justify-between gap-2 mb-1">
                                          <p className="text-white text-sm font-semibold leading-snug">{sf.pattern_name}</p>
                                          <span className={`text-xs font-bold font-mono shrink-0 ${sevText[sf.severity] ?? sevText.INFO}`}>
                                            {sf.severity}
                                            {sf.penalty > 0 && <span className="text-slate-500 font-normal ml-1">−{sf.penalty}pt</span>}
                                          </span>
                                        </div>

                                        {/* Valeur masquée + source */}
                                        <div className="flex items-center gap-3 text-[10px] font-mono text-slate-500 mb-1.5 flex-wrap">
                                          <span>
                                            <span className="text-slate-600">{lang === 'fr' ? 'Valeur :' : 'Value:'} </span>
                                            <span className="text-red-300/80">{sf.matched_value}</span>
                                          </span>
                                          {sf.source_url && (
                                            <span className="truncate max-w-[240px]">
                                              <span className="text-slate-600">{lang === 'fr' ? 'Source :' : 'Source:'} </span>
                                              <span className="text-slate-400">{sf.source_url.replace(/^https?:\/\/[^/]+/, '')}</span>
                                            </span>
                                          )}
                                        </div>

                                        {/* Contexte (extrait du bundle) */}
                                        {sf.context && (
                                          <div className="bg-slate-900 rounded px-2.5 py-1.5 font-mono text-[10px] text-slate-400 break-all mb-1.5">
                                            {sf.context}
                                          </div>
                                        )}

                                        <p className="text-slate-400 text-xs leading-relaxed mb-1.5">{sf.description}</p>
                                        <p className="text-cyan-400/70 text-[10px] font-mono leading-relaxed">{sf.recommendation}</p>
                                      </div>
                                    ))}
                                  </div>

                                </div>
                              );
                            })()}
                          </div>
                        );
                      })}
                    </div>
                  )}

                </div>
              )}

              {/* ══════════════════════════════════════════════════════════════
                  TAB 2 — MONITORING
              ══════════════════════════════════════════════════════════════ */}
              {tab === 'monitoring' && (
                <div className="flex flex-col gap-5">

                  {/* Add domain */}
                  <div className="sku-card rounded-xl p-5">
                    <div className="flex items-center justify-between mb-4">
                      <div>
                        <p className="text-white font-bold text-sm flex items-center gap-2">
                          <Plus size={14} className="text-cyan-400" />
                          {lang === 'fr' ? 'Ajouter un domaine' : 'Add a domain'}
                        </p>
                        <p className="text-slate-500 text-xs mt-0.5">
                          {domains.length}/{planLimit !== null ? planLimit : '∞'} {lang === 'fr' ? 'domaine' : 'domain'}{domains.length !== 1 ? (lang === 'fr' ? 's' : 's') : ''} {lang === 'fr' ? 'utilisé' : 'used'}{domains.length !== 1 ? (lang === 'fr' ? 's' : '') : ''}
                        </p>
                      </div>
                      {planLimit !== null && domains.length >= planLimit && (
                        <span className="text-xs text-orange-400 font-mono bg-orange-500/10 border border-orange-500/20 px-2 py-1 rounded-lg">
                          {lang === 'fr' ? 'Limite atteinte' : 'Limit reached'}
                        </span>
                      )}
                    </div>
                    <div className="flex flex-col gap-4">
                      {/* Row 1: Domain input + Add button */}
                      <div className="flex gap-2 flex-wrap">
                        <input
                          type="text"
                          placeholder="exemple.com"
                          value={newDomain}
                          onChange={e => { setNewDomain(e.target.value); setAddError(''); }}
                          onKeyDown={e => e.key === 'Enter' && addDomain()}
                          disabled={planLimit !== null && domains.length >= planLimit}
                          className="flex-1 min-w-[220px] bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-cyan-500 transition placeholder:text-slate-600 disabled:opacity-40"
                        />
                        <button
                          onClick={addDomain}
                          disabled={addLoading || !newDomain.trim() || (planLimit !== null && domains.length >= planLimit)}
                          className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 hover:bg-cyan-500/30 transition text-sm font-semibold disabled:opacity-40"
                        >
                          {addLoading
                            ? <div className="w-3.5 h-3.5 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
                            : <Plus size={14} />
                          }
                          {lang === 'fr' ? 'Ajouter' : 'Add'}
                        </button>
                      </div>
                      {/* Row 2: Checks + Planification config */}
                      <div className="border border-slate-800 rounded-xl p-4 flex flex-col gap-4 bg-slate-800/20">
                        <p className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">
                          {lang === 'fr' ? 'Configuration du monitoring' : 'Monitoring configuration'}
                        </p>
                        {/* Checks */}
                        <div className="flex flex-col gap-2">
                          <p className="text-xs text-slate-400 font-medium">{lang === 'fr' ? 'Checks à effectuer' : 'Checks to run'}</p>
                          <div className="flex gap-1.5 flex-wrap">
                            {CHECK_LABELS.map(({ key, label }) => {
                              const enabled = newDomainChecks[key] !== false;
                              return (
                                <button
                                  key={key}
                                  type="button"
                                  onClick={() => setNewDomainChecks(prev => ({ ...prev, [key]: !enabled }))}
                                  className={`
                                    text-[10px] font-mono px-2.5 py-1 rounded-md border transition-all
                                    ${enabled
                                      ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30 hover:bg-cyan-500/20'
                                      : 'bg-slate-900 text-slate-600 border-slate-700 hover:border-slate-600'}
                                  `}
                                >
                                  {label}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                        {/* Planification */}
                        <div className="flex items-end gap-6 flex-wrap">
                          <div className="flex flex-col gap-1.5">
                            <p className="text-xs text-slate-400 font-medium">{lang === 'fr' ? 'Fréquence de scan' : 'Scan frequency'}</p>
                            <select
                              value={newDomainFrequency}
                              onChange={e => setNewDomainFrequency(e.target.value as 'weekly' | 'biweekly' | 'monthly')}
                              className="bg-slate-800 border border-slate-700 text-slate-300 text-xs font-mono rounded-md px-2.5 py-1.5 focus:outline-none focus:border-cyan-500/50 cursor-pointer hover:border-slate-600 transition"
                            >
                              <option value="weekly">{lang === 'fr' ? 'Hebdomadaire' : 'Weekly'}</option>
                              <option value="biweekly">{lang === 'fr' ? 'Bimensuel' : 'Biweekly'}</option>
                              <option value="monthly">{lang === 'fr' ? 'Mensuel' : 'Monthly'}</option>
                            </select>
                          </div>
                          <label className="flex items-center gap-2 cursor-pointer pb-1">
                            <input
                              type="checkbox"
                              checked={newDomainEmailReport}
                              onChange={e => setNewDomainEmailReport(e.target.checked)}
                              className="w-3.5 h-3.5 accent-cyan-400 cursor-pointer"
                            />
                            <span className="text-xs font-mono text-slate-400 hover:text-slate-300 transition">
                              {lang === 'fr' ? 'Rapport PDF par email' : 'PDF report by email'}
                            </span>
                          </label>
                        </div>
                      </div>
                    </div>
                    {addError && (
                      <p className="mt-2 text-red-400 text-xs font-mono bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-1.5">
                        {addError}
                      </p>
                    )}
                  </div>

                  {/* Upsell banner — Starter avec 1 domaine (limite atteinte) */}
                  {user?.plan === 'starter' && domains.length >= 1 && (
                    <motion.div
                      initial={{ opacity: 0, y: -6 }}
                      animate={{ opacity: 1, y: 0 }}
                      className={`rounded-xl border p-4 flex flex-col sm:flex-row items-start sm:items-center gap-3 ${
                        domains.length >= 1
                          ? 'border-orange-500/30 bg-orange-500/5'
                          : 'border-purple-500/30 bg-purple-500/5'
                      }`}
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-orange-300 font-bold text-sm">
                          {lang === 'fr' ? '⚠ Limite Starter atteinte' : '⚠ Starter limit reached'}
                        </p>
                        <p className="text-slate-400 text-xs mt-0.5">
                          {lang === 'fr'
                            ? 'Passez Pro pour surveiller des domaines en illimité, accéder aux webhooks et débloquer toutes les fonctionnalités.'
                            : 'Upgrade to Pro to monitor unlimited domains, access webhooks and unlock all features.'}
                        </p>
                      </div>
                      <button
                        onClick={() => setPricingModalOpen(true)}
                        className="shrink-0 flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold transition bg-orange-500/20 text-orange-300 border border-orange-500/30 hover:bg-orange-500/30"
                      >
                        {lang === 'fr' ? 'Passer Pro →' : 'Upgrade to Pro →'}
                      </button>
                    </motion.div>
                  )}

                  {/* Domains table */}
                  {domains.length === 0 ? (
                    <div className="py-16 text-center text-slate-600 text-sm">
                      {lang === 'fr' ? 'Ajoutez votre premier domaine ci-dessus pour commencer.' : 'Add your first domain above to get started.'}
                    </div>
                  ) : (
                    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
                      <div className="px-5 py-3 border-b border-slate-800 flex items-center justify-between">
                        <p className="text-white font-bold text-sm">{domains.length} {lang === 'fr' ? 'domaine' : 'domain'}{domains.length !== 1 ? (lang === 'fr' ? 's' : 's') : ''} {lang === 'fr' ? 'surveillé' : 'monitored'}{domains.length !== 1 ? (lang === 'fr' ? 's' : '') : ''}</p>
                        <p className="text-slate-600 text-xs font-mono">{lang === 'fr' ? 'Fréquence configurable par domaine' : 'Configurable frequency per domain'}</p>
                      </div>
                      <div className="overflow-x-auto">
                        <table className="w-full">
                          <thead>
                            <tr className="border-b border-slate-800">
                              <th className="px-5 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Domaine' : 'Domain'}</th>
                              <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Score' : 'Score'}</th>
                              <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Tendance' : 'Trend'}</th>
                              <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Risque' : 'Risk'}</th>
                              <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Dernier scan' : 'Last scan'}</th>
                              <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Seuil alerte' : 'Alert threshold'}</th>
                              <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">Checks</th>
                              <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Planification' : 'Schedule'}</th>
                              <th className="px-4 py-3 text-xs font-mono text-slate-500 uppercase tracking-wider" />
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/50">
                            {domains.map(d => (
                              <tr key={d.domain} className="hover:bg-slate-800/30 transition-colors group">

                                {/* Domain */}
                                <td className="px-5 py-4">
                                  <div className="flex items-center gap-2">
                                    <Globe size={12} className="text-slate-500 shrink-0" />
                                    <span className="text-white font-mono font-medium text-sm">{d.domain}</span>
                                  </div>
                                </td>

                                {/* Score */}
                                <td className="px-4 py-4">
                                  <span className={`text-xl font-black font-mono ${scoreColor(d.last_score)}`}>
                                    {d.last_score ?? '—'}
                                  </span>
                                </td>

                                {/* Tendance sparkline */}
                                <td className="px-4 py-4">
                                  {(() => {
                                    const scores = [...(historyByDomain[d.domain] ?? [])]
                                      .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
                                      .map(s => s.security_score);
                                    return <Sparkline scores={scores} width={80} height={28} />;
                                  })()}
                                </td>

                                {/* Risk */}
                                <td className="px-4 py-4">
                                  <RiskBadge level={d.last_risk_level} />
                                </td>

                                {/* Last scan */}
                                <td className="px-4 py-4 text-slate-500 text-xs font-mono">
                                  {d.last_scan_at
                                    ? new Date(d.last_scan_at).toLocaleDateString(lang === 'fr' ? 'fr-FR' : 'en-GB', { day: '2-digit', month: '2-digit', year: 'numeric' })
                                    : '—'}
                                </td>

                                {/* Threshold — éditable inline */}
                                <td className="px-4 py-4">
                                  {editingThreshold === d.domain ? (
                                    <div className="flex items-center gap-1.5">
                                      <input
                                        type="number"
                                        min={1} max={50}
                                        value={thresholdValue}
                                        onChange={e => setThresholdValue(Number(e.target.value))}
                                        className="w-14 bg-slate-800 border border-cyan-500/40 rounded px-2 py-1 text-xs text-white font-mono focus:outline-none text-center"
                                        autoFocus
                                      />
                                      <span className="text-slate-600 text-xs">pts</span>
                                      <button
                                        onClick={() => saveThreshold(d.domain)}
                                        className="p-1 rounded text-green-400 hover:bg-green-500/10 transition"
                                        title={lang === 'fr' ? 'Sauvegarder' : 'Save'}
                                      >
                                        <Check size={13} />
                                      </button>
                                      <button
                                        onClick={() => setEditingThreshold(null)}
                                        className="p-1 rounded text-slate-600 hover:text-slate-400 transition"
                                        title={lang === 'fr' ? 'Annuler' : 'Cancel'}
                                      >
                                        <X size={13} />
                                      </button>
                                    </div>
                                  ) : (
                                    <button
                                      onClick={() => { setEditingThreshold(d.domain); setThresholdValue(d.alert_threshold); }}
                                      className="flex items-center gap-1.5 text-xs font-mono text-slate-400 hover:text-white transition group-hover:opacity-100"
                                      title={lang === 'fr' ? 'Modifier le seuil' : 'Edit threshold'}
                                    >
                                      <Bell size={11} className="text-slate-600" />
                                      −{d.alert_threshold} pts
                                    </button>
                                  )}
                                </td>

                                {/* Checks — toggles interactifs */}
                                <td className="px-4 py-4">
                                  <div className="flex gap-1 flex-wrap">
                                    {CHECK_LABELS.map(({ key, label }) => {
                                      const cfg = pendingChecks[d.domain] ?? d.checks_config;
                                      const enabled = cfg[key] !== false;
                                      const isLoading = checksLoading === d.domain + ':' + key;
                                      return (
                                        <button
                                          key={key}
                                          onClick={() => toggleCheck(d, key)}
                                          disabled={isLoading}
                                          title={enabled ? (lang === 'fr' ? `Désactiver le check ${label}` : `Disable check ${label}`) : (lang === 'fr' ? `Activer le check ${label}` : `Enable check ${label}`)}
                                          className={`
                                            text-[9px] font-mono px-1.5 py-0.5 rounded border transition-all
                                            ${enabled
                                              ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30 hover:bg-cyan-500/20'
                                              : 'bg-slate-900 text-slate-600 border-slate-800 hover:border-slate-700'}
                                            disabled:opacity-40
                                          `}
                                        >
                                          {label}
                                        </button>
                                      );
                                    })}
                                  </div>
                                  <p className="text-xs text-slate-500 mt-1.5">{lang === 'fr' ? 'Cliquer pour activer / désactiver' : 'Click to enable / disable'}</p>
                                </td>

                                {/* Planification + Alertes — Feature 3 & 4 */}
                                <td className="px-4 py-4">
                                  <div className="flex flex-col gap-2">
                                    {/* Fréquence de scan */}
                                    <select
                                      value={d.scan_frequency}
                                      onChange={async e => {
                                        const freq = e.target.value as 'weekly' | 'biweekly' | 'monthly';
                                        setDomains(prev => prev.map(x => x.domain === d.domain ? { ...x, scan_frequency: freq } : x));
                                        try { await apiClient.patch(`/monitoring/domains/${d.domain}`, { scan_frequency: freq }); }
                                        catch { /* silently ignore */ }
                                      }}
                                      className="bg-slate-800 border border-slate-700 text-slate-300 text-[10px] font-mono rounded px-1.5 py-1 focus:outline-none focus:border-cyan-500/50 cursor-pointer hover:border-slate-600 transition"
                                      title={lang === 'fr' ? 'Fréquence de scan' : 'Scan frequency'}
                                    >
                                      <option value="weekly">{lang === 'fr' ? 'Hebdo' : 'Weekly'}</option>
                                      <option value="biweekly">{lang === 'fr' ? 'Bimensuel' : 'Biweekly'}</option>
                                      <option value="monthly">{lang === 'fr' ? 'Mensuel' : 'Monthly'}</option>
                                    </select>

                                    {/* Seuil SSL — Feature 4 */}
                                    <select
                                      value={d.ssl_alert_days ?? 30}
                                      onChange={async e => {
                                        const days = Number(e.target.value);
                                        setDomains(prev => prev.map(x => x.domain === d.domain ? { ...x, ssl_alert_days: days } : x));
                                        try { await apiClient.patch(`/monitoring/domains/${d.domain}`, { ssl_alert_days: days }); }
                                        catch { /* silently ignore */ }
                                      }}
                                      className="bg-slate-800 border border-slate-700 text-slate-300 text-[10px] font-mono rounded px-1.5 py-1 focus:outline-none focus:border-cyan-500/50 cursor-pointer hover:border-slate-600 transition"
                                      title={lang === 'fr' ? 'Seuil d\'alerte SSL' : 'SSL alert threshold'}
                                    >
                                      <option value={7}>{lang === 'fr' ? 'SSL &lt; 7j' : 'SSL &lt; 7d'}</option>
                                      <option value={14}>{lang === 'fr' ? 'SSL &lt; 14j' : 'SSL &lt; 14d'}</option>
                                      <option value={30}>{lang === 'fr' ? 'SSL &lt; 30j' : 'SSL &lt; 30d'}</option>
                                      <option value={60}>{lang === 'fr' ? 'SSL &lt; 60j' : 'SSL &lt; 60d'}</option>
                                    </select>

                                    {/* Email rapport PDF */}
                                    <label className="flex items-center gap-1.5 cursor-pointer group/pdf">
                                      <input
                                        type="checkbox"
                                        checked={d.email_report}
                                        onChange={async e => {
                                          const val = e.target.checked;
                                          setDomains(prev => prev.map(x => x.domain === d.domain ? { ...x, email_report: val } : x));
                                          try { await apiClient.patch(`/monitoring/domains/${d.domain}`, { email_report: val }); }
                                          catch { /* silently ignore */ }
                                        }}
                                        className="w-3 h-3 accent-cyan-400 cursor-pointer"
                                      />
                                      <span className="text-[10px] font-mono text-slate-500 group-hover/pdf:text-slate-400 transition">
                                        {lang === 'fr' ? 'PDF par email' : 'PDF by email'}
                                      </span>
                                    </label>

                                    {/* Types d'alertes — Feature 4 */}
                                    <details className="group/alerts">
                                      <summary className="text-[10px] font-mono text-slate-600 hover:text-slate-400 cursor-pointer list-none flex items-center gap-1 transition">
                                        <span className="group-open/alerts:rotate-90 transition-transform inline-block">▶</span>
                                        {lang === 'fr' ? 'Types d\'alertes' : 'Alert types'}
                                      </summary>
                                      <div className="mt-1.5 flex flex-col gap-1 pl-2">
                                        {([
                                          { key: 'score_drop',        label: lang === 'fr' ? 'Chute de score'          : 'Score drop'        },
                                          { key: 'critical_findings', label: lang === 'fr' ? 'Vulnérabilités critiques' : 'Critical findings'  },
                                          { key: 'ssl_expiry',        label: lang === 'fr' ? 'Expiration SSL'          : 'SSL expiry'        },
                                          { key: 'port_changes',      label: lang === 'fr' ? 'Nouveaux ports'         : 'Port changes'      },
                                          { key: 'tech_changes',      label: lang === 'fr' ? 'Changements de version' : 'Version changes'   },
                                        ] as const).map(({ key, label }) => {
                                          const cfg = d.alert_config_parsed ?? {};
                                          const enabled = (cfg as Record<string, boolean>)[key] !== false;
                                          return (
                                            <label key={key} className="flex items-center gap-1.5 cursor-pointer group/al">
                                              <input
                                                type="checkbox"
                                                checked={enabled}
                                                onChange={async e => {
                                                  const val = e.target.checked;
                                                  const newCfg = { ...cfg, [key]: val };
                                                  setDomains(prev => prev.map(x =>
                                                    x.domain === d.domain
                                                      ? { ...x, alert_config_parsed: { ...x.alert_config_parsed, [key]: val } }
                                                      : x
                                                  ));
                                                  try { await apiClient.patch(`/monitoring/domains/${d.domain}`, { alert_config: newCfg }); }
                                                  catch { /* silently ignore */ }
                                                }}
                                                className="w-3 h-3 accent-cyan-400 cursor-pointer"
                                              />
                                              <span className="text-[10px] font-mono text-slate-500 group-hover/al:text-slate-400 transition">
                                                {label}
                                              </span>
                                            </label>
                                          );
                                        })}
                                      </div>
                                    </details>
                                  </div>
                                </td>

                                {/* Actions — Scan Now + Delete */}
                                <td className="px-4 py-4 text-right">
                                  <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                    {/* Scan maintenant */}
                                    <button
                                      onClick={() => scanDomainNow(d.domain)}
                                      disabled={!!scanningDomain}
                                      title={lang === 'fr' ? 'Lancer un scan immédiat' : 'Run an immediate scan'}
                                      className={`p-1.5 rounded-lg transition ${
                                        scanDoneMap[d.domain]
                                          ? 'text-green-400 bg-green-500/10'
                                          : 'text-slate-500 hover:text-cyan-400 hover:bg-cyan-500/10'
                                      } disabled:opacity-40 disabled:cursor-not-allowed`}
                                    >
                                      {scanningDomain === d.domain
                                        ? <RefreshCw size={13} className="animate-spin" />
                                        : scanDoneMap[d.domain]
                                          ? <Check size={13} />
                                          : <RefreshCw size={13} />}
                                    </button>
                                    {/* Supprimer */}
                                    <button
                                      onClick={() => removeDomain(d.domain)}
                                      className="p-1.5 rounded-lg text-slate-700 hover:text-red-400 hover:bg-red-500/10 transition"
                                      title={lang === 'fr' ? 'Retirer du monitoring' : 'Remove from monitoring'}
                                    >
                                      <Trash2 size={13} />
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  <p className="text-center text-[11px] text-slate-700 font-mono">
                    {lang === 'fr' ? 'Alerte email automatique si le score baisse du seuil configuré · Fréquence configurable par domaine' : 'Automatic email alert if score drops below configured threshold · Configurable frequency per domain'}
                  </p>
                </div>
              )}

              {/* ══════════════════════════════════════════════════════════════
                  TAB 3 — HISTORIQUE
              ══════════════════════════════════════════════════════════════ */}
              {tab === 'history' && (
                <div className="flex flex-col gap-5">

                  {/* Domain sparkline cards */}
                  {Object.keys(historyByDomain).length > 0 && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                      {Object.entries(historyByDomain).map(([domain, scans]) => {
                        const sorted = [...scans].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
                        const scores = sorted.map(s => s.security_score);
                        const latest = scans[0];
                        const isActive = historyDomain === domain;

                        return (
                          <button
                            key={domain}
                            onClick={() => setHistoryDomain(isActive ? 'all' : domain)}
                            className={`
                              rounded-xl border p-4 text-left transition-all
                              ${isActive
                                ? 'border-cyan-500/40 bg-cyan-500/5 ring-1 ring-cyan-500/20'
                                : 'border-slate-800 bg-slate-900 hover:border-slate-700'}
                            `}
                          >
                            <div className="flex items-center justify-between mb-3">
                              <span className="text-white font-mono text-sm font-bold truncate max-w-[130px]">{domain}</span>
                              <span className={`text-xl font-black font-mono ${scoreColor(latest?.security_score ?? null)}`}>
                                {latest?.security_score ?? '—'}
                              </span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-slate-600 text-xs font-mono">{scans.length} scan{scans.length !== 1 ? 's' : ''}</span>
                              <Sparkline scores={scores} width={90} height={28} />
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  )}

                  {/* Full chart for selected domain */}
                  {historyDomain !== 'all' && historyByDomain[historyDomain] && (
                    <div className="flex flex-col gap-2">
                      <p className="text-sm font-bold text-white">
                        {lang === 'fr' ? 'Évolution du score' : 'Score evolution'} — <span className="text-cyan-400 font-mono">{historyDomain}</span>
                      </p>
                      <ScoreLineChart scans={historyByDomain[historyDomain]} lang={lang} />
                    </div>
                  )}

                  {/* All domains filter pill */}
                  {historyDomain !== 'all' && (
                    <button
                      onClick={() => setHistoryDomain('all')}
                      className="self-start flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition font-mono border border-slate-800 rounded-lg px-3 py-1.5 hover:border-slate-700"
                    >
                      <X size={11} />
                      {lang === 'fr' ? 'Voir tous les domaines' : 'View all domains'}
                    </button>
                  )}

                  {/* Scan list table */}
                  {filteredHistory.length === 0 ? (
                    <div className="py-16 text-center text-slate-600 text-sm">
                      {history.length === 0 ? (lang === 'fr' ? 'Aucun scan dans votre historique.' : 'No scan in your history.') : (lang === 'fr' ? 'Aucun scan pour ce domaine.' : 'No scan for this domain.')}
                    </div>
                  ) : (
                    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
                      <div className="px-5 py-3 border-b border-slate-800 flex items-center justify-between">
                        <p className="text-white font-bold text-sm">
                          {filteredHistory.length} scan{filteredHistory.length !== 1 ? 's' : ''}
                          {historyDomain !== 'all' && <span className="text-cyan-400 font-mono ml-2">{historyDomain}</span>}
                        </p>
                      </div>
                      <div className="overflow-x-auto">
                        <table className="w-full">
                          <thead>
                            <tr className="border-b border-slate-800">
                              <th className="px-5 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Domaine' : 'Domain'}</th>
                              <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">Score</th>
                              <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Risque' : 'Risk'}</th>
                              <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">Findings</th>
                              <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Date' : 'Date'}</th>
                              <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Durée' : 'Duration'}</th>
                              {isPremium ? (
                                <>
                                  <th className="px-4 py-3 text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Voir' : 'View'}</th>
                                  <th className="px-4 py-3 text-xs font-mono text-slate-500 uppercase tracking-wider">PDF</th>
                                  <th className="px-4 py-3 text-xs font-mono text-slate-500 uppercase tracking-wider">Export</th>
                                  <th className="px-4 py-3 text-xs font-mono text-slate-500 uppercase tracking-wider">{lang === 'fr' ? 'Lien' : 'Share'}</th>
                                </>
                              ) : null}
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/40">
                            {filteredHistory.map(scan => (
                              <tr key={scan.scan_uuid} className="hover:bg-slate-800/25 transition-colors">
                                <td className="px-5 py-3.5 font-mono text-slate-300 text-xs">{scan.domain}</td>
                                <td className="px-4 py-3.5">
                                  <span className={`text-lg font-black font-mono ${scoreColor(scan.security_score)}`}>
                                    {scan.security_score}
                                  </span>
                                </td>
                                <td className="px-4 py-3.5"><RiskBadge level={scan.risk_level} /></td>
                                <td className="px-4 py-3.5 text-slate-500 font-mono text-xs">{scan.findings_count}</td>
                                <td className="px-4 py-3.5 text-slate-500 text-xs font-mono">
                                  {new Date(scan.created_at).toLocaleDateString(lang === 'fr' ? 'fr-FR' : 'en-GB', {
                                    day: '2-digit', month: '2-digit', year: 'numeric',
                                    hour: '2-digit', minute: '2-digit',
                                  })}
                                </td>
                                <td className="px-4 py-3.5 text-slate-600 text-xs font-mono">{scan.scan_duration}s</td>
                                {isPremium && (
                                  <>
                                    <td className="px-4 py-3.5">
                                      <button
                                        onClick={() => openScanModal(scan.scan_uuid)}
                                        disabled={scanModalLoading === scan.scan_uuid}
                                        title={lang === 'fr' ? 'Voir les résultats' : 'View results'}
                                        className="flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-200 transition disabled:opacity-40"
                                      >
                                        {scanModalLoading === scan.scan_uuid
                                          ? <div className="w-3 h-3 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
                                          : <Shield size={13} />
                                        }
                                        {lang === 'fr' ? 'Voir' : 'View'}
                                      </button>
                                    </td>
                                    <td className="px-4 py-3.5">
                                      <button
                                        onClick={() => generatePdf(scan.scan_uuid, scan.domain)}
                                        disabled={pdfLoading === scan.scan_uuid}
                                        className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200 transition disabled:opacity-40"
                                      >
                                        {pdfLoading === scan.scan_uuid
                                          ? <div className="w-3 h-3 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
                                          : <FileDown size={13} />
                                        }
                                        PDF
                                      </button>
                                    </td>
                                    <td className="px-4 py-3.5">
                                      <div className="flex items-center gap-2">
                                        <button
                                          onClick={() => exportScan(scan.scan_uuid, scan.domain, 'json')}
                                          disabled={exportLoading === `${scan.scan_uuid}-json`}
                                          title={lang === 'fr' ? 'Télécharger JSON' : 'Download JSON'}
                                          className="text-xs font-mono text-slate-400 hover:text-cyan-400 transition disabled:opacity-40"
                                        >
                                          {exportLoading === `${scan.scan_uuid}-json`
                                            ? <div className="w-3 h-3 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
                                            : 'JSON'}
                                        </button>
                                        <span className="text-slate-700">|</span>
                                        <button
                                          onClick={() => exportScan(scan.scan_uuid, scan.domain, 'csv')}
                                          disabled={exportLoading === `${scan.scan_uuid}-csv`}
                                          title={lang === 'fr' ? 'Télécharger CSV' : 'Download CSV'}
                                          className="text-xs font-mono text-slate-400 hover:text-emerald-400 transition disabled:opacity-40"
                                        >
                                          {exportLoading === `${scan.scan_uuid}-csv`
                                            ? <div className="w-3 h-3 border-2 border-emerald-400/30 border-t-emerald-400 rounded-full animate-spin" />
                                            : 'CSV'}
                                        </button>
                                      </div>
                                    </td>
                                    <td className="px-4 py-3.5">
                                      <button
                                        onClick={() => toggleShare(scan.scan_uuid)}
                                        disabled={shareLoading === scan.scan_uuid}
                                        title={
                                          shareCopied === scan.scan_uuid
                                            ? (lang === 'fr' ? 'Lien copié !' : 'Link copied!')
                                            : scan.public_share
                                              ? (lang === 'fr' ? 'Désactiver le lien public' : 'Disable public link')
                                              : (lang === 'fr' ? 'Activer le lien public' : 'Enable public link')
                                        }
                                        className={`flex items-center gap-1 text-xs transition disabled:opacity-40 ${
                                          shareCopied === scan.scan_uuid
                                            ? 'text-green-400'
                                            : scan.public_share
                                              ? 'text-violet-400 hover:text-violet-300'
                                              : 'text-slate-500 hover:text-slate-300'
                                        }`}
                                      >
                                        {shareLoading === scan.scan_uuid
                                          ? <div className="w-3 h-3 border-2 border-slate-400/30 border-t-slate-400 rounded-full animate-spin" />
                                          : shareCopied === scan.scan_uuid
                                            ? <Check size={13} />
                                            : <ExternalLink size={13} />
                                        }
                                        {shareCopied === scan.scan_uuid
                                          ? (lang === 'fr' ? 'Copié' : 'Copied')
                                          : scan.public_share
                                            ? (lang === 'fr' ? 'Actif' : 'Active')
                                            : (lang === 'fr' ? 'Partager' : 'Share')}
                                      </button>
                                    </td>
                                  </>
                                )}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* ══════════════════════════════════════════════════════════════
                  TAB 5 — DÉVELOPPEUR (Pro/Team uniquement)
              ══════════════════════════════════════════════════════════════ */}
              {tab === 'developer' && (
                <div className="flex flex-col gap-6">

                  {/* ── API Key ── */}
                  <div className="sku-card rounded-xl p-5">
                    <div className="flex items-center gap-3 mb-1">
                      <SkuIcon color="#a78bfa" size={32}><Key size={13} className="text-violet-300" /></SkuIcon>
                      <h3 className="text-white font-semibold text-sm">{lang === 'fr' ? 'Clé API' : 'API Key'}</h3>
                    </div>
                    <p className="text-slate-500 text-xs mb-4">
                      {lang === 'fr'
                        ? 'Utilisez cette clé comme Bearer token pour accéder à l\'API sans cookie de session.'
                        : 'Use this key as a Bearer token to access the API without a session cookie.'}
                    </p>

                    {apiKeyMsg && (
                      <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs mb-3 ${apiKeyMsg.type === 'ok' ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                        {apiKeyMsg.type === 'ok' ? <Check size={12} /> : <AlertTriangle size={12} />}
                        {apiKeyMsg.text}
                      </div>
                    )}

                    <div className="flex items-center gap-2 mb-4">
                      <div className="flex-1 bg-slate-800/60 border border-slate-700 rounded-lg px-3 py-2 font-mono text-xs text-slate-300 overflow-hidden">
                        {user?.api_key
                          ? (apiKeyVisible ? user.api_key : user.api_key.slice(0, 8) + '••••••••••••••••••••••••••••••••••••••••••••••••••••••••')
                          : <span className="text-slate-600">{lang === 'fr' ? 'Aucune clé générée' : 'No key generated'}</span>
                        }
                      </div>
                      {user?.api_key && (
                        <>
                          <button
                            onClick={() => setApiKeyVisible(v => !v)}
                            className="p-2 rounded-lg border border-slate-700 hover:border-slate-600 text-slate-500 hover:text-slate-300 transition"
                            title={apiKeyVisible ? (lang === 'fr' ? 'Masquer' : 'Hide') : (lang === 'fr' ? 'Afficher' : 'Show')}
                          >
                            <Shield size={13} />
                          </button>
                          <button
                            onClick={copyApiKey}
                            className="p-2 rounded-lg border border-slate-700 hover:border-slate-600 text-slate-500 hover:text-cyan-400 transition"
                            title={lang === 'fr' ? 'Copier' : 'Copy'}
                          >
                            {apiKeyCopied ? <Check size={13} className="text-green-400" /> : <Copy size={13} />}
                          </button>
                        </>
                      )}
                    </div>

                    <button
                      onClick={regenerateApiKey}
                      disabled={apiKeyLoading}
                      className="flex items-center gap-2 bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/30 text-cyan-400 px-4 py-2 rounded-lg text-xs font-semibold transition disabled:opacity-40"
                    >
                      {apiKeyLoading ? <RefreshCw size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                      {lang === 'fr' ? 'Régénérer la clé' : 'Regenerate key'}
                    </button>

                    <div className="mt-4 bg-slate-800/40 border border-slate-700/50 rounded-lg p-3">
                      <p className="text-slate-500 text-xs font-mono leading-relaxed">
                        <span className="text-cyan-500">Authorization:</span> Bearer {'<your-api-key>'}
                      </p>
                    </div>
                  </div>

                  {/* ── Badge SVG ── */}
                  <div className="sku-card rounded-xl p-5">
                    <div className="flex items-center gap-3 mb-1">
                      <SkuIcon color="#22d3ee" size={32}><Shield size={13} className="text-cyan-300" /></SkuIcon>
                      <h3 className="text-white font-semibold text-sm">{lang === 'fr' ? 'Badge de sécurité' : 'Security badge'}</h3>
                    </div>
                    <p className="text-slate-500 text-xs mb-4">
                      {lang === 'fr'
                        ? 'Affichez votre score de sécurité en temps réel sur votre site, README GitHub, ou emails.'
                        : 'Display your real-time security score on your website, GitHub README, or emails.'}
                    </p>
                    {domains.length === 0 ? (
                      <p className="text-slate-600 text-xs">{lang === 'fr' ? 'Ajoutez un domaine en monitoring pour obtenir un badge.' : 'Add a monitored domain to get a badge.'}</p>
                    ) : (
                      <div className="flex flex-col gap-3">
                        {domains.slice(0, 3).map(d => {
                          const badgeUrl = `/api/public/badge/${d.domain}`;
                          const embedMd  = `![Security Score](https://scan.wezea.net/api/public/badge/${d.domain})`;
                          const embedHtml = `<img src="https://scan.wezea.net/api/public/badge/${d.domain}" alt="Security Score" />`;
                          return (
                            <div key={d.domain} className="bg-slate-800/40 border border-slate-700/50 rounded-lg p-3">
                              <div className="flex items-center justify-between mb-2">
                                <span className="text-slate-300 font-mono text-xs">{d.domain}</span>
                                <a href={badgeUrl} target="_blank" rel="noreferrer"
                                  className="flex items-center gap-1 text-xs text-slate-500 hover:text-cyan-400 transition">
                                  <ExternalLink size={11} />
                                  {lang === 'fr' ? 'Aperçu' : 'Preview'}
                                </a>
                              </div>
                              <div className="flex flex-col gap-1.5">
                                <div>
                                  <p className="text-slate-600 text-[10px] mb-0.5 uppercase font-mono tracking-wider">Markdown</p>
                                  <div className="flex items-center gap-2">
                                    <code className="flex-1 text-[10px] text-slate-400 font-mono bg-slate-900/60 rounded px-2 py-1 overflow-hidden text-ellipsis whitespace-nowrap">{embedMd}</code>
                                    <button onClick={() => navigator.clipboard.writeText(embedMd)}
                                      className="p-1.5 rounded border border-slate-700 hover:border-slate-600 text-slate-500 hover:text-cyan-400 transition shrink-0">
                                      <Copy size={11} />
                                    </button>
                                  </div>
                                </div>
                                <div>
                                  <p className="text-slate-600 text-[10px] mb-0.5 uppercase font-mono tracking-wider">HTML</p>
                                  <div className="flex items-center gap-2">
                                    <code className="flex-1 text-[10px] text-slate-400 font-mono bg-slate-900/60 rounded px-2 py-1 overflow-hidden text-ellipsis whitespace-nowrap">{embedHtml}</code>
                                    <button onClick={() => navigator.clipboard.writeText(embedHtml)}
                                      className="p-1.5 rounded border border-slate-700 hover:border-slate-600 text-slate-500 hover:text-cyan-400 transition shrink-0">
                                      <Copy size={11} />
                                    </button>
                                  </div>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  {/* ── Webhooks ── */}
                  <div className="sku-card rounded-xl p-5">
                    <div className="flex items-center gap-3 mb-1">
                      <SkuIcon color="#a78bfa" size={32}><Webhook size={13} className="text-violet-300" /></SkuIcon>
                      <h3 className="text-white font-semibold text-sm">Webhooks</h3>
                    </div>
                    <p className="text-slate-500 text-xs mb-4">
                      {lang === 'fr'
                        ? 'Recevez les événements de scan en temps réel dans votre système (Zapier, Slack, CI/CD…). Max 5 webhooks.'
                        : 'Receive scan events in real-time in your system (Zapier, Slack, CI/CD…). Max 5 webhooks.'}
                    </p>

                    {/* Created secret banner */}
                    {whCreatedSecret && (
                      <div className="mb-4 bg-green-500/10 border border-green-500/30 rounded-lg p-3">
                        <p className="text-green-400 text-xs font-semibold mb-1 flex items-center gap-1">
                          <Check size={12} />
                          {lang === 'fr' ? 'Webhook créé — conservez ce secret (affiché une seule fois) :' : 'Webhook created — save this secret (shown once):'}
                        </p>
                        <div className="flex items-center gap-2">
                          <code className="flex-1 text-green-300 font-mono text-xs bg-green-500/5 rounded px-2 py-1 break-all">{whCreatedSecret}</code>
                          <button onClick={() => navigator.clipboard.writeText(whCreatedSecret)}
                            className="p-1.5 rounded border border-green-500/30 text-green-400 hover:text-green-200 transition shrink-0">
                            <Copy size={11} />
                          </button>
                        </div>
                        <button onClick={() => setWhCreatedSecret(null)}
                          className="mt-2 text-[10px] text-green-600 hover:text-green-400 transition">
                          {lang === 'fr' ? 'Fermer' : 'Dismiss'}
                        </button>
                      </div>
                    )}

                    {/* Add webhook form */}
                    <div className="bg-slate-800/40 border border-slate-700/50 rounded-lg p-4 mb-4">
                      <p className="text-slate-400 text-xs font-semibold mb-3">{lang === 'fr' ? 'Nouveau webhook' : 'New webhook'}</p>
                      <div className="flex flex-col gap-2">
                        <input
                          type="url"
                          placeholder="https://hooks.zapier.com/…"
                          value={whNewUrl}
                          onChange={e => setWhNewUrl(e.target.value)}
                          className="w-full bg-slate-900/60 border border-slate-700 text-white text-xs rounded-lg px-3 py-2 outline-none focus:border-cyan-500/50 placeholder-slate-600 font-mono"
                        />
                        <input
                          type="text"
                          placeholder={lang === 'fr' ? 'Secret HMAC (optionnel)' : 'HMAC secret (optional)'}
                          value={whNewSecret}
                          onChange={e => setWhNewSecret(e.target.value)}
                          className="w-full bg-slate-900/60 border border-slate-700 text-white text-xs rounded-lg px-3 py-2 outline-none focus:border-cyan-500/50 placeholder-slate-600 font-mono"
                        />
                        {/* Events checkboxes */}
                        <div className="flex flex-wrap gap-2">
                          {ALLOWED_EVENTS.map(ev => (
                            <label key={ev} className="flex items-center gap-1.5 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={whNewEvents.includes(ev)}
                                onChange={e => setWhNewEvents(prev =>
                                  e.target.checked ? [...prev, ev] : prev.filter(x => x !== ev)
                                )}
                                className="w-3 h-3 accent-cyan-500"
                              />
                              <span className="text-slate-400 text-xs font-mono">{ev}</span>
                            </label>
                          ))}
                        </div>
                        {whAddError && (
                          <div className="flex items-center gap-1.5 text-red-400 text-xs">
                            <AlertTriangle size={11} />{whAddError}
                          </div>
                        )}
                        <button
                          onClick={addWebhook}
                          disabled={whAddLoading || !whNewUrl || whNewEvents.length === 0}
                          className="self-start flex items-center gap-2 bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/30 text-cyan-400 px-4 py-2 rounded-lg text-xs font-semibold transition disabled:opacity-40"
                        >
                          {whAddLoading ? <RefreshCw size={12} className="animate-spin" /> : <Plus size={12} />}
                          {lang === 'fr' ? 'Créer' : 'Create'}
                        </button>
                      </div>
                    </div>

                    {/* Webhook list */}
                    {whLoading ? (
                      <div className="flex items-center gap-2 text-slate-600 text-xs py-4">
                        <RefreshCw size={12} className="animate-spin" />
                        {lang === 'fr' ? 'Chargement…' : 'Loading…'}
                      </div>
                    ) : webhooks.length === 0 ? (
                      <p className="text-slate-600 text-xs py-4 text-center">
                        {lang === 'fr' ? 'Aucun webhook configuré.' : 'No webhook configured.'}
                      </p>
                    ) : (
                      <div className="flex flex-col gap-3">
                        {webhooks.map(hook => (
                          <div key={hook.id} className="bg-slate-800/40 border border-slate-700/50 rounded-lg p-3">
                            <div className="flex items-start justify-between gap-2 mb-2">
                              <div className="min-w-0">
                                <p className="text-slate-300 text-xs font-mono truncate">{hook.url}</p>
                                <div className="flex flex-wrap gap-1 mt-1">
                                  {hook.events.map(ev => (
                                    <span key={ev} className="text-[10px] bg-slate-700/60 border border-slate-600/40 text-slate-400 rounded px-1.5 py-0.5 font-mono">{ev}</span>
                                  ))}
                                </div>
                              </div>
                              <div className="flex items-center gap-1.5 shrink-0">
                                {/* Test button */}
                                <button
                                  onClick={() => testWebhook(hook.id)}
                                  disabled={whTestLoading === hook.id}
                                  className="flex items-center gap-1 text-[10px] px-2 py-1 rounded border border-slate-700 hover:border-cyan-500/40 text-slate-500 hover:text-cyan-400 transition font-semibold"
                                  title={lang === 'fr' ? 'Envoyer un test' : 'Send a test'}
                                >
                                  {whTestLoading === hook.id
                                    ? <RefreshCw size={10} className="animate-spin" />
                                    : <Bell size={10} />}
                                  Test
                                </button>
                                {/* Delete button */}
                                <button
                                  onClick={() => deleteWebhook(hook.id)}
                                  className="p-1.5 rounded border border-slate-700 hover:border-red-500/40 text-slate-500 hover:text-red-400 transition"
                                  title={lang === 'fr' ? 'Supprimer' : 'Delete'}
                                >
                                  <Trash2 size={11} />
                                </button>
                              </div>
                            </div>
                            {/* Status / last fired */}
                            <div className="flex items-center gap-3 text-[10px] font-mono text-slate-600">
                              {hook.last_fired_at && (
                                <span className="flex items-center gap-1">
                                  <Clock size={9} />
                                  {new Date(hook.last_fired_at).toLocaleDateString(lang === 'fr' ? 'fr-FR' : 'en-GB', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                </span>
                              )}
                              {hook.last_status !== null && (
                                <span className={hook.last_status >= 200 && hook.last_status < 400 ? 'text-green-500' : 'text-red-400'}>
                                  HTTP {hook.last_status || 'timeout'}
                                </span>
                              )}
                              {/* Test result */}
                              {whTestResult[hook.id] !== undefined && (
                                <span className={whTestResult[hook.id].ok ? 'text-green-400' : 'text-red-400'}>
                                  {whTestResult[hook.id].ok ? '✓ delivered' : `✗ HTTP ${whTestResult[hook.id].status || 'timeout'}`}
                                </span>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* ── Intégrations Slack / Teams ── */}
                  <div className="sku-card rounded-xl p-5">
                    <div className="flex items-center gap-3 mb-5">
                      <SkuIcon color="#22d3ee" size={36}><Link2 size={16} className="text-cyan-300" /></SkuIcon>
                      <div>
                        <h3 className="font-semibold text-slate-100 text-sm">
                          {lang === 'fr' ? 'Intégrations Slack & Teams' : 'Slack & Teams Integrations'}
                        </h3>
                        <p className="text-xs text-slate-400 mt-0.5">
                          {lang === 'fr'
                            ? 'Recevez vos alertes de monitoring directement dans vos channels.'
                            : 'Receive monitoring alerts directly in your channels.'}
                        </p>
                      </div>
                    </div>

                    <div className="flex flex-col gap-4">
                      {/* Slack */}
                      <div className="sku-inset rounded-lg p-4">
                        <div className="flex items-center gap-2 mb-3">
                          <MessageSquare size={14} className="text-cyan-400 shrink-0" />
                          <span className="text-sm font-medium text-slate-200">Slack</span>
                          {integrConfigured.slack && (
                            <span className="ml-auto text-xs bg-green-500/15 text-green-400 px-2 py-0.5 rounded-full border border-green-500/20">
                              ✓ {lang === 'fr' ? 'Configuré' : 'Configured'}
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-400 mb-3">
                          {lang === 'fr'
                            ? 'URL Incoming Webhook depuis Slack → App directory → Incoming Webhooks'
                            : 'Incoming Webhook URL from Slack → App directory → Incoming Webhooks'}
                        </p>
                        <div className="flex gap-2">
                          <input
                            type="url"
                            value={slackUrl}
                            onChange={e => setSlackUrl(e.target.value)}
                            placeholder="https://hooks.slack.com/services/T…/B…/…"
                            className="sku-inset flex-1 rounded px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:ring-1 focus:ring-cyan-500/40"
                          />
                          <button
                            onClick={async () => {
                              setIntegrLoading(true); setIntegrMsg(null);
                              try {
                                await apiClient.patch('/auth/integrations', { slack_webhook_url: slackUrl });
                                setIntegrConfigured(c => ({ ...c, slack: slackUrl.trim() !== '' }));
                                setIntegrMsg({ type: 'ok', text: lang === 'fr' ? 'Slack enregistré ✓' : 'Slack saved ✓' });
                                setSlackUrl('');
                              } catch (e: unknown) {
                                const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
                                setIntegrMsg({ type: 'err', text: msg || (lang === 'fr' ? 'URL invalide' : 'Invalid URL') });
                              } finally { setIntegrLoading(false); }
                            }}
                            disabled={integrLoading || !slackUrl.trim()}
                            className="sku-btn-primary px-3 py-2 rounded text-xs font-medium disabled:opacity-40 shrink-0"
                          >
                            {lang === 'fr' ? 'Enregistrer' : 'Save'}
                          </button>
                          {integrConfigured.slack && (
                            <button
                              onClick={async () => {
                                setIntegrLoading(true); setIntegrMsg(null);
                                try {
                                  await apiClient.patch('/auth/integrations', { slack_webhook_url: '' });
                                  setIntegrConfigured(c => ({ ...c, slack: false }));
                                  setIntegrMsg({ type: 'ok', text: lang === 'fr' ? 'Slack supprimé' : 'Slack removed' });
                                } catch { /* silencieux */ } finally { setIntegrLoading(false); }
                              }}
                              disabled={integrLoading}
                              className="sku-btn-ghost px-3 py-2 rounded text-xs font-medium text-red-400 hover:text-red-300 shrink-0"
                            >
                              <Trash2 size={12} />
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Teams */}
                      <div className="sku-inset rounded-lg p-4">
                        <div className="flex items-center gap-2 mb-3">
                          <MessageSquare size={14} className="text-violet-400 shrink-0" />
                          <span className="text-sm font-medium text-slate-200">Microsoft Teams</span>
                          {integrConfigured.teams && (
                            <span className="ml-auto text-xs bg-green-500/15 text-green-400 px-2 py-0.5 rounded-full border border-green-500/20">
                              ✓ {lang === 'fr' ? 'Configuré' : 'Configured'}
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-400 mb-3">
                          {lang === 'fr'
                            ? 'URL Incoming Webhook depuis Teams → channel → Connecteurs → Incoming Webhook'
                            : 'Incoming Webhook URL from Teams → channel → Connectors → Incoming Webhook'}
                        </p>
                        <div className="flex gap-2">
                          <input
                            type="url"
                            value={teamsUrl}
                            onChange={e => setTeamsUrl(e.target.value)}
                            placeholder="https://…webhook.office.com/webhookb2/…"
                            className="sku-inset flex-1 rounded px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:ring-1 focus:ring-violet-500/40"
                          />
                          <button
                            onClick={async () => {
                              setIntegrLoading(true); setIntegrMsg(null);
                              try {
                                await apiClient.patch('/auth/integrations', { teams_webhook_url: teamsUrl });
                                setIntegrConfigured(c => ({ ...c, teams: teamsUrl.trim() !== '' }));
                                setIntegrMsg({ type: 'ok', text: lang === 'fr' ? 'Teams enregistré ✓' : 'Teams saved ✓' });
                                setTeamsUrl('');
                              } catch (e: unknown) {
                                const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
                                setIntegrMsg({ type: 'err', text: msg || (lang === 'fr' ? 'URL invalide' : 'Invalid URL') });
                              } finally { setIntegrLoading(false); }
                            }}
                            disabled={integrLoading || !teamsUrl.trim()}
                            className="sku-btn-primary px-3 py-2 rounded text-xs font-medium disabled:opacity-40 shrink-0"
                          >
                            {lang === 'fr' ? 'Enregistrer' : 'Save'}
                          </button>
                          {integrConfigured.teams && (
                            <button
                              onClick={async () => {
                                setIntegrLoading(true); setIntegrMsg(null);
                                try {
                                  await apiClient.patch('/auth/integrations', { teams_webhook_url: '' });
                                  setIntegrConfigured(c => ({ ...c, teams: false }));
                                  setIntegrMsg({ type: 'ok', text: lang === 'fr' ? 'Teams supprimé' : 'Teams removed' });
                                } catch { /* silencieux */ } finally { setIntegrLoading(false); }
                              }}
                              disabled={integrLoading}
                              className="sku-btn-ghost px-3 py-2 rounded text-xs font-medium text-red-400 hover:text-red-300 shrink-0"
                            >
                              <Trash2 size={12} />
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Message retour */}
                      {integrMsg && (
                        <p className={`text-xs px-3 py-2 rounded ${integrMsg.type === 'ok' ? 'text-green-400 bg-green-500/10' : 'text-red-400 bg-red-500/10'}`}>
                          {integrMsg.text}
                        </p>
                      )}
                    </div>
                  </div>

                </div>
              )}

              {/* ══════════════════════════════════════════════════════════════
                  TAB 4 — PARAMÈTRES
              ══════════════════════════════════════════════════════════════ */}
              {tab === 'settings' && (
                <div className="flex flex-col gap-5">

                  {/* Sub-nav */}
                  <div className="flex gap-2 flex-wrap">
                    {([
                      { id: 'profile'     as const, label: lang === 'fr' ? 'Profil & Sécurité' : 'Profile & Security', icon: <Key size={13} /> },
                      { id: 'billing'     as const, label: lang === 'fr' ? 'Facturation' : 'Billing',                  icon: <CreditCard size={13} /> },
                      ...(user?.plan && (user.plan === 'pro' || user.plan === 'dev') ? [{
                        id: 'whitelabel' as const,
                        label: lang === 'fr' ? 'Marque blanche' : 'White-label',
                        icon: <Shield size={13} />,
                      }] : []),
                      { id: 'danger'      as const, label: lang === 'fr' ? 'Zone dangereuse' : 'Danger zone',          icon: <AlertTriangle size={13} /> },
                    ]).map(s => (
                      <button
                        key={s.id}
                        onClick={() => setSettingsSection(s.id)}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition border ${
                          settingsSection === s.id
                            ? s.id === 'danger'
                              ? 'bg-red-500/20 text-red-400 border-red-500/30'
                              : 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30'
                            : 'text-slate-500 border-slate-800 hover:border-slate-700 hover:text-slate-300'
                        }`}
                      >
                        {s.icon}{s.label}
                      </button>
                    ))}
                  </div>

                  {/* ── PROFILE & SECURITY ── */}
                  {settingsSection === 'profile' && (
                    <div className="flex flex-col gap-4">

                      {/* Change email */}
                      <div className="sku-card rounded-xl p-5">
                        <div className="flex items-center gap-3 mb-4">
                          <SkuIcon color="#22d3ee" size={32}><Mail size={13} className="text-cyan-300" /></SkuIcon>
                          <h3 className="text-white font-semibold text-sm">{lang === 'fr' ? 'Adresse email' : 'Email address'}</h3>
                        </div>
                        {user?.google_id ? (
                          <p className="text-slate-400 text-xs">
                            {lang === 'fr' ? 'Votre compte est lié à Google. L\'email est géré par Google.' : 'Your account is linked to Google. Email is managed by Google.'}
                          </p>
                        ) : (
                          <>
                            <p className="text-slate-500 text-xs mb-4">
                              {lang === 'fr' ? 'Email actuel :' : 'Current email:'}{' '}
                              <span className="text-slate-300 font-mono">{user?.email}</span>
                            </p>
                            {emailMsg && (
                              <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs mb-3 ${emailMsg.type === 'ok' ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                                {emailMsg.type === 'ok' ? <Check size={12} /> : <AlertTriangle size={12} />}
                                {emailMsg.text}
                              </div>
                            )}
                            <div className="flex flex-col gap-3">
                              <input
                                type="email"
                                placeholder={lang === 'fr' ? 'Nouvel email' : 'New email'}
                                value={newEmail}
                                onChange={e => setNewEmail(e.target.value)}
                                className="w-full bg-slate-800/60 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 outline-none focus:border-cyan-500/50 placeholder-slate-600"
                              />
                              <input
                                type="password"
                                placeholder={lang === 'fr' ? 'Mot de passe actuel (confirmation)' : 'Current password (confirmation)'}
                                value={emailPassword}
                                onChange={e => setEmailPassword(e.target.value)}
                                className="w-full bg-slate-800/60 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 outline-none focus:border-cyan-500/50 placeholder-slate-600"
                              />
                              <button
                                onClick={handleChangeEmail}
                                disabled={emailLoading || !newEmail || !emailPassword}
                                className="self-start flex items-center gap-2 bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/30 text-cyan-400 px-4 py-2 rounded-lg text-xs font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed"
                              >
                                {emailLoading ? <RefreshCw size={12} className="animate-spin" /> : <Check size={12} />}
                                {lang === 'fr' ? 'Mettre à jour l\'email' : 'Update email'}
                              </button>
                            </div>
                          </>
                        )}
                      </div>

                      {/* Change password */}
                      <div className="sku-card rounded-xl p-5">
                        <div className="flex items-center gap-3 mb-4">
                          <SkuIcon color="#818cf8" size={32}><Key size={13} className="text-indigo-300" /></SkuIcon>
                          <h3 className="text-white font-semibold text-sm">{lang === 'fr' ? 'Mot de passe' : 'Password'}</h3>
                        </div>
                        {user?.google_id ? (
                          <p className="text-slate-400 text-xs">
                            {lang === 'fr' ? 'Votre compte est lié à Google. Connectez-vous via Google.' : 'Your account is linked to Google. Sign in via Google.'}
                          </p>
                        ) : (
                          <>
                            {pwdMsg && (
                              <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs mb-3 ${pwdMsg.type === 'ok' ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                                {pwdMsg.type === 'ok' ? <Check size={12} /> : <AlertTriangle size={12} />}
                                {pwdMsg.text}
                              </div>
                            )}
                            <div className="flex flex-col gap-3">
                              <input
                                type="password"
                                placeholder={lang === 'fr' ? 'Mot de passe actuel' : 'Current password'}
                                value={currentPwd}
                                onChange={e => setCurrentPwd(e.target.value)}
                                className="w-full bg-slate-800/60 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 outline-none focus:border-cyan-500/50 placeholder-slate-600"
                              />
                              <input
                                type="password"
                                placeholder={lang === 'fr' ? 'Nouveau mot de passe' : 'New password'}
                                value={newPwd}
                                onChange={e => setNewPwd(e.target.value)}
                                className="w-full bg-slate-800/60 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 outline-none focus:border-cyan-500/50 placeholder-slate-600"
                              />
                              <input
                                type="password"
                                placeholder={lang === 'fr' ? 'Confirmer le nouveau mot de passe' : 'Confirm new password'}
                                value={confirmPwd}
                                onChange={e => setConfirmPwd(e.target.value)}
                                className="w-full bg-slate-800/60 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 outline-none focus:border-cyan-500/50 placeholder-slate-600"
                              />
                              <button
                                onClick={handleChangePassword}
                                disabled={pwdLoading || !currentPwd || !newPwd || !confirmPwd}
                                className="self-start flex items-center gap-2 bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/30 text-cyan-400 px-4 py-2 rounded-lg text-xs font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed"
                              >
                                {pwdLoading ? <RefreshCw size={12} className="animate-spin" /> : <Check size={12} />}
                                {lang === 'fr' ? 'Mettre à jour le mot de passe' : 'Update password'}
                              </button>
                            </div>
                          </>
                        )}
                      </div>

                      {/* ── 2FA ── */}
                      <div className="sku-card rounded-xl p-5">
                        <div className="flex items-center gap-3 mb-4">
                          <SkuIcon color="#4ade80" size={32}><Shield size={13} className="text-green-300" /></SkuIcon>
                          <div>
                            <h3 className="text-white font-semibold text-sm">{lang === 'fr' ? 'Double authentification (2FA)' : 'Two-factor authentication (2FA)'}</h3>
                            {user?.mfa_enabled && (
                              <span className="inline-flex items-center gap-1 text-xs text-green-400 mt-0.5">
                                <Check size={10} />{lang === 'fr' ? 'Activée' : 'Enabled'}
                              </span>
                            )}
                          </div>
                        </div>

                        {mfaMsg && (
                          <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs mb-3 ${mfaMsg.type === 'ok' ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                            {mfaMsg.type === 'ok' ? <Check size={12} /> : <AlertTriangle size={12} />}
                            {mfaMsg.text}
                          </div>
                        )}

                        {!user?.mfa_enabled && mfaStep === null && (
                          <div>
                            <p className="text-slate-400 text-xs mb-3">
                              {lang === 'fr'
                                ? 'Protégez votre compte avec une application d\'authentification (Google Authenticator, Authy…).'
                                : 'Protect your account with an authenticator app (Google Authenticator, Authy…).'}
                            </p>
                            <button
                              onClick={handleMfaSetup}
                              disabled={mfaLoading}
                              className="flex items-center gap-2 bg-green-500/15 hover:bg-green-500/25 border border-green-500/30 text-green-400 px-4 py-2 rounded-lg text-xs font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed"
                            >
                              {mfaLoading ? <RefreshCw size={12} className="animate-spin" /> : <Shield size={12} />}
                              {lang === 'fr' ? 'Configurer la 2FA' : 'Set up 2FA'}
                            </button>
                          </div>
                        )}

                        {!user?.mfa_enabled && mfaStep === 'setup' && (
                          <div className="flex flex-col gap-4">
                            <p className="text-slate-400 text-xs">
                              {lang === 'fr'
                                ? 'Scannez ce QR code avec votre application d\'authentification, puis entrez le code à 6 chiffres pour confirmer.'
                                : 'Scan this QR code with your authenticator app, then enter the 6-digit code to confirm.'}
                            </p>
                            {mfaQrCode && (
                              <div className="flex justify-center">
                                <img
                                  src={`data:image/png;base64,${mfaQrCode}`}
                                  alt="QR 2FA"
                                  className="w-36 h-36 rounded-lg border border-slate-700"
                                />
                              </div>
                            )}
                            {mfaSecret && (
                              <div className="bg-slate-800/60 border border-slate-700 rounded-lg px-3 py-2">
                                <p className="text-slate-500 text-xs mb-1">{lang === 'fr' ? 'Clé manuelle (si QR indisponible) :' : 'Manual key (if QR unavailable):'}</p>
                                <code className="text-cyan-400 text-xs font-mono tracking-widest break-all">{mfaSecret}</code>
                              </div>
                            )}
                            <input
                              type="text"
                              inputMode="numeric"
                              maxLength={6}
                              placeholder={lang === 'fr' ? 'Code à 6 chiffres' : '6-digit code'}
                              value={mfaCode}
                              onChange={e => setMfaCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                              className="w-full bg-slate-800/60 border border-slate-700 text-white text-center text-xl font-mono tracking-widest rounded-lg px-3 py-2 outline-none focus:border-green-500/50 placeholder-slate-600"
                            />
                            <div className="flex items-center gap-2">
                              <button
                                onClick={handleMfaVerify}
                                disabled={mfaLoading || mfaCode.length !== 6}
                                className="flex items-center gap-2 bg-green-500/15 hover:bg-green-500/25 border border-green-500/30 text-green-400 px-4 py-2 rounded-lg text-xs font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed"
                              >
                                {mfaLoading ? <RefreshCw size={12} className="animate-spin" /> : <Check size={12} />}
                                {lang === 'fr' ? 'Confirmer' : 'Confirm'}
                              </button>
                              <button
                                onClick={() => { setMfaStep(null); setMfaMsg(null); setMfaCode(''); }}
                                className="text-slate-500 hover:text-slate-300 text-xs transition"
                              >
                                {lang === 'fr' ? 'Annuler' : 'Cancel'}
                              </button>
                            </div>
                          </div>
                        )}

                        {user?.mfa_enabled && mfaStep === null && (
                          <div>
                            <p className="text-slate-400 text-xs mb-3">
                              {lang === 'fr'
                                ? 'La double authentification est activée. Chaque connexion nécessite un code de votre application.'
                                : 'Two-factor authentication is enabled. Every sign-in requires a code from your app.'}
                            </p>
                            <button
                              onClick={() => { setMfaStep('disabling'); setMfaCode(''); setMfaDisablePwd(''); setMfaMsg(null); }}
                              className="flex items-center gap-2 bg-red-500/15 hover:bg-red-500/25 border border-red-500/30 text-red-400 px-4 py-2 rounded-lg text-xs font-semibold transition"
                            >
                              <X size={12} />
                              {lang === 'fr' ? 'Désactiver la 2FA' : 'Disable 2FA'}
                            </button>
                          </div>
                        )}

                        {user?.mfa_enabled && mfaStep === 'disabling' && (
                          <div className="flex flex-col gap-3">
                            <p className="text-slate-400 text-xs">
                              {user?.google_id
                                ? (lang === 'fr'
                                    ? 'Confirmez avec votre code TOTP actuel.'
                                    : 'Confirm with your current TOTP code.')
                                : (lang === 'fr'
                                    ? 'Confirmez avec votre mot de passe et votre code TOTP actuel.'
                                    : 'Confirm with your password and current TOTP code.')}
                            </p>
                            {/* Mot de passe : seulement pour les comptes non-Google */}
                            {!user?.google_id && (
                              <input
                                type="password"
                                placeholder={lang === 'fr' ? 'Mot de passe' : 'Password'}
                                value={mfaDisablePwd}
                                onChange={e => setMfaDisablePwd(e.target.value)}
                                className="w-full bg-slate-800/60 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 outline-none focus:border-red-500/50 placeholder-slate-600"
                              />
                            )}
                            <input
                              type="text"
                              inputMode="numeric"
                              maxLength={6}
                              placeholder={lang === 'fr' ? 'Code TOTP (6 chiffres)' : 'TOTP code (6 digits)'}
                              value={mfaCode}
                              onChange={e => setMfaCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                              className="w-full bg-slate-800/60 border border-slate-700 text-white text-center text-xl font-mono tracking-widest rounded-lg px-3 py-2 outline-none focus:border-red-500/50 placeholder-slate-600"
                            />
                            <div className="flex items-center gap-2">
                              <button
                                onClick={handleMfaDisable}
                                disabled={mfaLoading || (!user?.google_id && !mfaDisablePwd) || mfaCode.length !== 6}
                                className="flex items-center gap-2 bg-red-500/15 hover:bg-red-500/25 border border-red-500/30 text-red-400 px-4 py-2 rounded-lg text-xs font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed"
                              >
                                {mfaLoading ? <RefreshCw size={12} className="animate-spin" /> : <X size={12} />}
                                {lang === 'fr' ? 'Désactiver' : 'Disable'}
                              </button>
                              <button
                                onClick={() => { setMfaStep(null); setMfaMsg(null); setMfaCode(''); setMfaDisablePwd(''); }}
                                className="text-slate-500 hover:text-slate-300 text-xs transition"
                              >
                                {lang === 'fr' ? 'Annuler' : 'Cancel'}
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* ── BILLING ── */}
                  {settingsSection === 'billing' && (
                    <div className="flex flex-col gap-4">
                      <div className="sku-card rounded-xl p-5">
                        <div className="flex items-center gap-3 mb-5">
                          <SkuIcon color="#22d3ee" size={32}><CreditCard size={13} className="text-cyan-300" /></SkuIcon>
                          <h3 className="text-white font-semibold text-sm">{lang === 'fr' ? 'Abonnement actuel' : 'Current plan'}</h3>
                        </div>
                        <div className="flex items-center justify-between flex-wrap gap-4">
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <span className={`text-xl font-black tracking-wide ${user?.plan === 'dev' ? 'text-violet-400' : user?.plan === 'pro' ? 'text-purple-400' : user?.plan === 'starter' ? 'text-cyan-400' : 'text-slate-400'}`}>
                                {user?.plan?.toUpperCase() ?? 'FREE'}
                              </span>
                              {isPremium && (
                                <span className="text-xs bg-green-500/15 text-green-400 border border-green-500/30 px-1.5 py-0.5 rounded font-semibold">
                                  {lang === 'fr' ? 'Actif' : 'Active'}
                                </span>
                              )}
                            </div>
                            <p className="text-slate-500 text-xs">
                              {user?.plan === 'dev'
                                ? (lang === 'fr' ? '29,90 € / mois · API + Application Scanning' : '€29.90 / month · API + Application Scanning')
                                : user?.plan === 'pro'
                                ? (lang === 'fr' ? '19,90 € / mois · monitoring illimité' : '€19.90 / month · unlimited monitoring')
                                : user?.plan === 'starter'
                                ? (lang === 'fr' ? '9,90 € / mois · 1 domaine surveillé' : '€9.90 / month · 1 monitored domain')
                                : (lang === 'fr' ? 'Plan gratuit · 1 scan / jour' : 'Free plan · 1 scan / day')}
                            </p>
                          </div>
                          {isPremium && (
                            <button
                              onClick={handlePortal}
                              disabled={portalLoading}
                              className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 px-4 py-2 rounded-lg text-xs font-semibold transition disabled:opacity-40"
                            >
                              {portalLoading ? <RefreshCw size={12} className="animate-spin" /> : <CreditCard size={12} />}
                              {lang === 'fr' ? 'Gérer l\'abonnement' : 'Manage subscription'}
                            </button>
                          )}
                        </div>

                        {/* Divider */}
                        <div className="border-t border-slate-800 my-5" />

                        {/* Plan comparison */}
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                          <div className={`rounded-xl border p-4 ${!isPremium ? 'border-cyan-500/30 bg-cyan-500/5' : 'border-slate-800'}`}>
                            <p className="text-slate-300 font-bold text-sm mb-1">Free</p>
                            <p className="text-slate-600 text-xs mb-3">{lang === 'fr' ? '0 € / mois' : '€0 / month'}</p>
                            <ul className="text-slate-500 text-xs space-y-1">
                              <li>· {lang === 'fr' ? '1 scan / jour' : '1 scan / day'}</li>
                              <li>· {lang === 'fr' ? 'Résultats basiques' : 'Basic results'}</li>
                            </ul>
                          </div>
                          <div className={`rounded-xl border p-4 ${user?.plan === 'starter' ? 'border-cyan-500/30 bg-cyan-500/5' : 'border-slate-800'}`}>
                            <p className="text-cyan-400 font-bold text-sm mb-1">Starter</p>
                            <p className="text-slate-600 text-xs mb-3">{lang === 'fr' ? '9,90 € / mois' : '€9.90 / month'}</p>
                            <ul className="text-slate-500 text-xs space-y-1">
                              <li>· {lang === 'fr' ? '1 domaine surveillé' : '1 monitored domain'}</li>
                              <li>· {lang === 'fr' ? 'Checks avancés' : 'Advanced checks'}</li>
                              <li>· {lang === 'fr' ? 'Rapports PDF' : 'PDF reports'}</li>
                            </ul>
                          </div>
                          <div className={`rounded-xl border p-4 ${user?.plan === 'pro' ? 'border-purple-500/30 bg-purple-500/5' : 'border-slate-800'}`}>
                            <p className="text-purple-400 font-bold text-sm mb-1">Pro</p>
                            <p className="text-slate-600 text-xs mb-3">{lang === 'fr' ? '19,90 € / mois' : '€19.90 / month'}</p>
                            <ul className="text-slate-500 text-xs space-y-1">
                              <li>· {lang === 'fr' ? 'Monitoring illimité' : 'Unlimited monitoring'}</li>
                              <li>· {lang === 'fr' ? 'Webhooks & marque blanche' : 'Webhooks & white-label'}</li>
                            </ul>
                          </div>
                          <div className={`rounded-xl border p-4 ${user?.plan === 'dev' ? 'border-violet-500/30 bg-violet-500/5' : 'border-slate-800'}`}>
                            <p className="text-violet-400 font-bold text-sm mb-1">Dev</p>
                            <p className="text-slate-600 text-xs mb-3">{lang === 'fr' ? '29,90 € / mois' : '€29.90 / month'}</p>
                            <ul className="text-slate-500 text-xs space-y-1">
                              <li>· {lang === 'fr' ? 'Accès API (wsk_)' : 'API access (wsk_)'}</li>
                              <li>· {lang === 'fr' ? 'Application Scanning' : 'Application Scanning'}</li>
                            </ul>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* ── WHITE-LABEL ── */}
                  {settingsSection === 'whitelabel' && (
                    <div className="flex flex-col gap-5">
                      <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-5">
                        <div className="flex items-center gap-3 mb-1">
                          <SkuIcon color="#22d3ee" size={32}><Shield size={13} className="text-cyan-300" /></SkuIcon>
                          <h3 className="text-cyan-400 font-semibold text-sm">{lang === 'fr' ? 'Marque blanche — Rapports PDF' : 'White-label — PDF Reports'}</h3>
                        </div>
                        <p className="text-slate-400 text-xs mb-5">
                          {lang === 'fr'
                            ? 'Personnalisez les rapports PDF avec le nom et le logo de votre agence. Vos clients verront votre marque, pas Wezea.'
                            : 'Customise PDF reports with your agency name and logo. Your clients will see your brand, not Wezea.'}
                        </p>

                        {wbLoading ? (
                          <div className="text-slate-500 text-xs">{lang === 'fr' ? 'Chargement...' : 'Loading...'}</div>
                        ) : (
                          <div className="flex flex-col gap-4">

                            {/* Toggle activer */}
                            <label className="flex items-center gap-3 cursor-pointer">
                              <div
                                onClick={() => setWbEnabled(v => !v)}
                                className={`relative w-10 h-5 rounded-full transition-colors ${wbEnabled ? 'bg-cyan-500' : 'bg-slate-700'}`}
                              >
                                <div className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${wbEnabled ? 'translate-x-5' : ''}`} />
                              </div>
                              <span className="text-slate-300 text-sm">
                                {lang === 'fr' ? 'Activer la marque blanche' : 'Enable white-label'}
                              </span>
                            </label>

                            {/* Nom de l'agence */}
                            <div>
                              <label className="text-slate-400 text-xs block mb-1.5">
                                {lang === 'fr' ? 'Nom de l\'agence' : 'Agency name'}
                              </label>
                              <input
                                type="text"
                                value={wbName}
                                onChange={e => setWbName(e.target.value)}
                                maxLength={100}
                                placeholder={lang === 'fr' ? 'Mon Agence IT' : 'My IT Agency'}
                                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm placeholder-slate-600 focus:outline-none focus:border-cyan-500 transition"
                              />
                            </div>

                            {/* Couleur principale */}
                            <div>
                              <label className="text-slate-400 text-xs block mb-1.5">
                                {lang === 'fr' ? 'Couleur principale' : 'Primary colour'}
                              </label>
                              <div className="flex items-center gap-3">
                                <input
                                  type="color"
                                  value={wbColor}
                                  onChange={e => setWbColor(e.target.value)}
                                  className="w-10 h-9 rounded-lg border border-slate-700 bg-slate-800 cursor-pointer p-0.5"
                                />
                                <input
                                  type="text"
                                  value={wbColor}
                                  onChange={e => setWbColor(e.target.value)}
                                  maxLength={7}
                                  placeholder="#22d3ee"
                                  className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm placeholder-slate-600 focus:outline-none focus:border-cyan-500 transition font-mono"
                                />
                                <div className="w-8 h-8 rounded-lg border border-slate-700 shrink-0" style={{ backgroundColor: wbColor }} />
                              </div>
                            </div>

                            {/* Upload logo */}
                            <div>
                              <label className="text-slate-400 text-xs block mb-1.5">
                                {lang === 'fr' ? 'Logo (PNG, JPG, SVG — max 200 Ko)' : 'Logo (PNG, JPG, SVG — max 200 KB)'}
                              </label>
                              <div className="flex items-center gap-3">
                                {wb?.has_logo && wb.logo_b64 && (
                                  <img src={wb.logo_b64} alt="logo" className="h-10 max-w-[100px] object-contain rounded border border-slate-700 bg-slate-800 p-1" />
                                )}
                                <label className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg px-3 py-2 text-slate-300 text-xs font-medium cursor-pointer transition">
                                  <input
                                    type="file"
                                    accept="image/png,image/jpeg,image/svg+xml,image/webp"
                                    className="hidden"
                                    disabled={wbLogoUploading}
                                    onChange={async e => {
                                      const file = e.target.files?.[0];
                                      if (!file) return;
                                      setWbLogoUploading(true);
                                      setWbMsg(null);
                                      try {
                                        await uploadWhiteLabelLogo(file);
                                        const updated = await getWhiteLabel();
                                        setWb(updated);
                                        setWbMsg({ type: 'ok', text: lang === 'fr' ? 'Logo uploadé ✓' : 'Logo uploaded ✓' });
                                      } catch (err: unknown) {
                                        const raw = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
                                        const detail = typeof raw === 'string' ? raw : undefined;
                                        setWbMsg({ type: 'err', text: detail || (lang === 'fr' ? 'Erreur upload logo' : 'Logo upload error') });
                                      } finally {
                                        setWbLogoUploading(false);
                                      }
                                    }}
                                  />
                                  {wbLogoUploading
                                    ? (lang === 'fr' ? 'Upload...' : 'Uploading...')
                                    : (lang === 'fr' ? 'Choisir un logo' : 'Choose a logo')}
                                </label>
                                {wb?.has_logo && (
                                  <button
                                    onClick={async () => {
                                      setWbMsg(null);
                                      try {
                                        await deleteWhiteLabelLogo();
                                        setWb(prev => prev ? { ...prev, has_logo: false, logo_b64: null } : null);
                                        setWbMsg({ type: 'ok', text: lang === 'fr' ? 'Logo supprimé' : 'Logo deleted' });
                                      } catch {
                                        setWbMsg({ type: 'err', text: lang === 'fr' ? 'Erreur suppression' : 'Delete error' });
                                      }
                                    }}
                                    className="text-red-400 hover:text-red-300 text-xs transition"
                                  >
                                    {lang === 'fr' ? 'Supprimer' : 'Delete'}
                                  </button>
                                )}
                              </div>
                            </div>

                            {/* Message feedback */}
                            {wbMsg && (
                              <p className={`text-xs ${wbMsg.type === 'ok' ? 'text-emerald-400' : 'text-red-400'}`}>
                                {wbMsg.text}
                              </p>
                            )}

                            {/* Bouton sauvegarder */}
                            <button
                              disabled={wbSaving}
                              onClick={async () => {
                                setWbSaving(true);
                                setWbMsg(null);
                                try {
                                  const updated = await updateWhiteLabel({
                                    enabled: wbEnabled,
                                    company_name: wbName,
                                    primary_color: wbColor,
                                  });
                                  setWb(prev => prev ? { ...prev, ...updated } : updated);
                                  setWbMsg({ type: 'ok', text: lang === 'fr' ? 'Paramètres sauvegardés ✓' : 'Settings saved ✓' });
                                } catch {
                                  setWbMsg({ type: 'err', text: lang === 'fr' ? 'Erreur lors de la sauvegarde' : 'Save error' });
                                } finally {
                                  setWbSaving(false);
                                }
                              }}
                              className="w-full py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 text-slate-900 text-sm font-bold transition"
                            >
                              {wbSaving
                                ? (lang === 'fr' ? 'Sauvegarde...' : 'Saving...')
                                : (lang === 'fr' ? 'Enregistrer les paramètres' : 'Save settings')}
                            </button>

                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* ── DANGER ZONE ── */}
                  {settingsSection === 'danger' && (
                    <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-5">
                      <div className="flex items-center gap-3 mb-2">
                        <SkuIcon color="#f87171" size={32}><AlertTriangle size={13} className="text-red-300" /></SkuIcon>
                        <h3 className="text-red-400 font-semibold text-sm">{lang === 'fr' ? 'Zone dangereuse' : 'Danger zone'}</h3>
                      </div>
                      <p className="text-slate-400 text-xs mb-5">
                        {lang === 'fr'
                          ? 'La suppression de votre compte est définitive. Toutes vos données (scans, domaines surveillés) seront effacées conformément au RGPD.'
                          : 'Deleting your account is permanent. All your data (scans, monitored domains) will be erased in compliance with GDPR.'}
                      </p>
                      <button
                        onClick={() => setShowDeleteModal(true)}
                        className="flex items-center gap-2 bg-red-500/15 hover:bg-red-500/25 border border-red-500/30 text-red-400 px-4 py-2 rounded-lg text-xs font-semibold transition"
                      >
                        <Trash2 size={12} />
                        {lang === 'fr' ? 'Supprimer mon compte' : 'Delete my account'}
                      </button>
                    </div>
                  )}

                </div>
              )}

            </motion.div>
          </AnimatePresence>
        )}
      </main>

      {/* ── Scan Result Modal ─────────────────────────────────────────────── */}
      {scanModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)' }}
          onClick={() => setScanModal(null)}
        >
          <div
            className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl"
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div className="sticky top-0 z-10 flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/95 backdrop-blur-sm">
              <div className="flex items-center gap-3">
                <SkuIcon color="#22d3ee" size={36}><Shield size={15} className="text-cyan-300" /></SkuIcon>
                <div>
                  <p className="text-white font-mono font-bold text-sm">{scanModal.domain}</p>
                  <p className="text-slate-500 text-xs">
                    {new Date(scanModal.created_at).toLocaleDateString(lang === 'fr' ? 'fr-FR' : 'en-GB', {
                      day: '2-digit', month: 'long', year: 'numeric',
                      hour: '2-digit', minute: '2-digit',
                    })}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                {/* Score */}
                <div className="text-right">
                  <p className={`text-2xl font-black font-mono ${scoreColor(scanModal.security_score)}`}>
                    {scanModal.security_score}<span className="text-xs text-slate-600 font-normal">/100</span>
                  </p>
                  <RiskBadge level={scanModal.risk_level} />
                </div>
                {/* PDF button */}
                <button
                  onClick={() => generatePdf(scanModal.scan_uuid, scanModal.domain)}
                  disabled={pdfLoading === scanModal.scan_uuid}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/20 transition text-xs font-semibold disabled:opacity-40"
                >
                  {pdfLoading === scanModal.scan_uuid
                    ? <div className="w-3 h-3 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
                    : <FileDown size={13} />
                  }
                  {lang === 'fr' ? 'Rapport PDF' : 'PDF Report'}
                </button>
                <button onClick={() => setScanModal(null)} className="text-slate-500 hover:text-white transition p-1">
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* Summary stats */}
            <div className="grid grid-cols-3 gap-3 px-6 py-4 border-b border-slate-800">
              <div className="bg-slate-800/50 rounded-lg p-3 text-center">
                <p className="text-2xl font-black font-mono text-white">{scanModal.findings.length}</p>
                <p className="text-slate-500 text-xs mt-0.5">{lang === 'fr' ? 'Findings' : 'Findings'}</p>
              </div>
              <div className="bg-slate-800/50 rounded-lg p-3 text-center">
                <p className="text-2xl font-black font-mono text-red-400">
                  {scanModal.findings.filter(f => f.severity === 'CRITICAL').length}
                </p>
                <p className="text-slate-500 text-xs mt-0.5">{lang === 'fr' ? 'Critiques' : 'Critical'}</p>
              </div>
              <div className="bg-slate-800/50 rounded-lg p-3 text-center">
                <p className="text-2xl font-black font-mono text-orange-400">
                  {scanModal.findings.filter(f => f.severity === 'HIGH').length}
                </p>
                <p className="text-slate-500 text-xs mt-0.5">{lang === 'fr' ? 'Élevés' : 'High'}</p>
              </div>
            </div>

            {/* Findings list */}
            <div className="px-6 py-4 flex flex-col gap-3">
              {scanModal.findings.length === 0 ? (
                <div className="py-8 text-center">
                  <p className="text-green-400 font-semibold text-sm">✓ {lang === 'fr' ? 'Aucune vulnérabilité détectée' : 'No vulnerability detected'}</p>
                </div>
              ) : (
                scanModal.findings.map((f, i) => {
                  const sevColors: Record<string, string> = {
                    CRITICAL: 'border-l-red-500 bg-red-500/5',
                    HIGH:     'border-l-orange-500 bg-orange-500/5',
                    MEDIUM:   'border-l-yellow-500 bg-yellow-500/5',
                    LOW:      'border-l-blue-500 bg-blue-500/5',
                    INFO:     'border-l-slate-500 bg-slate-800/30',
                  };
                  const sevText: Record<string, string> = {
                    CRITICAL: 'text-red-400', HIGH: 'text-orange-400',
                    MEDIUM: 'text-yellow-400', LOW: 'text-blue-400', INFO: 'text-slate-400',
                  };
                  return (
                    <div key={i} className={`border-l-2 rounded-r-lg p-3 ${sevColors[f.severity] ?? sevColors.INFO}`}>
                      <div className="flex items-start justify-between gap-2 mb-1">
                        <p className="text-white text-sm font-semibold leading-snug">{f.title ?? f.message}</p>
                        <span className={`text-xs font-bold font-mono shrink-0 ${sevText[f.severity] ?? sevText.INFO}`}>
                          {f.severity}
                          {(f.penalty ?? 0) > 0 && <span className="text-slate-500 font-normal ml-1">−{f.penalty}pt</span>}
                        </span>
                      </div>
                      <p className="text-slate-500 text-xs font-mono mb-2">{f.category}</p>
                      {f.plain_explanation && (
                        <p className="text-slate-300 text-xs leading-relaxed mb-2">{f.plain_explanation}</p>
                      )}
                      {f.recommendation && (() => {
                        const recLower = f.recommendation.toLowerCase();
                        const matchedLink = blogLinks.find(l =>
                          l.match_keyword.split(',').some(kw => recLower.includes(kw.trim().toLowerCase()))
                        );
                        return (
                          <>
                            <p className="text-cyan-400/80 text-xs leading-relaxed">→ {f.recommendation}</p>
                            {matchedLink && (
                              <a
                                href={matchedLink.article_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1.5 mt-1.5 text-[11px] text-cyan-400 hover:text-cyan-300 transition-colors font-medium"
                              >
                                <BookOpen size={10} />
                                {lang === 'fr' ? 'Lire l\'article : ' : 'Read article: '}{matchedLink.article_title}
                              </a>
                            )}
                          </>
                        );
                      })()}
                      {f.technical_detail && (
                        <p className="text-slate-600 text-xs font-mono mt-1 leading-relaxed">{f.technical_detail}</p>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Delete Account Modal ──────────────────────────────────────────── */}
      {showDeleteModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.80)', backdropFilter: 'blur(4px)' }}
          onClick={() => { setShowDeleteModal(false); setDeletePassword(''); setDeleteError(''); }}
        >
          <div
            className="w-full max-w-md rounded-2xl border border-red-500/20 bg-slate-900 shadow-2xl p-6"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 rounded-lg bg-red-500/10 border border-red-500/20">
                <AlertTriangle size={16} className="text-red-400" />
              </div>
              <div>
                <p className="text-white font-bold text-sm">
                  {lang === 'fr' ? 'Supprimer mon compte' : 'Delete my account'}
                </p>
                <p className="text-slate-500 text-xs">
                  {lang === 'fr' ? 'Cette action est irréversible.' : 'This action is irreversible.'}
                </p>
              </div>
            </div>
            <p className="text-slate-400 text-xs mb-4">
              {lang === 'fr'
                ? 'Tous vos scans et domaines surveillés seront définitivement supprimés. Confirmez votre mot de passe pour continuer.'
                : 'All your scans and monitored domains will be permanently deleted. Confirm your password to continue.'}
            </p>
            {deleteError && (
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-red-500/10 text-red-400 text-xs mb-3">
                <AlertTriangle size={12} />{deleteError}
              </div>
            )}
            <input
              type="password"
              placeholder={lang === 'fr' ? 'Mot de passe actuel' : 'Current password'}
              value={deletePassword}
              onChange={e => setDeletePassword(e.target.value)}
              className="w-full bg-slate-800/60 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 outline-none focus:border-red-500/50 placeholder-slate-600 mb-4"
            />
            <div className="flex gap-3">
              <button
                onClick={() => { setShowDeleteModal(false); setDeletePassword(''); setDeleteError(''); }}
                className="flex-1 px-4 py-2 rounded-lg border border-slate-700 text-slate-400 text-xs font-semibold hover:border-slate-600 transition"
              >
                {lang === 'fr' ? 'Annuler' : 'Cancel'}
              </button>
              <button
                onClick={handleDeleteAccount}
                disabled={deleteLoading || !deletePassword}
                className="flex-1 flex items-center justify-center gap-2 bg-red-500/20 hover:bg-red-500/30 border border-red-500/30 text-red-400 px-4 py-2 rounded-lg text-xs font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {deleteLoading ? <RefreshCw size={12} className="animate-spin" /> : <Trash2 size={12} />}
                {lang === 'fr' ? 'Supprimer définitivement' : 'Delete permanently'}
              </button>
            </div>
          </div>
        </div>
      )}
      <PricingModal
        open={pricingModalOpen}
        onClose={() => setPricingModalOpen(false)}
      />
    </div>
  );
}
