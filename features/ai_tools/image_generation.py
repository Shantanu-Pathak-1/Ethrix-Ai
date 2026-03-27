# ==================================================================================
#  FILE: image_generation.py
#  DESCRIPTION: 100% Free Image Generation — Pollinations.ai + Auto Prompt AI
#
#  FLOW:
#  User types anything (even "cat") → Groq AI enhances it → Best model generates
#
#  MODELS (Pollinations.ai — completely free, no API key):
#  Fast  + Realistic → turbo         (quick, solid quality)
#  Fast  + Painting  → dreamshaper   (quick, artistic)
#  Pro   + Realistic → flux-realism  (best realism available free)
#  Pro   + Painting  → flux          (best artistic quality available free)
# ==================================================================================

import aiohttp
import random
import urllib.parse
import os
from groq import Groq

# ==========================================
# NEGATIVE PROMPT (applied to all modes)
# ==========================================
NEGATIVE_PROMPT = (
    "blurry, deformed, disfigured, bad anatomy, ugly, pixelated, "
    "low quality, watermark, text, signature, nsfw, extra limbs, "
    "poorly drawn face, out of frame, cut off, draft"
)

# ==========================================
# AUTO PROMPT ENHANCER  (Groq — already in project, no extra key needed)
# ==========================================
def _enhance_prompt(user_prompt: str, style: str, tier: str) -> str:
    """
    User 'cat' likhta hai → Groq detailed cinematic prompt banata hai.
    Agar Groq unavailable ho toh original prompt + suffix return karta hai.
    """
    try:
        keys = os.getenv("GROQ_API_KEY_POOL", "").split(",")
        key  = next((k.strip() for k in keys if k.strip()), None) or os.getenv("GROQ_API_KEY", "")
        if not key:
            raise ValueError("No Groq key available")

        client = Groq(api_key=key)

        style_instruction = (
            "hyperrealistic photography style, DSLR shot, cinematic lighting, sharp focus, 8K resolution"
            if style == "realistic"
            else "stunning digital painting, vivid colors, detailed brushstrokes, concept art, ArtStation trending"
        )

        quality_instruction = (
            "ultra high detail, professional studio quality, award-winning"
            if tier == "pro"
            else "high quality, clean, well-composed"
        )

        enhance_msg = (
            f"You are an expert AI image prompt engineer specializing in Stable Diffusion and Flux models.\n"
            f"Convert this simple user idea into a single, rich, detailed image generation prompt.\n\n"
            f"User idea: \"{user_prompt}\"\n"
            f"Style: {style_instruction}\n"
            f"Quality level: {quality_instruction}\n\n"
            f"Rules:\n"
            f"- Return ONLY the final prompt text, nothing else\n"
            f"- No intro, no explanation, no quotes\n"
            f"- Include subject, environment, lighting, mood, camera details\n"
            f"- Maximum 120 words\n"
            f"- Write in English only"
        )

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": enhance_msg}],
            max_tokens=200,
            temperature=0.7
        )
        enhanced = response.choices[0].message.content.strip().strip('"').strip("'")
        return enhanced if enhanced else user_prompt

    except Exception as e:
        print(f"[Prompt Enhance Fallback]: {e}")
        if style == "realistic":
            return user_prompt + ", hyperrealistic, 8k, cinematic lighting, sharp focus, photorealistic, masterpiece"
        else:
            return user_prompt + ", digital painting, detailed brushstrokes, concept art, trending on ArtStation, masterpiece"


# ==========================================
# URL BUILDER
# ==========================================
def _build_url(enhanced_prompt: str, style: str, tier: str) -> str:
    if tier == "pro":
        model         = "flux-realism" if style == "realistic" else "flux"
        width, height = 1024, 1024
    else:
        model         = "turbo" if style == "realistic" else "dreamshaper"
        width, height = 768, 768

    encoded_prompt   = urllib.parse.quote(enhanced_prompt)
    encoded_negative = urllib.parse.quote(NEGATIVE_PROMPT)
    seed             = random.randint(0, 999999)

    return (
        f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        f"?model={model}"
        f"&negative_prompt={encoded_negative}"
        f"&width={width}&height={height}"
        f"&seed={seed}"
        f"&nologo=true"
        f"&enhance=true"
    )


# ==========================================
# TIER 1: FAST MODE
# ==========================================
async def generate_image_free(prompt: str, style_mode: str = "realistic") -> str:
    enhanced = _enhance_prompt(prompt, style_mode, tier="fast")
    print(f"[Fast] '{prompt}' → '{enhanced[:80]}...'")
    url = _build_url(enhanced, style_mode, tier="fast")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    return url
    except Exception as e:
        print(f"[Fast Image Gen Error]: {e}")
    return url  # return URL anyway — Pollinations usually serves it


# ==========================================
# TIER 2: PRO MODE
# ==========================================
async def generate_image_pro(prompt: str, style_mode: str = "realistic") -> str:
    enhanced = _enhance_prompt(prompt, style_mode, tier="pro")
    print(f"[Pro] '{prompt}' → '{enhanced[:80]}...'")
    url = _build_url(enhanced, style_mode, tier="pro")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status == 200:
                    return url
    except Exception as e:
        print(f"[Pro Image Gen Error]: {e}")
    return url