"""
Migration script to add profile_pic and bio fields to chat_users table.
Run this once after updating the models.

Usage:
    python migrate_profile.py
"""

from app import app, db
from sqlalchemy import text


def migrate():
    """Add profile_pic and bio columns to chat_users table"""
    with app.app_context():
        for col, typedef in [('profile_pic', 'VARCHAR(255)'), ('bio', 'TEXT')]:
            try:
                # Check if column already exists (works on PostgreSQL / MySQL)
                result = db.session.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='chat_users' AND column_name=:col"
                ), {'col': col})
                if result.fetchone():
                    print(f"[OK] {col} column already exists")
                    continue

                db.session.execute(text(
                    f"ALTER TABLE chat_users ADD COLUMN {col} {typedef}"
                ))
                db.session.commit()
                print(f"[OK] Added {col} column to chat_users")

            except Exception:
                # SQLite fallback – information_schema not available
                try:
                    db.session.rollback()
                    db.session.execute(text(
                        f"ALTER TABLE chat_users ADD COLUMN {col} {typedef}"
                    ))
                    db.session.commit()
                    print(f"[OK] Added {col} column to chat_users (SQLite)")
                except Exception as e2:
                    if 'duplicate column' in str(e2).lower() or 'already exists' in str(e2).lower():
                        print(f"[OK] {col} column already exists")
                    else:
                        print(f"[ERROR] Migration failed for {col}: {e2}")


if __name__ == '__main__':
    migrate()
