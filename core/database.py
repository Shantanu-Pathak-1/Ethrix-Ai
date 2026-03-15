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
SECRET_KEY          = os.getenv("SECRET_KEY")  # HF Spaces → Settings → Secrets mein set karo
GOOGLE_CLIENT_ID    = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET= os.getenv("GOOGLE_CLIENT_SECRET")
MONGO_URL           = os.getenv("MONGO_URL")
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
# 4. RAW DATABASE CONNECTIONS
# Both connections share the same MONGO_URL.
# They just point to different databases inside
# the same MongoDB Atlas cluster.
#
# ⚠️  connect=False  → Motor will NOT open a connection at import time.
#     It connects lazily on the FIRST actual DB call, which always happens
#     inside an async route (correct event loop). This eliminates the
#     "Future attached to a different loop" error from background tasks.
# ==========================================
_mongo_client = AsyncIOMotorClient(MONGO_URL, tlsCAFile=certifi.where(), connect=False)

_old_db = _mongo_client.shanvika_db   # ← Legacy data lives here (READ ONLY effectively)
_new_db = _mongo_client.ethrix_db     # ← All new data goes here (READ + WRITE)


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
    """
    def __init__(self, new_col, old_col):
        self._new = new_col  # ethrix_db collection  — reads + writes
        self._old = old_col  # shanvika_db collection — reads only

    # ── READ OPERATIONS ──────────────────────────────────────────────────────

    async def find_one(self, filter_dict=None, *args, **kwargs):
        """Try new DB first. If not found, check old DB."""
        filter_dict = filter_dict or {}
        doc = await self._new.find_one(filter_dict, *args, **kwargs)
        if doc is None:
            doc = await self._old.find_one(filter_dict, *args, **kwargs)
        return doc

    def find(self, filter_dict=None, *args, **kwargs):
        """Returns a DualCursor that merges results from both DBs."""
        filter_dict = filter_dict or {}
        return DualCursor(self._new, self._old, filter_dict)

    async def count_documents(self, filter_dict=None, *args, **kwargs):
        """Sum of both DBs for accurate totals in admin panel."""
        filter_dict = filter_dict or {}
        new_count = await self._new.count_documents(filter_dict, *args, **kwargs)
        old_count = await self._old.count_documents(filter_dict, *args, **kwargs)
        return new_count + old_count

    # ── WRITE OPERATIONS (new DB only) ───────────────────────────────────────

    async def update_one(self, filter_dict, update, **kwargs):
        """
        Write to new DB only.
        Special case: if user exists in old DB but NOT in new DB yet
        (e.g. a legacy Google login user), copy their doc to new DB first
        so that updates like profile name save don't silently vanish.
        """
        upsert = kwargs.get("upsert", False)

        # Check if the doc already exists in new DB
        existing_in_new = await self._new.find_one(filter_dict)

        if existing_in_new is None:
            # Check if it exists in old DB
            existing_in_old = await self._old.find_one(filter_dict)
            if existing_in_old is not None:
                # Migrate the old doc to new DB so the update lands correctly
                existing_in_old.pop("_id", None)   # remove old ObjectId
                try:
                    await self._new.insert_one(existing_in_old)
                except Exception:
                    pass  # doc may have been inserted by a race condition

        return await self._new.update_one(filter_dict, update, **kwargs)

    async def insert_one(self, document, **kwargs):
        """Insert into new DB only."""
        return await self._new.insert_one(document, **kwargs)

    async def delete_many(self, filter_dict, **kwargs):
        """Delete from new DB only. Old data in shanvika_db stays untouched."""
        return await self._new.delete_many(filter_dict, **kwargs)

    async def delete_one(self, filter_dict, **kwargs):
        """Delete from new DB only."""
        return await self._new.delete_one(filter_dict, **kwargs)


# ==========================================
# 7. COLLECTION INSTANCES
# These are the exact same variable names the
# routers import via `import core.database as db_module`.
# Swapping them for DualCollection objects requires
# ZERO changes in any router file.
# ==========================================
users_collection      = DualCollection(_new_db.users,      _old_db.users)
chats_collection      = DualCollection(_new_db.chats,      _old_db.chats)
otp_collection        = DualCollection(_new_db.otps,       _old_db.otps)
feedback_collection   = DualCollection(_new_db.feedback,   _old_db.feedback)
diary_collection      = DualCollection(_new_db.diary,      _old_db.diary)
gallery_collection    = DualCollection(_new_db.gallery,    _old_db.gallery)
tool_usage_collection = DualCollection(_new_db.tool_usage, _old_db.tool_usage)
error_logs_collection = DualCollection(_new_db.error_logs, _old_db.error_logs)
settings_collection   = DualCollection(_new_db.settings,   _old_db.settings)


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