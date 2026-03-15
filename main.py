import os
from dotenv import load_dotenv

# ❤️ SABSE PEHLE .env load karo taaki database file ko keys mil jayein!
load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import routers.profile_routers as profile_routers
import routers.settings_routers as settings_routers
# Ab import karo routers aur database ko
from routers.api_routers import router as api_router
import core.database as db_module
from routers.pages import router as pages_router
from routers.auth_routers import router as auth_router 


# Main app instance
app = FastAPI(title="Ethrix AI")

# Sabse zaroori: Session Middleware add karna
app.add_middleware(
    SessionMiddleware, 
    secret_key=db_module.SECRET_KEY,
    max_age=3600 * 24 * 7  # 7 days tak session valid rahega
)

# Tumhari UI ko sundar banane ke liye static files mount kar rahe hain
app.mount("/static", StaticFiles(directory="static"), name="static")

# Ab saare routers ko main app ke sath connect kar diya
app.include_router(pages_router)
app.include_router(auth_router)
app.include_router(api_router)
app.include_router(profile_routers.router)
app.include_router(settings_routers.router)