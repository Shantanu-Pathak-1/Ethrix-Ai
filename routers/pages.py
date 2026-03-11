from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import core.database as db_module

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request): 
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request): 
    return templates.TemplateResponse("onboarding.html", {"request": request, "email": "user", "name": "user"})

@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    user = await db_module.get_current_user(request)
    if user: return templates.TemplateResponse("index.html", {"request": request, "user": user})
    return templates.TemplateResponse("landing.html", {"request": request})

@router.get("/memory-dashboard", response_class=HTMLResponse)
async def memory_dashboard_page(request: Request):
    user = await db_module.get_current_user(request)
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("memory_dashboard.html", {"request": request, "user": user})

@router.get("/diary", response_class=HTMLResponse)
async def diary_page(request: Request):
    user = await db_module.get_current_user(request)
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("diary.html", {"request": request, "user": user})

@router.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    return templates.TemplateResponse("about.html", {"request": request})

@router.get("/gallery", response_class=HTMLResponse)
async def gallery_page(request: Request):
    user = await db_module.get_current_user(request)
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("gallery.html", {"request": request, "images": []})

@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    user = await db_module.get_current_user(request)
    if not user or user.get('email') != db_module.ADMIN_EMAIL: return RedirectResponse("/")
        
    total_users = await db_module.users_collection.count_documents({})
    total_chats = await db_module.chats_collection.count_documents({})
    banned_count = await db_module.users_collection.count_documents({"is_banned": True})
    
    top_tools = await db_module.tool_usage_collection.find({}).sort("count", -1).limit(6).to_list(length=None)
    max_tool_count = top_tools[0]['count'] if top_tools else 0
    recent_errors = await db_module.error_logs_collection.find({}).sort("timestamp", -1).limit(10).to_list(length=None)
    
    users_cursor = db_module.users_collection.find({}).sort("_id", -1).limit(50)
    users_list = []
    
    async for u in users_cursor:
        u["_id"] = str(u["_id"])
        user_chats = await db_module.chats_collection.find({"user_email": u.get("email")}).to_list(length=None)
        u["msg_count"] = sum(len(chat.get("messages", [])) for chat in user_chats)
        u.setdefault("picture", "/static/images/logo.png")
        u.setdefault("name", "Unknown")
        u.setdefault("username", "")
        u.setdefault("dob", "")
        u.setdefault("is_pro", False)
        u.setdefault("is_banned", False)
        users_list.append(u)
        
    return templates.TemplateResponse("admin.html", {
        "request": request, "total_users": total_users, "total_chats": total_chats,
        "banned_count": banned_count, "users": users_list, "admin_email": db_module.ADMIN_EMAIL,
        "top_tools": top_tools, "max_tool_count": max_tool_count, "recent_errors": recent_errors     
    })

# ==========================================
# 👑 ADMIN PANEL ACTIONS
# ==========================================
@router.post("/admin/promote_user")
async def promote_user(request: Request, email: str = Form(...)):
    user = await db_module.get_current_user(request)
    if not user or user.get('email') != db_module.ADMIN_EMAIL: return RedirectResponse("/")
    await db_module.users_collection.update_one({"email": email}, {"$set": {"is_pro": True}})
    return RedirectResponse("/admin", status_code=303)

@router.post("/admin/demote_user")
async def demote_user(request: Request, email: str = Form(...)):
    user = await db_module.get_current_user(request)
    if not user or user.get('email') != db_module.ADMIN_EMAIL: return RedirectResponse("/")
    await db_module.users_collection.update_one({"email": email}, {"$set": {"is_pro": False}})
    return RedirectResponse("/admin", status_code=303)

@router.post("/admin/ban_user")
async def ban_user(request: Request, email: str = Form(...)):
    user = await db_module.get_current_user(request)
    if not user or user.get('email') != db_module.ADMIN_EMAIL: return RedirectResponse("/")
    await db_module.users_collection.update_one({"email": email}, {"$set": {"is_banned": True}})
    return RedirectResponse("/admin", status_code=303)

@router.post("/admin/unban_user")
async def unban_user(request: Request, email: str = Form(...)):
    user = await db_module.get_current_user(request)
    if not user or user.get('email') != db_module.ADMIN_EMAIL: return RedirectResponse("/")
    await db_module.users_collection.update_one({"email": email}, {"$set": {"is_banned": False}})
    return RedirectResponse("/admin", status_code=303)

# ==========================================
# 🛠️ TOOLS DASHBOARD & DYNAMIC ROUTES
# ==========================================
@router.get("/tools", response_class=HTMLResponse)
async def tools_dashboard_page(request: Request):
    user = await db_module.get_current_user(request)
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools_dashboard.html", {"request": request, "user": user})

# 🚀 Ye ek single function tumhare 22 pages ko handle karega!
@router.get("/tools/{tool_name}", response_class=HTMLResponse)
async def tool_page(request: Request, tool_name: str):
    user = await db_module.get_current_user(request)
    if not user: return RedirectResponse("/login")
    
    valid_tools = [
        "flashcards", "image_gen", "prompt_writer", "qr_generator", "resume_analyzer",
        "github_review", "currency_converter", "youtube_summarizer", "password_generator",
        "grammar_fixer", "interview_questions", "mock_interviewer", "math_solver",
        "smart_todo", "resume_builder", "sing_with_me", "cold_email", "fitness_coach",
        "feynman_explainer", "code_debugger", "movie_talker", "anime_talker"
    ]
    
    if tool_name in valid_tools:
        return templates.TemplateResponse(f"tools/{tool_name}.html", {"request": request, "user": user})
    return RedirectResponse("/tools")