// ─── ClientSpace.tsx — Espace Client Pro ──────────────────────────────────────
//
// 4 onglets :
//   overview    → KPIs globaux + cartes domaines avec sparklines
//   monitoring  → CRUD domaines + seuil d'alerte éditable inline
//   history     → Historique des scans avec graphique + filtres par domaine
//   settings    → Profil & Sécurité, Facturation, Zone dangereuse
//
import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Globe, Shield, FileDown,
  BarChart2, Trash2, RefreshCw, X,
  AlertTriangle,
  Settings, Code,
  AppWindow, BookOpen,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { apiClient, getWhiteLabel } from '../lib/api';
import type { WhiteLabelSettings } from '../lib/api';
import { useLanguage } from '../i18n/LanguageContext';
import PricingModal from '../components/PricingModal';
import PageNavbar from '../components/PageNavbar';
import SkuIcon from '../components/SkuIcon';
import OverviewTab from '../components/clientspace/OverviewTab';
import AppsTab from '../components/clientspace/AppsTab';
import MonitoringTab from '../components/clientspace/MonitoringTab';
import HistoryTab from '../components/clientspace/HistoryTab';
import DeveloperTab from '../components/clientspace/DeveloperTab';
import SettingsTab from '../components/clientspace/SettingsTab';
import ComplianceDashboard from '../components/ComplianceDashboard';

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

type Tab = 'overview' | 'monitoring' | 'conformite' | 'apps' | 'history' | 'settings' | 'developer';

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

// ─────────────────────────────────────────────────────────────────────────────
// Wrapper — Conformité avec sélecteur de domaine
// ─────────────────────────────────────────────────────────────────────────────

function ComplianceTabWrapper({ domains, userPlan, lang }: {
  domains: MonitoredDomain[];
  userPlan: string;
  lang: string;
}) {
  const [selectedDomain, setSelectedDomain] = useState(domains[0]?.domain ?? '');

  if (domains.length === 0) {
    return (
      <div className="text-center py-16">
        <SkuIcon color="#818cf8" size={52}>
          <BookOpen size={24} className="text-indigo-300" />
        </SkuIcon>
        <p className="text-slate-400 mt-4 text-sm">
          {lang === 'fr'
            ? 'Ajoutez un domaine dans l\'onglet Monitoring pour accéder au rapport de conformité.'
            : 'Add a domain in the Monitoring tab to access the compliance report.'}
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {domains.length > 1 && (
        <select
          value={selectedDomain}
          onChange={e => setSelectedDomain(e.target.value)}
          className="sku-inset text-sm w-full max-w-xs"
        >
          {domains.map(d => (
            <option key={d.domain} value={d.domain}>{d.domain}</option>
          ))}
        </select>
      )}
      <ComplianceDashboard domain={selectedDomain} userPlan={userPlan} />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Composant principal
// ─────────────────────────────────────────────────────────────────────────────

export default function ClientSpace() {
  const { tab: routeTab } = useParams<{ tab?: string }>();
  const VALID_TABS: Tab[] = ['overview', 'monitoring', 'conformite', 'apps', 'history', 'settings', 'developer'];
  const initialTab = (routeTab && VALID_TABS.includes(routeTab as Tab) ? routeTab : undefined) as Tab | undefined;
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
  const [settingsSection, setSettingsSection] = useState<'profile' | 'billing' | 'whitelabel' | 'danger'>('profile');

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

  // Badge counts for tabs
  const monitoringAlertCount = domains.filter(d =>
    d.is_active && (
      d.last_risk_level === 'CRITICAL' ||
      d.last_risk_level === 'HIGH' ||
      (d.last_ssl_expiry_days !== null && d.last_ssl_expiry_days <= 14)
    )
  ).length;

  const tabs: { id: Tab; label: string; icon: JSX.Element; badge?: number }[] = [
    { id: 'overview',   label: lang === 'fr' ? 'Vue d\'ensemble' : 'Overview', icon: <BarChart2 size={14} /> },
    { id: 'monitoring', label: lang === 'fr' ? 'Monitoring' : 'Monitoring',    icon: <Globe size={14} />, badge: monitoringAlertCount },
    { id: 'conformite', label: lang === 'fr' ? 'Conformité' : 'Compliance',  icon: <BookOpen size={14} /> },
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
        title={lang === 'fr' ? 'Mon espace' : 'My space'}
        icon={<Shield size={14} />}
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
              {(t.badge ?? 0) > 0 && (
                <span className="ml-1 min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-[10px] font-bold text-white flex items-center justify-center">
                  {t.badge}
                </span>
              )}
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

              {tab === 'overview' && (
                <OverviewTab
                  domains={domains}
                  planLimit={planLimit}
                  avgScore={avgScore}
                  criticalDomains={criticalDomains}
                  totalOpenFindings={totalOpenFindings}
                  historyByDomain={historyByDomain}
                  setTab={setTab}
                  lang={lang}
                />
              )}

              {/* ══════════════════════════════════════════════════════════════
                  TAB — APPLICATIONS (Application Scanning)
              ══════════════════════════════════════════════════════════════ */}
              {tab === 'apps' && (
                <AppsTab
                  apps={apps}
                  appNewName={appNewName}
                  setAppNewName={setAppNewName}
                  appNewUrl={appNewUrl}
                  setAppNewUrl={setAppNewUrl}
                  appNewMethod={appNewMethod}
                  setAppNewMethod={setAppNewMethod}
                  appAddLoading={appAddLoading}
                  appAddError={appAddError}
                  setAppAddError={setAppAddError}
                  appVerifyLoading={appVerifyLoading}
                  appVerifyMsg={appVerifyMsg}
                  appScanLoading={appScanLoading}
                  appScanResults={appScanResults}
                  appScanDetails={appScanDetails}
                  appExpandedId={appExpandedId}
                  setAppExpandedId={setAppExpandedId}
                  appVerifyInfo={appVerifyInfo}
                  setAppVerifyInfo={setAppVerifyInfo}
                  handleAddApp={handleAddApp}
                  handleDeleteApp={handleDeleteApp}
                  handleVerifyApp={handleVerifyApp}
                  handleScanApp={handleScanApp}
                  lang={lang}
                />
              )}

              {/* ══════════════════════════════════════════════════════════════
                  TAB 2 — MONITORING
              ══════════════════════════════════════════════════════════════ */}
              {tab === 'monitoring' && (
                <MonitoringTab
                  domains={domains}
                  isPremium={isPremium}
                  planLimit={planLimit}
                  userPlan={user?.plan}
                  newDomain={newDomain}
                  setNewDomain={setNewDomain}
                  addError={addError}
                  setAddError={setAddError}
                  addLoading={addLoading}
                  newDomainChecks={newDomainChecks}
                  setNewDomainChecks={setNewDomainChecks}
                  newDomainFrequency={newDomainFrequency}
                  setNewDomainFrequency={setNewDomainFrequency}
                  newDomainEmailReport={newDomainEmailReport}
                  setNewDomainEmailReport={setNewDomainEmailReport}
                  editingThreshold={editingThreshold}
                  setEditingThreshold={setEditingThreshold}
                  thresholdValue={thresholdValue}
                  setThresholdValue={setThresholdValue}
                  pendingChecks={pendingChecks}
                  checksLoading={checksLoading}
                  scanningDomain={scanningDomain}
                  scanDoneMap={scanDoneMap}
                  historyByDomain={historyByDomain}
                  addDomain={addDomain}
                  removeDomain={removeDomain}
                  scanDomainNow={scanDomainNow}
                  saveThreshold={saveThreshold}
                  toggleCheck={toggleCheck}
                  setDomains={setDomains}
                  setPricingModalOpen={setPricingModalOpen}
                  lang={lang}
                />
              )}

              {/* ══════════════════════════════════════════════════════════════
                  TAB — CONFORMITÉ NIS2/RGPD
              ══════════════════════════════════════════════════════════════ */}
              {tab === 'conformite' && (
                <ComplianceTabWrapper
                  domains={domains}
                  userPlan={user?.plan ?? 'free'}
                  lang={lang}
                />
              )}

              {/* ══════════════════════════════════════════════════════════════
                  TAB 3 — HISTORIQUE
              ══════════════════════════════════════════════════════════════ */}
              {tab === 'history' && (
                <HistoryTab
                  domains={domains}
                  history={history}
                  filteredHistory={filteredHistory}
                  historyByDomain={historyByDomain}
                  historyDomain={historyDomain}
                  setHistoryDomain={setHistoryDomain}
                  isPremium={isPremium}
                  pdfLoading={pdfLoading}
                  exportLoading={exportLoading}
                  shareLoading={shareLoading}
                  shareCopied={shareCopied}
                  scanModalLoading={scanModalLoading}
                  generatePdf={generatePdf}
                  exportScan={exportScan}
                  toggleShare={toggleShare}
                  openScanModal={openScanModal}
                  lang={lang}
                />
              )}

              {/* ══════════════════════════════════════════════════════════════
                  TAB 5 — DÉVELOPPEUR (Pro/Team uniquement)
              ══════════════════════════════════════════════════════════════ */}
              {tab === 'developer' && (
                <DeveloperTab
                  user={user}
                  domains={domains}
                  webhooks={webhooks}
                  whLoading={whLoading}
                  whNewUrl={whNewUrl}
                  setWhNewUrl={setWhNewUrl}
                  whNewEvents={whNewEvents}
                  setWhNewEvents={setWhNewEvents}
                  whNewSecret={whNewSecret}
                  setWhNewSecret={setWhNewSecret}
                  whAddLoading={whAddLoading}
                  whAddError={whAddError}
                  whCreatedSecret={whCreatedSecret}
                  setWhCreatedSecret={setWhCreatedSecret}
                  whTestLoading={whTestLoading}
                  whTestResult={whTestResult}
                  addWebhook={addWebhook}
                  deleteWebhook={deleteWebhook}
                  testWebhook={testWebhook}
                  apiKeyVisible={apiKeyVisible}
                  setApiKeyVisible={setApiKeyVisible}
                  apiKeyLoading={apiKeyLoading}
                  apiKeyCopied={apiKeyCopied}
                  apiKeyMsg={apiKeyMsg}
                  regenerateApiKey={regenerateApiKey}
                  copyApiKey={copyApiKey}
                  slackUrl={slackUrl}
                  setSlackUrl={setSlackUrl}
                  teamsUrl={teamsUrl}
                  setTeamsUrl={setTeamsUrl}
                  integrLoading={integrLoading}
                  setIntegrLoading={setIntegrLoading}
                  integrMsg={integrMsg}
                  setIntegrMsg={setIntegrMsg}
                  integrConfigured={integrConfigured}
                  setIntegrConfigured={setIntegrConfigured}
                  ALLOWED_EVENTS={ALLOWED_EVENTS}
                  lang={lang}
                />
              )}

              {/* ══════════════════════════════════════════════════════════════
                  TAB 4 — PARAMÈTRES
              ══════════════════════════════════════════════════════════════ */}
              {tab === 'settings' && (
                <SettingsTab
                  user={user}
                  settingsSection={settingsSection}
                  setSettingsSection={setSettingsSection}
                  isPremium={isPremium}
                  lang={lang}
                  newEmail={newEmail}
                  setNewEmail={setNewEmail}
                  emailPassword={emailPassword}
                  setEmailPassword={setEmailPassword}
                  emailLoading={emailLoading}
                  emailMsg={emailMsg}
                  handleChangeEmail={handleChangeEmail}
                  currentPwd={currentPwd}
                  setCurrentPwd={setCurrentPwd}
                  newPwd={newPwd}
                  setNewPwd={setNewPwd}
                  confirmPwd={confirmPwd}
                  setConfirmPwd={setConfirmPwd}
                  pwdLoading={pwdLoading}
                  pwdMsg={pwdMsg}
                  handleChangePassword={handleChangePassword}
                  mfaStep={mfaStep}
                  setMfaStep={setMfaStep}
                  mfaQrCode={mfaQrCode}
                  mfaSecret={mfaSecret}
                  mfaCode={mfaCode}
                  setMfaCode={setMfaCode}
                  mfaDisablePwd={mfaDisablePwd}
                  setMfaDisablePwd={setMfaDisablePwd}
                  mfaLoading={mfaLoading}
                  mfaMsg={mfaMsg}
                  setMfaMsg={setMfaMsg}
                  handleMfaSetup={handleMfaSetup}
                  handleMfaVerify={handleMfaVerify}
                  handleMfaDisable={handleMfaDisable}
                  portalLoading={portalLoading}
                  handlePortal={handlePortal}
                  wb={wb}
                  setWb={setWb}
                  wbLoading={wbLoading}
                  wbSaving={wbSaving}
                  setWbSaving={setWbSaving}
                  wbMsg={wbMsg}
                  setWbMsg={setWbMsg}
                  wbName={wbName}
                  setWbName={setWbName}
                  wbColor={wbColor}
                  setWbColor={setWbColor}
                  wbEnabled={wbEnabled}
                  setWbEnabled={setWbEnabled}
                  wbLogoUploading={wbLogoUploading}
                  setWbLogoUploading={setWbLogoUploading}
                  setShowDeleteModal={setShowDeleteModal}
                />
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
