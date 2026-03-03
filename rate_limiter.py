"""
Rate Limiter for ClassPulse
Sliding window rate limiting with database persistence
"""

from datetime import datetime, timedelta
from models import db, RateLimitRecord
from config import Config


class RateLimiter:
    """
    Sliding window rate limiter for WhatsApp messages
    """

    def __init__(self):
        self.max_messages = Config.RATE_LIMIT_MESSAGES
        self.window_seconds = Config.RATE_LIMIT_WINDOW_SECONDS
        self.block_duration = Config.RATE_LIMIT_BLOCK_DURATION
        self.enabled = Config.RATE_LIMITING_ENABLED

    def is_allowed(self, phone_number):
        """
        Check if user can send a message

        Args:
            phone_number: User's phone number

        Returns:
            tuple: (allowed: bool, wait_seconds: int or None)
        """
        if not self.enabled:
            return True, None

        record = RateLimitRecord.query.filter_by(phone_number=phone_number).first()
        now = datetime.utcnow()

        if not record:
            # First message from this user
            record = RateLimitRecord(
                phone_number=phone_number,
                window_start=now,
                message_count=1
            )
            db.session.add(record)
            db.session.commit()
            return True, None

        # Check if blocked
        if record.is_blocked and record.blocked_until:
            if now < record.blocked_until:
                wait_seconds = int((record.blocked_until - now).total_seconds())
                return False, wait_seconds
            else:
                # Unblock
                record.is_blocked = False
                record.blocked_until = None

        # Check if window expired
        window_end = record.window_start + timedelta(seconds=self.window_seconds)

        if now > window_end:
            # Reset window
            record.window_start = now
            record.message_count = 1
            db.session.commit()
            return True, None

        # Check if within limit
        if record.message_count < self.max_messages:
            record.message_count += 1
            db.session.commit()
            return True, None

        # Rate limit exceeded
        record.violations += 1
        record.last_violation = now

        # Block if repeated violations (3+ in succession)
        if record.violations >= 3:
            record.is_blocked = True
            record.blocked_until = now + timedelta(seconds=self.block_duration)
            db.session.commit()
            return False, self.block_duration

        db.session.commit()

        wait_seconds = int((window_end - now).total_seconds())
        return False, max(1, wait_seconds)

    def get_remaining_messages(self, phone_number):
        """Get how many messages user can still send in current window"""
        if not self.enabled:
            return self.max_messages

        record = RateLimitRecord.query.filter_by(phone_number=phone_number).first()

        if not record:
            return self.max_messages

        now = datetime.utcnow()
        window_end = record.window_start + timedelta(seconds=self.window_seconds)

        if now > window_end:
            return self.max_messages

        return max(0, self.max_messages - record.message_count)

    def reset_violations(self, phone_number):
        """Reset violation count for a user (admin function)"""
        record = RateLimitRecord.query.filter_by(phone_number=phone_number).first()
        if record:
            record.violations = 0
            record.is_blocked = False
            record.blocked_until = None
            db.session.commit()

    def unblock_user(self, phone_number):
        """Immediately unblock a user (admin function)"""
        record = RateLimitRecord.query.filter_by(phone_number=phone_number).first()
        if record:
            record.is_blocked = False
            record.blocked_until = None
            db.session.commit()


class TokenBudgetTracker:
    """
    Optional daily token budget tracking
    """

    def __init__(self):
        self.daily_budget = Config.DAILY_TOKEN_BUDGET
        self.enabled = Config.TOKEN_BUDGET_ENABLED

    def can_consume(self, phone_number, tokens_needed):
        """Check if user has enough token budget"""
        if not self.enabled:
            return True

        record = RateLimitRecord.query.filter_by(phone_number=phone_number).first()
        today = datetime.utcnow().date()

        if not record:
            return True

        # Reset daily count if new day
        if record.token_reset_date != today:
            record.daily_tokens_used = 0
            record.token_reset_date = today
            db.session.commit()

        return record.daily_tokens_used + tokens_needed <= self.daily_budget

    def consume_tokens(self, phone_number, tokens_used):
        """Track token consumption"""
        if not self.enabled:
            return True

        record = RateLimitRecord.query.filter_by(phone_number=phone_number).first()
        today = datetime.utcnow().date()

        if not record:
            # Create record if doesn't exist
            record = RateLimitRecord(
                phone_number=phone_number,
                daily_tokens_used=tokens_used,
                token_reset_date=today
            )
            db.session.add(record)
            db.session.commit()
            return True

        # Reset daily count if new day
        if record.token_reset_date != today:
            record.daily_tokens_used = 0
            record.token_reset_date = today

        # Check budget
        if record.daily_tokens_used + tokens_used > self.daily_budget:
            return False

        record.daily_tokens_used += tokens_used
        db.session.commit()
        return True

    def get_remaining_budget(self, phone_number):
        """Get remaining token budget for today"""
        if not self.enabled:
            return float('inf')

        record = RateLimitRecord.query.filter_by(phone_number=phone_number).first()
        today = datetime.utcnow().date()

        if not record:
            return self.daily_budget

        if record.token_reset_date != today:
            return self.daily_budget

        return max(0, self.daily_budget - record.daily_tokens_used)


# Helper function for rate limit response message
def get_rate_limit_message(wait_seconds):
    """Generate user-friendly rate limit message"""
    if wait_seconds > 60:
        minutes = wait_seconds // 60
        return f"You're sending messages too quickly. Please wait {minutes} minute{'s' if minutes > 1 else ''} before sending another message."
    else:
        return f"You're sending messages too quickly. Please wait {wait_seconds} seconds before sending another message."
