import unittest
import os
os.environ['TESTING'] = 'true'
from app import app, db
from models import Lecturer, Course, ChatRoom

class TestLecturerRoutes(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SECRET_KEY'] = 'test-secret'
        self.client = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()
        
        # Re-initialize DB engine for the new URI
        db.init_app(app)
        db.create_all()
        
        # Seed test lecturer
        self.lecturer = Lecturer(
            phone_number="+1234567890",
            name="Professor Doe",
            email="doe@example.com"
        )
        self.lecturer.set_password("password123")
        db.session.add(self.lecturer)
        db.session.commit()

    def tearDown(self):
        db.session.rollback()
        db.drop_all()
        db.session.remove()
        self.app_context.pop()

    def test_login_success(self):
        response = self.client.post('/login', data={
            'phone': '+1234567890',
            'password': 'password123'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Welcome back', response.data)
        self.assertIn(b'Your Dashboard', response.data)

    def test_login_failure(self):
        response = self.client.post('/login', data={
            'phone': '+1234567890',
            'password': 'wrongpassword'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid phone number or password', response.data)

    def test_dashboard_with_courses(self):
        # Create course for lecturer
        course = Course(
            code="CS101",
            name="CompSci",
            semester="Fall",
            lecturer_id=self.lecturer.id
        )
        db.session.add(course)
        db.session.commit()
        
        # Create room linked to course
        room = ChatRoom(name="CS101 Room", room_type="group", course_id=course.id)
        db.session.add(room)
        db.session.commit()

        # Login
        self.client.post('/login', data={
            'phone': '+1234567890',
            'password': 'password123'
        })
        
        response = self.client.get('/dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'CS101', response.data)
        self.assertIn(b'Management', response.data)

    def test_course_detail(self):
        # Create course and room
        course = Course(code="CS101", name="CompSci", lecturer_id=self.lecturer.id)
        db.session.add(course)
        db.session.commit()
        room = ChatRoom(name="Room", course_id=course.id)
        db.session.add(room)
        db.session.commit()

        # Login
        self.client.post('/login', data={'phone': '+1234567890', 'password': 'password123'})
        
        response = self.client.get(f'/course/{course.id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'CS101', response.data)
        self.assertIn(b'Knowledge Base', response.data)

if __name__ == '__main__':
    unittest.main()
