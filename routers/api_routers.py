from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import tools_lab
import core.database as db_module

router = APIRouter()

# ==========================================
# 💬 1. MAIN CHAT ENDPOINT (Shanvika's Brain)
# ==========================================
@router.post("/api/chat")
async def main_chat(request: Request):
    try:
        data = await request.json()
        user_message = data.get("message", "")
        
        # Tools Lab se Agent Task (Chat) ko call kar rahe hain
        bot_reply = await tools_lab.run_agent_task(user_message)
        return {"status": "success", "reply": bot_reply}
        
    except Exception as e:
        print(f"Chat Error: {str(e)}")
        return JSONResponse({"status": "error", "message": "Server error. Please try again!"}, status_code=500)

# ==========================================
# 🛠️ 2. DYNAMIC TOOLS ENDPOINT (Saare Tools Yahan Connect Honge)
# ==========================================
@router.post("/api/tool/{tool_name}")
async def handle_tool(tool_name: str, request: Request):
    try:
        data = await request.json()
        user_input = data.get("input", "")
        result = ""
        
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
            
        # Tools with History context
        elif tool_name == "movie_talker":
            history = data.get("history", "")
            result = await tools_lab.movie_talker_tool(user_input, history)
        elif tool_name == "anime_talker":
            history = data.get("history", "")
            result = await tools_lab.anime_talker_tool(user_input, history)
            
        # Tools with Files/Images
        elif tool_name == "math_solver":
            file_data = data.get("file_data")
            result = await tools_lab.solve_math_problem(file_data, user_input)
        elif tool_name == "resume_analyzer":
            file_data = data.get("file_data")
            result = await tools_lab.analyze_resume(file_data, user_input)
            
        else:
            return JSONResponse({"status": "error", "message": "Tool not found or not connected yet!"}, status_code=404)
            
        return {"status": "success", "result": result}
        
    except Exception as e:
        print(f"Tool Error ({tool_name}): {str(e)}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)