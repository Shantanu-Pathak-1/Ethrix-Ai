# ==================================================================================
#  FILE: routers/api_routers.py
#  DESCRIPTION: All API Endpoints — Main Chat (4-Mode Brain) + Dynamic Tools
#
#  CHAT MODES (restored from original working logic):
#  1. "chat"         → Normal Mode   : Groq LLM + long-term memory + system prompt
#  2. "research"     → Search Mode   : DuckDuckGo web search → AI synthesis
#  3. "code_debugger"→ Coding Mode   : tools_lab.code_debugger_tool (coding models)
#  4. "ethrix_agent" → Agent Mode    : External HF Space API integration
#  + All individual tool modes (image_gen, qr_generator, resume_analyzer, etc.)
#  + Custom user-created tools (mode starts with "custom_")
# ==================================================================================

# ==========================================
# [SECTION 1] IMPORTS
# ==========================================
from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime
import os
import json
import httpx
import random
import hashlib
import traceback
import google.generativeai as genai
from groq import Groq
from duckduckgo_search import DDGS

import tools_lab
import core.database as db_module

router = APIRouter()


# ==========================================
# [SECTION 2] SYSTEM INTELLIGENCE
# Loads Ethrix's character, personality rules,
# and creator profile from character_config.json
# ==========================================
def load_system_instructions():
    """Reads character_config.json and builds the master system prompt for Ethrix."""
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


# Load once at startup so every request has it instantly
DEFAULT_SYSTEM_INSTRUCTIONS = load_system_instructions()


# ==========================================
# [SECTION 3] API KEY POOL HELPERS
# Random-rotation across multiple keys prevents
# rate-limiting on any single key.
# ==========================================
def get_random_groq_key():
    """Returns a random Groq API key from the pool env var."""
    keys     = os.getenv("GROQ_API_KEY_POOL", "").split(",")
    possible = [k.strip() for k in keys if k.strip()]
    return random.choice(possible) if possible else os.getenv("GROQ_API_KEY")


def get_groq():
    """Returns an initialised Groq client or None if no key is available."""
    key = get_random_groq_key()
    return Groq(api_key=key) if key else None


def get_random_gemini_key():
    """Returns a random Gemini API key from the pool env var."""
    keys     = os.getenv("GEMINI_API_KEY_POOL", "").split(",")
    possible = [k.strip() for k in keys if k.strip()]
    return random.choice(possible) if possible else os.getenv("GEMINI_API_KEY")


def get_random_openrouter_key():
    """Returns a random OpenRouter API key from the pool env var."""
    keys     = os.getenv("OPENROUTER_API_KEY_POOL", "").split(",")
    possible = [k.strip() for k in keys if k.strip()]
    return random.choice(possible) if possible else os.getenv("OPENROUTER_API_KEY")


# ==========================================
# [SECTION 4] MEMORY & VECTOR DB HELPERS
# Vector embeddings via Gemini + Pinecone retrieval.
# Falls back to recent MongoDB memories if Pinecone
# is not configured or returns nothing.
# ==========================================
def get_embedding(text: str) -> list:
    """Generates a vector embedding for the given text using Gemini."""
    try:
        key = get_random_gemini_key()
        if key:
            genai.configure(api_key=key)
        result = genai.embed_content(
            model="models/embedding-001",
            content=text,
            task_type="retrieval_document"
        )
        return result['embedding']
    except Exception:
        return []


def search_vector_db(query: str, user_email: str) -> str:
    """
    Queries Pinecone for the top-3 most semantically relevant memories for this user.
    Returns them as a newline-separated string, or '' if Pinecone is unavailable.
    """
    if not db_module.index:
        return ""
    vec = get_embedding(query)
    if not vec:
        return ""
    res = db_module.index.query(
        vector=vec,
        top_k=3,
        include_metadata=True,
        filter={"email": user_email}
    )
    return "\n".join([m['metadata']['text'] for m in res['matches']])


async def perform_research_task(query: str) -> str:
    """
    MODE 2 — SEARCH MODE helper.
    Uses DuckDuckGo to fetch the top 3 web results for the query
    and formats them as a readable context block for the AI to synthesise.
    """
    try:
        results   = DDGS().text(query, max_results=3)
        formatted = "\n\n".join([f"🔹 **{r['title']}**\n{r['body']}" for r in results])
        return f"📊 **Research:**\n\n{formatted}"
    except Exception:
        return "⚠️ Research failed. The search engine is temporarily unavailable."


async def extract_and_save_memory(user_email: str, user_message: str):
    """
    Background task — runs silently after every normal chat message.
    Checks if the message contains a personal fact the user wants saved,
    extracts it via a fast LLM, de-duplicates, then stores in MongoDB + Pinecone.
    """
    try:
        # Only bother calling the LLM if a save-trigger phrase is detected
        # OR the message is long enough to potentially contain personal info
        triggers = [
            "my name is", "i live in", "i like", "i love", "remember", "save this",
            "my birthday", "i am", "mera naam", "main rehta hu", "mujhe pasand hai",
            "yaad rakhna", "yaad rakho", "save kar", "note kar", "isko save"
        ]
        if (
            not any(t in user_message.lower() for t in triggers)
            and len(user_message.split()) < 4
        ):
            return

        extraction_prompt = (
            f'Analyze this user message: "{user_message}"\n'
            "Extract ANY permanent user fact or anything the user explicitly asks to "
            "save/remember. Return ONLY the fact as a short sentence. "
            "DO NOT save facts about the AI (like 'User knows Ethrix'). "
            "If nothing worth remembering, return 'NO_DATA'."
        )

        openrouter_key = get_random_openrouter_key()
        if not openrouter_key:
            return

        headers = {
            "Authorization": f"Bearer {openrouter_key}",
            "Content-Type":  "application/json"
        }
        # Use small, fast models for memory extraction to keep latency near-zero
        fast_models = [
            "zhipu/glm-4-flash",
            "stepfun/step-1-flash",
            "meta-llama/llama-3-8b-instruct:free"
        ]
        data = {
            "model":    random.choice(fast_models),
            "messages": [{"role": "user", "content": extraction_prompt}]
        }

        async with httpx.AsyncClient() as http_client:
            resp      = await http_client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=15.0
            )
            extracted = resp.json()['choices'][0]['message']['content'].strip()

        if "NO_DATA" not in extracted and len(extracted) > 5:
            # Clean pronouns so memories read naturally in future prompts
            clean_memory = (
                extracted
                .replace("User", "You")
                .replace("user", "You")
                .replace("Ethrix", "me")
            )

            # Duplicate guard — don't save the same fact twice
            db_user = await db_module.users_collection.find_one({"email": user_email})
            if db_user and clean_memory in db_user.get("memories", []):
                return

            # 1. Save to MongoDB
            await db_module.users_collection.update_one(
                {"email": user_email},
                {"$push": {"memories": clean_memory}}
            )
            # 2. Save vector to Pinecone for semantic retrieval
            if db_module.index:
                vec = get_embedding(clean_memory)
                if vec:
                    mem_id = f"{user_email}_{hashlib.md5(clean_memory.encode()).hexdigest()}"
                    db_module.index.upsert(
                        vectors=[(mem_id, vec, {"text": clean_memory, "email": user_email})]
                    )
    except Exception as e:
        print(f"[Auto-Memory Error]: {e}")


# ==========================================
# [SECTION 5] REQUEST MODELS
# ==========================================
class ChatRequest(BaseModel):
    message:    str
    session_id: str
    mode:       str          = "chat"
    file_data:  str | None  = None   # base64-encoded for resume_analyzer / math_solver
    file_type:  str | None  = None


# ==========================================
# [SECTION 6] MAIN CHAT ENDPOINT
# The restored 4-mode brain of Ethrix AI.
# ==========================================
@router.post("/api/chat")
async def main_chat(req: ChatRequest, request: Request, background_tasks: BackgroundTasks):
    """
    Central chat dispatcher. Reads `req.mode` from the frontend payload and routes
    to the correct logic:

    MODE 1 — "chat"          → Normal conversational AI with memory + persona
    MODE 2 — "research"      → Web search (DuckDuckGo) → AI synthesised answer
    MODE 3 — "code_debugger" → Specialised coding models via tools_lab
    MODE 4 — "ethrix_agent"  → External HF Space agent integration
    + All tool modes and custom user tools
    """
    try:
        # --- Auth Guard ---
        user = await db_module.get_current_user(request)
        if not user:
            return {"reply": "⚠️ Login required."}

        sid  = req.session_id
        mode = req.mode
        msg  = req.message

        # --- Background: Auto-save memories for normal chat messages only ---
        if mode == "chat":
            background_tasks.add_task(extract_and_save_memory, user['email'], msg)

        # --- Fetch user from DB (ban check, memories, custom instruction) ---
        db_user = await db_module.users_collection.find_one({"email": user['email']})

        # --- Ban Check ---
        if db_user and db_user.get("is_banned"):
            return {"reply": "🚫 You have been banned by the Admin. Access Denied."}

        # -----------------------------------------------------------------------
        # BUILD THE FINAL SYSTEM PROMPT
        # Priority: user's custom instruction > DEFAULT_SYSTEM_INSTRUCTIONS
        # Then inject: user's name + long-term memories
        # -----------------------------------------------------------------------
        user_custom_prompt = (db_user.get("custom_instruction", "") if db_user else "")
        retrieved_memory   = ""

        # 1. Try semantic vector search in Pinecone first
        if db_module.index:
            retrieved_memory = search_vector_db(msg, user['email'])

        # 2. Fallback to last 5 MongoDB memories if Pinecone returned nothing
        if not retrieved_memory and db_user:
            recent_mems = db_user.get("memories", [])[-5:]
            if recent_mems:
                retrieved_memory = "\n".join(recent_mems)

        # Use custom instruction if the user has set one, otherwise default persona
        FINAL_SYSTEM_PROMPT = (
            user_custom_prompt
            if user_custom_prompt and user_custom_prompt.strip()
            else DEFAULT_SYSTEM_INSTRUCTIONS
        )

        # Personalise with user's real name
        user_display_name = (
            (db_user.get("name") if db_user else None)
            or user.get("name", "User")
        )

        if user_display_name in ("User", "") or "guest" in user_display_name.lower():
            name_instruction = (
                "The user's name is currently unknown. In your first reply, very politely and "
                "affectionately ask for their name so you can remember it forever."
            )
        else:
            name_instruction = (
                f"The person you are talking to is {user_display_name}. "
                "Address them affectionately by their name."
            )

        FINAL_SYSTEM_PROMPT += (
            f"\n\n[IMPORTANT CONTEXT]: You are Ethrix. {name_instruction} "
            "DO NOT call the user 'Ethrix' ever. DO NOT save memories about your own name."
        )

        # Inject retrieved memories so Ethrix can personalise the response
        if retrieved_memory:
            FINAL_SYSTEM_PROMPT += (
                f"\n\n[USER LONG-TERM MEMORY]:\n{retrieved_memory}\n"
                "(Use this information to personalise the conversation)"
            )

        # -----------------------------------------------------------------------
        # SESSION / CHAT HISTORY MANAGEMENT
        # -----------------------------------------------------------------------
        chat_doc = await db_module.chats_collection.find_one({"session_id": sid})
        if not chat_doc:
            title_prefix = "Chat" if mode == "chat" else f"Tool: {mode.replace('_', ' ').title()}"
            await db_module.chats_collection.insert_one({
                "session_id": sid,
                "user_email": user['email'],
                "title":      f"{title_prefix} - {msg[:15]}...",
                "messages":   []
            })
            chat_doc = {"messages": []}

        # Save the user's message to the session
        await db_module.chats_collection.update_one(
            {"session_id": sid},
            {"$push": {"messages": {
                "role":      "user",
                "content":   msg,
                "timestamp": datetime.utcnow()
            }}}
        )

        # Build recent context for persona/roleplay tools that need conversation flow
        context_history = ""
        if mode in ("sing_with_me", "movie_talker", "anime_talker"):
            for m in chat_doc.get("messages", [])[-6:]:
                context_history += f"{m['role']}: {m['content']} | "

        # Track usage per tool for the admin analytics panel
        await db_module.tool_usage_collection.update_one(
            {"tool_name": mode}, {"$inc": {"count": 1}}, upsert=True
        )

        # -----------------------------------------------------------------------
        # 🚦 MODE ROUTING — THE CORE 4-MODE + TOOL SWITCH
        # -----------------------------------------------------------------------
        reply = ""

        # ── Specialist Tool Modes ─────────────────────────────────────────────

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

        # ── MODE 3: CODING MODE ───────────────────────────────────────────────
        # Routed to code_debugger_tool which uses OpenRouter coding-specific models.
        elif mode == "code_debugger":
            reply = await tools_lab.code_debugger_tool(msg)

        # ── MODE 2: SEARCH MODE ───────────────────────────────────────────────
        # Fetches top-3 DuckDuckGo results, then synthesises with Groq.
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
                # Graceful fallback: return raw search data if Groq is unavailable
                reply = research_data

        # ── MODE 4: AGENT MODE ────────────────────────────────────────────────
        # Sends the task to the external HF Space agent with full session context.
        elif mode == "ethrix_agent":
            try:
                async with httpx.AsyncClient() as http_client:
                    agent_headers = {
                        "x-api-key":    os.getenv("AGENT_API_KEY", "shantanu_super_secret_key"),
                        "Content-Type": "application/json"
                    }
                    # Send up to last 15 messages as history for the agent to reason over
                    clean_history = [
                        {"role": m["role"], "content": m["content"]}
                        for m in (chat_doc.get("messages", []) + [{"role": "user", "content": msg}])[-15:]
                    ]
                    payload = {
                        "query":        msg,
                        "user_context": FINAL_SYSTEM_PROMPT,
                        "history":      clean_history,
                        "user_email":   user['email']
                    }
                    AGENT_URL = os.getenv(
                        "HF_AGENT_URL",
                        "https://shantanupathak94-ai-agent-for-ethrix-ai.hf.space/run-agent"
                    )
                    resp = await http_client.post(
                        AGENT_URL,
                        headers=agent_headers,
                        json=payload,
                        timeout=40.0
                    )
                    if resp.status_code == 200:
                        reply = resp.json().get("response", "Agent processing complete.")
                    else:
                        reply = f"⚠️ Ethrix Agent connection error! Status: {resp.status_code}"
            except Exception as agent_error:
                reply = f"⚠️ Ethrix Agent is offline or unreachable: {str(agent_error)}"

        # ── Custom User-Created Tools ─────────────────────────────────────────
        # Modes that start with "custom_" are tools the user built themselves
        # via the custom tool creation feature.
        elif mode.startswith("custom_"):
            custom_tool = next(
                (t for t in (db_user.get("custom_tools", []) if db_user else []) if t["id"] == mode),
                None
            )
            if custom_tool:
                tool_prompt = (
                    f"{FINAL_SYSTEM_PROMPT}\n\n"
                    "[STRICT TOOL INSTRUCTION]: Act exactly as the following tool:\n"
                    f"{custom_tool['instruction']}"
                )
                groq_client = get_groq()
                if groq_client:
                    clean_history = [
                        {"role": m["role"], "content": m["content"]}
                        for m in (chat_doc.get("messages", []) + [{"role": "user", "content": msg}])[-15:]
                    ]
                    reply = groq_client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[
                            {"role": "system", "content": tool_prompt},
                            *clean_history
                        ]
                    ).choices[0].message.content
                else:
                    reply = "⚠️ AI API Error. Please try again."
            else:
                reply = "⚠️ This custom tool was deleted or could not be found."

        # ── MODE 1: NORMAL CHAT MODE (default / mode == "chat") ──────────────
        # Full conversational Ethrix experience with persona + memory + history.
        # This is the catch-all — any unrecognised mode also falls here safely.
        else:
            groq_client = get_groq()
            if groq_client:
                # Include up to last 15 messages for coherent multi-turn conversation
                clean_history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in (chat_doc.get("messages", []) + [{"role": "user", "content": msg}])[-15:]
                ]
                reply = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": FINAL_SYSTEM_PROMPT},
                        *clean_history
                    ]
                ).choices[0].message.content
            else:
                reply = "⚠️ AI API Error. Please try again in a moment."

        # -----------------------------------------------------------------------
        # SAVE AI REPLY TO DB & RETURN
        # -----------------------------------------------------------------------
        await db_module.chats_collection.update_one(
            {"session_id": sid},
            {"$push": {"messages": {
                "role":      "assistant",
                "content":   reply,
                "timestamp": datetime.utcnow()
            }}}
        )

        # Update the chat title for tool sessions with no prior history
        if len(chat_doc.get("messages", [])) < 2 and mode != "chat":
            await db_module.chats_collection.update_one(
                {"session_id": sid},
                {"$set": {"title": f"Tool: {mode.replace('_', ' ').title()}"}}
            )

        return {"reply": reply}

    except Exception as e:
        # Log the full stack trace to MongoDB for admin-panel debugging
        full_trace = traceback.format_exc()
        await db_module.error_logs_collection.insert_one({
            "error":     str(e),
            "trace":     full_trace,
            "endpoint":  f"/api/chat ({req.mode})",
            "timestamp": datetime.utcnow()
        })
        return {"reply": "⚠️ Server Error: We ran into a small issue. Please try again!"}


# ==========================================
# [SECTION 7] DYNAMIC TOOLS ENDPOINT
# New feature — kept 100% intact, zero changes.
# Exposes all tools_lab functions via a single
# parameterised route for frontend flexibility.
# ==========================================
@router.post("/api/tool/{tool_name}")
async def handle_tool(tool_name: str, request: Request):
    try:
        data       = await request.json()
        user_input = data.get("input", "")
        result     = ""

        # Match tool_name and call the exact function from tools_lab
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

        # Tools with conversation history context
        elif tool_name == "movie_talker":
            history = data.get("history", "")
            result  = await tools_lab.movie_talker_tool(user_input, history)
        elif tool_name == "anime_talker":
            history = data.get("history", "")
            result  = await tools_lab.anime_talker_tool(user_input, history)

        # Tools that accept file uploads (base64-encoded)
        elif tool_name == "math_solver":
            file_data = data.get("file_data")
            result    = await tools_lab.solve_math_problem(file_data, user_input)
        elif tool_name == "resume_analyzer":
            file_data = data.get("file_data")
            result    = await tools_lab.analyze_resume(file_data, user_input)

        else:
            return JSONResponse(
                {"status": "error", "message": "Tool not found or not connected yet!"},
                status_code=404
            )

        return {"status": "success", "result": result}

    except Exception as e:
        print(f"Tool Error ({tool_name}): {str(e)}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)