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
from app.models import User, ScanHistory, Payment, BlogLink, BlogArticle
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
    mfa_enabled: bool = False


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
    from sqlalchemy.orm import aliased
    scan_count_sq = (
        db.query(ScanHistory.user_id, func.count(ScanHistory.id).label("cnt"))
        .group_by(ScanHistory.user_id)
        .subquery()
    )
    rows = (
        db.query(User, scan_count_sq.c.cnt)
        .outerjoin(scan_count_sq, User.id == scan_count_sq.c.user_id)
        .order_by(User.created_at.desc())
        .all()
    )
    return [
        UserAdminView(
            id=u.id,
            email=u.email,
            plan=u.plan,
            is_active=u.is_active,
            is_admin=bool(u.is_admin),
            scan_count=cnt or 0,
            created_at=u.created_at.isoformat(),
            mfa_enabled=bool(u.mfa_enabled),
        )
        for u, cnt in rows
    ]


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
        created_at=user.created_at.isoformat(), mfa_enabled=bool(user.mfa_enabled),
    )


@router.post("/users/{user_id}/reset-2fa", status_code=200)
def admin_reset_2fa(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Réinitialise (désactive) la 2FA d'un utilisateur — action admin uniquement."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if not user.mfa_enabled:
        raise HTTPException(status_code=400, detail="La 2FA n'est pas activée sur ce compte.")
    user.mfa_enabled = False
    user.mfa_secret  = None
    db.commit()
    return {"status": "ok", "message": f"2FA réinitialisée pour {user.email}"}


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
    pro_users    = db.query(func.count(User.id)).filter(User.plan.in_(["starter", "pro", "dev"])).scalar() or 0
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
    paid_users  = sum(plan_breakdown.get(p, 0) for p in ("starter", "pro", "dev"))
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

    model_config = {"from_attributes": True}


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
    for field, value in body.model_dump(exclude_none=True).items():
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


# ─── Blog Articles ─────────────────────────────────────────────────────────────

class ArticleCreate(BaseModel):
    slug:             str
    title:            str
    content_md:       str
    meta_description: Optional[str] = None
    category:         Optional[str] = None
    tags:             Optional[str] = None
    author:           Optional[str] = "Wezea"
    reading_time_min: Optional[int] = 5
    is_published:     Optional[bool] = False


class ArticleUpdate(BaseModel):
    slug:             Optional[str] = None
    title:            Optional[str] = None
    content_md:       Optional[str] = None
    meta_description: Optional[str] = None
    category:         Optional[str] = None
    tags:             Optional[str] = None
    author:           Optional[str] = None
    reading_time_min: Optional[int] = None
    is_published:     Optional[bool] = None


class ArticleView(BaseModel):
    id:               int
    slug:             str
    title:            str
    meta_description: Optional[str]
    content_md:       str
    category:         Optional[str]
    tags:             Optional[str]
    author:           Optional[str]
    reading_time_min: Optional[int]
    is_published:     bool
    published_at:     Optional[datetime]
    created_at:       Optional[datetime]
    updated_at:       Optional[datetime]

    model_config = {"from_attributes": True}


@router.get("/articles", response_model=List[ArticleView])
def list_articles(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return db.query(BlogArticle).order_by(BlogArticle.created_at.desc()).all()


@router.post("/articles", response_model=ArticleView, status_code=201)
def create_article(
    body: ArticleCreate,
    db:   Session = Depends(get_db),
    _:    User = Depends(require_admin),
):
    existing = db.query(BlogArticle).filter(BlogArticle.slug == body.slug.strip()).first()
    if existing:
        raise HTTPException(status_code=409, detail="Slug déjà utilisé")
    article = BlogArticle(
        slug=body.slug.strip(),
        title=body.title.strip(),
        content_md=body.content_md,
        meta_description=body.meta_description,
        category=body.category,
        tags=body.tags,
        author=(body.author or "Wezea").strip(),
        reading_time_min=body.reading_time_min or 5,
        is_published=body.is_published or False,
        published_at=datetime.now(timezone.utc) if body.is_published else None,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return article


@router.put("/articles/{article_id}", response_model=ArticleView)
def update_article(
    article_id: int,
    body: ArticleUpdate,
    db:   Session = Depends(get_db),
    _:    User = Depends(require_admin),
):
    article = db.query(BlogArticle).filter(BlogArticle.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article introuvable")
    data = body.model_dump(exclude_none=True)
    if "slug" in data:
        dup = db.query(BlogArticle).filter(
            BlogArticle.slug == data["slug"].strip(),
            BlogArticle.id != article_id,
        ).first()
        if dup:
            raise HTTPException(status_code=409, detail="Slug déjà utilisé")
    if "is_published" in data and data["is_published"] and not article.is_published:
        article.published_at = datetime.now(timezone.utc)
    for field, value in data.items():
        setattr(article, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(article)
    return article


@router.delete("/articles/{article_id}", status_code=204)
def delete_article(
    article_id: int,
    db:   Session = Depends(get_db),
    _:    User = Depends(require_admin),
):
    article = db.query(BlogArticle).filter(BlogArticle.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article introuvable")
    db.delete(article)
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Purge RGPD — scans anciens
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/purge-scans")
def purge_scans_dry_run(
    retention_days: int = 90,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Aperçu (dry-run) : combien de scans seraient supprimés."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    count = db.query(func.count(ScanHistory.id)).filter(ScanHistory.created_at < cutoff).scalar()
    return {
        "dry_run": True,
        "retention_days": retention_days,
        "cutoff": cutoff.isoformat(),
        "scans_to_delete": count,
    }


@router.delete("/purge-scans", status_code=200)
def purge_scans_execute(
    retention_days: int = 90,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Exécute la purge des scans plus anciens que retention_days.
    Retourne le nombre de scans supprimés.
    """
    from sqlalchemy import delete as sa_delete
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    result = db.execute(sa_delete(ScanHistory).where(ScanHistory.created_at < cutoff))
    db.commit()
    deleted = result.rowcount
    return {
        "dry_run": False,
        "retention_days": retention_days,
        "scans_deleted": deleted,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Métriques de performance API
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/metrics/performance")
def get_api_performance(
    _: User = Depends(require_admin),
):
    """Retourne les statistiques de performance par endpoint (p50/p95/p99/avg).
    Basé sur un buffer rolling en mémoire (2000 dernières requêtes).
    """
    from app.metrics import get_performance_stats
    return get_performance_stats()
