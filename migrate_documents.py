"""
Migration script to create ai_documents table.
Run this once after updating the models.

Usage:
    python migrate_documents.py
"""

from app import app, db
from sqlalchemy import text


def migrate():
    """Create ai_documents table"""
    with app.app_context():
        try:
            result = db.session.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='ai_documents'"
            ))
            if result.fetchone():
                print("[OK] ai_documents table already exists")
                return

            db.session.execute(text("""
                CREATE TABLE ai_documents (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES chat_users(id),
                    filename VARCHAR(255) NOT NULL,
                    content TEXT NOT NULL,
                    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            db.session.commit()
            print("[OK] Created ai_documents table")

        except Exception as e:
            try:
                db.session.rollback()
                result = db.session.execute(text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_name='ai_documents'"
                ))
                if result.fetchone():
                    print("[OK] ai_documents table already exists")
                    return

                db.session.execute(text("""
                    CREATE TABLE ai_documents (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES chat_users(id),
                        filename VARCHAR(255) NOT NULL,
                        content TEXT NOT NULL,
                        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                db.session.commit()
                print("[OK] Created ai_documents table (PostgreSQL)")
            except Exception as e2:
                print(f"[ERROR] Migration failed: {e2}")


if __name__ == '__main__':
    migrate()
