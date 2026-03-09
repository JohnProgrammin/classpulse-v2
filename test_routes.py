import os
os.environ['TESTING'] = 'true'
import unittest
from app import app, db
from models import ChatUser, ChatRoom, ChatMember
import json

class TestRoutes(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['DEBUG'] = False
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SECRET_KEY'] = 'test-secret-key'
        self.client = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_chat_login_get(self):
        response = self.client.get('/chat/login')
        self.assertEqual(response.status_code, 200)
        # Check for 'Sign in' or 'Login' depending on templates
        self.assertIn(b'Sign In', response.data)

    def test_chat_register_post(self):
        data = {
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'password123',
            'display_name': 'New User'
        }
        response = self.client.post('/chat/register', data=data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Account created!', response.data)
        
        user = ChatUser.query.filter_by(username='newuser').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.email, 'new@example.com')

    def test_chat_login_post(self):
        # Register first
        user = ChatUser(username='loginuser', email='login@example.com')
        user.set_password('pass123')
        db.session.add(user)
        db.session.commit()
        
        data = {
            'username': 'loginuser',
            'password': 'pass123'
        }
        response = self.client.post('/chat/login', data=data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Logged in successfully!', response.data)

    def test_api_rooms_unauthenticated(self):
        response = self.client.get('/api/chat/rooms')
        self.assertEqual(response.status_code, 401)

    def test_api_rooms_authenticated(self):
        # Register and login
        user = ChatUser(username='roomuser', email='room@example.com')
        user.set_password('pass123')
        db.session.add(user)
        db.session.commit()
        
        with self.client.session_transaction() as sess:
            sess['chat_user_id'] = user.id
            sess['chat_username'] = user.username
            sess['chat_role'] = user.role
            
        # Create a room
        room = ChatRoom(name="Test Room", room_type="group")
        db.session.add(room)
        db.session.commit()
        
        member = ChatMember(room_id=room.id, user_id=user.id)
        db.session.add(member)
        db.session.commit()
        
        response = self.client.get('/api/chat/rooms')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data['rooms']), 1)
        self.assertEqual(data['rooms'][0]['name'], 'Test Room')

    def test_404_handler(self):
        response = self.client.get('/non-existent-page')
        self.assertEqual(response.status_code, 404)

if __name__ == '__main__':
    unittest.main()
