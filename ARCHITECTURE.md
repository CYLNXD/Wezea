# CyberHealth Scanner — Architecture MVP

```
cyberhealth-scanner/
│
├── backend/                          # FastAPI (Python 3.12+)
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                   # API FastAPI : endpoints /scan, /report/request
│   │   ├── scanner.py                # ★ Moteur de scan (AuditManager + Auditeurs)
│   │   │
│   │   ├── auditors/                 # (étape 2) Modules extensibles
│   │   │   ├── __init__.py
│   │   │   ├── http_headers.py       # → X-Frame-Options, CSP, HSTS…
│   │   │   ├── whois.py              # → Expiration domaine, registrar
│   │   │   └── subdomain.py          # → Énumération passive (crt.sh)
│   │   │
│   │   ├── services/
│   │   │   ├── email_service.py      # Envoi du rapport PDF par email
│   │   │   ├── crm_service.py        # Intégration HubSpot / Zapier
│   │   │   └── pdf_generator.py      # Génération rapport WeasyPrint
│   │   │
│   │   └── models/
│   │       ├── scan.py               # Modèles SQLAlchemy (persistance)
│   │       └── lead.py               # Modèle Lead (CRM)
│   │
│   ├── tests/
│   │   ├── test_scanner.py
│   │   └── test_api.py
│   │
│   ├── requirements.txt
│   ├── .env.example                  # Template variables d'environnement
│   └── Dockerfile
│
├── frontend/                         # React 18 + Vite + Tailwind CSS
│   ├── src/
│   │   ├── components/
│   │   │   ├── SearchBar.jsx         # Barre de recherche domaine
│   │   │   ├── ScanConsole.jsx       # Console simulant les étapes de scan
│   │   │   ├── SecurityGauge.jsx     # Jauge circulaire (Score 0-100)
│   │   │   ├── FindingCard.jsx       # Carte résultat (Vert/Orange/Rouge)
│   │   │   ├── PortMap.jsx           # Visualisation ports ouverts
│   │   │   └── LeadGenModal.jsx      # CTA email rapport complet
│   │   │
│   │   ├── pages/
│   │   │   ├── Home.jsx              # Landing + barre de recherche
│   │   │   └── Dashboard.jsx         # Résultats du scan
│   │   │
│   │   ├── hooks/
│   │   │   └── useScan.js            # Hook React Query pour /scan
│   │   │
│   │   └── lib/
│   │       ├── api.js                # Client Axios
│   │       └── score.js              # Helpers couleurs/labels
│   │
│   ├── tailwind.config.js
│   └── package.json
│
├── docker-compose.yml                # Dev : API + Redis + PostgreSQL
└── README.md
```

---

## Moteur de Score — Logique métier

```
SecurityScore = 100 - Σ(pénalités des findings)

Catégorie              | Condition                    | Pénalité
-----------------------|------------------------------|----------
DNS — SPF              | Manquant ou +all             | -15 pts
DNS — DMARC            | Manquant                     | -20 pts
DNS — DMARC            | Politique p=none             |  -8 pts
SSL — Certificat       | Expiré, invalide, auto-signé | -30 pts
SSL — TLS              | Version < 1.2                | -10 pts
Ports — RDP/SMB        | 3389 ou 445 ouverts          | -40 pts ⚠ CRITIQUE
Ports — FTP/Telnet     | 21 ou 23 ouverts             | -20 pts
Ports — Bases données  | 3306 ou 5432 ouverts         | -25 pts

Niveau de risque :
  80-100 → LOW      (Faible)
  60-79  → MEDIUM   (Modéré)
  40-59  → HIGH     (Élevé)
   0-39  → CRITICAL (Critique)
```

---

## Extensibilité — Ajouter un nouveau module de scan

```python
# Exemple : Auditeur HTTP Security Headers
from app.scanner import BaseAuditor, Finding

class HTTPHeaderAuditor(BaseAuditor):
    async def audit(self) -> list[Finding]:
        # 1. Faire une requête HEAD sur le domaine
        # 2. Vérifier X-Frame-Options, Content-Security-Policy, HSTS…
        # 3. Retourner les findings
        ...

# Dans AuditManager.run() :
self._auditors.append(HTTPHeaderAuditor(self.domain))
```

---

## Flux de données

```
Client → POST /scan {domain}
           │
           ▼
    Validation (Pydantic)
           │
           ▼
    AuditManager.run()
    ┌──────┬──────────┬────────────┐
    │ DNS  │   SSL    │   Ports    │  (parallèle, asyncio.gather)
    └──────┴──────────┴────────────┘
           │
           ▼
    ScoreEngine.compute()
           │
           ▼
    ScanResult → JSON Response
           │
           ▼ (si /report/request)
    LeadGen → CRM + PDF Email
```
