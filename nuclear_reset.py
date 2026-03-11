from app import app
from models import (
    db, Lecturer, Course, FAQ, PendingQuestion, ScheduledMessage, Message, Analytics,
    ChatUser, ChatRoom, ChatMember, ChatMessage, Notification, ExportLog, 
    ConversationHistory, CourseContext, AIPersonalityConfig, RateLimitRecord,
    VoiceTranscription, MessageReadReceipt, Assignment, AssignmentSubmission
)

def nuclear_reset():
    with app.app_context():
        print("[NUCLEAR] Deleting all data from tables...")
        try:
            # Order matters for foreign keys, but we'll try to disable checks if possible
            # or just delete in a sensible order
            
            # Submissions/Receipts first
            AssignmentSubmission.query.delete()
            MessageReadReceipt.query.delete()
            
            # Secondary models
            Assignment.query.delete()
            ChatMessage.query.delete()
            ChatMember.query.delete()
            ChatRoom.query.delete()
            ChatUser.query.delete()
            
            FAQ.query.delete()
            PendingQuestion.query.delete()
            ScheduledMessage.query.delete()
            Message.query.delete()
            Analytics.query.delete()
            Notification.query.delete()
            ExportLog.query.delete()
            ConversationHistory.query.delete()
            CourseContext.query.delete()
            AIPersonalityConfig.query.delete()
            RateLimitRecord.query.delete()
            VoiceTranscription.query.delete()
            
            # Finally core models
            Course.query.delete()
            Lecturer.query.delete()
            
            db.session.commit()
            print("[SUCCESS] All data cleared.")
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] Deletion failed: {e}")
            print("\n[TIP] If the database is locked, please temporarily stop 'python app.py' and try again.")

if __name__ == "__main__":
    nuclear_reset()
