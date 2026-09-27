"""Built-in accounts, for installations without a Supabase project.

A real account system, not a stand-in:

* **Passwords are never stored.** Each is run through scrypt — a deliberately
  slow, memory-hard key-derivation function — with a random 16-byte salt, and
  only the result is kept. Comparison is constant-time.
* **Tokens are signed**, HS256 with a server-held secret, and carry an expiry,
  an audience and an issuer. The backend derives the user from the signature,
  exactly as it does for Supabase tokens; nothing the client says about itself
  is trusted.
* **Guessing is throttled.** Repeated failures for one email pause further
  attempts, and a failed login never says whether the email exists.

Supabase remains the recommended production path. This exists so the product
works end to end the moment it is cloned, with nothing to provision first.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.app.config import settings

try:  # pragma: no cover - availability depends on the environment
    import jwt

    _JWT_AVAILABLE = True
except ImportError:  # pragma: no cover
    jwt = None  # type: ignore[assignment]
    _JWT_AVAILABLE = False

ISSUER = "merchantai-local"
AUDIENCE = "authenticated"

# scrypt cost. n=2**14 takes ~50 ms here: slow enough to make offline guessing
# expensive, quick enough that a sign-in does not feel it.
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64

MIN_PASSWORD = 8
MAX_PASSWORD = 128
MAX_EMAIL = 254
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# One message for every login failure. Saying "no such account" or "wrong
# password" separately would let anyone test which emails are registered.
INVALID_LOGIN = "That email and password combination did not work. Check both and try again."


class LocalAuthError(Exception):
    """An account operation that failed, with the HTTP status to return."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class LocalUser:
    id: str
    email: str
    full_name: str | None
    created_at: str


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------
_lock = threading.RLock()
_secret_cache: str | None = None


def data_dir():
    path = settings.local_data_path
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path():
    return data_dir() / "merchantai.db"


def connect() -> sqlite3.Connection:
    """Open the database, creating the schema on first use.

    A connection per call keeps this safe across the threads FastAPI runs sync
    routes on; SQLite opens in well under a millisecond.
    """
    connection = sqlite3.connect(db_path(), timeout=15, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id            TEXT PRIMARY KEY,
            email         TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            full_name     TEXT,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        );

        -- Every workspace record: merchants, uploads, analyses, reports,
        -- profiles. `owner_id` is indexed because every read is scoped by it.
        CREATE TABLE IF NOT EXISTS records (
            tbl        TEXT NOT NULL,
            id         TEXT NOT NULL,
            owner_id   TEXT NOT NULL,
            created_at TEXT NOT NULL,
            data       TEXT NOT NULL,
            PRIMARY KEY (tbl, id)
        );
        CREATE INDEX IF NOT EXISTS records_owner_idx ON records (tbl, owner_id);
        """
    )
    return connection


def reset_caches() -> None:
    """Forget the cached secret and throttle state. Used by tests."""
    global _secret_cache
    with _lock:
        _secret_cache = None
        _attempts.clear()


def signing_secret() -> str:
    """The token-signing secret: configured, or generated once and kept.

    Stored inside the data directory, which is git-ignored, so a fresh clone
    works without configuration and no secret is ever committed.
    """
    global _secret_cache
    if settings.local_auth_secret:
        return settings.local_auth_secret
    with _lock:
        if _secret_cache:
            return _secret_cache
        path = data_dir() / ".auth_secret"
        if path.exists():
            _secret_cache = path.read_text(encoding="utf-8").strip()
        if not _secret_cache:
            _secret_cache = secrets.token_urlsafe(48)
            path.write_text(_secret_cache, encoding="utf-8")
            try:
                os.chmod(path, 0o600)
            except OSError:  # pragma: no cover - not meaningful on every OS
                pass
        return _secret_cache


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------
def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_password(password: str) -> str:
    """scrypt with a random salt. The format records its own parameters."""
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=base64.b64decode(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# A real hash to compare against when the email is unknown, so a failed login
# costs the same time whether or not the account exists.
_DUMMY_HASH: str | None = None


def _dummy_hash() -> str:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
    return _DUMMY_HASH


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def normalise_email(email: str) -> str:
    value = str(email or "").strip().lower()
    if not value or len(value) > MAX_EMAIL or not _EMAIL.match(value):
        raise LocalAuthError("Enter a valid email address.", 422)
    return value


def check_password_strength(password: str) -> None:
    """Same rules the sign-up form shows, enforced again on the server."""
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        raise LocalAuthError(f"Use at least {MIN_PASSWORD} characters for your password.", 422)
    if len(password) > MAX_PASSWORD:
        raise LocalAuthError(f"Passwords are limited to {MAX_PASSWORD} characters.", 422)
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise LocalAuthError("Your password needs at least one letter and one number.", 422)


# --------------------------------------------------------------------------
# Throttling
# --------------------------------------------------------------------------
_attempts: dict[str, list[float]] = {}


def _throttle_check(email: str) -> None:
    window = settings.login_attempt_window_seconds
    cutoff = time.time() - window
    with _lock:
        recent = [t for t in _attempts.get(email, []) if t > cutoff]
        _attempts[email] = recent
        if len(recent) >= settings.login_attempt_limit:
            wait = int(recent[0] + window - time.time()) + 1
            minutes = max(1, round(wait / 60))
            raise LocalAuthError(
                f"Too many attempts for this account. Try again in about {minutes} minute(s).",
                429,
            )


def _throttle_fail(email: str) -> None:
    with _lock:
        _attempts.setdefault(email, []).append(time.time())


def _throttle_clear(email: str) -> None:
    with _lock:
        _attempts.pop(email, None)


# --------------------------------------------------------------------------
# Accounts
# --------------------------------------------------------------------------
def _row_to_user(row: sqlite3.Row) -> LocalUser:
    return LocalUser(
        id=row["id"],
        email=row["email"],
        full_name=row["full_name"],
        created_at=row["created_at"],
    )


def find_user_by_email(email: str) -> LocalUser | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE email = ?", (normalise_email(email),)
        ).fetchone()
    return _row_to_user(row) if row else None


def get_user(user_id: str) -> LocalUser | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_user(row) if row else None


def create_user(
    email: str,
    password: str,
    full_name: str | None = None,
    *,
    user_id: str | None = None,
) -> LocalUser:
    """Register an account and create its profile in one step.

    The profile is written here, the way the Supabase sign-up trigger does it,
    so the app never meets an account without one.
    """
    address = normalise_email(email)
    check_password_strength(password)
    name = (full_name or "").strip()[:120] or None

    new_id = user_id or str(uuid.uuid4())
    now = _now()
    password_hash = hash_password(password)

    with _lock, connect() as connection:
        exists = connection.execute(
            "SELECT 1 FROM users WHERE email = ?", (address,)
        ).fetchone()
        if exists:
            raise LocalAuthError(
                "An account already exists for that email. Try signing in instead.", 409
            )
        connection.execute(
            "INSERT INTO users (id, email, password_hash, full_name, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (new_id, address, password_hash, name, now, now),
        )
        import json

        connection.execute(
            "INSERT OR IGNORE INTO records (tbl, id, owner_id, created_at, data) "
            "VALUES ('profiles', ?, ?, ?, ?)",
            (
                new_id,
                new_id,
                now,
                json.dumps(
                    {"id": new_id, "full_name": name, "created_at": now, "updated_at": now}
                ),
            ),
        )

    return LocalUser(id=new_id, email=address, full_name=name, created_at=now)


def authenticate(email: str, password: str) -> LocalUser:
    """Check a password. Every failure produces the same message."""
    try:
        address = normalise_email(email)
    except LocalAuthError:
        raise LocalAuthError(INVALID_LOGIN, 401) from None

    _throttle_check(address)

    with connect() as connection:
        row = connection.execute("SELECT * FROM users WHERE email = ?", (address,)).fetchone()

    if row is None:
        # Spend the same effort as a real check before answering.
        verify_password(password or "", _dummy_hash())
        _throttle_fail(address)
        raise LocalAuthError(INVALID_LOGIN, 401)

    if not verify_password(password or "", row["password_hash"]):
        _throttle_fail(address)
        raise LocalAuthError(INVALID_LOGIN, 401)

    _throttle_clear(address)
    return _row_to_user(row)


def change_password(user_id: str, new_password: str) -> None:
    check_password_strength(new_password)
    with _lock, connect() as connection:
        updated = connection.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (hash_password(new_password), _now(), user_id),
        ).rowcount
    if not updated:
        raise LocalAuthError("Account not found.", 404)


def set_password(email: str, new_password: str) -> None:
    """Administrative reset, used by scripts/reset_password.py."""
    user = find_user_by_email(email)
    if user is None:
        raise LocalAuthError("No account exists for that email.", 404)
    change_password(user.id, new_password)
    _throttle_clear(user.email)


def delete_user(user_id: str) -> None:
    """Remove an account and every record it owns."""
    with _lock, connect() as connection:
        connection.execute("DELETE FROM records WHERE owner_id = ?", (user_id,))
        connection.execute("DELETE FROM users WHERE id = ?", (user_id,))


# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------
def issue_token(user: LocalUser) -> dict:
    """A signed access token plus the fields the browser keeps with it."""
    if not _JWT_AVAILABLE:
        raise LocalAuthError("PyJWT is not installed, so tokens cannot be issued.", 503)

    issued = int(time.time())
    expires = issued + settings.local_token_ttl_hours * 3600
    token = jwt.encode(
        {
            "sub": user.id,
            "email": user.email,
            "role": "authenticated",
            "aud": AUDIENCE,
            "iss": ISSUER,
            "iat": issued,
            "exp": expires,
        },
        signing_secret(),
        algorithm="HS256",
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires,
        "user": {
            "id": user.id,
            "email": user.email,
            "user_metadata": {"full_name": user.full_name},
        },
    }


def verify_local_token(token: str) -> dict:
    """Return the claims of a valid built-in token, or raise.

    Beyond the signature and expiry, the account must still exist: a token for
    a deleted account stops working at once rather than at expiry.
    """
    if not _JWT_AVAILABLE:
        raise LocalAuthError("PyJWT is not installed, so tokens cannot be verified.", 503)

    try:
        claims = jwt.decode(
            token,
            signing_secret(),
            algorithms=["HS256"],
            audience=AUDIENCE,
            issuer=ISSUER,
            options={"require": ["exp", "sub", "iss", "aud"]},
        )
    except Exception as exc:  # noqa: BLE001 - every decode failure means "not valid"
        raise LocalAuthError("Invalid or expired access token.", 401) from exc

    if get_user(str(claims["sub"])) is None:
        raise LocalAuthError("This account no longer exists.", 401)
    return claims


# --------------------------------------------------------------------------
# Signed file links
# --------------------------------------------------------------------------
def sign_file_reference(bucket: str, path: str, expires_in: int) -> str:
    """A short-lived, tamper-evident reference to one stored object.

    The equivalent of a Supabase signed URL. It is minted only after the caller's
    ownership of the object has been confirmed, and it names exactly one file.
    """
    import json

    payload = json.dumps(
        {"b": bucket, "p": path, "e": int(time.time()) + int(expires_in)},
        separators=(",", ":"),
    ).encode()
    body = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    signature = hmac.new(signing_secret().encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def read_file_reference(reference: str) -> tuple[str, str]:
    """Validate a signed reference and return (bucket, path)."""
    import json

    try:
        body, signature = reference.rsplit(".", 1)
    except ValueError as exc:
        raise LocalAuthError("This download link is not valid.", 403) from exc

    expected = hmac.new(signing_secret().encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise LocalAuthError("This download link is not valid.", 403)

    try:
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, TypeError) as exc:
        raise LocalAuthError("This download link is not valid.", 403) from exc

    if int(payload.get("e", 0)) < time.time():
        raise LocalAuthError("This download link has expired. Request a new one.", 403)

    return str(payload["b"]), str(payload["p"])
