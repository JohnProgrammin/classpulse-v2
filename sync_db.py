from app import app
from models import db

def sync_db():
    with app.app_context():
        print("[SYNC] Checking for missing tables...")
        # create_all() creates tables that don't exist
        db.create_all()
        print("[SYNC] Database schema synchronized.")

if __name__ == "__main__":
    sync_db()
