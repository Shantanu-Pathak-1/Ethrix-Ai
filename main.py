from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

import core.database as db_module

# Apne dono routers ko import kar rahe hain
from routers.pages import router as pages_router
from routers.auth_routers import router as auth_router 

# Main app instance
app = FastAPI(title="Ethrix AI")

# Sabse zaroori: Session Middleware add karna (Iski wajah se 500 error aa raha tha!)
app.add_middleware(
    SessionMiddleware, 
    secret_key=db_module.SECRET_KEY,
    max_age=3600 * 24 * 7  # 7 days tak session valid rahega
)

# Tumhari UI ko sundar banane ke liye static files mount kar rahe hain
app.mount("/static", StaticFiles(directory="static"), name="static")

# Ab dono routers ko main app ke sath connect kar diya
app.include_router(pages_router)
app.include_router(auth_router)