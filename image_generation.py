# tools_lab/image_generation.py

import aiohttp
import random
import os
import urllib.parse

# --- PROMPT ENHANCERS ---
# Ye prompts ko chupke se modify karke quality badhayenge
REALISTIC_SUFFIX = ", hyperrealistic, 8k resolution, highly detailed, photorealistic, cinematic lighting, sharp focus, raw photo, shot on dslr"
PAINTING_SUFFIX = ", beautiful digital painting, brushstrokes, artistic style, concept art, highly detailed, trending on artstation"

NEGATIVE_PROMPT = "cartoon, anime, blurry, deformed, disfigured, bad anatomy, ugly, pixelated, low quality, watermark, text, signature"

# --- TIER 1: FREE MODE ENGINE (Pollinations AI Optimized) ---
async def generate_image_free(prompt: str, style_mode: str = "realistic"):
    try:
        # 1. Prompt Engineering based on style
        final_prompt = prompt
        if style_mode == "realistic":
            final_prompt += REALISTIC_SUFFIX
        else:
            final_prompt += PAINTING_SUFFIX
            
        # URL encode the prompt
        encoded_prompt = urllib.parse.quote(final_prompt)
        encoded_negative = urllib.parse.quote(NEGATIVE_PROMPT)
        
        # Pollinations URL construct (using Turbo model for speed & quality)
        # Hum negative prompt bhi pass kar rahe hain taaki quality improve ho
        image_url = f"https://pollinations.ai/p/{encoded_prompt}?negative_prompt={encoded_negative}&model=turbo&width=1024&height=1024&seed={random.randint(0, 999999)}"
        
        # Check if URL actually works
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status == 200:
                    return image_url
                else:
                    return "⚠️ Free tier server busy. Try Pro mode."
                    
    except Exception as e:
        print(f"Free Image Gen Error: {e}")
        return f"⚠️ Generation failed: {str(e)}"

# --- TIER 2: PRO MODE ENGINE (HF Serverless API - The Real Deal) ---
async def generate_image_pro(prompt: str, style_mode: str = "realistic"):
    # Iske liye tumhe .env mein HUGGINGFACE_PRO_TOKEN dalna padega
    # (Apne main HF account se ek WRITE token bana lena)
    hf_token = os.getenv("HUGGINGFACE_PRO_TOKEN")
    if not hf_token or hf_token == "your_hf_token_here":
        return "⚠️ Pro Token missing in backend configuration."

    # PRO MODEL SELECTION:
    # Realistic ke liye SDXL 1.0 Base use karenge (Best for realism on HF API)
    # Painting ke liye bhi ye acha hai, bas prompt badal denge.
    model_id = "stabilityai/stable-diffusion-xl-base-1.0"
    api_url = f"https://api-inference.huggingface.co/models/{model_id}"
    
    headers = {"Authorization": f"Bearer {hf_token}"}
    
    # Prompt enhancement
    final_prompt = prompt
    if style_mode == "realistic":
        final_prompt += REALISTIC_SUFFIX
    else:
        final_prompt += PAINTING_SUFFIX

    payload = {
        "inputs": final_prompt,
        "parameters": {
            "negative_prompt": NEGATIVE_PROMPT,
            "num_inference_steps": 30, # Higher quality steps
            "guidance_scale": 7.5,
            "width": 1024,
            "height": 1024
        }
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    err = await resp.read()
                    print(f"HF Pro API Error: {err}")
                    # Agar model load ho raha hai (503 error)
                    if resp.status == 503:
                         return "⚠️ Pro Model is waking up (loading). Please try again in 30 seconds."
                    return f"⚠️ Pro API Error: {resp.status}"
                
                image_bytes = await resp.read()
                
                # Image ko temporarily save karna padega taaki frontend ko bhej sakein
                # (Production mein isko S3 bucket ya Cloudinary pe dalte hain, abhi local save karte hain)
                filename = f"gen_{random.randint(1000,9999)}.png"
                filepath = os.path.join("static", "generated_images", filename)
                
                # Ensure directory exists
                os.makedirs(os.path.join("static", "generated_images"), exist_ok=True)
                
                with open(filepath, "wb") as f:
                    f.write(image_bytes)
                    
                # Return local path accessible by frontend
                return f"/static/generated_images/{filename}"

    except Exception as e:
         print(f"Pro Image Gen Error: {e}")
         return f"⚠️ Pro generation failed: {str(e)}"