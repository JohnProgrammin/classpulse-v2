from app import app
from models import db, Lecturer, ChatUser

def check_counts():
    with app.app_context():
        print(f"Lecturers: {Lecturer.query.count()}")
        print(f"ChatUsers (Students): {ChatUser.query.count()}")
        
        if Lecturer.query.count() > 0:
            print("First few lecturers:")
            for l in Lecturer.query.limit(5).all():
                print(f"- {l.name} ({l.phone_number})")

if __name__ == "__main__":
    check_counts()
