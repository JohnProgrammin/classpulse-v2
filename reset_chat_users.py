"""
reset_chat_users.py
-------------------
Clears ALL ChatUser accounts and all related web-chat data from the DB.
Preserves: Lecturers, Courses, FAQs, Messages (WhatsApp side).
"""

from app import app, db
from models import (
    ChatUser, ChatRoom, ChatMember, ChatMessage,
    MessageReaction, AIDocument, TeachingSession
)

with app.app_context():
    print("[*] Starting database reset for web-chat users...")

    # Order matters: delete children before parents to avoid FK violations
    deleted_reactions   = MessageReaction.query.delete()
    deleted_teaching    = TeachingSession.query.delete()
    deleted_messages    = ChatMessage.query.delete()
    deleted_members     = ChatMember.query.delete()
    deleted_rooms       = ChatRoom.query.delete()
    deleted_documents   = AIDocument.query.delete()
    deleted_users       = ChatUser.query.delete()

    db.session.commit()

    print(f"[OK] Deleted {deleted_users} users")
    print(f"[OK] Deleted {deleted_rooms} chat rooms")
    print(f"[OK] Deleted {deleted_members} room memberships")
    print(f"[OK] Deleted {deleted_messages} chat messages")
    print(f"[OK] Deleted {deleted_reactions} message reactions")
    print(f"[OK] Deleted {deleted_documents} AI documents")
    print(f"[OK] Deleted {deleted_teaching} teaching sessions")
    print()
    print("[DONE] Database is clean. You can now register a fresh admin account.")
