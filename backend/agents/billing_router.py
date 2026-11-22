"""
MarketPulse Billing & Pro Package Engine (`backend/agents/billing_router.py`)

Design Rules:
  - Internal LLM API token budgets are tracked silently in PostgreSQL (`user_wallets` and `agent_token_logs`)
    to cover backend LLM API costs, NEVER exposed as raw token numbers to end users.
  - User-facing UI & responses strictly present capabilities:
      * Starter Free ($0): Market news feed, ticker search, and watchlist tracking.
      * Pro Package (`pro_monthly` — $19/mo): Unlocks full Multi-Agent AI Analysis for tracked companies,
        Autonomous Corporate Footprint & Supply-Chain Discovery, Contradiction Radar, and Quant Factor Research.
  - Supports Stripe Checkout Sessions (`STRIPE_SECRET_KEY`) with an automatic built-in Stripe Sandbox Checkout
    for local development.
"""

import asyncio
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
import httpx
from loguru import logger
from pydantic import BaseModel

from agents.db import query
from auth import get_current_user

billing_router = APIRouter(prefix="/billing", tags=["Billing & Pro Package"])

# Tracks which authenticated user triggered the current LLM agent execution for silent backend token accounting
current_billing_user_id: ContextVar[Optional[int]] = ContextVar("current_billing_user_id", default=None)

# Internal backend token budgets (never displayed in UI)
INTERNAL_FREE_TOKEN_BUDGET = 50_000
INTERNAL_PRO_TOKEN_BUDGET = 500_000

TIER_RANK: Dict[str, int] = {
    "free": 0,
    "pro": 1,
}

PACKAGES_CATALOG: Dict[str, Dict[str, Any]] = {
    "free": {
        "id": "free",
        "name": "Starter Free",
        "kind": "subscription",
        "tier": "free",
        "price_usd": 0,
        "price_cents": 0,
        "billing_interval": "forever",
        "badge": "Current Default",
        "tagline": "Essential market monitoring and watchlist tracking.",
        "description": "Track your favorite companies, follow live market news, and browse ticker snapshots.",
        "capabilities": [
            "Real-Time Market News Feed",
            "Personal Company Watchlist Tracking",
            "Global Ticker Search & Sector Snapshots",
            "Preview Demo Analysis Reports",
        ],
        "_internal_tokens": INTERNAL_FREE_TOKEN_BUDGET,
    },
    "pro_monthly": {
        "id": "pro_monthly",
        "name": "Pro Package",
        "kind": "subscription",
        "tier": "pro",
        "price_usd": 19,
        "price_cents": 1900,
        "billing_interval": "month",
        "badge": "Recommended",
        "tagline": "Full autonomous multi-agent intelligence for every company you track.",
        "description": (
            "Unlock deep 6-agent consensus equity research, live SEC 10-K & Wikipedia supply-chain footprint "
            "discovery, cross-perspective contradiction alerts, and quantitative position sizing."
        ),
        "capabilities": [
            "Agentic AI Analysis for Tracked Companies (News, Sentiment, Fundamentals, Technical, Equity & Risk Agents)",
            "Autonomous Corporate Footprint & Tier-1 Supplier Discovery (SEC 10-K + Wikipedia + Web Verification)",
            "Contradiction Radar (Western Wires vs. Local On-Ground Hub Press)",
            "Quantitative Factor Research (QRA) & Portfolio Position Sizing",
            "Priority AI Synthesis & Guardrail-Verified Citations",
        ],
        "_internal_tokens": INTERNAL_PRO_TOKEN_BUDGET,
    },
}

_billing_tables_ready = False
_MEM_WALLETS: Dict[int, Dict[str, Any]] = {}
_MEM_TRANSACTIONS: List[Dict[str, Any]] = []


def ensure_billing_tables() -> None:
    """Idempotently creates `user_wallets` and `payment_transactions` in PostgreSQL."""
    global _billing_tables_ready
    if _billing_tables_ready:
        return
    try:
        query(
            """CREATE TABLE IF NOT EXISTS user_wallets (
                user_id INTEGER PRIMARY KEY,
                tier VARCHAR(32) NOT NULL DEFAULT 'free',
                token_balance BIGINT NOT NULL DEFAULT 50000,
                monthly_allowance BIGINT NOT NULL DEFAULT 50000,
                total_tokens_purchased BIGINT NOT NULL DEFAULT 50000,
                total_tokens_consumed BIGINT NOT NULL DEFAULT 0,
                stripe_customer_id VARCHAR(128),
                stripe_subscription_id VARCHAR(128),
                period_ends_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        query(
            """CREATE TABLE IF NOT EXISTS payment_transactions (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(128) UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                package_id VARCHAR(64) NOT NULL,
                package_name VARCHAR(128) NOT NULL,
                kind VARCHAR(32) NOT NULL,
                tier_granted VARCHAR(32),
                amount_cents INTEGER NOT NULL,
                currency VARCHAR(10) NOT NULL DEFAULT 'USD',
                tokens_granted BIGINT NOT NULL,
                provider VARCHAR(32) NOT NULL DEFAULT 'stripe_sandbox',
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                card_last4 VARCHAR(8),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )"""
        )
        query(
            """ALTER TABLE agent_token_logs
               ADD COLUMN IF NOT EXISTS user_id INTEGER"""
        )
        _billing_tables_ready = True
    except Exception as exc:
        logger.debug(f"Billing tables init note (using memory fallback if DB offline): {exc}")


def get_or_create_wallet(user_id: int) -> Dict[str, Any]:
    """Fetches or initializes the user's subscription record (internal token fields stay server-side)."""
    uid = int(user_id)
    ensure_billing_tables()
    try:
        res = query("SELECT * FROM user_wallets WHERE user_id = %s", [uid])
        if res.rows:
            row = dict(res.rows[0])
            _MEM_WALLETS[uid] = row
            return row

        query(
            """INSERT INTO user_wallets
               (user_id, tier, token_balance, monthly_allowance, total_tokens_purchased, total_tokens_consumed)
               VALUES (%s, 'free', %s, %s, %s, 0)
               ON CONFLICT (user_id) DO NOTHING""",
            [uid, INTERNAL_FREE_TOKEN_BUDGET, INTERNAL_FREE_TOKEN_BUDGET, INTERNAL_FREE_TOKEN_BUDGET],
        )
        res2 = query("SELECT * FROM user_wallets WHERE user_id = %s", [uid])
        if res2.rows:
            row = dict(res2.rows[0])
            _MEM_WALLETS[uid] = row
            return row
    except Exception as exc:
        logger.debug(f"DB wallet lookup fallback for user {uid}: {exc}")

    if uid not in _MEM_WALLETS:
        _MEM_WALLETS[uid] = {
            "user_id": uid,
            "tier": "free",
            "token_balance": INTERNAL_FREE_TOKEN_BUDGET,
            "monthly_allowance": INTERNAL_FREE_TOKEN_BUDGET,
            "total_tokens_purchased": INTERNAL_FREE_TOKEN_BUDGET,
            "total_tokens_consumed": 0,
            "period_ends_at": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    return _MEM_WALLETS[uid]


def sanitize_public_package(pkg: Dict[str, Any]) -> Dict[str, Any]:
    """Strips internal token budget fields before sending package definitions to the frontend."""
    return {k: v for k, v in pkg.items() if not k.startswith("_")}


def sanitize_public_membership(wallet: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns user-facing membership details WITHOUT exposing raw token counts.
    """
    tier = str(wallet.get("tier", "free")).lower()
    is_pro = TIER_RANK.get(tier, 0) >= TIER_RANK["pro"]
    internal_balance = int(wallet.get("token_balance", 0))
    pkg = PACKAGES_CATALOG["pro_monthly"] if is_pro else PACKAGES_CATALOG["free"]

    return {
        "user_id": wallet.get("user_id"),
        "tier": "pro" if is_pro else "free",
        "plan_name": pkg["name"],
        "status": "active" if (is_pro and internal_balance > 0) else ("capacity_reached" if is_pro else "free_tier"),
        "is_pro": is_pro,
        "has_active_capacity": internal_balance > 0,
        "period_ends_at": wallet.get("period_ends_at"),
        "capabilities": pkg["capabilities"],
        "permissions": {
            "agentic_company_analysis": is_pro or internal_balance > 0,
            "live_footprint_discovery": is_pro,
            "contradiction_radar": is_pro,
            "quant_research_qra": is_pro,
        },
    }


def deduct_user_tokens(user_id: Optional[int], tokens_used: int, agent_name: str = "", ticker: str = "") -> Optional[Dict[str, Any]]:
    """
    Silently deducts exact LLM tokens consumed (`prompt_tokens + completion_tokens`) in the backend database
    so Pro package payments fund the user's internal API token allocation.
    """
    if user_id is None or tokens_used <= 0:
        return None

    uid = int(user_id)
    wallet = get_or_create_wallet(uid)
    new_balance = max(0, int(wallet.get("token_balance", 0)) - int(tokens_used))
    new_consumed = int(wallet.get("total_tokens_consumed", 0)) + int(tokens_used)

    wallet["token_balance"] = new_balance
    wallet["total_tokens_consumed"] = new_consumed
    _MEM_WALLETS[uid] = wallet

    try:
        query(
            """UPDATE user_wallets
               SET token_balance = GREATEST(0, token_balance - %s),
                   total_tokens_consumed = total_tokens_consumed + %s,
                   updated_at = CURRENT_TIMESTAMP
               WHERE user_id = %s""",
            [int(tokens_used), int(tokens_used), uid],
        )
    except Exception as exc:
        logger.debug(f"DB silent token deduction fallback for user {uid}: {exc}")

    logger.info(f"[Backend Token Accounting | User {uid}] {agent_name} ({ticker}) used {tokens_used:,} tokens.")
    return wallet


def check_tokens_and_tier(
    user: dict,
    min_tokens_required: int = 1,
    required_tier: str = "free",
    feature_name: str = "Agentic Company Analysis",
) -> Dict[str, Any]:
    """
    Checks whether the user's membership tier and internal API capacity allow running `feature_name`.
    Never exposes raw token counts in error messages—prompts the user to unlock/renew the Pro Package.
    """
    raw_sub = user.get("sub")
    if not raw_sub or raw_sub == "internal-service":
        return {"tier": "pro", "is_pro": True}

    uid = int(raw_sub)
    wallet = get_or_create_wallet(uid)
    user_tier = str(wallet.get("tier", "free")).lower()
    balance = int(wallet.get("token_balance", 0))

    if TIER_RANK.get(user_tier, 0) < TIER_RANK.get(required_tier.lower(), 0):
        raise HTTPException(
            status_code=402,
            detail={
                "code": "PRO_UPGRADE_REQUIRED",
                "message": (
                    f"'{feature_name}' is a Pro Package capability. "
                    "Upgrade to the Pro Package ($19/mo) to unlock full multi-agent AI analysis "
                    "and live supply-chain intelligence for the companies you track."
                ),
                "current_tier": user_tier,
                "required_tier": "pro",
                "feature_name": feature_name,
            },
        )

    if balance < min_tokens_required:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "PRO_CAPACITY_REACHED",
                "message": (
                    f"You have reached your current plan's AI analysis capacity for '{feature_name}'. "
                    "Upgrade or renew your Pro Package ($19/mo) to continue running live multi-agent research."
                ),
                "current_tier": user_tier,
                "required_tier": "pro",
                "feature_name": feature_name,
            },
        )

    return sanitize_public_membership(wallet)


def _fulfill_pro_purchase(
    session_id: str,
    user_id: int,
    package_id: str = "pro_monthly",
    provider: str = "stripe_sandbox",
    card_last4: str = "4242",
) -> Dict[str, Any]:
    """
    Activates the user's Pro Package membership and silently provisions the internal API token budget.
    """
    pkg = PACKAGES_CATALOG.get(package_id) or PACKAGES_CATALOG["pro_monthly"]
    uid = int(user_id)
    wallet = get_or_create_wallet(uid)
    ensure_billing_tables()

    try:
        existing = query("SELECT * FROM payment_transactions WHERE session_id = %s", [session_id])
        if existing.rows and existing.rows[0].get("status") == "completed":
            tx_clean = dict(existing.rows[0])
            tx_clean.pop("tokens_granted", None)
            return {
                "already_completed": True,
                "transaction": tx_clean,
                "membership": sanitize_public_membership(get_or_create_wallet(uid)),
            }
    except Exception:
        for tx in _MEM_TRANSACTIONS:
            if tx.get("session_id") == session_id and tx.get("status") == "completed":
                return {
                    "already_completed": True,
                    "transaction": {k: v for k, v in tx.items() if k != "tokens_granted"},
                    "membership": sanitize_public_membership(wallet),
                }

    internal_tokens = int(pkg.get("_internal_tokens", INTERNAL_PRO_TOKEN_BUDGET))
    period_ends = (datetime.now(timezone.utc) + timedelta(days=30)).replace(tzinfo=None)
    new_balance = int(wallet.get("token_balance", 0)) + internal_tokens
    new_purchased = int(wallet.get("total_tokens_purchased", 0)) + internal_tokens

    wallet.update(
        {
            "tier": "pro",
            "token_balance": new_balance,
            "monthly_allowance": internal_tokens,
            "total_tokens_purchased": new_purchased,
            "period_ends_at": period_ends.isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _MEM_WALLETS[uid] = wallet

    tx_record = {
        "session_id": session_id,
        "user_id": uid,
        "package_id": pkg["id"],
        "package_name": pkg["name"],
        "kind": pkg["kind"],
        "tier_granted": "pro",
        "amount_cents": pkg["price_cents"],
        "currency": "USD",
        "provider": provider,
        "status": "completed",
        "card_last4": card_last4,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        query(
            """UPDATE user_wallets
               SET tier = 'pro',
                   token_balance = token_balance + %s,
                   monthly_allowance = %s,
                   total_tokens_purchased = total_tokens_purchased + %s,
                   period_ends_at = %s,
                   updated_at = CURRENT_TIMESTAMP
               WHERE user_id = %s""",
            [internal_tokens, internal_tokens, internal_tokens, period_ends, uid],
        )
        query(
            """INSERT INTO payment_transactions
               (session_id, user_id, package_id, package_name, kind, tier_granted,
                amount_cents, currency, tokens_granted, provider, status, card_last4, completed_at)
               VALUES (%s, %s, %s, %s, %s, 'pro', %s, 'USD', %s, %s, 'completed', %s, CURRENT_TIMESTAMP)
               ON CONFLICT (session_id) DO UPDATE SET
                   status = 'completed',
                   card_last4 = EXCLUDED.card_last4,
                   completed_at = CURRENT_TIMESTAMP""",
            [
                session_id,
                uid,
                pkg["id"],
                pkg["name"],
                pkg["kind"],
                pkg["price_cents"],
                internal_tokens,
                provider,
                card_last4,
            ],
        )
    except Exception as exc:
        logger.debug(f"DB Pro activation fallback for user {uid} (using memory store): {exc}")
        _MEM_TRANSACTIONS.append({**tx_record, "tokens_granted": internal_tokens})

    logger.info(f"[Billing | User {uid}] Pro Package activated via {provider} (session {session_id}).")
    return {
        "already_completed": False,
        "transaction": tx_record,
        "membership": sanitize_public_membership(wallet),
    }


class CreateCheckoutRequest(BaseModel):
    package_id: str = "pro_monthly"
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class ConfirmCheckoutRequest(BaseModel):
    session_id: str
    package_id: Optional[str] = "pro_monthly"
    card_last4: Optional[str] = None


async def _verify_stripe_session(session_id: str, uid: int, stripe_secret: str) -> Dict[str, Any]:
    """
    Server-side check that a real Stripe Checkout Session was paid by THIS user.
    The browser only tells us a session_id, so we never trust it without asking Stripe.
    """
    try:
        async with httpx.AsyncClient() as http_client:
            resp = await http_client.get(
                f"https://api.stripe.com/v1/checkout/sessions/{session_id}",
                auth=(stripe_secret, ""),
                timeout=10.0,
            )
    except httpx.HTTPError as exc:
        logger.warning(f"Stripe session verification unreachable: {exc}")
        raise HTTPException(status_code=502, detail="Could not reach Stripe to verify payment. Please retry.")
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Could not verify this checkout session with Stripe.")
    session = resp.json()
    if session.get("client_reference_id") != str(uid):
        raise HTTPException(status_code=403, detail="This checkout session belongs to a different account.")
    if session.get("status") != "complete" or session.get("payment_status") not in ("paid", "no_payment_required"):
        raise HTTPException(status_code=402, detail="Payment has not been completed for this checkout session.")
    return session


@billing_router.get("/packages")
async def list_billing_packages():
    """Returns the Starter Free plan and the Pro Package (with capability descriptions only, no token counts)."""
    stripe_configured = bool(os.environ.get("STRIPE_SECRET_KEY", "").strip())
    return {
        "currency": "USD",
        "stripe_mode": "live_api" if stripe_configured else "sandbox_checkout",
        "packages": [
            sanitize_public_package(PACKAGES_CATALOG["free"]),
            sanitize_public_package(PACKAGES_CATALOG["pro_monthly"]),
        ],
    }


@billing_router.get("/wallet")
async def get_user_membership_status(user: dict = Depends(get_current_user)):
    """
    Returns the authenticated user's active membership plan, unlocked capabilities,
    and payment receipt history (never exposes raw token numbers).
    """
    uid = int(user["sub"])
    wallet = await asyncio.to_thread(get_or_create_wallet, uid)
    membership = sanitize_public_membership(wallet)

    transactions: List[Dict[str, Any]] = []
    try:
        tx_res = await asyncio.to_thread(
            query,
            """SELECT session_id, package_id, package_name, kind, tier_granted,
                      amount_cents, currency, provider, status, card_last4, created_at, completed_at
               FROM payment_transactions
               WHERE user_id = %s
               ORDER BY id DESC
               LIMIT 15""",
            [uid],
        )
        transactions = [dict(r) for r in tx_res.rows]
    except Exception:
        transactions = [
            {k: v for k, v in t.items() if k != "tokens_granted"}
            for t in _MEM_TRANSACTIONS
            if t.get("user_id") == uid
        ][:15]

    return {
        "membership": membership,
        "transactions": transactions,
    }


@billing_router.post("/checkout")
async def create_checkout_session(body: CreateCheckoutRequest, user: dict = Depends(get_current_user)):
    """
    Initializes a Stripe Checkout Session for the Pro Package ($19/mo).
    Uses official Stripe Checkout API if `STRIPE_SECRET_KEY` is present in `.env`,
    otherwise launches the interactive Stripe Sandbox Checkout modal.
    """
    pkg = PACKAGES_CATALOG.get(body.package_id)
    if not pkg or pkg["price_cents"] <= 0:
        raise HTTPException(status_code=400, detail="Please select the Pro Package to proceed to checkout.")

    uid = int(user["sub"])
    public_pkg = sanitize_public_package(pkg)
    stripe_secret = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    origin = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    success_url = body.success_url or f"{origin}/billing?checkout=success&package_id={pkg['id']}&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = body.cancel_url or f"{origin}/billing?checkout=cancelled"

    if stripe_secret.startswith(("sk_test_", "sk_live_")):
        try:
            form_data: Dict[str, Any] = {
                "mode": "subscription",
                "success_url": success_url,
                "cancel_url": cancel_url,
                "client_reference_id": str(uid),
                "customer_email": user.get("email", ""),
                "metadata[user_id]": str(uid),
                "metadata[package_id]": pkg["id"],
                "line_items[0][quantity]": "1",
                "line_items[0][price_data][currency]": "usd",
                "line_items[0][price_data][unit_amount]": str(pkg["price_cents"]),
                "line_items[0][price_data][recurring][interval]": "month",
                "line_items[0][price_data][product_data][name]": f"FinnWinn {pkg['name']}",
                "line_items[0][price_data][product_data][description]": pkg["tagline"],
            }
            async with httpx.AsyncClient() as http_client:
                resp = await http_client.post(
                    "https://api.stripe.com/v1/checkout/sessions",
                    data=form_data,
                    auth=(stripe_secret, ""),
                    timeout=10.0,
                )
            if resp.status_code == 200:
                s_data = resp.json()
                return {
                    "mode": "stripe_redirect",
                    "session_id": s_data["id"],
                    "checkout_url": s_data["url"],
                    "package": public_pkg,
                }
        except Exception as exc:
            logger.warning(f"Stripe API call fallback to Sandbox Checkout: {exc}")

    sandbox_session_id = f"cs_test_{uuid.uuid4().hex[:24]}"
    return {
        "mode": "stripe_sandbox",
        "session_id": sandbox_session_id,
        "checkout_url": None,
        "package": public_pkg,
    }


@billing_router.post("/confirm")
async def confirm_checkout_payment(body: ConfirmCheckoutRequest, user: dict = Depends(get_current_user)):
    """Confirms a Pro Package payment and unlocks Pro agentic analysis capabilities."""
    uid = int(user["sub"])
    clean_last4 = (body.card_last4 or "4242").strip()[-4:]
    stripe_secret = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    provider = "stripe_sandbox"

    if stripe_secret.startswith(("sk_test_", "sk_live_")):
        # Real Stripe is configured: only activate Pro if Stripe says this user paid.
        await _verify_stripe_session(body.session_id, uid, stripe_secret)
        provider = "stripe"
    elif os.environ.get("ALLOW_SANDBOX_BILLING", "true").strip().lower() in ("false", "0", "no"):
        raise HTTPException(status_code=503, detail="Payments are not available right now. Please try again later.")

    result = await asyncio.to_thread(
        _fulfill_pro_purchase,
        body.session_id,
        uid,
        body.package_id or "pro_monthly",
        provider,
        clean_last4,
    )
    return {
        "status": "succeeded",
        "message": "Pro Package activated! You now have full multi-agent AI analysis for the companies you track.",
        **result,
    }
