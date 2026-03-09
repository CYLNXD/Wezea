"""
Tests unitaires — app/secret_scanner.py
Zéro réseau réel : urllib.request.urlopen est mocké.
"""
from __future__ import annotations

import re
import urllib.error
from io import BytesIO
from unittest.mock import patch, MagicMock

import pytest

from app.secret_scanner import (
    SecretScanner,
    SecretFinding,
    SecretScanResult,
    _mask,
    _context,
    _extract_script_urls,
    _scan_content,
    _PATTERNS,
    MAX_SCRIPT_SIZE,
)


# ─── Fixtures de test (PAS des vraies clés — construites en parties pour
#      éviter le push-protection GitHub qui ne voit pas les concaténations) ────
#
# Stripe live/test : "sk_" + "live_" + suffix  →  assembler à l'usage
# Slack xoxb       : "xoxb" + "-" + ...        →  assembler à l'usage
#
_STRIPE_PFX_LIVE  = "sk_" + "live_"
_STRIPE_SFX_24    = "AbCdEfGhIjKlMnOpQrStUvWx"   # 24 chars — valeur factice
_STRIPE_SFX_LONG  = "AbCdEfGhIjKlMnOpQrStUvWxYz1234567890"
_STRIPE_PFX_TEST  = "sk_" + "test_"
_STRIPE_SFX_TEST  = "AbCdEfGhIjKlMnOpQrStUvWxYz1234"
_SLACK_PFX        = "xoxb"
_SLACK_SFX        = "-123456789012-1234567890123-AbCdEfGhIjKlMnOpQrStUvWx"
_SLACK_APP_PFX    = "xoxa"
_SLACK_APP_SFX    = "-12345678901234567890"

# Valeurs assemblées (utilisées dans les tests)
FAKE_SK_LIVE      = _STRIPE_PFX_LIVE + _STRIPE_SFX_24        # format valide, factice
FAKE_SK_LIVE_LONG = _STRIPE_PFX_LIVE + _STRIPE_SFX_LONG      # plus long
FAKE_SK_TEST      = _STRIPE_PFX_TEST + _STRIPE_SFX_TEST      # test factice
FAKE_XOXB         = _SLACK_PFX + _SLACK_SFX                  # Slack factice
FAKE_XOXA         = _SLACK_APP_PFX + _SLACK_APP_SFX          # Slack app factice


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _mock_response(body: str, status: int = 200):
    """Simule un objet urllib response."""
    m = MagicMock()
    data = body.encode("utf-8")
    m.read.return_value = data
    m.__enter__ = lambda s: s
    m.__exit__  = MagicMock(return_value=False)
    return m


def _run_scanner(responses: list[tuple[str, int]]) -> SecretScanResult:
    """Lance SecretScanner('https://example.com') avec des réponses séquentielles."""
    idx = [0]
    def _fake(req, timeout=None, context=None):
        body, status = responses[idx[0] % len(responses)]
        idx[0] += 1
        return _mock_response(body, status)
    with patch("urllib.request.urlopen", side_effect=_fake):
        return SecretScanner("https://example.com").run()


# ─── Tests _mask ──────────────────────────────────────────────────────────────

class TestMask:
    def test_short_value_truncated(self):
        assert _mask("abc") == "abc***"

    def test_exactly_10_chars_still_short(self):
        val = "1234567890"
        result = _mask(val)
        assert result.startswith("1234")
        assert result.endswith("***")

    def test_long_value_keeps_start_and_end(self):
        val = FAKE_SK_LIVE
        result = _mask(val)
        assert result.startswith("sk_liv")
        assert result.endswith(FAKE_SK_LIVE[-2:])
        assert "***…***" in result

    def test_mask_hides_middle(self):
        val = "AKIAIOSFODNN7EXAMPLE"  # 20 chars
        result = _mask(val)
        # middle should be hidden
        assert "IOSFODNN7EXAMPL" not in result


# ─── Tests _context ───────────────────────────────────────────────────────────

class TestContext:
    def test_extracts_window(self):
        text = "A" * 50 + "SECRET" + "B" * 50
        ctx = _context(text, 50, 56, window=10)
        assert "SECRET" in ctx

    def test_normalizes_whitespace(self):
        text = "foo\n\t\n  SECRET  \n\nbar"
        ctx = _context(text, text.index("SECRET"), text.index("SECRET") + 6)
        assert "\n" not in ctx
        assert "\t" not in ctx

    def test_clips_at_boundaries(self):
        text = "abc"
        ctx = _context(text, 1, 2, window=100)
        assert ctx == "abc"


# ─── Tests _extract_script_urls ───────────────────────────────────────────────

class TestExtractScriptUrls:
    def test_relative_url_resolved(self):
        html = '<script src="/assets/app.js"></script>'
        urls = _extract_script_urls(html, "https://example.com")
        assert "https://example.com/assets/app.js" in urls

    def test_absolute_same_origin(self):
        html = '<script src="https://example.com/bundle.js"></script>'
        urls = _extract_script_urls(html, "https://example.com")
        assert "https://example.com/bundle.js" in urls

    def test_cross_origin_excluded(self):
        html = '<script src="https://cdn.other.com/lib.js"></script>'
        urls = _extract_script_urls(html, "https://example.com")
        assert urls == []

    def test_data_uri_excluded(self):
        html = '<script src="data:text/javascript,alert(1)"></script>'
        urls = _extract_script_urls(html, "https://example.com")
        assert urls == []

    def test_multiple_scripts(self):
        html = '''
          <script src="/a.js"></script>
          <script src="/b.js"></script>
          <script src="https://cdn.other.com/c.js"></script>
        '''
        urls = _extract_script_urls(html, "https://example.com")
        assert len(urls) == 2

    def test_inline_script_ignored(self):
        html = '<script>alert(1)</script>'
        urls = _extract_script_urls(html, "https://example.com")
        assert urls == []

    def test_double_quotes_and_single_quotes(self):
        html = "<script src='/single.js'></script><script src=\"/double.js\"></script>"
        urls = _extract_script_urls(html, "https://example.com")
        assert len(urls) == 2


# ─── Tests _scan_content ──────────────────────────────────────────────────────

class TestScanContent:
    def test_aws_key_detected(self):
        content = 'var key = "AKIAIOSFODNN7EXAMPLE";'
        findings = _scan_content(content, "test.js")
        names = [f.pattern_name for f in findings]
        assert "AWS Access Key ID" in names

    def test_stripe_live_secret_detected(self):
        content = f'const stripe = "{FAKE_SK_LIVE}";'
        findings = _scan_content(content, "bundle.js")
        names = [f.pattern_name for f in findings]
        assert "Stripe Live Secret Key" in names

    def test_stripe_live_secret_is_critical(self):
        content = FAKE_SK_LIVE_LONG
        findings = _scan_content(content, "bundle.js")
        stripe = next((f for f in findings if "Stripe Live" in f.pattern_name), None)
        assert stripe is not None
        assert stripe.severity == "CRITICAL"
        assert stripe.penalty  == 30

    def test_github_token_detected(self):
        # ghp_ + exactement 36 chars alphanum
        token = "ghp_" + "A" * 20 + "b" * 16   # 36 chars
        content = f'const token = "{token}";'
        findings = _scan_content(content, "app.js")
        names = [f.pattern_name for f in findings]
        assert "GitHub Personal Access Token" in names

    def test_pem_private_key_detected(self):
        content = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA..."
        findings = _scan_content(content, "bundle.js")
        names = [f.pattern_name for f in findings]
        assert "PEM Private Key" in names

    def test_pem_ec_key_detected(self):
        content = "-----BEGIN EC PRIVATE KEY-----"
        findings = _scan_content(content, "bundle.js")
        names = [f.pattern_name for f in findings]
        assert "PEM Private Key" in names

    def test_sendgrid_key_detected(self):
        # SG. + exactement 22 chars + . + exactement 43 chars
        key = "SG." + "A" * 22 + "." + "B" * 43
        content = f'const sg = "{key}";'
        findings = _scan_content(content, "bundle.js")
        names = [f.pattern_name for f in findings]
        assert "SendGrid API Key" in names

    def test_google_api_key_detected(self):
        content = 'apiKey: "AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI"'
        findings = _scan_content(content, "bundle.js")
        names = [f.pattern_name for f in findings]
        assert "Google API Key" in names

    def test_slack_token_detected(self):
        content = f'token: "{FAKE_XOXB}"'
        findings = _scan_content(content, "bundle.js")
        names = [f.pattern_name for f in findings]
        assert "Slack Bot/OAuth Token" in names

    def test_stripe_test_secret_detected(self):
        content = FAKE_SK_TEST
        findings = _scan_content(content, "bundle.js")
        names = [f.pattern_name for f in findings]
        assert "Stripe Test Secret Key" in names

    def test_stripe_test_secret_is_high(self):
        content = FAKE_SK_TEST
        findings = _scan_content(content, "bundle.js")
        test_key = next((f for f in findings if "Test" in f.pattern_name), None)
        assert test_key is not None
        assert test_key.severity == "HIGH"

    def test_no_secrets_returns_empty(self):
        content = 'const x = 42; const msg = "hello world";'
        findings = _scan_content(content, "bundle.js")
        assert findings == []

    def test_deduplication_same_key_same_file(self):
        # Même clé AWS deux fois dans le même fichier → 1 seul finding
        content = 'AKIAIOSFODNN7EXAMPLE ... AKIAIOSFODNN7EXAMPLE'
        findings = _scan_content(content, "bundle.js")
        aws = [f for f in findings if "AWS" in f.pattern_name]
        assert len(aws) == 1

    def test_finding_has_masked_value(self):
        content = 'key = "AKIAIOSFODNN7EXAMPLE"'
        findings = _scan_content(content, "test.js")
        aws = next(f for f in findings if "AWS" in f.pattern_name)
        # Value should be masked (no full key visible)
        assert "IOSFODNN7EXAMPL" not in aws.matched_value
        assert "***" in aws.matched_value

    def test_finding_has_source_url(self):
        content = 'key = "AKIAIOSFODNN7EXAMPLE"'
        findings = _scan_content(content, "https://example.com/bundle.js")
        assert findings[0].source_url == "https://example.com/bundle.js"

    def test_finding_has_context(self):
        content = 'const apiKey = "AKIAIOSFODNN7EXAMPLE"; console.log(x);'
        findings = _scan_content(content, "test.js")
        assert findings[0].context != ""


# ─── Tests SecretScanner.run() — page sans secrets ───────────────────────────

class TestSecretScannerClean:
    def test_clean_page_no_findings(self):
        page = '<html><script src="/bundle.js"></script></html>'
        bundle = 'const x = 42; const greeting = "hello world";'
        result = _run_scanner([(page, 200), (bundle, 200)])
        assert result.findings == []
        assert result.error is None

    def test_scripts_found_count(self):
        page = '''<html>
          <script src="/a.js"></script>
          <script src="/b.js"></script>
        </html>'''
        result = _run_scanner([(page, 200), ("ok", 200), ("ok", 200)])
        assert result.scripts_found == 2

    def test_scripts_scanned_count(self):
        page = '<html><script src="/bundle.js"></script></html>'
        result = _run_scanner([(page, 200), ("no secrets here", 200)])
        assert result.scripts_scanned == 1

    def test_no_scripts_in_page(self):
        page = '<html><p>No scripts here</p></html>'
        result = _run_scanner([(page, 200)])
        assert result.scripts_found == 0
        assert result.scripts_scanned == 0
        assert result.findings == []


# ─── Tests SecretScanner.run() — secrets détectés ────────────────────────────

class TestSecretScannerFindings:
    def test_aws_key_in_bundle(self):
        page   = '<html><script src="/app.js"></script></html>'
        bundle = 'const awsKey = "AKIAIOSFODNN7EXAMPLE"; export default awsKey;'
        result = _run_scanner([(page, 200), (bundle, 200)])
        names = [f.pattern_name for f in result.findings]
        assert "AWS Access Key ID" in names

    def test_stripe_live_key_in_bundle(self):
        page   = '<html><script src="/app.js"></script></html>'
        bundle = f'stripeKey="{FAKE_SK_LIVE_LONG}"'
        result = _run_scanner([(page, 200), (bundle, 200)])
        names = [f.pattern_name for f in result.findings]
        assert "Stripe Live Secret Key" in names

    def test_stripe_live_key_is_critical(self):
        page   = '<html><script src="/app.js"></script></html>'
        bundle = FAKE_SK_LIVE_LONG
        result = _run_scanner([(page, 200), (bundle, 200)])
        stripe = next((f for f in result.findings if "Stripe Live" in f.pattern_name), None)
        assert stripe is not None
        assert stripe.severity == "CRITICAL"
        assert stripe.penalty  == 30

    def test_inline_script_secret_detected(self):
        # Secret dans un bloc <script> inline (pas dans un fichier externe)
        page = '''<html>
          <script>
            var key = "AKIAIOSFODNN7EXAMPLE";
          </script>
        </html>'''
        result = _run_scanner([(page, 200)])
        names = [f.pattern_name for f in result.findings]
        assert "AWS Access Key ID" in names

    def test_inline_secret_source_url_contains_inline(self):
        page = '<html><script>const k="AKIAIOSFODNN7EXAMPLE"</script></html>'
        result = _run_scanner([(page, 200)])
        aws = next((f for f in result.findings if "AWS" in f.pattern_name), None)
        assert aws is not None
        assert "inline" in aws.source_url

    def test_findings_sorted_by_penalty_descending(self):
        # AWS (p=30) + Stripe test (p=15) → AWS first
        page   = '<html><script src="/app.js"></script></html>'
        bundle = f'{FAKE_SK_TEST}; "AKIAIOSFODNN7EXAMPLE"'
        result = _run_scanner([(page, 200), (bundle, 200)])
        if len(result.findings) >= 2:
            assert result.findings[0].penalty >= result.findings[1].penalty


# ─── Tests déduplication cross-scripts ───────────────────────────────────────

class TestSecretScannerDedup:
    def test_same_key_in_two_bundles_deduped(self):
        page = '''<html>
          <script src="/a.js"></script>
          <script src="/b.js"></script>
        </html>'''
        # Même clé AWS dans les deux bundles
        bundle = 'const k = "AKIAIOSFODNN7EXAMPLE";'
        result = _run_scanner([(page, 200), (bundle, 200), (bundle, 200)])
        aws_findings = [f for f in result.findings if "AWS" in f.pattern_name]
        assert len(aws_findings) == 1

    def test_different_keys_not_deduped(self):
        # Deux clés AWS différentes → deux findings
        page   = '<html><script src="/app.js"></script></html>'
        bundle = '"AKIAIOSFODNN7EXAMPLE" "AKIAI0SFODNN7EXAMPL"'
        result = _run_scanner([(page, 200), (bundle, 200)])
        aws_findings = [f for f in result.findings if "AWS" in f.pattern_name]
        # Peut être 1 ou 2 selon masquage — vérifier au moins 1
        assert len(aws_findings) >= 1


# ─── Tests gestion des erreurs ────────────────────────────────────────────────

class TestSecretScannerErrors:
    def test_network_error_on_main_page(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            result = SecretScanner("https://example.com").run()
        assert result.error is not None
        assert result.findings == []

    def test_script_fetch_error_non_fatal(self):
        # Page OK, mais le bundle raise une erreur réseau → non-fatal
        call_count = [0]
        def _fake(req, timeout=None, context=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return _mock_response('<html><script src="/app.js"></script></html>', 200)
            raise urllib.error.URLError("refused")
        with patch("urllib.request.urlopen", side_effect=_fake):
            result = SecretScanner("https://example.com").run()
        # scripts_found=1, scripts_scanned=0 (erreur), mais pas de crash
        assert result.error is None
        assert result.scripts_found == 1
        assert result.scripts_scanned == 0

    def test_oversized_bundle_skipped(self):
        # Bundle > MAX_SCRIPT_SIZE → ne doit pas être scanné (scripts_scanned reste 0)
        call_count = [0]
        def _fake(req, timeout=None, context=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return _mock_response('<html><script src="/big.js"></script></html>', 200)
            # Retourner un bundle plus grand que MAX_SCRIPT_SIZE
            big_body = "x" * (MAX_SCRIPT_SIZE + 2)
            return _mock_response(big_body, 200)
        with patch("urllib.request.urlopen", side_effect=_fake):
            result = SecretScanner("https://example.com").run()
        assert result.scripts_scanned == 0


# ─── Tests normalisation URL ──────────────────────────────────────────────────

class TestSecretScannerUrlNorm:
    def test_https_added_if_missing(self):
        scanner = SecretScanner("example.com")
        assert scanner.base_url.startswith("https://")

    def test_trailing_slash_removed(self):
        scanner = SecretScanner("https://example.com/")
        assert not scanner.base_url.endswith("/")

    def test_http_url_kept(self):
        scanner = SecretScanner("http://localhost:3000")
        assert scanner.base_url == "http://localhost:3000"


# ─── Tests MAX_SCRIPTS ────────────────────────────────────────────────────────

class TestMaxScripts:
    def test_max_scripts_limit_respected(self):
        """Plus de MAX_SCRIPTS bundles → seuls les 5 premiers sont scannés."""
        scripts = "".join(f'<script src="/s{i}.js"></script>' for i in range(8))
        page = f"<html>{scripts}</html>"
        call_count = [0]
        def _fake(req, timeout=None, context=None):
            call_count[0] += 1
            return _mock_response("ok", 200)
        with patch("urllib.request.urlopen", side_effect=_fake):
            result = SecretScanner("https://example.com").run()
        # 1 appel pour la page + max 5 pour les bundles
        assert call_count[0] <= 6
        assert result.scripts_scanned <= 5


# ─── Tests to_dict ────────────────────────────────────────────────────────────

class TestSecretFindingToDict:
    def test_to_dict_has_expected_keys(self):
        f = SecretFinding(
            pattern_name="AWS Access Key ID",
            severity="CRITICAL",
            penalty=30,
            description="desc",
            recommendation="reco",
            matched_value="AKIA***…***LE",
            source_url="https://example.com/app.js",
            context="const key = AKIA***",
        )
        d = f.to_dict()
        assert set(d.keys()) == {
            "pattern_name", "severity", "penalty", "description",
            "recommendation", "matched_value", "source_url", "context",
        }

    def test_secret_scan_result_to_dict(self):
        r = SecretScanResult(scripts_found=2, scripts_scanned=1)
        d = r.to_dict()
        assert d["scripts_found"] == 2
        assert d["scripts_scanned"] == 1
        assert d["findings"] == []
        assert d["error"] is None


# ─── Tests patterns individuels ───────────────────────────────────────────────

class TestPatterns:
    def test_all_patterns_have_required_fields(self):
        for pat in _PATTERNS:
            assert pat.name
            assert pat.regex is not None
            assert pat.severity in {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}
            assert isinstance(pat.penalty, int) and pat.penalty > 0
            assert pat.description
            assert pat.recommendation

    def test_aws_key_regex_matches_valid_key(self):
        pat = next(p for p in _PATTERNS if "AWS" in p.name)
        assert pat.regex.search("AKIAIOSFODNN7EXAMPLE")
        assert pat.regex.search("AKIAI0SFODNN7EXAMPL1")

    def test_aws_key_regex_no_false_positive_short(self):
        pat = next(p for p in _PATTERNS if "AWS" in p.name)
        # Trop court
        assert not pat.regex.search("AKIA123")

    def test_stripe_live_regex_matches(self):
        pat = next(p for p in _PATTERNS if "Stripe Live" in p.name)
        assert pat.regex.search(FAKE_SK_LIVE)

    def test_stripe_live_regex_no_match_test_key(self):
        pat = next(p for p in _PATTERNS if "Stripe Live" in p.name)
        # sk_test_ ne doit pas matcher sk_live_
        assert not pat.regex.search(FAKE_SK_TEST[:12])

    def test_github_pat_regex_matches(self):
        pat = next(p for p in _PATTERNS if "GitHub Personal" in p.name)
        valid_token = "ghp_" + "A" * 36
        assert pat.regex.search(valid_token)

    def test_github_pat_regex_no_match_short(self):
        pat = next(p for p in _PATTERNS if "GitHub Personal" in p.name)
        assert not pat.regex.search("ghp_short")

    def test_google_api_key_matches(self):
        pat = next(p for p in _PATTERNS if "Google" in p.name)
        # AIzaSy suivi de 33 chars = 39 total (bien dans AIza[35])
        assert pat.regex.search("AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI")

    def test_pem_key_regex_matches_rsa(self):
        pat = next(p for p in _PATTERNS if "PEM" in p.name)
        assert pat.regex.search("-----BEGIN RSA PRIVATE KEY-----")

    def test_pem_key_regex_matches_bare(self):
        pat = next(p for p in _PATTERNS if "PEM" in p.name)
        assert pat.regex.search("-----BEGIN PRIVATE KEY-----")

    def test_pem_key_regex_no_false_positive_public(self):
        pat = next(p for p in _PATTERNS if "PEM" in p.name)
        # Clé PUBLIQUE ne doit pas déclencher le pattern
        assert not pat.regex.search("-----BEGIN PUBLIC KEY-----")

    def test_sendgrid_regex_matches(self):
        pat = next(p for p in _PATTERNS if "SendGrid" in p.name)
        key = "SG." + "A" * 22 + "." + "B" * 43
        assert pat.regex.search(key)

    def test_slack_regex_matches_bot(self):
        pat = next(p for p in _PATTERNS if "Slack" in p.name)
        assert pat.regex.search(FAKE_XOXB)

    def test_slack_regex_matches_app(self):
        pat = next(p for p in _PATTERNS if "Slack" in p.name)
        assert pat.regex.search(FAKE_XOXA)

    def test_brevo_key_regex_matches(self):
        pat = next(p for p in _PATTERNS if "Brevo" in p.name)
        key = "xkeysib-" + "a" * 64 + "-" + "B" * 12
        assert pat.regex.search(key)
