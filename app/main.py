from contextlib import asynccontextmanager
import time

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles

from app.auth import routes as auth_routes
from app.core.errors import register_all_errors
from app.items import routes as item_routes
from app.rbac import admin_routes as admin_rbac_routes
from app.settings import STATIC_ASSETS_PATH, UPLOAD_DIR_ROOT, settings
from app.user import device_routes, routes as user_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown hooks."""
    yield


_docs_enabled = settings.ENVIRONMENT in ["development", "staging"]

app = FastAPI(
    title="FastAPI Performance & Containerization Showcase",
    root_path=settings.SERVICE_PATH or "",
    lifespan=lifespan,
    debug=settings.LOG_LEVEL == "DEBUG",
    swagger_ui_parameters={
        "syntaxHighlight.theme": "obsidian",
        "persistAuthorization": True,
    },
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

register_all_errors(app)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.TRUSTED_HOSTS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Application Routers
app_router = APIRouter(prefix="/v1")

# Core Auth, User Profile & RBAC modules
app_router.include_router(auth_routes.router)
app_router.include_router(user_routes.router)
app_router.include_router(device_routes.router)
app_router.include_router(admin_rbac_routes.router)

# Performance & Benchmarking CRUD module
app_router.include_router(item_routes.router)

# Static file mounts
if UPLOAD_DIR_ROOT.exists():
    app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR_ROOT), name="uploads")
if STATIC_ASSETS_PATH.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_ASSETS_PATH), name="assets")


@app.get("/")
def read_root():
    return {
        "service": "fastapi-performance-containerization",
        "runtime": "Python 3.14 + Uvicorn + asyncio",
        "status": "online",
    }


@app.get("/health")
def read_health():
    return {
        "status": "healthy",
        "framework": "FastAPI",
    }


app.include_router(app_router)


@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    start_time = time.perf_counter()
    response: Response = await call_next(request)
    process_time = time.perf_counter() - start_time
    response.headers["X-Process-Time"] = f"{process_time:.6f}"
    return response
