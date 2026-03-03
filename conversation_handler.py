import json
import re
from datetime import datetime, timedelta
from models import db, Course, Lecturer, PendingQuestion, FAQ
from intent_engine import IntentClassifier
from conversation_engine import ConversationMemory, ContextBuilder
from personality_engine import AIPersonality
from config import Config
from groq import Groq

# Initialize Groq client
groq_client = None
if Config.GROQ_API_KEY:
    groq_client = Groq(api_key=Config.GROQ_API_KEY)


class ConversationHandler:
    """
    Handles natural language interactions with lecturers
    Orchestrates intent classification, conversation memory, and personality
    """

    def __init__(self, lecturer, course=None):
        self.lecturer = lecturer
        self.course = course
        self.intent_classifier = IntentClassifier()

        # Initialize components if course is available
        if course:
            self.memory = ConversationMemory(course.id)
            self.personality = AIPersonality(course.id)
            self.context_builder = ContextBuilder()
        else:
            self.memory = None
            self.personality = None
            self.context_builder = None

    def process_message(self, message_text):
        """
        Main entry point for conversational messages
        Returns: AI response text
        """
        response = None

        try:
            # Get recent conversation context
            recent_context = None
            if self.memory:
                try:
                    recent_context = self.memory.get_recent_context(limit=5)
                except Exception as e:
                    print(f"[WARN] Could not get recent context: {e}")

            # 1. Classify intent
            intent, confidence, params = self.intent_classifier.classify_intent(
                message_text,
                context=recent_context
            )

            print(f"[AI] Detected intent: {intent} (confidence: {confidence})")

            # 2. Handle based on intent
            if intent == 'register_course':
                response = self._handle_register_course(message_text, params)

            elif intent == 'link_group':
                response = self._handle_link_group(message_text, params)

            elif intent == 'broadcast':
                if not self.course:
                    response = "Register a course first."
                else:
                    response = self._handle_broadcast(message_text, params)

            elif intent == 'schedule_message':
                if not self.course:
                    response = "Which course?"
                else:
                    response = self._handle_schedule(message_text, params)

            elif intent == 'provide_info':
                if not self.course:
                    response = "Which course is this for?"
                else:
                    response = self._handle_course_info(message_text, params)

            elif intent == 'casual_conversation':
                response = self._handle_casual(message_text)

            elif intent == 'answer_question':
                if not self.course:
                    response = "Which course is this answer for?"
                else:
                    response = self._handle_answer_question(message_text, params)

            else:
                # Unknown or low confidence
                if confidence < 0.7:
                    response = self._ask_clarification(message_text, intent, confidence)
                else:
                    response = self._handle_casual(message_text)

            # Ensure response is not None
            if not response:
                response = "How can I help?"

            # 3. Store conversation in memory (don't let this fail the response)
            try:
                if self.memory and self.course and response:
                    self.memory.store_conversation(
                        lecturer_id=self.lecturer.id,
                        role='lecturer',
                        message=message_text,
                        intent=intent,
                        params=params
                    )
                    self.memory.store_conversation(
                        lecturer_id=self.lecturer.id,
                        role='ai',
                        message=response,
                        intent='response'
                    )
            except Exception as e:
                print(f"[WARN] Could not store conversation: {e}")

            # 4. Check if AI should ask a curious question (don't let this fail the response)
            try:
                if self.personality and self.course and response:
                    curiosity_question = self.personality.check_curiosity_trigger(
                        message_text,
                        context=self._build_context_string(recent_context)
                    )
                    if curiosity_question:
                        response += f" {curiosity_question}"
            except Exception as e:
                print(f"[WARN] Curiosity trigger failed: {e}")

        except Exception as e:
            print(f"[ERROR] process_message error: {e}")
            import traceback
            traceback.print_exc()
            response = "Something went wrong. Try again?"

        print(f"[DEBUG] Final response: {response[:100] if response else 'NONE'}")
        return response

    def _handle_register_course(self, message, params):
        """
        Handle course registration from natural language
        """
        # Extract course code and name from params or message
        course_code = params.get('course_code')
        course_name = params.get('course_name')

        # If not in params, try to extract with AI
        if not course_code or not course_name:
            extracted = self._extract_course_info_with_ai(message)
            course_code = extracted.get('course_code', course_code)
            course_name = extracted.get('course_name', course_name)

        if not course_code or not course_name:
            return "What's the course code and name? (e.g., CSC302 Computer Networks)"

        # Check if course already exists
        existing = Course.query.filter_by(
            code=course_code,
            lecturer_id=self.lecturer.id
        ).first()

        if existing:
            return f"You already have {course_code} registered. Want to link it to a WhatsApp group?"

        # Create new course
        course = Course(
            code=course_code,
            name=course_name,
            lecturer_id=self.lecturer.id
        )
        db.session.add(course)
        db.session.commit()

        # Update self.course
        self.course = course
        self.memory = ConversationMemory(course.id)
        self.personality = AIPersonality(course.id)

        return f"Done! {course_code} registered. Link a WhatsApp number?"

    def _handle_link_group(self, message, params):
        """
        Handle linking WhatsApp group
        """
        phone_number = params.get('phone_number')

        if not phone_number:
            return "Share a phone number to link (e.g., +234...)"

        # Clean and format phone number (remove spaces, dashes, parentheses)
        phone_number = ''.join(c for c in phone_number if c.isdigit() or c == '+')

        if not phone_number.startswith('+'):
            phone_number = '+' + phone_number

        if not phone_number.startswith('whatsapp:'):
            phone_number = 'whatsapp:' + phone_number

        print(f"[LINK] Linking group with number: {phone_number}")

        # Find unlinked course
        if not self.course:
            course = Course.query.filter_by(
                lecturer_id=self.lecturer.id,
                group_id=None
            ).order_by(Course.created_at.desc()).first()

            if not course:
                return "You need to register a course first before linking a group."
        else:
            course = self.course

        course.group_id = phone_number
        db.session.commit()

        return f"Linked! {course.code} → {phone_number.replace('whatsapp:', '')}. They must join the sandbox first to receive messages."

    def _handle_broadcast(self, message, params):
        """
        Handle broadcast message
        """
        # Import here to avoid circular dependency
        from bot_handler import send_whatsapp_message, log_message, track_analytics

        broadcast_content = params.get('message_body', message)

        # If message_body is empty or same as original, ask for clarification
        if not broadcast_content or broadcast_content == message:
            # Use AI to extract the actual message
            extracted = self._extract_broadcast_content(message)
            broadcast_content = extracted

        if not self.course.group_id:
            return f"I don't have a WhatsApp group linked to {self.course.code} yet. Want to link one?"

        # Send broadcast - keep it natural, not robotic
        full_message = f"📢 {self.course.code}:\n\n{broadcast_content}"

        if send_whatsapp_message(self.course.group_id, full_message):
            log_message(self.course.id, self.lecturer.phone_number, 'broadcast', broadcast_content)
            track_analytics(self.course.id, 'message_sent')
            return "Sent!"
        else:
            return "Oops, something went wrong sending the message. Check your group connection?"

    def _handle_schedule(self, message, params):
        """
        Handle scheduling a message
        """
        hour = params.get('hour')
        minute = params.get('minute')
        message_body = params.get('message_body')

        if not hour or not minute:
            return "What time should I send it? Give me a time like '2:30 PM' or '14:30'."

        if not message_body:
            return "What message should I send at that time?"

        # Create scheduled message (import here to avoid circular imports)
        from models import ScheduledMessage

        target_time = datetime.now().replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )

        if target_time < datetime.now():
            target_time += timedelta(days=1)

        scheduled = ScheduledMessage(
            course_id=self.course.id,
            message=message_body,
            scheduled_time=target_time
        )
        db.session.add(scheduled)
        db.session.commit()

        return f"Scheduled! I'll send it at {target_time.strftime('%I:%M %p')} (server time)."

    def _handle_course_info(self, message, params):
        """
        Extract and store course information from casual conversation
        """
        # Use AI to extract structured info
        extracted_info = self._extract_structured_info(message)

        if not extracted_info:
            # If AI couldn't extract anything, just acknowledge
            response = "Noted! I'll remember this."
        else:
            # Store in CourseContext
            for key, value in extracted_info.items():
                self.memory.store_course_context(
                    context_type=params.get('info_type', 'general_info'),
                    key=key,
                    value=value,
                    confidence=0.8
                )

            # Generate acknowledgment
            info_summary = ", ".join([f"{k}" for k in extracted_info.keys()])
            response = f"Got it! I've noted the {info_summary}. Students can ask me about this anytime."

        return response

    def _handle_answer_question(self, message, params):
        """
        Handle lecturer answering a pending question conversationally
        """
        from bot_handler import send_whatsapp_message, log_message

        # Get the answer text (could be the whole message or extracted)
        answer_text = self._extract_answer_content(message)

        # Get the most recent pending question for this lecturer's courses
        pending = PendingQuestion.query.join(Course).filter(
            Course.lecturer_id == self.lecturer.id,
            PendingQuestion.status == 'pending'
        ).order_by(PendingQuestion.asked_at.desc()).first()

        if not pending:
            return "I don't see any pending questions to answer. Your students are all set!"

        # Save as FAQ for future reference
        faq = FAQ(
            question=pending.question,
            answer=answer_text,
            course_id=pending.course_id
        )
        db.session.add(faq)

        # Update question status
        pending.status = 'answered'
        pending.answered_at = datetime.utcnow()
        pending.answer_text = answer_text

        # Send reply to group
        course = Course.query.get(pending.course_id)

        if pending.is_anonymous:
            # Don't reveal student identity for anonymous questions
            reply = f"Regarding a student question:\n\n'{pending.question}'\n\n{answer_text}\n\n- {self.lecturer.name}"
        else:
            reply = f"Regarding: '{pending.question}'\n\n{answer_text}\n\n- {self.lecturer.name}"

        if course and course.group_id:
            send_whatsapp_message(course.group_id, reply)
            log_message(course.id, self.lecturer.phone_number, 'answer', answer_text)

        db.session.commit()

        return "Answer sent and saved to FAQ!"

    def _extract_answer_content(self, message):
        """
        Extract the actual answer content from a conversational message
        """
        # Remove common prefixes
        prefixes = [
            'answer:',
            'the answer is',
            'my answer is',
            'tell them',
            'respond with',
            'reply:',
            'here\'s my answer:',
        ]

        message_stripped = message.strip()
        message_lower = message_stripped.lower()

        for prefix in prefixes:
            if message_lower.startswith(prefix):
                content = message_stripped[len(prefix):].strip()
                return content

        # If no prefix found, return the whole message
        return message_stripped

    def _handle_casual(self, message):
        """
        Handle casual conversation - keep responses concise
        """
        # Default response for new lecturers without a course
        if not self.personality or not self.course:
            if any(greeting in message.lower() for greeting in ['hi', 'hello', 'hey']):
                return "Hi! Ready to set up a course?"
            elif any(thanks in message.lower() for thanks in ['thanks', 'thank you']):
                return "You're welcome!"
            else:
                return "I can help with courses, broadcasts, and questions. What do you need?"

        # Try to use personality engine for response
        try:
            course_info = f"{self.course.code} - {self.course.name}"
            recent_context = self.memory.get_recent_context(limit=5) if self.memory else []
            context_str = self._build_context_string(recent_context)

            response = self.personality.generate_response(
                message,
                context=context_str,
                course_info=course_info
            )

            # If personality engine returns empty, use fallback
            if response:
                return response
        except Exception as e:
            print(f"[WARN] Personality engine error: {e}")

        # Fallback response
        return f"How can I help with {self.course.code}?"

    def _ask_clarification(self, message, intent, confidence):
        """
        Ask for clarification when intent is unclear
        """
        return "Not sure what you need. Register course? Broadcast? Share info?"

    def _build_context_string(self, conversations):
        """
        Build a context string from conversation history
        """
        if not conversations:
            return ""

        return "\n".join([
            f"{conv.role}: {conv.message}"
            for conv in reversed(conversations[-5:])
        ])

    def _extract_course_info_with_ai(self, message):
        """
        Use AI to extract course code and name
        """
        if not groq_client:
            return {}

        try:
            prompt = f"""Extract the course code and name from this message.

Message: "{message}"

Return ONLY valid JSON (no markdown):
{{
    "course_code": "...",
    "course_name": "..."
}}

If not found, use empty strings."""

            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=150
            )

            response_text = response.choices[0].message.content.strip()
            if response_text.startswith('```'):
                response_text = re.sub(r'```(?:json)?\n?', '', response_text).strip()

            return json.loads(response_text)

        except Exception as e:
            print(f"[ERROR] Course info extraction error: {e}")
            return {}

    def _extract_broadcast_content(self, message):
        """
        Extract the actual broadcast content from a conversational message
        """
        # Remove common prefixes
        prefixes = [
            'broadcast',
            'send this',
            'tell students',
            'inform students',
            'let students know',
            'announce',
        ]

        message_lower = message.lower()
        for prefix in prefixes:
            if message_lower.startswith(prefix):
                # Remove prefix and any following colon or space
                content = message[len(prefix):].strip()
                if content.startswith(':'):
                    content = content[1:].strip()
                return content

        # If no prefix found, return the whole message
        return message

    def _extract_structured_info(self, message):
        """
        Use AI to extract structured key-value information
        """
        if not groq_client:
            return {}

        try:
            prompt = f"""Extract course information from this message as key-value pairs.

Message: "{message}"

Look for:
- exam dates, times, venues
- assignment deadlines
- class schedules
- office hours
- grading policies
- any other course-related information

Return ONLY valid JSON (no markdown):
{{
    "key1": "value1",
    "key2": "value2"
}}

Only include information explicitly stated. Use clear, concise keys like "exam_date", "exam_venue", "assignment_deadline", etc."""

            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300
            )

            response_text = response.choices[0].message.content.strip()
            if response_text.startswith('```'):
                response_text = re.sub(r'```(?:json)?\n?', '', response_text).strip()

            result = json.loads(response_text)

            # Filter out empty values
            return {k: v for k, v in result.items() if v and v.strip()}

        except Exception as e:
            print(f"[ERROR] Structured info extraction error: {e}")
            return {}
