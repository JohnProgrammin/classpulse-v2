"""
Web Chat Handler for ClassPulse
Handles WebSocket events for real-time chat functionality
"""

from datetime import datetime
import secrets
from flask import request
from flask_socketio import emit, join_room, leave_room, rooms
from models import db, ChatUser, ChatRoom, ChatMember, ChatMessage, MessageReaction, AIDocument, Course


def generate_invite_code():
    """Generate a unique 6-character invite code"""
    while True:
        code = secrets.token_hex(3).upper()  # 6 characters
        if not ChatRoom.query.filter_by(invite_code=code).first():
            return code


def get_or_create_ai_user():
    """Get or create the AI system user"""
    ai_user = ChatUser.query.filter_by(username='classpulse_ai').first()
    if not ai_user:
        ai_user = ChatUser(
            username='classpulse_ai',
            email='ai@classpulse.local',
            display_name='ClassPulse AI',
            role='system'
        )
        ai_user.set_password(secrets.token_hex(32))  # Random password, not used
        db.session.add(ai_user)
        db.session.commit()
    return ai_user


def process_teaching_sessions():
    """Scheduled: post daily lessons and close expired teaching groups."""
    from datetime import timedelta
    from models import TeachingSession

    now = datetime.utcnow()
    sessions = TeachingSession.query.filter(
        TeachingSession.current_day < TeachingSession.total_days
    ).all()

    for session in sessions:
        room = ChatRoom.query.get(session.room_id)
        if not room or not room.is_active:
            continue

        # Check if it's time for the next day's lesson
        next_lesson_date = session.start_date + timedelta(days=session.current_day)
        if now.date() < next_lesson_date.date():
            continue  # Not yet time

        # Generate lesson via Groq
        try:
            from groq import Groq
            from config import Config

            if not Config.GROQ_API_KEY:
                continue

            day_num = session.current_day + 1
            prompt = f"""You are a teaching AI posting Day {day_num} of {session.total_days} in a group chat.
Topic: {session.topic}

Write a practical, engaging lesson for Day {day_num}. Make it relatable with real examples, analogies, or mini-exercises.
- Keep it concise (3–6 short paragraphs max).
- Start with "📚 **Day {day_num}: [lesson title]**"
- End with a simple reflection question or mini-challenge for students.
- Assume students have seen Days 1–{day_num - 1} already (build on previous lessons progressively).
- Don't add any meta-commentary — just the lesson itself."""

            groq_client = Groq(api_key=Config.GROQ_API_KEY)
            completion = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.7,
                max_tokens=600
            )
            lesson_text = completion.choices[0].message.content

            # Post as AI message
            ai_user = get_or_create_ai_user()
            lesson_msg = ChatMessage(
                room_id=room.id,
                sender_id=ai_user.id,
                content=lesson_text,
                message_type='ai_response'
            )
            db.session.add(lesson_msg)
            session.current_day = day_num
            db.session.commit()

            print(f"[TEACH] Posted Day {day_num}/{session.total_days} for '{session.topic}' in room {room.id}")

        except Exception as e:
            print(f"[ERROR] Teaching lesson generation failed for '{session.topic}': {e}")

    # Close expired teaching groups
    expired = TeachingSession.query.filter(TeachingSession.close_date <= now).all()
    for session in expired:
        room = ChatRoom.query.get(session.room_id)
        if room and room.is_active:
            # Post closing message
            ai_user = get_or_create_ai_user()
            close_msg = ChatMessage(
                room_id=room.id,
                sender_id=ai_user.id,
                content=f"✅ This {session.total_days}-day teaching session on **{session.topic}** has concluded. Great work, everyone! Feel free to revisit the lessons above anytime.",
                message_type='system'
            )
            db.session.add(close_msg)
            room.is_active = False
            db.session.commit()
            print(f"[TEACH] Closed teaching group '{session.topic}' (room {room.id})")


def register_socket_events(socketio):
    """Register all Socket.IO event handlers"""
    # Map of sids to user_ids for presence tracking
    connection_map = {}


    @socketio.on('connect')
    def handle_connect():
        """Handle client connection"""
        print(f"[CHAT] Client connected: {request.sid}")

    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection"""
        print(f"[CHAT] Client disconnected: {request.sid}")
        user_id = connection_map.pop(request.sid, None)
        if user_id:
            # Check if user has other active connections
            if user_id not in connection_map.values():
                # Update DB
                user = ChatUser.query.get(user_id)
                if user:
                    user.is_online = False
                    user.last_seen = datetime.utcnow()
                    db.session.commit()
                emit('presence_update', {'user_id': user_id, 'status': 'offline'}, broadcast=True)

    @socketio.on('authenticate')
    def handle_authenticate(data):
        """Authenticate user and join their rooms"""
        user_id = data.get('user_id')
        if not user_id:
            emit('error', {'message': 'Authentication required'})
            return

        user = ChatUser.query.get(user_id)
        if not user:
            emit('error', {'message': 'User not found'})
            return

        # Presence mapping
        is_first_connection = user_id not in connection_map.values()
        connection_map[request.sid] = user_id
        
        if is_first_connection:
            user.is_online = True
            user.last_seen = datetime.utcnow()
            db.session.commit()
            emit('presence_update', {'user_id': user_id, 'status': 'online'}, broadcast=True)

        # Join all rooms the user is a member of
        memberships = ChatMember.query.filter_by(user_id=user_id).all()
        for membership in memberships:
            join_room(f'room_{membership.room_id}')
            print(f"[CHAT] User {user.username} joined room_{membership.room_id}")

        emit('authenticated', {
            'user_id': user.id,
            'username': user.username,
            'display_name': user.display_name,
            'role': user.role,
            'rooms': [m.room_id for m in memberships]
        })

    @socketio.on('join_room')
    def handle_join_room(data):
        """Join a specific chat room"""
        user_id = data.get('user_id')
        room_id = data.get('room_id')

        membership = ChatMember.query.filter_by(
            user_id=user_id, room_id=room_id
        ).first()

        if not membership:
            emit('error', {'message': 'Not a member of this room'})
            return

        join_room(f'room_{room_id}')

        # Mark as read
        membership.last_read_at = datetime.utcnow()
        db.session.commit()

        # Get recent messages
        messages = ChatMessage.query.filter_by(room_id=room_id)\
            .order_by(ChatMessage.created_at.desc())\
            .limit(50)\
            .all()

        def build_message_data(m):
            data = {
                'id': m.id,
                'content': m.content,
                'sender_id': m.sender_id,
                'sender_name': m.sender.display_name if m.sender else 'System',
                'sender_pic': '__bot__' if (m.sender and m.sender.username == 'classpulse_ai') else (m.sender.profile_pic if m.sender else None),
                'message_type': m.message_type,
                'created_at': m.created_at.isoformat(),
                'edited_at': m.edited_at.isoformat() if m.edited_at else None,
                'reply_to': None
            }
            if m.reply_to_id and m.reply_to:
                data['reply_to'] = {
                    'id': m.reply_to.id,
                    'content': m.reply_to.content[:100] + ('...' if len(m.reply_to.content) > 100 else ''),
                    'sender_name': m.reply_to.sender.display_name if m.reply_to.sender else 'Unknown'
                }
            # Aggregate reactions
            reaction_map = {}
            for r in m.reactions:
                reaction_map.setdefault(r.emoji, []).append(r.user_id)
            data['reactions'] = [{'emoji': e, 'count': len(uids), 'user_ids': uids} for e, uids in reaction_map.items()]
            
            # Read status
            data['status'] = m.status
            from models import MessageReadReceipt
            read_by = MessageReadReceipt.query.filter_by(message_id=m.id).count()
            data['read_count'] = read_by
            
            return data

        room = ChatRoom.query.get(room_id)

        # Check for teaching session
        from models import TeachingSession
        teach_session = TeachingSession.query.filter_by(room_id=room_id).first()
        teaching_data = None
        if teach_session:
            teaching_data = {
                'topic': teach_session.topic,
                'total_days': teach_session.total_days,
                'current_day': teach_session.current_day,
                'close_date': teach_session.close_date.isoformat()
            }

        emit('room_joined', {
            'room_id': room_id,
            'locked': bool(room.locked) if room else False,
            'teaching': teaching_data,
            'messages': [build_message_data(m) for m in reversed(messages)]
        })

    @socketio.on('leave_room')
    def handle_leave_room(data):
        """Leave a chat room (WebSocket only, not membership)"""
        room_id = data.get('room_id')
        leave_room(f'room_{room_id}')

    @socketio.on('send_message')
    def handle_send_message(data):
        """Handle sending a message"""
        user_id = data.get('user_id')
        room_id = data.get('room_id')
        content = data.get('content', '').strip()

        if not content:
            return

        user = ChatUser.query.get(user_id)
        room = ChatRoom.query.get(room_id)

        if not user or not room:
            emit('error', {'message': 'Invalid user or room'})
            return

        # Verify membership
        membership = ChatMember.query.filter_by(
            user_id=user_id, room_id=room_id
        ).first()

        if not membership:
            emit('error', {'message': 'Not a member of this room'})
            return

        # Block non-admins when room is locked
        if room.locked and membership.role != 'admin' and not user.is_admin():
            emit('error', {'message': 'This group is locked by the lecturer.'})
            return

        # Create the message
        message = ChatMessage(
            room_id=room_id,
            sender_id=user_id,
            content=content,
            message_type='text'
        )
        db.session.add(message)
        db.session.commit()

        # Broadcast to room
        message_data = {
            'id': message.id,
            'room_id': room_id,
            'content': content,
            'sender_id': user_id,
            'sender_name': user.display_name or user.username,
            'sender_pic': user.profile_pic,
            'message_type': 'text',
            'status': message.status,
            'created_at': message.created_at.isoformat()
        }
        emit('new_message', message_data, room=f'room_{room_id}')

        # Check if this is an AI DM — any user can chat with AI
        if room.room_type == 'ai_dm':
            handle_ai_response(user, room, content, socketio)

    @socketio.on('create_group')
    def handle_create_group(data):
        """Create a new group chat (admin only)"""
        user_id = data.get('user_id')
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        course_id = data.get('course_id')  # Optional link to course

        user = ChatUser.query.get(user_id)
        if not user or not user.is_admin():
            emit('error', {'message': 'Only admins can create groups'})
            return

        if not name:
            emit('error', {'message': 'Group name required'})
            return

        # Create the room
        room = ChatRoom(
            name=name,
            description=description,
            room_type='group',
            invite_code=generate_invite_code(),
            created_by=user_id,
            course_id=course_id
        )
        db.session.add(room)
        db.session.flush()

        # Add creator as admin member
        member = ChatMember(
            room_id=room.id,
            user_id=user_id,
            role='admin'
        )
        db.session.add(member)

        # Add system message
        system_msg = ChatMessage(
            room_id=room.id,
            content=f"Group '{name}' created by {user.display_name or user.username}",
            message_type='system'
        )
        db.session.add(system_msg)
        db.session.commit()

        # Join the room
        join_room(f'room_{room.id}')

        emit('group_created', {
            'room_id': room.id,
            'name': room.name,
            'invite_code': room.invite_code,
            'course_id': room.course_id
        })

    @socketio.on('join_with_code')
    def handle_join_with_code(data):
        """Join a group using invite code"""
        user_id = data.get('user_id')
        invite_code = data.get('invite_code', '').strip().upper()

        user = ChatUser.query.get(user_id)
        if not user:
            emit('error', {'message': 'User not found'})
            return

        room = ChatRoom.query.filter_by(invite_code=invite_code, is_active=True).first()
        if not room:
            emit('error', {'message': 'Invalid invite code'})
            return

        # Check if already a member
        existing = ChatMember.query.filter_by(
            user_id=user_id, room_id=room.id
        ).first()

        if existing:
            emit('error', {'message': 'Already a member of this group'})
            return

        # Add as member
        member = ChatMember(
            room_id=room.id,
            user_id=user_id,
            role='member'
        )
        db.session.add(member)

        # System message
        system_msg = ChatMessage(
            room_id=room.id,
            content=f"{user.display_name or user.username} joined the group",
            message_type='system'
        )
        db.session.add(system_msg)
        db.session.commit()

        # Join the room
        join_room(f'room_{room.id}')

        # Notify room
        emit('user_joined', {
            'room_id': room.id,
            'user_id': user.id,
            'username': user.username,
            'display_name': user.display_name
        }, room=f'room_{room.id}')

        emit('joined_group', {
            'room_id': room.id,
            'name': room.name,
            'description': room.description
        })

    @socketio.on('start_ai_dm')
    def handle_start_ai_dm(data):
        """Start or get AI DM room (any authenticated user)"""
        user_id = data.get('user_id')

        user = ChatUser.query.get(user_id)
        if not user:
            emit('error', {'message': 'User not found'})
            return

        # Check for existing AI DM room
        existing_room = ChatRoom.query.filter_by(
            room_type='ai_dm',
            created_by=user_id
        ).first()

        if existing_room:
            join_room(f'room_{existing_room.id}')

            # Get messages
            messages = ChatMessage.query.filter_by(room_id=existing_room.id)\
                .order_by(ChatMessage.created_at.desc())\
                .limit(50)\
                .all()

            emit('ai_dm_ready', {
                'room_id': existing_room.id,
                'messages': [{
                    'id': m.id,
                    'content': m.content,
                    'sender_id': m.sender_id,
                    'sender_name': m.sender.display_name if m.sender else 'ClassPulse AI',
                    'sender_pic': '__bot__' if (m.sender and m.sender.username == 'classpulse_ai') else (m.sender.profile_pic if m.sender else None),
                    'message_type': m.message_type,
                    'created_at': m.created_at.isoformat()
                } for m in reversed(messages)]
            })
            return

        # Create new AI DM room
        room = ChatRoom(
            name='AI Assistant',
            room_type='ai_dm',
            created_by=user_id
        )
        db.session.add(room)
        db.session.flush()

        # Add user as member
        member = ChatMember(
            room_id=room.id,
            user_id=user_id,
            role='admin'
        )
        db.session.add(member)

        # Welcome message from AI
        ai_user = get_or_create_ai_user()
        welcome = ChatMessage(
            room_id=room.id,
            sender_id=ai_user.id,
            content="Hello! I'm your ClassPulse AI assistant. You can:\n\n"
                   "• Register courses (e.g., 'Register CSC301 Software Engineering')\n"
                   "• Broadcast to groups (e.g., 'Send to CSC301: Class is cancelled today')\n"
                   "• Schedule messages\n"
                   "• Ask me anything about your courses\n\n"
                   "How can I help you today?",
            message_type='ai_response'
        )
        db.session.add(welcome)
        db.session.commit()

        join_room(f'room_{room.id}')

        emit('ai_dm_ready', {
            'room_id': room.id,
            'messages': [{
                'id': welcome.id,
                'content': welcome.content,
                'sender_id': ai_user.id,
                'sender_name': 'ClassPulse AI',
                'sender_pic': '__bot__',
                'message_type': 'ai_response',
                'created_at': welcome.created_at.isoformat()
            }]
        })

    @socketio.on('broadcast_to_group')
    def handle_broadcast(data):
        """Broadcast a message to a group (admin only, usually from AI conversation)"""
        user_id = data.get('user_id')
        room_id = data.get('room_id')
        content = data.get('content', '').strip()

        user = ChatUser.query.get(user_id)
        room = ChatRoom.query.get(room_id)

        if not user or not user.is_admin():
            emit('error', {'message': 'Only admins can broadcast'})
            return

        if not room or room.room_type != 'group':
            emit('error', {'message': 'Invalid group'})
            return

        # Create broadcast message
        message = ChatMessage(
            room_id=room_id,
            sender_id=user_id,
            content=f"📢 {content}",
            message_type='broadcast'
        )
        db.session.add(message)
        db.session.commit()

        # Broadcast to room
        emit('new_message', {
            'id': message.id,
            'room_id': room_id,
            'content': message.content,
            'sender_id': user_id,
            'sender_name': user.display_name or user.username,
            'sender_pic': user.profile_pic,
            'message_type': 'broadcast',
            'created_at': message.created_at.isoformat()
        }, room=f'room_{room_id}')

        emit('broadcast_sent', {
            'room_id': room_id,
            'message': 'Broadcast sent successfully'
        })

    @socketio.on('delete_message')
    def handle_delete_message(data):
        """Delete a message (only sender can delete their own messages)"""
        user_id = data.get('user_id')
        message_id = data.get('message_id')

        user = ChatUser.query.get(user_id)
        message = ChatMessage.query.get(message_id)

        if not user or not message:
            emit('error', {'message': 'Message not found'})
            return

        # Only sender can delete (or admin can delete any message in their groups)
        if message.sender_id != user_id and not user.is_admin():
            emit('error', {'message': 'Cannot delete this message'})
            return

        room_id = message.room_id

        # Soft delete - mark as deleted
        message.content = "This message was deleted"
        message.message_type = 'deleted'
        message.edited_at = datetime.utcnow()
        db.session.commit()

        # Notify room
        emit('message_deleted', {
            'message_id': message_id,
            'room_id': room_id
        }, room=f'room_{room_id}')

    @socketio.on('edit_message')
    def handle_edit_message(data):
        """Edit a message (only sender can edit their own messages)"""
        user_id = data.get('user_id')
        message_id = data.get('message_id')
        new_content = data.get('content', '').strip()

        if not new_content:
            emit('error', {'message': 'Message cannot be empty'})
            return

        user = ChatUser.query.get(user_id)
        message = ChatMessage.query.get(message_id)

        if not user or not message:
            emit('error', {'message': 'Message not found'})
            return

        # Only sender can edit
        if message.sender_id != user_id:
            emit('error', {'message': 'Cannot edit this message'})
            return

        # Cannot edit system/AI/broadcast/deleted messages
        if message.message_type in ['system', 'deleted', 'ai_response', 'broadcast']:
            emit('error', {'message': 'Cannot edit this message'})
            return

        room_id = message.room_id
        message.content = new_content
        message.edited_at = datetime.utcnow()
        db.session.commit()

        # Notify room
        emit('message_edited', {
            'message_id': message_id,
            'room_id': room_id,
            'content': new_content,
            'edited_at': message.edited_at.isoformat()
        }, room=f'room_{room_id}')

    @socketio.on('send_reply')
    def handle_send_reply(data):
        """Send a message as a reply to another message"""
        user_id = data.get('user_id')
        room_id = data.get('room_id')
        content = data.get('content', '').strip()
        reply_to_id = data.get('reply_to_id')

        if not content:
            return

        user = ChatUser.query.get(user_id)
        room = ChatRoom.query.get(room_id)
        reply_to = ChatMessage.query.get(reply_to_id) if reply_to_id else None

        if not user or not room:
            emit('error', {'message': 'Invalid user or room'})
            return

        # Verify membership
        membership = ChatMember.query.filter_by(
            user_id=user_id, room_id=room_id
        ).first()

        if not membership:
            emit('error', {'message': 'Not a member of this room'})
            return

        # Block non-admins when room is locked
        if room.locked and membership.role != 'admin' and not user.is_admin():
            emit('error', {'message': 'This group is locked by the lecturer.'})
            return

        # Create the message with reply reference
        message = ChatMessage(
            room_id=room_id,
            sender_id=user_id,
            content=content,
            message_type='text',
            reply_to_id=reply_to_id
        )
        db.session.add(message)
        db.session.commit()

        # Build reply context
        reply_data = None
        if reply_to:
            reply_data = {
                'id': reply_to.id,
                'content': reply_to.content[:100] + ('...' if len(reply_to.content) > 100 else ''),
                'sender_name': reply_to.sender.display_name if reply_to.sender else 'Unknown'
            }

        # Broadcast to room
        message_data = {
            'id': message.id,
            'room_id': room_id,
            'content': content,
            'sender_id': user_id,
            'sender_name': user.display_name or user.username,
            'sender_pic': user.profile_pic,
            'message_type': 'text',
            'created_at': message.created_at.isoformat(),
            'reply_to': reply_data
        }
        emit('new_message', message_data, room=f'room_{room_id}')

        # Check if this is an AI DM — any user can chat with AI
        if room.room_type == 'ai_dm':
            handle_ai_response(user, room, content, socketio)

        # If replying to an AI message in a group, trigger AI reply
        if room.room_type == 'group' and reply_to:
            ai_user = get_or_create_ai_user()
            if reply_to.sender_id == ai_user.id:
                handle_group_ai_reply(user, room, content, reply_to, message, socketio)

    @socketio.on('delete_for_me')
    def handle_delete_for_me(data):
        """Delete a message only for the current user (client-side acknowledgement)"""
        # This is a no-op on the server — the client handles it via localStorage.
        # We just emit an ack so the client knows it went through.
        emit('delete_for_me_ack', {
            'message_id': data.get('message_id')
        })

    @socketio.on('typing')
    def handle_typing(data):
        """User started typing"""
        user_id = data.get('user_id')
        room_id = data.get('room_id')
        user = ChatUser.query.get(user_id)
        if user:
            emit('typing', {
                'room_id': room_id,
                'user_id': user_id,
                'username': user.username,
                'display_name': user.display_name or user.username
            }, room=f'room_{room_id}', include_self=False)

    @socketio.on('stop_typing')
    def handle_stop_typing(data):
        """User stopped typing"""
        user_id = data.get('user_id')
        room_id = data.get('room_id')
        emit('stop_typing', {'user_id': user_id, 'room_id': room_id}, room=f'room_{room_id}', include_self=False)

    @socketio.on('mark_read')
    def handle_mark_read(data):
        """Mark messages as read for a user in a room"""
        user_id = data.get('user_id')
        room_id = data.get('room_id')
        
        from models import MessageReadReceipt, ChatMember, ChatMessage
        
        # Update membership last_read_at
        membership = ChatMember.query.filter_by(user_id=user_id, room_id=room_id).first()
        if membership:
            membership.last_read_at = datetime.utcnow()
            
        # Get unread message IDs for this user in this room (excluding own)
        # Using a subquery for better performance
        read_receipts_subquery = db.session.query(MessageReadReceipt.message_id).filter_by(user_id=user_id).subquery()
        
        unread_messages = ChatMessage.query.filter(
            ChatMessage.room_id == room_id,
            ChatMessage.sender_id != user_id
        ).filter(
            ~ChatMessage.id.in_(read_receipts_subquery)
        ).all()
        
        new_receipts = []
        for msg in unread_messages:
            new_receipts.append(MessageReadReceipt(message_id=msg.id, user_id=user_id))
            
            # If DM, mark as read
            room = ChatRoom.query.get(room_id)
            if room and room.room_type in ('dm', 'ai_dm'):
                msg.status = 'read'
        
        if new_receipts:
            db.session.add_all(new_receipts)
        
        db.session.commit()
        
        # Notify others in the room that messages were read
        emit('messages_read', {
            'user_id': user_id,
            'room_id': room_id,
            'read_at': datetime.utcnow().isoformat()
        }, room=f'room_{room_id}', include_self=False)

    @socketio.on('toggle_reaction')
    def handle_toggle_reaction(data):
        """Toggle an emoji reaction on a message"""
        message_id = data.get('message_id')
        user_id = data.get('user_id')
        emoji = data.get('emoji')

        if not all([message_id, user_id, emoji]):
            return

        message = ChatMessage.query.get(message_id)
        if not message:
            return

        # Toggle: remove if exists, add if not
        existing = MessageReaction.query.filter_by(
            message_id=message_id, user_id=user_id, emoji=emoji
        ).first()

        if existing:
            db.session.delete(existing)
        else:
            db.session.add(MessageReaction(message_id=message_id, user_id=user_id, emoji=emoji))
        db.session.commit()

        # Build updated reactions payload
        all_reactions = MessageReaction.query.filter_by(message_id=message_id).all()
        reaction_map = {}
        for r in all_reactions:
            reaction_map.setdefault(r.emoji, []).append(r.user_id)

        emit('reaction_update', {
            'message_id': message_id,
            'reactions': [{'emoji': e, 'count': len(uids), 'user_ids': uids} for e, uids in reaction_map.items()]
        }, room=f'room_{message.room_id}')

    @socketio.on('send_voice_note')
    def handle_send_voice_note(data):
        """Receive audio blob, transcribe via Groq Whisper, forward to AI"""
        import base64
        import tempfile
        import os

        user_id = data.get('user_id')
        room_id = data.get('room_id')
        audio_data = data.get('audio_data')
        mime_type = data.get('mime_type', 'audio/webm')

        user = ChatUser.query.get(user_id)
        room = ChatRoom.query.get(room_id)

        if not user or not room:
            emit('error', {'message': 'Invalid user or room'})
            return

        if room.room_type != 'ai_dm':
            emit('error', {'message': 'Voice notes are only supported in AI DM.'})
            return

        tmp_path = None
        try:
            # Decode and save audio to temp file
            audio_bytes = base64.b64decode(audio_data)
            ext = '.webm' if 'webm' in mime_type else '.ogg' if 'ogg' in mime_type else '.mp3'
            fd, tmp_path = tempfile.mkstemp(suffix=ext)
            with os.fdopen(fd, 'wb') as f:
                f.write(audio_bytes)

            # Transcribe using Groq Whisper
            from groq import Groq
            from config import Config

            if not Config.GROQ_API_KEY:
                emit('error', {'message': 'AI service not configured.'})
                return

            groq_client = Groq(api_key=Config.GROQ_API_KEY)
            with open(tmp_path, 'rb') as audio_file:
                transcription = groq_client.audio.transcriptions.create(
                    file=(os.path.basename(tmp_path), audio_file, mime_type),
                    model="whisper-large-v3-turbo"
                )

            transcript = transcription.text.strip()
            if not transcript:
                emit('error', {'message': 'Could not transcribe audio. Try again.'})
                return

            # Save the voice note as a visible message
            voice_content = f"🎤 {transcript}"
            voice_msg = ChatMessage(
                room_id=room_id,
                sender_id=user_id,
                content=voice_content,
                message_type='text'
            )
            db.session.add(voice_msg)
            db.session.commit()

            # Emit the voice note message to the room
            emit('new_message', {
                'id': voice_msg.id,
                'room_id': room_id,
                'content': voice_content,
                'sender_id': user_id,
                'sender_name': user.display_name or user.username,
                'sender_pic': user.profile_pic,
                'message_type': 'text',
                'created_at': voice_msg.created_at.isoformat()
            }, room=f'room_{room_id}')

            # Trigger AI response with the transcript
            handle_ai_response(user, room, transcript, socketio)

        except Exception as e:
            print(f"[ERROR] Voice note failed: {e}")
            emit('error', {'message': 'Voice note processing failed. Try again.'})
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    @socketio.on('send_document')
    def handle_send_document(data):
        """Upload a text document to AI memory"""
        import base64

        user_id = data.get('user_id')
        room_id = data.get('room_id')
        filename = data.get('filename', 'document.txt')
        file_data = data.get('file_data')  # base64
        file_size = data.get('file_size', 0)

        user = ChatUser.query.get(user_id)
        room = ChatRoom.query.get(room_id)

        if not user or not room:
            emit('error', {'message': 'Invalid user or room'})
            return

        if room.room_type != 'ai_dm':
            emit('error', {'message': 'Document upload is only supported in AI DM.'})
            return

        # Validate size (2 MB max)
        if file_size > 2 * 1024 * 1024:
            emit('error', {'message': 'Document must be 2 MB or less.'})
            return

        try:
            # Decode content
            content_bytes = base64.b64decode(file_data)
            # Try decoding as UTF-8; reject binary files
            try:
                content_text = content_bytes.decode('utf-8')
            except UnicodeDecodeError:
                emit('error', {'message': 'Only text-based documents are supported (txt, md, csv, etc.).'})
                return

            # Save to AI documents
            doc = AIDocument(user_id=user_id, filename=filename, content=content_text)
            db.session.add(doc)
            db.session.commit()

            # Confirm in chat
            ai_user = get_or_create_ai_user()
            confirm_content = f"📄 Document **{filename}** uploaded and saved to memory."
            confirm_msg = ChatMessage(
                room_id=room_id,
                sender_id=ai_user.id,
                content=confirm_content,
                message_type='ai_response'
            )
            db.session.add(confirm_msg)
            db.session.commit()

            emit('new_message', {
                'id': confirm_msg.id,
                'room_id': room_id,
                'content': confirm_content,
                'sender_id': ai_user.id,
                'sender_name': 'ClassPulse AI',
                'sender_pic': '__bot__',
                'message_type': 'ai_response',
                'created_at': confirm_msg.created_at.isoformat()
            }, room=f'room_{room_id}')

        except Exception as e:
            print(f"[ERROR] Document upload failed: {e}")
            emit('error', {'message': 'Document upload failed. Try again.'})

    @socketio.on('get_teaching_stats')
    def handle_get_teaching_stats(data):
        """Get student activity stats for a teaching group"""
        room_id = data.get('room_id')

        room = ChatRoom.query.get(room_id)
        if not room:
            emit('error', {'message': 'Room not found'})
            return

        # Get teaching session
        from models import TeachingSession
        teach_session = TeachingSession.query.filter_by(room_id=room_id).first()
        if not teach_session:
            emit('teaching_stats', {'room_id': room_id, 'stats': []})
            return

        # Count messages per student (exclude AI and system messages)
        from sqlalchemy import func
        ai_user = get_or_create_ai_user()

        stats_query = db.session.query(
            ChatMessage.sender_id,
            ChatUser.display_name,
            ChatUser.username,
            func.count(ChatMessage.id).label('message_count')
        ).join(ChatUser, ChatMessage.sender_id == ChatUser.id)\
         .filter(ChatMessage.room_id == room_id)\
         .filter(ChatMessage.sender_id != ai_user.id)\
         .filter(ChatMessage.message_type.in_(['text']))\
         .group_by(ChatMessage.sender_id)\
         .order_by(func.count(ChatMessage.id).desc())\
         .limit(10)\
         .all()

        stats = [{
            'user_id': s.sender_id,
            'name': s.display_name or s.username,
            'messages': s.message_count
        } for s in stats_query]

        emit('teaching_stats', {
            'room_id': room_id,
            'topic': teach_session.topic,
            'day': teach_session.current_day,
            'total_days': teach_session.total_days,
            'stats': stats
        })

    @socketio.on('search_messages')
    def handle_search_messages(data):
        """Search for messages containing a query string across all user's rooms"""
        user_id = data.get('user_id')
        query = data.get('query', '').strip()
        
        if not user_id or not query:
            emit('search_results', {'results': []})
            return
            
        # Get all rooms the user is a member of
        user_rooms = db.session.query(ChatMember.room_id).filter_by(user_id=user_id).all()
        room_ids = [r.room_id for r in user_rooms]
        
        # Search messages in those rooms
        messages = ChatMessage.query.filter(
            ChatMessage.room_id.in_(room_ids),
            ChatMessage.content.ilike(f'%{query}%'),
            ChatMessage.message_type != 'deleted'
        ).order_by(ChatMessage.created_at.desc()).limit(50).all()
        
        results = []
        for m in messages:
            results.append({
                'id': m.id,
                'room_id': m.room_id,
                'room_name': m.room.name if m.room.name else (f"AI Assistant" if m.room.room_type == 'ai_dm' else "Direct Message"),
                'room_type': m.room.room_type,
                'content': m.content,
                'sender_name': m.sender.display_name if m.sender else 'System',
                'created_at': m.created_at.isoformat()
            })
            
        emit('search_results', {'results': results})

    @socketio.on('toggle_lock')
    def handle_toggle_lock(data):
        """Admin toggles group lock"""
        user_id = data.get('user_id')
        room_id = data.get('room_id')

        user = ChatUser.query.get(user_id)
        room = ChatRoom.query.get(room_id)
        if not user or not room:
            return

        # Only admin can lock/unlock
        if not user.is_admin():
            membership = ChatMember.query.filter_by(user_id=user_id, room_id=room_id).first()
            if not membership or membership.role != 'admin':
                emit('error', {'message': 'Only the admin can lock/unlock this group.'})
                return

        room.locked = not room.locked
        db.session.commit()

        # Notify all clients in room
        emit('room_lock_update', {
            'room_id': room_id,
            'locked': room.locked
        }, room=f'room_{room_id}')

        # System message
        action = "locked" if room.locked else "unlocked"
        sys_msg = ChatMessage(
            room_id=room_id,
            content=f"🔒 {user.display_name or user.username} {action} this group.",
            message_type='system'
        )
        db.session.add(sys_msg)
        db.session.commit()

        ai_user = get_or_create_ai_user()
        emit('new_message', {
            'id': sys_msg.id,
            'room_id': room_id,
            'content': sys_msg.content,
            'sender_id': ai_user.id,
            'sender_name': 'System',
            'sender_pic': None,
            'message_type': 'system',
            'created_at': sys_msg.created_at.isoformat()
        }, room=f'room_{room_id}')


def handle_group_ai_reply(student, room, student_message, original_ai_msg, student_msg_obj, socketio):
    """
    When a student replies to an AI message in a group chat,
    generate an AI response that sounds like the admin relaying info.
    Keeps replies short and helpful.
    """
    try:
        from groq import Groq
        from config import Config

        if not Config.GROQ_API_KEY:
            return

        # Find the admin (room creator or first admin member)
        admin = None
        admin_member = ChatMember.query.filter_by(room_id=room.id, role='admin').first()
        if admin_member:
            admin = ChatUser.query.get(admin_member.user_id)
        if not admin:
            admin_member = ChatMember.query.filter_by(room_id=room.id).first()
            if admin_member:
                admin = ChatUser.query.get(admin_member.user_id)

        admin_name = admin.display_name or admin.username if admin else "Your Lecturer"

        # Check if this is a teaching group
        from models import TeachingSession
        teach_session = TeachingSession.query.filter_by(room_id=room.id).first()
        teaching_topic = teach_session.topic if teach_session else None

        # Get a few recent messages in the group for context
        recent = ChatMessage.query.filter_by(room_id=room.id)\
            .order_by(ChatMessage.created_at.desc()).limit(8).all()
        context_lines = []
        for m in reversed(recent):
            sender = m.sender.display_name if m.sender else "System"
            if m.message_type in ('system', 'deleted'):
                continue
            context_lines.append(f"{sender}: {m.content[:120]}")

        # Build topic restriction if teaching group
        topic_rules = ""
        if teaching_topic:
            topic_rules = f"""
TEACHING GROUP RULES (this is a teaching session on "{teaching_topic}"):
- ONLY answer questions related to "{teaching_topic}" or closely related topics.
- If the student's question is completely off-topic (not about {teaching_topic}), politely say: "Let's keep this group focused on {teaching_topic} — feel free to ask about that!"
- Stay in teaching mode — helpful, educational, on-topic.
"""

        system_prompt = f"""You are posting in a group chat on behalf of {admin_name}. Write your reply exactly as {admin_name} would — casual, direct, human. The student won't know an AI wrote this unless you give it away, so don't.

STRICT RULES:
- Write as {admin_name}. First person = {admin_name}. No "As {admin_name} says..." or "According to {admin_name}..."
- Max 2 sentences. Cut anything that isn't essential.
- If you can helpfully advise the student, do it in one sentence.
- If you genuinely don't know, say: "I'll get back to you on that one" — nothing more.
- Do NOT invent deadlines, policies, or grades.
- Match the tone of the group — keep it real.
{topic_rules}
IMPORTANT: If the question is something you truly cannot answer (needs admin's real input — like grades, schedule changes, personal matters, or course-specific details you don't have), add [NEED_ADMIN] at the very end of your reply. This will silently notify the admin. Do NOT use this for simple questions you can handle.

GROUP: {room.name}
RECENT CONTEXT:
{chr(10).join(context_lines[-6:]) if context_lines else "No recent messages."}

THE MESSAGE THE STUDENT REPLIED TO:
"{original_ai_msg.content}"

STUDENT ({student.display_name or student.username}) WROTE:
"{student_message}"

Reply now:"""

        ai_user = get_or_create_ai_user()
        # Emit AI typing event
        socketio.emit('typing', {
            'room_id': room.id,
            'user_id': ai_user.id,
            'username': ai_user.username,
            'display_name': ai_user.display_name or ai_user.username
        }, room=f'room_{room.id}')

        groq_client = Groq(api_key=Config.GROQ_API_KEY)
        completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": student_message}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=200
        )

        ai_reply_text = completion.choices[0].message.content

        # Stop AI typing event
        socketio.emit('stop_typing', {
            'room_id': room.id,
            'user_id': ai_user.id
        }, room=f'room_{room.id}')

        # Check if AI flagged this as needing admin attention
        needs_admin = '[NEED_ADMIN]' in ai_reply_text
        ai_reply_text = ai_reply_text.replace('[NEED_ADMIN]', '').strip()

        # Post the AI reply as a reply to the student's message
        ai_user = get_or_create_ai_user()
        ai_msg = ChatMessage(
            room_id=room.id,
            sender_id=ai_user.id,
            content=ai_reply_text,
            message_type='ai_response',
            reply_to_id=student_msg_obj.id
        )
        db.session.add(ai_msg)
        db.session.commit()

        socketio.emit('new_message', {
            'id': ai_msg.id,
            'room_id': room.id,
            'content': ai_reply_text,
            'sender_id': ai_user.id,
            'sender_name': 'ClassPulse AI',
            'sender_pic': '__bot__',
            'message_type': 'ai_response',
            'created_at': ai_msg.created_at.isoformat(),
            'reply_to': {
                'id': student_msg_obj.id,
                'content': student_message[:100],
                'sender_name': student.display_name or student.username
            }
        }, room=f'room_{room.id}')

        print(f"[AI GROUP REPLY] Replied in {room.name} to {student.display_name or student.username}")

        # If flagged, notify the admin in their AI DM
        if needs_admin and admin:
            try:
                # Find or create admin's AI DM
                admin_ai_dm = ChatRoom.query.filter_by(
                    room_type='ai_dm',
                    created_by=admin.id,
                    is_active=True
                ).first()

                if admin_ai_dm:
                    alert_content = f"🔔 **Student question needs your attention**\n\n**Group:** {room.name}\n**Student:** {student.display_name or student.username}\n**Question:** {student_message[:200]}\n\nI gave them a holding response, but this needs your real input."
                    alert_msg = ChatMessage(
                        room_id=admin_ai_dm.id,
                        sender_id=ai_user.id,
                        content=alert_content,
                        message_type='ai_response'
                    )
                    db.session.add(alert_msg)
                    db.session.commit()

                    socketio.emit('new_message', {
                        'id': alert_msg.id,
                        'room_id': admin_ai_dm.id,
                        'content': alert_content,
                        'sender_id': ai_user.id,
                        'sender_name': 'ClassPulse AI',
                        'sender_pic': '__bot__',
                        'message_type': 'ai_response',
                        'created_at': alert_msg.created_at.isoformat()
                    }, room=f'room_{admin_ai_dm.id}')

                    print(f"[AI ALERT] Notified admin about question in {room.name}")
            except Exception as alert_err:
                print(f"[ERROR] Failed to alert admin: {alert_err}")

    except Exception as e:
        print(f"[ERROR] Group AI reply failed: {e}")
        import traceback
        traceback.print_exc()


def parse_broadcast_command(response, groups):
    """
    Parse AI response for broadcast commands
    Format: [BROADCAST:group_name]message content[/BROADCAST]
    Returns list of (group, message) tuples
    """
    import re
    broadcasts = []
    pattern = r'\[BROADCAST:([^\]]+)\](.*?)\[/BROADCAST\]'
    matches = re.findall(pattern, response, re.DOTALL)

    for group_name, message in matches:
        group_name = group_name.strip()
        message = message.strip()

        # Find matching group (case-insensitive)
        for group in groups:
            if group.name.lower() == group_name.lower() or group.invite_code.lower() == group_name.lower():
                broadcasts.append((group, message))
                break

    return broadcasts


def parse_create_group_command(response):
    """Parse [CREATE_GROUP:name|description] commands from AI response"""
    import re
    pattern = r'\[CREATE_GROUP:([^|]+)\|([^\]]*)\]'
    matches = re.findall(pattern, response)
    return [(name.strip(), desc.strip()) for name, desc in matches]


def parse_delete_group_command(response):
    """Parse [DELETE_GROUP:GroupName] commands from AI response"""
    import re
    pattern = r'\[DELETE_GROUP:([^\]]+)\]'
    return re.findall(pattern, response)


def parse_teach_command(response):
    """Parse [TEACH:Topic|Days] commands. Returns list of (topic, days) tuples."""
    import re
    commands = []
    pattern = r'\[TEACH:([^|]+)\|(\d+)\]'
    for match in re.finditer(pattern, response):
        topic = match.group(1).strip()
        days = int(match.group(2))
        if 1 <= days <= 30 and topic:
            commands.append((topic, days))
    return commands


def parse_delete_teach_command(response):
    """Parse [DELETE_TEACH:GroupName] commands. Returns list of group names."""
    import re
    pattern = r'\[DELETE_TEACH:([^\]]+)\]'
    return [m.strip() for m in re.findall(pattern, response)]


def parse_lock_command(response, groups):
    """Parse [LOCK:GroupName] and [UNLOCK:GroupName] commands. Returns list of (group, action) tuples where action is 'lock' or 'unlock'."""
    import re
    commands = []
    for action_tag, action in [('LOCK', 'lock'), ('UNLOCK', 'unlock')]:
        pattern = rf'\[{action_tag}:([^\]]+)\]'
        for match in re.finditer(pattern, response):
            group_name = match.group(1).strip()
            for g in groups:
                if g.name.lower() == group_name.lower() or g.invite_code.lower() == group_name.lower():
                    commands.append((g, action))
                    break
    return commands


def parse_create_course_command(response):
    """Parse [CREATE_COURSE:CourseName|CourseCode] commands. Returns list of (name, code) tuples."""
    import re
    pattern = r'\[CREATE_COURSE:([^|]+)\|([^\]]+)\]'
    commands = []
    for match in re.finditer(pattern, response):
        name = match.group(1).strip()
        code = match.group(2).strip()
        if name and code:
            commands.append((name, code))
    return commands


def parse_create_perm_group_command(response):
    """Parse [CREATE_PERM_GROUP:GroupName] commands. Returns list of group names."""
    import re
    pattern = r'\[CREATE_PERM_GROUP:([^\]]+)\]'
    return [m.strip() for m in re.findall(pattern, response)]


def clean_response_for_display(response):
    """Strip command tags, replace with confirmation notes"""
    import re
    cleaned = re.sub(
        r'\[BROADCAST:([^\]]+)\](.*?)\[/BROADCAST\]',
        r'✅ Sent to \1',
        response,
        flags=re.DOTALL
    )
    cleaned = re.sub(
        r'\[CREATE_GROUP:([^|]+)\|[^\]]*\]',
        r'✅ Group "\1" created',
        cleaned
    )
    cleaned = re.sub(r'\[LOCK:([^\]]+)\]', r'🔒 "\1" locked', cleaned)
    cleaned = re.sub(r'\[UNLOCK:([^\]]+)\]', r'🔓 "\1" unlocked', cleaned)
    cleaned = re.sub(r'\[TEACH:([^|]+)\|(\d+)\]', r'📚 Teaching group for "\1" created (\2 days)', cleaned)
    cleaned = re.sub(r'\[DELETE_TEACH:([^\]]+)\]', '', cleaned)  # Remove tag, stats appended separately
    cleaned = re.sub(r'\[CREATE_COURSE:([^|]+)\|([^\]]+)\]', r'📖 Course "\1" (\2) registered', cleaned)
    cleaned = re.sub(r'\[CREATE_PERM_GROUP:([^\]]+)\]', r'👥 Group "\1" created', cleaned)
    return cleaned.strip()


def handle_ai_response(user, room, user_message, socketio):
    """
    Process admin message and generate AI response
    Uses direct conversational AI - no lecturer account required
    Can actually broadcast messages to groups

    Args:
        user: ChatUser (admin)
        room: ChatRoom (ai_dm type)
        user_message: The message text
        socketio: SocketIO instance for emitting
    """
    try:
        from groq import Groq
        from config import Config

        # Get conversation history for context
        recent_messages = ChatMessage.query.filter_by(room_id=room.id)\
            .order_by(ChatMessage.created_at.desc())\
            .limit(10)\
            .all()

        # Build conversation history
        history = []
        for msg in reversed(recent_messages):
            if msg.message_type == 'ai_response':
                history.append({"role": "assistant", "content": msg.content})
            elif msg.sender_id == user.id:
                history.append({"role": "user", "content": msg.content})

        # Get list of existing courses for context
        courses = Course.query.filter_by(is_active=True).all()
        course_list = ", ".join([f"{c.code}" for c in courses]) if courses else "No courses registered yet"

        # Get chat groups for context
        groups = ChatRoom.query.filter_by(room_type='group', is_active=True).all()
        group_info = []
        for g in groups:
            member_count = ChatMember.query.filter_by(room_id=g.id).count()
            group_info.append(f"{g.name} (code: {g.invite_code}, {member_count} members)")
        group_list = ", ".join(group_info) if group_info else "No groups created yet"

        # Load uploaded documents for context
        uploaded_docs = AIDocument.query.filter_by(user_id=user.id).order_by(AIDocument.uploaded_at.desc()).all()
        docs_section = ""
        if uploaded_docs:
            docs_section = "\n\n=== UPLOADED DOCUMENTS (in memory) ===\n"
            for doc in uploaded_docs:
                # Truncate very large docs to keep prompt manageable
                doc_preview = doc.content[:3000] + ("...[truncated]" if len(doc.content) > 3000 else "")
                docs_section += f"\n--- {doc.filename} (uploaded {doc.uploaded_at.strftime('%Y-%m-%d')}) ---\n{doc_preview}\n"

        # System prompt — adapts based on user role
        role_label = "Admin" if user.role == 'admin' else ("Lecturer" if user.role == 'lecturer' else "Student")
        is_staff = user.role in ['admin', 'lecturer']
        
        system_prompt = f"""You are ClassPulse AI — the intelligent assistant for the ClassPulse education platform. You talk like a smart, direct friend. No corporate speak, no filler.

PERSONALITY:
- Skip the "Sure!" and "Of course!" openers. Just get to the point.
- Be warm but not syrupy. Direct and confident.
- One clear thought per message unless they asked for more.
- Humor when it fits naturally — don't force it.
- When you don't know something, say so plainly.

WHO YOU'RE TALKING TO:
Name: {user.display_name or user.username}
Role: {role_label}
{"(Staff member with management permissions)" if is_staff else "(Student user)"}

PLATFORM STATE:
- Courses: {course_list}
- Groups: {group_list}
{docs_section}

=== SYSTEM COMMANDS ===
You can take actions in the system. Use these tags ONLY when the user asks for them. Place them at the END of your message.

--- BROADCAST (send a message to a group) ---
Format: [BROADCAST:GroupName]message text[/BROADCAST]
- ONLY available for Admin/Lecturers. Write as them, in first person.
- GroupName must match exactly.

--- CREATE GROUP (create a new group chat) ---
Format: [CREATE_GROUP:Group Name|Description]
- ONLY available for Admin/Lecturers.

--- TEACH (create a temporary teaching group) ---
Format: [TEACH:Topic|Days]
- ONLY available for Admin/Lecturers. Starts an AI-led daily teaching session.

--- DELETE GROUP / TEACHING (permanently remove) ---
Format: [DELETE_GROUP:GroupName] or [DELETE_TEACH:GroupName]
- ONLY available for Admin/Lecturers. Use for removing groups or closing sessions early.

--- LOCK / UNLOCK GROUP (management) ---
Format: [LOCK:GroupName] or [UNLOCK:GroupName]
- ONLY available for Admin/Lecturers.

--- CREATE COURSE (registration) ---
Format: [CREATE_COURSE:CourseName|CourseCode]
- ONLY available for Admin/Lecturers.

--- CREATE PERMANENT GROUP ---
Format: [CREATE_PERM_GROUP:GroupName]
- ONLY available for Admin/Lecturers.

=== RULES ===
- Commands go at the END of your reply, after any conversational text.
- Only use a command when the admin actually asks you to do something.
- You can use multiple commands in one response if asked.
- Don't hallucinate group names — stick to what exists.
- Keep the conversational part short and natural."""

        # Initialize Groq client
        ai_user = get_or_create_ai_user()
        if not Config.GROQ_API_KEY:
            response = "I'm having trouble connecting to my brain right now. The AI service isn't configured properly."
        else:
            groq_client = Groq(api_key=Config.GROQ_API_KEY)

            # Build messages for API
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(history[-6:])  # Last 6 messages for context
            messages.append({"role": "user", "content": user_message})

            # Emit AI typing event
            socketio.emit('typing', {
                'room_id': room.id,
                'user_id': ai_user.id,
                'username': ai_user.username,
                'display_name': ai_user.display_name or ai_user.username
            }, room=f'room_{room.id}')

            chat_completion = groq_client.chat.completions.create(
                messages=messages,
                model="llama-3.3-70b-versatile",
                temperature=0.8,
                max_tokens=500
            )

            response = chat_completion.choices[0].message.content

            # Stop AI typing event
            socketio.emit('stop_typing', {
                'room_id': room.id,
                'user_id': ai_user.id
            }, room=f'room_{room.id}')

        # Check for broadcast commands and execute them
        broadcasts = parse_broadcast_command(response, groups)
        broadcast_results = []

        ai_user = get_or_create_ai_user()

        admin_name = user.display_name or user.username

        for target_group, broadcast_message in broadcasts:
            try:
                # AI already wrote it in admin's voice per the prompt — just tag it
                framed_message = f"📢 {broadcast_message}"

                broadcast_msg = ChatMessage(
                    room_id=target_group.id,
                    sender_id=ai_user.id,
                    content=framed_message,
                    message_type='broadcast'
                )
                db.session.add(broadcast_msg)
                db.session.flush()

                # Show as the admin's name so it reads naturally in the group
                socketio.emit('new_message', {
                    'id': broadcast_msg.id,
                    'room_id': target_group.id,
                    'content': framed_message,
                    'sender_id': ai_user.id,
                    'sender_name': admin_name,
                    'sender_pic': user.profile_pic,
                    'message_type': 'broadcast',
                    'created_at': broadcast_msg.created_at.isoformat()
                }, room=f'room_{target_group.id}')

                broadcast_results.append((target_group.name, True))
                print(f"[BROADCAST] Sent to {target_group.name}: {broadcast_message[:50]}...")

            except Exception as e:
                print(f"[ERROR] Failed to broadcast to {target_group.name}: {e}")
                broadcast_results.append((target_group.name, False))

        # Execute CREATE_GROUP commands
        create_group_commands = parse_create_group_command(response)
        created_groups = []

        for group_name, group_desc in create_group_commands:
            try:
                new_room = ChatRoom(
                    name=group_name,
                    description=group_desc,
                    room_type='group',
                    invite_code=generate_invite_code(),
                    created_by=user.id
                )
                db.session.add(new_room)
                db.session.flush()

                # Add admin as member
                member = ChatMember(room_id=new_room.id, user_id=user.id, role='admin')
                db.session.add(member)

                # System message in the new group
                sys_msg = ChatMessage(
                    room_id=new_room.id,
                    content=f"Group created by {user.display_name or user.username}",
                    message_type='system'
                )
                db.session.add(sys_msg)
                db.session.flush()

                created_groups.append((group_name, new_room.invite_code))

                # Push new group to admin's sidebar without navigating away
                socketio.emit('ai_created_group', {
                    'room_id': new_room.id,
                    'name': new_room.name,
                    'invite_code': new_room.invite_code
                }, room=f'room_{room.id}')

                print(f"[AI CREATE_GROUP] Created: {group_name}")
            except Exception as e:
                print(f"[ERROR] Failed to create group '{group_name}': {e}")

        # Execute LOCK / UNLOCK commands
        lock_commands = parse_lock_command(response, groups)
        for target_group, action in lock_commands:
            try:
                target_group.locked = (action == 'lock')
                db.session.commit()
                socketio.emit('room_lock_update', {
                    'room_id': target_group.id,
                    'locked': target_group.locked
                }, room=f'room_{target_group.id}')
            except Exception as e:
                print(f"[ERROR] Failed to toggle lock on '{target_group.name}': {e}")

        # Execute DELETE_GROUP commands
        delete_group_commands = parse_delete_group_command(response)
        for group_name in delete_group_commands:
            try:
                # Find group by name (case-insensitive) or code
                res_group = ChatRoom.query.filter(
                    (ChatRoom.name.ilike(group_name)) |
                    (ChatRoom.invite_code.ilike(group_name))
                ).first()
                
                if res_group:
                    target_id = res_group.id
                    # Notify all members before deletion
                    socketio.emit('room_removed', {'room_id': target_id}, room=f'room_{target_id}')
                    
                    # Delete room (cascade will handle members and messages)
                    db.session.delete(res_group)
                    db.session.commit()
                    print(f"[AI DELETE_GROUP] Deleted: {group_name}")
            except Exception as e:
                print(f"[ERROR] Failed to delete group '{group_name}': {e}")

        # Execute TEACH commands
        from models import TeachingSession
        teach_commands = parse_teach_command(response)
        for topic, days in teach_commands:
            try:
                from datetime import timedelta
                now = datetime.utcnow()
                teach_room = ChatRoom(
                    name=f"📚 {topic}",
                    description=f"AI-led {days}-day teaching session on: {topic}",
                    room_type='group',
                    invite_code=generate_invite_code(),
                    created_by=user.id
                )
                db.session.add(teach_room)
                db.session.flush()

                # Add admin as member
                db.session.add(ChatMember(room_id=teach_room.id, user_id=user.id, role='admin'))

                # Create teaching session record
                session_record = TeachingSession(
                    room_id=teach_room.id,
                    topic=topic,
                    total_days=days,
                    current_day=0,
                    start_date=now,
                    close_date=now + timedelta(days=days),
                    created_by=user.id
                )
                db.session.add(session_record)

                # Welcome message
                welcome = ChatMessage(
                    room_id=teach_room.id,
                    content=f"👋 Welcome! This is a {days}-day AI-led teaching session on **{topic}**.\n\nThe AI will post one lesson each day. Share this group's invite code with your students so they can join!\n\n📅 Day 1 lesson will be posted shortly.",
                    message_type='system'
                )
                db.session.add(welcome)
                db.session.commit()

                # Push to admin sidebar
                socketio.emit('ai_created_group', {
                    'room_id': teach_room.id,
                    'name': teach_room.name,
                    'invite_code': teach_room.invite_code
                }, room=f'room_{room.id}')

                print(f"[AI TEACH] Created teaching group: {topic} ({days} days)")
            except Exception as e:
                print(f"[ERROR] Failed to create teaching group '{topic}': {e}")

        # Execute DELETE_TEACH commands
        from sqlalchemy import func
        delete_teach_commands = parse_delete_teach_command(response)
        deleted_group_stats = []  # Store stats for deleted groups
        for group_name in delete_teach_commands:
            try:
                # Find the teaching group by name (case-insensitive)
                target_room = ChatRoom.query.filter(
                    ChatRoom.name.ilike(f'%{group_name}%'),
                    ChatRoom.is_active == True
                ).first()
                if target_room:
                    # Check if it's a teaching session
                    teach_session = TeachingSession.query.filter_by(room_id=target_room.id).first()
                    if teach_session:
                        # Gather activity stats before closing
                        stats_query = db.session.query(
                            ChatMessage.sender_id,
                            ChatUser.username,
                            func.count(ChatMessage.id).label('msg_count')
                        ).join(ChatUser, ChatMessage.sender_id == ChatUser.id)\
                         .filter(
                            ChatMessage.room_id == target_room.id,
                            ChatMessage.message_type == 'user',
                            ChatUser.role != 'admin'
                         ).group_by(ChatMessage.sender_id, ChatUser.username)\
                         .order_by(func.count(ChatMessage.id).desc())\
                         .limit(5).all()

                        total_messages = ChatMessage.query.filter_by(
                            room_id=target_room.id, message_type='user'
                        ).count()

                        total_students = db.session.query(func.count(func.distinct(ChatMessage.sender_id)))\
                            .filter(ChatMessage.room_id == target_room.id, ChatMessage.message_type == 'user')\
                            .scalar() or 0

                        # Build stats summary
                        stats_summary = {
                            'group_name': target_room.name,
                            'topic': teach_session.topic,
                            'total_messages': total_messages,
                            'total_students': total_students,
                            'top_students': [(s.username, s.msg_count) for s in stats_query]
                        }
                        deleted_group_stats.append(stats_summary)

                        # Deactivate the room
                        target_room.is_active = False
                        db.session.commit()

                        # Emit room_removed to ALL clients so it disappears from sidebar
                        socketio.emit('room_removed', {
                            'room_id': target_room.id
                        })

                        print(f"[AI DELETE_TEACH] Closed teaching group: {target_room.name}")
            except Exception as e:
                print(f"[ERROR] Failed to delete teaching group '{group_name}': {e}")

        # Execute CREATE_COURSE commands
        course_commands = parse_create_course_command(response)
        created_courses = []
        for course_name, course_code in course_commands:
            try:
                # Check if course already exists
                existing = Course.query.filter(
                    (Course.code.ilike(course_code)) | (Course.name.ilike(course_name))
                ).first()
                if existing:
                    print(f"[AI CREATE_COURSE] Course already exists: {course_code}")
                    continue

                # Create the course (linked to admin/lecturer if exists)
                new_course = Course(
                    name=course_name,
                    code=course_code,
                    is_active=True
                )
                db.session.add(new_course)
                db.session.commit()
                created_courses.append((course_name, course_code))
                print(f"[AI CREATE_COURSE] Created course: {course_name} ({course_code})")
            except Exception as e:
                print(f"[ERROR] Failed to create course '{course_name}': {e}")

        # Execute CREATE_PERM_GROUP commands
        perm_group_commands = parse_create_perm_group_command(response)
        created_perm_groups = []
        for group_name in perm_group_commands:
            try:
                # Generate invite code
                import secrets
                invite_code = secrets.token_hex(3).upper()

                # Create permanent group
                new_room = ChatRoom(
                    name=group_name,
                    room_type='group',
                    invite_code=invite_code,
                    created_by=user.id,
                    is_active=True
                )
                db.session.add(new_room)
                db.session.commit()

                # Add admin as member
                admin_member = ChatMember(user_id=user.id, room_id=new_room.id)
                db.session.add(admin_member)
                db.session.commit()

                created_perm_groups.append((group_name, invite_code))

                # Emit to admin's socket so group appears in sidebar
                socketio.emit('group_created', {
                    'room_id': new_room.id,
                    'name': new_room.name,
                    'invite_code': invite_code
                }, room=f'user_{user.id}')

                print(f"[AI CREATE_PERM_GROUP] Created group: {group_name} (code: {invite_code})")
            except Exception as e:
                print(f"[ERROR] Failed to create permanent group '{group_name}': {e}")

        # Clean response for display (replace command tags with confirmation)
        display_response = clean_response_for_display(response)

        # Append invite codes for created groups
        for gname, code in created_groups:
            display_response = display_response.replace(
                f'✅ Group "{gname}" created',
                f'✅ Group "{gname}" created — invite code: {code}'
            )

        # Append invite codes for permanent groups
        for gname, code in created_perm_groups:
            display_response = display_response.replace(
                f'👥 Group "{gname}" created',
                f'👥 Group "{gname}" created — invite code: {code}'
            )

        # Warn about failed broadcasts
        if broadcast_results:
            failed_groups = [name for name, success in broadcast_results if not success]
            if failed_groups:
                display_response += f"\n\n⚠️ Failed to send to: {', '.join(failed_groups)}"

        # Append stats summary for deleted teaching groups
        if deleted_group_stats:
            for stats in deleted_group_stats:
                display_response += f"\n\n🗑️ **{stats['group_name']}** closed.\n"
                display_response += f"📊 **Session Summary:**\n"
                display_response += f"• {stats['total_students']} students participated\n"
                display_response += f"• {stats['total_messages']} total messages\n"
                if stats['top_students']:
                    top_names = ', '.join([f"{name} ({count})" for name, count in stats['top_students'][:3]])
                    display_response += f"• Most active: {top_names}\n"
                display_response += f"_(Ask me for detailed stats if needed)_"

        # Save AI response
        ai_message = ChatMessage(
            room_id=room.id,
            sender_id=ai_user.id,
            content=display_response,
            message_type='ai_response'
        )
        db.session.add(ai_message)
        db.session.commit()

        # Emit AI response
        socketio.emit('new_message', {
            'id': ai_message.id,
            'room_id': room.id,
            'content': display_response,
            'sender_id': ai_user.id,
            'sender_name': 'ClassPulse AI',
            'sender_pic': '__bot__',
            'message_type': 'ai_response',
            'created_at': ai_message.created_at.isoformat()
        }, room=f'room_{room.id}')

    except Exception as e:
        print(f"[ERROR] AI response error: {e}")
        import traceback
        traceback.print_exc()

        # Send error message
        ai_user = get_or_create_ai_user()
        error_msg = ChatMessage(
            room_id=room.id,
            sender_id=ai_user.id,
            content="Oops, something went wrong on my end. Mind trying that again?",
            message_type='ai_response'
        )
        db.session.add(error_msg)
        db.session.commit()

        socketio.emit('new_message', {
            'id': error_msg.id,
            'room_id': room.id,
            'content': error_msg.content,
            'sender_id': ai_user.id,
            'sender_name': 'ClassPulse AI',
            'sender_pic': '__bot__',
            'message_type': 'ai_response',
            'created_at': error_msg.created_at.isoformat()
        }, room=f'room_{room.id}')
