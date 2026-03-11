from datetime import datetime, timedelta
from models import db, ChatRoom, ChatMember, ChatMessage, Course, TeachingSession, ChatUser
import secrets

class ActionEngine:
    @staticmethod
    def create_group(lecturer_id, name, description="", course_id=None):
        """Create a new group chat"""
        # Verification: course_id check if provided
        if course_id:
            course = Course.query.get(course_id)
            if not course or course.lecturer_id != lecturer_id:
                return False, "Unauthorized or course not found."

        # Generate unique invite code
        invite_code = secrets.token_hex(3).upper()
        
        room = ChatRoom(
            name=name,
            description=description,
            room_type='group',
            invite_code=invite_code,
            created_by=lecturer_id,
            course_id=course_id
        )
        db.session.add(room)
        db.session.flush()

        # Add lecturer as admin
        member = ChatMember(room_id=room.id, user_id=lecturer_id, role='admin')
        db.session.add(member)
        
        db.session.commit()
        return True, f"Group '{name}' created with invite code: {invite_code}"

    @staticmethod
    def lock_group(lecturer_id, room_id, lock=True):
        """Lock or unlock a group chat"""
        room = ChatRoom.query.get(room_id)
        if not room or room.created_by != lecturer_id:
            return False, "Group not found or unauthorized."
        
        room.locked = lock
        db.session.commit()
        
        status = "locked" if lock else "unlocked"
        return True, f"Group '{room.name}' has been {status}."

    @staticmethod
    def create_teaching_session(lecturer_id, room_id, topic, days):
        """Turn a group into a teaching session"""
        room = ChatRoom.query.get(room_id)
        if not room or room.created_by != lecturer_id:
            return False, "Group not found or unauthorized."
        
        start_date = datetime.utcnow()
        close_date = start_date + timedelta(days=days)
        
        session = TeachingSession(
            room_id=room.id,
            topic=topic,
            total_days=days,
            start_date=start_date,
            close_date=close_date,
            created_by=lecturer_id
        )
        db.session.add(session)
        db.session.commit()
        return True, f"Teaching session on '{topic}' scheduled for {days} days."

    @staticmethod
    def send_broadcast(lecturer_id, room_id, message):
        """Send a message to a group on behalf of the lecturer"""
        room = ChatRoom.query.get(room_id)
        if not room:
            return False, "Room not found."
            
        # Check membership
        member = ChatMember.query.filter_by(room_id=room_id, user_id=lecturer_id).first()
        if not member or member.role != 'admin':
            return False, "Unauthorized to broadcast in this room."

        msg = ChatMessage(
            room_id=room_id,
            sender_id=lecturer_id,
            content=message,
            message_type='broadcast'
        )
        db.session.add(msg)
        db.session.commit()
        return True, f"Message broadcasted to '{room.name}'."

    @staticmethod
    def delete_group(lecturer_id, room_id):
        """Permanently delete a group"""
        room = ChatRoom.query.get(room_id)
        if not room or room.created_by != lecturer_id:
            return False, "Group not found or unauthorized."
        
        db.session.delete(room)
        db.session.commit()
        return True, "Group deleted successfully."
