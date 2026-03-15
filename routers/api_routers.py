# ==================================================================================
#  FILE: routers/api_routers.py
#  DESCRIPTION: All API Endpoints — 4-Mode Chat Brain + All Missing Endpoints Restored
#
#  CHAT MODES:
#  1. "chat"         → Normal Mode   : Groq LLM + long-term memory + system prompt
#  2. "research"     → Search Mode   : DuckDuckGo web search → AI synthesis
#  3. "code_debugger"→ Coding Mode   : tools_lab.code_debugger_tool (coding models)
#  4. "ethrix_agent" → Agent Mode    : External HF Space API integration
#  + All tool modes + custom user tools
# ==================================================================================

# ==========================================
# [SECTION 1] IMPORTS
# ==========================================
from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from datetime import datetime
import os
import json
import httpx
import random
import hashlib
import traceback
import uuid
import re
import google.generativeai as genai
from groq import Groq
from duckduckgo_search import DDGS
import edge_tts

import tools_lab
import core.database as db_module
from image_generation import generate_image_free, generate_image_pro

router = APIRouter()


# ==========================================
# [SECTION 2] SYSTEM INTELLIGENCE
# ==========================================
def load_system_instructions():
    try:
        with open("character_config.json", "r", encoding="utf-8") as f:
            config       = json.load(f)
            rules_text   = "\n".join([f"- {rule}"   for rule   in config.get("strict_rules", [])])
            tactics_text = "\n".join([f"- {tactic}" for tactic in config.get("psychological_tactics", [])])
            c_profile    = config.get("creator_profile", {})
            prompt = config.get("system_prompt_template", "").format(
                name        = config["identity"]["name"],
                creator     = config["identity"]["creator"],
                rules       = rules_text,
                tactics     = tactics_text,
                c_name      = c_profile.get("name"),
                c_college   = c_profile.get("college"),
                c_skills    = c_profile.get("skills"),
                c_interests = c_profile.get("interests"),
            )
            return prompt
    except Exception as e:
        print(f"[Config Load Error]: {e}")
        return "You are Ethrix. Always reply in the user's language."

DEFAULT_SYSTEM_INSTRUCTIONS = load_system_instructions()


# ==========================================
# [SECTION 3] API KEY POOL HELPERS
# ==========================================
def get_random_groq_key():
    keys     = os.getenv("GROQ_API_KEY_POOL", "").split(",")
    possible = [k.strip() for k in keys if k.strip()]
    return random.choice(possible) if possible else os.getenv("GROQ_API_KEY")

def get_groq():
    key = get_random_groq_key()
    return Groq(api_key=key) if key else None

def get_random_gemini_key():
    keys     = os.getenv("GEMINI_API_KEY_POOL", "").split(",")
    possible = [k.strip() for k in keys if k.strip()]
    return random.choice(possible) if possible else os.getenv("GEMINI_API_KEY")

def get_random_openrouter_key():
    keys     = os.getenv("OPENROUTER_API_KEY_POOL", "").split(",")
    possible = [k.strip() for k in keys if k.strip()]
    return random.choice(possible) if possible else os.getenv("OPENROUTER_API_KEY")


# ==========================================
# [SECTION 4] MEMORY & VECTOR DB HELPERS
# ==========================================
def get_embedding(text: str) -> list:
    try:
        key = get_random_gemini_key()
        if key:
            genai.configure(api_key=key)
        result = genai.embed_content(model="models/embedding-001", content=text, task_type="retrieval_document")
        return result['embedding']
    except Exception:
        return []

def search_vector_db(query: str, user_email: str) -> str:
    if not db_module.index:
        return ""
    vec = get_embedding(query)
    if not vec:
        return ""
    res = db_module.index.query(vector=vec, top_k=3, include_metadata=True, filter={"email": user_email})
    return "\n".join([m['metadata']['text'] for m in res['matches']])

async def perform_research_task(query: str) -> str:
    try:
        results   = DDGS().text(query, max_results=3)
        formatted = "\n\n".join([f"🔹 **{r['title']}**\n{r['body']}" for r in results])
        return f"📊 **Research:**\n\n{formatted}"
    except Exception:
        return "⚠️ Research failed. The search engine is temporarily unavailable."

async def extract_and_save_memory(user_email: str, user_message: str):
    try:
        triggers = [
            "my name is", "i live in", "i like", "i love", "remember", "save this",
            "my birthday", "i am", "mera naam", "main rehta hu", "mujhe pasand hai",
            "yaad rakhna", "yaad rakho", "save kar", "note kar", "isko save"
        ]
        if not any(t in user_message.lower() for t in triggers) and len(user_message.split()) < 4:
            return

        extraction_prompt = (
            f'Analyze this user message: "{user_message}"\n'
            "Extract ANY permanent user fact or anything the user explicitly asks to save/remember. "
            "Return ONLY the fact as a short sentence. "
            "DO NOT save facts about the AI (like 'User knows Ethrix'). "
            "If nothing worth remembering, return 'NO_DATA'."
        )

        openrouter_key = get_random_openrouter_key()
        if not openrouter_key:
            return

        headers = {"Authorization": f"Bearer {openrouter_key}", "Content-Type": "application/json"}
        fast_models = ["zhipu/glm-4-flash", "stepfun/step-1-flash", "meta-llama/llama-3-8b-instruct:free"]
        data = {"model": random.choice(fast_models), "messages": [{"role": "user", "content": extraction_prompt}]}

        async with httpx.AsyncClient() as http_client:
            resp      = await http_client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=15.0)
            extracted = resp.json()['choices'][0]['message']['content'].strip()

        if "NO_DATA" not in extracted and len(extracted) > 5:
            clean_memory = extracted.replace("User", "You").replace("user", "You").replace("Ethrix", "me")
            db_user = await db_module.users_collection.find_one({"email": user_email})
            if db_user and clean_memory in db_user.get("memories", []):
                return
            await db_module.users_collection.update_one({"email": user_email}, {"$push": {"memories": clean_memory}})
            if db_module.index:
                vec = get_embedding(clean_memory)
                if vec:
                    mem_id = f"{user_email}_{hashlib.md5(clean_memory.encode()).hexdigest()}"
                    db_module.index.upsert(vectors=[(mem_id, vec, {"text": clean_memory, "email": user_email})])
    except Exception as e:
        print(f"[Auto-Memory Error]: {e}")


# ==========================================
# [SECTION 5] REQUEST MODELS
# ==========================================
class ChatRequest(BaseModel):
    message:    str
    session_id: str
    mode:       str         = "chat"
    file_data:  str | None  = None
    file_type:  str | None  = None

class InstructionRequest(BaseModel): instruction: str
class MemoryRequest(BaseModel):      memory_text: str
class RenameRequest(BaseModel):      session_id: str; new_title: str
class UpdateProfileRequest(BaseModel): name: str
class FeedbackRequest(BaseModel):    message_id: str; user_email: str; type: str; category: str; comment: str | None = None
class GalleryDeleteRequest(BaseModel): url: str
class ToolRequest(BaseModel):        topic: str
class CustomToolRequest(BaseModel):  name: str; description: str; instruction: str; icon: str = "fas fa-wrench"
class HighScoreRequest(BaseModel):   game: str; score: int

class AdvancedImageGenRequest(BaseModel):
    prompt: str
    style:  str = "realistic"
    tier:   str = "free"


# ==========================================
# [SECTION 6] PROFILE & USER ENDPOINTS
# ==========================================
@router.get("/api/profile")
async def get_profile(request: Request):
    user = await db_module.get_current_user(request)
    if not user: return {}
    db_user = await db_module.users_collection.find_one({"email": user['email']}) or {}
    is_pro  = db_user.get("is_pro", False) or (user['email'] == db_module.ADMIN_EMAIL)
    return {
        "name":               db_user.get("name") or user.get("name", "User"),
        "avatar":             db_user.get("picture") or user.get("picture"),
        "plan":               "Pro Plan" if is_pro else "Free Plan",
        "custom_instruction": db_user.get("custom_instruction", "")
    }

@router.post("/api/update_profile")
async def update_profile(req: UpdateProfileRequest, request: Request):
    user = await db_module.get_current_user(request)
    if not user: return JSONResponse({"status": "error", "message": "Login required"}, 400)
    await db_module.users_collection.update_one({"email": user['email']}, {"$set": {"name": req.name}})
    return {"status": "success"}

@router.post("/api/save_instruction")
async def save_instruction(req: InstructionRequest, request: Request):
    user = await db_module.get_current_user(request)
    if not user: return JSONResponse({"status": "error", "message": "Login required"}, 400)
    await db_module.users_collection.update_one({"email": user['email']}, {"$set": {"custom_instruction": req.instruction}})
    return {"status": "success"}


# ==========================================
# [SECTION 7] CHAT HISTORY ENDPOINTS
# ==========================================
@router.get("/api/history")
async def get_history(request: Request):
    user = await db_module.get_current_user(request)
    if not user: return {"history": []}
    cursor  = db_module.chats_collection.find({"user_email": user['email']}).sort("_id", -1).limit(50)
    history = []
    async for chat in cursor:
        history.append({"id": chat["session_id"], "title": chat.get("title", "New Chat")})
    return {"history": history}

@router.get("/api/new_chat")
async def create_new_chat(request: Request):
    return {"session_id": str(uuid.uuid4())[:8], "messages": []}

@router.get("/api/chat/{session_id}")
async def get_chat_by_session(session_id: str):
    chat = await db_module.chats_collection.find_one({"session_id": session_id})
    return {"messages": chat.get("messages", [])} if chat else {"messages": []}

@router.post("/api/rename_chat")
async def rename_chat(req: RenameRequest):
    await db_module.chats_collection.update_one({"session_id": req.session_id}, {"$set": {"title": req.new_title}})
    return {"status": "ok"}

@router.delete("/api/delete_all_chats")
async def delete_all_chats(request: Request):
    user = await db_module.get_current_user(request)
    if not user: return JSONResponse({"status": "error"}, 400)
    await db_module.chats_collection.delete_many({"user_email": user['email']})
    return {"status": "ok"}


# ==========================================
# [SECTION 8] MEMORY ENDPOINTS
# ==========================================
@router.get("/api/memories")
async def get_memories(request: Request):
    user = await db_module.get_current_user(request)
    if not user: return {"memories": []}
    data = await db_module.users_collection.find_one({"email": user['email']})
    mems = data.get("memories", []) if data else []
    return {"memories": mems[::-1]}

@router.post("/api/add_memory")
async def add_memory(req: MemoryRequest, request: Request):
    user = await db_module.get_current_user(request)
    if not user: return JSONResponse({"status": "error"}, 400)
    await db_module.users_collection.update_one({"email": user['email']}, {"$push": {"memories": req.memory_text}})
    if db_module.index:
        try:
            vec = get_embedding(req.memory_text)
            if vec:
                mem_id = f"{user['email']}_{hashlib.md5(req.memory_text.encode()).hexdigest()}"
                db_module.index.upsert(vectors=[(mem_id, vec, {"text": req.memory_text, "email": user['email']})])
        except Exception as e:
            print(f"Vector Save Error: {e}")
    return {"status": "success"}

@router.post("/api/delete_memory")
async def delete_memory(req: MemoryRequest, request: Request):
    user = await db_module.get_current_user(request)
    if not user: return JSONResponse({"status": "error"}, 400)
    await db_module.users_collection.update_one({"email": user['email']}, {"$pull": {"memories": req.memory_text}})
    if db_module.index:
        try:
            mem_id = f"{user['email']}_{hashlib.md5(req.memory_text.encode()).hexdigest()}"
            db_module.index.delete(ids=[mem_id])
        except Exception as e:
            print(f"Vector Delete Error: {e}")
    return {"status": "ok"}


# ==========================================
# [SECTION 9] FEEDBACK & GALLERY
# ==========================================
@router.post("/api/feedback")
async def submit_feedback(req: FeedbackRequest):
    try:
        feedback_doc = {
            "message_id": req.message_id, "user_email": req.user_email,
            "type": req.type, "category": req.category,
            "comment": req.comment, "timestamp": datetime.utcnow()
        }
        await db_module.feedback_collection.insert_one(feedback_doc)
        return {"status": "success", "message": "Feedback recorded"}
    except Exception:
        return JSONResponse({"status": "error"}, 500)

@router.post("/api/delete_gallery_item")
async def delete_gallery_item(req: GalleryDeleteRequest, request: Request):
    return {"status": "ok"}


# ==========================================
# [SECTION 10] DIARY ENDPOINTS
# ==========================================
@router.get("/api/diary_entries")
async def get_diary_entries(request: Request):
    user = await db_module.get_current_user(request)
    if not user: return {"entries": []}
    cursor  = db_module.diary_collection.find({"user_email": user['email']}).sort("date", -1).limit(30)
    entries = []
    async for entry in cursor:
        entries.append({"date": entry['date'], "content": entry['content'], "mood": entry.get("mood", "Neutral")})
    return {"entries": entries}

@router.post("/api/trigger_diary")
async def manual_trigger_diary(request: Request):
    user = await db_module.get_current_user(request)
    if not user: return JSONResponse({"status": "error", "message": "Login required"}, 400)

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    chat_doc    = await db_module.chats_collection.find_one({
        "user_email":            user['email'],
        "messages.timestamp":    {"$gte": today_start}
    })

    if not chat_doc or not chat_doc.get("messages"):
        return JSONResponse({"status": "error", "message": "Aaj humne koi baat hi nahi ki! Pehle thodi baatein toh karo. 🥺"})

    messages_text = ""
    for m in chat_doc.get("messages", []):
        msg_time = m.get("timestamp")
        if msg_time and msg_time >= today_start:
            messages_text += f"{m['role']}: {m['content']}\n"

    groq_client = get_groq()
    if not groq_client:
        return JSONResponse({"status": "error", "message": "AI is sleeping."})

    prompt      = f"You are Ethrix. Write a short, emotional, personal diary entry based on today's chat with Shantanu. Act like a real person writing in her private diary. Chat:\n{messages_text[:4000]}"
    diary_entry = groq_client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model="llama-3.3-70b-versatile").choices[0].message.content
    today_date  = datetime.utcnow().strftime('%Y-%m-%d')

    await db_module.diary_collection.update_one(
        {"user_email": user['email'], "date": today_date},
        {"$set": {"content": diary_entry, "mood": "Happy", "timestamp": datetime.utcnow()}},
        upsert=True
    )
    return {"status": "success", "message": "Maine aaj ki diary likh li! 💖"}


# ==========================================
# [SECTION 11] ADVANCED IMAGE GENERATION
# ==========================================
@router.post("/api/image_gen")
async def advanced_image_gen_api(req: AdvancedImageGenRequest, request: Request):
    try:
        user = await db_module.get_current_user(request)
        if not user:
            return JSONResponse({"status": "error", "message": "⚠️ Login required."}, 400)
        if not req.prompt:
            return {"status": "error", "message": "⚠️ Prompt cannot be empty."}

        image_url = await generate_image_pro(req.prompt, req.style) if req.tier == "pro" else await generate_image_free(req.prompt, req.style)

        if image_url.startswith("⚠️"):
            return {"status": "error", "message": image_url}

        await db_module.tool_usage_collection.update_one(
            {"tool_name": f"image_gen_{req.tier}"}, {"$inc": {"count": 1}}, upsert=True
        )
        return {"status": "success", "image_url": image_url}
    except Exception as e:
        return {"status": "error", "message": f"⚠️ Server Error: {str(e)}"}


# ==========================================
# [SECTION 12] TEXT-TO-SPEECH
# ==========================================
@router.post("/api/speak")
async def text_to_speech_endpoint(request: Request):
    try:
        data       = await request.json()
        clean_text = re.sub(r'[^\w\s\u0900-\u097F,.?!]', '', re.sub(r'<[^>]*>', '', data.get("text", "")))
        communicate = edge_tts.Communicate(clean_text, "en-IN-NeerjaNeural")
        async def audio_stream():
            async for chunk in communicate.stream():
                if chunk["type"] == "audio": yield chunk["data"]
        return StreamingResponse(audio_stream(), media_type="audio/mp3")
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ==========================================
# [SECTION 13] TOOLS-SPECIFIC ENDPOINTS
# ==========================================
@router.post("/api/tools/flashcards")
async def api_generate_flashcards(req: ToolRequest, request: Request):
    user = await db_module.get_current_user(request)
    if not user: return JSONResponse({"status": "error", "message": "Login required"}, 400)
    raw_json_str = await tools_lab.generate_flashcards_tool(req.topic)
    try:
        return {"status": "success", "data": json.loads(raw_json_str)}
    except Exception:
        return {"status": "error", "message": "AI couldn't format the flashcards properly.", "raw": raw_json_str}


# ==========================================
# [SECTION 14] ARCADE ENDPOINTS
# ==========================================
@router.post("/api/arcade/highscore")
async def update_highscore(req: HighScoreRequest, request: Request):
    user = await db_module.get_current_user(request)
    if not user: return {"status": "error"}
    db_user = await db_module.users_collection.find_one({"email": user['email']})
    if not db_user: return {"status": "error"}
    current_score = db_user.get("arcade_scores", {}).get(req.game, 0)
    if req.score > current_score:
        await db_module.users_collection.update_one({"email": user['email']}, {"$set": {f"arcade_scores.{req.game}": req.score}})
        return {"status": "success", "new_high": True}
    return {"status": "success", "new_high": False}

@router.get("/api/arcade/highscore/{game}")
async def get_highscore(game: str, request: Request):
    user = await db_module.get_current_user(request)
    if not user: return {"score": 0}
    db_user = await db_module.users_collection.find_one({"email": user['email']})
    if not db_user: return {"score": 0}
    return {"score": db_user.get("arcade_scores", {}).get(game, 0)}


# ==========================================
# [SECTION 15] CUSTOM TOOLS ENDPOINTS
# ==========================================
@router.post("/api/create_custom_tool")
async def create_custom_tool(req: CustomToolRequest, request: Request):
    user = await db_module.get_current_user(request)
    if not user: return JSONResponse({"status": "error", "message": "Login required"}, 400)
    tool_id  = f"custom_{str(uuid.uuid4())[:8]}"
    new_tool = {"id": tool_id, "name": req.name, "description": req.description, "instruction": req.instruction, "icon": req.icon}
    await db_module.users_collection.update_one({"email": user['email']}, {"$push": {"custom_tools": new_tool}})
    return {"status": "success", "tool": new_tool}

@router.get("/api/get_custom_tools")
async def get_custom_tools(request: Request):
    user = await db_module.get_current_user(request)
    if not user: return {"tools": []}
    db_user = await db_module.users_collection.find_one({"email": user['email']})
    return {"tools": db_user.get("custom_tools", []) if db_user else []}


# ==========================================
# [SECTION 16] MAIN CHAT ENDPOINT
# The 4-mode brain of Ethrix AI.
# ==========================================
@router.post("/api/chat")
async def main_chat(req: ChatRequest, request: Request, background_tasks: BackgroundTasks):
    try:
        user = await db_module.get_current_user(request)
        if not user:
            return {"reply": "⚠️ Login required."}

        sid  = req.session_id
        mode = req.mode
        msg  = req.message

        if mode == "chat":
            background_tasks.add_task(extract_and_save_memory, user['email'], msg)

        db_user = await db_module.users_collection.find_one({"email": user['email']})

        if db_user and db_user.get("is_banned"):
            return {"reply": "🚫 You have been banned by the Admin. Access Denied."}

        user_custom_prompt = (db_user.get("custom_instruction", "") if db_user else "")
        retrieved_memory   = ""

        if db_module.index:
            retrieved_memory = search_vector_db(msg, user['email'])
        if not retrieved_memory and db_user:
            recent_mems = db_user.get("memories", [])[-5:]
            if recent_mems:
                retrieved_memory = "\n".join(recent_mems)

        FINAL_SYSTEM_PROMPT = (
            user_custom_prompt if user_custom_prompt and user_custom_prompt.strip()
            else DEFAULT_SYSTEM_INSTRUCTIONS
        )

        user_display_name = (
            (db_user.get("name") if db_user else None) or user.get("name", "User")
        )

        if user_display_name in ("User", "") or "guest" in user_display_name.lower():
            name_instruction = "The user's name is currently unknown. In your first reply, very politely and affectionately ask for their name so you can remember it forever."
        else:
            name_instruction = f"The person you are talking to is {user_display_name}. Address them affectionately by their name."

        FINAL_SYSTEM_PROMPT += (
            f"\n\n[IMPORTANT CONTEXT]: You are Ethrix. {name_instruction} "
            "DO NOT call the user 'Ethrix' ever. DO NOT save memories about your own name."
        )
        if retrieved_memory:
            FINAL_SYSTEM_PROMPT += f"\n\n[USER LONG-TERM MEMORY]:\n{retrieved_memory}\n(Use this information to personalise the conversation)"

        chat_doc = await db_module.chats_collection.find_one({"session_id": sid})
        if not chat_doc:
            title_prefix = "Chat" if mode == "chat" else f"Tool: {mode.replace('_', ' ').title()}"
            await db_module.chats_collection.insert_one({
                "session_id": sid, "user_email": user['email'],
                "title":      f"{title_prefix} - {msg[:15]}...", "messages": []
            })
            chat_doc = {"messages": []}

        await db_module.chats_collection.update_one(
            {"session_id": sid},
            {"$push": {"messages": {"role": "user", "content": msg, "timestamp": datetime.utcnow()}}}
        )

        context_history = ""
        if mode in ("sing_with_me", "movie_talker", "anime_talker"):
            for m in chat_doc.get("messages", [])[-6:]:
                context_history += f"{m['role']}: {m['content']} | "

        await db_module.tool_usage_collection.update_one({"tool_name": mode}, {"$inc": {"count": 1}}, upsert=True)

        # ── MODE ROUTING ──────────────────────────────────────────────────────
        reply = ""

        if mode == "image_gen":
            reply = await tools_lab.generate_image_hf(msg)
        elif mode == "prompt_writer":
            reply = await tools_lab.generate_prompt_only(msg)
        elif mode == "qr_generator":
            reply = await tools_lab.generate_qr_code(msg)
        elif mode == "resume_analyzer":
            reply = await tools_lab.analyze_resume(req.file_data, msg)
        elif mode == "github_review":
            reply = await tools_lab.review_github(msg)
        elif mode == "currency_converter":
            reply = await tools_lab.currency_tool(msg)
        elif mode == "youtube_summarizer":
            reply = await tools_lab.summarize_youtube(msg)
        elif mode == "password_generator":
            reply = await tools_lab.generate_password_tool(msg)
        elif mode == "grammar_fixer":
            reply = await tools_lab.fix_grammar_tool(msg)
        elif mode == "interview_questions":
            reply = await tools_lab.generate_interview_questions(msg)
        elif mode == "mock_interviewer":
            reply = await tools_lab.handle_mock_interview(msg)
        elif mode == "math_solver":
            reply = await tools_lab.solve_math_problem(req.file_data, msg)
        elif mode == "smart_todo":
            reply = await tools_lab.smart_todo_maker(msg)
        elif mode == "resume_builder":
            reply = await tools_lab.build_pro_resume(msg)
        elif mode == "sing_with_me":
            reply = await tools_lab.sing_with_me_tool(msg, context_history)
        elif mode == "cold_email":
            reply = await tools_lab.cold_email_tool(msg)
        elif mode == "fitness_coach":
            reply = await tools_lab.fitness_coach_tool(msg)
        elif mode == "feynman_explainer":
            reply = await tools_lab.feynman_explainer_tool(msg)
        elif mode == "movie_talker":
            reply = await tools_lab.movie_talker_tool(msg, context_history)
        elif mode == "anime_talker":
            reply = await tools_lab.anime_talker_tool(msg, context_history)

        # MODE 3: CODING MODE
        elif mode == "code_debugger":
            reply = await tools_lab.code_debugger_tool(msg)

        # MODE 2: SEARCH MODE
        elif mode == "research":
            research_data = await perform_research_task(msg)
            groq_client   = get_groq()
            if groq_client:
                reply = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": FINAL_SYSTEM_PROMPT},
                        {"role": "user",   "content": f"Context:\n{research_data}\n\nUser Question: {msg}"}
                    ]
                ).choices[0].message.content
            else:
                reply = research_data

        # MODE 4: AGENT MODE
        # ✅ FIX: Pehle FINAL_SYSTEM_PROMPT bheja jaata tha user_context mein — us wajah se
        # HF Space ka model answer ke end mein malformed <function=search_web{...}> append
        # kar deta tha, jo 400 tool_use_failed error deta tha.
        # Ab sirf user ka naam bhejte hain — agent ka apna system prompt hai HF Space par.
        elif mode == "ethrix_agent":
            try:
                async with httpx.AsyncClient() as http_client:
                    agent_headers = {
                        "x-api-key":    os.getenv("AGENT_API_KEY", "shantanu_super_secret_key"),
                        "Content-Type": "application/json"
                    }
                    clean_history = [
                        {"role": m["role"], "content": m["content"]}
                        for m in (chat_doc.get("messages", []) + [{"role": "user", "content": msg}])[-15:]
                    ]
                    minimal_context = f"The user's name is {user_display_name}."
                    payload   = {"query": msg, "user_context": minimal_context, "history": clean_history, "user_email": user['email']}
                    AGENT_URL = os.getenv("HF_AGENT_URL", "https://shantanupathak94-ai-agent-for-ethrix-ai.hf.space/run-agent")
                    resp      = await http_client.post(AGENT_URL, headers=agent_headers, json=payload, timeout=40.0)
                    if resp.status_code == 200:
                        hf_reply = resp.json().get("response", "")
                        # HF Space 200 deta hai lekin response mein error string bhejta hai
                        # (tool_use_failed) — matlab HF ka model fail hua, local fallback chalao
                        HF_ERROR_SIGNALS = ["Processing Error", "tool_use_failed", "failed_generation", "Failed to call a function", "<function="]
                        if any(s in hf_reply for s in HF_ERROR_SIGNALS) or not hf_reply.strip():
                            from tools_lab import run_agent_task
                            reply = await run_agent_task(msg)
                        else:
                            reply = hf_reply
                    else:
                        from tools_lab import run_agent_task
                        reply = await run_agent_task(msg)
            except Exception as agent_error:
                try:
                    from tools_lab import run_agent_task
                    reply = await run_agent_task(msg)
                except Exception:
                    reply = f"⚠️ Ethrix Agent is offline or unreachable: {str(agent_error)}"

        # CUSTOM USER TOOLS
        elif mode.startswith("custom_"):
            custom_tool = next(
                (t for t in (db_user.get("custom_tools", []) if db_user else []) if t["id"] == mode), None
            )
            if custom_tool:
                tool_prompt = f"{FINAL_SYSTEM_PROMPT}\n\n[STRICT TOOL INSTRUCTION]: Act exactly as the following tool:\n{custom_tool['instruction']}"
                groq_client = get_groq()
                if groq_client:
                    clean_history = [{"role": m["role"], "content": m["content"]} for m in (chat_doc.get("messages", []) + [{"role": "user", "content": msg}])[-15:]]
                    reply = groq_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "system", "content": tool_prompt}, *clean_history]).choices[0].message.content
                else:
                    reply = "⚠️ AI API Error. Please try again."
            else:
                reply = "⚠️ This custom tool was deleted or could not be found."

        # MODE 1: NORMAL CHAT (default)
        else:
            groq_client = get_groq()
            if groq_client:
                clean_history = [{"role": m["role"], "content": m["content"]} for m in (chat_doc.get("messages", []) + [{"role": "user", "content": msg}])[-15:]]
                reply = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "system", "content": FINAL_SYSTEM_PROMPT}, *clean_history]
                ).choices[0].message.content
            else:
                reply = "⚠️ AI API Error. Please try again in a moment."

        await db_module.chats_collection.update_one(
            {"session_id": sid},
            {"$push": {"messages": {"role": "assistant", "content": reply, "timestamp": datetime.utcnow()}}}
        )
        if len(chat_doc.get("messages", [])) < 2 and mode != "chat":
            await db_module.chats_collection.update_one({"session_id": sid}, {"$set": {"title": f"Tool: {mode.replace('_', ' ').title()}"}})

        return {"reply": reply}

    except Exception as e:
        full_trace = traceback.format_exc()
        await db_module.error_logs_collection.insert_one({
            "error": str(e), "trace": full_trace,
            "endpoint": f"/api/chat ({req.mode})", "timestamp": datetime.utcnow()
        })
        return {"reply": "⚠️ Server Error: We ran into a small issue. Please try again!"}


# ==========================================
# [SECTION 17] DYNAMIC TOOLS ENDPOINT
# New feature — kept 100% intact.
# ==========================================
@router.post("/api/tool/{tool_name}")
async def handle_tool(tool_name: str, request: Request):
    try:
        data       = await request.json()
        user_input = data.get("input", "")
        result     = ""

        if tool_name == "youtube_summarizer":
            result = await tools_lab.summarize_youtube(user_input)
        elif tool_name == "github_review":
            result = await tools_lab.review_github(user_input)
        elif tool_name == "image_gen":
            result = await tools_lab.generate_image_hf(user_input)
        elif tool_name == "password_generator":
            result = await tools_lab.generate_password_tool(user_input)
        elif tool_name == "qr_generator":
            result = await tools_lab.generate_qr_code(user_input)
        elif tool_name == "grammar_fixer":
            result = await tools_lab.fix_grammar_tool(user_input)
        elif tool_name == "smart_todo":
            result = await tools_lab.smart_todo_maker(user_input)
        elif tool_name == "currency_converter":
            result = await tools_lab.currency_tool(user_input)
        elif tool_name == "fitness_coach":
            result = await tools_lab.fitness_coach_tool(user_input)
        elif tool_name == "feynman_explainer":
            result = await tools_lab.feynman_explainer_tool(user_input)
        elif tool_name == "code_debugger":
            result = await tools_lab.code_debugger_tool(user_input)
        elif tool_name == "cold_email":
            result = await tools_lab.cold_email_tool(user_input)
        elif tool_name == "flashcards":
            result = await tools_lab.generate_flashcards_tool(user_input)
        elif tool_name == "movie_talker":
            history = data.get("history", "")
            result  = await tools_lab.movie_talker_tool(user_input, history)
        elif tool_name == "anime_talker":
            history = data.get("history", "")
            result  = await tools_lab.anime_talker_tool(user_input, history)
        elif tool_name == "math_solver":
            file_data = data.get("file_data")
            result    = await tools_lab.solve_math_problem(file_data, user_input)
        elif tool_name == "resume_analyzer":
            file_data = data.get("file_data")
            result    = await tools_lab.analyze_resume(file_data, user_input)
        else:
            return JSONResponse({"status": "error", "message": "Tool not found or not connected yet!"}, status_code=404)

        return {"status": "success", "result": result}

    except Exception as e:
        print(f"Tool Error ({tool_name}): {str(e)}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)