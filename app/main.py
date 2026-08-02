from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

# Load this application's own .env before importing dashboard modules.
BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.dashboard import router as dashboard_router


app = FastAPI(
    title="DreamShift Client Intelligence",
    version="1.0.0",
    description=(
        "Standalone, read-only client intelligence dashboard backed by "
        "DreamShift's Airtable data."
    ),
)

app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "app" / "static"),
    name="static",
)
app.include_router(dashboard_router)


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=307)


@app.get("/health", tags=["Operations"])
async def health() -> dict[str, str]:
    return {"status": "ok", "app": "dreamshift-client-intelligence"}
