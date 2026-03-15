# ==================================================================================
#  FILE: core/rate_limiter.py
#  DESCRIPTION: MongoDB-based Rate Limiter — 3 Tiers (Free / Pro / Elite)
#
#  PLANS:
#  - free  → 20 AI  + 10 tool  calls / day
#  - pro   → 80 AI  + 40 tool  calls / day
#  - elite → 200 AI + 100 tool calls / day
#  - admin → unlimited (always bypassed)
#
#  BACKWARD COMPAT:
#  - Purane users jinke paas sirf is_pro:true hai → "pro" treat hoga
#  - Naye users ke paas plan:"free"|"pro"|"elite" field hoga
# ==================================================================================

from datetime import date
import core.database as db_module

# ==========================================
# PLAN LIMITS — ek jagah se sab control
# ==========================================
LIMITS = {
    "free":  {"ai_calls": 20,  "tool_calls": 10},
    "pro":   {"ai_calls": 80,  "tool_calls": 40},
    "elite": {"ai_calls": 200, "tool_calls": 100},
}

PLAN_DISPLAY = {
    "free":  {"label": "Free Plan",  "color": "cyan",   "icon": "✦"},
    "pro":   {"label": "Pro Plan",   "color": "blue",   "icon": "⚡"},
    "elite": {"label": "Elite Plan", "color": "purple", "icon": "👑"},
}


def _get_plan(user: dict) -> str:
    """
    User document se plan determine karo.
    Priority: plan field > is_pro field > default free
    """
    plan = user.get("plan", "")
    if plan in ("free", "pro", "elite"):
        return plan
    # Backward compat — purane is_pro users
    if user.get("is_pro", False):
        return "pro"
    return "free"


async def check_and_increment(user_email: str, call_type: str = "ai_calls") -> dict:
    """
    Limit check karo aur ek call count karo.
    Returns: allowed, used, limit, remaining, plan, upgrade_needed
    """
    today = str(date.today())

    # Admin hamesha allowed — koi count nahi
    if user_email == db_module.ADMIN_EMAIL:
        return {
            "allowed": True, "used": 0, "limit": 9999,
            "remaining": 9999, "plan": "admin"
        }

    # Guest users — free plan limits apply
    if user_email.endswith("@ethrix.ai"):
        return {
            "allowed": False,
            "reason": "Guests can't use AI features. Please login! 😊",
            "upgrade_needed": False,
            "plan": "guest"
        }

    user = await db_module.users_collection.find_one({"email": user_email})
    if not user:
        return {"allowed": False, "reason": "User not found", "upgrade_needed": False}

    plan  = _get_plan(user)
    limit = LIMITS[plan][call_type]

    # Daily usage
    usage = user.get("daily_usage", {})
    if usage.get("date") != today:
        usage = {"date": today, "ai_calls": 0, "tool_calls": 0}

    current = usage.get(call_type, 0)

    if current >= limit:
        plan_labels = {"free": "Pro", "pro": "Elite"}
        upgrade_to  = plan_labels.get(plan, "")
        reason_msg  = (
            f"Aaj ka limit khatam! ({current}/{limit})"
            + (f" Upgrade to {upgrade_to} for more." if upgrade_to else "")
        )
        return {
            "allowed":        False,
            "reason":         reason_msg,
            "used":           current,
            "limit":          limit,
            "remaining":      0,
            "upgrade_needed": plan in ("free", "pro"),
            "current_plan":   plan,
            "plan":           plan,
        }

    # Increment
    usage[call_type] = current + 1
    await db_module.users_collection.update_one(
        {"email": user_email},
        {"$set": {"daily_usage": usage}}
    )

    return {
        "allowed":   True,
        "used":      current + 1,
        "limit":     limit,
        "remaining": limit - current - 1,
        "plan":      plan,
    }


async def get_usage_info(user_email: str) -> dict:
    """
    /api/usage endpoint ke liye — current day usage + plan info
    """
    today = str(date.today())

    if user_email == db_module.ADMIN_EMAIL:
        return {
            "ai_calls": 0, "tool_calls": 0,
            "ai_limit": 9999, "tool_limit": 9999,
            "ai_remaining": 9999, "tool_remaining": 9999,
            "plan": "admin", "plan_label": "Admin",
            "plan_color": "red", "plan_icon": "🛡️"
        }

    user = await db_module.users_collection.find_one({"email": user_email})
    if not user:
        return {
            "ai_calls": 0, "tool_calls": 0,
            "ai_limit": 20, "tool_limit": 10,
            "ai_remaining": 20, "tool_remaining": 10,
            "plan": "free", "plan_label": "Free Plan",
            "plan_color": "cyan", "plan_icon": "✦"
        }

    plan       = _get_plan(user)
    ai_limit   = LIMITS[plan]["ai_calls"]
    tool_limit = LIMITS[plan]["tool_calls"]

    usage      = user.get("daily_usage", {})
    ai_used    = usage.get("ai_calls",   0) if usage.get("date") == today else 0
    tool_used  = usage.get("tool_calls", 0) if usage.get("date") == today else 0

    display = PLAN_DISPLAY.get(plan, PLAN_DISPLAY["free"])

    return {
        "ai_calls":      ai_used,
        "tool_calls":    tool_used,
        "ai_limit":      ai_limit,
        "tool_limit":    tool_limit,
        "ai_remaining":  max(0, ai_limit   - ai_used),
        "tool_remaining":max(0, tool_limit - tool_used),
        "plan":          plan,
        "plan_label":    display["label"],
        "plan_color":    display["color"],
        "plan_icon":     display["icon"],
    }