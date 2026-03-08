"""
CyberHealth Scanner — Script de load testing Locust
=====================================================
Simule 3 profils d'utilisateurs réels :
  - AnonUser      : visiteur non connecté (scan public, stats, blog)
  - AuthUser      : utilisateur connecté (historique, profil, monitoring)
  - ScanUser      : utilisateur qui lance des scans (rate-limitié par l'API)

Usage :
    pip install locust
    locust -f locustfile.py --host=https://scan.wezea.net

Puis ouvrir http://localhost:8089 et lancer avec :
    Users : 50   |   Spawn rate : 5/s   |   Run time : 2min

Cibles réalistes :
    - p95 < 200ms pour tous les endpoints hors /scan
    - p95 < 8s    pour /scan (timeout serveur = 8s)
    - 0% error rate sur /health et endpoints GET légers

Variables d'environnement optionnelles :
    LOCUST_EMAIL    : email d'un compte de test existant
    LOCUST_PASSWORD : mot de passe correspondant
    LOCUST_DOMAIN   : domaine à scanner (défaut : example.com)
"""

from __future__ import annotations

import json
import os
import random
import time
import uuid

from locust import HttpUser, TaskSet, between, constant, task, events

# ─── Config ──────────────────────────────────────────────────────────────────

TEST_EMAIL    = os.getenv("LOCUST_EMAIL",    "loadtest@example.com")
TEST_PASSWORD = os.getenv("LOCUST_PASSWORD", "LoadTest2026!")
TEST_DOMAIN   = os.getenv("LOCUST_DOMAIN",  "example.com")

# Domaines rapides à scanner (peu de findings, résolution DNS rapide)
_SAFE_DOMAINS = ["example.com", "example.org", "example.net"]

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _json(response) -> dict:
    """Retourne le JSON de la réponse ou {} si parsing échoue."""
    try:
        return response.json()
    except Exception:
        return {}


# ─── Profil 1 : Visiteur anonyme ─────────────────────────────────────────────

class AnonUser(HttpUser):
    """
    Simule un visiteur non connecté qui arrive sur le dashboard.
    Représente ~60% du trafic réel.
    Poids élevé : 3 instances pour 1 AuthUser.
    """
    weight        = 3
    wait_time     = between(1, 4)   # temps de lecture entre les actions

    def on_start(self):
        # Récupérer un client-id comme le ferait le browser
        r = self.client.get("/client-id", name="/client-id")
        data = _json(r)
        self.client_id = data.get("client_id", str(uuid.uuid4()))

    @task(5)
    def load_dashboard_data(self):
        """Données chargées à chaque ouverture du Dashboard."""
        self.client.get("/scan/limits", name="/scan/limits [anon]")

    @task(4)
    def load_public_stats(self):
        """Widget maturité industrie."""
        self.client.get("/public/stats", name="/public/stats")

    @task(3)
    def load_blog_links(self):
        """Liens blog dans le dashboard."""
        self.client.get("/public/blog-links", name="/public/blog-links")

    @task(2)
    def health_check(self):
        """Uptime monitoring simulé."""
        self.client.get("/health", name="/health")

    @task(1)
    def launch_anonymous_scan(self):
        """
        Scan anonyme — l'action principale du visiteur.
        Limité à ~5/jour par IP côté API, on ne spamme pas.
        """
        domain = random.choice(_SAFE_DOMAINS)
        with self.client.post(
            "/scan",
            json={"domain": domain, "lang": "fr"},
            name="/scan [anon]",
            catch_response=True,
            timeout=12,
        ) as r:
            if r.status_code == 429:
                # Rate limit attendu — pas une erreur de notre côté
                r.success()
            elif r.status_code >= 500:
                r.failure(f"Server error {r.status_code}")


# ─── Profil 2 : Utilisateur connecté (sans scan) ─────────────────────────────

class AuthUser(HttpUser):
    """
    Simule un utilisateur qui consulte son espace client.
    Représente ~35% du trafic.
    """
    weight    = 2
    wait_time = between(2, 6)

    def on_start(self):
        """Login une seule fois, conserver le token JWT."""
        self.token = None
        self._login()

    def _login(self):
        """Authentification — récupère et stocke le JWT."""
        r = self.client.post(
            "/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            name="/auth/login",
        )
        data = _json(r)
        if r.status_code == 200 and "access_token" in data:
            self.token = data["access_token"]
            self.client.headers.update({"Authorization": f"Bearer {self.token}"})
        elif r.status_code == 429:
            # Rate limit login — attendre avant de réessayer
            time.sleep(5)
        # Si login échoue (ex : compte inexistant), on continue sans auth
        # → les endpoints authentifiés retourneront 401 (comptés comme failure normalement)

    def _auth_headers(self) -> dict:
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    @task(6)
    def check_me(self):
        """GET /auth/me — appelé à chaque chargement de page connectée."""
        self.client.get("/auth/me", name="/auth/me", headers=self._auth_headers())

    @task(5)
    def scan_limits(self):
        """Quotas de scan de l'utilisateur connecté."""
        self.client.get(
            "/scan/limits",
            name="/scan/limits [auth]",
            headers=self._auth_headers(),
        )

    @task(4)
    def scan_history(self):
        """Historique des scans — HistoryPage."""
        self.client.get(
            "/scans/history?limit=20",
            name="/scans/history",
            headers=self._auth_headers(),
        )

    @task(3)
    def monitoring_status(self):
        """Statut surveillance — ClientSpace monitoring tab."""
        self.client.get(
            "/monitoring/status",
            name="/monitoring/status",
            headers=self._auth_headers(),
        )

    @task(3)
    def monitoring_domains(self):
        """Liste des domaines surveillés."""
        self.client.get(
            "/monitoring/domains",
            name="/monitoring/domains",
            headers=self._auth_headers(),
        )

    @task(2)
    def payment_status(self):
        """Statut abonnement Stripe — ClientSpace billing tab."""
        self.client.get(
            "/payment/status",
            name="/payment/status",
            headers=self._auth_headers(),
        )

    @task(1)
    def public_stats(self):
        """Stats industrie — même que les anonymes."""
        self.client.get("/public/stats", name="/public/stats")


# ─── Profil 3 : Utilisateur qui scanne activement ────────────────────────────

class ScanUser(HttpUser):
    """
    Simule un utilisateur Pro qui lance des scans fréquemment.
    Représente ~5% du trafic mais génère le plus de charge CPU.
    Wait_time long pour respecter les rate limits.
    """
    weight    = 1
    wait_time = between(10, 30)  # scans espacés — Pro = 50/jour

    def on_start(self):
        self.token = None
        r = self.client.post(
            "/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            name="/auth/login",
        )
        data = _json(r)
        if r.status_code == 200 and "access_token" in data:
            self.token = data["access_token"]
            self.client.headers.update({"Authorization": f"Bearer {self.token}"})

    @task(3)
    def authenticated_scan(self):
        """Scan complet avec sauvegarde en historique."""
        domain = random.choice(_SAFE_DOMAINS)
        with self.client.post(
            "/scan",
            json={"domain": domain, "lang": "fr"},
            name="/scan [auth]",
            catch_response=True,
            timeout=12,
        ) as r:
            if r.status_code == 429:
                r.success()  # rate limit attendu, pas une erreur
            elif r.status_code >= 500:
                r.failure(f"Server error {r.status_code}")
            elif r.status_code == 200:
                data = _json(r)
                # Vérification minimale de la structure de réponse
                if "score" not in data:
                    r.failure("Réponse scan sans champ 'score'")

    @task(1)
    def scan_history_after_scan(self):
        """Consulter l'historique après un scan."""
        self.client.get(
            "/scans/history?limit=5",
            name="/scans/history [post-scan]",
        )


# ─── Événements Locust (affichage custom) ─────────────────────────────────────

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("\n" + "="*60)
    print("🚀 CyberHealth Load Test démarré")
    print(f"   Host     : {environment.host}")
    print(f"   Domain   : {TEST_DOMAIN}")
    print(f"   Profils  : AnonUser×3, AuthUser×2, ScanUser×1")
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
