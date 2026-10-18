import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import Base, engine
from app import models  # noqa: F401  (registers every table with Base)
from app.routers.auth import router as auth_router
from app.routers.teacher import router as teacher_router
from app.routers.analytics import router as analytics_router
from app.routers.parent import router as parent_router
from app.routers.admin import router as admin_router

logger = logging.getLogger(__name__)

# Create tables on startup if database is available
try:
    Base.metadata.create_all(bind=engine)
except Exception as exc:
    logger.warning("Could not automatically create tables at startup (database connection deferred): %s", exc)


app = FastAPI(
    title="Intelligent Parent Dashboard System",
    version="1.0.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(
    auth_router,
    prefix="/api"
)

app.include_router(
    teacher_router,
    prefix="/api"
)

app.include_router(
    analytics_router,
    prefix="/api"
)

app.include_router(
    parent_router,
    prefix="/api"
)

app.include_router(
    admin_router,
    prefix="/api"
)


@app.get("/")
def root():
    return {
        "message": "Intelligent Parent Dashboard API is running"
    }


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy"
    }