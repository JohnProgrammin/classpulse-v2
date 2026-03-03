"""
Migration script to add reply_to_id field to chat_messages table.
Run this once after updating the models.

Usage:
    python migrate_chat.py
"""

from app import app, db
from sqlalchemy import text

def migrate():
    """Add reply_to_id column to chat_messages table"""
    with app.app_context():
        try:
            # Check if column already exists
            result = db.session.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='chat_messages' AND column_name='reply_to_id'"
            ))
            if result.fetchone():
                print("[OK] reply_to_id column already exists")
                return

            # Add the column
            db.session.execute(text(
                "ALTER TABLE chat_messages ADD COLUMN reply_to_id INTEGER "
                "REFERENCES chat_messages(id)"
            ))
            db.session.commit()
            print("[OK] Added reply_to_id column to chat_messages table")

        except Exception as e:
            # SQLite fallback - different syntax
            try:
                db.session.rollback()
                db.session.execute(text(
                    "ALTER TABLE chat_messages ADD COLUMN reply_to_id INTEGER"
                ))
                db.session.commit()
                print("[OK] Added reply_to_id column to chat_messages table (SQLite)")
            except Exception as e2:
                if 'duplicate column' in str(e2).lower() or 'already exists' in str(e2).lower():
                    print("[OK] reply_to_id column already exists")
                else:
                    print(f"[ERROR] Migration failed: {e2}")
                    print("[INFO] You may need to recreate the database or manually add the column")

if __name__ == '__main__':
    migrate()
