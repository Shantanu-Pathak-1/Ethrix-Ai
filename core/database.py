# ==================================================================================
#  FILE: core/database.py
#  DESCRIPTION: Dual-Database Setup — shanvika_db (old) + ethrix_db (new)
#
#  STRATEGY:
#  - READS   → Merge results from BOTH databases transparently
#  - WRITES  → Only to ethrix_db (new data always goes here)
#
#  How it works:
#  All collection variables (users_collection, chats_collection, etc.) are
#  DualCollection wrapper objects. Every router does db_module.users_collection
#  as normal — it has no idea two DBs exist underneath. The wrapper handles
#  merging automatically.
#
#  find_one()       → ethrix_db first; if not found, fallback to shanvika_db
#  find()           → fetches from both, merges, sort/limit applied on combined
#  count_documents()→ sum of both DBs (admin panel shows correct total counts)
#  update_one()     → ethrix_db only (new writes)
#  insert_one()     → ethrix_db only
#  delete_many()    → ethrix_db only (old data in shanvika_db stays untouched)
# ==================================================================================

import os
import hashlib
import httpx
import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from pinecone import Pinecone, ServerlessSpec
from passlib.context import CryptContext
from authlib.integrations.starlette_client import OAuth
from fastapi import Request

# ==========================================
# 1. KEYS & CONFIG
# ==========================================
ADMIN_EMAIL         = "shantanupathak94@gmail.com"
SECRET_KEY          = os.getenv("SECRET_KEY") or "ethrix_secret_key_default_fallback_2026"
GOOGLE_CLIENT_ID    = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET= os.getenv("GOOGLE_CLIENT_SECRET")
MONGO_URL           = os.getenv("MONGO_URL") or os.getenv("MONGODB_URI") or "mongodb+srv://shanpathak06_db_user:Shan1234@code-editor.h6ffeug.mongodb.net/?appName=code-editor"
PINECONE_API_KEY    = os.getenv("PINECONE_API_KEY")
MAIL_USERNAME       = os.getenv("MAIL_USERNAME")
BREVO_API_KEY       = os.getenv("BREVO_API_KEY")

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

def verify_password(plain, hashed):
    return pwd_context.verify(hashlib.sha256(plain.encode()).hexdigest(), hashed) if plain and hashed else False

def get_password_hash(password):
    return pwd_context.hash(hashlib.sha256(password.encode()).hexdigest())

async def get_current_user(request: Request):
    return request.session.get('user')

async def send_email(to, subject, body):
    """
    Async email sender — server block nahi karega.
    Brevo (Sendinblue) SMTP API use karta hai.
    """
    api = BREVO_API_KEY
    if not api: return False
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            await client.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={"api-key": api, "content-type": "application/json"},
                json={"sender": {"email": MAIL_USERNAME, "name": "Ethrix"}, "to": [{"email": to}], "subject": subject, "htmlContent": body}
            )
        return True
    except Exception as e:
        print(f"[Email Error]: {e}")
        return False

# ==========================================
# 4. RAW DATABASE CONNECTIONS (LOOP-AWARE)
# Both connections share the same MONGO_URL.
# They just point to different databases inside
# the same MongoDB Atlas cluster.
# ==========================================
_client_instances = {}

def get_mongo_client():
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    client = _client_instances.get(loop)
    if client is None or (loop and loop.is_closed()):
        client = AsyncIOMotorClient(
            MONGO_URL,
            tlsCAFile=certifi.where(),
            connect=False,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            socketTimeoutMS=5000
        )
        if loop and not loop.is_closed():
            _client_instances[loop] = client
    return client

def get_old_db():
    return get_mongo_client().shanvika_db

def get_new_db():
    return get_mongo_client().ethrix_db


# ==========================================
# 5. DUAL CURSOR
# Wraps the chained .sort().limit().to_list()
# and async for iteration patterns used in routers.
# ==========================================
class DualCursor:
    """
    Mimics a Motor cursor but fetches from two collections and merges results.
    Supports: .sort(), .limit(), .to_list(), async for iteration.
    """
    def __init__(self, new_col, old_col, filter_dict):
        self._new_col    = new_col
        self._old_col    = old_col
        self._filter     = filter_dict
        self._sort_args  = None   # e.g. ("_id", -1)
        self._limit_val  = 0      # 0 = no limit
        self._results    = None   # populated lazily

    def sort(self, key, direction):
        self._sort_args = (key, direction)
        return self  # chainable

    def limit(self, n):
        self._limit_val = n
        return self  # chainable

    async def _fetch(self):
        """Fetch + merge from both DBs once, cache in self._results."""
        if self._results is not None:
            return  # already fetched

        # Fetch from both DBs — use a generous limit so we get enough to merge
        fetch_limit = (self._limit_val * 2) if self._limit_val else 0

        new_cursor = self._new_col.find(self._filter)
        old_cursor = self._old_col.find(self._filter)

        if self._sort_args:
            new_cursor = new_cursor.sort(*self._sort_args)
            old_cursor = old_cursor.sort(*self._sort_args)
        if fetch_limit:
            new_cursor = new_cursor.limit(fetch_limit)
            old_cursor = old_cursor.limit(fetch_limit)

        new_docs = await new_cursor.to_list(length=None)
        old_docs = await old_cursor.to_list(length=None)

        # Deduplicate: prefer new_db doc when the same logical key appears in both.
        # Keys: email (users), session_id (chats), user_email+date (diary), else _id str.
        seen    = set()
        merged  = []

        def _dedup_key(doc):
            if "email"      in doc: return ("email",      doc["email"])
            if "session_id" in doc: return ("session_id", doc["session_id"])
            if "user_email" in doc and "date" in doc:
                return ("diary", doc["user_email"] + doc["date"])
            return ("_id", str(doc.get("_id", "")))

        # new_db docs take priority
        for doc in new_docs:
            k = _dedup_key(doc)
            if k not in seen:
                seen.add(k)
                merged.append(doc)

        # old_db docs fill the gaps
        for doc in old_docs:
            k = _dedup_key(doc)
            if k not in seen:
                seen.add(k)
                merged.append(doc)

        # Re-sort the merged list if a sort was requested
        if self._sort_args:
            sort_key, sort_dir = self._sort_args
            import pymongo
            reverse = (sort_dir == pymongo.DESCENDING or sort_dir == -1)
            merged.sort(key=lambda d: d.get(sort_key, ""), reverse=reverse)

        # Apply final limit
        if self._limit_val:
            merged = merged[:self._limit_val]

        self._results = merged

    async def to_list(self, length=None):
        await self._fetch()
        results = self._results
        if length is not None and length > 0:
            return results[:length]
        return results

    # Support: async for doc in cursor
    def __aiter__(self):
        self._iter_index = 0
        return self

    async def __anext__(self):
        await self._fetch()
        if self._iter_index >= len(self._results):
            raise StopAsyncIteration
        doc = self._results[self._iter_index]
        self._iter_index += 1
        return doc


# ==========================================
# 6. DUAL COLLECTION WRAPPER
# Drop-in replacement for a Motor collection.
# Reads from both, writes to new only.
# ==========================================
class DualCollection:
    """
    Transparent wrapper around two Motor collections.
    Routers use this exactly like a normal Motor collection.
    Dynamically accesses the active event loop's database collections.
    """
    def __init__(self, collection_name: str):
        self._name = collection_name

    @property
    def _new(self):
        return get_new_db()[self._name]

    @property
    def _old(self):
        return get_old_db()[self._name]

    # ── READ OPERATIONS ──────────────────────────────────────────────────────

    async def find_one(self, filter_dict=None, *args, **kwargs):
        """Try new DB first. If not found, check old DB."""
        filter_dict = filter_dict or {}
        try:
            doc = await self._new.find_one(filter_dict, *args, **kwargs)
            if doc is None:
                doc = await self._old.find_one(filter_dict, *args, **kwargs)
            return doc
        except Exception as e:
            print(f"[DB find_one Error]: {e}")
            return None

    def find(self, filter_dict=None, *args, **kwargs):
        """Returns a DualCursor that merges results from both DBs."""
        filter_dict = filter_dict or {}
        return DualCursor(self._new, self._old, filter_dict)

    async def count_documents(self, filter_dict=None, *args, **kwargs):
        """Sum of both DBs for accurate totals in admin panel."""
        filter_dict = filter_dict or {}
        try:
            new_count = await self._new.count_documents(filter_dict, *args, **kwargs)
            old_count = await self._old.count_documents(filter_dict, *args, **kwargs)
            return new_count + old_count
        except Exception as e:
            print(f"[DB count_documents Error]: {e}")
            return 0

    # ── WRITE OPERATIONS (new DB only) ───────────────────────────────────────

    async def update_one(self, filter_dict, update, **kwargs):
        """
        Write to new DB only.
        Special case: if user exists in old DB but NOT in new DB yet
        (e.g. a legacy Google login user), copy their doc to new DB first
        so that updates like profile name save don't silently vanish.
        """
        try:
            existing_in_new = await self._new.find_one(filter_dict)

            if existing_in_new is None:
                existing_in_old = await self._old.find_one(filter_dict)
                if existing_in_old is not None:
                    existing_in_old.pop("_id", None)
                    try:
                        await self._new.insert_one(existing_in_old)
                    except Exception:
                        pass

            return await self._new.update_one(filter_dict, update, **kwargs)
        except Exception as e:
            print(f"[DB update_one Error]: {e}")
            return None

    async def insert_one(self, document, **kwargs):
        """Insert into new DB only."""
        try:
            return await self._new.insert_one(document, **kwargs)
        except Exception as e:
            print(f"[DB insert_one Error]: {e}")
            return None

    async def delete_many(self, filter_dict, **kwargs):
        """Delete from new DB only. Old data in shanvika_db stays untouched."""
        try:
            return await self._new.delete_many(filter_dict, **kwargs)
        except Exception as e:
            print(f"[DB delete_many Error]: {e}")
            return None

    async def delete_one(self, filter_dict, **kwargs):
        """Delete from new DB only."""
        try:
            return await self._new.delete_one(filter_dict, **kwargs)
        except Exception as e:
            print(f"[DB delete_one Error]: {e}")
            return None


# ==========================================
# 7. COLLECTION INSTANCES
# These are the exact same variable names the
# routers import via `import core.database as db_module`.
# Swapping them for DualCollection objects requires
# ZERO changes in any router file.
# ==========================================
users_collection      = DualCollection("users")
chats_collection      = DualCollection("chats")
otp_collection        = DualCollection("otps")
feedback_collection   = DualCollection("feedback")
diary_collection      = DualCollection("diary")
gallery_collection    = DualCollection("gallery")
tool_usage_collection = DualCollection("tool_usage")
error_logs_collection = DualCollection("error_logs")
settings_collection   = DualCollection("settings")


# ==========================================
# 8. PINECONE SETUP
# ==========================================
pc    = None
index = None
try:
    if PINECONE_API_KEY:
        pc         = Pinecone(api_key=PINECONE_API_KEY)
        index_name = "ethrix-memory"
        if index_name not in pc.list_indexes().names():
            try:
                pc.create_index(
                    name=index_name, dimension=768, metric='cosine',
                    spec=ServerlessSpec(cloud='aws', region='us-east-1')
                )
            except:
                pass
        index = pc.Index(index_name)
except:
    pass