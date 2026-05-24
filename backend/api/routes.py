from fastapi import APIRouter

from backend.api.chat import router as chat_router
from backend.api.admin import router as admin_router

router = APIRouter()
router.include_router(chat_router)
router.include_router(admin_router)


@router.get("/")
async def api_root():
    return {
        "message": "Tanger Med / CIRES Technologies RAG API",
        "version": "0.1.0",
    }
