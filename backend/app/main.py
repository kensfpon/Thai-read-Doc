"""FastAPI application. Phase 0: health endpoint only; services arrive in Phase 2."""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="HART Reader", version="0.1.0")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
