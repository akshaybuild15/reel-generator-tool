from fastapi import APIRouter

router = APIRouter(prefix="/videos", tags=["videos"])

# TODO (Phase 2): POST /upload-url, POST /{id}/process, GET /{id}/status, GET /{id}/reels
