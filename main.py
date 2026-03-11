from fastapi import FastAPI
import core.database as db_module

# Apne dono routers ko import kar rahe hain
# (Dhyan rakhna dono files mein 'router = APIRouter()' define hona chahiye)
from routers.pages import router as pages_router
from routers.auth_routers import router as auth_router 

# Main app instance
app = FastAPI(title="Ethrix AI")

# Ab dono routers ko main app ke sath pyare tarike se connect kar diya
app.include_router(pages_router)
app.include_router(auth_router)

# Agar future mein database ka koi startup event add karna ho, toh yahan kar sakte ho
# @app.on_event("startup")
# async def startup_event():
#     print("Database connected successfully!")