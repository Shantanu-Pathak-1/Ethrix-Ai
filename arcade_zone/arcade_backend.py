from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os

# Independent Arcade App
arcade_app = FastAPI(title="Shanvika Arcade")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@arcade_app.get("/tic-tac-toe", response_class=HTMLResponse)
async def play_tic_tac_toe(request: Request):
    return templates.TemplateResponse("tic_tac_toe.html", {"request": request})

@arcade_app.get("/code-le", response_class=HTMLResponse)
async def play_code_le(request: Request):
    return templates.TemplateResponse("code_le.html", {"request": request})

@arcade_app.get("/anime-match", response_class=HTMLResponse)
async def play_anime_match(request: Request):
    return templates.TemplateResponse("anime_match.html", {"request": request})

@arcade_app.get("/flappy-bug", response_class=HTMLResponse)
async def play_flappy_bug(request: Request):
    return templates.TemplateResponse("flappy_bug.html", {"request": request})

@arcade_app.get("/ludo", response_class=HTMLResponse)
async def play_ludo(request: Request):
    return templates.TemplateResponse("ludo.html", {"request": request})