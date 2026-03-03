import re
import json
from config import Config
from groq import Groq

# Initialize Groq client
groq_client = None
if Config.GROQ_API_KEY:
    groq_client = Groq(api_key=Config.GROQ_API_KEY)


class IntentClassifier:
    """
    Two-tier intent classification system for natural language understanding
    Tier 1: Fast pattern matching (no API calls)
    Tier 2: Groq AI classification (for ambiguous cases)
    """

    # Intent patterns for fast matching
    INTENT_PATTERNS = {
        'register_course': [
            r'(?:register|create|setup).*(?:course|class)',
            r'(?:new|add).*(?:course|class)',
            r'(?:i want to|let me).*(?:create|register).*(?:course|class)'
        ],
        'broadcast': [
            r'(?:broadcast|announce|tell students)',
            r'send.*(?:message|announcement)',
            r'(?:inform|notify).*(?:students|class)',
            r'(?:students should know|everyone should)',
        ],
        'schedule_message': [
            r'schedule.*(?:message|announcement)',
            r'(?:remind|send).*(?:at|tomorrow|later)',
            r'(?:send|post).*(?:tomorrow|next|later)'
        ],
        'answer_question': [
            r'(?:answer|respond to|reply)',
            r'(?:the|their) question',
            r'(?:here\'s the answer|my response is)'
        ],
        'provide_info': [
            r'(?:exam|test|quiz).*(?:is|will be|date|time|venue)',
            r'(?:assignment|homework).*(?:due|deadline|submit)',
            r'(?:class|lecture).*(?:venue|location|time|room)',
            r'(?:office hours|consultation)',
            r'(?:grading|marking).*(?:policy|criteria)',
            r'(?:project|presentation)',
            r'(?:deadline|due date)',
        ],
        'link_group': [
            r'/link',
            r'link.*(?:group|number)',
            r'connect.*(?:group|whatsapp)'
        ],
        'casual_conversation': [
            r'^(?:hi|hello|hey|thanks|thank you)',
            r'^(?:how are you|what\'s up|good morning|good afternoon)',
            r'^(?:okay|ok|alright|got it|noted|sure)',
        ]
    }

    def __init__(self):
        self.groq_available = groq_client is not None

    def classify_intent(self, message, context=None):
        """
        Classify the intent of a message
        Returns: (intent, confidence, extracted_params)

        intent: string representing the detected intent
        confidence: float 0.0-1.0
        extracted_params: dict with extracted information
        """
        # Tier 1: Fast pattern matching
        pattern_result = self._fast_pattern_match(message)
        if pattern_result:
            return pattern_result

        # Tier 2: AI classification (if available and pattern match failed)
        if self.groq_available:
            return self._ai_classify(message, context)

        # Fallback: unable to classify
        return ('unknown', 0.0, {})

    def _fast_pattern_match(self, message):
        """
        Tier 1: Fast regex-based pattern matching
        Returns (intent, confidence, params) or None
        """
        message_lower = message.lower().strip()

        for intent, patterns in self.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, message_lower):
                    # Extract parameters based on intent
                    params = self._extract_params(message, intent)
                    return (intent, 0.9, params)

        return None

    def _extract_params(self, message, intent):
        """
        Extract parameters from message based on intent
        """
        params = {}

        if intent == 'register_course':
            # Try to extract course code and name
            # Pattern: "... CSC302, Computer Networks" or "... CSC302 Computer Networks"
            code_name_match = re.search(r'([A-Z]{2,4}\d{2,4})[,\s]+(.+?)(?:\.|$)', message, re.IGNORECASE)
            if code_name_match:
                params['course_code'] = code_name_match.group(1).upper()
                params['course_name'] = code_name_match.group(2).strip()

        elif intent == 'link_group':
            # Extract phone number
            phone_match = re.search(r'\+?\d[\d\s\-()]{7,}', message)
            if phone_match:
                params['phone_number'] = phone_match.group(0).strip()

        elif intent == 'schedule_message':
            # Extract time
            time_match = re.search(r'(\d{1,2}):(\d{2})', message)
            if time_match:
                params['hour'] = int(time_match.group(1))
                params['minute'] = int(time_match.group(2))

            # Extract message body after time
            if time_match:
                msg_after_time = message[time_match.end():].strip()
                if msg_after_time.startswith(':'):
                    msg_after_time = msg_after_time[1:].strip()
                params['message_body'] = msg_after_time

        elif intent == 'broadcast':
            # Extract broadcast content (everything after "broadcast:")
            broadcast_match = re.search(r'broadcast[:\s]+(.+)', message, re.IGNORECASE)
            if broadcast_match:
                params['message_body'] = broadcast_match.group(1).strip()
            else:
                # If no explicit "broadcast:" prefix, the whole message might be the broadcast
                params['message_body'] = message

        elif intent == 'provide_info':
            # Try to extract structured information
            params['info_type'] = self._detect_info_type(message)
            params['raw_info'] = message

        return params

    def _detect_info_type(self, message):
        """
        Detect what type of information is being provided
        """
        message_lower = message.lower()

        if re.search(r'exam|test|quiz', message_lower):
            return 'exam_info'
        elif re.search(r'assignment|homework', message_lower):
            return 'assignment_info'
        elif re.search(r'venue|location|room', message_lower):
            return 'venue_info'
        elif re.search(r'deadline|due date', message_lower):
            return 'deadline_info'
        elif re.search(r'office hours|consultation', message_lower):
            return 'office_hours'
        elif re.search(r'grading|marking', message_lower):
            return 'grading_policy'
        else:
            return 'general_info'

    def _ai_classify(self, message, context):
        """
        Tier 2: AI-based classification using Groq
        Returns (intent, confidence, params)
        """
        try:
            # Build context string if available
            context_str = ""
            if context:
                context_str = "\n\nRecent conversation context:\n" + "\n".join([
                    f"{c.role}: {c.message}" for c in context[-5:]
                ])

            prompt = f"""Classify this lecturer message into one of these intents:

Intents:
- register_course: Lecturer wants to create/register a new course
- broadcast: Lecturer wants to send a message to students now
- schedule_message: Lecturer wants to schedule a message for later
- answer_question: Lecturer is answering a student's question
- provide_info: Lecturer is providing course-related information (exam dates, deadlines, venues, etc.)
- link_group: Lecturer wants to link/connect a WhatsApp group
- casual_conversation: Casual greeting or acknowledgment
- other: Doesn't fit any category

Message: "{message}"{context_str}

IMPORTANT: If the message contains course information like exam dates, deadlines, venues, or any academic details, classify as "provide_info".

Return ONLY valid JSON (no markdown, no extra text):
{{
    "intent": "...",
    "confidence": 0.0-1.0,
    "extracted_info": {{
        "any_extracted_parameters": "..."
    }},
    "reasoning": "brief explanation"
}}"""

            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300
            )

            response_text = response.choices[0].message.content.strip()

            # Remove markdown code blocks if present
            if response_text.startswith('```'):
                response_text = re.sub(r'```(?:json)?\n?', '', response_text)
                response_text = response_text.strip()

            result = json.loads(response_text)

            intent = result.get('intent', 'unknown')
            confidence = float(result.get('confidence', 0.0))
            extracted_info = result.get('extracted_info', {})

            return (intent, confidence, extracted_info)

        except Exception as e:
            print(f"[ERROR] AI classification error: {e}")
            return ('unknown', 0.0, {})

    def needs_clarification(self, intent, confidence):
        """
        Determine if the classification needs clarification from lecturer
        """
        if confidence < 0.7:
            return True
        if intent == 'unknown':
            return True
        return False
