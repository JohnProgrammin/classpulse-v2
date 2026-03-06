from app import app
from models import db

def reset_database():
    with app.app_context():
        print("[RESET] Dropping all tables...")
        db.drop_all()
        print("[RESET] Creating all tables...")
        db.create_all()
        print("[RESET] Database cleared and schema recreated successfully.")

if __name__ == "__main__":
    reset_database()
