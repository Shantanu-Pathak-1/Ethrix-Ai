# ==================================================================================
#  FILE: routers/settings_routers.py
#  DESCRIPTION: Dedicated Settings Page & Preferences API
# ==================================================================================

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import core.database as db_module

router = APIRouter()
templates = Jinja2Templates(directory="templates")

class PreferencesRequest(BaseModel):
    theme: str
    font: str
    voice: bool
    primary_color: str
    send_on_enter: bool
    ui_sfx: bool
    fast_mode: bool
    auto_scroll: bool
    smart_memory: bool
    zen_mode: bool
    ai_persona: str
    chat_text_size: str
    cursor_mode: str = "neon"  # ✅ NEW — default neon

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    user = await db_module.get_current_user(request)
    if not user:
        return RedirectResponse("/login")
        
    db_user = await db_module.users_collection.find_one({"email": user['email']})
    
    # Default preferences with Ethrix Cyan Color
    default_prefs = {
    "theme": "dark", "font": "Inter", "voice": False, "primary_color": "#00E5FF",
    "send_on_enter": True, "ui_sfx": True, "fast_mode": False, "auto_scroll": True,
    "smart_memory": True, "zen_mode": False, "ai_persona": "friendly", "chat_text_size": "default"
}
    prefs = db_user.get("preferences", default_prefs) if db_user else default_prefs
    
    return templates.TemplateResponse("settings.html", {"request": request, "user": user, "prefs": prefs})

@router.post("/api/save_preferences")
async def save_preferences(req: PreferencesRequest, request: Request):
    user = await db_module.get_current_user(request)
    if not user: 
        return JSONResponse({"status": "error", "message": "Login required!"}, 400)
        
    await db_module.users_collection.update_one(
        {"email": user['email']},
        {"$set": {"preferences": req.model_dump()}}
    )
    return {"status": "success", "message": "Settings saved beautifully! 💖"}

@router.get("/api/get_preferences")
async def get_preferences(request: Request):
    user = await db_module.get_current_user(request)
    if not user: 
        return {"theme": "dark", "font": "Inter", "voice": False, "primary_color": "#00E5FF"}
        
    db_user = await db_module.users_collection.find_one({"email": user['email']})
    prefs = db_user.get("preferences", {"theme": "dark", "font": "Inter", "voice": False, "primary_color": "#00E5FF"}) if db_user else {"theme": "dark", "font": "Inter", "voice": False, "primary_color": "#00E5FF"}
    return prefs