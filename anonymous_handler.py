"""
Anonymous Question Handler for ClassPulse
Detects and processes anonymous question requests from students
"""

import re


# Patterns that indicate anonymous intent
ANONYMOUS_PATTERNS = [
    r'anonymously\s+(?:ask|tell|send|question)',
    r'ask\s+(?:anonymously|without\s+my\s+name)',
    r'(?:don\'t|do\s+not|dont)\s+(?:share|reveal|show|include|mention)\s+(?:my\s+)?(?:name|identity|number|phone)',
    r'hide\s+my\s+(?:name|identity|number)',
    r'private(?:ly)?\s+(?:ask|question|send)',
    r'secret(?:ly)?\s+(?:ask|question)',
    r'anonymous\s+question',
    r'without\s+(?:my\s+)?(?:name|identity)',
    r'keep\s+(?:me|my\s+identity|my\s+name)\s+(?:hidden|anonymous|private|secret)',
    r'(?:i\s+)?(?:want|wish|prefer)\s+to\s+(?:remain|stay|be)\s+anonymous',
    r'can\s+(?:i|you)\s+(?:ask|send)\s+(?:this\s+)?anonymously',
]

# Patterns to clean from the message (remove anonymous-related phrases)
CLEANUP_PATTERNS = [
    r'anonymously\s+',
    r'ask\s+without\s+my\s+name[:\s]*',
    r'(?:don\'t|do\s+not|dont)\s+(?:share|reveal|show|include|mention)\s+(?:my\s+)?(?:name|identity|number|phone)[:\s]*',
    r'hide\s+my\s+(?:name|identity|number)[:\s]*',
    r'private(?:ly)?\s+',
    r'secret(?:ly)?\s+',
    r'anonymous(?:ly)?\s+(?:question|ask)?[:\s]*',
    r'without\s+(?:my\s+)?(?:name|identity)[:\s]*',
    r'keep\s+(?:me|my\s+identity|my\s+name)\s+(?:hidden|anonymous|private|secret)[:\s]*',
    r'(?:i\s+)?(?:want|wish|prefer)\s+to\s+(?:remain|stay|be)\s+anonymous[:\s]*',
    r'can\s+(?:i|you)\s+(?:ask|send)\s+(?:this\s+)?anonymously[:\s,]*',
]


def detect_anonymous_intent(message):
    """
    Detect if user wants to ask anonymously and extract the actual question

    Args:
        message: Raw message text

    Returns:
        tuple: (is_anonymous: bool, clean_message: str)
    """
    if not message:
        return False, message

    message_lower = message.lower()

    # Check for anonymous patterns
    is_anonymous = any(
        re.search(pattern, message_lower)
        for pattern in ANONYMOUS_PATTERNS
    )

    if not is_anonymous:
        return False, message

    # Clean the message by removing anonymous-related phrases
    clean_message = message
    for pattern in CLEANUP_PATTERNS:
        clean_message = re.sub(pattern, '', clean_message, flags=re.IGNORECASE)

    # Clean up extra whitespace and punctuation at start
    clean_message = clean_message.strip()
    clean_message = re.sub(r'^[:\s,]+', '', clean_message)  # Remove leading colons, spaces, commas
    clean_message = ' '.join(clean_message.split())  # Normalize whitespace

    # If message is empty after cleaning, use original (minus obvious anonymous prefix)
    if not clean_message or len(clean_message) < 3:
        # Try to extract just the question part
        clean_message = re.sub(r'^.*?(?:ask|question)[:\s]*', '', message, flags=re.IGNORECASE)
        clean_message = clean_message.strip()

    # Final fallback
    if not clean_message or len(clean_message) < 3:
        clean_message = message

    return True, clean_message


def format_anonymous_notification(question, course_code, course_name=None):
    """
    Format notification for lecturer about anonymous question

    Args:
        question: The student's question
        course_code: Course code
        course_name: Optional course name

    Returns:
        str: Formatted notification message
    """
    course_display = f"{course_code} - {course_name}" if course_name else course_code

    return f"""[ANONYMOUS QUESTION] New question in {course_display}:

"{question}"

(Student requested anonymity)

Reply to answer this question."""


def format_anonymous_answer(question, answer, lecturer_name):
    """
    Format the answer to be sent back to the group (without revealing student)

    Args:
        question: Original question
        answer: Lecturer's answer
        lecturer_name: Lecturer's name

    Returns:
        str: Formatted answer message
    """
    return f"""Regarding a student's question:

"{question}"

{answer}

- {lecturer_name}"""


def is_anonymous_request(message):
    """
    Quick check if message contains anonymous intent (without cleaning)

    Args:
        message: Raw message text

    Returns:
        bool: True if anonymous intent detected
    """
    if not message:
        return False

    message_lower = message.lower()

    return any(
        re.search(pattern, message_lower)
        for pattern in ANONYMOUS_PATTERNS
    )
