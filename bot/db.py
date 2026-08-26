import json

import aiosqlite

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  tg_id INTEGER PRIMARY KEY,
  username TEXT,
  balance INTEGER DEFAULT 0,
  free_runs INTEGER DEFAULT 0,
  referred_by INTEGER,
  ref_done INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS ideas(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tg_id INTEGER,
  title TEXT,
  raw TEXT,
  mode TEXT DEFAULT 'full',
  profile TEXT DEFAULT 'online',
  idx INTEGER DEFAULT 0,
  status TEXT DEFAULT 'active',
  verdict TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS steps(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  idea_id INTEGER,
  step_key TEXT,
  num INTEGER,
  content TEXT,
  sources TEXT,
  regens INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now')),
  UNIQUE(idea_id, step_key)
);
CREATE TABLE IF NOT EXISTS questions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  idea_id INTEGER,
  step_key TEXT,
  text TEXT,
  options TEXT,
  answer TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tg_id INTEGER,
  username TEXT,
  idea_id INTEGER,
  product TEXT,
  amount INTEGER,
  status TEXT DEFAULT 'new',
  note TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  paid_at TEXT
);
CREATE TABLE IF NOT EXISTS tx(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tg_id INTEGER,
  kind TEXT,
  amount INTEGER,
  note TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
"""


MIGRATIONS = [
    ("ideas", "profile", "ALTER TABLE ideas ADD COLUMN profile TEXT DEFAULT 'online'"),
]


async def init():
    async with aiosqlite.connect(DB_PATH) as d:
        await d.executescript(SCHEMA)
        for table, column, sql in MIGRATIONS:
            cur = await d.execute(f"PRAGMA table_info({table})")
            if column not in [r[1] for r in await cur.fetchall()]:
                await d.execute(sql)
        await d.commit()


def _row(r):
    return dict(r) if r else None


# ---------------- users ----------------
async def ensure_user(tg_id, username=None, referred_by=None, free_runs=0):
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        cur = await d.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,))
        row = await cur.fetchone()
        if row:
            if username and row["username"] != username:
                await d.execute("UPDATE users SET username=? WHERE tg_id=?", (username, tg_id))
                await d.commit()
            return _row(row)
        ref = referred_by if referred_by and referred_by != tg_id else None
        await d.execute(
            "INSERT INTO users(tg_id, username, free_runs, referred_by) VALUES(?,?,?,?)",
            (tg_id, username, free_runs, ref))
        await d.commit()
        cur = await d.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,))
        return _row(await cur.fetchone())


async def get_user(tg_id):
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        cur = await d.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,))
        return _row(await cur.fetchone())


async def add_balance(tg_id, n, kind, note=""):
    async with aiosqlite.connect(DB_PATH) as d:
        await d.execute("UPDATE users SET balance=balance+? WHERE tg_id=?", (n, tg_id))
        await d.execute("INSERT INTO tx(tg_id, kind, amount, note) VALUES(?,?,?,?)",
                        (tg_id, kind, n, note))
        await d.commit()


async def add_free_runs(tg_id, n):
    async with aiosqlite.connect(DB_PATH) as d:
        await d.execute("UPDATE users SET free_runs=MAX(0, free_runs+?) WHERE tg_id=?", (n, tg_id))
        await d.commit()


async def add_tx(tg_id, kind, amount, note=""):
    async with aiosqlite.connect(DB_PATH) as d:
        await d.execute("INSERT INTO tx(tg_id, kind, amount, note) VALUES(?,?,?,?)",
                        (tg_id, kind, amount, note))
        await d.commit()


async def qualify_referral(tg_id):
    """Marks the referral as earned and returns the referrer once, or None."""
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        cur = await d.execute("SELECT referred_by, ref_done FROM users WHERE tg_id=?", (tg_id,))
        row = await cur.fetchone()
        if not row or not row["referred_by"] or row["ref_done"]:
            return None
        await d.execute("UPDATE users SET ref_done=1 WHERE tg_id=?", (tg_id,))
        await d.commit()
        return row["referred_by"]


# ---------------- ideas ----------------
async def create_idea(tg_id, title, raw, mode, profile="online"):
    async with aiosqlite.connect(DB_PATH) as d:
        cur = await d.execute(
            "INSERT INTO ideas(tg_id, title, raw, mode, profile) VALUES(?,?,?,?,?)",
            (tg_id, title, raw, mode, profile))
        await d.commit()
        return cur.lastrowid


async def get_idea(idea_id):
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        cur = await d.execute("SELECT * FROM ideas WHERE id=?", (idea_id,))
        return _row(await cur.fetchone())


async def list_ideas(tg_id, limit=20):
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        cur = await d.execute(
            "SELECT * FROM ideas WHERE tg_id=? ORDER BY updated_at DESC LIMIT ?", (tg_id, limit))
        return [dict(r) for r in await cur.fetchall()]


async def update_idea(idea_id, **fields):
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    async with aiosqlite.connect(DB_PATH) as d:
        await d.execute(f"UPDATE ideas SET {sets}, updated_at=datetime('now') WHERE id=?",
                        (*fields.values(), idea_id))
        await d.commit()


async def count_ideas(tg_id):
    async with aiosqlite.connect(DB_PATH) as d:
        cur = await d.execute("SELECT COUNT(*) FROM ideas WHERE tg_id=?", (tg_id,))
        return (await cur.fetchone())[0]


# ---------------- steps ----------------
async def save_step(idea_id, key, num, content, sources=None):
    async with aiosqlite.connect(DB_PATH) as d:
        await d.execute(
            """INSERT INTO steps(idea_id, step_key, num, content, sources) VALUES(?,?,?,?,?)
               ON CONFLICT(idea_id, step_key) DO UPDATE SET
                 content=excluded.content, sources=excluded.sources, regens=regens+1""",
            (idea_id, key, num, content, json.dumps(sources or [], ensure_ascii=False)))
        await d.commit()


async def get_steps(idea_id):
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        cur = await d.execute("SELECT * FROM steps WHERE idea_id=? ORDER BY num", (idea_id,))
        out = []
        for r in await cur.fetchall():
            row = dict(r)
            row["sources"] = json.loads(row["sources"] or "[]")
            out.append(row)
        return out


async def get_step(idea_id, key):
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        cur = await d.execute("SELECT * FROM steps WHERE idea_id=? AND step_key=?", (idea_id, key))
        row = await cur.fetchone()
        if not row:
            return None
        out = dict(row)
        out["sources"] = json.loads(out["sources"] or "[]")
        return out


async def delete_idea(idea_id):
    async with aiosqlite.connect(DB_PATH) as d:
        await d.execute("DELETE FROM steps WHERE idea_id=?", (idea_id,))
        await d.execute("DELETE FROM questions WHERE idea_id=?", (idea_id,))
        await d.execute("DELETE FROM ideas WHERE id=?", (idea_id,))
        await d.commit()


# ---------------- orders (settled by hand) ----------------
async def create_order(tg_id, username, idea_id, product, amount):
    """Reuses an open order for the same idea so double taps don't pile up invoices."""
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        cur = await d.execute(
            """SELECT * FROM orders WHERE tg_id=? AND idea_id=? AND product=?
               AND status IN ('new','claimed') ORDER BY id DESC LIMIT 1""",
            (tg_id, idea_id, product))
        row = await cur.fetchone()
        if row:
            return dict(row)
        cur = await d.execute(
            """INSERT INTO orders(tg_id, username, idea_id, product, amount)
               VALUES(?,?,?,?,?)""", (tg_id, username, idea_id, product, amount))
        await d.commit()
        cur = await d.execute("SELECT * FROM orders WHERE id=?", (cur.lastrowid,))
        return dict(await cur.fetchone())


async def get_order(order_id):
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        cur = await d.execute("SELECT * FROM orders WHERE id=?", (order_id,))
        return _row(await cur.fetchone())


async def set_order_status(order_id, status, note=None):
    paid = ", paid_at=datetime('now')" if status == "paid" else ""
    async with aiosqlite.connect(DB_PATH) as d:
        await d.execute(f"UPDATE orders SET status=?, note=COALESCE(?, note){paid} WHERE id=?",
                        (status, note, order_id))
        await d.commit()


async def list_orders(status=None, limit=15):
    q = "SELECT * FROM orders"
    args = []
    if status:
        q += " WHERE status=?"
        args.append(status)
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        cur = await d.execute(q + " ORDER BY id DESC LIMIT ?", (*args, limit))
        return [dict(r) for r in await cur.fetchall()]


async def has_paid(tg_id, idea_id, product):
    async with aiosqlite.connect(DB_PATH) as d:
        cur = await d.execute(
            "SELECT 1 FROM orders WHERE tg_id=? AND idea_id=? AND product=? AND status='paid'",
            (tg_id, idea_id, product))
        return (await cur.fetchone()) is not None


# ---------------- micro-survey ----------------
async def save_questions(idea_id, step_key, items):
    """items: [{'q': str, 'options': [str]}]. Returns nothing; ids come from get_questions."""
    async with aiosqlite.connect(DB_PATH) as d:
        for it in items:
            await d.execute(
                "INSERT INTO questions(idea_id, step_key, text, options) VALUES(?,?,?,?)",
                (idea_id, step_key, it["q"], json.dumps(it.get("options") or [],
                                                        ensure_ascii=False)))
        await d.commit()


async def get_questions(idea_id, step_key=None):
    q = "SELECT * FROM questions WHERE idea_id=?"
    args = [idea_id]
    if step_key:
        q += " AND step_key=?"
        args.append(step_key)
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        cur = await d.execute(q + " ORDER BY id", args)
        out = []
        for r in await cur.fetchall():
            row = dict(r)
            row["options"] = json.loads(row["options"] or "[]")
            out.append(row)
        return out


async def get_question(qid):
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        cur = await d.execute("SELECT * FROM questions WHERE id=?", (qid,))
        row = await cur.fetchone()
        if not row:
            return None
        out = dict(row)
        out["options"] = json.loads(out["options"] or "[]")
        return out


async def set_answer(qid, answer):
    async with aiosqlite.connect(DB_PATH) as d:
        await d.execute("UPDATE questions SET answer=? WHERE id=?", (answer, qid))
        await d.commit()


async def skip_rest(idea_id, step_key):
    async with aiosqlite.connect(DB_PATH) as d:
        await d.execute(
            "UPDATE questions SET answer='' WHERE idea_id=? AND step_key=? AND answer IS NULL",
            (idea_id, step_key))
        await d.commit()
