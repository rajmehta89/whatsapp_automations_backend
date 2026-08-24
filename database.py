import sqlite3
from config import CONV_DB_PATH, MAX_MESSAGES


DEFAULT_LEAD_STAGE = "new"


def get_connection():
    return sqlite3.connect(CONV_DB_PATH)


def _ensure_lead_tasks_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lead_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            due_label TEXT,
            created_at INTEGER,
            updated_at INTEGER
        )
    """)


def init_db():
    """Initialize the SQLite database with a unique constraint."""
    # create folder if it doesn't exist

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            message_content TEXT,
            timestamp INTEGER,
            from_me BOOLEAN,
            UNIQUE(user_id, message_content, timestamp, from_me)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            user_id TEXT PRIMARY KEY,
            display_name TEXT,
            updated_at INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lead_meta (
            user_id TEXT PRIMARY KEY,
            manual_name TEXT,
            stage TEXT NOT NULL DEFAULT 'new',
            updated_at INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lead_tags (
            user_id TEXT NOT NULL,
            tag TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            updated_at INTEGER,
            PRIMARY KEY (user_id, tag)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lead_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            note TEXT NOT NULL,
            created_at INTEGER
        )
    """)
    _ensure_lead_tasks_table(cursor)
    conn.commit()
    conn.close()


def save_contact_name(user_id, display_name, updated_at):
    if not user_id or not display_name or not display_name.strip():
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO contacts (user_id, display_name, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            display_name = excluded.display_name,
            updated_at = excluded.updated_at
    """, (user_id, display_name.strip(), updated_at))
    conn.commit()
    conn.close()


def get_contact_name(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT display_name
        FROM contacts
        WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def save_message(user_id, message_content, timestamp, from_me):
    """Insert a message into the DB if it doesn't already exist."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO messages (user_id, message_content, timestamp, from_me)
            VALUES (?, ?, ?, ?)
        """, (user_id, message_content, timestamp, from_me))
        conn.commit()
    except sqlite3.IntegrityError:
        # A message with the same (user_id, message_content, timestamp, from_me) already exists
        pass
    finally:
        conn.close()

def get_messages(user_id):
    """Retrieve all messages for a particular user_id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT message_content, timestamp, from_me
        FROM messages
        WHERE user_id = ?
        ORDER BY timestamp
    """, (user_id,))
    results = cursor.fetchall()
    conn.close()
    return results

def get_recent_messages(user_id):
    """
    Retrieve the most recent `max_messages` for a particular user_id, ordered oldest to newest.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT message_content, timestamp, from_me
        FROM messages
        WHERE user_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    """, (user_id, MAX_MESSAGES))
    results = cursor.fetchall()
    conn.close()

    # Reverse the results to return them in chronological order
    return results[::-1]

def delete_messages(user_id):
    """Delete all messages for the specified user_id from the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM contacts WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM lead_meta WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM lead_tags WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM lead_notes WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM lead_tasks WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def save_lead_meta(user_id, manual_name=None, stage=None, updated_at=None):
    if not user_id:
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO lead_meta (user_id, manual_name, stage, updated_at)
        VALUES (?, ?, COALESCE(?, ?), ?)
        ON CONFLICT(user_id) DO UPDATE SET
            manual_name = COALESCE(excluded.manual_name, lead_meta.manual_name),
            stage = COALESCE(excluded.stage, lead_meta.stage),
            updated_at = excluded.updated_at
    """, (user_id, manual_name, stage, DEFAULT_LEAD_STAGE, updated_at))
    conn.commit()
    conn.close()


def get_lead_meta(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT manual_name, stage, updated_at
        FROM lead_meta
        WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {"manual_name": None, "stage": DEFAULT_LEAD_STAGE, "updated_at": None}
    return {"manual_name": row[0], "stage": row[1] or DEFAULT_LEAD_STAGE, "updated_at": row[2]}


def set_lead_stage(user_id, stage, updated_at):
    if not user_id:
        return
    existing = get_lead_meta(user_id)
    save_lead_meta(
        user_id=user_id,
        manual_name=existing.get("manual_name"),
        stage=stage or DEFAULT_LEAD_STAGE,
        updated_at=updated_at,
    )


def set_manual_lead_name(user_id, manual_name, updated_at):
    if not user_id:
        return
    existing = get_lead_meta(user_id)
    cleaned_name = (manual_name or "").strip() or None
    save_lead_meta(
        user_id=user_id,
        manual_name=cleaned_name,
        stage=existing.get("stage") or DEFAULT_LEAD_STAGE,
        updated_at=updated_at,
    )


def list_lead_tags(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT tag, source, updated_at
        FROM lead_tags
        WHERE user_id = ?
        ORDER BY tag
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {"tag": row[0], "source": row[1], "updated_at": row[2]}
        for row in rows
    ]


def upsert_lead_tag(user_id, tag, source, updated_at):
    if not user_id or not tag:
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO lead_tags (user_id, tag, source, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, tag) DO UPDATE SET
            source = excluded.source,
            updated_at = excluded.updated_at
    """, (user_id, tag, source, updated_at))
    conn.commit()
    conn.close()


def delete_lead_tag(user_id, tag):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM lead_tags WHERE user_id = ? AND tag = ?", (user_id, tag))
    conn.commit()
    conn.close()


def list_lead_notes(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, note, created_at
        FROM lead_notes
        WHERE user_id = ?
        ORDER BY created_at DESC, id DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": row[0], "note": row[1], "created_at": row[2]}
        for row in rows
    ]


def add_lead_note(user_id, note, created_at):
    if not user_id or not note or not note.strip():
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO lead_notes (user_id, note, created_at)
        VALUES (?, ?, ?)
    """, (user_id, note.strip(), created_at))
    conn.commit()
    conn.close()


def list_lead_tasks(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    _ensure_lead_tasks_table(cursor)
    cursor.execute("""
        SELECT id, title, status, due_label, created_at, updated_at
        FROM lead_tasks
        WHERE user_id = ?
        ORDER BY
            CASE WHEN status = 'open' THEN 0 ELSE 1 END,
            updated_at DESC,
            id DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": row[0],
            "title": row[1],
            "status": row[2],
            "due_label": row[3],
            "created_at": row[4],
            "updated_at": row[5],
        }
        for row in rows
    ]


def add_lead_task(user_id, title, due_label, created_at):
    if not user_id or not title or not title.strip():
        return
    conn = get_connection()
    cursor = conn.cursor()
    _ensure_lead_tasks_table(cursor)
    cursor.execute("""
        INSERT INTO lead_tasks (user_id, title, status, due_label, created_at, updated_at)
        VALUES (?, ?, 'open', ?, ?, ?)
    """, (user_id, title.strip(), (due_label or "").strip() or None, created_at, created_at))
    conn.commit()
    conn.close()


def set_lead_task_status(task_id, status, updated_at):
    conn = get_connection()
    cursor = conn.cursor()
    _ensure_lead_tasks_table(cursor)
    cursor.execute("""
        UPDATE lead_tasks
        SET status = ?, updated_at = ?
        WHERE id = ?
    """, (status, updated_at, task_id))
    conn.commit()
    conn.close()

def get_recent_messages_formatted(user_id):
    # Build a minimal text representation of the conversation
    conversation_history = get_recent_messages(user_id)
    lines = []
    for msg_content, msg_timestamp, from_me in conversation_history:
        if from_me:
            speaker = "ASSISTANT"
        else:
            speaker = "USER"
        lines.append(f"{speaker}: {msg_content}")

    conversation_text = "\n".join(lines)

    return conversation_text
