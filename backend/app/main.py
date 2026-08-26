from fastapi import FastAPI

from app.routers import reels, videos

app = FastAPI(title="AI Reels Generator API")

app.include_router(videos.router)
app.include_router(reels.router)


@app.get("/")
def health() -> dict:
    return {"status": "ok"}
