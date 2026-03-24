# ==================================================================================
#  FILE: routers/settings_routers.py
#  DESCRIPTION: Settings Page, Preferences API + Google Workspace OAuth
# ==================================================================================

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import os
import httpx
import core.database as db_module

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# ── HF Agent base URL (derive from HF_AGENT_URL env var) ─────────────────────
_HF_AGENT_URL = os.getenv("HF_AGENT_URL", "")
HF_BASE_URL   = _HF_AGENT_URL.rsplit("/", 1)[0] if _HF_AGENT_URL else ""


# ==========================================
# PREFERENCES MODEL
# ==========================================
class PreferencesRequest(BaseModel):
    theme:         str
    font:          str
    voice:         bool
    primary_color: str
    send_on_enter: bool
    ui_sfx:        bool
    fast_mode:     bool
    auto_scroll:   bool
    smart_memory:  bool
    zen_mode:      bool
    ai_persona:    str
    chat_text_size:str
    cursor_mode:   str = "neon"


# ==========================================
# SETTINGS PAGE
# ==========================================
@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    user = await db_module.get_current_user(request)
    if not user:
        return RedirectResponse("/login")

    db_user = await db_module.users_collection.find_one({"email": user['email']})

    default_prefs = {
        "theme": "dark", "font": "Inter", "voice": False, "primary_color": "#00E5FF",
        "send_on_enter": True, "ui_sfx": True, "fast_mode": False, "auto_scroll": True,
        "smart_memory": True, "zen_mode": False, "ai_persona": "friendly",
        "chat_text_size": "default", "cursor_mode": "neon"
    }
    prefs = db_user.get("preferences", default_prefs) if db_user else default_prefs

    # 🔥 FIX: Properly Indented Inside the Function 🔥
    google_connected = False
    # Checking both direct tokens and db_user token field based on your logic
    if user.get("google_access_token") or user.get("google_refresh_token") or (db_user and db_user.get("google_token")):
        google_connected = True
    
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "user": user, 
            "prefs": prefs,
            "google_connected": google_connected
        }
    )

# ==========================================
# SAVE / GET PREFERENCES
# ==========================================
@router.post("/api/save_preferences")
async def save_preferences(req: PreferencesRequest, request: Request):
    user = await db_module.get_current_user(request)
    if not user:
        return JSONResponse({"status": "error", "message": "Login required!"}, 400)

    await db_module.users_collection.update_one(
        {"email": user['email']},
        {"$set": {"preferences": req.model_dump()}}
    )
    return {"status": "success", "message": "Settings saved! 💖"}


@router.get("/api/get_preferences")
async def get_preferences(request: Request):
    user = await db_module.get_current_user(request)
    if not user:
        return {"theme": "dark", "font": "Inter", "voice": False, "primary_color": "#00E5FF"}

    db_user = await db_module.users_collection.find_one({"email": user['email']})
    prefs = db_user.get("preferences", {
        "theme": "dark", "font": "Inter", "voice": False, "primary_color": "#00E5FF"
    }) if db_user else {
        "theme": "dark", "font": "Inter", "voice": False, "primary_color": "#00E5FF"
    }
    return prefs

# ==========================================
# DELETE CHATS (Added for the new UI button)
# ==========================================
@router.delete("/api/delete_all_chats")
async def delete_all_chats(request: Request):
    user = await db_module.get_current_user(request)
    if not user:
        return JSONResponse({"status": "error", "message": "Login required!"}, 400)
    
    try:
        # Assuming your chats collection logic here
        await db_module.chats_collection.delete_many({"user_email": user["email"]})
        return {"status": "success", "message": "All chats deleted"}
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, 500)

# ==========================================
# GOOGLE WORKSPACE — OAUTH ENDPOINTS
# ==========================================

@router.get("/api/google/connect")
async def google_connect_init(request: Request):
    """
    Step 1: Initiate Google OAuth.
    Calls the HF Agent Space to get the auth URL, then redirects the user there.
    """
    user = await db_module.get_current_user(request)
    if not user:
        return RedirectResponse("/login")

    if not HF_BASE_URL:
        return JSONResponse(
            {"status": "error", "message": "Agent URL not configured. Set HF_AGENT_URL env var."},
            status_code=503
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{HF_BASE_URL}/google/auth-url",
                params={"email": user["email"]}
            )
            data = resp.json()

        auth_url = data.get("auth_url")
        if not auth_url:
            error_msg = data.get("error", "Could not get Google auth URL.")
            return JSONResponse({"status": "error", "message": error_msg}, status_code=500)

        # Redirect user directly to Google OAuth consent screen
        return RedirectResponse(auth_url)

    except httpx.TimeoutException:
        return JSONResponse(
            {"status": "error", "message": "Agent server timed out. Please try again."},
            status_code=504
        )
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@router.get("/api/google/status")
async def google_status(request: Request):
    """
    Check whether the current user has connected their Google account.
    Returns: { connected: bool }
    """
    user = await db_module.get_current_user(request)
    if not user:
        return {"connected": False}

    if not HF_BASE_URL:
        # Fallback: check MongoDB directly
        db_user = await db_module.users_collection.find_one({"email": user["email"]})
        connected = bool(db_user and db_user.get("google_connected") and db_user.get("google_token"))
        return {"connected": connected}

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{HF_BASE_URL}/google/status",
                params={"email": user["email"]}
            )
            return resp.json()
    except Exception:
        # Fallback to MongoDB check
        db_user = await db_module.users_collection.find_one({"email": user["email"]})
        connected = bool(db_user and db_user.get("google_connected") and db_user.get("google_token"))
        return {"connected": connected}


@router.post("/api/google/disconnect")
async def google_disconnect(request: Request):
    """
    Remove the user's stored Google OAuth tokens.
    """
    user = await db_module.get_current_user(request)
    if not user:
        return JSONResponse({"status": "error", "message": "Login required."}, 400)

    # Remove from MongoDB via the agent space
    if HF_BASE_URL:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                await client.delete(
                    f"{HF_BASE_URL}/google/disconnect",
                    params={"email": user["email"]}
                )
        except Exception as e:
            print(f"[Google Disconnect Remote Error]: {e}")

    # Also remove locally from our own DB (belt-and-suspenders)
    await db_module.users_collection.update_one(
        {"email": user["email"]},
        {"$unset": {"google_token": "", "google_connected": ""}}
    )

    return {"status": "success", "message": "Google account disconnected successfully."}