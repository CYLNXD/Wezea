# Load Tests — CyberHealth Scanner

## Installation

```bash
pip install locust==2.32.3
```

## Lancement rapide (UI interactive)

```bash
cd load_tests
locust -f locustfile.py --host=https://scan.wezea.net
# Ouvrir http://localhost:8089
# Users: 50 | Spawn rate: 5/s | Run time: 2min
```

## Lancement headless (CI / terminal)

```bash
locust -f locustfile.py \
  --host=https://scan.wezea.net \
  --users=50 \
  --spawn-rate=5 \
  --run-time=2m \
  --headless \
  --csv=results/run_$(date +%Y%m%d_%H%M)
```

## Variables d'environnement

| Variable          | Défaut                  | Description                        |
|-------------------|-------------------------|------------------------------------|
| `LOCUST_EMAIL`    | `loadtest@example.com`  | Email d'un compte de test existant |
| `LOCUST_PASSWORD` | `LoadTest2026!`         | Mot de passe correspondant         |
| `LOCUST_DOMAIN`   | `example.com`           | Domaine à scanner                  |

> **Important** : créer le compte de test manuellement via `wezea.net` avant
> de lancer les tests. Un compte plan Free suffit.

## Profils simulés

| Profil     | Poids | Wait time | Actions principales                       |
|------------|-------|-----------|-------------------------------------------|
| `AnonUser` | ×3    | 1–4s      | scan/limits, public/stats, /scan anonyme  |
| `AuthUser` | ×2    | 2–6s      | auth/me, history, monitoring, payment     |
| `ScanUser` | ×1    | 10–30s    | /scan authentifié (respecte rate limits)  |

## Objectifs de performance

| Endpoint          | p50   | p95   | Erreurs |
|-------------------|-------|-------|---------|
| `/health`         | <10ms | <50ms | 0%      |
| `/scan/limits`    | <30ms | <100ms| 0%      |
| `/public/stats`   | <50ms | <150ms| 0%      |
| `/auth/me`        | <50ms | <200ms| 0%      |
| `/scans/history`  | <100ms| <300ms| 0%      |
| `/scan`           | <3s   | <8s   | <1% (hors 429) |

## Interprétation des résultats

- **429 sur /scan** → Normal, rate limit en action. Compté comme succès.
- **p95 > 500ms sur GET légers** → Problème SQLite ou CPU saturé.
- **p95 > 8s sur /scan** → Timeout réseau externe (DNS/SSL lents), pas forcément un bug.
- **Erreurs > 1%** → Investiguer avec `journalctl -u cyberhealth-api -n 100`.
