# ==================================================================================
#  FILE: core/geo_pricing.py
#  DESCRIPTION: IP Geolocation + Country-based Pricing
#
#  STRATEGY:
#  1. User ka IP detect karo (request headers se — HF Spaces X-Forwarded-For use karta hai)
#  2. ip-api.com se country code fetch karo (free, no API key, 45 req/min)
#  3. MongoDB mein country_code save karo — baar baar API call nahi karni
#  4. Country ke hisaab se pricing return karo
#
#  PRICING LOGIC (PPP-based):
#  - India (IN)       → INR pricing (affordable)
#  - Other countries  → USD pricing (international rate)
# ==================================================================================

import httpx
import core.database as db_module

# ==========================================
# PRICING TABLE
# Sirf yahan badlo agar prices update karni hain
# ==========================================
PRICING = {
    "IN": {
        "country":  "India",
        "currency": "INR",
        "symbol":   "₹",
        "pro":      149,
        "elite":    399,
        "pro_display":   "₹149",
        "elite_display": "₹399",
    },
    "DEFAULT": {
        "country":  "International",
        "currency": "USD",
        "symbol":   "$",
        "pro":      5.99,
        "elite":    14.99,
        "pro_display":   "$5.99",
        "elite_display": "$14.99",
    }
}

# Countries jahan local pricing deni hai (baad mein add kar sakte ho)
LOCAL_PRICING_COUNTRIES = {"IN"}


def get_client_ip(request) -> str:
    """
    Real IP detect karo — HF Spaces aur reverse proxies ke peeche bhi.
    X-Forwarded-For header mein pehla IP real hota hai.
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP", "")
    if real_ip:
        return real_ip.strip()
    # Fallback — direct connection (localhost dev mein)
    client = getattr(request, "client", None)
    return client.host if client else "127.0.0.1"


async def fetch_country_from_ip(ip: str) -> str:
    """
    ip-api.com se country code fetch karo.
    Free tier: 45 req/min, no API key needed.
    Returns: "IN", "US", "GB" etc. — ya "IN" agar fail ho
    """
    # Localhost / private IP = India assume karo (dev environment)
    if ip in ("127.0.0.1", "::1", "localhost") or ip.startswith("192.168.") or ip.startswith("10."):
        return "IN"

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"http://ip-api.com/json/{ip}?fields=countryCode,status")
            data = resp.json()
            if data.get("status") == "success":
                return data.get("countryCode", "IN")
    except Exception as e:
        print(f"[GEO] IP lookup failed for {ip}: {e}")

    return "IN"  # Default fallback


async def get_pricing_for_user(request, user_email: str) -> dict:
    """
    Main function — user ke liye correct pricing return karo.

    Flow:
    1. MongoDB mein cached country_code check karo
    2. Agar nahi mila toh IP se fetch karo + MongoDB mein save karo
    3. Country ke hisaab se pricing return karo
    """
    country_code = "IN"  # default

    # Step 1: MongoDB cache check
    if user_email and not user_email.endswith("@ethrix.ai"):
        try:
            user = await db_module.users_collection.find_one(
                {"email": user_email},
                {"country_code": 1}
            )
            if user and user.get("country_code"):
                country_code = user["country_code"]
            else:
                # Step 2: IP se fetch karo
                ip = get_client_ip(request)
                country_code = await fetch_country_from_ip(ip)

                # Step 3: MongoDB mein save karo (ek baar hi)
                await db_module.users_collection.update_one(
                    {"email": user_email},
                    {"$set": {"country_code": country_code}}
                )
        except Exception as e:
            print(f"[GEO] Pricing fetch error: {e}")
    else:
        # Guest user — IP se detect karo (save nahi karenge)
        ip = get_client_ip(request)
        country_code = await fetch_country_from_ip(ip)

    # Step 4: Pricing determine karo
    pricing = PRICING.get(country_code) if country_code in LOCAL_PRICING_COUNTRIES else PRICING["DEFAULT"]

    return {
        "country_code":   country_code,
        "country":        pricing["country"],
        "currency":       pricing["currency"],
        "symbol":         pricing["symbol"],
        "pro_price":      pricing["pro"],
        "elite_price":    pricing["elite"],
        "pro_display":    pricing["pro_display"],
        "elite_display":  pricing["elite_display"],
        "period":         "/ month",
    }