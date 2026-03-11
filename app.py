

from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, session, make_response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO
from apscheduler.schedulers.background import BackgroundScheduler
from config import Config
from models import (
    db, Lecturer, Course, FAQ, PendingQuestion, ScheduledMessage, Message, Analytics,
    ChatUser, ChatRoom, ChatMember, ChatMessage
)
from chat_handler import register_socket_events, process_teaching_sessions
from datetime import datetime, timedelta
import os
import secrets
from sqlalchemy import func

# ==========================================
# 1. APP INITIALIZATION
# ==========================================
app = Flask(__name__)
app.config.from_object(Config)

# Initialize extensions
db.init_app(app)
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, AnonymousUserMixin

# ... inside app initialization ...
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'chat_login'

class AnonymousUser(AnonymousUserMixin):
    def is_lecturer(self): return False
    def is_student(self): return False
    def is_admin(self): return False

login_manager.anonymous_user = AnonymousUser

# Initialize Socket.IO for real-time chat with explicit threading mode for Python 3.13 compatibility
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Create database tables
if not os.environ.get('TESTING'):
    with app.app_context():
        db.create_all()
        print("[OK] Database initialized")

# Register Socket.IO events for chat
register_socket_events(socketio)
print("[OK] Chat WebSocket events registered")

# Initialize scheduler for teaching sessions
def scheduled_job_with_context():
    """Wrapper to run scheduled jobs with Flask app context"""
    with app.app_context():
        process_teaching_sessions()

if not os.environ.get('TESTING'):
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=scheduled_job_with_context,
        trigger="interval",
        seconds=60
    )
    scheduler.start()
    print("[OK] Scheduler started")
else:
    print("[INFO] Testing mode detected: Scheduler disabled")


# ==========================================
# 2. AUTHENTICATION (Lecturer Dashboard)
# ==========================================
@login_manager.user_loader
def load_user(user_id):
    return Lecturer.query.get(int(user_id))


# ==========================================
# 3. MAIN REDIRECT
# ==========================================
@app.route('/')
def index():
    """Landing page - Medium style"""
    return render_template('index.html')

@app.route('/get-started')
def auth_choice():
    """Choice page for Lecturers vs Students"""
    return render_template('auth_choice.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Lecturer login page"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        
        # Match Lecturer by phone number OR email
        lecturer = Lecturer.query.filter((Lecturer.phone_number == phone) | (Lecturer.email == phone)).first()

        if lecturer and (not lecturer.password_hash or lecturer.check_password(password)):
            login_user(lecturer)
            lecturer.last_login = datetime.utcnow()
            db.session.commit()
            flash('Welcome back, Professor!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid phone number/email or password.', 'error')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    """Logout current lecturer"""
    logout_user()
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Educator registration page"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not name or not phone or not password:
            flash('Name, phone, and password are required', 'error')
            return render_template('register.html')

        if Lecturer.query.filter_by(phone_number=phone).first():
            flash('Phone number already registered', 'error')
            return render_template('register.html')

        if email and Lecturer.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return render_template('register.html')

        new_lecturer = Lecturer(
            name=name,
            phone_number=phone,
            email=email if email else None
        )
        new_lecturer.set_password(password)
        db.session.add(new_lecturer)
        db.session.commit()

        flash('Educator account created! Please sign in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/dashboard')
@login_required
def dashboard():
    """Lecturer dashboard overview"""
    courses = Course.query.filter_by(lecturer_id=current_user.id, is_active=True).all()
    
    # Calculate some stats for the dashboard
    stats = {
        'active_courses': len(courses),
        'total_messages': Message.query.filter(Message.course_id.in_([c.id for c in courses])).count() if courses else 0,
        'pending_questions': PendingQuestion.query.filter(
            PendingQuestion.course_id.in_([c.id for c in courses]),
            PendingQuestion.status == 'pending'
        ).count() if courses else 0
    }

    return render_template('dashboard.html', 
        user=current_user, 
        courses=courses,
        stats=stats
    )


@app.route('/add-course', methods=['POST'])
@login_required
def add_course():
    """Create a new course and associated chat room"""
    name = request.form.get('name')
    code = request.form.get('code', '').upper()
    semester = request.form.get('semester')

    if not name or not code:
        flash('Course name and code are required', 'error')
        return redirect(url_for('dashboard'))

    # Check if code already exists
    if Course.query.filter_by(code=code, is_active=True).first():
        flash(f'Course {code} already exists', 'error')
        return redirect(url_for('dashboard'))

    # Create random group ID
    group_id = f"c_{secrets.token_hex(4)}"
    
    # Create the Course
    new_course = Course(
        name=name,
        code=code,
        semester=semester,
        lecturer_id=current_user.id,
        group_id=group_id
    )
    db.session.add(new_course)
    db.session.flush()

    # Create associated ChatRoom for the web chat system
    from chat_handler import generate_invite_code
    new_room = ChatRoom(
        name=f"{code} - {name}",
        description=f"Official group for {name}",
        room_type='group',
        invite_code=generate_invite_code(),
        created_by=None, # System created
        course_id=new_course.id
    )
    db.session.add(new_room)
    db.session.commit()

    flash(f'Course {code} successfully created!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/chat/room/<int:room_id>')
@login_required
def chat_room(room_id):
    """Redirect to the main chat app with a specific room focus"""
    return redirect(url_for('chat_app', room_focus=room_id))


@app.route('/course/<int:course_id>')
@login_required
def course_detail(course_id):
    """Detailed view for a specific course"""
    course = Course.query.get_or_404(course_id)
    
    # Check ownership
    if course.lecturer_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard'))

    faqs = FAQ.query.filter_by(course_id=course_id).order_by(FAQ.created_at.desc()).all()
    pending = PendingQuestion.query.filter_by(course_id=course_id, status='pending').order_by(PendingQuestion.asked_at.desc()).all()
    scheduled = ScheduledMessage.query.filter_by(course_id=course_id, status='pending').order_by(ScheduledMessage.scheduled_time.asc()).all()
    
    # Get recent messages from the associated room
    recent_messages = []
    if course.room:
        recent_messages = ChatMessage.query.filter_by(room_id=course.room.id)\
            .order_by(ChatMessage.created_at.desc()).limit(20).all()

    return render_template('course_detail.html',
        course=course,
        faqs=faqs,
        pending=pending,
        scheduled=scheduled,
        recent_messages=recent_messages
    )


# ==========================================
# 4. WEB CHAT ROUTES
# ==========================================
@app.route('/chat')
def chat_index():
    """Chat landing - login or go to chat"""
    if 'chat_user_id' in session:
        return redirect(url_for('chat_app'))
    return redirect(url_for('chat_login'))


@app.route('/chat/login', methods=['GET', 'POST'])
def chat_login():
    """Chat login page"""
    if 'chat_user_id' in session:
        return redirect(url_for('chat_app'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = ChatUser.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session['chat_user_id'] = user.id
            session['chat_username'] = user.username
            session['chat_role'] = user.role
            flash('Logged in successfully!', 'success')
            return redirect(url_for('chat_app'))
        else:
            flash('Invalid username or password', 'error')

    return render_template('chat_login.html')


@app.route('/chat/register', methods=['GET', 'POST'])
def chat_register():
    """Chat registration page"""
    if 'chat_user_id' in session:
        return redirect(url_for('chat_app'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        display_name = request.form.get('display_name', '').strip()

        if not username or not email or not password:
            flash('All fields are required', 'error')
            return render_template('chat_register.html')

        if len(username) < 3:
            flash('Username must be at least 3 characters', 'error')
            return render_template('chat_register.html')

        if len(password) < 6:
            flash('Password must be at least 6 characters', 'error')
            return render_template('chat_register.html')

        if ChatUser.query.filter_by(username=username).first():
            flash('Username already taken', 'error')
            return render_template('chat_register.html')

        if ChatUser.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return render_template('chat_register.html')

        # All users start as plain 'user' — role is upgraded separately via secret code
        user = ChatUser(
            username=username,
            email=email,
            display_name=display_name or username,
            role='user'
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('Account created! Please sign in.', 'success')
        return redirect(url_for('chat_login'))

    return render_template('chat_register.html')


@app.route('/chat/logout')
def chat_logout():
    """Logout from chat"""
    session.pop('chat_user_id', None)
    session.pop('chat_username', None)
    session.pop('chat_role', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('chat_login'))


@app.route('/chat/app')
def chat_app():
    """Main chat application"""
    if 'chat_user_id' not in session:
        return redirect(url_for('chat_login'))

    user = ChatUser.query.get(session['chat_user_id'])
    if not user:
        session.clear()
        return redirect(url_for('chat_login'))

    memberships = ChatMember.query.filter_by(user_id=user.id).all()
    rooms_data = []
    
    for m in memberships:
        room = m.room
        if not room.is_active:
            continue
            
        # Add other_user_id for DMs
        other_user_id = None
        if room.room_type == 'dm':
            other_member = ChatMember.query.filter(
                ChatMember.room_id == room.id,
                ChatMember.user_id != user.id
            ).first()
            if other_member:
                other_user_id = other_member.user_id
        
        # Attach temporarily to the room object for the template
        room.other_user_id = other_user_id
        rooms_data.append(room)

    courses = []
    if user.is_admin():
        courses = Course.query.filter_by(is_active=True).all()

    return render_template('chat.html',
        user=user,
        rooms=rooms_data,
        courses=courses
    )


@app.route('/chat/profile', methods=['GET', 'POST'])
def chat_profile():
    """Edit user profile – avatar, display name, bio"""
    if 'chat_user_id' not in session:
        return redirect(url_for('chat_login'))

    user = ChatUser.query.get(session['chat_user_id'])
    if not user:
        session.clear()
        return redirect(url_for('chat_login'))

    if request.method == 'POST':
        if request.form.get('remove_avatar') == 'true':
            if user.profile_pic:
                old_path = os.path.join(app.root_path, 'static', user.profile_pic)
                if os.path.exists(old_path):
                    os.remove(old_path)
                user.profile_pic = None
            db.session.commit()
            flash('Photo removed', 'success')
            return redirect(url_for('chat_profile'))

        display_name = request.form.get('display_name', '').strip()
        if display_name:
            user.display_name = display_name

        user.bio = request.form.get('bio', '').strip()

        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename != '':
                allowed_ext = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
                if ext in allowed_ext:
                    if user.profile_pic:
                        old_path = os.path.join(app.root_path, 'static', user.profile_pic)
                        if os.path.exists(old_path):
                            os.remove(old_path)
                    avatar_dir = os.path.join(app.root_path, 'static', 'uploads', 'avatars')
                    os.makedirs(avatar_dir, exist_ok=True)
                    filename = f"{user.id}_{int(datetime.utcnow().timestamp())}_{secrets.token_hex(4)}.{ext}"
                    file.save(os.path.join(avatar_dir, filename))
                    user.profile_pic = f'uploads/avatars/{filename}'

        db.session.commit()
        flash('Profile updated', 'success')
        return redirect(url_for('chat_profile'))

    return render_template('chat_profile.html', user=user)


# ==========================================
# 5. API ENDPOINTS
# ==========================================
@app.route('/api/chat/rooms')
def get_chat_rooms():
    """Get user's chat rooms"""
    if 'chat_user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    user_id = session['chat_user_id']
    memberships = ChatMember.query.filter_by(user_id=user_id).all()

    rooms = []
    for m in memberships:
        room = m.room
        last_message = ChatMessage.query.filter_by(room_id=room.id)\
            .order_by(ChatMessage.created_at.desc()).first()

        rooms.append({
            'id': room.id,
            'name': room.name,
            'room_type': room.room_type,
            'invite_code': room.invite_code if room.room_type == 'group' else None,
            'last_message': last_message.content[:50] if last_message else None,
            'last_message_time': last_message.created_at.isoformat() if last_message else None
        })

    return jsonify({'rooms': rooms})


# Removed /api/chat/upgrade-admin per user request (consolidated to Lecturer)


@app.route('/api/chat/upgrade-lecturer', methods=['POST'])
def upgrade_lecturer():
    """Upgrade a plain user account to lecturer role using a secret code"""
    from config import Config
    if 'chat_user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json() or {}
    # Accept both client-side 'secret_code' and 'lecturer_code' for compatibility
    code = (data.get('secret_code') or data.get('lecturer_code') or '').strip()

    user = ChatUser.query.get(session['chat_user_id'])
    if not user:
        session.clear()
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    if user.role in ['lecturer', 'admin']:
        return jsonify({'status': 'success', 'message': 'Already a lecturer or admin'})

    if code == Config.LECTURER_SECRET_CODE:
        user.role = 'lecturer'
        db.session.commit()
        session['chat_role'] = 'lecturer'
        return jsonify({'status': 'success', 'message': 'Access granted! You now have lecturer privileges.'})

    return jsonify({'status': 'error', 'message': 'Invalid access code. Please contact your administrator.'}), 400


@app.route('/api/chat/delete-account', methods=['POST'])
def delete_chat_account():
    """Delete current user's account"""
    if 'chat_user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    user = ChatUser.query.get(session['chat_user_id'])
    if not user:
        session.clear()
        return jsonify({'error': 'User not found'}), 404

    if user.role == 'admin':
        return jsonify({'error': 'Admins cannot delete their own accounts'}), 403

    # Perform deletion
    db.session.delete(user)
    db.session.commit()

    # Clear session
    session.clear()

    return jsonify({'success': True, 'message': 'Account deleted successfully'})


@app.route('/api/chat/export/<int:room_id>')
def export_chat(room_id):
    """Export chat history as a text file (admin only)"""
    if 'chat_user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    current = ChatUser.query.get(session['chat_user_id'])
    if not current or not current.is_admin():
        return jsonify({'error': 'Admin access required'}), 403

    room = ChatRoom.query.get(room_id)
    if not room:
        return jsonify({'error': 'Room not found'}), 404

    messages = ChatMessage.query.filter_by(room_id=room_id)\
        .order_by(ChatMessage.created_at.asc()).all()

    lines = [
        "=== ClassPulse Chat Export ===",
        f"Group: {room.name}",
        f"Exported by: {current.display_name or current.username}",
        f"Exported at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        f"Total messages: {len(messages)}",
        "=" * 40,
        ""
    ]

    for m in messages:
        if m.message_type == 'deleted':
            continue
        timestamp = m.created_at.strftime('%Y-%m-%d %H:%M')
        sender = m.sender.display_name if m.sender else 'System'
        if m.message_type == 'system':
            lines.append(f"[{timestamp}] --- {m.content} ---")
        elif m.message_type == 'broadcast':
            lines.append(f"[{timestamp}] 📢 {sender}: {m.content}")
        elif m.message_type == 'ai_response':
            lines.append(f"[{timestamp}] ClassPulse AI: {m.content}")
        else:
            lines.append(f"[{timestamp}] {sender}: {m.content}")

    export_text = "\n".join(lines)
    safe_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '' for c in room.name)
    filename = f"ClassPulse_Chat_{safe_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.txt"

    response = make_response(export_text)
    response.headers['Content-Type'] = 'text/plain; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# --- RESTORED API ENDPOINTS ---

@app.route('/api/faq/add', methods=['POST'])
@login_required
def api_add_faq():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    course_id = data.get('course_id')
    question = data.get('question')
    answer = data.get('answer')
    
    if not course_id or not question or not answer:
        return jsonify({'success': False, 'error': 'Missing fields'}), 400
        
    course = Course.query.get(course_id)
    if not course or course.lecturer_id != current_user.id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
    new_faq = FAQ(course_id=course_id, question=question, answer=answer)
    db.session.add(new_faq)
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/api/faq/delete/<int:faq_id>', methods=['DELETE'])
@login_required
def api_delete_faq(faq_id):
    faq = FAQ.query.get_or_404(faq_id)
    course = Course.query.get(faq.course_id)
    
    if not course or course.lecturer_id != current_user.id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
    db.session.delete(faq)
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/api/question/dismiss/<int:question_id>', methods=['POST'])
@login_required
def api_dismiss_question(question_id):
    question = PendingQuestion.query.get_or_404(question_id)
    course = Course.query.get(question.course_id)
    
    if not course or course.lecturer_id != current_user.id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
    question.status = 'dismissed'
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/api/scheduled/cancel/<int:message_id>', methods=['POST'])
@login_required
def api_cancel_scheduled(message_id):
    msg = ScheduledMessage.query.get_or_404(message_id)
    course = Course.query.get(msg.course_id)
    
    if not course or course.lecturer_id != current_user.id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
    msg.status = 'cancelled'
    db.session.commit()
    
    return jsonify({'success': True})


# ==========================================
# 6. ERROR HANDLERS
# ==========================================
@app.route('/api/command_center', methods=['POST'])
@login_required
def api_command_center():
    """Lecturer-AI direct chat interaction"""
    if not current_user.is_lecturer():
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    data = request.get_json() or {}
    message = data.get('message', '').strip()
    course_id = data.get('course_id')

    if not message or not course_id:
        return jsonify({'success': False, 'error': 'Missing data'}), 400

    course = Course.query.get(course_id)
    if not course or course.lecturer_id != current_user.id:
        return jsonify({'success': False, 'error': 'Course not found or unauthorized'}), 404

    try:
        from ai_engine import ask_groq_ai_direct
        from action_engine import ActionEngine
        import json

        # Build a specialized prompt for the lecturer command center
        prompt = f"""You are the ClassPulse Control AI for {course.code}. 
You are speaking directly to LECTURER {current_user.name}.
Your job is to assist them with:
1. Summarizing student needs
2. Analyzing course data
3. Drafting academic content
4. Answering technical system questions
5. Executing system actions (Create group, lock chat, teaching sessions, etc.)

Be professional, concise, and proactive.

LECTURER COMMAND: {message}"""

        response = ask_groq_ai_direct(prompt, tools_enabled=True)
        
        if response:
            # Check for JSON action block
            action_result = None
            if "{" in response and "}" in response:
                try:
                    # Crude extraction of JSON from response
                    json_str = response[response.find("{"):response.rfind("}")+1]
                    action_data = json.loads(json_str)
                    action = action_data.get('action')
                    params = action_data.get('params', {})
                    
                    if action == 'create_group':
                        success, res = ActionEngine.create_group(current_user.id, params.get('name'), params.get('description'), course.id)
                        action_result = res
                    elif action == 'lock_group':
                        success, res = ActionEngine.lock_group(current_user.id, params.get('room_id'), params.get('lock'))
                        action_result = res
                    elif action == 'create_teaching_session':
                        success, res = ActionEngine.create_teaching_session(current_user.id, params.get('room_id'), params.get('topic'), params.get('days'))
                        action_result = res
                    elif action == 'send_broadcast':
                        success, res = ActionEngine.send_broadcast(current_user.id, params.get('room_id'), params.get('message'))
                        action_result = res
                    elif action == 'delete_group':
                        success, res = ActionEngine.delete_group(current_user.id, params.get('room_id'))
                        action_result = res
                except Exception as e:
                    print(f"[WARN] Failed to parse AI action: {e}")

            return jsonify({
                'success': True, 
                'response': response,
                'action_result': action_result,
                'timestamp': datetime.utcnow().isoformat()
            })
        else:
            return jsonify({'success': False, 'error': 'AI failed to respond'}), 500

    except Exception as e:
        print(f"[ERROR] Command Center Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/voice_command', methods=['POST'])
@login_required
def api_voice_command():
    """Handle voice commands from lecturer to AI"""
    if not current_user.is_lecturer():
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    if 'audio' not in request.files:
        return jsonify({'success': False, 'error': 'No audio file provided'}), 400

    course_id = request.form.get('course_id')
    audio_file = request.files['audio']

    try:
        from voice_handler import transcribe_voice_note
        import tempfile
        import os

        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as tmp:
            audio_file.save(tmp.name)
            tmp_path = tmp.name

        try:
            # Transcribe locally or via API
            # Note: transcribe_voice_note expects a URL normally, but let's assume we can pass a path or update it
            # For simplicity, let's mock the transcription if we can't easily use the existing handler
            from groq import Groq
            client = Groq(api_key=Config.GROQ_API_KEY)
            
            with open(tmp_path, 'rb') as f:
                transcription = client.audio.transcriptions.create(
                    file=(os.path.basename(tmp_path), f.read()),
                    model="whisper-large-v3",
                    language="en",
                    response_format="json"
                )
            
            text = transcription.text.strip()
            
            # Now treat the text as a command
            # Reuse logic or call the endpoint internally? Let's assume we return the text for the frontend to then 'send'
            return jsonify({
                'success': True,
                'transcription': text,
                'message': 'Voice processed successfully'
            })

        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except Exception as e:
        print(f"[ERROR] Voice Command Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/chat/voice', methods=['POST'])
@login_required
def api_chat_voice():
    """Handle voice notes sent by lecturer to group chats"""
    if not current_user.is_lecturer():
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    if 'audio' not in request.files:
        return jsonify({'success': False, 'error': 'No audio file provided'}), 400

    room_id = request.form.get('room_id')
    audio_file = request.files['audio']

    try:
        from groq import Groq
        import tempfile
        import os
        from models import ChatRoom, ChatMessage, VoiceTranscription

        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as tmp:
            audio_file.save(tmp.name)
            tmp_path = tmp.name

        try:
            client = Groq(api_key=Config.GROQ_API_KEY)
            with open(tmp_path, 'rb') as f:
                transcription_res = client.audio.transcriptions.create(
                    file=(os.path.basename(tmp_path), f.read()),
                    model="whisper-large-v3",
                    language="en",
                    response_format="json"
                )
            
            text = transcription_res.text.strip()
            
            # Save the voice note to the database as a message
            # In a real app, you'd save the audio file to S3/Cloudinary.
            # Here we'll simulate it by tagging the message as 'voice_note'
            msg = ChatMessage(
                room_id=room_id,
                sender_id=current_user.id,
                content=f"[Voice Note: {text}]",
                message_type='voice_note'
            )
            db.session.add(msg)
            db.session.commit()

            # Record the transcription metadata using the existing VoiceTranscription model
            vt = VoiceTranscription(
                phone_number=current_user.username,  # use username as identifier
                transcribed_text=text,
                status='completed',
                duration_seconds=0
            )
            db.session.add(vt)
            db.session.commit()

            # Emit via socket
            socketio.emit('new_message', {
                'id': msg.id,
                'room_id': room_id,
                'content': msg.content,
                'sender_id': current_user.id,
                'sender_name': current_user.display_name or current_user.username,
                'sender_pic': current_user.profile_pic,
                'message_type': 'voice_note',
                'created_at': msg.created_at.isoformat(),
                'transcription': text
            }, room=f'room_{room_id}')

            return jsonify({'success': True, 'message_id': msg.id})

        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except Exception as e:
        print(f"[ERROR] Chat Voice Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404


# @app.errorhandler(500)
# def internal_error(error):
#     db.session.rollback()
#     return render_template('500.html'), 500


# ==========================================
# 7. RUN APPLICATION
# ==========================================
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5001, debug=Config.DEBUG)