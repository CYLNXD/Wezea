// ─── CyberHealth Scanner — useScanner Hook ────────────────────────────────────
//
// Gère :
//   1. L'appel API réel (POST /scan)
//   2. La simulation des logs de console (pour l'UX — indépendante de l'API)
//   3. La synchronisation : on attend que LES DEUX soient terminés avant d'afficher
//
import { useState, useCallback, useRef } from 'react';
import { scanDomain, extractApiError, extractRateLimitDetail, apiClient } from '../lib/api';
import type { RateLimitInfo } from '../lib/api';
import type { ConsoleLog, ScanResult, ScanStatus } from '../types/scanner';

// ── Séquence de simulation des logs ──────────────────────────────────────────

interface SimStep {
  message:  string;
  delay:    number;   // ms depuis le début
  type:     ConsoleLog['type'];
}

const buildSimSteps = (domain: string, lang: string = 'fr'): SimStep[] => {
  const fr: SimStep[] = [
    { delay: 0,    type: 'system',  message: `Wezea Security Scanner — cible : ${domain}` },
    { delay: 180,  type: 'info',    message: `→ Résolution DNS de ${domain}...` },
    { delay: 420,  type: 'info',    message: '→ Interrogation des serveurs de noms autoritaires...' },
    { delay: 720,  type: 'info',    message: '→ Recherche de l\'enregistrement SPF (TXT)...' },
    { delay: 1050, type: 'info',    message: '→ Vérification de la politique DMARC (_dmarc)...' },
    { delay: 1380, type: 'info',    message: '→ Initiation du handshake TLS sur le port 443...' },
    { delay: 1650, type: 'info',    message: '→ Extraction du certificat X.509...' },
    { delay: 1900, type: 'info',    message: '→ Vérification de la chaîne de certification (CA)...' },
    { delay: 2150, type: 'info',    message: '→ Négociation de la version TLS...' },
    { delay: 2450, type: 'warning', message: '→ Scan TCP des ports critiques [21, 22, 23, 80, 443, 445, 3306, 3389, 5432]...' },
    { delay: 2750, type: 'warning', message: '→ Test d\'exposition RDP (Port 3389) — vecteur ransomware #1...' },
    { delay: 3050, type: 'warning', message: '→ Test d\'exposition SMB (Port 445) — vecteur WannaCry/NotPetya...' },
    { delay: 3300, type: 'warning', message: '→ Test d\'accès aux bases de données (3306/5432)...' },
    { delay: 3550, type: 'warning', message: '→ Détection des protocoles obsolètes (FTP/Telnet)...' },
    { delay: 3800, type: 'info',    message: '→ Agrégation des findings de sécurité...' },
    { delay: 4050, type: 'info',    message: '→ Application du moteur de scoring (base 100)...' },
    { delay: 4300, type: 'info',    message: '→ Génération du rapport JSON...' },
  ];
  const en: SimStep[] = [
    { delay: 0,    type: 'system',  message: `Wezea Security Scanner — target: ${domain}` },
    { delay: 180,  type: 'info',    message: `→ Resolving DNS for ${domain}...` },
    { delay: 420,  type: 'info',    message: '→ Querying authoritative name servers...' },
    { delay: 720,  type: 'info',    message: '→ Looking up SPF record (TXT)...' },
    { delay: 1050, type: 'info',    message: '→ Checking DMARC policy (_dmarc)...' },
    { delay: 1380, type: 'info',    message: '→ Initiating TLS handshake on port 443...' },
    { delay: 1650, type: 'info',    message: '→ Extracting X.509 certificate...' },
    { delay: 1900, type: 'info',    message: '→ Verifying certificate chain (CA)...' },
    { delay: 2150, type: 'info',    message: '→ Negotiating TLS version...' },
    { delay: 2450, type: 'warning', message: '→ TCP scan of critical ports [21, 22, 23, 80, 443, 445, 3306, 3389, 5432]...' },
    { delay: 2750, type: 'warning', message: '→ Testing RDP exposure (Port 3389) — ransomware vector #1...' },
    { delay: 3050, type: 'warning', message: '→ Testing SMB exposure (Port 445) — WannaCry/NotPetya vector...' },
    { delay: 3300, type: 'warning', message: '→ Testing database access (3306/5432)...' },
    { delay: 3550, type: 'warning', message: '→ Detecting obsolete protocols (FTP/Telnet)...' },
    { delay: 3800, type: 'info',    message: '→ Aggregating security findings...' },
    { delay: 4050, type: 'info',    message: '→ Applying scoring engine (base 100)...' },
    { delay: 4300, type: 'info',    message: '→ Generating JSON report...' },
  ];
  return lang === 'en' ? en : fr;
};

const SIMULATION_TOTAL_MS = 4800; // durée totale de la simulation

// ── Types exportés ────────────────────────────────────────────────────────────

export interface ScannerState {
  status:          ScanStatus;
  result:          ScanResult | null;
  error:           string | null;
  rateLimitData:   (RateLimitInfo & { message?: string }) | null;
  consoleLogs:     ConsoleLog[];
  progress:        number;  // 0–100
}

export interface ScannerActions {
  startScan:       (domain: string, lang?: string) => Promise<void>;
  loadFromHistory: (scanUuid: string) => Promise<void>;
  reset:           () => void;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

let logCounter = 0;
function makeLog(message: string, type: ConsoleLog['type'], lang: string = 'fr'): ConsoleLog {
  return {
    id:        `log-${++logCounter}`,
    message,
    type,
    timestamp: new Date().toLocaleTimeString(lang === 'en' ? 'en-GB' : 'fr-FR', { hour12: false }),
  };
}

// ── Hook principal ────────────────────────────────────────────────────────────

export function useScanner(): ScannerState & ScannerActions {
  const [state, setState] = useState<ScannerState>({
    status:        'idle',
    result:        null,
    error:         null,
    rateLimitData: null,
    consoleLogs:   [],
    progress:      0,
  });

  // Refs pour les timers — nettoyage si reset()
  const timersRef  = useRef<ReturnType<typeof setTimeout>[]>([]);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearAllTimers = () => {
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  };

  const appendLog = useCallback((log: ConsoleLog) => {
    setState(prev => ({
      ...prev,
      consoleLogs: [...prev.consoleLogs, log],
    }));
  }, []);

  const startScan = useCallback(async (domain: string, lang: string = 'fr') => {
    clearAllTimers();
    logCounter = 0;

    // Réinitialiser l'état
    setState({
      status:        'scanning',
      result:        null,
      error:         null,
      rateLimitData: null,
      consoleLogs:   [],
      progress:      0,
    });

    const steps = buildSimSteps(domain, lang);

    // ── 1. Lancer la simulation des logs (indépendante de l'API) ─────────────
    steps.forEach((step) => {
      const t = setTimeout(() => {
        appendLog(makeLog(step.message, step.type, lang));
      }, step.delay);
      timersRef.current.push(t);
    });

    // ── 2. Progress bar (se remplit sur SIMULATION_TOTAL_MS) ─────────────────
    const startTime = Date.now();
    intervalRef.current = setInterval(() => {
      const elapsed  = Date.now() - startTime;
      const progress = Math.min(95, Math.round((elapsed / SIMULATION_TOTAL_MS) * 95));
      setState(prev => ({ ...prev, progress }));
    }, 60);

    // ── 3. Appel API réel (parallèle) ─────────────────────────────────────────
    let apiResult:     ScanResult | null                             = null;
    let apiError:      string | null                                 = null;
    let apiRateLimit:  (RateLimitInfo & { message?: string }) | null = null;

    try {
      apiResult = await scanDomain(domain, lang);
    } catch (err) {
      apiError     = extractApiError(err);
      apiRateLimit = extractRateLimitDetail(err);
    }

    // ── 4. Attendre que la simulation soit terminée avant d'afficher ──────────
    const elapsed = Date.now() - startTime;
    const remaining = Math.max(0, SIMULATION_TOTAL_MS - elapsed);

    setTimeout(() => {
      clearAllTimers();

      if (apiError || !apiResult) {
        appendLog(makeLog(
          lang === 'en'
            ? `✗ Error: ${apiError ?? 'Invalid response'}`
            : `✗ Erreur : ${apiError ?? 'Réponse invalide'}`,
          'error', lang
        ));
        setState(prev => ({
          ...prev,
          status:        'error',
          error:         apiError,
          rateLimitData: apiRateLimit,
          progress:      0,
        }));
        return;
      }

      // Log de fin contextuel
      const score = apiResult.security_score;
      const finalType: ConsoleLog['type'] =
        score >= 70 ? 'success' : score >= 40 ? 'warning' : 'error';
      const finalMsg = lang === 'en'
        ? (score >= 70
          ? `✓ Scan complete — SecurityScore: ${score}/100 — Level: ${apiResult.risk_level}`
          : `⚠ Scan complete — CRITICAL SecurityScore: ${score}/100 — ${apiResult.findings.length} vulnerability(ies) detected`)
        : (score >= 70
          ? `✓ Scan terminé — SecurityScore : ${score}/100 — Niveau : ${apiResult.risk_level}`
          : `⚠ Scan terminé — SecurityScore CRITIQUE : ${score}/100 — ${apiResult.findings.length} vulnérabilité(s) détectée(s)`);

      appendLog(makeLog(finalMsg, finalType, lang));

      setState(prev => ({
        ...prev,
        status:   'success',
        result:   apiResult,
        progress: 100,
      }));
    }, remaining + 200); // 200ms de marge pour le dernier log

  }, [appendLog]);

  const reset = useCallback(() => {
    clearAllTimers();
    setState({
      status:        'idle',
      result:        null,
      error:         null,
      rateLimitData: null,
      consoleLogs:   [],
      progress:      0,
    });
  }, []);

  // ── Charge un scan existant depuis l'historique (sans simulation) ──────────
  // Mappings API → ScanResult :
  //   scan_uuid      → scan_id
  //   created_at     → scanned_at
  //   scan_duration  → scan_duration_ms (×1000)
  const loadFromHistory = useCallback(async (scanUuid: string) => {
    clearAllTimers();
    setState(prev => ({ ...prev, status: 'scanning', result: null, error: null, consoleLogs: [], progress: 50 }));
    try {
      const { data } = await apiClient.get(`/scans/history/${scanUuid}`);
      const result: ScanResult = {
        scan_id:           data.scan_uuid,
        domain:            data.domain,
        scanned_at:        data.created_at,
        security_score:    data.security_score,
        risk_level:        data.risk_level,
        findings:          data.findings ?? [],
        dns_details:       data.dns_details      ?? {},
        ssl_details:       data.ssl_details      ?? {},
        port_details:      data.port_details      ?? {},
        recommendations:   data.recommendations   ?? [],
        scan_duration_ms:  (data.scan_duration ?? 0) * 1000,
        subdomain_details: data.subdomain_details ?? {},
        vuln_details:      data.vuln_details      ?? {},
        meta:              {},
      };
      setState(prev => ({ ...prev, status: 'success', result, progress: 100 }));
    } catch {
      setState(prev => ({
        ...prev,
        status: 'error',
        error:  'Impossible de charger ce scan.',
        progress: 0,
      }));
    }
  }, []);

  return { ...state, startScan, loadFromHistory, reset };
}
