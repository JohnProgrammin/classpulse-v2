"""
Migration script to create message_reactions table.
Run this once after updating the models.

Usage:
    python migrate_reactions.py
"""

from app import app, db
from sqlalchemy import text


def migrate():
    """Create message_reactions table"""
    with app.app_context():
        try:
            # Check if table already exists
            result = db.session.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='message_reactions'"
            ))
            if result.fetchone():
                print("[OK] message_reactions table already exists")
                return

            db.session.execute(text("""
                CREATE TABLE message_reactions (
                    id INTEGER PRIMARY KEY,
                    message_id INTEGER NOT NULL REFERENCES chat_messages(id),
                    user_id INTEGER NOT NULL REFERENCES chat_users(id),
                    emoji VARCHAR(10) NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(message_id, user_id, emoji)
                )
            """))
            db.session.commit()
            print("[OK] Created message_reactions table")

        except Exception as e:
            # PostgreSQL / MySQL fallback using information_schema check
            try:
                db.session.rollback()
                result = db.session.execute(text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_name='message_reactions'"
                ))
                if result.fetchone():
                    print("[OK] message_reactions table already exists")
                    return

                db.session.execute(text("""
                    CREATE TABLE message_reactions (
                        id SERIAL PRIMARY KEY,
                        message_id INTEGER NOT NULL REFERENCES chat_messages(id),
                        user_id INTEGER NOT NULL REFERENCES chat_users(id),
                        emoji VARCHAR(10) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(message_id, user_id, emoji)
                    )
                """))
                db.session.commit()
                print("[OK] Created message_reactions table (PostgreSQL)")
            except Exception as e2:
                print(f"[ERROR] Migration failed: {e2}")


if __name__ == '__main__':
    migrate()
