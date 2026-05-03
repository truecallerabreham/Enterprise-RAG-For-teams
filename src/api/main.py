from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="Cross-Repo Code Search RAG", version="0.1.0")
    app.include_router(router)

    static_dir = Path(__file__).resolve().parents[1] / "ui" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

        @app.get("/app", include_in_schema=False)
        def web_app() -> FileResponse:
            return FileResponse(static_dir / "index.html")

    return app


app = create_app()
