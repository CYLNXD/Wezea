"""
CyberHealth Scanner — Script de load testing Locust
=====================================================
Simule 3 profils d'utilisateurs réels :
  - AnonUser      : visiteur non connecté (scan public, stats, blog)
  - AuthUser      : utilisateur connecté (historique, profil, monitoring)
  - ScanUser      : utilisateur qui lance des scans (rate-limité par l'API)

Usage :
    pip install locust
    locust -f locustfile.py --host=https://scan.wezea.net

Puis ouvrir http://localhost:8089 et lancer avec :
    Users : 50   |   Spawn rate : 5/s   |   Run time : 2min

Cibles réalistes :
    - p95 < 200ms pour tous les endpoints hors /scan
    - p95 < 8s    pour /scan (timeout serveur = 8s)
    - 0% error rate sur /health et endpoints GET légers (hors 429)

Variables d'environnement optionnelles :
    LOCUST_EMAIL    : email d'un compte de test existant
    LOCUST_PASSWORD : mot de passe correspondant
    LOCUST_DOMAIN   : domaine à scanner (défaut : example.com)
"""

from __future__ import annotations

import os
import random
import threading
import time
import uuid

from locust import HttpUser, between, task, events

# ─── Config ──────────────────────────────────────────────────────────────────

TEST_EMAIL    = os.getenv("LOCUST_EMAIL",    "loadtest@example.com")
TEST_PASSWORD = os.getenv("LOCUST_PASSWORD", "LoadTest2026!")
TEST_DOMAIN   = os.getenv("LOCUST_DOMAIN",  "example.com")

# Domaines rapides à scanner (peu de findings, résolution DNS rapide)
_SAFE_DOMAINS = ["example.com", "example.org", "example.net"]

# ─── Token partagé ───────────────────────────────────────────────────────────
# Un seul login pour tous les AuthUser/ScanUser — évite d'inonder le rate
# limiter de /auth/login au démarrage (50 users × on_start = 50 logins)

_token_lock  = threading.Lock()
_shared_token: str | None = None


def _get_shared_token(client) -> str | None:
    """
    Retourne le JWT partagé entre tous les users authentifiés.
    Login effectué une seule fois, résultat mis en cache globalement.
    """
    global _shared_token
    if _shared_token:
        return _shared_token
    with _token_lock:
        # Double-check après acquisition du verrou
        if _shared_token:
            return _shared_token
        r = client.post(
            "/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            name="/auth/login [setup]",
            catch_response=True,
        )
        with r:
            data = _json(r)
            if r.status_code == 200 and "access_token" in data:
                _shared_token = data["access_token"]
                r.success()
            elif r.status_code == 429:
                r.success()  # rate limit — réessayer plus tard
                time.sleep(3)
            else:
                r.failure(f"Login failed: {r.status_code}")
    return _shared_token


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _json(response) -> dict:
    """Retourne le JSON de la réponse ou {} si parsing échoue."""
    try:
        return response.json()
    except Exception:
        return {}


def _get(client, path: str, name: str, token: str | None = None):
    """
    GET avec gestion automatique des 429 (comptés comme succès).
    Les 401 sur endpoints authentifiés sont des vraies erreurs.
    """
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with client.get(path, name=name, headers=headers, catch_response=True) as r:
        if r.status_code == 429:
            r.success()   # rate limit = comportement attendu, pas un bug
        elif r.status_code >= 500:
            r.failure(f"Server error {r.status_code}")
        # 401 → failure automatique si token absent/expiré (comportement voulu)
    return r


# ─── Profil 1 : Visiteur anonyme ─────────────────────────────────────────────

class AnonUser(HttpUser):
    """
    Simule un visiteur non connecté qui arrive sur le dashboard.
    Représente ~60% du trafic réel.
    """
    weight    = 3
    wait_time = between(1, 4)

    def on_start(self):
        r = self.client.get("/client-id", name="/client-id", catch_response=True)
        with r:
            r.success()  # 429 aussi accepté

    @task(5)
    def load_dashboard_data(self):
        _get(self.client, "/scan/limits", "/scan/limits [anon]")

    @task(4)
    def load_public_stats(self):
        _get(self.client, "/public/stats", "/public/stats")

    @task(3)
    def load_blog_links(self):
        _get(self.client, "/public/blog-links", "/public/blog-links")

    @task(2)
    def health_check(self):
        self.client.get("/health", name="/health")

    @task(1)
    def launch_anonymous_scan(self):
        """Scan anonyme — rate limité 5/jour par IP, 429 = succès."""
        domain = random.choice(_SAFE_DOMAINS)
        with self.client.post(
            "/scan",
            json={"domain": domain, "lang": "fr"},
            name="/scan [anon]",
            catch_response=True,
            timeout=12,
        ) as r:
            if r.status_code in (429, 401):
                r.success()
            elif r.status_code >= 500:
                r.failure(f"Server error {r.status_code}")


# ─── Profil 2 : Utilisateur connecté (sans scan) ─────────────────────────────

class AuthUser(HttpUser):
    """
    Simule un utilisateur qui consulte son espace client.
    Utilise le token partagé — pas de login individuel.
    """
    weight    = 2
    wait_time = between(2, 6)

    def on_start(self):
        self.token = _get_shared_token(self.client)

    @task(6)
    def check_me(self):
        _get(self.client, "/auth/me", "/auth/me", self.token)

    @task(5)
    def scan_limits(self):
        _get(self.client, "/scan/limits", "/scan/limits [auth]", self.token)

    @task(4)
    def scan_history(self):
        _get(self.client, "/scans/history?limit=20", "/scans/history", self.token)

    @task(3)
    def monitoring_status(self):
        _get(self.client, "/monitoring/status", "/monitoring/status", self.token)

    @task(3)
    def monitoring_domains(self):
        _get(self.client, "/monitoring/domains", "/monitoring/domains", self.token)

    @task(2)
    def payment_status(self):
        _get(self.client, "/payment/status", "/payment/status", self.token)

    @task(1)
    def public_stats(self):
        _get(self.client, "/public/stats", "/public/stats")


# ─── Profil 3 : Utilisateur qui scanne activement ────────────────────────────

class ScanUser(HttpUser):
    """
    Simule un utilisateur Pro qui lance des scans fréquemment.
    Wait_time long pour respecter les rate limits serveur.
    """
    weight    = 1
    wait_time = between(10, 30)

    def on_start(self):
        self.token = _get_shared_token(self.client)

    @task(3)
    def authenticated_scan(self):
        domain = random.choice(_SAFE_DOMAINS)
        with self.client.post(
            "/scan",
            json={"domain": domain, "lang": "fr"},
            name="/scan [auth]",
            catch_response=True,
            timeout=12,
        ) as r:
            if r.status_code == 429:
                r.success()
            elif r.status_code >= 500:
                r.failure(f"Server error {r.status_code}")
            elif r.status_code == 200:
                if "score" not in _json(r):
                    r.failure("Réponse scan sans champ 'score'")

    @task(1)
    def scan_history_after_scan(self):
        _get(self.client, "/scans/history?limit=5", "/scans/history [post-scan]", self.token)


# ─── Événements Locust ────────────────────────────────────────────────────────

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("\n" + "="*60)
    print("🚀 CyberHealth Load Test démarré")
    print(f"   Host     : {environment.host}")
    print(f"   Compte   : {TEST_EMAIL}")
    print(f"   Profils  : AnonUser×3, AuthUser×2, ScanUser×1")
    print(f"   Token    : partagé (1 login pour tous les users auth)")
    print("="*60 + "\n")

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    stats = environment.stats.total
    print("\n" + "="*60)
    print("📊 Résultats CyberHealth Load Test")
    print(f"   Requêtes totales : {stats.num_requests}")
    print(f"   Erreurs          : {stats.num_failures} ({stats.fail_ratio*100:.1f}%)")
    print(f"   Médiane (p50)    : {stats.median_response_time}ms")
    print(f"   p95              : {stats.get_response_time_percentile(0.95)}ms")
    print(f"   p99              : {stats.get_response_time_percentile(0.99)}ms")
    print(f"   RPS max          : {stats.max_requests_per_sec:.1f}")
    print("="*60 + "\n")
