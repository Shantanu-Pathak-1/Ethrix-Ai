import os
import hashlib
from motor.motor_asyncio import AsyncIOMotorClient
from pinecone import Pinecone, ServerlessSpec
from passlib.context import CryptContext
from authlib.integrations.starlette_client import OAuth
import httpx
from fastapi import Request
import certifi
from dotenv import load_dotenv # ❤️ Yeh naya import add karo

load_dotenv() # ❤️ Aur yeh function call kar do taaki saari keys load ho jayein!

# =========================================
# 1. KEYS & CONFIG
# ==========================================
ADMIN_EMAIL = "shantanupathak94@gmail.com"
SECRET_KEY = os.getenv("SECRET_KEY", "super_secret")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
MONGO_URL = os.getenv("MONGO_URL")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
MAIL_USERNAME = os.getenv("MAIL_USERNAME") 
BREVO_API_KEY = os.getenv("BREVO_API_KEY")

MAINTENANCE_MODE = True

# ==========================================
# 2. OAUTH SETUP (GOOGLE LOGIN)
# ==========================================
oauth = OAuth()
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    oauth.register(
        name='google',
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )

# ==========================================
# 3. SECURITY & HELPERS
# ==========================================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
def verify_password(plain, hashed): return pwd_context.verify(hashlib.sha256(plain.encode()).hexdigest(), hashed) if plain and hashed else False
def get_password_hash(password): return pwd_context.hash(hashlib.sha256(password.encode()).hexdigest())
async def get_current_user(request: Request): return request.session.get('user')

def send_email(to, subject, body):
    api = BREVO_API_KEY
    if not api: return False
    try:
        httpx.post("https://api.brevo.com/v3/smtp/email", headers={"api-key": api, "content-type": "application/json"}, json={"sender": {"email": MAIL_USERNAME, "name": "Ethrix"}, "to": [{"email": to}], "subject": subject, "htmlContent": body})
        return True
    except: return False

# ==========================================
# 4. DATABASE SETUP
# ==========================================
client = AsyncIOMotorClient(MONGO_URL, tlsCAFile=certifi.where()) 
db = client.shanvika_db
users_collection = db.users
chats_collection = db.chats
otp_collection = db.otps 
feedback_collection = db.feedback 
diary_collection = db.diary
gallery_collection = db.gallery 
tool_usage_collection = db.tool_usage
error_logs_collection = db.error_logs
settings_collection = db.settings

# ==========================================
# 5. PINECONE SETUP
# ==========================================
pc = None
index = None
try:
    if PINECONE_API_KEY:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        index_name = "ethrix-memory"
        if index_name not in pc.list_indexes().names():
            try: pc.create_index(name=index_name, dimension=768, metric='cosine', spec=ServerlessSpec(cloud='aws', region='us-east-1'))
            except: pass
        index = pc.Index(index_name)
except: pass