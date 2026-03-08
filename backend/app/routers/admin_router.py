"""
Admin Router — Gestion des utilisateurs + métriques business
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, distinct
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, ScanHistory, Payment, BlogLink
from app.routers.auth_router import get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])

PLAN_PRICES: dict[str, int] = {
    "starter": 990,
    "pro":     1990,
    "dev":     2990,
}


# ─── Guard admin ──────────────────────────────────────────────────────────────

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs WEZEA")
    return current_user


# ─── Schemas ──────────────────────────────────────────────────────────────────

class UserAdminView(BaseModel):
    id: int
    email: str
    plan: str
    is_active: bool
    is_admin: bool
    scan_count: int
    created_at: str


class UpdateUserRequest(BaseModel):
    plan: Optional[str] = None
    is_active: Optional[bool] = None


# ─── Endpoints — Users ────────────────────────────────────────────────────────

@router.get("/users", response_model=List[UserAdminView])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Liste tous les utilisateurs avec leur nombre de scans."""
    users = db.query(User).order_by(User.created_at.desc()).all()
    result = []
    for u in users:
        scan_count = db.query(func.count(ScanHistory.id)).filter(
            ScanHistory.user_id == u.id
        ).scalar() or 0
        result.append(UserAdminView(
            id=u.id,
            email=u.email,
            plan=u.plan,
            is_active=u.is_active,
            is_admin=bool(u.is_admin),
            scan_count=scan_count,
            created_at=u.created_at.isoformat(),
        ))
    return result


@router.patch("/users/{user_id}", response_model=UserAdminView)
def update_user(
    user_id: int,
    req: UpdateUserRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Modifie le plan ou le statut d'un utilisateur."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas modifier votre propre compte ici")

    if req.plan is not None:
        if req.plan not in ("free", "starter", "pro", "dev"):
            raise HTTPException(status_code=400, detail="Plan invalide (free / starter / pro / dev)")
        user.plan = req.plan
        if req.plan == "free":
            user.subscription_status = None
        elif user.subscription_status not in ("active",):
            user.subscription_status = "active"
    if req.is_active is not None:
        user.is_active = req.is_active

    db.commit()
    db.refresh(user)

    scan_count = db.query(func.count(ScanHistory.id)).filter(
        ScanHistory.user_id == user.id
    ).scalar() or 0

    return UserAdminView(
        id=user.id, email=user.email, plan=user.plan,
        is_active=user.is_active, is_admin=bool(user.is_admin), scan_count=scan_count,
        created_at=user.created_at.isoformat(),
    )


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Supprime un utilisateur et tout son historique."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas supprimer votre propre compte")

    db.delete(user)
    db.commit()
    return None


# ─── Endpoints — Stats (legacy) ───────────────────────────────────────────────

@router.get("/stats")
def admin_stats(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Statistiques globales de la plateforme (version compacte)."""
    total_users  = db.query(func.count(User.id)).scalar() or 0
    active_users = db.query(func.count(User.id)).filter(User.is_active == True).scalar() or 0
    pro_users    = db.query(func.count(User.id)).filter(User.plan.in_(["starter", "pro"])).scalar() or 0
    total_scans  = db.query(func.count(ScanHistory.id)).scalar() or 0
    return {
        "total_users":  total_users,
        "active_users": active_users,
        "pro_users":    pro_users,
        "free_users":   total_users - pro_users,
        "total_scans":  total_scans,
    }


# ─── Endpoints — Metrics (business dashboard) ─────────────────────────────────

@router.get("/metrics")
def admin_metrics(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Métriques business complètes : MRR, conversions, churns, revenus, tendances."""
    now         = datetime.now(timezone.utc)
    thirty_ago  = now - timedelta(days=30)
    fourteen_ago = now - timedelta(days=14)
    seven_ago   = now - timedelta(days=7)

    # ── MRR ──────────────────────────────────────────────────────────────────
    mrr_cents = 0
    for plan, price in PLAN_PRICES.items():
        count = db.query(func.count(User.id)).filter(
            User.plan == plan,
            User.subscription_status == "active",
        ).scalar() or 0
        mrr_cents += count * price

    # ── Plan breakdown ────────────────────────────────────────────────────────
    plan_breakdown: dict[str, int] = {}
    for p in ("free", "starter", "pro", "dev"):
        plan_breakdown[p] = db.query(func.count(User.id)).filter(User.plan == p).scalar() or 0

    # ── Revenue last 30d ──────────────────────────────────────────────────────
    revenue_30d = db.query(func.sum(Payment.amount)).filter(
        Payment.status == "completed",
        Payment.paid_at >= thirty_ago,
    ).scalar() or 0

    # ── Conversions last 30d (paiements complétés) ────────────────────────────
    conversions_30d = db.query(func.count(Payment.id)).filter(
        Payment.status == "completed",
        Payment.paid_at >= thirty_ago,
    ).scalar() or 0

    # ── Churns last 30d ───────────────────────────────────────────────────────
    churns_30d = db.query(func.count(User.id)).filter(
        User.subscription_status == "cancelled",
        User.updated_at >= thirty_ago,
    ).scalar() or 0

    # ── New signups last 30d ──────────────────────────────────────────────────
    new_signups_30d = db.query(func.count(User.id)).filter(
        User.created_at >= thirty_ago,
    ).scalar() or 0

    # ── Active users (at least 1 scan in last 7d) ─────────────────────────────
    active_7d = db.query(func.count(distinct(ScanHistory.user_id))).filter(
        ScanHistory.user_id.isnot(None),
        ScanHistory.created_at >= seven_ago,
    ).scalar() or 0

    # ── Conversion rate (paid / total) ────────────────────────────────────────
    total_users = db.query(func.count(User.id)).scalar() or 1
    paid_users  = sum(plan_breakdown.get(p, 0) for p in ("starter", "pro"))
    conversion_rate = round(paid_users / total_users * 100, 1)

    # ── Signups per day (last 30d) ────────────────────────────────────────────
    signups_rows = (
        db.query(
            func.date(User.created_at).label("d"),
            func.count(User.id).label("n"),
        )
        .filter(User.created_at >= thirty_ago)
        .group_by(func.date(User.created_at))
        .order_by("d")
        .all()
    )

    # ── Scans per day (last 14d) ──────────────────────────────────────────────
    scans_rows = (
        db.query(
            func.date(ScanHistory.created_at).label("d"),
            func.count(ScanHistory.id).label("n"),
        )
        .filter(ScanHistory.created_at >= fourteen_ago)
        .group_by(func.date(ScanHistory.created_at))
        .order_by("d")
        .all()
    )

    return {
        "mrr_cents":        mrr_cents,
        "plan_breakdown":   plan_breakdown,
        "revenue_30d_cents": revenue_30d,
        "conversions_30d":  conversions_30d,
        "churns_30d":       churns_30d,
        "new_signups_30d":  new_signups_30d,
        "active_users_7d":  active_7d,
        "conversion_rate":  conversion_rate,
        "signups_last_30d": [{"date": str(r.d), "count": r.n} for r in signups_rows],
        "scans_last_14d":   [{"date": str(r.d), "count": r.n} for r in scans_rows],
    }


# ─── Blog Links ───────────────────────────────────────────────────────────────

class BlogLinkCreate(BaseModel):
    match_keyword: str
    article_title: str
    article_url:   str


class BlogLinkUpdate(BaseModel):
    match_keyword: Optional[str] = None
    article_title: Optional[str] = None
    article_url:   Optional[str] = None


class BlogLinkView(BaseModel):
    id:            int
    match_keyword: str
    article_title: str
    article_url:   str

    class Config:
        from_attributes = True


@router.get("/blog-links", response_model=List[BlogLinkView])
def list_blog_links(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return db.query(BlogLink).order_by(BlogLink.created_at.desc()).all()


@router.post("/blog-links", response_model=BlogLinkView, status_code=201)
def create_blog_link(
    body: BlogLinkCreate,
    db:   Session = Depends(get_db),
    _:    User = Depends(require_admin),
):
    link = BlogLink(
        match_keyword=body.match_keyword.strip(),
        article_title=body.article_title.strip(),
        article_url=body.article_url.strip(),
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


@router.put("/blog-links/{link_id}", response_model=BlogLinkView)
def update_blog_link(
    link_id: int,
    body: BlogLinkUpdate,
    db:   Session = Depends(get_db),
    _:    User = Depends(require_admin),
):
    link = db.query(BlogLink).filter(BlogLink.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Lien introuvable")
    for field, value in body.dict(exclude_none=True).items():
        setattr(link, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(link)
    return link


@router.delete("/blog-links/{link_id}", status_code=204)
def delete_blog_link(
    link_id: int,
    db:   Session = Depends(get_db),
    _:    User = Depends(require_admin),
):
    link = db.query(BlogLink).filter(BlogLink.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Lien introuvable")
    db.delete(link)
    db.commit()
