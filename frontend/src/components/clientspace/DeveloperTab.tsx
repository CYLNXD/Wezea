// ─── DeveloperTab — API Key, Badge, Webhooks, Integrations ─────────────────────
import React from 'react';
import {
  Key, Shield, Copy, RefreshCw, Plus, Webhook, ExternalLink,
  Check, AlertTriangle, Bell, Trash2, Clock, Link2, MessageSquare,
} from 'lucide-react';
import SkuIcon from '../SkuIcon';
import { apiClient } from '../../lib/api';
import type { MonitoredDomain, WebhookItem } from './types';

// ─── Props ──────────────────────────────────────────────────────────────────────

export interface DeveloperTabProps {
  user: any;
  domains: MonitoredDomain[];
  webhooks: WebhookItem[];
  whLoading: boolean;
  whNewUrl: string;
  setWhNewUrl: (v: string) => void;
  whNewEvents: string[];
  setWhNewEvents: React.Dispatch<React.SetStateAction<string[]>>;
  whNewSecret: string;
  setWhNewSecret: (v: string) => void;
  whAddLoading: boolean;
  whAddError: string;
  whCreatedSecret: string | null;
  setWhCreatedSecret: (v: string | null) => void;
  whTestLoading: number | null;
  whTestResult: Record<number, { ok: boolean; status: number }>;
  addWebhook: () => void;
  deleteWebhook: (id: number) => void;
  testWebhook: (id: number) => void;
  apiKeyVisible: boolean;
  setApiKeyVisible: (v: boolean) => void;
  apiKeyLoading: boolean;
  apiKeyCopied: boolean;
  apiKeyMsg: { type: 'ok' | 'err'; text: string } | null;
  regenerateApiKey: () => void;
  copyApiKey: () => void;
  slackUrl: string;
  setSlackUrl: (v: string) => void;
  teamsUrl: string;
  setTeamsUrl: (v: string) => void;
  integrLoading: boolean;
  setIntegrLoading: (v: boolean) => void;
  integrMsg: { type: 'ok' | 'err'; text: string } | null;
  setIntegrMsg: (v: { type: 'ok' | 'err'; text: string } | null) => void;
  integrConfigured: { slack: boolean; teams: boolean };
  setIntegrConfigured: React.Dispatch<React.SetStateAction<{ slack: boolean; teams: boolean }>>;
  ALLOWED_EVENTS: string[];
  lang: 'fr' | 'en';
}

// ─── Component ──────────────────────────────────────────────────────────────────

export default function DeveloperTab({
  user,
  domains,
  webhooks,
  whLoading,
  whNewUrl, setWhNewUrl,
  whNewEvents, setWhNewEvents,
  whNewSecret, setWhNewSecret,
  whAddLoading,
  whAddError,
  whCreatedSecret, setWhCreatedSecret,
  whTestLoading,
  whTestResult,
  addWebhook,
  deleteWebhook,
  testWebhook,
  apiKeyVisible, setApiKeyVisible,
  apiKeyLoading,
  apiKeyCopied,
  apiKeyMsg,
  regenerateApiKey,
  copyApiKey,
  slackUrl, setSlackUrl,
  teamsUrl, setTeamsUrl,
  integrLoading, setIntegrLoading,
  integrMsg, setIntegrMsg,
  integrConfigured, setIntegrConfigured,
  ALLOWED_EVENTS,
  lang,
}: DeveloperTabProps) {
  return (
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
                onClick={() => setApiKeyVisible(!apiKeyVisible)}
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
  );
}
