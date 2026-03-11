// ─── CyberHealth Scanner — Shared TypeScript Types ────────────────────────────

export type ScanStatus = 'idle' | 'scanning' | 'success' | 'error';

export type Severity  = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO';
export type RiskLevel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';

export interface Finding {
  category:           string;
  severity:           Severity;
  // Format original (DNS/SSL/Ports)
  title?:             string;
  technical_detail?:  string;
  plain_explanation?: string;
  penalty?:           number;
  // Format extra checks (En-têtes HTTP / Email / Tech / Réputation)
  message?:           string;
  // Commun aux deux
  recommendation:     string;
  // Premium finding (détails masqués pour les plans gratuits)
  is_premium?:        boolean;
}

export interface PortDetail {
  service:  string;
  open:     boolean;
  severity: string;
}

export interface SubdomainInfo {
  subdomain:  string;
  ip:         string | null;
  active:     boolean;
}

export interface CertInfo {
  subdomain:   string;
  expires_at:  string | null;
  days_left:   number;
  expired:     boolean;
  expiring_soon: boolean;
  error?:      string;
}

export interface SubdomainDetails {
  subdomains:    SubdomainInfo[];
  expired_certs: CertInfo[];
  expiring_soon: CertInfo[];
  orphaned:      string[];
  total_found:   number;
}

export interface VulnDetails {
  server_header:   string;
  powered_by:      string;
  detected_stack:  Array<{ tech: string; version: string }>;
}

export interface ScanResult {
  scan_id:           string;
  domain:            string;
  scanned_at:        string;
  security_score:    number;
  risk_level:        RiskLevel;
  findings:          Finding[];
  dns_details:       Record<string, unknown>;
  ssl_details:       Record<string, unknown>;
  port_details:      Record<string, PortDetail>;
  recommendations:   string[];
  scan_duration_ms:  number;
  meta:              Record<string, unknown>;
  // Champs premium
  subdomain_details: SubdomainDetails | Record<string, never>;
  vuln_details:      VulnDetails      | Record<string, never>;
  breach_details?:   BreachDetails;
  typosquat_details?: TyposquatDetails;
  ct_details?:        CtDetails;
  // Conformité réglementaire — tous plans
  compliance?:       ComplianceData;
}

export interface ComplianceArticle {
  code:           string;
  framework:      'NIS2' | 'RGPD';
  title:          string;
  title_en:       string;
  description:    string;
  description_en: string;
  compliant:      boolean;
  triggered_by:   string[];
}

export interface ComplianceData {
  nis2_score:    number;
  rgpd_score:    number;
  overall_level: 'conforme' | 'partiel' | 'non_conforme';
  nis2:          ComplianceArticle[];
  rgpd:          ComplianceArticle[];
}

export interface BreachDetails {
  status:        'clean' | 'breached' | 'no_api_key';
  breach_count?: number;
  breach_names?: string[];
}

export interface TyposquatHit {
  domain:       string;
  variant_type: 'tld' | 'missing' | 'double' | 'transposition' | 'homoglyph' | 'keyboard';
  ip:           string;
}

export interface TyposquatDetails {
  status:    'clean' | 'squatted';
  checked:   number;
  hit_count: number;
  hits:      TyposquatHit[];
}

export interface CtCertRecord {
  common_name: string;
  name_value:  string;
  issuer:      string;
  logged_at:   string;
  not_before:  string;
  not_after:   string;
}

export interface CtDetails {
  status:         'no_data' | 'certs_found';
  total_found:    number;
  recent_7days:   number;
  recent_30days:  number;
  wildcard_count: number;
  issuers:        string[];
  recent_certs:   CtCertRecord[];
  wildcard_certs: CtCertRecord[];
}

export interface ConsoleLog {
  id:        string;
  message:   string;
  type:      'info' | 'success' | 'warning' | 'error' | 'system';
  timestamp: string;
}

// Couleurs Tailwind par sévérité
export const SEVERITY_CONFIG: Record<Severity, {
  border: string; bg: string; text: string; badge: string; icon: string;
}> = {
  CRITICAL: {
    border: 'border-red-500/60',
    bg:     'bg-red-500/10',
    text:   'text-red-400',
    badge:  'bg-red-500/20 text-red-300 border border-red-500/40',
    icon:   'text-red-500',
  },
  HIGH: {
    border: 'border-orange-500/60',
    bg:     'bg-orange-500/10',
    text:   'text-orange-400',
    badge:  'bg-orange-500/20 text-orange-300 border border-orange-500/40',
    icon:   'text-orange-500',
  },
  MEDIUM: {
    border: 'border-yellow-500/60',
    bg:     'bg-yellow-500/10',
    text:   'text-yellow-400',
    badge:  'bg-yellow-500/20 text-yellow-300 border border-yellow-500/40',
    icon:   'text-yellow-500',
  },
  LOW: {
    border: 'border-green-500/60',
    bg:     'bg-green-500/10',
    text:   'text-green-400',
    badge:  'bg-green-500/20 text-green-300 border border-green-500/40',
    icon:   'text-green-500',
  },
  INFO: {
    border: 'border-blue-500/40',
    bg:     'bg-blue-500/5',
    text:   'text-blue-400',
    badge:  'bg-blue-500/20 text-blue-300 border border-blue-500/40',
    icon:   'text-blue-400',
  },
};

// Score → couleur de la jauge
export function scoreColor(score: number): {
  gauge: string; glow: string; label: string; textClass: string;
} {
  if (score >= 70) return {
    gauge:     '#22c55e',
    glow:      '0 0 30px rgba(34,197,94,0.5)',
    label:     'Bon',
    textClass: 'text-green-400',
  };
  if (score >= 40) return {
    gauge:     '#f97316',
    glow:      '0 0 30px rgba(249,115,22,0.5)',
    label:     'Risqué',
    textClass: 'text-orange-400',
  };
  return {
    gauge:     '#ef4444',
    glow:      '0 0 30px rgba(239,68,68,0.5)',
    label:     'Critique',
    textClass: 'text-red-400',
  };
}
