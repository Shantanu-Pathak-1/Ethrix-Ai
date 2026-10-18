from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel
import uuid
import random
from routers.profile_routers import get_random_manual_profile
# Import database, config and helpers from core
from core.database import (
    oauth, users_collection, otp_collection, ADMIN_EMAIL, 
    get_password_hash, verify_password, send_email
)
import core.database as db_module

router = APIRouter()

# Auth Schemas
class SignupRequest(BaseModel): email: str; password: str; full_name: str; dob: str; username: str
class OTPRequest(BaseModel): email: str
class OTPVerifyRequest(BaseModel): email: str; otp: str
class LoginRequest(BaseModel): identifier: str; password: str

@router.get("/auth/login")
async def login(request: Request):
    redirect_uri = str(request.url_for('auth_callback')).replace("http://", "https://")
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/auth/callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        user = token.get('userinfo')
        
        # 💖 Database se Maintenance Check
        setting = await db_module.settings_collection.find_one({"_id": "system_settings"})
        is_maintenance = setting.get("maintenance_mode", False) if setting else False
        
        if is_maintenance and user['email'] != ADMIN_EMAIL:
            return HTMLResponse(content="<h1>Site Under Maintenance</h1>", status_code=503)

        existing_user = await users_collection.find_one({"email": user['email']})
        
        if not existing_user:
            subject = '🚀 New User — Ethrix AI'
            body = f"""<div style="font-family:sans-serif;max-width:480px;margin:auto;background:#0B0F19;color:#e0e0e0;border-radius:16px;padding:24px;border:1px solid rgba(0,229,255,0.2)">
<h2 style="color:#00E5FF;margin-bottom:4px">New User Joined! 🎉</h2>
<p style="color:#9ca3af;font-size:14px;margin-top:0">Ethrix AI</p>
<hr style="border-color:rgba(255,255,255,0.08);margin:16px 0">
<p><b>Name:</b> {user.get('name','New User')}</p>
<p><b>Email:</b> {user['email']}</p>
<p><b>Method:</b> Google OAuth</p>
<hr style="border-color:rgba(255,255,255,0.08);margin:16px 0">
<a href="/admin" style="background:#00E5FF;color:#000;padding:10px 20px;border-radius:8px;font-weight:bold;text-decoration:none">Open Admin Panel</a>
</div>"""
            await send_email(ADMIN_EMAIL, subject, body)

        request.session['user'] = user
        await users_collection.update_one({"email": user['email']}, {"$set": {"name": user.get('name'), "picture": user.get('picture'), "username": user['email'].split('@')[0]}}, upsert=True)
        return RedirectResponse("/")
    except Exception as e: 
        print(f"Login error: {e}")
        return RedirectResponse("/login")

@router.get("/logout")
async def logout(request: Request): 
    request.session.pop('user', None)
    return RedirectResponse("/")

async def _persist_guest_user(guest_email: str):
    try:
        await db_module.get_new_db().users.update_one(
            {"email": guest_email},
            {"$set": {
                "name": "Guest",
                "email": guest_email,
                "username": "guest",
                "is_guest": True,
                "plan": "free",
                "picture": "/static/images/logo.png"
            }},
            upsert=True
        )
    except Exception as e:
        print(f"[Guest Save Info]: {e}")

@router.get("/auth/bypass")
@router.get("/guest_login")
@router.get("/bypass")
async def bypass_login(request: Request, background_tasks: BackgroundTasks):
    guest_email = f"guest_{uuid.uuid4().hex[:8]}@ethrix.ai"
    guest_user = {
        "email": guest_email,
        "name": "Guest",
        "username": "guest",
        "picture": "/static/images/logo.png",
        "is_guest": True,
        "plan": "free"
    }
    request.session['user'] = guest_user
    background_tasks.add_task(_persist_guest_user, guest_email)
    return RedirectResponse(url="/?guest=1", status_code=303)

@router.post("/api/guest_login")
async def guest_login(request: Request, background_tasks: BackgroundTasks):
    guest_email = f"guest_{uuid.uuid4().hex[:8]}@ethrix.ai"
    guest_user = {
        "email": guest_email,
        "name": "Guest",
        "username": "guest",
        "picture": "/static/images/logo.png",
        "is_guest": True,
        "plan": "free"
    }
    request.session['user'] = guest_user
    background_tasks.add_task(_persist_guest_user, guest_email)
    return {"status": "success", "redirect": "/?guest=1"}

@router.post("/api/send_otp")
async def send_otp_endpoint(req: OTPRequest):
    if await users_collection.find_one({"email": req.email}):
        return JSONResponse({"status": "error", "message": "Email already registered! Please sign in."}, 400)
    
    otp = str(random.randint(100000, 999999))
    await otp_collection.update_one({"email": req.email}, {"$set": {"otp": otp}}, upsert=True)
    
    email_html = f"""
    <div style="font-family:'Segoe UI',Roboto,Helvetica,sans-serif;max-width:480px;margin:auto;background:#0B0F19;color:#FFFFFF;border-radius:16px;padding:32px;border:1px solid rgba(0,229,255,0.25);text-align:center;">
        <h2 style="color:#00E5FF;margin-bottom:8px;font-size:24px;">Ethrix AI Verification</h2>
        <p style="color:#94A3B8;font-size:14px;margin-top:0;">Your 6-digit verification code is below:</p>
        <div style="background:rgba(0,229,255,0.1);border:1.5px dashed #00E5FF;border-radius:12px;padding:16px 24px;margin:24px 0;display:inline-block;">
            <span style="font-size:32px;font-weight:800;letter-spacing:8px;color:#00E5FF;">{otp}</span>
        </div>
        <p style="color:#64748B;font-size:12px;margin-top:20px;">Valid for 10 minutes. If you did not request this, please ignore.</p>
    </div>
    """
    
    sent = await send_email(req.email, f"{otp} is your Ethrix AI verification code", email_html)
    if sent:
        return {"status": "success", "message": "Verification code sent to your email!"}
    
    # Dev mode fallback: OTP saved in DB & logged in console so user is never blocked
    return {
        "status": "success",
        "message": f"Verification code generated! (Dev mode: check terminal for code)",
        "dev_otp": otp
    }

@router.post("/api/verify_otp")
async def verify_otp_endpoint(req: OTPVerifyRequest):
    record = await otp_collection.find_one({"email": req.email})
    if record and record.get("otp") == req.otp: return {"status": "success"}
    return JSONResponse({"status": "error"}, 400)

@router.post("/api/complete_signup")
async def complete_signup(req: SignupRequest, request: Request):
    # 💖 Database se Maintenance Check
    setting = await db_module.settings_collection.find_one({"_id": "system_settings"})
    is_maintenance = setting.get("maintenance_mode", False) if setting else False

    if is_maintenance and req.email != ADMIN_EMAIL: 
        return JSONResponse({"status": "error", "message": "Site is under maintenance!"}, 503)

    if await users_collection.find_one({"username": req.username}): return JSONResponse({"status": "error"}, 400)
    
    subject = '🚀 New User (Manual) — Ethrix AI'
    body = f"""<div style="font-family:sans-serif;max-width:480px;margin:auto;background:#0B0F19;color:#e0e0e0;border-radius:16px;padding:24px;border:1px solid rgba(0,229,255,0.2)">
<h2 style="color:#00E5FF;margin-bottom:4px">New User Joined! 🎉</h2>
<p style="color:#9ca3af;font-size:14px;margin-top:0">Ethrix AI</p>
<hr style="border-color:rgba(255,255,255,0.08);margin:16px 0">
<p><b>Name:</b> {req.full_name}</p>
<p><b>Email:</b> {req.email}</p>
<p><b>Username:</b> @{req.username}</p>
<p><b>Method:</b> Manual Signup</p>
<hr style="border-color:rgba(255,255,255,0.08);margin:16px 0">
<a href="/admin" style="background:#00E5FF;color:#000;padding:10px 20px;border-radius:8px;font-weight:bold;text-decoration:none">Open Admin Panel</a>
</div>"""
    await send_email(ADMIN_EMAIL, subject, body)

    # ✨ YAHAN SE NAYA LOGIC SHURU HOTA HAI ✨
    random_profile = get_random_manual_profile()
    final_name = req.full_name if req.full_name else random_profile["name"]

    await users_collection.insert_one({
        "email": req.email, 
        "username": req.username, 
        "password_hash": get_password_hash(req.password), 
        "name": final_name, 
        "picture": random_profile["picture"], # <-- Random pyari si DP lag jayegi!
        "memories": [], 
        "custom_instruction": ""
    })
    
    request.session['user'] = {"email": req.email, "name": final_name}
    return {"status": "success"}

@router.post("/api/login_manual")
async def login_manual(req: LoginRequest, request: Request):
    user = await users_collection.find_one({"$or": [{"email": req.identifier}, {"username": req.identifier}]})
    if user and verify_password(req.password, user.get('password_hash')):
        # 💖 Database se Maintenance Check
        setting = await db_module.settings_collection.find_one({"_id": "system_settings"})
        is_maintenance = setting.get("maintenance_mode", False) if setting else False
        
        if is_maintenance and user['email'] != ADMIN_EMAIL:
            return JSONResponse({"status": "error", "message": "Site is under maintenance! Only admins can login."}, 503)
            
        request.session['user'] = {"email": user['email'], "name": user['name']}
        return {"status": "success"}
    return JSONResponse({"status": "error"}, 400)

class GoogleOnboardingRequest(BaseModel):
    username: str
    dob: str | None = None

@router.post("/api/complete_google_onboarding")
async def complete_google_onboarding(req: GoogleOnboardingRequest, request: Request):
    user = await db_module.get_current_user(request)
    if not user:
        return JSONResponse({"status": "error", "message": "Login required"}, 401)
    
    existing = await users_collection.find_one({"username": req.username, "email": {"$ne": user['email']}})
    if existing:
        return JSONResponse({"status": "error", "message": "Username already taken"}, 400)
    
    update_data = {"username": req.username}
    if req.dob:
        update_data["dob"] = req.dob
        
    await users_collection.update_one({"email": user['email']}, {"$set": update_data}, upsert=True)
    
    session_user = request.session.get('user', {})
    session_user['username'] = req.username
    request.session['user'] = session_user
    
    return {"status": "success"}