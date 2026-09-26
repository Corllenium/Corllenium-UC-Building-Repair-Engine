from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.db import get_db
from api.routers.docs import router as docs_router
from api.routers.errors import router as errors_router
from api.routers.fixes import router as fixes_router
from api.routers.models import router as models_router
from api.routers.source import router as source_router
from api.routers.versions import router as versions_router


def create_app() -> FastAPI:
    app = FastAPI(title="UC Model Fixer API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5190"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(source_router)
    app.include_router(models_router)
    app.include_router(versions_router)
    app.include_router(fixes_router)
    app.include_router(errors_router)
    app.include_router(docs_router)

    @app.get("/api/health")
    def health(db: Session = Depends(get_db)):
        db_ok = False
        try:
            db.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False
        return {"status": "ok", "db": db_ok}

    return app


app = create_app()
