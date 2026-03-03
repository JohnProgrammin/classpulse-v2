import re
import json
from models import db, AIPersonalityConfig
from config import Config
from groq import Groq

# Initialize Groq client
groq_client = None
if Config.GROQ_API_KEY:
    groq_client = Groq(api_key=Config.GROQ_API_KEY)


class AIPersonality:
    """
    Manages AI personality and response styling
    Makes the AI feel human-like, brief, and curious
    """

    def __init__(self, course_id):
        self.course_id = course_id
        self.config = AIPersonalityConfig.query.filter_by(
            course_id=course_id
        ).first()

        # Create default config if doesn't exist
        if not self.config:
            self.config = AIPersonalityConfig(course_id=course_id)
            db.session.add(self.config)
            db.session.commit()

    def build_system_prompt(self, course_info=""):
        """
        Build personality-aware system prompt
        """
        base_prompt = f"""You are ClassPulse AI for {course_info}.

STRICT RULES:
- Maximum 35 words per response
- Sound human, not robotic
- Be direct and helpful
- Use contractions (I'll, you're, let's)
- Ask for clarification when needed
- No "Certainly!", "Absolutely!", "Of course!"

FILTERED TOPICS (respond "..."): {self._format_filtered_topics()}
"""

        if self.config.custom_system_prompt:
            base_prompt += f"\n\nCUSTOM INSTRUCTIONS:\n{self.config.custom_system_prompt}"

        return base_prompt

    def _format_filtered_topics(self):
        """Format filtered topics for system prompt"""
        if not self.config.filtered_topics:
            return "None specified"
        return ", ".join(self.config.filtered_topics)

    def generate_response(self, user_message, context="", course_info=""):
        """
        Generate response with personality
        """
        if not groq_client:
            return "I need the Groq API to be configured to respond."

        system_prompt = self.build_system_prompt(course_info)

        # Build full prompt with context
        full_message = user_message
        if context:
            full_message = f"{context}\n\nLecturer: {user_message}"

        try:
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": full_message}
                ],
                temperature=0.7,
                max_tokens=100  # Keep responses short
            )

            raw_response = response.choices[0].message.content

            # Apply post-processing
            formatted_response = self._apply_formatting_rules(raw_response)

            return formatted_response

        except Exception as e:
            print(f"[ERROR] Personality response generation error: {e}")
            return "Sorry, I'm having trouble responding right now."

    def _apply_formatting_rules(self, response):
        """
        Ensure response follows personality guidelines (max 35 words)
        """
        # Remove excessive formality
        for phrase in ["Certainly!", "Absolutely!", "Of course!", "Great question!"]:
            response = response.replace(phrase, "")

        # Clean up extra spaces
        response = re.sub(r'\s+', ' ', response).strip()

        # Enforce max 35 words
        words = response.split()
        if len(words) > 35:
            response = ' '.join(words[:35])
            # End at a natural point
            if not response.endswith(('.', '!', '?')):
                response += '.'

        return response.strip()

    def check_curiosity_trigger(self, message, context):
        """
        Determine if AI should ask a follow-up question
        Returns: question string or None
        """
        if not self.config.curiosity_enabled:
            return None

        message_lower = message.lower()

        # Rule-based curiosity triggers
        triggers = [
            # Exam mentioned without date/time
            {
                'pattern': r'\b(exam|test|quiz)\b',
                'missing': ['date', 'time', 'when'],
                'question': "When is it scheduled?"
            },
            # Assignment mentioned without deadline
            {
                'pattern': r'\b(assignment|homework|project)\b',
                'missing': ['deadline', 'due', 'submit by'],
                'question': "What's the deadline?"
            },
            # Venue mentioned without time
            {
                'pattern': r'\b(venue|location|room|hall)\b',
                'missing': ['time', 'when', 'at'],
                'question': "What time should they be there?"
            },
            # Time mentioned without venue
            {
                'pattern': r'\b(\d{1,2}:\d{2}|morning|afternoon)\b',
                'missing': ['venue', 'room', 'location', 'where'],
                'question': "Where should they go?"
            },
        ]

        for trigger in triggers:
            # Check if trigger pattern is in message
            if re.search(trigger['pattern'], message_lower):
                # Check if missing information is NOT in message or context
                missing_info = all(
                    missing_word not in message_lower
                    for missing_word in trigger['missing']
                )

                if missing_info:
                    # Also check context to avoid asking twice
                    if context and not any(
                        missing_word in context.lower()
                        for missing_word in trigger['missing']
                    ):
                        return trigger['question']
                    elif not context:
                        return trigger['question']

        return None

    def is_off_topic(self, message, course_context):
        """
        Detect if a message is off-topic
        Returns: True if off-topic, False otherwise
        """
        if not self.config.filtered_topics:
            return False

        message_lower = message.lower()

        # Quick keyword check
        for topic in self.config.filtered_topics:
            if topic.lower() in message_lower:
                return True

        # AI-based detection for complex cases
        if groq_client:
            try:
                prompt = f"""Is this question related to the course "{course_context}"?

Question: "{message}"

Course-related topics include: lectures, exams, assignments, course materials, grades, venue, schedule, office hours, course content.

Return ONLY valid JSON (no markdown):
{{
    "is_course_related": true/false,
    "confidence": 0.0-1.0
}}"""

                response = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=100
                )

                response_text = response.choices[0].message.content.strip()
                if response_text.startswith('```'):
                    response_text = re.sub(r'```(?:json)?\n?', '', response_text).strip()

                result = json.loads(response_text)

                return not result['is_course_related'] and result['confidence'] > 0.7

            except Exception as e:
                print(f"[ERROR] Off-topic detection error: {e}")
                return False

        return False

    def add_filtered_topic(self, topic):
        """
        Add a topic to the filter list
        """
        if not self.config.filtered_topics:
            self.config.filtered_topics = []

        if topic not in self.config.filtered_topics:
            topics = self.config.filtered_topics.copy()
            topics.append(topic)
            self.config.filtered_topics = topics
            db.session.commit()

    def remove_filtered_topic(self, topic):
        """
        Remove a topic from the filter list
        """
        if self.config.filtered_topics and topic in self.config.filtered_topics:
            topics = self.config.filtered_topics.copy()
            topics.remove(topic)
            self.config.filtered_topics = topics
            db.session.commit()

    def update_settings(self, **kwargs):
        """
        Update personality settings
        """
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)

        db.session.commit()
