"""
Migration script to add locked column to chat_rooms table.
Run this once after updating the models.

Usage:
    python migrate_lock.py
"""

from app import app, db
from sqlalchemy import text


def migrate():
    """Add locked column to chat_rooms table"""
    with app.app_context():
        for col, typedef, default in [('locked', 'BOOLEAN', 'DEFAULT 0')]:
            try:
                result = db.session.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='chat_rooms' AND column_name=:col"
                ), {'col': col})
                if result.fetchone():
                    print(f"[OK] {col} column already exists")
                    continue

                db.session.execute(text(
                    f"ALTER TABLE chat_rooms ADD COLUMN {col} {typedef} {default}"
                ))
                db.session.commit()
                print(f"[OK] Added {col} column to chat_rooms")

            except Exception:
                # SQLite fallback
                try:
                    db.session.rollback()
                    db.session.execute(text(
                        f"ALTER TABLE chat_rooms ADD COLUMN {col} {typedef} {default}"
                    ))
                    db.session.commit()
                    print(f"[OK] Added {col} column to chat_rooms (SQLite)")
                except Exception as e2:
                    if 'duplicate column' in str(e2).lower() or 'already exists' in str(e2).lower():
                        print(f"[OK] {col} column already exists")
                    else:
                        print(f"[ERROR] Migration failed for {col}: {e2}")


if __name__ == '__main__':
    migrate()
