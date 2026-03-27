import os
from dotenv import load_dotenv

# ❤️ SABSE PEHLE .env load karo taaki database file ko keys mil jayein!
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
import features.profile.profile_routers as profile_routers
import features.profile.settings_routers as settings_routers
from features.ai_tools.api_routers import router as api_router
import core.database as db_module
from features.public_pages.pages import router as pages_router
from features.auth.auth_routers import router as auth_router
from arcade_zone.arcade_backend import arcade_app

# Main app instance
app = FastAPI(title="Ethrix AI")

# Proxy Headers Middleware — HTTPS ke liye zaroori hai (Railway/Render/etc.)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# Session Middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=db_module.SECRET_KEY,
    max_age=3600 * 24 * 7,  # 7 days
    https_only=True,         # Production mein session secure rahega
    same_site="lax"
)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Arcade Zone
app.mount("/arcade", arcade_app)

# Routers
app.include_router(pages_router)
app.include_router(auth_router)
app.include_router(api_router)
app.include_router(profile_routers.router)
app.include_router(settings_routers.router)

# ==========================================
# CUSTOM ERROR PAGES
# ==========================================
_templates = Jinja2Templates(directory="templates")

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    return _templates.TemplateResponse(
        request=request,
        name="404.html",
        status_code=404
    )

@app.exception_handler(500)
async def server_error_handler(request: Request, exc: Exception):
    return _templates.TemplateResponse(
        request=request,
        name="500.html",
        status_code=500
    )

@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    import traceback, core.database as _db
    try:
        await _db.error_logs_collection.insert_one({
            "error":     str(exc),
            "trace":     traceback.format_exc(),
            "endpoint":  str(request.url),
            "timestamp": __import__("datetime").datetime.utcnow()
        })
    except Exception:
        pass
    return _templates.TemplateResponse(
        request=request,
        name="500.html",
        status_code=500
    )