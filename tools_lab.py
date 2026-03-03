# ==================================================================================
#  FILE: tools_lab.py
#  DESCRIPTION: Backend Logic + NEW AI AGENT BRAIN
# ==================================================================================

import os
import random
import string
import requests
import qrcode
import io
import base64
import PyPDF2
from youtube_transcript_api import YouTubeTranscriptApi
from duckduckgo_search import DDGS
import google.generativeai as genai
from groq import Groq
import PIL.Image
import lyricsgenius
from bs4 import BeautifulSoup 
import sys
from io import StringIO
import re

# Load Keys
HF_TOKEN = os.getenv("HF_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GENIUS_API_KEY = os.getenv("GENIUS_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def get_llm_response(prompt, model="llama-3.3-70b-versatile"):
    try:
        client = Groq(api_key=GROQ_API_KEY)
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=model,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"⚠️ LLM Error: {str(e)}"

# 🚀 Naya OpenRouter Helper Function
# 🚀 SMART OPENROUTER HELPER (WITH TASK-BASED MODELS)
def get_openrouter_response(prompt, task_type="fast"):
    try:
        keys = os.getenv("OPENROUTER_API_KEY_POOL", "").split(",")
        possible_keys = [k.strip() for k in keys if k.strip()]
        key = random.choice(possible_keys) if possible_keys else os.getenv("OPENROUTER_API_KEY")
        
        if not key:
            return "⚠️ API Key missing."
            
        # 🧠 Smart Model Selection Logic
        if task_type == "coding":
            # Best for logic and debugging
            model = random.choice(["deepseek/deepseek-coder", "deepseek/deepseek-chat:free"])
        elif task_type == "vision":
            # For image/PDF tasks if Gemini fails
            model = "nvidia/nemotron-mini-4b-instruct" # Using Nemotron family for vision fallback
        elif task_type == "heavy":
            # Deep reasoning, writing, emails, resumes
            model = random.choice(["meta-llama/llama-3.1-8b-instruct:free", "qwen/qwen-2.5-7b-instruct:free"])
        else:
            # Fast/Lightweight tasks: Grammar, Summaries, Memory
            model = random.choice(["zhipu/glm-4-flash", "stepfun/step-1-flash", "meta-llama/llama-3-8b-instruct:free"])
            
        headers = {
            "Authorization": f"Bearer {key}",
            "HTTP-Referer": "https://shanvika.ai", 
            "X-Title": "Shanvika AI", 
            "Content-Type": "application/json"
        }
        
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
        response_json = response.json()
        return response_json['choices'][0]['message']['content']
    except Exception as e:
        return f"⚠️ OpenRouter Error: {str(e)}"

# ==================================================================================
# [CATEGORY] NEW: AI AGENT TOOLS (Web Surfer, Python, File)
# ==================================================================================

def scrape_website(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        for script in soup(["script", "style", "nav", "footer"]):
            script.decompose() 
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        return text[:6000] 
    except Exception as e:
        return f"Error reading website: {str(e)}"

def execute_python_code(code):
    old_stdout = sys.stdout
    redirected_output = sys.stdout = StringIO()
    try:
        exec(code, {'__builtins__': __builtins__, 'math': __import__('math'), 'random': __import__('random')})
        sys.stdout = old_stdout
        return redirected_output.getvalue()
    except Exception as e:
        sys.stdout = old_stdout
        return f"Python Error: {str(e)}"

def create_file_tool(filename, content):
    try:
        if ".." in filename or "/" in filename: filename = os.path.basename(filename) 
        path = f"static/user_files/{filename}"
        if not os.path.exists("static/user_files"): os.makedirs("static/user_files")
        with open(path, "w", encoding='utf-8') as f:
            f.write(content)
        return f"✅ File Created: {filename} (Saved in static/user_files)"
    except Exception as e:
        return f"Error creating file: {str(e)}"

# ==================================================================================
# [CATEGORY] NEW: THE AGENT BRAIN (ReAct Loop)
# ==================================================================================
async def run_agent_task(query):
    max_steps = 5 
    history = f"Task: {query}\n"
    
    for step in range(max_steps):
        prompt = f"""
        You are an Autonomous AI Agent.
        Goal: {query}
        
        Available Tools:
        1. SEARCH: <query> (Use to find info on Google/DuckDuckGo)
        2. SCRAPE: <url> (Use to read content of a link found in search)
        3. PYTHON: <code> (Use for math, logic, or data processing. Print the result.)
        4. CREATE_FILE: <filename>|<content> (Use to save code/text to a file)
        5. ANSWER: <final_response> (Use when you have the result)

        History so far:
        {history}

        INSTRUCTIONS:
        - Decide the NEXT STEP based on History.
        - Return ONLY the command (e.g., SEARCH: python tutorials).
        - Do not talk, just command.
        """
        
        command = get_llm_response(prompt).strip()
        history += f"\nStep {step+1}: AI Thought: {command}\n"
        print(f"🤖 Agent Step {step+1}: {command}")

        result = ""
        
        if command.startswith("SEARCH:"):
            q = command.replace("SEARCH:", "").strip()
            res = DDGS().text(q, max_results=3)
            result = str(res)
            
        elif command.startswith("SCRAPE:"):
            url = command.replace("SCRAPE:", "").strip()
            result = scrape_website(url)
            
        elif command.startswith("PYTHON:"):
            code = command.replace("PYTHON:", "").strip()
            if code.startswith("```"): code = code.replace("```python", "").replace("```", "")
            result = execute_python_code(code)
            
        elif command.startswith("CREATE_FILE:"):
            parts = command.replace("CREATE_FILE:", "").strip().split("|", 1)
            if len(parts) == 2:
                result = create_file_tool(parts[0], parts[1])
            else:
                result = "Error: Use format CREATE_FILE: filename|content"
                
        elif command.startswith("ANSWER:"):
            return command.replace("ANSWER:", "").strip() + f"\n\n_(Process: {step} steps)_"
        
        else:
            result = "Invalid Command. Please use SEARCH, SCRAPE, PYTHON, CREATE_FILE, or ANSWER."

        history += f"Observation: {result[:1000]}...\n" 

    return "⚠️ Agent timed out (Too many steps). Here is what I found:\n" + history
    

# ==================================================================================
# [EXISTING TOOLS BELOW]
# ==================================================================================
async def generate_image_hf(prompt):
    enhanced_prompt = prompt
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        enhancement_request = f"Convert this simple user idea into a highly detailed, professional AI image generation prompt (photorealistic, 8k, lighting details). User idea: '{prompt}'. Return ONLY the prompt text, no intro."
        res = model.generate_content(enhancement_request)
        if res.text:
            enhanced_prompt = res.text
    except:
        pass 

    API_URL = "[https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-dev](https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-dev)"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    
    try:
        response = requests.post(API_URL, headers=headers, json={"inputs": enhanced_prompt}, timeout=25)
        
        if response.status_code == 200:
            image_bytes = response.content
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            return f"""
            <div class="glass p-2 rounded-xl">
                <p class="text-xs text-gray-400 mb-2">✨ Prompt: {enhanced_prompt[:100]}...</p>
                <img src="data:image/jpeg;base64,{base64_image}" alt="Generated Image" class="rounded-lg w-full">
            </div>
            """
        else:
            raise Exception("HF Busy")

    except Exception as e:
        try:
            safe_prompt = enhanced_prompt.replace(" ", "%20")
            pollinations_url = f"[https://image.pollinations.ai/prompt/](https://image.pollinations.ai/prompt/){safe_prompt}"
            return f"""
            <div class="glass p-2 rounded-xl">
                <p class="text-xs text-yellow-400 mb-2">⚠️ Server Busy. Switched to Backup AI.</p>
                <img src="{pollinations_url}" alt="Generated Image" class="rounded-lg w-full">
            </div>
            """
        except:
            return "⚠️ All Image Servers are currently down. Please try again later."

async def analyze_resume(file_data, user_msg):
    if not file_data: return "⚠️ Please upload a PDF resume first."
    try:
        header, encoded = file_data.split(",", 1)
        pdf_bytes = base64.b64decode(encoded)
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages: text += page.extract_text()
        prompt = f"Act as an expert HR Manager. Analyze this resume:\n{text[:3000]}...\nProvide Score, Strengths, Weaknesses, and ATS tips."
        
        # 🚀 Shifting to Gemini for large context
        model = genai.GenerativeModel('gemini-1.5-flash')
        res = model.generate_content(prompt)
        return res.text
    except Exception as e: return f"⚠️ Error: {str(e)}"

async def review_github(url):
    username = url.split("/")[-1]
    if not username: return "⚠️ Invalid GitHub URL."
    try:
        user_data = requests.get(f"[https://api.github.com/users/](https://api.github.com/users/){username}").json()
        repos_data = requests.get(f"[https://api.github.com/users/](https://api.github.com/users/){username}/repos?sort=updated").json()
        
        if "message" in user_data: return "⚠️ User not found."
        top_repos = [r['name'] for r in repos_data[:5]]
        prompt = f"Review GitHub Profile: {username}, Bio: {user_data.get('bio')}, Repos: {user_data.get('public_repos')}, Recent: {', '.join(top_repos)}. Give rating and advice."
        return get_llm_response(prompt) # Complex task, keeping Groq
    except Exception as e: 
        return f"⚠️ Error: {str(e)}"

async def summarize_youtube(url):
    try:
        video_id = url.split("v=")[1].split("&")[0]
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        full_text = " ".join([i['text'] for i in transcript_list])
        prompt = f"Summarize this YouTube video transcript into 5 key bullet points:\n{full_text[:4000]}..."
        return get_openrouter_response(prompt, "fast")
    except: return "⚠️ Could not fetch transcript."

async def generate_interview_questions(role):
    return get_llm_response(f"Generate 10 hard interview questions for {role}.")

async def handle_mock_interview(msg):
    return get_llm_response(f"You are an interviewer. User said: '{msg}'. Reply professionally.")

async def solve_math_problem(file_data, query):
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        if file_data:
            header, encoded = file_data.split(",", 1)
            image = PIL.Image.open(io.BytesIO(base64.b64decode(encoded)))
            response = model.generate_content(["Solve this math problem:", image])
        else:
            response = model.generate_content(f"Solve this math problem: {query}")
        return response.text
    except Exception as e: return f"⚠️ Math Error: {str(e)}"

async def smart_todo_maker(raw_text):
    return get_openrouter_response(f"Convert to To-Do List with priorities:\n{raw_text}", "heavy")

async def generate_password_tool(req):
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    return f"🔐 `{ ''.join(random.choice(chars) for i in range(12)) }`"

async def generate_qr_code(text):
    qr = qrcode.make(text)
    buffered = io.BytesIO()
    qr.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f'<div class="flex justify-center p-4 bg-white rounded-xl w-fit mx-auto"><img src="data:image/png;base64,{img_str}" alt="QR Code" width="200"></div>'

async def fix_grammar_tool(text):
    return get_openrouter_response(f"Fix grammar and make professional:\n{text}", "fast") # 🚀 Shifted to OpenRouter

async def generate_prompt_only(idea):
    return get_llm_response(f"Write a professional AI image prompt for: '{idea}'")

async def build_pro_resume(details):
    return get_llm_response(f"Create a resume structure for: {details}")

async def sing_with_me_tool(user_line, history):
    if GENIUS_API_KEY:
        try:
            genius = lyricsgenius.Genius(GENIUS_API_KEY)
            song = genius.search_song(user_line)
            if song:
                lyrics = song.lyrics.split('\n')
                for i, line in enumerate(lyrics):
                    if user_line.lower() in line.lower() and i+1 < len(lyrics):
                        return f"🎶 {lyrics[i+1]} 🎶\n(Song: {song.title})"
        except: pass
    return get_llm_response(f"We are singing. User sang: '{user_line}'. Sing the next line nicely.")

async def currency_tool(query):
    try:
        res = DDGS().text(f"convert {query}", max_results=1)
        return f"💱 **Conversion:**\n{res[0]['body']}" if res else "⚠️ Error."
    except: return "⚠️ Service unavailable."

async def cold_email_tool(details):
    prompt = f"""
    Write a highly professional, standout cold email based on these details: {details}. 
    The goal is to get a response from a hiring manager or recruiter for a high-paying remote tech job (80+ LPA target) or a foreign opportunity. 
    Keep it concise, compelling, and action-oriented. Do not include placeholder brackets like [Your Name] if the user has provided the info.
    """
    return get_llm_response(prompt)

async def fitness_coach_tool(query):
    prompt = f"""
    Act as an expert fitness coach specializing in home workouts, calisthenics, and boxing.
    The user says: "{query}"
    Provide a structured, actionable workout routine or diet advice. Use motivating language, bold headings, and bullet points to make it easy to read.
    """
    return get_llm_response(prompt)

async def feynman_explainer_tool(concept):
    prompt = f"""
    Explain the following concept using the Feynman Technique: "{concept}"
    Explain it so simply that a 10-year-old could understand it. Use relatable real-life analogies. 
    If it's an Artificial Intelligence, Machine Learning, or B.Tech Math concept, make it engaging and strip away all the confusing jargon.
    """
    return get_llm_response(prompt)

async def code_debugger_tool(code_input):
    prompt = f"""
    Act as a Senior Software Architect. Analyze the following code or error message:
    {code_input}
    1. Identify the bug or issue.
    2. Explain briefly why it happened.
    3. Provide the fully corrected and optimized code using markdown code blocks.
    """
    return get_openrouter_response(prompt, "coding")

async def movie_talker_tool(message, context_history):
    prompt = f"""
    Act as an enthusiastic movie and web series geek. You absolutely love the series "Lucifer" and its devilish charm, but you are highly knowledgeable about all movies.
    Respond to the user's message naturally, like a best friend gossiping, explaining a plot, or discussing theories.
    
    Context of conversation: {context_history}
    User: {message}
    """
    return get_llm_response(prompt)

async def anime_talker_tool(message, context_history):
    prompt = f"""
    Act as a hardcore anime otaku. You are a huge fan of Kiyotaka Ayanokoji from "Classroom of the Elite" (you love his mastermind strategies) and the epic action of "Solo Leveling".
    Respond to the user's message about anime, explain lore, or discuss character theories like a fellow anime lover.
    
    Context of conversation: {context_history}
    User: {message}
    """
    return get_llm_response(prompt)

async def generate_flashcards_tool(topic):
    prompt = f"""
    You are an expert study assistant. Generate exactly 6 highly effective flashcards for the topic: "{topic}".
    The questions should be conceptual and answers should be clear and concise.
    
    Return the output STRICTLY in a valid JSON array format like this:
    [
        {{"question": "What is Python?", "answer": "A high-level programming language."}},
        {{"question": "...", "answer": "..."}}
    ]
    Do not add any other text, explanation, or markdown formatting outside this JSON array.
    """
    try:
        response = get_llm_response(prompt)
        if response.startswith("```"):
            response = response.replace("```json", "").replace("```", "").strip()
        return response
    except Exception as e:
        return f'[{{"question": "Error", "answer": "{str(e)}"}}]'