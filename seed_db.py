from app import app, db
from models import Lecturer, Course, ChatRoom
import secrets

def seed_data():
    with app.app_context():
        # Create Lecturer
        lecturer = Lecturer(
            phone_number="+1234567890",
            name="Professor John Doe",
            email="john@example.com"
        )
        lecturer.set_password("password123")
        db.session.add(lecturer)
        db.session.flush()

        # Create Course
        course = Course(
            code="CS101",
            name="Introduction to Computer Science",
            semester="Fall 2024",
            lecturer_id=lecturer.id,
            group_id="test_group_id"
        )
        db.session.add(course)
        db.session.flush()

        # Create ChatRoom linked to Course
        room = ChatRoom(
            name="CS101 - Introduction to Computer Science",
            room_type='group',
            invite_code="ABC123",
            course_id=course.id
        )
        db.session.add(room)
        
        db.session.commit()
        print(f"[OK] Seeded test data: Lecturer {lecturer.phone_number}, Password: password123")

if __name__ == "__main__":
    seed_data()
