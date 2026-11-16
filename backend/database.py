
import sqlite3
from pathlib import Path


# Ruta de la base de datos
DATABASE = Path(__file__).resolve().parent / "database.db"


def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    connection = get_db_connection()

    try:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id)
                    REFERENCES conversations (id)
                    ON DELETE CASCADE
            )
        """)

        connection.commit()

    finally:
        connection.close()


def create_conversation():
    connection = get_db_connection()

    try:
        cursor = connection.execute(
            "INSERT INTO conversations (title) VALUES (?)",
            ("New conversation",)
        )

        connection.commit()
        return cursor.lastrowid

    finally:
        connection.close()


def save_message(conversation_id: int, role: str, content: str):
    connection = get_db_connection()

    try:
        connection.execute(
            """
            INSERT INTO messages (conversation_id, role, content)
            VALUES (?, ?, ?)
            """,
            (conversation_id, role, content)
        )

        connection.commit()

    finally:
        connection.close()


def get_conversations():
    connection = get_db_connection()

    try:
        cursor = connection.execute("""
            SELECT id, title, created_at, updated_at
            FROM conversations
            ORDER BY updated_at DESC, id DESC
        """)

        return [dict(row) for row in cursor.fetchall()]

    finally:
        connection.close()


def update_conversation_title(conversation_id: int, title: str):
    connection = get_db_connection()

    try:
        connection.execute(
            """
            UPDATE conversations
            SET title = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (title, conversation_id)
        )

        connection.commit()

    finally:
        connection.close()


def get_messages(conversation_id: int):
    connection = get_db_connection()

    try:
        cursor = connection.execute(
            """
            SELECT id, role, content, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,)
        )

        return [dict(row) for row in cursor.fetchall()]

    finally:
        connection.close()
