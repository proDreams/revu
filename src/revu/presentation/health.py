from fastapi import APIRouter

health_router = APIRouter(tags=["Health"])


@health_router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe for docker-compose and reverse proxies."""
    return {"status": "ok"}
