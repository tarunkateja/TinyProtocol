from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from app.config import settings
from app.routers import (
    assistant,
    auth,
    babies,
    care,
    docs,
    events,
    family,
    feeds,
    foods,
    presets,
    summary,
    timeline,
)

app = FastAPI(
    title="TinyProtocol API",
    version="0.1.0",
    description="A GA1-aware feed & care tracker for newborns.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (
    auth, family, babies, foods, feeds, events, timeline, summary, assistant,
    presets, care, docs,
):
    app.include_router(module.router, prefix="/v1")


@app.get("/")
def health():
    return {"app": settings.app_name, "stage": settings.stage, "ok": True}


handler = Mangum(app, lifespan="off")
