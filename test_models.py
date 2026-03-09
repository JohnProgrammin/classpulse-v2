import os
os.environ['TESTING'] = 'true'
import unittest
from app import app, db
from models import Lecturer, ChatUser, Course, FAQ

class TestModels(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app_context = app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_lecturer_password_hashing(self):
        lecturer = Lecturer(name="Test Lecturer", phone_number="+1234567890")
        lecturer.set_password("password123")
        self.assertTrue(lecturer.check_password("password123"))
        self.assertFalse(lecturer.check_password("wrongpassword"))
        self.assertNotEqual(lecturer.password_hash, "password123")

    def test_chatuser_password_hashing(self):
        user = ChatUser(username="testuser", email="test@example.com")
        user.set_password("securepassword")
        self.assertTrue(user.check_password("securepassword"))
        self.assertFalse(user.check_password("wrongpassword"))
        self.assertNotEqual(user.password_hash, "securepassword")

    def test_chatuser_roles(self):
        admin = ChatUser(username="admin", email="admin@example.com", role="admin")
        lecturer = ChatUser(username="lecturer", email="lecturer@example.com", role="lecturer")
        student = ChatUser(username="student", email="student@example.com", role="user")
        
        self.assertTrue(admin.is_admin())
        self.assertTrue(admin.is_lecturer())
        self.assertTrue(admin.is_staff())
        
        self.assertFalse(lecturer.is_admin())
        self.assertTrue(lecturer.is_lecturer())
        
        self.assertFalse(student.is_admin())
        self.assertFalse(student.is_lecturer())

    def test_course_creation(self):
        lecturer = ChatUser(username="profsnape", email="snape@hogwarts.edu", role="lecturer")
        lecturer.set_password("password123")
        db.session.add(lecturer)
        db.session.commit()
        
        course = Course(code="POT101", name="Potions", lecturer_id=lecturer.id)
        db.session.add(course)
        db.session.commit()
        
        self.assertEqual(course.code, "POT101")
        self.assertEqual(course.lecturer_id, lecturer.id)

    def test_faq_relationship(self):
        lecturer = ChatUser(username="profsnape", email="snape@hogwarts.edu", role="lecturer")
        lecturer.set_password("password123")
        db.session.add(lecturer)
        db.session.commit()
        
        course = Course(code="POT101", name="Potions", lecturer_id=lecturer.id)
        db.session.add(course)
        db.session.commit()
        
        faq = FAQ(question="What is this?", answer="A test.", course_id=course.id)
        db.session.add(faq)
        db.session.commit()
        
        self.assertEqual(len(course.faqs), 1)
        self.assertEqual(course.faqs[0].question, "What is this?")

if __name__ == '__main__':
    unittest.main()
