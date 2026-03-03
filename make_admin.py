"""
Utility script to make a chat user an admin.
Run this after creating your first account to grant admin privileges.

Usage:
    python make_admin.py <username>

Example:
    python make_admin.py admin
"""

import sys
from app import app, db
from models import ChatUser


def make_admin(username):
    """Make a user an admin"""
    with app.app_context():
        user = ChatUser.query.filter_by(username=username).first()

        if not user:
            print(f"Error: User '{username}' not found.")
            print("\nExisting users:")
            users = ChatUser.query.all()
            if users:
                for u in users:
                    print(f"  - {u.username} ({u.email}) - Role: {u.role}")
            else:
                print("  No users registered yet. Register at /chat/register first.")
            return False

        if user.role == 'admin':
            print(f"User '{username}' is already an admin.")
            return True

        user.role = 'admin'
        db.session.commit()
        print(f"Success! User '{username}' is now an admin.")
        print(f"\nAdmin capabilities:")
        print(f"  - Create group chats")
        print(f"  - Chat with AI assistant")
        print(f"  - Broadcast to groups")
        return True


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python make_admin.py <username>")
        print("\nThis script grants admin privileges to a chat user.")
        print("The admin can create groups and chat with the AI.")
        sys.exit(1)

    username = sys.argv[1]
    make_admin(username)
