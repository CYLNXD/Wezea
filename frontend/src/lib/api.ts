// ─── CyberHealth Scanner — API Client ─────────────────────────────────────────
import axios, { AxiosError } from 'axios';
import type { ScanResult } from '../types/scanner';

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

// ── Type : quota hebdomadaire ─────────────────────────────────────────────────
export interface RateLimitInfo {
  type:      'anonymous' | 'free' | 'unlimited';
  limit:     number | null;
  used:      number;
  remaining: number | null;
  day_key:   string;
}

export const apiClient = axios.create({
  baseURL:         BASE_URL,
  timeout:         60_000,  // 60s — les scans de ports peuvent être longs
  headers:         { 'Content-Type': 'application/json' },
  withCredentials: true,    // envoie le cookie wezea_cid (HttpOnly) cross-origin
});

// Injecter le token JWT automatiquement
apiClient.interceptors.request.use(config => {
  const token = localStorage.getItem('wezea_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

/**
 * À appeler une fois au démarrage de l'app.
 * Déclenche GET /client-id → le backend pose un cookie HttpOnly `wezea_cid`
 * si ce n'est pas déjà fait. Ce cookie sert à identifier les visiteurs anonymes
 * de façon sécurisée (non spoofable depuis JS).
 */
export async function initClientId(): Promise<void> {
  try {
    await apiClient.get('/client-id');
  } catch {
    // Silencieux — le fallback IP prend le relais si le cookie échoue
  }
}

// ── Endpoints ─────────────────────────────────────────────────────────────────

export async function scanDomain(domain: string, lang: string = 'fr'): Promise<ScanResult> {
  const { data } = await apiClient.post<ScanResult>('/scan', { domain, lang });
  return data;
}

export async function requestFullReport(payload: {
  domain:      string;
  email:       string;
  first_name?: string;
  last_name?:  string;
  company?:    string;
  scan_data?:  Record<string, unknown> | null;
}): Promise<{ lead_id: string; scan_id?: string; message: string }> {
  const { data } = await apiClient.post('/report/request', payload);
  return data;
}

/**
 * Génère le rapport PDF et retourne un Blob téléchargeable.
 * Envoie le JSON complet du scan à POST /generate-pdf.
 */
export async function generatePDF(scanResult: ScanResult, lang: string = 'fr'): Promise<Blob> {
  const response = await apiClient.post('/generate-pdf', { ...scanResult, lang }, {
    responseType: 'blob',
    timeout:      90_000,   // WeasyPrint peut nécessiter plus de temps
  });
  return new Blob([response.data], { type: 'application/pdf' });
}

/**
 * Déclenche le téléchargement navigateur d'un Blob PDF.
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url  = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href     = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

// ── Récupérer le quota hebdomadaire ───────────────────────────────────────────

export async function getScanLimits(): Promise<RateLimitInfo> {
  const { data } = await apiClient.get<RateLimitInfo>('/scan/limits');
  return data;
}

// ── Error helpers ─────────────────────────────────────────────────────────────

export function extractApiError(err: unknown): string {
  if (err instanceof AxiosError) {
    const detail = err.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (detail?.message) return detail.message;
    if (err.response?.status === 422) return 'Domaine invalide. Vérifiez le format (ex: exemple.fr).';
    if (err.response?.status === 429) return detail?.message ?? "Limite de scans atteinte pour aujourd'hui.";
    if (err.code === 'ECONNABORTED') return 'Le scan a pris trop de temps. Réessayez.';
  }
  return 'Erreur inattendue. Veuillez réessayer.';
}

/** Extrait les infos de rate limit d'une erreur 429. */
export function extractRateLimitDetail(err: unknown): (RateLimitInfo & { message?: string }) | null {
  if (err instanceof AxiosError && err.response?.status === 429) {
    const detail = err.response?.data?.detail;
    if (detail?.limit !== undefined) {
      return detail as RateLimitInfo & { message?: string };
    }
  }
  return null;
}

// ── White-label API ───────────────────────────────────────────────────────────

export interface WhiteLabelSettings {
  enabled:       boolean;
  company_name:  string | null;
  primary_color: string | null;
  has_logo:      boolean;
  logo_b64:      string | null;
}

export async function getWhiteLabel(): Promise<WhiteLabelSettings> {
  const { data } = await apiClient.get<WhiteLabelSettings>('/auth/white-label');
  return data;
}

export async function updateWhiteLabel(payload: {
  enabled?:       boolean;
  company_name?:  string;
  primary_color?: string;
}): Promise<WhiteLabelSettings> {
  const { data } = await apiClient.patch<WhiteLabelSettings>('/auth/white-label', payload);
  return data;
}

export async function uploadWhiteLabelLogo(file: File): Promise<{ has_logo: boolean; size_kb: number }> {
  const form = new FormData();
  form.append('file', file);
  // Utiliser fetch natif : apiClient a un default 'Content-Type: application/json'
  // qui écrase le multipart/form-data nécessaire pour l'upload.
  // fetch() laisse le browser gérer automatiquement la boundary multipart.
  const token = localStorage.getItem('wezea_token');
  const res = await fetch(`${BASE_URL}/auth/white-label/logo`, {
    method:  'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body:    form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    // eslint-disable-next-line @typescript-eslint/no-throw-literal
    throw { response: { data: err } };
  }
  return res.json();
}

export async function deleteWhiteLabelLogo(): Promise<void> {
  await apiClient.delete('/auth/white-label/logo');
}
