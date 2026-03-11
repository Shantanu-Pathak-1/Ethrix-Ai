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
import docx
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
        # 🛡️ Agar Groq (Main Chat) fail hota hai, toh OpenRouter ke heavy models handle karenge!
        print(f"Groq API Busy! Falling back to OpenRouter: {str(e)}")
        return get_openrouter_response(prompt, task_type="heavy")

# 🚀 SMART OPENROUTER HELPER (WITH TASK-BASED MODELS)
def get_openrouter_response(prompt, task_type="fast"):
    keys = os.getenv("OPENROUTER_API_KEY_POOL", "").split(",")
    possible_keys = [k.strip() for k in keys if k.strip()]
    key = random.choice(possible_keys) if possible_keys else os.getenv("OPENROUTER_API_KEY")
    
    if not key:
        return "⚠️ API Key missing."
        
    # 🧠 SMART MODEL LISTS (4-5 Models per category)
    if task_type == "coding":
        models = [
            "qwen/qwen-2.5-coder-32b-instruct:free", 
            "meta-llama/llama-3.1-8b-instruct:free",
            "google/gemma-2-9b-it:free",
            "mistralai/mistral-7b-instruct:free",
            "deepseek/deepseek-chat:free"
        ]
    elif task_type == "vision":
        models = ["nvidia/nemotron-mini-4b-instruct"] # Vision ke liye specific
    elif task_type == "heavy":
        # Research aur Main Chat Fallback ke liye sabse smart models
        models = [
            "meta-llama/llama-3.3-70b-instruct:free",
            "nvidia/llama-3.1-nemotron-70b-instruct:free",
            "qwen/qwen-2.5-7b-instruct:free",
            "google/gemma-2-9b-it:free",
            "mistralai/mistral-7b-instruct:free"
        ]
    else:
        # Fast / General Tools ke liye superfast models
        models = [
            "zhipu/glm-4-flash", 
            "stepfun/step-1-flash", 
            "meta-llama/llama-3-8b-instruct:free",
            "google/gemma-2-9b-it:free",
            "qwen/qwen-2-7b-instruct:free"
        ]
        
    headers = {
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": "https://ethrix.ai", 
        "X-Title": "Ethrix AI", 
        "Content-Type": "application/json"
    }
    
    # 🚀 FALLBACK LOOP: Ek fail hua toh dusra chalega!
    for model in models:
        try:
            data = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}]
            }
            
            response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=15)
            response_json = response.json()
            
            if 'choices' in response_json and len(response_json['choices']) > 0:
                return response_json['choices'][0]['message']['content']
            else:
                # Agar choice nahi aayi (server busy), toh chup-chap continue karke next model try karo
                print(f"Model {model} is busy. Trying next model...")
                continue 
                
        except Exception as e:
            print(f"Network error with {model}. Trying next...")
            continue
            
    # Agar 5 ke 5 models fail ho jayein (jo ki almost impossible hai)
    return "⚠️ All AI Servers are currently overloaded. Please give me a few seconds and try again!"

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
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
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
    if not file_data: return "⚠️ Please upload a PDF or DOCX resume first."
    try:
        header, encoded = file_data.split(",", 1)
        file_bytes = base64.b64decode(encoded)
        text = ""
        
        if "pdf" in header.lower():
            reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            for page in reader.pages: text += page.extract_text()
            
        elif "officedocument.wordprocessingml.document" in header.lower() or "msword" in header.lower():
            doc = docx.Document(io.BytesIO(file_bytes))
            text = "\n".join([para.text for para in doc.paragraphs])
            
        else:
            return "⚠️ Unsupported format! Please upload a .pdf or .docx file."

        prompt = f"Act as an expert HR Manager. Analyze this resume:\n{text[:3000]}...\nProvide Score, Strengths, Weaknesses, and ATS tips."
        
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        res = model.generate_content(prompt)
        return res.text
    except Exception as e: 
        return f"⚠️ Error parsing resume: {str(e)}"

async def review_github(url):
    username = url.rstrip("/").split("/")[-1]
    if not username: return "⚠️ Invalid GitHub URL."
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        user_res = requests.get(f"[https://api.github.com/users/](https://api.github.com/users/){username}", headers=headers)
        
        if user_res.status_code == 404: 
            return "⚠️ GitHub User not found."
            
        user_data = user_res.json()
        repos_data = requests.get(f"[https://api.github.com/users/](https://api.github.com/users/){username}/repos?sort=updated", headers=headers).json()
        
        top_repos = [r['name'] for r in repos_data[:5]] if isinstance(repos_data, list) else []
        prompt = f"Review GitHub Profile: {username}, Bio: {user_data.get('bio')}, Repos: {user_data.get('public_repos')}, Recent: {', '.join(top_repos)}. Give rating and advice."
        return get_llm_response(prompt)
    except Exception as e: 
        return f"⚠️ API Error: {str(e)}"

async def summarize_youtube(url):
    try:
        if "v=" in url:
            video_id = url.split("v=")[1].split("&")[0]
        elif "youtu.be/" in url:
            video_id = url.split("youtu.be/")[1].split("?")[0]
        else:
            return "⚠️ Invalid YouTube URL. Please provide a valid link."
            
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        full_text = " ".join([i['text'] for i in transcript_list])
        prompt = f"Summarize this YouTube video transcript into 5 key bullet points:\n{full_text[:4000]}..."
        return get_openrouter_response(prompt, "fast")
    except Exception as e: 
        return f"⚠️ Could not fetch transcript. The video might not have captions enabled. (Error: {str(e)})"

async def generate_interview_questions(role):
    return get_llm_response(f"Generate 10 hard interview questions for {role}.")

async def handle_mock_interview(msg):
    prompt = f"Act as a professional Interviewer. The user says: '{msg}'. DO NOT list all questions at once. Ask exactly ONE relevant interview question based on the conversation flow, then wait for the user to answer. Keep it natural and conversational."
    return get_llm_response(prompt)

async def solve_math_problem(file_data, query):
    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
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
    prompt = f"You are a smart password generator. The user wants a password matching this criteria: '{req}'. Create a highly secure, strong password (at least 12 chars) that incorporates their request (e.g., if they asked for an animal, use an animal name creatively with symbols and numbers). Return ONLY the password, nothing else."
    result = get_llm_response(prompt)
    return f"🔐 `{result.strip()}`"

async def generate_qr_code(text, file_data=None):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    
    if file_data:
        try:
            header, encoded = file_data.split(",", 1)
            logo_bytes = base64.b64decode(encoded)
            logo = PIL.Image.open(io.BytesIO(logo_bytes))
            
            basewidth = int(img.size[0] / 4)
            wpercent = (basewidth/float(logo.size[0]))
            hsize = int((float(logo.size[1])*float(wpercent)))
            logo = logo.resize((basewidth, hsize), PIL.Image.LANCZOS)
            
            pos = ((img.size[0] - logo.size[0]) // 2, (img.size[1] - logo.size[1]) // 2)
            img.paste(logo, pos)
        except Exception as e:
            pass 

    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f'<div class="flex justify-center p-4 bg-white rounded-xl w-fit mx-auto"><img src="data:image/png;base64,{img_str}" alt="QR Code" width="200"></div>'

async def fix_grammar_tool(text):
    return get_openrouter_response(f"Fix grammar and make professional:\n{text}", "fast") 

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
                        return f"🎶 {lyrics[i+1]} 🎶\n*(Song: {song.title})*"
        except: pass
    
    prompt = f"We are playing a singing game. I sang: '{user_line}'. Identify the song I am singing. Return EXACTLY the very next line of that song, and nothing else. Add a 🎶 emoji."
    return get_llm_response(prompt)

async def currency_tool(query):
    try:
        prompt = f"You are a currency converter tool. A user asked: '{query}'. Provide the most recent approximate exchange rate and the final calculated amount. Keep it short and clear."
        res = get_openrouter_response(prompt, "fast")
        return f"💱 **Conversion Details:**\n{res}"
    except: 
        return "⚠️ Currency service unavailable."

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
    Act as an enthusiastic movie and web series geek. You love "Lucifer".
    CRITICAL INSTRUCTION: The user you are talking to is a BOY. You MUST use male pronouns and grammar in Hindi/Hinglish (e.g., say 'tum dekhte ho', NEVER say 'tum dekhti ho'). 
    DO NOT use the user's name anywhere in your response. Just talk like a best friend.
    Context: {context_history}
    User: {message}
    """
    return get_llm_response(prompt)

async def anime_talker_tool(message, context_history):
    prompt = f"""
    Act as a hardcore anime otaku. You love Ayanokoji from "Classroom of the Elite" and "Solo Leveling".
    CRITICAL INSTRUCTION: The user you are talking to is a BOY. You MUST use male pronouns and grammar in Hindi/Hinglish (e.g., say 'tum samajhte ho', NEVER say 'tum samajhti ho'). 
    DO NOT use the user's name anywhere in your response. 
    Context: {context_history}
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