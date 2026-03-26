from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel
import uuid
import random
import os
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
    # Pehle env variable check karo, nahi to auto-generate karo
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI") or str(request.url_for('auth_callback'))
    # Ensure HTTPS (proxy ke peeche url_for http return kar sakta hai)
    redirect_uri = redirect_uri.replace("http://", "https://")
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

@router.post("/api/guest_login")
async def guest_login(request: Request):
    # 💖 Database se Maintenance Check
    setting = await db_module.settings_collection.find_one({"_id": "system_settings"})
    is_maintenance = setting.get("maintenance_mode", False) if setting else False
    
    if is_maintenance:
        return JSONResponse({"status": "error", "message": "Site is under maintenance! Guest login disabled."}, 503)
        
    request.session['user'] = {"email": f"guest_{uuid.uuid4()}@ethrix.ai", "name": "Guest", "picture": "", "is_guest": True}
    return {"status": "success"}

@router.post("/api/send_otp")
async def send_otp_endpoint(req: OTPRequest):
    if await users_collection.find_one({"email": req.email}): return JSONResponse({"status": "error", "message": "Exists!"}, 400)
    otp = str(random.randint(100000, 999999))
    await otp_collection.update_one({"email": req.email}, {"$set": {"otp": otp}}, upsert=True)
    sent = await send_email(req.email, "Code", f"<h1>{otp}</h1>")
    if sent: return {"status": "success"}
    return JSONResponse({"status": "error"}, 500)

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