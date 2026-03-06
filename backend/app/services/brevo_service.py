"""
CyberHealth Scanner — Brevo (ex Sendinblue) Email Service
==========================================================
Toutes les fonctions d'envoi d'email transactionnel via l'API Brevo.

Fonctions exportées :
  Auth / compte
    send_welcome_email(email)
    add_registered_user_contact(email, first_name, last_name)
    update_brevo_contact(email, plan)
    delete_brevo_contact(email)

  Paiement / upgrade
    send_upgrade_email(email, plan)

  Onboarding
    send_activation_nudge_email(email)             J+1
    send_upgrade_nudge_email(email)                J+3
    send_value_reminder_email(email, scan_count)   J+7
    send_winback_email(email)                      J+14

  Monitoring
    send_monitoring_alert_email(email, first_name, domain, new_score,
                                prev_score, risk_level, reason, findings)
    send_pdf_email(email, domain, pdf_bytes, score, risk_level)

  Contact
    send_contact_notification(name, email, subject, message)
    send_contact_confirmation(name, email)
"""
from __future__ import annotations

import base64
import datetime
import html as _html
import logging
import os
from typing import Any


def _esc(value: str) -> str:
    """Échappe les caractères HTML dans les valeurs fournies par les utilisateurs."""
    return _html.escape(str(value), quote=True)

import httpx

logger = logging.getLogger("cyberhealth.brevo")

BREVO_API_KEY  = os.getenv("BREVO_API_KEY", "")
BREVO_API_URL  = "https://api.brevo.com/v3/smtp/email"
BREVO_CONTACTS = "https://api.brevo.com/v3/contacts"

SENDER       = {"name": "Wezea Security", "email": "noreply@wezea.net"}
FRONTEND_URL = "https://wezea.net"


# ─────────────────────────────────────────────────────────────────────────────
# Helper HTTP
# ─────────────────────────────────────────────────────────────────────────────

async def _send(payload: dict) -> bool:
    """Envoie un email via l'API Brevo. Retourne True si succès."""
    if not BREVO_API_KEY:
        logger.warning("BREVO_API_KEY manquant — email non envoyé : %s", payload.get("subject", "?"))
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                BREVO_API_URL,
                json=payload,
                headers={
                    "api-key":      BREVO_API_KEY,
                    "Content-Type": "application/json",
                },
            )
            if r.status_code not in (200, 201):
                logger.error("Brevo API error %s : %s", r.status_code, r.text[:200])
                return False
            return True
    except Exception as exc:
        logger.error("Brevo send error : %s", exc)
        return False


async def _contacts_request(method: str, url: str, **kwargs) -> bool:
    if not BREVO_API_KEY:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await getattr(client, method)(
                url,
                headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"},
                **kwargs,
            )
            return r.status_code in (200, 201, 204)
    except Exception as exc:
        logger.error("Brevo contacts error : %s", exc)
        return False


def _base_html(content: str) -> str:
    """Enveloppe HTML commune pour tous les emails Wezea."""
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <style>
    body {{
      margin:0; padding:0; background:#0d1117;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }}
    .wrap {{ max-width:600px; margin:0 auto; padding:32px 24px; }}
    .logo {{
      font-family:monospace; font-size:22px; font-weight:900; color:#22d3ee;
      letter-spacing:-0.5px; text-decoration:none;
    }}
    .logo span {{ color:#e2e8f0; }}
    .card {{
      background:#161b22; border:1px solid #30363d;
      border-radius:12px; padding:32px; margin-top:24px;
    }}
    h1 {{ color:#e2e8f0; font-size:20px; margin:0 0 16px; font-weight:700; }}
    p  {{ color:#94a3b8; font-size:14px; line-height:1.7; margin:0 0 14px; }}
    .btn {{
      display:inline-block; background:#22d3ee; color:#0d1117;
      font-weight:700; font-size:14px; padding:12px 28px;
      border-radius:8px; text-decoration:none; margin:8px 0;
    }}
    .score {{
      display:inline-block; font-family:monospace; font-size:36px;
      font-weight:900; color:#22d3ee;
    }}
    .risk-low      {{ color:#34d399; }}
    .risk-medium   {{ color:#fbbf24; }}
    .risk-high     {{ color:#f97316; }}
    .risk-critical {{ color:#ef4444; }}
    .panel {{
      background:#0d1117; border:1px solid #30363d; border-radius:8px;
      padding:16px; margin:16px 0;
    }}
    .panel p {{ margin:4px 0; font-size:13px; }}
    .label {{ color:#64748b; font-size:12px; font-family:monospace; }}
    .finding {{
      background:#1c2128; border-left:3px solid #ef4444;
      border-radius:4px; padding:8px 12px; margin:8px 0;
      color:#fca5a5; font-size:13px; font-family:monospace;
    }}
    .footer {{ margin-top:32px; text-align:center; color:#475569; font-size:12px; }}
    .footer a {{ color:#475569; }}
  </style>
</head>
<body>
  <div class="wrap">
    <a href="{FRONTEND_URL}" class="logo">We<span>zea</span></a>
    {content}
    <div class="footer">
      <p>
        &copy; 2026 Wezea &middot; BCE 0811.380.056<br/>
        <a href="{FRONTEND_URL}?legal=mentions">Mentions l&eacute;gales</a> &middot;
        <a href="{FRONTEND_URL}?legal=confidentialite">Confidentialit&eacute;</a>
      </p>
    </div>
  </div>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Auth / compte
# ─────────────────────────────────────────────────────────────────────────────

async def send_welcome_email(email: str) -> bool:
    """Email de bienvenue envoyé à l'inscription."""
    html = _base_html(f"""
    <div class="card">
      <h1>Bienvenue sur Wezea !</h1>
      <p>
        Votre compte est pr&ecirc;t. Lancez votre premier audit de s&eacute;curit&eacute;
        et obtenez un score complet en moins de 60 secondes.
      </p>
      <p>Ce qu'on v&eacute;rifie pour vous&nbsp;: SSL/TLS &middot; SPF &middot; DKIM &middot; DMARC &middot; Ports r&eacute;seau &middot; CVE &middot; Blacklists</p>
      <a href="{FRONTEND_URL}" class="btn">&rarr; Scanner mon domaine</a>
    </div>
    """)
    return await _send({
        "sender":      SENDER,
        "to":          [{"email": email}],
        "subject":     "Bienvenue sur Wezea — votre scanner de sécurité",
        "htmlContent": html,
    })


async def add_registered_user_contact(
    email:      str,
    first_name: str | None = None,
    last_name:  str | None = None,
) -> bool:
    """Ajoute l'utilisateur à la liste Brevo (liste 2 = Utilisateurs inscrits)."""
    attrs: dict[str, Any] = {}
    if first_name:
        attrs["FIRSTNAME"] = first_name
    if last_name:
        attrs["LASTNAME"] = last_name

    return await _contacts_request(
        "post",
        BREVO_CONTACTS,
        json={
            "email":         email,
            "attributes":    attrs,
            "listIds":       [2],
            "updateEnabled": True,
        },
    )


async def update_brevo_contact(email: str, plan: str) -> bool:
    """Met à jour le plan d'un contact Brevo."""
    return await _contacts_request(
        "put",
        f"{BREVO_CONTACTS}/{email}",
        json={"attributes": {"PLAN": plan}},
    )


async def delete_brevo_contact(email: str) -> bool:
    """Supprime un contact de Brevo (demande RGPD)."""
    return await _contacts_request("delete", f"{BREVO_CONTACTS}/{email}")


async def send_password_reset_email(email: str, reset_url: str) -> bool:
    """Email de réinitialisation du mot de passe (lien valide 1 heure)."""
    safe_url = _esc(reset_url)
    html = _base_html(f"""
    <div class="card">
      <h1>R&eacute;initialiser votre mot de passe</h1>
      <p>
        Vous avez demand&eacute; la r&eacute;initialisation de votre mot de passe Wezea.
        Cliquez sur le bouton ci-dessous pour choisir un nouveau mot de passe.
      </p>
      <p>
        Ce lien est valable <strong>1&nbsp;heure</strong>.
        Apr&egrave;s ce d&eacute;lai, vous devrez faire une nouvelle demande.
      </p>
      <a href="{safe_url}" class="btn">&rarr; R&eacute;initialiser mon mot de passe</a>
      <p style="margin-top:1.5rem;font-size:13px;color:#64748b;">
        Si vous n&apos;&ecirc;tes pas &agrave; l&apos;origine de cette demande,
        ignorez simplement cet email — votre mot de passe ne sera pas modifi&eacute;.
      </p>
    </div>
    """)
    return await _send({
        "sender":      SENDER,
        "to":          [{"email": email}],
        "subject":     "Réinitialisation de votre mot de passe Wezea",
        "htmlContent": html,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Paiement / upgrade
# ─────────────────────────────────────────────────────────────────────────────

async def send_upgrade_email(email: str, plan: str) -> bool:
    """Confirmation d'upgrade vers Starter ou Pro."""
    plan_label = plan.capitalize()
    features = {
        "starter": "Scans illimit&eacute;s &middot; 1 domaine en surveillance &middot; Rapports PDF",
        "pro":     "Scans illimit&eacute;s &middot; Domaines illimit&eacute;s en surveillance &middot; Rapports PDF &middot; White-label",
    }
    feature_text = features.get(plan, "Toutes les fonctionnalit&eacute;s avanc&eacute;es")

    html = _base_html(f"""
    <div class="card">
      <h1>Votre plan {plan_label} est actif !</h1>
      <p>Merci pour votre confiance. Voici ce qui est maintenant d&eacute;bloqu&eacute;&nbsp;:</p>
      <div class="panel">
        <p>{feature_text}</p>
      </div>
      <a href="{FRONTEND_URL}" class="btn">&rarr; Acc&eacute;der &agrave; mon dashboard</a>
    </div>
    """)
    return await _send({
        "sender":      SENDER,
        "to":          [{"email": email}],
        "subject":     f"Votre plan Wezea {plan_label} est activé",
        "htmlContent": html,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Onboarding — séquence J+1 / J+3 / J+7 / J+14
# ─────────────────────────────────────────────────────────────────────────────

async def send_activation_nudge_email(email: str) -> bool:
    """J+1 — Utilisateur inscrit sans aucun scan."""
    html = _base_html(f"""
    <div class="card">
      <h1>Votre domaine est-il bien prot&eacute;g&eacute; ?</h1>
      <p>
        Vous avez cr&eacute;&eacute; votre compte hier — mais vous n&apos;avez pas encore lanc&eacute;
        votre premier scan. En 60 secondes, d&eacute;couvrez si votre domaine est expos&eacute;.
      </p>
      <div class="panel">
        <p class="label">CE QU&apos;ON V&Eacute;RIFIE</p>
        <p>SSL/TLS &middot; SPF &middot; DKIM &middot; DMARC &middot; Ports ouverts &middot; CVE &middot; Blacklists email</p>
      </div>
      <a href="{FRONTEND_URL}" class="btn">&rarr; Lancer mon premier scan</a>
      <p style="font-size:12px; color:#475569; margin-top:16px;">
        Gratuit, sans carte bancaire, r&eacute;sultats imm&eacute;diats.
      </p>
    </div>
    """)
    return await _send({
        "sender":      SENDER,
        "to":          [{"email": email}],
        "subject":     "Vous n'avez pas encore scanné votre domaine",
        "htmlContent": html,
    })


async def send_upgrade_nudge_email(email: str) -> bool:
    """J+3 — Utilisateur free, push vers Starter."""
    html = _base_html(f"""
    <div class="card">
      <h1>Votre domaine m&eacute;rite une surveillance continue</h1>
      <p>
        Le scan gratuit vous donne un &eacute;tat des lieux. Mais la s&eacute;curit&eacute; change
        tous les jours &mdash; un certificat peut expirer, un nouveau port s&apos;ouvrir,
        votre IP peut &ecirc;tre blacklist&eacute;e.
      </p>
      <div class="panel">
        <p class="label">PLAN STARTER &mdash; 9,90&euro;/mois</p>
        <p>Scans illimit&eacute;s &middot; 1 domaine en surveillance hebdomadaire &middot; Alerte email imm&eacute;diate &middot; Rapports PDF exportables</p>
      </div>
      <a href="{FRONTEND_URL}?upgrade=starter" class="btn">&rarr; Passer &agrave; Starter</a>
      <p style="font-size:12px; color:#475569; margin-top:16px;">
        R&eacute;siliable &agrave; tout moment.
      </p>
    </div>
    """)
    return await _send({
        "sender":      SENDER,
        "to":          [{"email": email}],
        "subject":     "Sachez quand votre sécurité change — plan Starter",
        "htmlContent": html,
    })


async def send_value_reminder_email(email: str, scan_count: int) -> bool:
    """J+7 — Utilisateur free ayant fait >=1 scan. Rappel valeur + upsell monitoring."""
    scans_label = f"{scan_count} scan{'s' if scan_count > 1 else ''}"
    html = _base_html(f"""
    <div class="card">
      <h1>Ce que vous avez trouv&eacute; avec Wezea</h1>
      <p>
        Vous avez effectu&eacute; {scans_label} cette semaine. C&apos;est bien &mdash; mais voici
        ce que vous ne voyez pas encore&nbsp;:
      </p>
      <div class="panel">
        <p>&middot; Un certificat SSL peut expirer silencieusement la nuit</p>
        <p>&middot; Une mise &agrave; jour peut ouvrir de nouveaux ports</p>
        <p>&middot; Votre IP peut &ecirc;tre blacklist&eacute;e sans notification</p>
        <p>&middot; Une CVE critique peut affecter votre stack ce soir</p>
      </div>
      <p>
        Le plan Starter surveille votre domaine chaque semaine et vous alerte
        d&egrave;s qu&apos;un changement est d&eacute;tect&eacute;. Vous n&apos;avez rien &agrave; faire.
      </p>
      <a href="{FRONTEND_URL}?upgrade=starter" class="btn">&rarr; Activer la surveillance automatique</a>
    </div>
    """)
    return await _send({
        "sender":      SENDER,
        "to":          [{"email": email}],
        "subject":     "Ce qui change sans que vous le sachiez",
        "htmlContent": html,
    })


async def send_winback_email(email: str) -> bool:
    """J+14 — Dernière relance, utilisateur toujours free."""
    html = _base_html(f"""
    <div class="card">
      <h1>Derni&egrave;re question avant de vous laisser tranquille</h1>
      <p>
        Cela fait 2 semaines que vous utilisez Wezea. En ce moment m&ecirc;me,
        des milliers de domaines subissent des attaques silencieuses.
      </p>
      <div class="panel">
        <p class="label">EN 14 JOURS, EN MOYENNE</p>
        <p>&middot; ~40 nouvelles CVE publi&eacute;es affectant des stacks courants</p>
        <p>&middot; Des centaines de domaines nouvellement blacklist&eacute;s</p>
        <p>&middot; Des dizaines de certificats SSL expir&eacute;s sans alerte</p>
      </div>
      <p>
        Le plan Starter (9,90&euro;/mois) surveille votre domaine chaque semaine
        et vous envoie une alerte si quelque chose change.
        C&apos;est la derni&egrave;re fois qu&apos;on vous en parle.
      </p>
      <a href="{FRONTEND_URL}?upgrade=starter" class="btn">&rarr; Essayer Starter</a>
      <p style="font-size:12px; color:#475569; margin-top:16px;">
        C&apos;est notre dernier email sur ce sujet. R&eacute;siliable &agrave; tout moment.
      </p>
    </div>
    """)
    return await _send({
        "sender":      SENDER,
        "to":          [{"email": email}],
        "subject":     "Un dernier email — puis on vous laisse tranquille",
        "htmlContent": html,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Monitoring — alertes automatiques
# ─────────────────────────────────────────────────────────────────────────────

async def send_monitoring_alert_email(
    email:      str,
    first_name: str,
    domain:     str,
    new_score:  int,
    prev_score: int | None,
    risk_level: str,
    reason:     str,
    findings:   list,
) -> bool:
    """Alerte de monitoring — score en baisse ou changement critique détecté."""
    risk_css = {
        "low":      "risk-low",
        "medium":   "risk-medium",
        "high":     "risk-high",
        "critical": "risk-critical",
    }.get((risk_level or "medium").lower(), "risk-medium")

    score_diff = ""
    if prev_score is not None:
        diff  = new_score - prev_score
        arrow = "&#9660;" if diff < 0 else "&#9650;"
        color = "#ef4444" if diff < 0 else "#34d399"
        score_diff = f'<span style="font-size:14px; color:{color};">{arrow} {abs(diff)} pts</span>'

    # Échapper les champs pouvant contenir des caractères HTML
    safe_first_name = _esc(first_name)
    safe_domain     = _esc(domain)
    safe_reason     = _esc(reason)

    findings_html = ""
    for f in findings[:3]:
        title = _esc(getattr(f, "title", str(f)))
        findings_html += f'<div class="finding">&#9888; {title}</div>'

    html = _base_html(f"""
    <div class="card">
      <h1>Alerte s&eacute;curit&eacute; &mdash; {safe_domain}</h1>
      <p>Bonjour {safe_first_name},<br/>
      Un changement a &eacute;t&eacute; d&eacute;tect&eacute; sur le domaine
      <strong style="color:#e2e8f0;">{safe_domain}</strong>
      lors du scan automatique de cette semaine.</p>

      <div class="panel" style="text-align:center;">
        <span class="score">{new_score}/100</span>
        &nbsp;
        <span class="{risk_css}" style="font-size:13px; font-weight:700;">
          {(risk_level or "").upper()}
        </span>
        <br/>{score_diff}
      </div>

      <p class="label" style="margin-top:16px;">RAISON DE L&apos;ALERTE</p>
      <div class="panel"><p>{safe_reason}</p></div>

      {findings_html}

      <a href="{FRONTEND_URL}?domain={safe_domain}" class="btn">&rarr; Voir le rapport complet</a>
      <p style="font-size:12px; color:#475569; margin-top:16px;">
        Vous recevez cet email car <strong>{safe_domain}</strong> est sous surveillance
        sur votre compte Wezea. Pour d&eacute;sactiver les alertes, rendez-vous dans
        votre dashboard.
      </p>
    </div>
    """)
    return await _send({
        "sender":      SENDER,
        "to":          [{"email": email}],
        "subject":     f"Alerte sécurité — {domain} ({new_score}/100)",
        "htmlContent": html,
    })


async def send_pdf_email(
    email:      str,
    domain:     str,
    pdf_bytes:  bytes,
    score:      int,
    risk_level: str,
) -> bool:
    """Envoie le rapport PDF en pièce jointe (rapport programmé hebdomadaire)."""
    pdf_b64  = base64.b64encode(pdf_bytes).decode()
    today    = datetime.date.today().isoformat()
    filename = f"rapport-securite-{domain}-{today}.pdf"

    html = _base_html(f"""
    <div class="card">
      <h1>Votre rapport de s&eacute;curit&eacute; hebdomadaire</h1>
      <p>
        Le rapport de s&eacute;curit&eacute; pour
        <strong style="color:#e2e8f0;">{domain}</strong>
        est disponible en pi&egrave;ce jointe.
      </p>
      <div class="panel" style="text-align:center;">
        <span class="score">{score}/100</span>
        &nbsp;
        <span style="font-size:13px; color:#94a3b8;">{(risk_level or "").upper()}</span>
      </div>
      <a href="{FRONTEND_URL}?domain={domain}" class="btn">&rarr; Voir en ligne</a>
    </div>
    """)
    return await _send({
        "sender":      SENDER,
        "to":          [{"email": email}],
        "subject":     f"Rapport sécurité hebdomadaire — {domain}",
        "htmlContent": html,
        "attachment":  [{"content": pdf_b64, "name": filename}],
    })


# ─────────────────────────────────────────────────────────────────────────────
# Contact
# ─────────────────────────────────────────────────────────────────────────────

async def send_contact_notification(
    name:    str,
    email:   str,
    subject: str,
    message: str,
) -> bool:
    """Notification interne — nouvelle demande de contact."""
    # Échapper les champs utilisateur pour éviter l'injection HTML dans l'email
    safe_name    = _esc(name)
    safe_email   = _esc(email)
    safe_subject = _esc(subject)
    safe_message = _esc(message)
    html = _base_html(f"""
    <div class="card">
      <h1>Nouveau message de contact</h1>
      <div class="panel">
        <p><span class="label">DE :</span> {safe_name} &lt;{safe_email}&gt;</p>
        <p><span class="label">SUJET :</span> {safe_subject}</p>
      </div>
      <div class="panel">
        <p style="white-space:pre-wrap; color:#e2e8f0;">{safe_message}</p>
      </div>
    </div>
    """)
    return await _send({
        "sender":      SENDER,
        "to":          [{"email": "contact@wezea.net"}],
        "replyTo":     {"email": email, "name": name},
        "subject":     f"[Contact Wezea] {subject}",
        "htmlContent": html,
    })


async def send_contact_confirmation(name: str, email: str) -> bool:
    """Confirmation envoyée à l'utilisateur après soumission du formulaire."""
    safe_name = _esc(name)
    html = _base_html(f"""
    <div class="card">
      <h1>Votre message a bien &eacute;t&eacute; re&ccedil;u</h1>
      <p>Bonjour {safe_name},</p>
      <p>
        Nous avons bien re&ccedil;u votre message et nous vous r&eacute;pondrons
        dans les plus brefs d&eacute;lais (g&eacute;n&eacute;ralement sous 24h en jours ouvr&eacute;s).
      </p>
      <a href="{FRONTEND_URL}" class="btn">&rarr; Retour sur Wezea</a>
    </div>
    """)
    return await _send({
        "sender":      SENDER,
        "to":          [{"email": email}],
        "subject":     "Votre message a bien été reçu — Wezea",
        "htmlContent": html,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Newsletter
# ─────────────────────────────────────────────────────────────────────────────

NEWSLETTER_LIST_ID = 3   # Liste Brevo dédiée newsletter (à créer dans Brevo si besoin)


async def send_newsletter_confirmation_email(email: str, token: str) -> bool:
    """Double opt-in : email de confirmation d'abonnement newsletter."""
    confirm_url = f"{FRONTEND_URL}/?newsletter_confirm={token}"
    html = _base_html(f"""
    <div class="card">
      <h1>Confirmez votre abonnement</h1>
      <p>
        Vous avez demandé à recevoir la newsletter Wezea — conseils en cybersécurité
        et nouveaux articles de blog.
      </p>
      <p>
        Pour finaliser votre inscription, cliquez sur le bouton ci-dessous.
        Ce lien est valable <strong>48&nbsp;heures</strong>.
      </p>
      <a href="{confirm_url}" class="btn">✓ Confirmer mon abonnement</a>
      <p style="margin-top:1.5rem;font-size:13px;color:#64748b;">
        Si vous n'êtes pas à l'origine de cette demande, ignorez simplement cet email.
        Aucun abonnement ne sera activé.
      </p>
    </div>
    """)
    return await _send({
        "sender":      SENDER,
        "to":          [{"email": email}],
        "subject":     "Confirmez votre abonnement à la newsletter Wezea",
        "htmlContent": html,
    })


async def send_newsletter_welcome_email(email: str) -> bool:
    """Email de bienvenue après confirmation de l'abonnement newsletter."""
    unsubscribe_url = f"{FRONTEND_URL}/?newsletter_unsubscribe=1"
    html = _base_html(f"""
    <div class="card">
      <h1>Bienvenue dans la newsletter Wezea 🎉</h1>
      <p>
        Votre abonnement est confirmé. Vous recevrez désormais nos conseils en cybersécurité
        et nos nouveaux articles de blog directement dans votre boîte mail.
      </p>
      <p><strong style="color:#e2e8f0;">Au programme :</strong></p>
      <ul>
        <li>Nouveaux articles du blog sécurité</li>
        <li>Conseils pratiques pour protéger vos domaines</li>
        <li>Actualités cybersécurité sélectionnées pour les PME et agences</li>
      </ul>
      <a href="{FRONTEND_URL}" class="btn">&rarr; Analyser mon domaine maintenant</a>
      <p style="margin-top:1.5rem;font-size:12px;color:#64748b;">
        Vous pouvez vous désabonner à tout moment en
        <a href="{unsubscribe_url}" style="color:#22d3ee;">cliquant ici</a>.
      </p>
    </div>
    """)
    return await _send({
        "sender":      SENDER,
        "to":          [{"email": email}],
        "subject":     "Bienvenue dans la newsletter Wezea",
        "htmlContent": html,
    })


async def add_newsletter_contact(email: str) -> bool:
    """Ajoute le contact à la liste newsletter Brevo (list 3)."""
    if not BREVO_API_KEY:
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Créer ou mettre à jour le contact
            r = await client.post(
                BREVO_CONTACTS,
                json={
                    "email":      email,
                    "listIds":    [NEWSLETTER_LIST_ID],
                    "updateEnabled": True,
                },
                headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"},
            )
            if r.status_code not in (200, 201, 204):
                # Contact existe peut-être déjà : essayer d'ajouter à la liste
                await client.post(
                    f"{BREVO_CONTACTS}/lists/{NEWSLETTER_LIST_ID}/contacts/add",
                    json={"emails": [email]},
                    headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"},
                )
            return True
    except Exception as exc:
        logger.error("Brevo add_newsletter_contact error: %s", exc)
        return False


async def remove_newsletter_contact(email: str) -> bool:
    """Retire le contact de la liste newsletter Brevo (désabonnement)."""
    if not BREVO_API_KEY:
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{BREVO_CONTACTS}/lists/{NEWSLETTER_LIST_ID}/contacts/remove",
                json={"emails": [email]},
                headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"},
            )
        return True
    except Exception as exc:
        logger.error("Brevo remove_newsletter_contact error: %s", exc)
        return False
