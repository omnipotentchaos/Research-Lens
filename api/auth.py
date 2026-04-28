import sqlite3
import hashlib
import secrets
from pathlib import Path

DB_PATH = Path("data/users.db")

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')

init_db()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(email: str, password: str) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", (email, hash_password(password)))
        return cur.lastrowid

def verify_user(email: str, password: str) -> int | None:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT id FROM users WHERE email = ? AND password_hash = ?", (email, hash_password(password)))
        row = cur.fetchone()
        return row[0] if row else None

def get_user_by_email(email: str) -> int | None:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT id FROM users WHERE email = ?", (email,))
        row = cur.fetchone()
        return row[0] if row else None

def create_session(user_id: int) -> str:
    token = secrets.token_hex(32)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, user_id))
    return token

def get_user_from_token(token: str) -> int | None:
    if not token:
        return None
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT user_id FROM sessions WHERE token = ?", (token,))
        row = cur.fetchone()
        return row[0] if row else None
