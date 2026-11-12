"""Accounts: username + password, per-user collections. Stdlib only (scrypt hashing)."""
import os, re, time, hmac, hashlib, secrets
from .db import conn

SESSION_DAYS = 30
MAX_USERS = int(os.environ.get("MAX_USERS", "10"))
_USERNAME = re.compile(r"^[A-Za-z0-9_.-]{3,20}$")
_fails: dict[str, list[float]] = {}          # login throttling (in memory)

def hash_pw(pw: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return salt.hex() + ":" + h.hex()

def verify_pw(pw: str, stored: str) -> bool:
    salt, h = stored.split(":")
    calc = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1, dklen=32)
    return hmac.compare_digest(calc.hex(), h)

def _th(token: str) -> str: return hashlib.sha256(token.encode()).hexdigest()

def check_new(username: str, password: str):
    if not _USERNAME.match(username or ""): return "Username must be 3-20 letters, numbers, . _ or -"
    if len(password or "") < 8: return "Password must be at least 8 characters"
    return None

def create_user(username: str, password: str) -> int:
    db = conn()
    try:
        first = db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        cur = db.execute("INSERT INTO users(username,pw_hash,created) VALUES(?,?,?)", (username, hash_pw(password), time.time()))
        uid = cur.lastrowid
        if first:   # the very first account adopts any collection saved before accounts existed
            db.execute("UPDATE collection SET user_id=? WHERE user_id IS NULL", (uid,))
        db.commit(); return uid
    except Exception:
        db.rollback(); raise          # never leave a half-finished transaction (it would lock the database)
    finally:
        db.close()

def user_count() -> int: return conn().execute("SELECT COUNT(*) FROM users").fetchone()[0]

def throttled(key: str) -> bool:
    now = time.time(); _fails[key] = [t for t in _fails.get(key, []) if now - t < 900]
    return len(_fails[key]) >= 8

def note_fail(key: str): _fails.setdefault(key, []).append(time.time())

def login(username: str, password: str):
    row = conn().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    ok = verify_pw(password, row["pw_hash"]) if row else (verify_pw(password, hash_pw("x")) and False)  # equal work either way
    return row["id"] if row and ok else None

def new_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32); db = conn()
    db.execute("INSERT INTO sessions VALUES(?,?,?)", (_th(token), user_id, time.time())); db.commit(); return token

def user_for_token(token: str):
    db = conn()
    r = db.execute("SELECT u.id, u.username, s.created FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?", (_th(token),)).fetchone()
    if not r or time.time() - r["created"] > SESSION_DAYS * 86400: return None
    return {"id": r["id"], "username": r["username"]}

def end_session(token: str):
    db = conn(); db.execute("DELETE FROM sessions WHERE token_hash=?", (_th(token),)); db.commit()
