from fastapi import APIRouter

from app.api.v1 import accounts, audit, auth, dashboard, documents, exports, health, review, settings, transfers

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(accounts.router)
router.include_router(documents.router)
router.include_router(review.router)
router.include_router(transfers.router)
router.include_router(exports.router)
router.include_router(audit.router)
router.include_router(settings.router)
router.include_router(dashboard.router)
router.include_router(health.router)
