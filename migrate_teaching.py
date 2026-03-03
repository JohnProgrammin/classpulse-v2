"""
Migration script to create teaching_sessions table.
Run this once after updating the models.

Usage:
    python migrate_teaching.py
"""

from app import app, db
from sqlalchemy import text


def migrate():
    """Create teaching_sessions table"""
    with app.app_context():
        try:
            result = db.session.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='teaching_sessions'"
            ))
            if result.fetchone():
                print("[OK] teaching_sessions table already exists")
                return

            db.session.execute(text("""
                CREATE TABLE teaching_sessions (
                    id INTEGER PRIMARY KEY,
                    room_id INTEGER NOT NULL REFERENCES chat_rooms(id),
                    topic TEXT NOT NULL,
                    total_days INTEGER NOT NULL,
                    current_day INTEGER DEFAULT 0,
                    start_date DATETIME NOT NULL,
                    close_date DATETIME NOT NULL,
                    created_by INTEGER REFERENCES chat_users(id)
                )
            """))
            db.session.commit()
            print("[OK] Created teaching_sessions table")

        except Exception as e:
            try:
                db.session.rollback()
                result = db.session.execute(text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_name='teaching_sessions'"
                ))
                if result.fetchone():
                    print("[OK] teaching_sessions table already exists")
                    return

                db.session.execute(text("""
                    CREATE TABLE teaching_sessions (
                        id SERIAL PRIMARY KEY,
                        room_id INTEGER NOT NULL REFERENCES chat_rooms(id),
                        topic TEXT NOT NULL,
                        total_days INTEGER NOT NULL,
                        current_day INTEGER DEFAULT 0,
                        start_date TIMESTAMP NOT NULL,
                        close_date TIMESTAMP NOT NULL,
                        created_by INTEGER REFERENCES chat_users(id)
                    )
                """))
                db.session.commit()
                print("[OK] Created teaching_sessions table (PostgreSQL)")
            except Exception as e2:
                print(f"[ERROR] Migration failed: {e2}")


if __name__ == '__main__':
    migrate()
