"""SQLite application database with salted PBKDF2 password hashing."""
import os
import sqlite3
import secrets
import hashlib
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv('FRAGMENTFUSION_DB', str(BASE / 'data' / 'fragmentfusion.sqlite3')))

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, role TEXT, password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS analyses(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, filename TEXT NOT NULL, kind TEXT NOT NULL, percentage REAL NOT NULL, word_count INTEGER NOT NULL, sentence_count INTEGER NOT NULL, flagged_count INTEGER NOT NULL, sources INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, details TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS saved_papers(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, title TEXT NOT NULL, authors TEXT, year TEXT, doi TEXT, url TEXT, UNIQUE(user_id,doi));
        ''')

def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 260000)
    return salt + ':' + dk.hex()

def verify(password, stored):
    try:
        salt, target = stored.split(':', 1)
        return secrets.compare_digest(hash_password(password, salt), stored)
    except (ValueError, AttributeError):
        return False

def register(name, email, password, role):
    email = email.strip().lower()
    with connect() as db:
        cur = db.execute('INSERT INTO users(name,email,role,password_hash) VALUES(?,?,?,?)', (name.strip(),email,role,hash_password(password)))
        return cur.lastrowid

def login(email, password):
    with connect() as db:
        user = db.execute('SELECT * FROM users WHERE email=?', (email.strip().lower(),)).fetchone()
        return dict(user) if user and verify(password, user['password_hash']) else None

def add_analysis(user_id, filename, kind, percentage, word_count, sentence_count, flagged_count, sources, details):
    with connect() as db:
        db.execute('INSERT INTO analyses(user_id,filename,kind,percentage,word_count,sentence_count,flagged_count,sources,created_at,details) VALUES(?,?,?,?,?,?,?,?,?,?)',
                   (user_id,filename,kind,percentage,word_count,sentence_count,flagged_count,sources,datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),details))

def history(user_id, limit=100):
    with connect() as db:
        return [dict(x) for x in db.execute('SELECT * FROM analyses WHERE user_id=? ORDER BY id DESC LIMIT ?', (user_id,limit)).fetchall()]

def save_paper(user_id, paper):
    with connect() as db:
        db.execute('INSERT OR IGNORE INTO saved_papers(user_id,title,authors,year,doi,url) VALUES(?,?,?,?,?,?)', (user_id,paper['title'],paper['authors'],str(paper['year']),paper['doi'],paper['url']))

def papers(user_id):
    with connect() as db:
        return [dict(x) for x in db.execute('SELECT * FROM saved_papers WHERE user_id=? ORDER BY id DESC', (user_id,)).fetchall()]
