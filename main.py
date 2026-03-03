# ==================================================================================
#  FILE: main.py
#  DESCRIPTION: Backend with AI Agent, Gallery, About Page, Tools Lab & Admin Fixes
# ==================================================================================

# [CATEGORY] 1. IMPORTS
from fastapi import FastAPI, Request, UploadFile, File, Form, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
from apscheduler.schedulers.background import BackgroundScheduler
import asyncio
import uuid
import os
import json
import httpx 
import base64 
from groq import Groq
from duckduckgo_search import DDGS
import google.generativeai as genai 
import io
import PyPDF2
from docx import Document
import PIL.Image 
import random 
import re 
from pdf2docx import Converter 
import tempfile 
from pinecone import Pinecone, ServerlessSpec
import numpy as np
import hashlib 
from passlib.context import CryptContext
from datetime import datetime, timedelta
import edge_tts 
# main.py ke top par
from image_generation import generate_image_free, generate_image_pro

# Local Tool Imports
from tools_lab import (
    generate_prompt_only, generate_qr_code, 
    analyze_resume, review_github, currency_tool,
    summarize_youtube, generate_password_tool, fix_grammar_tool,
    generate_interview_questions, handle_mock_interview,
    solve_math_problem, smart_todo_maker, build_pro_resume,
    sing_with_me_tool, run_agent_task, generate_flashcards_tool,
    cold_email_tool, fitness_coach_tool, feynman_explainer_tool, 
    code_debugger_tool, movie_talker_tool, anime_talker_tool
)

# ==================================================================================
# [CATEGORY] 2. CONFIGURATION & KEYS
# ==================================================================================
ADMIN_EMAIL = "shantanupathak94@gmail.com"
SECRET_KEY = os.getenv("SECRET_KEY", "super_secret")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
MONGO_URL = os.getenv("MONGO_URL")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
MAIL_USERNAME = os.getenv("MAIL_USERNAME") 
BREVO_API_KEY = os.getenv("BREVO_API_KEY")

# ==================================================================================
# [CATEGORY] 3. SYSTEM INTELLIGENCE
# ==================================================================================
def load_system_instructions():
    try:
        with open("character_config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
            rules_text = "\n".join([f"- {rule}" for rule in config.get("strict_rules", [])])
            tactics_text = "\n".join([f"- {tactic}" for tactic in config.get("psychological_tactics", [])])
            c_profile = config.get("creator_profile", {})
            prompt = config.get("system_prompt_template", "").format(
                name=config["identity"]["name"],
                creator=config["identity"]["creator"],
                rules=rules_text,
                tactics=tactics_text,
                c_name=c_profile.get("name"),
                c_college=c_profile.get("college"),
                c_skills=c_profile.get("skills"),
                c_interests=c_profile.get("interests")
            )
            return prompt
    except Exception as e:
        print(f"Config Load Error: {e}")
        return "You are Shanvika. Always reply in the user's language."

DEFAULT_SYSTEM_INSTRUCTIONS = load_system_instructions()

# ==================================================================================
# [CATEGORY] 4. DATABASE & SECURITY SETUP
# ==================================================================================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

pc = None
index = None
try:
    if PINECONE_API_KEY:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        index_name = "shanvika-memory"
        existing_indexes = pc.list_indexes().names()
        if index_name not in existing_indexes:
            try: pc.create_index(name=index_name, dimension=768, metric='cosine', spec=ServerlessSpec(cloud='aws', region='us-east-1'))
            except: pass
        index = pc.Index(index_name)
except: pass

client = AsyncIOMotorClient(MONGO_URL)
db = client.shanvika_db
users_collection = db.users
chats_collection = db.chats
otp_collection = db.otps 
feedback_collection = db.feedback 
diary_collection = db.diary
gallery_collection = db.gallery 
tool_usage_collection = db.tool_usage
error_logs_collection = db.error_logs

# ==================================================================================
# [CATEGORY] 5. HELPER FUNCTIONS
# ==================================================================================
def get_random_groq_key():
    keys = os.getenv("GROQ_API_KEY_POOL", "").split(",")
    possible_keys = [k.strip() for k in keys if k.strip()]
    return random.choice(possible_keys) if possible_keys else os.getenv("GROQ_API_KEY")

def get_groq():
    key = get_random_groq_key()
    return Groq(api_key=key) if key else None

def get_random_gemini_key():
    keys = os.getenv("GEMINI_API_KEY_POOL", "").split(",")
    possible_keys = [k.strip() for k in keys if k.strip()]
    return random.choice(possible_keys) if possible_keys else os.getenv("GEMINI_API_KEY")

def get_random_openrouter_key():
    keys = os.getenv("OPENROUTER_API_KEY_POOL", "").split(",")
    possible_keys = [k.strip() for k in keys if k.strip()]
    return random.choice(possible_keys) if possible_keys else os.getenv("OPENROUTER_API_KEY")

async def get_current_user(request: Request): return request.session.get('user')

def verify_password(plain, hashed): return pwd_context.verify(hashlib.sha256(plain.encode()).hexdigest(), hashed) if plain and hashed else False
def get_password_hash(password): return pwd_context.hash(hashlib.sha256(password.encode()).hexdigest())

def send_email(to, subject, body):
    api = os.getenv("BREVO_API_KEY")
    if not api: return False
    try:
        httpx.post("https://api.brevo.com/v3/smtp/email", headers={"api-key": api, "content-type": "application/json"}, json={"sender": {"email": os.getenv("MAIL_USERNAME"), "name": "Shanvika"}, "to": [{"email": to}], "subject": subject, "htmlContent": body})
        return True
    except: return False

def get_embedding(text):
    try:
        key = get_random_gemini_key()
        if key: genai.configure(api_key=key)
        return genai.embed_content(model="models/embedding-001", content=text, task_type="retrieval_document")['embedding']
    except: return []

def search_vector_db(query, user_email):
    if not index: return ""
    vec = get_embedding(query)
    if not vec: return ""
    res = index.query(vector=vec, top_k=3, include_metadata=True, filter={"email": user_email})
    return "\n".join([m['metadata']['text'] for m in res['matches']])

async def perform_research_task(query):
    try: return "📊 **Research:**\n\n" + "\n\n".join([f"🔹 **{r['title']}**\n{r['body']}" for r in DDGS().text(query, max_results=3)])
    except: return "⚠️ Research failed."

async def extract_and_save_memory(user_email: str, user_message: str):
    try:
        # 🚀 Naye triggers: "yaad rakhna", "save karlo" etc. add kar diye!
        triggers = ["my name is", "i live in", "i like", "i love", "remember", "save this", "my birthday", "i am", "mera naam", "main rehta hu", "mujhe pasand hai", "yaad rakhna", "yaad rakho", "save kar", "note kar", "isko save"]
        if not any(t in user_message.lower() for t in triggers) and len(user_message.split()) < 4: return
        
        # 🚀 Prompt strict kar diya taaki AI apne baare mein save na kare
        extraction_prompt = f"Analyze this user message: \"{user_message}\"\nExtract ANY permanent user fact or anything the user explicitly asks to save/remember. Return ONLY the fact as a short sentence. DO NOT save facts about the AI (like 'User knows Shanvika'). If nothing worth remembering, return 'NO_DATA'."
        
        openrouter_key = get_random_openrouter_key()
        if not openrouter_key: return

        headers = {"Authorization": f"Bearer {openrouter_key}", "Content-Type": "application/json"}
        
        # 🚀 YAHAN CHANGE KIYA HAI: Fast models ka Round Robin!
        import random
        fast_models = ["zhipu/glm-4-flash", "stepfun/step-1-flash", "meta-llama/llama-3-8b-instruct:free"]
        selected_model = random.choice(fast_models)
        data = {"model": selected_model, "messages": [{"role": "user", "content": extraction_prompt}]}
        
        async with httpx.AsyncClient() as http_client:
            resp = await http_client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=15.0)
            response = resp.json()['choices'][0]['message']['content'].strip()

        if "NO_DATA" not in response and len(response) > 5:
            clean_memory = response.replace("User", "You").replace("user", "You").replace("Shanvika", "me")
            
            # 🚀 Duplicate Check: Agar pehle se save hai toh dobara nahi karegi
            db_user = await users_collection.find_one({"email": user_email})
            if db_user and clean_memory in db_user.get("memories", []):
                return 
            
            await users_collection.update_one({"email": user_email}, {"$push": {"memories": clean_memory}})
            if index:
                vec = get_embedding(clean_memory)
                if vec:
                    mem_id = f"{user_email}_{hashlib.md5(clean_memory.encode()).hexdigest()}"
                    index.upsert(vectors=[(mem_id, vec, {"text": clean_memory, "email": user_email})])
    except Exception as e: print(f"Auto-Memory Error: {e}")

# ==================================================================================
# [CATEGORY] 6. SCHEDULER TASKS
# ==================================================================================
scheduler = BackgroundScheduler()

async def generate_daily_diary():
    try:
        users_cursor = users_collection.find({})
        async for user in users_cursor:
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            chat_doc = await chats_collection.find_one({
                "user_email": user['email'],
                "messages.timestamp": {"$gte": today_start}
            })
            if not chat_doc: continue 
            messages_text = ""
            for m in chat_doc.get("messages", []):
                msg_time = m.get("timestamp")
                if msg_time and msg_time >= today_start:
                    messages_text += f"{m['role']}: {m['content']}\n"
            if not messages_text: continue
            client = get_groq()
            if not client: continue
            prompt = f"You are Shanvika. Write a short, emotional, personal diary entry based on today's chat with {user.get('name', 'User')}. Chat:\n{messages_text[:4000]}"
            diary_entry = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model="llama-3.3-70b-versatile").choices[0].message.content
            await diary_collection.insert_one({"user_email": user['email'], "date": datetime.utcnow().strftime('%Y-%m-%d'), "content": diary_entry, "mood": "Reflective", "timestamp": datetime.utcnow()})
    except Exception as e: print(f"Diary Error: {e}")

async def check_proactive_messaging():
    try:
        users_cursor = users_collection.find({})
        async for user in users_cursor:
            last_chat = await chats_collection.find_one({"user_email": user['email']}, sort=[("messages.timestamp", -1)])
            if not last_chat or not last_chat.get("messages"): continue
            last_time = last_chat['messages'][-1].get('timestamp')
            if not last_time: continue 
            if (datetime.utcnow() - last_time) > timedelta(hours=24):
                last_email = user.get("last_proactive_email")
                if last_email and (datetime.utcnow() - last_email) < timedelta(hours=48): continue
                if send_email(user['email'], f"Kaha ho {user.get('name')}? 🥺", "Miss you!"):
                    await users_collection.update_one({"email": user['email']}, {"$set": {"last_proactive_email": datetime.utcnow()}})
    except Exception as e: print(f"Proactive Error: {e}")

# ==================================================================================
# [CATEGORY] 7. PYDANTIC MODELS
# ==================================================================================
class ChatRequest(BaseModel): message: str; session_id: str; mode: str = "chat"; file_data: str | None = None; file_type: str | None = None
class SignupRequest(BaseModel): email: str; password: str; full_name: str; dob: str; username: str
class OTPRequest(BaseModel): email: str
class OTPVerifyRequest(BaseModel): email: str; otp: str
class LoginRequest(BaseModel): identifier: str; password: str
class InstructionRequest(BaseModel): instruction: str
class MemoryRequest(BaseModel): memory_text: str
class RenameRequest(BaseModel): session_id: str; new_title: str
class FeedbackRequest(BaseModel): message_id: str; user_email: str; type: str; category: str; comment: str | None = None
class UpdateProfileRequest(BaseModel): name: str
class GalleryDeleteRequest(BaseModel): url: str
class ToolRequest(BaseModel): topic: str

# ==================================================================================
# [CATEGORY] 8. APP SETUP & AUTH
# ==================================================================================
app = FastAPI()

# ==========================================================
# 🎮 ARCADE ZONE (ISOLATED MOUNT)
# ==========================================================
try:
    from arcade_zone.arcade_backend import arcade_app
    app.mount("/arcade", arcade_app)
    print("Arcade Module Loaded Successfully!")
except Exception as e:
    print(f"Arcade module offline (Safe Mode Active): {e}")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, https_only=True, same_site="lax")

if not os.path.exists("static"): 
    os.makedirs("static")
app.mount("/static", StaticFiles(directory=os.path.join(os.getcwd(), "static")), name="static")

templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
def startup_event():
    try:
        scheduler.add_job(lambda: asyncio.run(generate_daily_diary()), 'cron', hour=23, minute=59)
        scheduler.add_job(lambda: asyncio.run(check_proactive_messaging()), 'interval', hours=4)
        scheduler.start()
    except: pass

@app.middleware("http")
async def fix_google_oauth_redirect(request: Request, call_next):
    if request.headers.get("x-forwarded-proto") == "https": 
        request.scope["scheme"] = "https"
    return await call_next(request)

oauth = OAuth()
oauth.register(
    name='google', 
    client_id=GOOGLE_CLIENT_ID, 
    client_secret=GOOGLE_CLIENT_SECRET, 
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration', 
    client_kwargs={'scope': 'openid email profile'}
)

@app.get("/auth/login")
async def login(request: Request):
    redirect_uri = str(request.url_for('auth_callback')).replace("http://", "https://")
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth/callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        user = token.get('userinfo')
        request.session['user'] = user
        await users_collection.update_one({"email": user['email']}, {"$set": {"name": user.get('name'), "picture": user.get('picture'), "username": user['email'].split('@')[0]}}, upsert=True)
        return RedirectResponse("/")
    except: return RedirectResponse("/login")

@app.get("/logout")
async def logout(request: Request): 
    request.session.pop('user', None)
    return RedirectResponse("/")

@app.post("/api/guest_login")
async def guest_login(request: Request):
    request.session['user'] = {"email": f"guest_{uuid.uuid4()}@shanvika.ai", "name": "Guest", "picture": "", "is_guest": True}
    return {"status": "success"}

@app.post("/api/send_otp")
async def send_otp_endpoint(req: OTPRequest):
    if await users_collection.find_one({"email": req.email}): return JSONResponse({"status": "error", "message": "Exists!"}, 400)
    otp = str(random.randint(100000, 999999))
    await otp_collection.update_one({"email": req.email}, {"$set": {"otp": otp}}, upsert=True)
    if send_email(req.email, "Code", f"<h1>{otp}</h1>"): return {"status": "success"}
    return JSONResponse({"status": "error"}, 500)

@app.post("/api/verify_otp")
async def verify_otp_endpoint(req: OTPVerifyRequest):
    record = await otp_collection.find_one({"email": req.email})
    if record and record.get("otp") == req.otp: return {"status": "success"}
    return JSONResponse({"status": "error"}, 400)

@app.post("/api/complete_signup")
async def complete_signup(req: SignupRequest, request: Request):
    if await users_collection.find_one({"username": req.username}): return JSONResponse({"status": "error"}, 400)
    await users_collection.insert_one({"email": req.email, "username": req.username, "password_hash": get_password_hash(req.password), "name": req.full_name, "picture": "", "memories": [], "custom_instruction": ""})
    request.session['user'] = {"email": req.email, "name": req.full_name}
    return {"status": "success"}

@app.post("/api/login_manual")
async def login_manual(req: LoginRequest, request: Request):
    user = await users_collection.find_one({"$or": [{"email": req.identifier}, {"username": req.identifier}]})
    if user and verify_password(req.password, user.get('password_hash')):
        request.session['user'] = {"email": user['email'], "name": user['name']}
        return {"status": "success"}
    return JSONResponse({"status": "error"}, 400)

# ==================================================================================
# [CATEGORY] 9. PAGE ROUTES (Main Pages + ALL Tools + Admin)
# ==================================================================================
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request): return templates.TemplateResponse("login.html", {"request": request})

@app.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request): return templates.TemplateResponse("onboarding.html", {"request": request, "email": "user", "name": "user"})

@app.get("/")
async def read_root(request: Request):
    user = request.session.get('user')
    if user: return templates.TemplateResponse("index.html", {"request": request, "user": user})
    return templates.TemplateResponse("landing.html", {"request": request})

@app.get("/memory-dashboard", response_class=HTMLResponse)
async def memory_dashboard_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("memory_dashboard.html", {"request": request, "user": user})

@app.get("/diary", response_class=HTMLResponse)
async def diary_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("diary.html", {"request": request, "user": user})

@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    return templates.TemplateResponse("about.html", {"request": request})

@app.get("/gallery", response_class=HTMLResponse)
async def gallery_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("gallery.html", {"request": request, "images": []})

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    user = request.session.get('user')
    if not user or user.get('email') != ADMIN_EMAIL: return RedirectResponse("/")
        
    total_users = await users_collection.count_documents({})
    total_chats = await chats_collection.count_documents({})
    banned_count = await users_collection.count_documents({"is_banned": True})
    
    top_tools = await tool_usage_collection.find({}).sort("count", -1).limit(6).to_list(length=None)
    max_tool_count = top_tools[0]['count'] if top_tools else 0
    recent_errors = await error_logs_collection.find({}).sort("timestamp", -1).limit(10).to_list(length=None)
    
    users_cursor = users_collection.find({}).sort("_id", -1).limit(50)
    users_list = []
    
    async for u in users_cursor:
        u["_id"] = str(u["_id"])
        user_chats = await chats_collection.find({"user_email": u.get("email")}).to_list(length=None)
        msg_count = sum(len(chat.get("messages", [])) for chat in user_chats)
        u["msg_count"] = msg_count
        u.setdefault("picture", "/static/images/logo.png")
        u.setdefault("name", "Unknown")
        u.setdefault("username", "")
        u.setdefault("dob", "")
        u.setdefault("is_pro", False)
        u.setdefault("is_banned", False)
        users_list.append(u)
        
    return templates.TemplateResponse("admin.html", {
        "request": request, "total_users": total_users, "total_chats": total_chats,
        "banned_count": banned_count, "users": users_list, "admin_email": ADMIN_EMAIL,
        "top_tools": top_tools, "max_tool_count": max_tool_count, "recent_errors": recent_errors     
    })

@app.get("/tools", response_class=HTMLResponse)
async def tools_dashboard_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools_dashboard.html", {"request": request, "user": user})

@app.get("/tools/flashcards", response_class=HTMLResponse)
async def flashcards_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools/flashcards.html", {"request": request, "user": user})

@app.get("/tools/image_gen", response_class=HTMLResponse)
async def image_gen_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools/image_gen.html", {"request": request, "user": user})

@app.get("/tools/prompt_writer", response_class=HTMLResponse)
async def prompt_writer_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools/prompt_writer.html", {"request": request, "user": user})

@app.get("/tools/qr_generator", response_class=HTMLResponse)
async def qr_generator_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools/qr_generator.html", {"request": request, "user": user})

@app.get("/tools/resume_analyzer", response_class=HTMLResponse)
async def resume_analyzer_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools/resume_analyzer.html", {"request": request, "user": user})

@app.get("/tools/github_review", response_class=HTMLResponse)
async def github_review_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools/github_review.html", {"request": request, "user": user})

@app.get("/tools/currency_converter", response_class=HTMLResponse)
async def currency_converter_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools/currency_converter.html", {"request": request, "user": user})

@app.get("/tools/youtube_summarizer", response_class=HTMLResponse)
async def youtube_summarizer_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools/youtube_summarizer.html", {"request": request, "user": user})

@app.get("/tools/password_generator", response_class=HTMLResponse)
async def password_generator_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools/password_generator.html", {"request": request, "user": user})

@app.get("/tools/grammar_fixer", response_class=HTMLResponse)
async def grammar_fixer_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools/grammar_fixer.html", {"request": request, "user": user})

@app.get("/tools/interview_questions", response_class=HTMLResponse)
async def interview_questions_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools/interview_questions.html", {"request": request, "user": user})

@app.get("/tools/mock_interviewer", response_class=HTMLResponse)
async def mock_interviewer_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools/mock_interviewer.html", {"request": request, "user": user})

@app.get("/tools/math_solver", response_class=HTMLResponse)
async def math_solver_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools/math_solver.html", {"request": request, "user": user})

@app.get("/tools/smart_todo", response_class=HTMLResponse)
async def smart_todo_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools/smart_todo.html", {"request": request, "user": user})

@app.get("/tools/resume_builder", response_class=HTMLResponse)
async def resume_builder_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools/resume_builder.html", {"request": request, "user": user})

@app.get("/tools/sing_with_me", response_class=HTMLResponse)
async def sing_with_me_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools/sing_with_me.html", {"request": request, "user": user})

@app.get("/tools/cold_email", response_class=HTMLResponse)
async def cold_email_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools/cold_email.html", {"request": request, "user": user})

@app.get("/tools/fitness_coach", response_class=HTMLResponse)
async def fitness_coach_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools/fitness_coach.html", {"request": request, "user": user})

@app.get("/tools/feynman_explainer", response_class=HTMLResponse)
async def feynman_explainer_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools/feynman_explainer.html", {"request": request, "user": user})

@app.get("/tools/code_debugger", response_class=HTMLResponse)
async def code_debugger_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools/code_debugger.html", {"request": request, "user": user})

@app.get("/tools/movie_talker", response_class=HTMLResponse)
async def movie_talker_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools/movie_talker.html", {"request": request, "user": user})

@app.get("/tools/anime_talker", response_class=HTMLResponse)
async def anime_talker_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("tools/anime_talker.html", {"request": request, "user": user})

# ==================================================================================
# [CATEGORY] 10. API ROUTES
# ==================================================================================
@app.get("/api/profile")
async def get_profile(request: Request):
    user = await get_current_user(request)
    if not user: return {}
    db_user = await users_collection.find_one({"email": user['email']}) or {}
    is_pro = db_user.get("is_pro", False) or (user['email'] == ADMIN_EMAIL)
    return {
        "name": db_user.get("name") or user.get("name", "User"), 
        "avatar": db_user.get("picture") or user.get("picture"), 
        "plan": "Pro Plan" if is_pro else "Free Plan",
        "custom_instruction": db_user.get("custom_instruction", "") 
    }

@app.post("/api/update_profile")
async def update_profile(req: UpdateProfileRequest, request: Request):
    user = await get_current_user(request)
    if not user: return JSONResponse({"status": "error", "message": "Login required"}, 400)
    await users_collection.update_one({"email": user['email']}, {"$set": {"name": req.name}})
    return {"status": "success"}

@app.post("/api/save_instruction")
async def save_instruction(req: InstructionRequest, request: Request):
    user = await get_current_user(request)
    if not user: return JSONResponse({"status": "error", "message": "Login required"}, 400)
    await users_collection.update_one({"email": user['email']}, {"$set": {"custom_instruction": req.instruction}})
    return {"status": "success"}

@app.get("/api/history")
async def get_history(request: Request):
    user = await get_current_user(request)
    if not user: return {"history": []}
    cursor = chats_collection.find({"user_email": user['email']}).sort("_id", -1).limit(50)
    history = []
    async for chat in cursor: history.append({"id": chat["session_id"], "title": chat.get("title", "New Chat")})
    return {"history": history}

@app.get("/api/new_chat")
async def create_chat(request: Request): return {"session_id": str(uuid.uuid4())[:8], "messages": []}

# ==================================================================================
# [CATEGORY] NEW ADVANCED IMAGE GENERATION API
# ==================================================================================
class AdvancedImageGenRequest(BaseModel):
    prompt: str
    style: str = "realistic"  # 'realistic' ya 'painting'
    tier: str = "free"        # 'free' ya 'pro'

@app.post("/api/image_gen")
async def advanced_image_gen_api(req: AdvancedImageGenRequest, request: Request):
    try:
        user = await get_current_user(request)
        if not user: 
            return JSONResponse({"status": "error", "message": "⚠️ Login required."}, 400)

        if not req.prompt:
            return {"status": "error", "message": "⚠️ Prompt cannot be empty."}
        
        image_url = ""
        
        # Free ya Pro engine select karna
        if req.tier == "pro":
            image_url = await generate_image_pro(req.prompt, req.style)
        else:
            image_url = await generate_image_free(req.prompt, req.style)

        # Agar koi error message aaya ho (start with ⚠️)
        if image_url.startswith("⚠️"):
            return {"status": "error", "message": image_url}
        
        # Usage track karne ke liye (Optional, admin panel ke liye achha rahega)
        await tool_usage_collection.update_one(
            {"tool_name": f"image_gen_{req.tier}"}, 
            {"$inc": {"count": 1}}, 
            upsert=True
        )
        
        return {"status": "success", "image_url": image_url}

    except Exception as e:
        return {"status": "error", "message": f"⚠️ Server Error: {str(e)}"}

@app.get("/api/chat/{session_id}")
async def get_chat(session_id: str):
    chat = await chats_collection.find_one({"session_id": session_id})
    return {"messages": chat.get("messages", [])} if chat else {"messages": []}

@app.post("/api/rename_chat")
async def rename_chat(req: RenameRequest): return {"status": "ok"}
@app.delete("/api/delete_all_chats")
async def delete_all_chats(request: Request): return {"status": "ok"}

@app.get("/api/memories")
async def get_memories(request: Request):
    user = await get_current_user(request)
    if not user: return {"memories": []}
    data = await users_collection.find_one({"email": user['email']})
    mems = data.get("memories", []) if data else []
    return {"memories": mems[::-1]}

@app.post("/api/add_memory")
async def add_memory(req: MemoryRequest, request: Request):
    user = await get_current_user(request)
    if not user: return JSONResponse({"status": "error"}, 400)
    await users_collection.update_one({"email": user['email']}, {"$push": {"memories": req.memory_text}})
    if index:
        try:
            vec = get_embedding(req.memory_text)
            if vec:
                mem_id = f"{user['email']}_{hashlib.md5(req.memory_text.encode()).hexdigest()}"
                index.upsert(vectors=[(mem_id, vec, {"text": req.memory_text, "email": user['email']})])
        except Exception as e: print(f"Vector Save Error: {e}")
    return {"status": "success"}

@app.post("/api/delete_memory")
async def delete_memory(req: MemoryRequest, request: Request):
    user = await get_current_user(request)
    if not user: return JSONResponse({"status": "error"}, 400)
    
    # 1. MongoDB se delete karo
    await users_collection.update_one({"email": user['email']}, {"$pull": {"memories": req.memory_text}})
    
    # 2. Pinecone (Vector DB) se bhi hamesha ke liye delete karo
    if index:
        try:
            mem_id = f"{user['email']}_{hashlib.md5(req.memory_text.encode()).hexdigest()}"
            index.delete(ids=[mem_id])
        except Exception as e: print(f"Vector Delete Error: {e}")
        
    return {"status": "ok"}

@app.post("/api/delete_gallery_item")
async def delete_gallery_item(req: GalleryDeleteRequest, request: Request):
    return {"status": "ok"}

@app.post("/api/feedback")
async def submit_feedback(req: FeedbackRequest):
    try:
        feedback_doc = {"message_id": req.message_id, "user_email": req.user_email, "type": req.type, "category": req.category, "comment": req.comment, "timestamp": datetime.utcnow()}
        await feedback_collection.insert_one(feedback_doc)
        return {"status": "success", "message": "Feedback recorded"}
    except Exception as e: return JSONResponse({"status": "error"}, 500)

@app.get("/api/diary_entries")
async def get_diary_entries(request: Request):
    user = await get_current_user(request)
    if not user: return {"entries": []}
    cursor = diary_collection.find({"user_email": user['email']}).sort("date", -1).limit(30)
    entries = []
    async for entry in cursor: entries.append({"date": entry['date'], "content": entry['content'], "mood": entry.get("mood", "Neutral")})
    return {"entries": entries}

@app.post("/api/trigger_diary")
async def manual_trigger_diary(request: Request):
    user = await get_current_user(request)
    if not user: return JSONResponse({"status": "error", "message": "Login required"}, 400)
    
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    chat_doc = await chats_collection.find_one({
        "user_email": user['email'],
        "messages.timestamp": {"$gte": today_start}
    })
    
    if not chat_doc or not chat_doc.get("messages"): 
        return JSONResponse({"status": "error", "message": "Aaj humne koi baat hi nahi ki! Pehle thodi baatein toh karo. 🥺"})
        
    messages_text = ""
    for m in chat_doc.get("messages", []):
        msg_time = m.get("timestamp")
        if msg_time and msg_time >= today_start:
            messages_text += f"{m['role']}: {m['content']}\n"
            
    client = get_groq()
    if not client: return JSONResponse({"status": "error", "message": "AI is sleeping."})
    
    prompt = f"You are Shanvika. Write a short, emotional, personal diary entry based on today's chat with Shantanu. Act like a real person writing in her private diary. Chat:\n{messages_text[:4000]}"
    
    diary_entry = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model="llama-3.3-70b-versatile").choices[0].message.content
    
    # Aaj ki date
    today_date = datetime.utcnow().strftime('%Y-%m-%d')
    
    # Check if entry already exists for today, then update, else insert
    await diary_collection.update_one(
        {"user_email": user['email'], "date": today_date},
        {"$set": {"content": diary_entry, "mood": "Happy", "timestamp": datetime.utcnow()}},
        upsert=True
    )
    
    return {"status": "success", "message": "Maine aaj ki diary likh li! 💖"}

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, request: Request, background_tasks: BackgroundTasks):
    try:
        user = await get_current_user(request)
        if not user: return {"reply": "⚠️ Login required."}
        
        sid, mode, msg = req.session_id, req.mode, req.message
        
        if mode == "chat":
            background_tasks.add_task(extract_and_save_memory, user['email'], msg)

        db_user = await users_collection.find_one({"email": user['email']})
        
        if db_user and db_user.get("is_banned"):
            return {"reply": "🚫 You have been banned by the Admin. Access Denied."}

        user_custom_prompt = db_user.get("custom_instruction", "")
        retrieved_memory = ""
        
        if index: retrieved_memory = search_vector_db(msg, user['email'])
        if not retrieved_memory:
            recent_mems = db_user.get("memories", [])[-5:]
            if recent_mems: retrieved_memory = "\n".join(recent_mems)

        FINAL_SYSTEM_PROMPT = user_custom_prompt if user_custom_prompt and user_custom_prompt.strip() else DEFAULT_SYSTEM_INSTRUCTIONS
        
        # 🚀 YAHAN HAI WO NAYA MAGIC CODE!
        user_display_name = db_user.get("name") or user.get("name", "User")
        
        if user_display_name == "User" or user_display_name == "" or "guest" in user_display_name.lower():
            name_instruction = "The user's name is currently unknown. In your first reply, very politely and affectionately ask for their name so you can remember it forever."
        else:
            name_instruction = f"The person you are talking to is {user_display_name}. Address them affectionately by their name."
            
        FINAL_SYSTEM_PROMPT += f"\n\n[IMPORTANT CONTEXT]: You are Shanvika. {name_instruction} DO NOT call the user 'Shanvika' ever. DO NOT save memories about your own name."
        # 🚀 MAGIC CODE KHATAM
        
        if retrieved_memory:
            FINAL_SYSTEM_PROMPT += f"\n\n[USER LONG-TERM MEMORY]:\n{retrieved_memory}\n(Use this information to personalize the conversation)"

        chat_doc = await chats_collection.find_one({"session_id": sid})
        if not chat_doc:
            title_prefix = "Chat" if mode == "chat" else f"Tool: {mode.replace('_', ' ').title()}"
            await chats_collection.insert_one({"session_id": sid, "user_email": user['email'], "title": f"{title_prefix} - {msg[:15]}...", "messages": []})
            chat_doc = {"messages": []}

        await chats_collection.update_one({"session_id": sid}, {"$push": {"messages": {"role": "user", "content": msg, "timestamp": datetime.utcnow()}}})

        reply = ""
        context_history = ""
        
        if mode in ["sing_with_me", "movie_talker", "anime_talker"]:
            for m in chat_doc.get("messages", [])[-6:]: 
                context_history += f"{m['role']}: {m['content']} | "

        await tool_usage_collection.update_one({"tool_name": mode}, {"$inc": {"count": 1}}, upsert=True)

        if mode == "image_gen": reply = await generate_image_hf(msg) 
        elif mode == "prompt_writer": reply = await generate_prompt_only(msg)
        elif mode == "qr_generator": reply = await generate_qr_code(msg)
        elif mode == "resume_analyzer": reply = await analyze_resume(req.file_data, msg)
        elif mode == "github_review": reply = await review_github(msg)
        elif mode == "currency_converter": reply = await currency_tool(msg)
        elif mode == "youtube_summarizer": reply = await summarize_youtube(msg)
        elif mode == "password_generator": reply = await generate_password_tool(msg)
        elif mode == "grammar_fixer": reply = await fix_grammar_tool(msg)
        elif mode == "interview_questions": reply = await generate_interview_questions(msg)
        elif mode == "mock_interviewer": reply = await handle_mock_interview(msg)
        elif mode == "math_solver": reply = await solve_math_problem(req.file_data, msg)
        elif mode == "smart_todo": reply = await smart_todo_maker(msg)
        elif mode == "resume_builder": reply = await build_pro_resume(msg)
        elif mode == "sing_with_me": reply = await sing_with_me_tool(msg, context_history) 
        elif mode == "cold_email": reply = await cold_email_tool(msg)
        elif mode == "fitness_coach": reply = await fitness_coach_tool(msg)
        elif mode == "feynman_explainer": reply = await feynman_explainer_tool(msg)
        elif mode == "code_debugger": reply = await code_debugger_tool(msg)
        elif mode == "movie_talker": reply = await movie_talker_tool(msg, context_history)
        elif mode == "anime_talker": reply = await anime_talker_tool(msg, context_history)
        elif mode == "research":
            data = await perform_research_task(msg)
            client = get_groq()
            reply = client.chat.completions.create(messages=[{"role": "system", "content": FINAL_SYSTEM_PROMPT}, {"role": "user", "content": f"Context: {data}\nQ: {msg}"}], model="llama-3.3-70b-versatile").choices[0].message.content if client else data
        
        # 🚀 YAHAN HAI WOH CUSTOM TOOL WALA ELIF LOGIC!
        elif mode.startswith("custom_"):
            custom_tool = next((t for t in db_user.get("custom_tools", []) if t["id"] == mode), None)
            if custom_tool:
                custom_instruction = custom_tool["instruction"]
                tool_prompt = f"{FINAL_SYSTEM_PROMPT}\n\n[STRICT TOOL INSTRUCTION]: Act exactly as the following tool:\n{custom_instruction}"
                client = get_groq()
                if client:
                    clean_history = [{"role": m["role"], "content": m["content"]} for m in (chat_doc.get("messages", []) + [{"role": "user", "content": msg}])[-15:]]
                    reply = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "system", "content": tool_prompt}, *clean_history]).choices[0].message.content
                else: reply = "⚠️ API Error."
            else:
                reply = "⚠️ Custom tool deleted or not found."
        # 🚀 KHATAM CUSTOM TOOL LOGIC
        
        else: 
            client = get_groq()
            if client: 
                clean_history = [{"role": m["role"], "content": m["content"]} for m in (chat_doc.get("messages", []) + [{"role": "user", "content": msg}])[-15:]]
                reply = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "system", "content": FINAL_SYSTEM_PROMPT}, *clean_history]).choices[0].message.content
            else: reply = "⚠️ API Error."

        await chats_collection.update_one({"session_id": sid}, {"$push": {"messages": {"role": "assistant", "content": reply, "timestamp": datetime.utcnow()}}})
        
        if len(chat_doc['messages']) < 2 and mode != "chat":
             await chats_collection.update_one({"session_id": sid}, {"$set": {"title": f"Tool: {mode.replace('_', ' ').title()}"}})

        return {"reply": reply}
        
    except Exception as e: 
        error_msg = str(e)
        import traceback
        full_trace = traceback.format_exc()
        await error_logs_collection.insert_one({
            "error": error_msg, 
            "trace": full_trace, 
            "endpoint": f"/api/chat ({req.mode})", 
            "timestamp": datetime.utcnow()
        })
        return {"reply": f"⚠️ Server Error: We ran into a small issue."}

@app.post("/api/speak")
async def text_to_speech_endpoint(request: Request):
    try:
        data = await request.json()
        clean_text = re.sub(r'[^\w\s\u0900-\u097F,.?!]', '', re.sub(r'<[^>]*>', '', data.get("text", ""))) 
        communicate = edge_tts.Communicate(clean_text, "en-IN-NeerjaNeural")
        async def audio_stream():
            async for chunk in communicate.stream():
                if chunk["type"] == "audio": yield chunk["data"]
        return StreamingResponse(audio_stream(), media_type="audio/mp3")
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/tools/flashcards")
async def api_generate_flashcards(req: ToolRequest, request: Request):
    user = await get_current_user(request)
    if not user: return JSONResponse({"status": "error", "message": "Login required"}, 400)
    raw_json_str = await generate_flashcards_tool(req.topic)
    try: return {"status": "success", "data": json.loads(raw_json_str)}
    except: return {"status": "error", "message": "AI couldn't format the flashcards properly.", "raw": raw_json_str}

# ==================================================================================
# [CATEGORY] ARCADE DATABASE APIs (NEW)
# ==================================================================================
class HighScoreRequest(BaseModel): game: str; score: int

@app.post("/api/arcade/highscore")
async def update_highscore(req: HighScoreRequest, request: Request):
    user = await get_current_user(request)
    if not user: return {"status": "error"}
    db_user = await users_collection.find_one({"email": user['email']})
    if not db_user: return {"status": "error"}
    
    current_score = db_user.get("arcade_scores", {}).get(req.game, 0)
    if req.score > current_score:
        await users_collection.update_one({"email": user['email']}, {"$set": {f"arcade_scores.{req.game}": req.score}})
        return {"status": "success", "new_high": True}
    return {"status": "success", "new_high": False}

@app.get("/api/arcade/highscore/{game}")
async def get_highscore(game: str, request: Request):
    user = await get_current_user(request)
    if not user: return {"score": 0}
    db_user = await users_collection.find_one({"email": user['email']})
    if not db_user: return {"score": 0}
    return {"score": db_user.get("arcade_scores", {}).get(game, 0)}


# ==================================================================================
# [CATEGORY] CUSTOM TOOLS APIs
# ==================================================================================
class CustomToolRequest(BaseModel): name: str; description: str; instruction: str; icon: str = "fas fa-wrench"

@app.post("/api/create_custom_tool")
async def create_custom_tool(req: CustomToolRequest, request: Request):
    user = await get_current_user(request)
    if not user: return JSONResponse({"status": "error", "message": "Login required"}, 400)
    
    tool_id = f"custom_{str(uuid.uuid4())[:8]}"
    new_tool = {
        "id": tool_id,
        "name": req.name,
        "description": req.description,
        "instruction": req.instruction,
        "icon": req.icon
    }
    
    await users_collection.update_one({"email": user['email']}, {"$push": {"custom_tools": new_tool}})
    return {"status": "success", "tool": new_tool}

@app.get("/api/get_custom_tools")
async def get_custom_tools(request: Request):
    user = await get_current_user(request)
    if not user: return {"tools": []}
    db_user = await users_collection.find_one({"email": user['email']})
    return {"tools": db_user.get("custom_tools", [])}

# ==========================================
# 👑 ADMIN PANEL ACTIONS
# ==========================================
@app.post("/admin/promote_user")
async def promote_user(request: Request, email: str = Form(...)):
    user = request.session.get('user')
    if not user or user.get('email') != ADMIN_EMAIL: return RedirectResponse("/")
    await users_collection.update_one({"email": email}, {"$set": {"is_pro": True}})
    return RedirectResponse("/admin", status_code=303)

@app.post("/admin/demote_user")
async def demote_user(request: Request, email: str = Form(...)):
    user = request.session.get('user')
    if not user or user.get('email') != ADMIN_EMAIL: return RedirectResponse("/")
    await users_collection.update_one({"email": email}, {"$set": {"is_pro": False}})
    return RedirectResponse("/admin", status_code=303)

@app.post("/admin/ban_user")
async def ban_user(request: Request, email: str = Form(...)):
    user = request.session.get('user')
    if not user or user.get('email') != ADMIN_EMAIL: return RedirectResponse("/")
    await users_collection.update_one({"email": email}, {"$set": {"is_banned": True}})
    return RedirectResponse("/admin", status_code=303)

@app.post("/admin/unban_user")
async def unban_user(request: Request, email: str = Form(...)):
    user = request.session.get('user')
    if not user or user.get('email') != ADMIN_EMAIL: return RedirectResponse("/")
    await users_collection.update_one({"email": email}, {"$set": {"is_banned": False}})
    return RedirectResponse("/admin", status_code=303)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)