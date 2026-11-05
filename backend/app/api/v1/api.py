"""API v1 router assembly."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    ai,
    analytics,
    auth,
    brokers,
    contracts,
    deals,
    exchange_rates,
    exports,
    health,
    meta,
    participants,
    statistics,
)

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(deals.router, prefix="/deals", tags=["deals"])
api_router.include_router(contracts.router, prefix="/contracts", tags=["contracts"])
api_router.include_router(brokers.router, prefix="/brokers", tags=["brokers"])
api_router.include_router(participants.router, prefix="/participants", tags=["participants"])
api_router.include_router(exchange_rates.router, prefix="/exchange-rates", tags=["exchange-rates"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(statistics.router, prefix="/statistics", tags=["statistics"])
api_router.include_router(exports.router, prefix="/export", tags=["export"])
api_router.include_router(meta.router, prefix="/meta", tags=["meta"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
