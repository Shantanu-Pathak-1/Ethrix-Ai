from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import core.database as db_module
from fastapi.responses import JSONResponse
from core.geo_pricing import get_pricing_for_user

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request):
    return templates.TemplateResponse(request=request, name="onboarding.html", context={"email": "user", "name": "user"})

@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    user = await db_module.get_current_user(request)
    if user:
        return templates.TemplateResponse(request=request, name="index.html", context={"user": user})
    return templates.TemplateResponse(request=request, name="landing.html")

@router.get("/memory-dashboard", response_class=HTMLResponse)
async def memory_dashboard_page(request: Request):
    user = await db_module.get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse(request=request, name="memory_dashboard.html", context={"user": user})

@router.get("/diary", response_class=HTMLResponse)
async def diary_page(request: Request):
    user = await db_module.get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse(request=request, name="diary.html", context={"user": user})

@router.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    return templates.TemplateResponse(request=request, name="about.html")

# @router.get("/legal", response_class=HTMLResponse)
# async def legal_page(request: Request):
#     return templates.TemplateResponse(request=request, name="legal.html")

# Agar tum FastAPI use kar rahe ho, toh aisa kuch code hoga:
@router.get("/legal")
async def legal_page(request: Request):
    return templates.TemplateResponse("legal.html", {"request": request})

@router.get("/privacy")
async def privacy_page(request: Request):
    return templates.TemplateResponse("legal.html", {"request": request})

@router.get("/disclaimer")
async def disclaimer_page(request: Request):
    return templates.TemplateResponse("legal.html", {"request": request})

@router.get("/gallery", response_class=HTMLResponse)
async def gallery_page(request: Request):
    user = await db_module.get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse(request=request, name="gallery.html", context={"images": []})

# ==========================================
# PRICING PAGE — /pricing
# ==========================================
@router.get("/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request):
    user = await db_module.get_current_user(request)
    email = user["email"] if user else None
    pricing = await get_pricing_for_user(request, email)
    return templates.TemplateResponse(request=request, name="pricing.html", context={
        "user": user,
        "pricing": pricing
    })

@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    user = await db_module.get_current_user(request)
    if not user or user.get('email') != db_module.ADMIN_EMAIL:
        return RedirectResponse("/")

    from core.rate_limiter import LIMITS
    from core.geo_pricing import PRICING

    total_users  = await db_module.users_collection.count_documents({})
    total_chats  = await db_module.chats_collection.count_documents({})
    banned_count = await db_module.users_collection.count_documents({"is_banned": True})
    pro_count    = await db_module.users_collection.count_documents({"plan": "pro"})
    elite_count  = await db_module.users_collection.count_documents({"plan": "elite"})

    top_tools      = await db_module.tool_usage_collection.find({}).sort("count", -1).limit(6).to_list(length=None)
    max_tool_count = top_tools[0]['count'] if top_tools else 0
    recent_errors  = await db_module.error_logs_collection.find({}).sort("timestamp", -1).limit(10).to_list(length=None)

    users_cursor = db_module.users_collection.find({}).sort("_id", -1).limit(50)
    users_list   = []

    async for u in users_cursor:
        u["_id"]  = str(u["_id"])
        chats     = await db_module.chats_collection.find({"user_email": u.get("email")}).to_list(length=None)
        u["msg_count"] = sum(len(c.get("messages", [])) for c in chats)
        u.setdefault("picture",  "/static/images/logo.png")
        u.setdefault("name",     "Unknown")
        u.setdefault("username", "")
        u.setdefault("is_banned", False)
        if u.get("plan") in ("free", "pro", "elite"):
            u["resolved_plan"] = u["plan"]
        elif u.get("is_pro"):
            u["resolved_plan"] = "pro"
        else:
            u["resolved_plan"] = "free"
        users_list.append(u)

    return templates.TemplateResponse(request=request, name="admin.html", context={
        "total_users":    total_users,
        "total_chats":    total_chats,
        "banned_count":   banned_count,
        "pro_count":      pro_count,
        "elite_count":    elite_count,
        "free_count":     total_users - pro_count - elite_count,
        "users":          users_list,
        "admin_email":    db_module.ADMIN_EMAIL,
        "top_tools":      top_tools,
        "max_tool_count": max_tool_count,
        "recent_errors":  recent_errors,
        "limits":         LIMITS,
        "pricing_in":     PRICING["IN"],
        "pricing_usd":    PRICING["DEFAULT"],
    })

# ==========================================
# ADMIN ACTIONS
# ==========================================
def _is_admin(user):
    return user and user.get('email') == db_module.ADMIN_EMAIL

@router.post("/admin/set_plan")
async def set_plan(request: Request, email: str = Form(...), plan: str = Form(...)):
    if not _is_admin(await db_module.get_current_user(request)):
        return RedirectResponse("/")
    if plan not in ("free", "pro", "elite"):
        return RedirectResponse("/admin")
    await db_module.users_collection.update_one(
        {"email": email},
        {"$set": {
            "plan":        plan,
            "is_pro":      plan in ("pro", "elite"),
            "daily_usage": {}
        }}
    )
    return RedirectResponse("/admin", status_code=303)

@router.post("/admin/ban_user")
async def ban_user(request: Request, email: str = Form(...)):
    if not _is_admin(await db_module.get_current_user(request)):
        return RedirectResponse("/")
    await db_module.users_collection.update_one({"email": email}, {"$set": {"is_banned": True}})
    return RedirectResponse("/admin", status_code=303)

@router.post("/admin/unban_user")
async def unban_user(request: Request, email: str = Form(...)):
    if not _is_admin(await db_module.get_current_user(request)):
        return RedirectResponse("/")
    await db_module.users_collection.update_one({"email": email}, {"$set": {"is_banned": False}})
    return RedirectResponse("/admin", status_code=303)

@router.post("/admin/promote_user")
async def promote_user(request: Request, email: str = Form(...)):
    if not _is_admin(await db_module.get_current_user(request)):
        return RedirectResponse("/")
    await db_module.users_collection.update_one(
        {"email": email}, {"$set": {"plan": "pro", "is_pro": True}}
    )
    return RedirectResponse("/admin", status_code=303)

@router.post("/admin/demote_user")
async def demote_user(request: Request, email: str = Form(...)):
    if not _is_admin(await db_module.get_current_user(request)):
        return RedirectResponse("/")
    await db_module.users_collection.update_one(
        {"email": email}, {"$set": {"plan": "free", "is_pro": False}}
    )
    return RedirectResponse("/admin", status_code=303)

@router.post("/admin/toggle_maintenance")
async def toggle_maintenance(request: Request):
    if not _is_admin(await db_module.get_current_user(request)):
        return JSONResponse({"status": "error"}, status_code=403)
    setting      = await db_module.settings_collection.find_one({"_id": "system_settings"})
    current_mode = setting.get("maintenance_mode", False) if setting else False
    new_mode     = not current_mode
    await db_module.settings_collection.update_one(
        {"_id": "system_settings"}, {"$set": {"maintenance_mode": new_mode}}, upsert=True
    )
    return {"status": "success", "mode": new_mode}

# ==========================================
# TOOLS DASHBOARD & DYNAMIC ROUTES
# ==========================================
@router.get("/tools", response_class=HTMLResponse)
async def tools_dashboard_page(request: Request):
    user = await db_module.get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse(request=request, name="tools_dashboard.html", context={"user": user})

@router.get("/tools/{tool_name}", response_class=HTMLResponse)
async def tool_page(request: Request, tool_name: str):
    user = await db_module.get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    valid_tools = [
        "flashcards", "image_gen", "prompt_writer", "qr_generator", "resume_analyzer",
        "github_review", "currency_converter", "youtube_summarizer", "password_generator",
        "grammar_fixer", "interview_questions", "mock_interviewer", "math_solver",
        "smart_todo", "resume_builder", "sing_with_me", "cold_email", "fitness_coach",
        "feynman_explainer", "code_debugger", "movie_talker", "anime_talker"
    ]
    if tool_name in valid_tools:
        return templates.TemplateResponse(request=request, name=f"tools/{tool_name}.html", context={"user": user})
    return RedirectResponse("/tools")