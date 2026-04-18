from __future__ import annotations

from fastapi import FastAPI

from app.api.admin import router as admin_router


def create_app() -> FastAPI:
    app = FastAPI(title="Private Market Insider: Australia - Admin")
    app.include_router(admin_router)
    return app


app = create_app()

