// ─── Types pour ClientSpace ────────────────────────────────────────────────────

export interface MonitoredDomain {
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

export const CHECK_LABELS: { key: string; label: string }[] = [
  { key: 'ssl',        label: 'SSL' },
  { key: 'dns',        label: 'DNS' },
  { key: 'ports',      label: 'Ports' },
  { key: 'headers',    label: 'Headers' },
  { key: 'email',      label: 'Email' },
  { key: 'tech',       label: 'Tech' },
  { key: 'reputation', label: 'Réput.' },
];

export interface ScanHistoryItem {
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

export interface ScanFinding {
  category:         string;
  severity:         string;
  title?:           string;
  message?:         string;
  plain_explanation?: string;
  technical_detail?:  string;
  recommendation?:    string;
  penalty?:           number;
}

export interface ScanDetail {
  scan_uuid:       string;
  domain:          string;
  security_score:  number;
  risk_level:      string;
  findings:        ScanFinding[];
  created_at:      string;
  scan_duration:   number;
}

export type Tab = 'overview' | 'monitoring' | 'apps' | 'history' | 'settings' | 'developer';

export interface WebhookItem {
  id:            number;
  url:           string;
  events:        string[];
  is_active:     boolean;
  created_at:    string;
  last_fired_at: string | null;
  last_status:   number | null;
}

export interface VerifiedApp {
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

export interface AppScanFinding {
  category: string;
  severity: string;
  title?: string;
  technical_detail?: string;
  plain_explanation?: string;
  recommendation?: string;
  penalty?: number;
}

export interface DastFindingDetail {
  test_type: 'xss' | 'sqli' | 'csrf';
  severity: string;
  penalty: number;
  title: string;
  detail: string;
  evidence?: string | null;
  form_action?: string | null;
  field_name?: string | null;
}

export interface DastDetails {
  forms_found: number;
  forms_tested: number;
  error?: string | null;
  findings: DastFindingDetail[];
}

export interface SecretFindingDetail {
  pattern_name:   string;
  severity:       string;
  penalty:        number;
  description:    string;
  recommendation: string;
  matched_value:  string;
  source_url:     string;
  context:        string;
}

export interface SecretDetails {
  scripts_found:   number;
  scripts_scanned: number;
  error?:          string | null;
  findings:        SecretFindingDetail[];
}
