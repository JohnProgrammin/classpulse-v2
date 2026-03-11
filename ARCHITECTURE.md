# ClassPulse v2 Architecture & System Overview

This document serves as a comprehensive guide for the ClassPulse v2 platform, designed to assist developers and AI agents in understanding and extending the system.

## 1. System Philosophy
ClassPulse is a "Medium-style" academic communication platform. It prioritizes minimalist, high-end aesthetics and "Time-Shifted Engagement"—the idea that communication should be meaningful, structured, and AI-assisted rather than a constant stream of noisy chat.

## 2. Core Components

### A. Authentication & Role System
The system maintains a strict separation between two primary roles:
- **Lecturers**: Manage courses, Knowledge Bases, and AI personality. Integrated with `Flask-Login`.
- **Students (ChatUsers)**: Interact via WhatsApp-style rooms. Uses manual session management for flexible chat scaling.

### B. AI Engine (`ai_engine.py`)
The heart of the intelligence system. It uses:
- **Groq AI (Llama 3 70B)**: For high-level reasoning, summarization, and natural language responses.
- **Sentence Transformers (all-MiniLM-L6-v2)**: For semantic mapping between student questions and the Knowledge Base (FAQ).
- **Multi-Strategy Response Logic**:
    1. FAQ Semantic Match (High confidence)
    2. Context-Aware Memory Retrieval
    3. LLM Generation (with system guards)
    4. Fallback to Lecturer Review

### C. Conversational Intelligence (`conversation_engine.py`)
- **Memory Management**: Vectors-based search for past conversations to provide contextually relevant answers.
- **Context Extraction**: Automatically identifies facts (dates, venues) from lecturer-AI chats and saves them to `CourseContext`.

## 3. Database Schema (`models.py`)
- `Lecturer`: Core educator model.
- `ChatUser`: Student/General chat participant.
- `Course`: links lecturers to rooms and AI configs.
- `FAQ`: The "Knowledge Base" for automated responses.
- `ChatRoom`: Group/DM/AI containers.
- `PendingQuestion`: Student queries needing lecturer intervention.

## 4. Web Interface
- **Frontend**: Vanilla HTML/Tailwind CSS with Lucide icons.
- **Real-time**: Socket.IO for live messaging and status updates.
- **Lecturer Command Center**: A direct high-level chat interface for lecturers to "program" their AI or summarize student needs.

## 5. Deployment & Environment
- **Containerization**: `Dockerfile` ready for cloud deployment (Koyeb/Render).
- **Environment**: `.env` driven configuration for API keys and secrets.
- **Python Version**: Optimized for Python 3.13 stability.

## 6. Key Handover Tips
- When adding AI features, update `ai_engine.py` using `ask_groq_ai_direct` for standardized prompting.
- All new UI elements should follow the CSS variables defined in `layout.html` for theme support (Light/Dark).
- Use `db.session.commit()` explicitly within `app.app_context()` when running background jobs (like the scheduler).
