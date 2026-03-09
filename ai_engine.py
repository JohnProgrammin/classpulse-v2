import os
from groq import Groq
import numpy as np
from models import FAQ, db
from config import Config

# Initialize AI models lazily
_sentence_model = None

def get_sentence_model():
    global _sentence_model
    if _sentence_model is None:
        from sentence_transformers import SentenceTransformer
        if os.environ.get('TESTING'):
            print("[INFO] Testing mode: Skipping heavy model loading (using mock/small model if needed)")
            # In testing, we could use a mock or a very small model, 
            # but for now let's just avoid loading the 100MB+ one if possible
            # or load it only once.
        print("[*] Loading AI Models...")
        _sentence_model = SentenceTransformer('all-MiniLM-L6-v2')
        print("[OK] AI Models loaded")
    return _sentence_model

# Initialize Groq client
groq_client = None
if Config.GROQ_API_KEY:
    groq_client = Groq(api_key=Config.GROQ_API_KEY)
    print("[OK] Groq AI initialized")
else:
    print("[WARNING] Groq API key not found. Using fallback FAQ matching only.")


def find_best_faq_match(question, course_id):
    """
    Uses sentence transformers to find the best matching FAQ
    Returns (faq_object, similarity_score) or (None, 0)
    """
    # Get all FAQs for this course
    faqs = FAQ.query.filter_by(course_id=course_id).all()
    
    if not faqs:
        return None, 0
    
    # Encode the user's question
    question_embedding = get_sentence_model().encode(question.lower())
    
    best_faq = None
    best_score = 0
    
    for faq in faqs:
        # Encode FAQ question
        faq_embedding = get_sentence_model().encode(faq.question.lower())
        
        # Calculate cosine similarity
        score = np.dot(question_embedding, faq_embedding) / (
            np.linalg.norm(question_embedding) * np.linalg.norm(faq_embedding)
        )
        
        if score > best_score:
            best_score = score
            best_faq = faq
    
    return best_faq, best_score


def ask_groq_ai(question, context="", course_info=""):
    """
    Ask Groq AI a question with optional context
    Returns the AI's response or None if unavailable
    """
    if not groq_client:
        return None
    
    try:
        system_prompt = f"""You are ClassPulse AI for {course_info}.

STRICT RULES:
- Maximum 35 words per response
- Be direct and helpful
- Sound natural, like a friendly TA
- If unsure, say "I'll check with the lecturer."

Context: {context}
"""
        
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=100  # Enforce short responses
        )
        
        return chat_completion.choices[0].message.content
    
    except Exception as e:
        print(f"[ERROR] Groq AI Error: {e}")
        return None


def generate_smart_response(question, course):
    """
    Main intelligence function: tries multiple strategies to answer
    Returns (response_text, response_type)

    response_type can be:
    - 'faq_match': Found answer in FAQ
    - 'context_aware_response': Answer from conversation history
    - 'ai_response': Groq AI generated response
    - 'forward_to_lecturer': Need to ask lecturer
    """

    # Strategy 1: Try FAQ matching first
    best_faq, similarity = find_best_faq_match(question, course.id)

    if similarity > Config.FAQ_SIMILARITY_THRESHOLD:
        # Update analytics
        best_faq.times_matched += 1
        db.session.commit()

        return best_faq.answer, 'faq_match'

    # Strategy 2: NEW - Search conversation history with lecturer
    try:
        from conversation_engine import ConversationMemory, ContextBuilder
        from models import CourseContext
        from personality_engine import AIPersonality

        memory = ConversationMemory(course.id, encoder=get_sentence_model())
        personality = AIPersonality(course.id)

        # Check if question is off-topic
        course_context_str = f"{course.code} - {course.name}"
        if personality.is_off_topic(question, course_context_str):
            return personality.config.off_topic_response, 'off_topic'

        # Search for relevant conversations
        relevant_convs = memory.search_relevant_context(question, limit=5, min_similarity=0.5)

        # Get structured course context
        structured_context = memory.get_course_context()

        if relevant_convs or structured_context:
            # Build context for AI
            context_builder = ContextBuilder()

            # Build conversation context string
            conversation_context = ""
            if relevant_convs:
                conversation_context = "RELEVANT CONVERSATIONS WITH LECTURER:\n"
                for conv, score in relevant_convs:
                    conversation_context += f"[{conv.role}]: {conv.message}\n"
                conversation_context += "\n"

            # Build structured context string
            structured_info = ""
            if structured_context:
                structured_info = "COURSE INFORMATION:\n"
                for ctx in structured_context[:10]:
                    structured_info += f"- {ctx.key}: {ctx.value}\n"
                structured_info += "\n"

            # Enhanced AI prompt with conversation context
            enhanced_prompt = f"""You are ClassPulse AI for {course.code} - {course.name}.

{structured_info}{conversation_context}STUDENT QUESTION: {question}

STRICT RULES:
- Maximum 35 words
- Be direct and natural
- If info not found: "I'll check with the lecturer."
- Sound like a friendly TA, not a robot"""

            if groq_client:
                ai_response = ask_groq_ai_direct(enhanced_prompt)

                if ai_response and "hasn't mentioned" not in ai_response.lower():
                    # Mark conversations as used
                    conv_ids = [conv.id for conv, _ in relevant_convs]
                    memory.mark_as_used(conv_ids)

                    return ai_response, 'context_aware_response'

    except Exception as e:
        print(f"[ERROR] Context-aware response error: {e}")
        # Fall through to Strategy 3

    # Strategy 3: Try Groq AI with FAQ context (existing strategy)
    if groq_client:
        # Build context from recent FAQs
        recent_faqs = FAQ.query.filter_by(course_id=course.id).order_by(
            FAQ.times_matched.desc()
        ).limit(5).all()

        context = "\n".join([
            f"Q: {faq.question}\nA: {faq.answer}"
            for faq in recent_faqs
        ])

        course_info = f"Course: {course.code} - {course.name}"

        ai_response = ask_groq_ai(question, context, course_info)

        if ai_response and "hasn't provided this information" not in ai_response:
            return ai_response, 'ai_response'

    # Strategy 4: Forward to lecturer
    return None, 'forward_to_lecturer'


def ask_groq_ai_direct(prompt):
    """
    Direct Groq AI call with full prompt control
    Used for context-aware responses
    """
    if not groq_client:
        return None

    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {"role": "user", "content": prompt}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=100  # Keep responses short
        )

        return chat_completion.choices[0].message.content

    except Exception as e:
        print(f"[ERROR] Groq AI Direct Error: {e}")
        return None


def summarize_pending_questions(questions):
    """
    Uses Groq AI to summarize multiple pending questions
    Useful for dashboard analytics
    """
    if not groq_client or not questions:
        return None
    
    try:
        questions_text = "\n".join([
            f"{i+1}. {q.question}" 
            for i, q in enumerate(questions)
        ])
        
        prompt = f"""Analyze these student questions and provide:
1. Common themes (max 3)
2. Most urgent question
3. Quick summary

Questions:
{questions_text}"""
        
        response = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.5,
            max_tokens=300
        )
        
        return response.choices[0].message.content
    
    except Exception as e:
        print(f"[ERROR] Summarization Error: {e}")
        return None