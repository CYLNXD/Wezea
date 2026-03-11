"""
Payment Router — Stripe Subscriptions
=======================================
Endpoints :
    POST /payment/create-checkout  → Crée une Stripe Checkout Session (starter / pro / dev)
    POST /payment/webhook          → Reçoit les événements Stripe
    GET  /payment/status           → Statut abonnement de l'utilisateur connecté
    GET  /payment/portal           → Génère un lien Stripe Customer Portal
    POST /payment/cancel           → Annule l'abonnement (fin de période)

Plans :
    starter  →  9,90 €/mois  — scans illimités, PDF avancé, monitoring
    pro      → 19,90 €/mois  — tout Starter + monitoring illimité + white-label + webhooks
    dev      → 29,90 €/mois  — tout Pro + API key + Application Scanning
"""

import logging
import os
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.limiter import limiter
from app.models import User, Payment, Partner
from app.routers.auth_router import get_current_user
from app.services.brevo_service import send_upgrade_email
import asyncio as _asyncio

_DEBUG = os.getenv("DEBUG", "false").lower() == "true"

logger = logging.getLogger("cyberhealth.payment")

router = APIRouter(prefix="/payment", tags=["payment"])

# ─── Configuration ────────────────────────────────────────────────────────────

stripe.api_key             = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_STARTER_PRICE_ID    = os.getenv("STRIPE_STARTER_PRICE_ID", "price_1T6vho3g9OojnV1te1YOoW2P")
STRIPE_PRO_PRICE_ID        = os.getenv("STRIPE_PRO_PRICE_ID",     "price_1T6sZ93g9OojnV1txjJJPtys")
STRIPE_DEV_PRICE_ID        = os.getenv("STRIPE_DEV_PRICE_ID",     "price_1T8MpWKOrtMvErGv0iXhORaP")
STRIPE_WEBHOOK_SECRET      = os.getenv("STRIPE_WEBHOOK_SECRET",   "")

if not STRIPE_WEBHOOK_SECRET:
    logger.warning(
        "STRIPE_WEBHOOK_SECRET absent — "
        "l'endpoint /payment/webhook refusera toutes les requêtes Stripe. "
        "Ajoutez STRIPE_WEBHOOK_SECRET=whsec_... dans backend/.env"
    )
    # Pas de sys.exit — les autres endpoints (scan, login, etc.) continuent de fonctionner

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://wezea.net")

# ─── Coupons referral (créés une seule fois, idempotent) ─────────────────────
REFERRAL_COUPON_ID        = "REFERRAL_20PCT"         # -20% premier mois pour les filleuls
PARTNER_REWARD_COUPON_ID  = "PARTNER_REWARD_30PCT"   # -30% un mois pour le partenaire
if stripe.api_key:
    for _cid, _pct, _name in [
        (REFERRAL_COUPON_ID,       20, "Filleul -20% (1er mois)"),
        (PARTNER_REWARD_COUPON_ID, 30, "Récompense partenaire -30%"),
    ]:
        try:
            stripe.Coupon.create(id=_cid, percent_off=_pct, duration="once", name=_name)
            logger.info("Stripe coupon %s created.", _cid)
        except stripe.InvalidRequestError:
            pass  # Already exists — expected on restart
        except Exception as exc:
            logger.warning("Could not create Stripe coupon %s: %s", _cid, exc)

# Map price_id → plan name
_PRICE_TO_PLAN: dict[str, str] = {
    STRIPE_STARTER_PRICE_ID: "starter",
    STRIPE_PRO_PRICE_ID:     "pro",
    STRIPE_DEV_PRICE_ID:     "dev",
}
_PLAN_AMOUNTS: dict[str, int] = {
    "starter": 990,
    "pro":     1990,
    "dev":     2990,
}


# ─── Schémas ──────────────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: str = "starter"   # "starter" | "pro" | "dev"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _price_id_for_plan(plan: str) -> str:
    if plan == "starter":
        return STRIPE_STARTER_PRICE_ID
    if plan == "dev":
        return STRIPE_DEV_PRICE_ID
    return STRIPE_PRO_PRICE_ID


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


def _user_from_subscription(subscription_id: str, db: Session) -> "User | None":
    """
    Trouve l'utilisateur lié à un abonnement Stripe.
    Priorité :
      1. stripe_customer_id stocké en base (robuste même après recréation de DB)
      2. email du customer Stripe → match en base
      3. metadata.user_id (fallback legacy)
    """
    try:
        sub         = stripe.Subscription.retrieve(subscription_id)
        customer_id = sub.get("customer")
        uid_meta    = sub.get("metadata", {}).get("user_id")

        # 1. Par stripe_customer_id
        if customer_id:
            user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
            if user:
                return user

        # 2. Par email du customer Stripe
        if customer_id:
            try:
                customer = stripe.Customer.retrieve(customer_id)
                email    = (customer.get("email") or "").lower().strip()
                if email:
                    user = db.query(User).filter(User.email == email).first()
                    if user:
                        # Mettre à jour stripe_customer_id pour les prochaines fois
                        user.stripe_customer_id = customer_id
                        db.commit()
                        return user
            except Exception:
                pass

        # 3. Fallback legacy : metadata.user_id
        if uid_meta:
            user = db.query(User).filter(User.id == int(uid_meta)).first()
            if user:
                if customer_id and not user.stripe_customer_id:
                    user.stripe_customer_id = customer_id
                    db.commit()
                return user

    except Exception:
        pass
    return None


def _ensure_plan_from_subscription(subscription_id: str, db: Session) -> None:
    """Active/maintient le bon plan pour l'utilisateur lié à cet abonnement."""
    try:
        user = _user_from_subscription(subscription_id, db)
        plan = _plan_from_subscription(subscription_id)
        if user and (user.plan != plan or user.subscription_status != "active"):
            # Sécurité : ne jamais modifier le plan d'un admin via Stripe
            if user.is_admin:
                return
            user.plan                = plan
            user.subscription_status = "active"
            db.commit()
    except Exception:
        pass


def _downgrade_from_subscription(subscription_id: str, db: Session) -> None:
    """Repasse l'utilisateur en plan Free."""
    try:
        user = _user_from_subscription(subscription_id, db)
        if user:
            # Sécurité : ne jamais downgrader un admin via Stripe
            if user.is_admin:
                return
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
@limiter.limit("5/hour")
async def create_checkout(
    request: Request,
    body:         CheckoutRequest = CheckoutRequest(),
    current_user: User            = Depends(get_current_user),
    db:           Session         = Depends(get_db),
):
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Paiement temporairement indisponible.")

    plan = body.plan if body.plan in ("starter", "pro", "dev") else "starter"

    # Hiérarchie des plans pour empêcher un downgrade via checkout
    _plan_rank = {"free": 0, "starter": 1, "pro": 2, "dev": 3}
    current_rank = _plan_rank.get(current_user.plan or "free", 0)
    target_rank  = _plan_rank.get(plan, 1)

    if current_user.plan == plan and current_user.subscription_status == "active":
        raise HTTPException(status_code=400, detail=f"Vous êtes déjà abonné au plan {plan.capitalize()}.")
    if current_rank > target_rank and current_user.subscription_status == "active":
        raise HTTPException(status_code=400, detail=f"Vous avez déjà un plan supérieur ({current_user.plan.capitalize()}).")

    price_id = _price_id_for_plan(plan)

    try:
        is_referred = current_user.referred_by_partner_id is not None

        checkout_kwargs = dict(
            mode               = "subscription",
            customer_email     = current_user.email,
            line_items         = [{"price": price_id, "quantity": 1}],
            success_url        = f"{FRONTEND_URL}?payment=success",
            cancel_url         = f"{FRONTEND_URL}?payment=cancelled",
            metadata           = {"user_id": str(current_user.id), "plan": plan},
            subscription_data  = {"metadata": {"user_id": str(current_user.id), "plan": plan}},
            billing_address_collection = "required",
            tax_id_collection          = {"enabled": True},
        )

        # discounts et allow_promotion_codes sont mutuellement exclusifs dans Stripe
        # Priorité 1 : récompense partenaire -30% (1 mois, une seule fois)
        partner_record = db.query(Partner).filter(
            Partner.email == current_user.email,
            Partner.referral_reward_used == False,  # noqa: E712
        ).first()
        if partner_record:
            has_paid_referral = db.query(User).filter(
                User.referred_by_partner_id == partner_record.id,
                User.plan != "free",
            ).first() is not None
            if has_paid_referral:
                checkout_kwargs["discounts"] = [{"coupon": PARTNER_REWARD_COUPON_ID}]
                partner_record.referral_reward_used = True
                db.commit()
            elif is_referred:
                checkout_kwargs["discounts"] = [{"coupon": REFERRAL_COUPON_ID}]
            else:
                checkout_kwargs["allow_promotion_codes"] = True
        # Priorité 2 : filleul -20% (premier mois)
        elif is_referred:
            checkout_kwargs["discounts"] = [{"coupon": REFERRAL_COUPON_ID}]
        # Sinon : promo codes classiques
        else:
            checkout_kwargs["allow_promotion_codes"] = True

        session = stripe.checkout.Session.create(**checkout_kwargs)
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
        detail = f"Webhook invalide : {exc}" if _DEBUG else "Webhook invalide."
        raise HTTPException(status_code=400, detail=detail)

    event_type = event["type"]
    data       = event["data"]["object"]

    # ── Paiement initial réussi ──────────────────────────────────────────────
    if event_type == "checkout.session.completed":
        user_id     = data.get("metadata", {}).get("user_id")
        plan        = data.get("metadata", {}).get("plan", "pro")
        session_id  = data.get("id")
        customer_id = data.get("customer")

        user = None

        # 1. Par metadata.user_id (nominal)
        if user_id:
            user = db.query(User).filter(User.id == int(user_id)).first()

        # 2. Par stripe_customer_id en DB (fallback si metadata absente/corrompue)
        if not user and customer_id:
            user = db.query(User).filter(User.stripe_customer_id == customer_id).first()

        # 3. Par email du customer Stripe (dernier recours)
        if not user and customer_id:
            try:
                customer = stripe.Customer.retrieve(customer_id)
                email    = (customer.get("email") or "").lower().strip()
                if email:
                    user = db.query(User).filter(User.email == email).first()
            except Exception:
                pass

        if user:
            # Sécurité : ne jamais modifier le plan d'un admin via Stripe
            if not user.is_admin:
                user.plan                    = plan
                user.subscription_status     = "active"
                user.subscription_expires_at = None
            # Stocker le customer Stripe pour résistance à la recréation de DB
            if customer_id and not user.stripe_customer_id:
                user.stripe_customer_id = customer_id

        payment = db.query(Payment).filter(Payment.stripe_session_id == session_id).first()
        if payment:
            payment.status  = "completed"
            payment.paid_at = datetime.now(timezone.utc)

        db.commit()

        # ── Récompense partenaire : -30% sur son prochain mois ─────────────
        if user and user.referred_by_partner_id:
            try:
                partner = db.query(Partner).filter(Partner.id == user.referred_by_partner_id).first()
                if partner and not partner.referral_reward_used:
                    # Le partenaire n'a pas de user_id — on le retrouve par email
                    partner_user = db.query(User).filter(User.email == partner.email).first()
                    if partner_user and partner_user.stripe_customer_id:
                        subs = stripe.Subscription.list(
                            customer=partner_user.stripe_customer_id, status="active", limit=1,
                        )
                        if subs.data:
                            stripe.Subscription.modify(subs.data[0].id, coupon=PARTNER_REWARD_COUPON_ID)
                            partner.referral_reward_used = True
                            db.commit()
            except Exception:
                pass  # Silencieux — sera appliqué au prochain checkout du partenaire

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
    is_paid   = plan in ("starter", "pro", "dev")
    is_active = is_paid and current_user.subscription_status == "active"
    prices    = {"free": 0.0, "starter": 9.90, "pro": 19.90, "dev": 29.90}

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
    if current_user.plan not in ("starter", "pro", "dev") or current_user.subscription_status not in ("active", "cancelling"):
        raise HTTPException(status_code=400, detail="Aucun abonnement actif.")

    last_payment = (
        db.query(Payment)
        .filter(Payment.user_id == current_user.id, Payment.status == "completed")
        .order_by(Payment.paid_at.desc())
        .first()
    )
    customer_id = None

    # 1. stripe_customer_id stocké en DB (le plus rapide et robuste)
    if current_user.stripe_customer_id:
        customer_id = current_user.stripe_customer_id

    # 2. Via la session Stripe (si pas en DB)
    if not customer_id and last_payment:
        try:
            checkout_session = stripe.checkout.Session.retrieve(last_payment.stripe_session_id)
            customer_id      = checkout_session.get("customer")
            if customer_id:
                # Mettre en cache pour la prochaine fois
                current_user.stripe_customer_id = customer_id
                db.commit()
        except stripe.StripeError:
            pass

    # 3. Fallback : chercher le customer par email
    if not customer_id:
        try:
            customers = stripe.Customer.list(email=current_user.email, limit=1)
            if customers.data:
                customer_id = customers.data[0].id
                current_user.stripe_customer_id = customer_id
                db.commit()
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
    if current_user.plan not in ("starter", "pro", "dev") or current_user.subscription_status not in ("active", "cancelling"):
        raise HTTPException(status_code=400, detail="Aucun abonnement actif à annuler.")

    last_payment = (
        db.query(Payment)
        .filter(Payment.user_id == current_user.id, Payment.status == "completed")
        .order_by(Payment.paid_at.desc())
        .first()
    )

    # Récupérer l'ID de subscription Stripe pour programmer la résiliation en fin de période
    sub_id = None

    # 1. Via stripe_customer_id stocké en DB
    if current_user.stripe_customer_id:
        try:
            subs = stripe.Subscription.list(customer=current_user.stripe_customer_id, status="active", limit=1)
            if subs.data:
                sub_id = subs.data[0].id
        except stripe.StripeError:
            pass

    # 2. Via le dernier paiement
    if not sub_id and last_payment:
        try:
            session = stripe.checkout.Session.retrieve(last_payment.stripe_session_id)
            sub_id  = session.get("subscription")
        except stripe.StripeError:
            pass

    if sub_id:
        try:
            stripe.Subscription.modify(sub_id, cancel_at_period_end=True)
        except stripe.StripeError:
            pass

    # Statut "cancelling" : l'accès reste actif, le webhook customer.subscription.deleted
    # passera en "free" à la fin de la période facturation.
    current_user.subscription_status = "cancelling"
    db.commit()

    plan_name = {"starter": "Starter", "pro": "Pro", "dev": "Dev"}.get(current_user.plan, "Pro")
    return {
        "status":  "cancelling",
        "message": f"Abonnement {plan_name} annulé. Votre accès reste actif jusqu'à la fin de la période en cours.",
    }
