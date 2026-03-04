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
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'chat_login'

# Initialize Socket.IO for real-time chat
socketio = SocketIO(app, cors_allowed_origins="*")

# Create database tables
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

scheduler = BackgroundScheduler()
scheduler.add_job(
    func=scheduled_job_with_context,
    trigger="interval",
    seconds=60
)
scheduler.start()
print("[OK] Scheduler started")


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
    """Landing page - redirect to chat"""
    if 'chat_user_id' in session:
        return redirect(url_for('chat_app'))
    return redirect(url_for('chat_login'))


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

        if ChatUser.query.filter_by(username=username).first():
            flash('Username already taken', 'error')
            return render_template('chat_register.html')

        if ChatUser.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return render_template('chat_register.html')

        # Capture role from form
        role = request.form.get('role', 'student').lower()
        if role not in ['student', 'lecturer']:
            role = 'student'

        user = ChatUser(
            username=username,
            email=email,
            display_name=display_name or username,
            role=role
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('Registration successful! Please login.', 'success')
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


    return jsonify({'success': True, 'message': f'{user.username} is now an admin'})


@app.route('/api/chat/upgrade-admin', methods=['POST'])
def upgrade_admin():
    """Upgrade user to admin using a code"""
    if 'chat_user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json()
    code = data.get('admin_code', '')

    if code == 'CP-ADMIN-2026':
        user = ChatUser.query.get(session['chat_user_id'])
        if user:
            user.role = 'admin'
            db.session.commit()
            session['chat_role'] = 'admin'
            return jsonify({'success': True, 'message': 'Account upgraded to admin'})
        return jsonify({'error': 'User not found'}), 404
    else:
        return jsonify({'error': 'Invalid admin code'}), 400


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


# ==========================================
# 6. ERROR HANDLERS
# ==========================================
@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500


# ==========================================
# 7. RUN APPLICATION
# ==========================================
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=Config.DEBUG)