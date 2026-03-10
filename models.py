from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import secrets

db = SQLAlchemy()

class Lecturer(UserMixin, db.Model):
    __tablename__ = 'lecturers'
    
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(255))
    
    # New fields for Phase 2
    university = db.Column(db.String(200))
    department = db.Column(db.String(200))
    bio = db.Column(db.Text)
    profile_image = db.Column(db.String(255))
    
    # Preferences
    email_notifications = db.Column(db.Boolean, default=True)
    weekly_reports = db.Column(db.Boolean, default=True)
    timezone = db.Column(db.String(50), default='UTC')
    
    # Security
    email_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(100))
    reset_token = db.Column(db.String(100))
    reset_token_expires = db.Column(db.DateTime)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Relationships handled by ChatUser now
    pass
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)
    
    def generate_verification_token(self):
        self.verification_token = secrets.token_urlsafe(32)
        return self.verification_token
    
    def generate_reset_token(self):
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expires = datetime.utcnow() + timedelta(hours=24)
        return self.reset_token
    
    def __repr__(self):
        return f'<Lecturer {self.name}>'


class Course(db.Model):
    __tablename__ = 'courses'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(200))
    description = db.Column(db.Text)
    group_id = db.Column(db.String(100), unique=True, index=True)
    lecturer_id = db.Column(db.Integer, db.ForeignKey('chat_users.id'), nullable=False)

    # New fields
    semester = db.Column(db.String(50))
    year = db.Column(db.Integer)
    student_count = db.Column(db.Integer, default=0)

    # Conversational AI fields
    conversation_summary = db.Column(db.Text)  # AI-generated course summary
    last_summary_update = db.Column(db.DateTime)
    total_conversations = db.Column(db.Integer, default=0)

    is_active = db.Column(db.Boolean, default=True)
    is_archived = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    faqs = db.relationship('FAQ', backref='course', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('Message', backref='course', lazy=True, cascade='all, delete-orphan')
    pending_questions = db.relationship('PendingQuestion', backref='course', lazy=True, cascade='all, delete-orphan')
    scheduled_messages = db.relationship('ScheduledMessage', backref='course', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Course {self.code}>'


class FAQ(db.Model):
    __tablename__ = 'faqs'
    
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    
    # Analytics
    times_matched = db.Column(db.Integer, default=0)
    last_matched = db.Column(db.DateTime)
    confidence_score = db.Column(db.Float, default=0.0)
    
    # Categorization
    category = db.Column(db.String(50))
    tags = db.Column(db.String(255))
    
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<FAQ {self.question[:30]}...>'


class Message(db.Model):
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    sender_phone = db.Column(db.String(50))
    sender_name = db.Column(db.String(100))
    message_type = db.Column(db.String(20))  # 'broadcast', 'scheduled', 'question', 'answer', 'ai_response'
    content = db.Column(db.Text, nullable=False)

    # Conversation tracking (new for conversational AI)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation_history.id'))
    response_strategy = db.Column(db.String(30))  # 'faq_match', 'context_search', 'ai_generation'
    context_used = db.Column(db.JSON)  # IDs of conversation history used

    # Delivery tracking
    status = db.Column(db.String(20), default='sent')  # 'sent', 'delivered', 'read', 'failed'
    delivery_time = db.Column(db.DateTime)
    read_time = db.Column(db.DateTime)

    sent_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Message {self.message_type} - {self.sent_at}>'


class PendingQuestion(db.Model):
    __tablename__ = 'pending_questions'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    student_phone = db.Column(db.String(50))
    student_name = db.Column(db.String(100), default='Student')
    question = db.Column(db.Text, nullable=False)

    # Anonymous support
    is_anonymous = db.Column(db.Boolean, default=False)
    original_message_type = db.Column(db.String(20), default='text')  # 'text', 'voice'

    # Priority and categorization
    priority = db.Column(db.String(20), default='normal')  # 'low', 'normal', 'high', 'urgent'
    category = db.Column(db.String(50))

    status = db.Column(db.String(20), default='pending')  # 'pending', 'answered', 'dismissed', 'forwarded'
    asked_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    answered_at = db.Column(db.DateTime)
    answer_text = db.Column(db.Text)

    # Notifications
    email_sent = db.Column(db.Boolean, default=False)
    email_sent_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<PendingQuestion {self.question[:30]}...>'


class ScheduledMessage(db.Model):
    __tablename__ = 'scheduled_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    scheduled_time = db.Column(db.DateTime, nullable=False, index=True)
    
    # Recurrence
    is_recurring = db.Column(db.Boolean, default=False)
    recurrence_pattern = db.Column(db.String(50))  # 'daily', 'weekly', 'monthly'
    recurrence_end = db.Column(db.DateTime)
    
    status = db.Column(db.String(20), default='pending')  # 'pending', 'sent', 'cancelled', 'failed'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_at = db.Column(db.DateTime)
    
    def __repr__(self):
        return f'<ScheduledMessage {self.scheduled_time}>'


class Analytics(db.Model):
    __tablename__ = 'analytics'
    
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    
    metric_type = db.Column(db.String(50), index=True)  
    # Types: 'message_sent', 'question_asked', 'faq_matched', 'ai_response', 'student_joined', 'engagement'
    
    value = db.Column(db.Integer, default=1)
    extra_data = db.Column(db.Text)  # JSON string for extra data
    
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    date = db.Column(db.Date, default=lambda: datetime.utcnow().date(), index=True)
    hour = db.Column(db.Integer, default=lambda: datetime.utcnow().hour)
    
    def __repr__(self):
        return f'<Analytics {self.metric_type}>'


class Notification(db.Model):
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    lecturer_id = db.Column(db.Integer, db.ForeignKey('lecturers.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))
    
    notification_type = db.Column(db.String(50))  # 'question', 'milestone', 'system', 'warning'
    title = db.Column(db.String(200))
    message = db.Column(db.Text)
    link = db.Column(db.String(255))
    
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    read_at = db.Column(db.DateTime)
    
    def __repr__(self):
        return f'<Notification {self.title}>'


class ExportLog(db.Model):
    __tablename__ = 'export_logs'

    id = db.Column(db.Integer, primary_key=True)
    lecturer_id = db.Column(db.Integer, db.ForeignKey('lecturers.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))

    export_type = db.Column(db.String(20))  # 'csv', 'pdf', 'excel'
    data_type = db.Column(db.String(50))  # 'messages', 'analytics', 'faqs', 'questions'
    file_path = db.Column(db.String(255))
    file_size = db.Column(db.Integer)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    downloaded = db.Column(db.Boolean, default=False)
    downloaded_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<ExportLog {self.export_type} - {self.data_type}>'


class ConversationHistory(db.Model):
    __tablename__ = 'conversation_history'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    lecturer_id = db.Column(db.Integer, db.ForeignKey('lecturers.id'), nullable=False)

    # Message content
    role = db.Column(db.String(20))  # 'lecturer', 'ai'
    message = db.Column(db.Text, nullable=False)

    # Intent classification
    detected_intent = db.Column(db.String(50))  # 'register_course', 'broadcast', 'casual_info', etc.
    intent_confidence = db.Column(db.Float, default=0.0)
    extracted_params = db.Column(db.JSON)  # Store structured parameters

    # Semantic search
    message_embedding = db.Column(db.LargeBinary)  # numpy array serialized

    # Threading
    thread_id = db.Column(db.String(50), index=True)  # Groups related messages
    parent_message_id = db.Column(db.Integer, db.ForeignKey('conversation_history.id'))

    # Analytics
    was_used_in_response = db.Column(db.Boolean, default=False)
    times_referenced = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f'<ConversationHistory {self.role} - {self.created_at}>'


class CourseContext(db.Model):
    __tablename__ = 'course_context'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)

    # Structured information
    context_type = db.Column(db.String(50))  # 'exam_info', 'assignment', 'venue', 'policy', etc.
    key = db.Column(db.String(100))  # e.g., 'midterm_date', 'late_submission_policy'
    value = db.Column(db.Text)

    # Source tracking
    source_conversation_id = db.Column(db.Integer, db.ForeignKey('conversation_history.id'))
    extracted_at = db.Column(db.DateTime, default=datetime.utcnow)
    confidence_score = db.Column(db.Float, default=1.0)

    # Metadata
    is_active = db.Column(db.Boolean, default=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<CourseContext {self.context_type}: {self.key}>'


class AIPersonalityConfig(db.Model):
    __tablename__ = 'ai_personality_config'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False, unique=True)

    # Personality settings
    tone = db.Column(db.String(50), default='professional_warm')  # 'formal', 'casual', etc.
    max_response_sentences = db.Column(db.Integer, default=3)
    curiosity_enabled = db.Column(db.Boolean, default=True)

    # Filter preferences
    filtered_topics = db.Column(db.JSON)  # ["sports", "politics", "personal_questions"]
    off_topic_response = db.Column(db.String(50), default='...')

    # Custom instructions
    custom_system_prompt = db.Column(db.Text)
    custom_style_notes = db.Column(db.Text)

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<AIPersonalityConfig Course: {self.course_id}>'


class RateLimitRecord(db.Model):
    """Track message rate limits per user"""
    __tablename__ = 'rate_limit_records'

    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(50), nullable=False, unique=True, index=True)

    # Sliding window tracking
    window_start = db.Column(db.DateTime, default=datetime.utcnow)
    message_count = db.Column(db.Integer, default=0)

    # Daily token tracking (optional)
    daily_tokens_used = db.Column(db.Integer, default=0)
    token_reset_date = db.Column(db.Date, default=lambda: datetime.utcnow().date())

    # Violation tracking
    violations = db.Column(db.Integer, default=0)
    last_violation = db.Column(db.DateTime)
    is_blocked = db.Column(db.Boolean, default=False)
    blocked_until = db.Column(db.DateTime)

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<RateLimitRecord {self.phone_number}>'


class VoiceTranscription(db.Model):
    """Log voice note transcriptions"""
    __tablename__ = 'voice_transcriptions'

    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(50), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))

    # Media info
    media_url = db.Column(db.String(500))
    media_content_type = db.Column(db.String(100))
    duration_seconds = db.Column(db.Float)

    # Transcription
    transcribed_text = db.Column(db.Text)
    transcription_confidence = db.Column(db.Float)

    # Processing status
    status = db.Column(db.String(20), default='pending')  # 'pending', 'completed', 'failed'
    error_message = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    processed_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<VoiceTranscription {self.status} - {self.created_at}>'


# ==========================================
# WEB CHAT SYSTEM MODELS
# ==========================================

class ChatUser(UserMixin, db.Model):
    """Users for the web chat system (separate from Lecturers)"""
    __tablename__ = 'chat_users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(100))
    profile_pic = db.Column(db.String(255))   # relative path inside static/, e.g. uploads/avatars/1_…​.jpg
    bio = db.Column(db.Text)

    # Role: 'admin', 'user'
    role = db.Column(db.String(20), default='user')

    # Status
    is_active = db.Column(db.Boolean, default=True)
    is_online = db.Column(db.Boolean, default=False)
    last_seen = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    memberships = db.relationship('ChatMember', backref='user', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('ChatMessage', backref='sender', lazy=True, cascade='all, delete-orphan')
    courses = db.relationship('Course', backref='creator', lazy=True)  # Link to courses created/managed by this user

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == 'admin'

    def is_lecturer(self):
        return self.role in ['lecturer', 'admin', 'system']

    def is_staff(self):
        return self.role in ['lecturer', 'admin', 'system']

    def is_student(self):
        return self.role == 'student'

    def __repr__(self):
        return f'<ChatUser {self.username}>'


class ChatRoom(db.Model):
    """Chat rooms (groups and DMs)"""
    __tablename__ = 'chat_rooms'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    description = db.Column(db.Text)

    # Room type: 'group', 'dm', 'ai_dm'
    room_type = db.Column(db.String(20), nullable=False, default='group')

    # Invite code for groups (e.g., 'ABC123')
    invite_code = db.Column(db.String(10), unique=True, index=True)

    # Creator (admin who made the room)
    created_by = db.Column(db.Integer, db.ForeignKey('chat_users.id'))

    # Link to course (optional - for broadcasting)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))

    profile_pic = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    locked = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    members = db.relationship('ChatMember', backref='room', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('ChatMessage', backref='room', lazy=True, cascade='all, delete-orphan')
    teaching_session = db.relationship('TeachingSession', backref='room', lazy=True, cascade='all, delete-orphan', uselist=False)
    assignments = db.relationship('Assignment', backref='room', lazy=True, cascade='all, delete-orphan')
    creator = db.relationship('ChatUser', foreign_keys=[created_by])

    def __repr__(self):
        return f'<ChatRoom {self.name or self.id}>'


class ChatMember(db.Model):
    """Room membership"""
    __tablename__ = 'chat_members'

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('chat_rooms.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('chat_users.id'), nullable=False)

    # Role in room: 'admin', 'member'
    role = db.Column(db.String(20), default='member')

    # Notifications
    muted = db.Column(db.Boolean, default=False)
    last_read_at = db.Column(db.DateTime)

    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('room_id', 'user_id', name='unique_room_member'),
    )

    def __repr__(self):
        return f'<ChatMember room={self.room_id} user={self.user_id}>'


class ChatMessage(db.Model):
    """Chat messages"""
    __tablename__ = 'chat_messages'

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('chat_rooms.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('chat_users.id'))  # NULL for system/AI messages

    # Message content
    content = db.Column(db.Text, nullable=False)

    # Message type: 'text', 'system', 'ai_response', 'broadcast', 'deleted'
    message_type = db.Column(db.String(20), default='text')

    # For AI responses - track which course it relates to
    related_course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))

    # Reply functionality
    reply_to_id = db.Column(db.Integer, db.ForeignKey('chat_messages.id'))
    reply_to = db.relationship('ChatMessage', remote_side=[id], backref='replies')

    # Metadata
    is_edited = db.Column(db.Boolean, default=False)
    edited_at = db.Column(db.DateTime)

    # Status: 'sent', 'delivered', 'read'
    status = db.Column(db.String(20), default='sent')

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f'<ChatMessage {self.id} in room {self.room_id}>'


# MessageReaction removed per user request


class AIDocument(db.Model):
    """Documents uploaded by admin to AI — persisted in memory until deleted"""
    __tablename__ = 'ai_documents'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('chat_users.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('ChatUser')

    def __repr__(self):
        return f'<AIDocument {self.filename}>'


class TeachingSession(db.Model):
    """Temporary teaching group — AI teaches day-by-day, auto-closes after N days"""
    __tablename__ = 'teaching_sessions'

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('chat_rooms.id'), nullable=False)
    topic = db.Column(db.Text, nullable=False)
    total_days = db.Column(db.Integer, nullable=False)
    current_day = db.Column(db.Integer, default=0)  # lessons posted so far
    start_date = db.Column(db.DateTime, nullable=False)
    close_date = db.Column(db.DateTime, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('chat_users.id'))

    creator = db.relationship('ChatUser')

    def __repr__(self):
        return f'<TeachingSession {self.id}>'


class MessageReadReceipt(db.Model):
    """Tracks who has read which message"""
    __tablename__ = 'message_read_receipts'
    
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('chat_messages.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('chat_users.id'), nullable=False)
    read_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship for convenience
    message = db.relationship('ChatMessage', backref=db.backref('read_receipts', lazy='dynamic'))
    user = db.relationship('ChatUser', backref=db.backref('read_receipts', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('message_id', 'user_id', name='unique_user_message_read'),
    )

    def __repr__(self):
        return f'<ReadReceipt msg:{self.message_id} user:{self.user_id}>'


class Assignment(db.Model):
    """Assignments posted by lecturers in groups"""
    __tablename__ = 'assignments'

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('chat_rooms.id'), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('chat_users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    due_date = db.Column(db.DateTime)
    
    # Document attached to assignment (optional)
    document_filename = db.Column(db.String(255))
    document_path = db.Column(db.String(255))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    submissions = db.relationship('AssignmentSubmission', backref='assignment', lazy=True, cascade='all, delete-orphan')
    creator_rel = db.relationship('ChatUser', foreign_keys=[creator_id])

    def __repr__(self):
        return f'<Assignment {self.title}>'


class AssignmentSubmission(db.Model):
    """Student submissions for assignments"""
    __tablename__ = 'assignment_submissions'

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignments.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('chat_users.id'), nullable=False)
    
    # Submission content
    content = db.Column(db.Text)
    document_filename = db.Column(db.String(255))
    document_path = db.Column(db.String(255))

    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    grade = db.Column(db.String(10))
    feedback = db.Column(db.Text)

    student = db.relationship('ChatUser', backref=db.backref('submissions', lazy=True))

    def __repr__(self):
        return f'<Submission for Assignment {self.assignment_id} by Student {self.student_id}>'