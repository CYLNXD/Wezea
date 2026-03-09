"""
dast_checks.py — DAST actif sur formulaires web
================================================
Tests actifs sur les formulaires découverts d'une application VÉRIFIÉE :

  1. XSS réfléchi    — probe inoffensive (balise custom + nonce) vérifiée
                        dans la réponse sans exécution JS
  2. SQLi basique     — injection d'une apostrophe + détection d'erreurs SQL
                        dans la réponse (pas d'extraction de données)
  3. CSRF             — détection de l'absence de token CSRF sur les
                        formulaires POST authentifiés

IMPORTANT :
  - Réservé aux apps VÉRIFIÉES (ownership confirmé via DNS ou fichier).
  - Aucune payload destructive ni payload à exécution réelle.
  - Max MAX_FORMS formulaires testés, MAX_FIELDS champs par formulaire.
  - Toutes les requêtes respectent DAST_TIMEOUT secondes.

Plans : Dev uniquement (le plus permissif, ownership mandatory).
"""
from __future__ import annotations

import html
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any

# ── Constantes ────────────────────────────────────────────────────────────────

MAX_FORMS     = 5       # formulaires à tester
MAX_FIELDS    = 3       # champs texte à tester par formulaire
DAST_TIMEOUT  = 6       # secondes par requête

# Probes XSS — aucune exécution JS, juste une balise HTML custom avec nonce
_XSS_PROBE_TAG   = "cyberhealth-xss-probe"   # nom de balise HTML custom
# Probe SQLi — provoque des erreurs SQL sans modifier de données
_SQLI_PROBE      = "'"                        # apostrophe simple

# Patterns d'erreurs SQL courants (minuscules)
_SQL_ERROR_PATTERNS = [
    "you have an error in your sql syntax",
    "unclosed quotation mark",
    "sql syntax",
    "mysql_fetch",
    "pg_query",
    "ora-",
    "odbc_exec",
    "microsoft ole db provider",
    "sqlite_exec",
    "sqlite error",
    "sqlite3.operationalerror",
    "psycopg2.errors",
    "sqlalchemy.exc",
    "warning: mysql",
    "division by zero",
    "invalid query",
    "sql command",
    "quoted string not properly terminated",
]

# Noms de champs associés aux tokens CSRF (minuscules)
_CSRF_FIELD_NAMES = {
    "csrf", "_csrf", "csrf_token", "_token", "authenticity_token",
    "csrfmiddlewaretoken", "xsrf_token", "__requestverificationtoken",
    "anti-csrf-token", "csrffield",
}

# Types d'inputs HTML qu'on peut tester (exclure file, submit, button, hidden…)
_TESTABLE_INPUT_TYPES = {"text", "email", "search", "url", "tel", "number", ""}


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class FormInput:
    name:  str
    type:  str   # type HTML (text, email, hidden, etc.)
    value: str   # valeur par défaut


@dataclass
class FormInfo:
    action:          str            # URL absolue d'action
    method:          str            # "GET" ou "POST"
    inputs:          list[FormInput]
    has_csrf_token:  bool = False

    def to_dict(self) -> dict:
        return {
            "action":         self.action,
            "method":         self.method,
            "has_csrf_token": self.has_csrf_token,
            "input_count":    len(self.inputs),
        }


@dataclass
class DastFinding:
    test_type:   str                 # "xss" | "sqli" | "csrf"
    severity:    str
    penalty:     int
    title:       str
    detail:      str
    evidence:    str | None = None
    form_action: str | None = None
    field_name:  str | None = None

    def to_dict(self) -> dict:
        return {
            "test_type":   self.test_type,
            "severity":    self.severity,
            "penalty":     self.penalty,
            "title":       self.title,
            "detail":      self.detail,
            "evidence":    self.evidence,
            "form_action": self.form_action,
            "field_name":  self.field_name,
        }


@dataclass
class DastResult:
    findings:    list[DastFinding] = field(default_factory=list)
    forms_found: int               = 0
    forms_tested: int              = 0
    error:       str | None        = None

    def to_dict(self) -> dict:
        return {
            "findings":     [f.to_dict() for f in self.findings],
            "forms_found":  self.forms_found,
            "forms_tested": self.forms_tested,
            "error":        self.error,
        }


# ── SSL context permissif (apps auto-signées) ────────────────────────────────

def _ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE
    return ctx


# ── Utilitaires HTTP ──────────────────────────────────────────────────────────

def _fetch(url: str, method: str = "GET", data: bytes | None = None,
           headers: dict | None = None) -> tuple[int, str]:
    """
    Requête HTTP/HTTPS synchrone.
    Retourne (status_code, body_excerpt).
    """
    _headers = {
        "User-Agent": "Mozilla/5.0 CyberHealth-DAST/1.0",
        "Accept":     "text/html,*/*",
    }
    if headers:
        _headers.update(headers)

    req = urllib.request.Request(url, data=data, headers=_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=DAST_TIMEOUT, context=_ssl_ctx()) as resp:
            body = resp.read(16384).decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as e:
        try:
            body = e.read(8192).decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return e.code, body
    except (urllib.error.URLError, OSError, Exception):
        return 0, ""


# ── Découverte de formulaires ─────────────────────────────────────────────────

_FORM_RE   = re.compile(r"<form\b[^>]*>.*?</form>", re.IGNORECASE | re.DOTALL)
_ACTION_RE = re.compile(r'\baction=["\']([^"\']*)["\']', re.IGNORECASE)
_METHOD_RE = re.compile(r'\bmethod=["\']([^"\']*)["\']', re.IGNORECASE)
_INPUT_RE  = re.compile(r"<input\b([^>]*)/?>", re.IGNORECASE)
_NAME_RE   = re.compile(r'\bname=["\']([^"\']*)["\']', re.IGNORECASE)
_TYPE_RE   = re.compile(r'\btype=["\']([^"\']*)["\']', re.IGNORECASE)
_VALUE_RE  = re.compile(r'\bvalue=["\']([^"\']*)["\']', re.IGNORECASE)


def discover_forms(base_url: str, html_body: str) -> list[FormInfo]:
    """Extrait les formulaires d'une page HTML."""
    forms: list[FormInfo] = []
    parsed_base = urllib.parse.urlparse(base_url)

    for form_match in _FORM_RE.finditer(html_body):
        form_html = form_match.group(0)

        # Action URL
        action_m = _ACTION_RE.search(form_html)
        raw_action = action_m.group(1).strip() if action_m else ""
        if raw_action:
            action = urllib.parse.urljoin(base_url, raw_action)
        else:
            action = base_url  # form sans action → soumet à la même URL

        # Method
        method_m = _METHOD_RE.search(form_html)
        method = (method_m.group(1).upper() if method_m else "GET").strip()
        if method not in ("GET", "POST"):
            method = "GET"

        # Inputs
        inputs: list[FormInput] = []
        has_csrf = False
        for inp_match in _INPUT_RE.finditer(form_html):
            attrs = inp_match.group(1)
            name_m  = _NAME_RE.search(attrs)
            type_m  = _TYPE_RE.search(attrs)
            value_m = _VALUE_RE.search(attrs)

            name  = name_m.group(1).strip()  if name_m  else ""
            itype = type_m.group(1).strip().lower() if type_m else "text"
            value = value_m.group(1).strip() if value_m else ""

            if name.lower() in _CSRF_FIELD_NAMES:
                has_csrf = True

            inputs.append(FormInput(name=name, type=itype, value=value))

        forms.append(FormInfo(
            action=action,
            method=method,
            inputs=inputs,
            has_csrf_token=has_csrf,
        ))

    return forms[:MAX_FORMS]


# ── DastAuditor ───────────────────────────────────────────────────────────────

class DastAuditor:
    """
    Teste les formulaires d'une application vérifiée pour XSS, SQLi et CSRF.
    Synchrone — appeler depuis run_in_executor.
    """

    def __init__(self, base_url: str):
        # Normaliser : assurer https://
        if not base_url.startswith(("http://", "https://")):
            base_url = "https://" + base_url
        self.base_url = base_url.rstrip("/")

    # ── Entrée principale ─────────────────────────────────────────────────────

    def run(self) -> DastResult:
        result = DastResult()

        # 1. Récupérer la page principale
        status, body = _fetch(self.base_url)
        if status == 0 or not body:
            result.error = "Impossible de joindre l'application."
            return result

        # 2. Découvrir les formulaires
        forms = discover_forms(self.base_url, body)
        result.forms_found  = len(forms)
        result.forms_tested = 0

        if not forms:
            return result

        # 3. Tester chaque formulaire
        tested_actions: set[str] = set()
        for form in forms:
            if form.action in tested_actions:
                continue
            tested_actions.add(form.action)
            result.forms_tested += 1

            # CSRF — ne nécessite pas d'envoi de requête
            csrf_f = self._check_csrf(form)
            if csrf_f:
                result.findings.append(csrf_f)

            # XSS + SQLi — seulement sur les formulaires POST
            # (GET params apparaissent en clair dans les logs — limite l'exposition)
            if form.method == "POST":
                xss_f = self._check_xss(form)
                if xss_f:
                    result.findings.append(xss_f)

                sqli_f = self._check_sqli(form)
                if sqli_f:
                    result.findings.append(sqli_f)

        return result

    # ── Check CSRF ────────────────────────────────────────────────────────────

    def _check_csrf(self, form: FormInfo) -> DastFinding | None:
        """Détecte l'absence de token CSRF sur les formulaires POST."""
        if form.method != "POST":
            return None
        if form.has_csrf_token:
            return None

        return DastFinding(
            test_type   = "csrf",
            severity    = "MEDIUM",
            penalty     = 8,
            title       = "Formulaire POST sans protection CSRF",
            detail      = (
                f"Le formulaire POST `{form.action}` ne contient aucun champ "
                f"de type token CSRF ({', '.join(sorted(_CSRF_FIELD_NAMES)[:5])}…). "
                f"Champs trouvés : {', '.join(i.name for i in form.inputs if i.name) or '(aucun)'}."
            ),
            evidence    = None,
            form_action = form.action,
            field_name  = None,
        )

    # ── Check XSS réfléchi ───────────────────────────────────────────────────

    def _check_xss(self, form: FormInfo) -> DastFinding | None:
        """
        Inject une balise HTML custom avec nonce dans les champs texte.
        Si la balise apparaît non-encodée dans la réponse → XSS potentiel.
        La probe est inoffensive : <cyberhealth-xss-probe id="CH-{nonce}">
        Aucun JS n'est exécuté.
        """
        # Sélectionner les champs testables
        testable = [
            inp for inp in form.inputs
            if inp.type in _TESTABLE_INPUT_TYPES and inp.name
        ][:MAX_FIELDS]

        if not testable:
            return None

        nonce = uuid.uuid4().hex[:8]
        probe = f'<{_XSS_PROBE_TAG} id="CH-{nonce}">'
        # Signature à rechercher dans la réponse (non encodée HTML)
        signature = f'id="CH-{nonce}"'

        for inp in testable:
            # Construire les données du formulaire
            payload_data: dict[str, str] = {}
            for field_obj in form.inputs:
                if not field_obj.name:
                    continue
                if field_obj.name == inp.name:
                    payload_data[field_obj.name] = probe
                else:
                    payload_data[field_obj.name] = field_obj.value or "test"

            encoded = urllib.parse.urlencode(payload_data).encode("utf-8")
            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            status, body = _fetch(form.action, method="POST", data=encoded, headers=headers)

            if status == 0:
                continue

            # Vérifier si la signature apparaît non-encodée dans la réponse
            # html.unescape pour gérer les réponses partiellement encodées
            body_unescaped = html.unescape(body)
            if signature in body_unescaped:
                # Extraire un contexte de 80 chars autour de la preuve
                idx = body_unescaped.find(signature)
                evidence = body_unescaped[max(0, idx - 30):idx + len(signature) + 30].strip()
                return DastFinding(
                    test_type   = "xss",
                    severity    = "HIGH",
                    penalty     = 15,
                    title       = f"XSS réfléchi potentiel — champ `{inp.name}`",
                    detail      = (
                        f"La probe `{probe}` injectée dans le champ `{inp.name}` "
                        f"du formulaire `{form.action}` est réfléchie non encodée dans la réponse. "
                        f"Aucun caractère HTML n'a été échappé (<, \", id=…)."
                    ),
                    evidence    = evidence[:120],
                    form_action = form.action,
                    field_name  = inp.name,
                )

        return None

    # ── Check SQLi basique ────────────────────────────────────────────────────

    def _check_sqli(self, form: FormInfo) -> DastFinding | None:
        """
        Injecte une apostrophe dans les champs texte et vérifie si la réponse
        contient des messages d'erreur SQL caractéristiques.
        Aucune modification de données — simple sonde de détection d'erreur.
        """
        testable = [
            inp for inp in form.inputs
            if inp.type in _TESTABLE_INPUT_TYPES and inp.name
        ][:MAX_FIELDS]

        if not testable:
            return None

        for inp in testable:
            payload_data: dict[str, str] = {}
            for field_obj in form.inputs:
                if not field_obj.name:
                    continue
                if field_obj.name == inp.name:
                    payload_data[field_obj.name] = _SQLI_PROBE
                else:
                    payload_data[field_obj.name] = field_obj.value or "test"

            encoded = urllib.parse.urlencode(payload_data).encode("utf-8")
            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            status, body = _fetch(form.action, method="POST", data=encoded, headers=headers)

            if status == 0:
                continue

            body_lower = body.lower()
            for pattern in _SQL_ERROR_PATTERNS:
                if pattern in body_lower:
                    # Extraire le contexte autour du pattern
                    idx = body_lower.find(pattern)
                    evidence = body[max(0, idx - 20):idx + len(pattern) + 60].strip()
                    return DastFinding(
                        test_type   = "sqli",
                        severity    = "CRITICAL",
                        penalty     = 25,
                        title       = f"Injection SQL potentielle — champ `{inp.name}`",
                        detail      = (
                            f"Une apostrophe (`'`) injectée dans le champ `{inp.name}` "
                            f"du formulaire `{form.action}` a déclenché un message d'erreur SQL : "
                            f"pattern `{pattern}` détecté dans la réponse HTTP {status}."
                        ),
                        evidence    = evidence[:120],
                        form_action = form.action,
                        field_name  = inp.name,
                    )

        return None
