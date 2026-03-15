# ==================================================================================
#  FILE: routers/profile_routers.py
#  DESCRIPTION: Advanced Profile Management with Cropping & History 💖
# ==================================================================================

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from datetime import datetime
import random
import core.database as db_module

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Models for Request
class ProfileUpdateRequest(BaseModel):
    new_name: str
    new_picture: str  # Can be a base64 string (cropped image) or a default avatar URL

# List of default 12 avatars (Tum inhe /static/avatars/ folder mein rakh lena)
DEFAULT_AVATARS = [f"/static/avatars/avatar_{i}.png" for i in range(1, 13)]

# Random cool names for manual signups
COOL_NAMES = ["Phantom Rider", "Neon Ninja", "Cyber Samurai", "Cosmic Voyager", "Star Gazer", "Pixel Hero"]

# Nayi Avatar Lists (11 normal, 4 premium)
DEFAULT_AVATARS = [f"/static/avatars/avatar_{i}.png" for i in range(1, 12)]
PREMIUM_AVATARS = [f"/static/avatars/premium_avatar_{i}.png" for i in range(1, 5)]

# Random manual signup ke liye humesha normal wale hi denge
def get_random_manual_profile():
    return {
        "name": random.choice(COOL_NAMES) + f" {random.randint(10, 99)}",
        "picture": random.choice(DEFAULT_AVATARS)
    }

@router.get("/profile-settings", response_class=HTMLResponse)
async def profile_settings_page(request: Request):
    user = await db_module.get_current_user(request)
    if not user:
        return RedirectResponse("/login")
        
    db_user = await db_module.users_collection.find_one({"email": user['email']})
    current_name = db_user.get("name") if db_user else user.get("name", "User")
    current_pic = db_user.get("picture") if db_user else user.get("picture", "/static/images/logo.png")
    
    # Check agar user Pro hai ya Admin hai
    is_pro = False
    if db_user and db_user.get("is_pro"):
        is_pro = True
    elif user['email'] == db_module.ADMIN_EMAIL:
        is_pro = True
    
    return templates.TemplateResponse("profile_settings.html", {
        "request": request, 
        "user": user,
        "current_name": current_name,
        "current_pic": current_pic,
        "default_avatars": DEFAULT_AVATARS,
        "premium_avatars": PREMIUM_AVATARS,
        "is_pro": is_pro
    })
 
@router.post("/api/update_advanced_profile")
async def update_advanced_profile(req: ProfileUpdateRequest, request: Request):
    user = await db_module.get_current_user(request)
    if not user:
        return JSONResponse({"status": "error", "message": "Login required!"}, 400)
        
    db_user = await db_module.users_collection.find_one({"email": user['email']})
    
    # Purana data history mein save karne ke liye (Recovery purpose)
    old_profile = {
        "name": db_user.get("name"),
        "picture": db_user.get("picture"),
        "changed_at": datetime.utcnow()
    }

    # Naya data update kar rahe hain
    update_data = {
        "name": req.new_name,
        "picture": req.new_picture
    }

    # Database query (History push + Naya update)
    await db_module.users_collection.update_one(
        {"email": user['email']}, 
        {
            "$set": update_data,
            "$push": {"profile_history": old_profile}
        }
    )
    
    # Session bhi update kar dete hai taaki bina reload naya name dikhe
    request.session['user']['name'] = req.new_name
    request.session['user']['picture'] = req.new_picture

    return {"status": "success", "message": "Profile updated beautifully! 💖"}