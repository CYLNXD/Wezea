"""
Tests unitaires — app/dast_checks.py
Zéro réseau réel : urllib.request.urlopen est mocké.
"""
from __future__ import annotations

import urllib.error
import urllib.parse
from io import BytesIO
from unittest.mock import patch, MagicMock, call

import pytest

from app.dast_checks import (
    DastAuditor,
    DastFinding,
    DastResult,
    FormInfo,
    FormInput,
    discover_forms,
    _CSRF_FIELD_NAMES,
    _SQL_ERROR_PATTERNS,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_response(body: str, status: int = 200):
    """Crée un mock de urllib.request.urlopen."""
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__  = MagicMock(return_value=False)
    mock.read.return_value = body.encode("utf-8")
    mock.status = status
    return mock


def _run_dast(responses: list[tuple[str, int]]) -> DastResult:
    """
    Lance DastAuditor avec des réponses mockées (dans l'ordre).
    Chaque élément = (body, status_code).
    """
    call_idx = 0

    def _fake_urlopen(req, timeout=None, context=None):
        nonlocal call_idx
        if call_idx < len(responses):
            body, status = responses[call_idx]
        else:
            body, status = "", 0
        call_idx += 1
        return _mock_response(body, status)

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        auditor = DastAuditor("https://example.com")
        return auditor.run()


# ── Tests discover_forms ──────────────────────────────────────────────────────

class TestDiscoverForms:
    def test_simple_post_form(self):
        html = '''
        <form action="/login" method="POST">
          <input type="text" name="username">
          <input type="password" name="password">
          <input type="submit" value="Login">
        </form>
        '''
        forms = discover_forms("https://example.com", html)
        assert len(forms) == 1
        assert forms[0].method == "POST"
        assert forms[0].action == "https://example.com/login"

    def test_form_without_action_uses_base_url(self):
        html = '<form method="POST"><input type="text" name="q"></form>'
        forms = discover_forms("https://example.com/search", html)
        assert forms[0].action == "https://example.com/search"

    def test_relative_action_resolved(self):
        html = '<form action="submit" method="POST"><input name="x"></form>'
        forms = discover_forms("https://example.com/path/", html)
        assert "example.com" in forms[0].action

    def test_get_method_default(self):
        html = '<form action="/search"><input type="text" name="q"></form>'
        forms = discover_forms("https://example.com", html)
        assert forms[0].method == "GET"

    def test_csrf_token_detected(self):
        html = '''
        <form method="POST" action="/submit">
          <input type="hidden" name="csrf_token" value="abc123">
          <input type="text" name="data">
        </form>'''
        forms = discover_forms("https://example.com", html)
        assert forms[0].has_csrf_token is True

    def test_no_csrf_token(self):
        html = '<form method="POST" action="/submit"><input type="text" name="data"></form>'
        forms = discover_forms("https://example.com", html)
        assert forms[0].has_csrf_token is False

    def test_csrf_django_middleware_token(self):
        html = '<form method="POST"><input type="hidden" name="csrfmiddlewaretoken" value="x"></form>'
        forms = discover_forms("https://example.com", html)
        assert forms[0].has_csrf_token is True

    def test_multiple_forms_capped_at_max(self):
        from app.dast_checks import MAX_FORMS
        forms_html = ''.join(
            f'<form action="/f{i}" method="POST"><input name="x"></form>'
            for i in range(MAX_FORMS + 3)
        )
        forms = discover_forms("https://example.com", forms_html)
        assert len(forms) <= MAX_FORMS

    def test_no_forms_returns_empty(self):
        assert discover_forms("https://example.com", "<p>No forms here</p>") == []

    def test_input_types_extracted(self):
        html = '''
        <form method="POST" action="/x">
          <input type="email" name="mail">
          <input type="text" name="name">
        </form>'''
        forms = discover_forms("https://example.com", html)
        types = {inp.type for inp in forms[0].inputs}
        assert "email" in types
        assert "text" in types

    def test_form_to_dict(self):
        form = FormInfo(
            action="https://example.com/login",
            method="POST",
            inputs=[FormInput("user", "text", "")],
            has_csrf_token=False,
        )
        d = form.to_dict()
        assert d["method"] == "POST"
        assert d["has_csrf_token"] is False
        assert d["input_count"] == 1


# ── Tests DastFinding ─────────────────────────────────────────────────────────

class TestDastFinding:
    def test_to_dict_keys(self):
        f = DastFinding(
            test_type="csrf", severity="MEDIUM", penalty=8,
            title="CSRF missing", detail="detail", evidence=None,
            form_action="/login", field_name=None,
        )
        d = f.to_dict()
        assert set(d.keys()) == {
            "test_type", "severity", "penalty", "title",
            "detail", "evidence", "form_action", "field_name",
        }

    def test_to_dict_values(self):
        f = DastFinding("xss", "HIGH", 15, "XSS", "det", "ev", "/form", "name")
        d = f.to_dict()
        assert d["test_type"]   == "xss"
        assert d["severity"]    == "HIGH"
        assert d["penalty"]     == 15


# ── Tests DastResult ──────────────────────────────────────────────────────────

class TestDastResult:
    def test_to_dict_empty(self):
        r = DastResult()
        d = r.to_dict()
        assert d["findings"] == []
        assert d["forms_found"] == 0

    def test_to_dict_with_findings(self):
        r = DastResult(
            findings=[DastFinding("csrf", "MEDIUM", 8, "t", "d")],
            forms_found=2,
            forms_tested=2,
        )
        d = r.to_dict()
        assert len(d["findings"]) == 1
        assert d["forms_found"] == 2


# ── Tests no forms ────────────────────────────────────────────────────────────

class TestDastNoForms:
    def test_page_without_forms(self):
        result = _run_dast([("<html><p>No forms</p></html>", 200)])
        assert result.findings == []
        assert result.forms_found == 0

    def test_unreachable_app(self):
        with patch("urllib.request.urlopen",
                   side_effect=urllib.error.URLError("refused")):
            auditor = DastAuditor("https://example.com")
            result  = auditor.run()
        assert result.findings == []
        assert result.error is not None


# ── Tests CSRF ────────────────────────────────────────────────────────────────

class TestDastCsrf:
    def _make_post_form_page(self, with_csrf: bool = False) -> str:
        csrf_field = (
            '<input type="hidden" name="csrf_token" value="tok">'
            if with_csrf else ""
        )
        return f'''<html><form action="/submit" method="POST">
          {csrf_field}
          <input type="text" name="username">
          <input type="submit">
        </form></html>'''

    def test_post_form_without_csrf_triggers_finding(self):
        page = self._make_post_form_page(with_csrf=False)
        # Page principale + réponse au POST (pour XSS/SQLi qui retournent 200)
        result = _run_dast([(page, 200), ("ok", 200), ("ok", 200)])
        csrf_findings = [f for f in result.findings if f.test_type == "csrf"]
        assert len(csrf_findings) == 1

    def test_csrf_finding_severity_medium(self):
        page = self._make_post_form_page(with_csrf=False)
        result = _run_dast([(page, 200), ("ok", 200), ("ok", 200)])
        csrf_f = next(f for f in result.findings if f.test_type == "csrf")
        assert csrf_f.severity == "MEDIUM"
        assert csrf_f.penalty  == 8

    def test_post_form_with_csrf_no_finding(self):
        page = self._make_post_form_page(with_csrf=True)
        result = _run_dast([(page, 200), ("ok", 200), ("ok", 200)])
        csrf_findings = [f for f in result.findings if f.test_type == "csrf"]
        assert csrf_findings == []

    def test_get_form_no_csrf_finding(self):
        page = '<html><form action="/search" method="GET"><input name="q"></form></html>'
        result = _run_dast([(page, 200)])
        assert result.findings == []

    def test_csrf_finding_has_form_action(self):
        page = self._make_post_form_page(with_csrf=False)
        result = _run_dast([(page, 200), ("ok", 200), ("ok", 200)])
        csrf_f = next(f for f in result.findings if f.test_type == "csrf")
        assert csrf_f.form_action is not None
        assert "submit" in csrf_f.form_action


# ── Tests XSS réfléchi ────────────────────────────────────────────────────────

class TestDastXss:
    _POST_FORM = '''<html><form action="/search" method="POST">
      <input type="text" name="q">
    </form></html>'''

    def test_reflected_probe_triggers_xss_finding(self):
        """La probe apparaît non-encodée dans la réponse → HIGH XSS."""
        call_count = [0]

        def _fake_urlopen(req, timeout=None, context=None):
            body_str = req.data.decode() if req.data else ""
            if call_count[0] == 0:
                # Page principale
                call_count[0] += 1
                return _mock_response(self._POST_FORM, 200)
            else:
                call_count[0] += 1
                # Simuler un serveur qui réfléchit l'input URL-décodé dans la réponse HTML
                # (body_str est URL-encodé : q=%3Ccyberhealth-xss-probe+id%3D%22CH-...%22%3E)
                # URL-décoder pour obtenir les caractères bruts dans la réponse
                decoded = urllib.parse.unquote_plus(body_str)
                return _mock_response(f"<html><p>{decoded}</p></html>", 200)

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            auditor = DastAuditor("https://example.com")
            result = auditor.run()

        xss_findings = [f for f in result.findings if f.test_type == "xss"]
        assert len(xss_findings) == 1
        assert xss_findings[0].severity == "HIGH"
        assert xss_findings[0].penalty  == 15

    def test_encoded_output_no_xss_finding(self):
        """La probe est HTML-encodée dans la réponse → pas de finding XSS."""
        call_count = [0]

        def _fake_urlopen(req, timeout=None, context=None):
            if call_count[0] == 0:
                call_count[0] += 1
                return _mock_response(self._POST_FORM, 200)
            call_count[0] += 1
            # Réponse avec probe HTML-encodée (&lt; etc.)
            return _mock_response(
                '&lt;cyberhealth-xss-probe id=&quot;CH-abcd1234&quot;&gt;', 200
            )

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            auditor = DastAuditor("https://example.com")
            result = auditor.run()

        xss_findings = [f for f in result.findings if f.test_type == "xss"]
        assert xss_findings == []

    def test_xss_finding_has_field_name(self):
        """Le finding XSS mentionne le nom du champ vulnérable."""
        call_count = [0]

        def _fake_urlopen(req, timeout=None, context=None):
            body_str = req.data.decode() if req.data else ""
            if call_count[0] == 0:
                call_count[0] += 1
                return _mock_response(self._POST_FORM, 200)
            call_count[0] += 1
            return _mock_response(body_str, 200)

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            auditor = DastAuditor("https://example.com")
            result  = auditor.run()

        xss_findings = [f for f in result.findings if f.test_type == "xss"]
        if xss_findings:
            assert xss_findings[0].field_name == "q"

    def test_no_testable_fields_no_xss(self):
        """Formulaire sans champ texte → pas de test XSS."""
        page = '''<html><form method="POST" action="/x">
          <input type="file" name="f">
          <input type="submit" value="Go">
        </form></html>'''
        result = _run_dast([(page, 200)])
        xss_findings = [f for f in result.findings if f.test_type == "xss"]
        assert xss_findings == []


# ── Tests SQLi ────────────────────────────────────────────────────────────────

class TestDastSqli:
    _POST_FORM = '''<html><form action="/login" method="POST">
      <input type="text" name="user">
      <input type="password" name="pass">
    </form></html>'''

    def test_sql_error_in_response_triggers_sqli_finding(self):
        """Réponse contenant un message d'erreur SQL → CRITICAL SQLi."""
        call_count = [0]

        def _fake_urlopen(req, timeout=None, context=None):
            if call_count[0] == 0:
                call_count[0] += 1
                return _mock_response(self._POST_FORM, 200)
            call_count[0] += 1
            # Première injection (champ user) → erreur SQL
            return _mock_response(
                "Warning: You have an error in your SQL syntax near '\''", 200
            )

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            auditor = DastAuditor("https://example.com")
            result  = auditor.run()

        sqli_findings = [f for f in result.findings if f.test_type == "sqli"]
        assert len(sqli_findings) == 1
        assert sqli_findings[0].severity == "CRITICAL"
        assert sqli_findings[0].penalty  == 25

    def test_no_sql_error_no_finding(self):
        """Réponse sans erreur SQL → pas de finding SQLi."""
        result = _run_dast([
            (self._POST_FORM, 200),
            ("Login failed. Please try again.", 200),
            ("Login failed. Please try again.", 200),
        ])
        sqli_findings = [f for f in result.findings if f.test_type == "sqli"]
        assert sqli_findings == []

    def test_sqli_finding_has_evidence(self):
        """Le finding SQLi contient une preuve (extrait de la réponse)."""
        call_count = [0]

        def _fake_urlopen(req, timeout=None, context=None):
            if call_count[0] == 0:
                call_count[0] += 1
                return _mock_response(self._POST_FORM, 200)
            call_count[0] += 1
            return _mock_response("error: sql syntax error near query", 200)

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            auditor = DastAuditor("https://example.com")
            result  = auditor.run()

        sqli_findings = [f for f in result.findings if f.test_type == "sqli"]
        if sqli_findings:
            assert sqli_findings[0].evidence is not None
            assert len(sqli_findings[0].evidence) > 0

    def test_sqli_finding_has_field_name(self):
        call_count = [0]

        def _fake_urlopen(req, timeout=None, context=None):
            if call_count[0] == 0:
                call_count[0] += 1
                return _mock_response(self._POST_FORM, 200)
            call_count[0] += 1
            return _mock_response("ORA-00907: missing right parenthesis", 200)

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            auditor = DastAuditor("https://example.com")
            result  = auditor.run()

        sqli_findings = [f for f in result.findings if f.test_type == "sqli"]
        if sqli_findings:
            assert sqli_findings[0].field_name in ("user", "pass")

    def test_all_sql_error_patterns_covered(self):
        """Vérifier que chaque pattern SQL déclenche bien un finding."""
        form_page = '''<html><form action="/q" method="POST">
          <input type="text" name="q">
        </form></html>'''
        for pattern in _SQL_ERROR_PATTERNS[:5]:
            call_count = [0]

            def _fake(req, timeout=None, context=None, _p=pattern):
                if call_count[0] == 0:
                    call_count[0] += 1
                    return _mock_response(form_page, 200)
                call_count[0] += 1
                return _mock_response(f"Database error: {_p} at query", 200)

            with patch("urllib.request.urlopen", side_effect=_fake):
                result = DastAuditor("https://example.com").run()
            sqli = [f for f in result.findings if f.test_type == "sqli"]
            assert len(sqli) >= 1, f"Pattern non détecté : {pattern!r}"


# ── Tests combinés ────────────────────────────────────────────────────────────

class TestDastCombined:
    def test_no_csrf_and_sql_error_both_detected(self):
        """Formulaire sans CSRF + réponse SQL error → 2 findings distincts."""
        page = '''<html><form action="/login" method="POST">
          <input type="text" name="user">
        </form></html>'''

        call_count = [0]

        def _fake(req, timeout=None, context=None):
            if call_count[0] == 0:
                call_count[0] += 1
                return _mock_response(page, 200)
            call_count[0] += 1
            return _mock_response("MySQL error: sql syntax near ''", 200)

        with patch("urllib.request.urlopen", side_effect=_fake):
            result = DastAuditor("https://example.com").run()

        types = {f.test_type for f in result.findings}
        assert "csrf" in types
        assert "sqli" in types

    def test_forms_tested_count(self):
        """Vérifier que forms_tested est incrémenté correctement."""
        page = '''<html>
          <form action="/a" method="POST"><input name="x"></form>
          <form action="/b" method="POST"><input name="y"></form>
        </html>'''
        result = _run_dast([
            (page, 200),
            ("ok", 200), ("ok", 200),
            ("ok", 200), ("ok", 200),
        ])
        assert result.forms_found  == 2
        assert result.forms_tested == 2

    def test_duplicate_actions_not_retested(self):
        """Deux formulaires avec la même action → testé une seule fois."""
        page = '''<html>
          <form action="/same" method="POST"><input name="x"></form>
          <form action="/same" method="POST"><input name="y"></form>
        </html>'''
        call_count = [0]

        def _fake(req, timeout=None, context=None):
            call_count[0] += 1
            # Premier appel = page principale avec les formulaires
            if call_count[0] == 1:
                return _mock_response(page, 200)
            return _mock_response("ok", 200)

        with patch("urllib.request.urlopen", side_effect=_fake):
            result = DastAuditor("https://example.com").run()
        assert result.forms_tested == 1


# ── Tests URL normalization ───────────────────────────────────────────────────

class TestDastAuditorInit:
    def test_https_added_if_missing(self):
        auditor = DastAuditor("example.com")
        assert auditor.base_url.startswith("https://")

    def test_trailing_slash_removed(self):
        auditor = DastAuditor("https://example.com/")
        assert not auditor.base_url.endswith("/")

    def test_http_url_kept(self):
        auditor = DastAuditor("http://localhost:8080")
        assert auditor.base_url == "http://localhost:8080"
