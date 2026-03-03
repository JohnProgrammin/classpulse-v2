"""
Bot Handler for ClassPulse
Handles all WhatsApp message processing - fully conversational, no commands
Uses Meta WhatsApp Cloud API for messaging
"""

from datetime import datetime, timedelta
from models import (
    db, Lecturer, Course, FAQ, Message,
    PendingQuestion, ScheduledMessage, Analytics
)
from ai_engine import generate_smart_response
from config import Config
from conversation_handler import ConversationHandler
from anonymous_handler import detect_anonymous_intent, format_anonymous_notification
from meta_whatsapp import send_whatsapp_message as meta_send_message


def truncate_for_whatsapp(message, max_length=None):
    """
    Truncate message to WhatsApp character limit

    Args:
        message: The message text
        max_length: Maximum length (defaults to config value)

    Returns:
        str: Truncated message
    """
    if max_length is None:
        max_length = Config.WHATSAPP_CHAR_LIMIT

    if not message or len(message) <= max_length:
        return message

    # Leave room for truncation notice
    truncated = message[:max_length - 30]

    # Try to break at a sentence or word boundary
    last_period = truncated.rfind('.')
    last_space = truncated.rfind(' ')

    if last_period > max_length * 0.7:
        truncated = truncated[:last_period + 1]
    elif last_space > max_length * 0.7:
        truncated = truncated[:last_space]

    return truncated + "\n\n[Message truncated]"


def send_whatsapp_message(to_number, message_text):
    """Send a WhatsApp message via Meta Cloud API"""
    # Ensure message doesn't exceed WhatsApp limits
    message_text = truncate_for_whatsapp(message_text)

    # Use Meta API
    return meta_send_message(to_number, message_text)


def log_message(course_id, sender_phone, message_type, content):
    """Log message to database for analytics"""
    message = Message(
        course_id=course_id,
        sender_phone=sender_phone,
        message_type=message_type,
        content=content
    )
    db.session.add(message)
    db.session.commit()


def track_analytics(course_id, metric_type):
    """Track analytics event"""
    analytics = Analytics(
        course_id=course_id,
        metric_type=metric_type
    )
    db.session.add(analytics)
    db.session.commit()


def handle_lecturer_dm(lecturer, message_text, message_type='text'):
    """
    Handle direct messages from lecturers using conversational AI

    All interactions are conversational - no commands required.
    The AI understands natural language for all actions.

    Args:
        lecturer: Lecturer model instance
        message_text: The message content
        message_type: 'text' or 'voice' (for tracking)

    Returns:
        str: Response text
    """
    try:
        # Find lecturer's most recent active course for context
        course = Course.query.filter_by(
            lecturer_id=lecturer.id,
            is_active=True
        ).order_by(Course.created_at.desc()).first()

        # Create conversation handler
        handler = ConversationHandler(lecturer, course)

        # Process message conversationally
        response = handler.process_message(message_text)

        # Apply WhatsApp character limit
        return truncate_for_whatsapp(response)

    except Exception as e:
        print(f"[ERROR] Conversation handler error: {e}")
        import traceback
        traceback.print_exc()

        # Friendly error response
        return "I'm having trouble processing that right now. Could you try rephrasing?"


def handle_group_message(group_id, message_text, sender_phone=None, message_type='text'):
    """
    Handle messages from student groups with anonymous question support

    Args:
        group_id: WhatsApp group ID
        message_text: The message content
        sender_phone: Student's phone number
        message_type: 'text' or 'voice' (for tracking)

    Returns:
        str: Response text or None
    """
    # Find which course this group belongs to
    course = Course.query.filter_by(group_id=group_id, is_active=True).first()

    if not course:
        return None  # Not a registered group

    msg_lower = message_text.lower().strip()

    # Ignore common non-question messages
    ignore_phrases = ['ok', 'okay', 'thanks', 'thank you', 'noted', 'alright', 'sure', 'yes', 'no', 'cool', 'nice']
    if msg_lower in ignore_phrases:
        return None

    # Detect if this is an anonymous question
    is_anonymous, clean_message = detect_anonymous_intent(message_text)

    if is_anonymous:
        print(f"[ANON] Anonymous question detected from {sender_phone}")

    # Try to generate a smart response using the cleaned message
    response, response_type = generate_smart_response(clean_message, course)

    if response_type == 'faq_match':
        track_analytics(course.id, 'faq_matched')
        return truncate_for_whatsapp(f"[AI] {response}")

    elif response_type == 'context_aware_response':
        track_analytics(course.id, 'context_response_given')
        return truncate_for_whatsapp(f"[AI] {response}")

    elif response_type == 'ai_response':
        track_analytics(course.id, 'ai_response_given')
        return truncate_for_whatsapp(f"[AI] {response}\n\n(AI-generated response)")

    elif response_type == 'off_topic':
        track_analytics(course.id, 'off_topic_filtered')
        return response  # Usually "..."

    elif response_type == 'forward_to_lecturer':
        # Create pending question with anonymous flag
        pending = PendingQuestion(
            course_id=course.id,
            student_phone=sender_phone if not is_anonymous else None,
            student_name="Anonymous" if is_anonymous else "Student",
            question=clean_message,
            is_anonymous=is_anonymous,
            original_message_type=message_type
        )
        db.session.add(pending)
        db.session.commit()

        # Notify lecturer
        lecturer = course.lecturer

        if is_anonymous:
            notification = format_anonymous_notification(
                clean_message,
                course.code,
                course.name
            )
        else:
            notification = f"""[QUESTION] New question in {course.code}:

"{clean_message}"

Reply to answer this question."""

        send_whatsapp_message(lecturer.phone_number, notification)
        track_analytics(course.id, 'question_forwarded')

        if is_anonymous:
            return "I've forwarded your question to the lecturer anonymously. You'll see the answer here when they respond!"
        else:
            return "I've forwarded your question to the lecturer. You'll get a response soon!"

    return None


def process_scheduled_messages():
    """
    Called by scheduler to send pending messages
    """
    now = datetime.utcnow()

    pending_messages = ScheduledMessage.query.filter(
        ScheduledMessage.status == 'pending',
        ScheduledMessage.scheduled_time <= now
    ).all()

    for msg in pending_messages:
        course = Course.query.get(msg.course_id)

        if course and course.group_id:
            full_message = f"[SCHEDULED] Scheduled Message:\n\n{msg.message}"

            if send_whatsapp_message(course.group_id, full_message):
                msg.status = 'sent'
                msg.sent_at = datetime.utcnow()
                log_message(course.id, course.lecturer.phone_number, 'scheduled', msg.message)
                print(f"[OK] Sent scheduled message for {course.code}")
            else:
                print(f"[ERROR] Failed to send scheduled message for {course.code}")

    db.session.commit()
