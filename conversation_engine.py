import pickle
import numpy as np
from datetime import datetime
from sentence_transformers import SentenceTransformer
from models import db, ConversationHistory, CourseContext, Course
import uuid


class ConversationMemory:
    """
    Manages conversation history and semantic search
    Stores lecturer-AI conversations with embeddings for semantic retrieval
    """

    def __init__(self, course_id, encoder=None):
        self.course_id = course_id
        self.encoder = encoder or SentenceTransformer('all-MiniLM-L6-v2')

    def store_conversation(self, lecturer_id, role, message, intent=None, params=None, thread_id=None):
        """
        Store conversation with semantic embedding
        Returns: ConversationHistory object
        """
        # Generate embedding
        embedding = self.encoder.encode(message)
        embedding_bytes = pickle.dumps(embedding)

        # Generate thread_id if not provided
        if not thread_id:
            thread_id = str(uuid.uuid4())[:8]

        # Create record
        conv = ConversationHistory(
            course_id=self.course_id,
            lecturer_id=lecturer_id,
            role=role,
            message=message,
            detected_intent=intent,
            extracted_params=params,
            message_embedding=embedding_bytes,
            thread_id=thread_id
        )

        db.session.add(conv)
        db.session.commit()

        # Update course conversation count
        course = Course.query.get(self.course_id)
        if course:
            course.total_conversations = (course.total_conversations or 0) + 1
            db.session.commit()

        return conv

    def search_relevant_context(self, query, limit=5, min_similarity=0.5):
        """
        Semantic search for relevant past conversations
        Returns: list of (ConversationHistory, similarity_score) tuples
        """
        # Encode query
        query_embedding = self.encoder.encode(query)

        # Get all conversation embeddings for this course
        conversations = ConversationHistory.query.filter_by(
            course_id=self.course_id
        ).order_by(ConversationHistory.created_at.desc()).limit(100).all()

        if not conversations:
            return []

        # Calculate similarities
        similarities = []
        for conv in conversations:
            try:
                conv_embedding = pickle.loads(conv.message_embedding)

                # Calculate cosine similarity
                similarity = np.dot(query_embedding, conv_embedding) / (
                    np.linalg.norm(query_embedding) * np.linalg.norm(conv_embedding)
                )

                # Apply temporal decay (recent messages get boost)
                days_old = (datetime.utcnow() - conv.created_at).days
                temporal_weight = 1.0 / (1.0 + 0.1 * days_old)

                # Weighted score: 70% similarity, 30% recency
                final_score = similarity * 0.7 + temporal_weight * 0.3

                if final_score >= min_similarity:
                    similarities.append((conv, final_score))

            except Exception as e:
                print(f"[ERROR] Error processing conversation {conv.id}: {e}")
                continue

        # Sort and return top results
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:limit]

    def get_recent_context(self, limit=10):
        """
        Get recent conversation history (no semantic search)
        Returns: list of ConversationHistory objects
        """
        return ConversationHistory.query.filter_by(
            course_id=self.course_id
        ).order_by(ConversationHistory.created_at.desc()).limit(limit).all()

    def mark_as_used(self, conversation_ids):
        """
        Mark conversations as having been used in a response
        """
        for conv_id in conversation_ids:
            conv = ConversationHistory.query.get(conv_id)
            if conv:
                conv.was_used_in_response = True
                conv.times_referenced += 1

        db.session.commit()

    def store_course_context(self, context_type, key, value, source_conversation_id=None, confidence=1.0):
        """
        Store structured course information extracted from conversations
        """
        # Check if context already exists
        existing = CourseContext.query.filter_by(
            course_id=self.course_id,
            context_type=context_type,
            key=key
        ).first()

        if existing:
            # Update existing context
            existing.value = value
            existing.confidence_score = confidence
            existing.updated_at = datetime.utcnow()
            if source_conversation_id:
                existing.source_conversation_id = source_conversation_id
        else:
            # Create new context
            context = CourseContext(
                course_id=self.course_id,
                context_type=context_type,
                key=key,
                value=value,
                source_conversation_id=source_conversation_id,
                confidence_score=confidence
            )
            db.session.add(context)

        db.session.commit()

    def get_course_context(self, context_type=None):
        """
        Retrieve structured course context
        """
        query = CourseContext.query.filter_by(
            course_id=self.course_id,
            is_active=True
        )

        if context_type:
            query = query.filter_by(context_type=context_type)

        return query.order_by(CourseContext.updated_at.desc()).all()


class ContextBuilder:
    """
    Builds context for AI prompts with token budget management
    """

    def __init__(self, max_tokens=8000):
        self.max_tokens = max_tokens

    def build_prompt_context(self, relevant_conversations, structured_context, recent_conversations):
        """
        Build a context string for AI prompts
        Prioritizes: Recent > Relevant > Structured
        """
        context_parts = []

        # Part 1: Structured course information (highest priority)
        if structured_context:
            context_parts.append("COURSE INFORMATION:")
            for ctx in structured_context[:10]:  # Limit to 10 items
                context_parts.append(f"- {ctx.key}: {ctx.value}")
            context_parts.append("")

        # Part 2: Relevant conversations (semantic matches)
        if relevant_conversations:
            context_parts.append("RELEVANT PAST CONVERSATIONS:")
            for conv, score in relevant_conversations[:5]:  # Top 5
                context_parts.append(f"[{conv.role}]: {conv.message}")
            context_parts.append("")

        # Part 3: Recent conversations (context continuity)
        if recent_conversations:
            context_parts.append("RECENT EXCHANGES:")
            for conv in recent_conversations[:5]:  # Last 5
                context_parts.append(f"[{conv.role}]: {conv.message}")
            context_parts.append("")

        full_context = "\n".join(context_parts)

        # Rough token estimation (4 chars ≈ 1 token)
        estimated_tokens = len(full_context) // 4

        if estimated_tokens > self.max_tokens:
            # Trim context if too long
            full_context = full_context[:self.max_tokens * 4]

        return full_context

    def prioritize_context(self, conversations):
        """
        Prioritize which conversations to include based on relevance and recency
        """
        # Sort by times_referenced (frequently used) and created_at (recent)
        sorted_convs = sorted(
            conversations,
            key=lambda c: (c.times_referenced * 0.4 + (1.0 if c.was_used_in_response else 0.0) * 0.6),
            reverse=True
        )
        return sorted_convs
