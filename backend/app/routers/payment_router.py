"""
Payment Router — Stripe Subscriptions
=======================================
Endpoints :
    POST /payment/create-checkout  → Crée une Stripe Checkout Session (starter ou pro)
    POST /payment/webhook          → Reçoit les événements Stripe
    GET  /payment/status           → Statut abonnement de l'utilisateur connecté
    GET  /payment/portal           → Génère un lien Stripe Customer Portal
    POST /payment/cancel           → Annule l'abonnement (fin de période)

Plans :
    starter  → 9,90 €/mois  — scans illimités, PDF avancé, monitoring (sans API)
    pro      → 19,90 €/mois — tout le Starter + accès API
"""

import os
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Payment
from app.routers.auth_router import get_current_user
from app.services.brevo_service import send_upgrade_email
import asyncio as _asyncio

router = APIRouter(prefix="/payment", tags=["payment"])

# ─── Configuration ────────────────────────────────────────────────────────────

stripe.api_key             = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_STARTER_PRICE_ID    = os.getenv("STRIPE_STARTER_PRICE_ID", "price_1T6vho3g9OojnV1te1YOoW2P")
STRIPE_PRO_PRICE_ID        = os.getenv("STRIPE_PRO_PRICE_ID",     "price_1T6sZ93g9OojnV1txjJJPtys")
STRIPE_WEBHOOK_SECRET      = os.getenv("STRIPE_WEBHOOK_SECRET",   "")

if not STRIPE_WEBHOOK_SECRET:
    import sys
    print(
        "⚠  AVERTISSEMENT SÉCURITÉ : STRIPE_WEBHOOK_SECRET absent.\n"
        "   L'endpoint /payment/webhook refusera toutes les requêtes Stripe.\n"
        "   Récupérez-le dans le Dashboard Stripe → Webhooks → Signing secret.\n"
        "   Ajoutez STRIPE_WEBHOOK_SECRET=whsec_... dans le fichier .env du backend.",
        file=sys.stderr,
    )
    # Pas de sys.exit — les autres endpoints (scan, login, etc.) continuent de fonctionner

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://wezea.net")

# Map price_id → plan name
_PRICE_TO_PLAN: dict[str, str] = {
    STRIPE_STARTER_PRICE_ID: "starter",
    STRIPE_PRO_PRICE_ID:     "pro",
}
_PLAN_AMOUNTS: dict[str, int] = {
    "starter": 990,
    "pro":     1990,
}


# ─── Schémas ──────────────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: str = "starter"   # "starter" | "pro"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _price_id_for_plan(plan: str) -> str:
    return STRIPE_STARTER_PRICE_ID if plan == "starter" else STRIPE_PRO_PRICE_ID


def _plan_from_subscription(subscription_id: str) -> str:
    """Détermine le plan (starter/pro) depuis l'ID Stripe Subscription."""
    try:
        sub   = stripe.Subscription.retrieve(subscription_id, expand=["items.data.price"])
        items = sub.get("items", {}).get("data", [])
        if items:
            price_id = items[0].get("price", {}).get("id", "")
            return _PRICE_TO_PLAN.get(price_id, "pro")
    except Exception:
        pass
    return "pro"


def _uid_from_subscription(subscription_id: str) -> str | None:
    try:
        sub = stripe.Subscription.retrieve(subscription_id)
        return sub.get("metadata", {}).get("user_id")
    except Exception:
        return None


def _ensure_plan_from_subscription(subscription_id: str, db: Session) -> None:
    """Active/maintient le bon plan pour l'utilisateur lié à cet abonnement."""
    try:
        uid  = _uid_from_subscription(subscription_id)
        plan = _plan_from_subscription(subscription_id)
        if uid:
            user = db.query(User).filter(User.id == int(uid)).first()
            if user and (user.plan != plan or user.subscription_status != "active"):
                user.plan                = plan
                user.subscription_status = "active"
                db.commit()
    except Exception:
        pass


def _downgrade_from_subscription(subscription_id: str, db: Session) -> None:
    """Repasse l'utilisateur en plan Free."""
    try:
        uid = _uid_from_subscription(subscription_id)
        if uid:
            user = db.query(User).filter(User.id == int(uid)).first()
            if user:
                user.plan                = "free"
                user.subscription_status = "cancelled"
                db.commit()
    except Exception:
        pass


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post(
    "/create-checkout",
    summary     = "Créer une Stripe Checkout Session",
    description = "Crée une session d'abonnement Stripe (starter ou pro) et retourne l'URL de checkout.",
)
async def create_checkout(
    body:         CheckoutRequest = CheckoutRequest(),
    current_user: User            = Depends(get_current_user),
    db:           Session         = Depends(get_db),
):
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Paiement temporairement indisponible.")

    plan = body.plan if body.plan in ("starter", "pro") else "starter"

    # Déjà abonné au même plan ou supérieur
    if current_user.plan == plan and current_user.subscription_status == "active":
        raise HTTPException(status_code=400, detail=f"Vous êtes déjà abonné au plan {plan.capitalize()}.")
    if current_user.plan == "pro" and plan == "starter" and current_user.subscription_status == "active":
        raise HTTPException(status_code=400, detail="Vous avez déjà un plan supérieur (Pro).")

    price_id = _price_id_for_plan(plan)

    try:
        session = stripe.checkout.Session.create(
            mode               = "subscription",
            customer_email     = current_user.email,
            line_items         = [{"price": price_id, "quantity": 1}],
            success_url        = f"{FRONTEND_URL}?payment=success",
            cancel_url         = f"{FRONTEND_URL}?payment=cancelled",
            metadata           = {"user_id": str(current_user.id), "plan": plan},
            subscription_data  = {"metadata": {"user_id": str(current_user.id), "plan": plan}},
            allow_promotion_codes    = True,
            billing_address_collection = "required",
            tax_id_collection          = {"enabled": True},
        )
    except stripe.StripeError as exc:
        raise HTTPException(status_code=502, detail=f"Erreur Stripe : {exc.user_message or str(exc)}")

    payment = Payment(
        user_id           = current_user.id,
        stripe_session_id = session.id,
        amount            = _PLAN_AMOUNTS[plan],
        currency          = "EUR",
        status            = "pending",
    )
    db.add(payment)
    db.commit()

    return {"checkout_url": session.url, "session_id": session.id}


@router.post(
    "/webhook",
    summary     = "Webhook Stripe",
    description = "Reçoit et traite les événements Stripe (abonnements, paiements).",
    status_code = status.HTTP_200_OK,
)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Webhook désactivé : STRIPE_WEBHOOK_SECRET non configuré sur ce serveur.",
        )

    body = await request.body()
    sig  = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(body, sig, STRIPE_WEBHOOK_SECRET)
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Signature webhook invalide.")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Webhook invalide : {exc}")

    event_type = event["type"]
    data       = event["data"]["object"]

    # ── Paiement initial réussi ──────────────────────────────────────────────
    if event_type == "checkout.session.completed":
        user_id    = data.get("metadata", {}).get("user_id")
        plan       = data.get("metadata", {}).get("plan", "pro")
        session_id = data.get("id")

        if user_id:
            user = db.query(User).filter(User.id == int(user_id)).first()
            if user:
                user.plan                    = plan
                user.subscription_status     = "active"
                user.subscription_expires_at = None

        payment = db.query(Payment).filter(Payment.stripe_session_id == session_id).first()
        if payment:
            payment.status  = "completed"
            payment.paid_at = datetime.now(timezone.utc)

        db.commit()

        # ── Email de confirmation d'upgrade ──────────────────────────────────
        if user:
            try:
                _asyncio.create_task(send_upgrade_email(user.email, plan))
            except RuntimeError:
                # Pas de boucle asyncio active (tests, workers sync) → ignorer silencieusement
                pass

    # ── Renouvellement mensuel ───────────────────────────────────────────────
    elif event_type == "invoice.payment_succeeded":
        sub_id = data.get("subscription")
        if sub_id:
            _ensure_plan_from_subscription(sub_id, db)

    # ── Paiement échoué ──────────────────────────────────────────────────────
    elif event_type == "invoice.payment_failed":
        sub_id = data.get("subscription")
        if sub_id:
            _downgrade_from_subscription(sub_id, db)

    # ── Abonnement supprimé / résilié ────────────────────────────────────────
    elif event_type == "customer.subscription.deleted":
        sub_id = data.get("id")
        if sub_id:
            _downgrade_from_subscription(sub_id, db)

    # ── Abonnement mis à jour ────────────────────────────────────────────────
    elif event_type == "customer.subscription.updated":
        sub_id     = data.get("id")
        sub_status = data.get("status")
        if sub_id and sub_status in ("active", "trialing"):
            _ensure_plan_from_subscription(sub_id, db)
        elif sub_id and sub_status in ("canceled", "unpaid", "incomplete_expired"):
            _downgrade_from_subscription(sub_id, db)

    return {"status": "ok"}


@router.get(
    "/status",
    summary = "Statut de l'abonnement",
)
async def subscription_status(current_user: User = Depends(get_current_user)):
    plan      = current_user.plan or "free"
    is_paid   = plan in ("starter", "pro")
    is_active = is_paid and current_user.subscription_status == "active"
    prices    = {"free": 0.0, "starter": 9.90, "pro": 19.90}

    return {
        "plan":                    plan,
        "subscription_status":     current_user.subscription_status or "none",
        "subscription_expires_at": (
            current_user.subscription_expires_at.isoformat()
            if current_user.subscription_expires_at else None
        ),
        "is_active":               is_active,
        "price_monthly":           prices.get(plan, 0.0),
        "currency":                "EUR",
    }


@router.get(
    "/portal",
    summary     = "Stripe Customer Portal",
    description = "Génère un lien vers le portail Stripe pour gérer l'abonnement.",
)
async def customer_portal(
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    if current_user.plan not in ("starter", "pro") or current_user.subscription_status != "active":
        raise HTTPException(status_code=400, detail="Aucun abonnement actif.")

    last_payment = (
        db.query(Payment)
        .filter(Payment.user_id == current_user.id, Payment.status == "completed")
        .order_by(Payment.paid_at.desc())
        .first()
    )
    customer_id = None

    # 1. Chercher via la session Stripe
    if last_payment:
        try:
            checkout_session = stripe.checkout.Session.retrieve(last_payment.stripe_session_id)
            customer_id      = checkout_session.get("customer")
        except stripe.StripeError:
            pass

    # 2. Fallback : chercher le customer par email
    if not customer_id:
        try:
            customers = stripe.Customer.list(email=current_user.email, limit=1)
            if customers.data:
                customer_id = customers.data[0].id
        except stripe.StripeError:
            pass

    if not customer_id:
        raise HTTPException(
            status_code=404,
            detail="Client Stripe introuvable. Assurez-vous d'avoir effectué un paiement via Stripe."
        )

    try:
        portal = stripe.billing_portal.Session.create(
            customer   = customer_id,
            return_url = FRONTEND_URL,
        )
        return {"portal_url": portal.url}
    except stripe.StripeError as exc:
        raise HTTPException(status_code=502, detail=f"Erreur Stripe : {exc.user_message or str(exc)}")


@router.post(
    "/cancel",
    summary = "Annuler l'abonnement",
)
async def cancel_subscription(
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    if current_user.plan not in ("starter", "pro") or current_user.subscription_status != "active":
        raise HTTPException(status_code=400, detail="Aucun abonnement actif à annuler.")

    last_payment = (
        db.query(Payment)
        .filter(Payment.user_id == current_user.id, Payment.status == "completed")
        .order_by(Payment.paid_at.desc())
        .first()
    )

    if last_payment:
        try:
            session = stripe.checkout.Session.retrieve(last_payment.stripe_session_id)
            sub_id  = session.get("subscription")
            if sub_id:
                stripe.Subscription.modify(sub_id, cancel_at_period_end=True)
        except stripe.StripeError:
            pass

    current_user.subscription_status = "cancelled"
    db.commit()

    plan_name = "Starter" if current_user.plan == "starter" else "Pro"
    return {
        "status":  "cancelled",
        "message": f"Abonnement {plan_name} annulé. Votre accès reste actif jusqu'à la fin de la période en cours.",
    }
