"""Local HarborLedger API used as the default performance target.

All records are synthetic. Latency is injected only when a caller sends
``X-Demo-Latency-Ms`` and is capped by ``DEMO_MAX_LATENCY_MS`` (default 400).
Bundled performance profiles do not send that header, so their response times
are the real cost of this process plus the client.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import threading
import time
import uuid
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

LOCAL_DEMO_USERNAME = os.environ.get("DEMO_API_USERNAME", "demo")
LOCAL_DEMO_PASSWORD = os.environ.get("DEMO_API_PASSWORD", "demo-local-only")
TOKEN_SECRET = os.environ.get("DEMO_TOKEN_SECRET", "demo-token-secret-local")
MAX_LATENCY_MS = int(os.environ.get("DEMO_MAX_LATENCY_MS", "400"))
TOKEN_TTL_SECONDS = 3600

app = FastAPI(title="HarborLedger Demo API", version="1.0.0")
_LOCK = threading.Lock()

USERS: list[dict[str, Any]] = [
    {"id": "usr-1001", "name": "Avery Quinn", "email": "avery.quinn@example.test"},
    {"id": "usr-1002", "name": "Blake Chen", "email": "blake.chen@example.test"},
    {"id": "usr-1003", "name": "Casey Okonkwo", "email": "casey.okonkwo@example.test"},
    {"id": "usr-1004", "name": "Devon Patel", "email": "devon.patel@example.test"},
]
ACCOUNTS: list[dict[str, Any]] = [
    {"id": "acct-1001", "user_id": "usr-1001", "currency": "USD", "balance": 1_000_000.0},
    {"id": "acct-1002", "user_id": "usr-1002", "currency": "USD", "balance": 1_000_000.0},
    {"id": "acct-1003", "user_id": "usr-1003", "currency": "EUR", "balance": 1_000_000.0},
    {"id": "acct-1004", "user_id": "usr-1004", "currency": "USD", "balance": 1_000_000.0},
    {"id": "acct-2001", "user_id": "usr-1004", "currency": "USD", "balance": 5.0},
]
TRANSACTIONS: list[dict[str, Any]] = [
    {
        "id": f"txn-{index:04d}",
        "account_id": ACCOUNTS[index % len(ACCOUNTS)]["id"],
        "amount": float((index % 20) + 1),
        "description": f"synthetic transfer {index}",
    }
    for index in range(1, 41)
]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(pattern=r"^[^@\s]+@example\.test$")


class TransactionCreate(BaseModel):
    account_id: str = Field(pattern=r"^acct-\d{4}$")
    amount: int = Field(ge=1, le=500)
    description: str = Field(min_length=3, max_length=80)


def _sign(payload: str) -> str:
    return hmac.new(TOKEN_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def issue_token(username: str) -> str:
    expires = int(time.time()) + TOKEN_TTL_SECONDS
    payload = f"{username}.{expires}"
    return f"{payload}.{_sign(payload)}"


def verify_token(token: str) -> str | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = f"{parts[0]}.{parts[1]}"
    expected = _sign(payload)
    if not hmac.compare_digest(expected, parts[2]):
        return None
    try:
        expires = int(parts[1])
    except ValueError:
        return None
    if expires < int(time.time()):
        return None
    return parts[0]


def require_user(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="authentication required")
    username = verify_token(authorization.split(" ", 1)[1].strip())
    if username is None:
        raise HTTPException(status_code=401, detail="invalid token")
    return username


def paginate(items: list[dict[str, Any]], page: int, page_size: int) -> dict[str, Any]:
    start = (page - 1) * page_size
    view = items[start : start + page_size]
    return {
        "page": page,
        "page_size": page_size,
        "total": len(items),
        "items": view,
    }


@app.middleware("http")
async def injected_latency(request, call_next):
    raw = request.headers.get("x-demo-latency-ms", "0")
    try:
        requested = int(raw)
    except ValueError:
        requested = 0
    injected = max(0, min(requested, MAX_LATENCY_MS))
    if injected:
        await asyncio.sleep(injected / 1000)
    response = await call_next(request)
    response.headers["X-Demo-Injected-Latency-Ms"] = str(injected)
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "harborledger-demo"}


@app.post("/auth/token")
def login(body: LoginRequest) -> dict[str, Any]:
    password_ok = hmac.compare_digest(body.password, LOCAL_DEMO_PASSWORD)
    user_ok = hmac.compare_digest(body.username, LOCAL_DEMO_USERNAME)
    if not (password_ok and user_ok):
        raise HTTPException(status_code=401, detail="invalid credentials")
    scheme = "bearer"
    return {
        "access_token": issue_token(body.username),
        "token_type": scheme,
        "expires_in": TOKEN_TTL_SECONDS,
    }


@app.get("/users")
def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    _: str = Depends(require_user),
) -> dict[str, Any]:
    return paginate(USERS, page, page_size)


@app.get("/users/{user_id}")
def get_user(user_id: str, _: str = Depends(require_user)) -> dict[str, Any]:
    for user in USERS:
        if user["id"] == user_id:
            return user
    raise HTTPException(status_code=404, detail="user not found")


@app.post("/users", status_code=201)
def create_user(body: UserCreate, _: str = Depends(require_user)) -> dict[str, Any]:
    record = {"id": f"usr-{uuid.uuid4().hex[:4]}", "name": body.name, "email": body.email}
    with _LOCK:
        USERS.append(record)
    return record


@app.get("/accounts")
def list_accounts(_: str = Depends(require_user)) -> dict[str, Any]:
    return {"items": ACCOUNTS}


@app.get("/accounts/{account_id}")
def get_account(account_id: str, _: str = Depends(require_user)) -> dict[str, Any]:
    for account in ACCOUNTS:
        if account["id"] == account_id:
            return account
    raise HTTPException(status_code=404, detail="account not found")


@app.get("/transactions")
def list_transactions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    account_id: str | None = None,
    _: str = Depends(require_user),
) -> dict[str, Any]:
    rows = TRANSACTIONS
    if account_id:
        rows = [row for row in TRANSACTIONS if row["account_id"] == account_id]
    return paginate(list(rows), page, page_size)


@app.post("/transactions", status_code=201)
def create_transaction(body: TransactionCreate, _: str = Depends(require_user)) -> dict[str, Any]:
    with _LOCK:
        account = next((item for item in ACCOUNTS if item["id"] == body.account_id), None)
        if account is None:
            raise HTTPException(status_code=404, detail="account not found")
        if body.amount > account["balance"]:
            raise HTTPException(status_code=409, detail="insufficient funds")
        record = {
            "id": f"txn-{uuid.uuid4().hex[:8]}",
            "account_id": body.account_id,
            "amount": body.amount,
            "description": body.description,
        }
        account["balance"] = round(account["balance"] - body.amount, 2)
        TRANSACTIONS.append(record)
    return record


@app.get("/search")
def search(q: str = Query(min_length=2, max_length=40), _: str = Depends(require_user)) -> dict[str, Any]:
    needle = q.lower()
    users = [user for user in USERS if needle in user["name"].lower() or needle in user["email"].lower()]
    accounts = [account for account in ACCOUNTS if needle in account["id"].lower()]
    transactions = [
        row
        for row in TRANSACTIONS
        if needle in row["description"].lower() or needle in row["id"].lower()
    ]
    return {"users": users, "accounts": accounts, "transactions": transactions[:10]}


@app.get("/demo/fault")
def fault(status: int = Query(default=500), _: str = Depends(require_user)) -> None:
    allowed = {400, 401, 404, 409, 422, 500, 503}
    if status not in allowed:
        raise HTTPException(status_code=400, detail="unsupported fault status")
    raise HTTPException(status_code=status, detail=f"controlled demo fault {status}")
