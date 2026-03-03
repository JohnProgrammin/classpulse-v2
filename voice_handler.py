"""
Voice Note Handler for ClassPulse
Handles voice note transcription via Groq Whisper API
"""

import requests
import tempfile
import os
from datetime import datetime
from config import Config

# Initialize Groq client (lazy load to avoid circular imports)
groq_client = None


def get_groq_client():
    """Get or initialize Groq client"""
    global groq_client
    if groq_client is None and Config.GROQ_API_KEY:
        from groq import Groq
        groq_client = Groq(api_key=Config.GROQ_API_KEY)
    return groq_client


def transcribe_voice_note(media_url, phone_number=None, course_id=None, is_meta=False):
    """
    Download and transcribe a voice note using Groq's Whisper API

    Args:
        media_url: Media URL (Twilio or Meta)
        phone_number: Sender's phone (for logging)
        course_id: Course ID (for logging)
        is_meta: True if using Meta WhatsApp API

    Returns:
        str: Transcribed text, or None if failed
    """
    if not Config.VOICE_TRANSCRIPTION_ENABLED:
        print("[VOICE] Voice transcription is disabled")
        return None

    client = get_groq_client()
    if not client:
        print("[ERROR] Groq client not initialized for voice transcription")
        return None

    # Import here to avoid circular imports
    from models import db, VoiceTranscription

    # Create transcription record for logging
    transcription_record = None
    if phone_number:
        try:
            transcription_record = VoiceTranscription(
                phone_number=phone_number,
                course_id=course_id,
                media_url=media_url,
                status='pending'
            )
            db.session.add(transcription_record)
            db.session.commit()
        except Exception as e:
            print(f"[WARN] Could not create transcription record: {e}")

    try:
        # Download audio file
        if is_meta:
            audio_data = download_meta_media(media_url)
        else:
            audio_data = download_twilio_media(media_url)

        if not audio_data:
            if transcription_record:
                transcription_record.status = 'failed'
                transcription_record.error_message = 'Failed to download media from Twilio'
                db.session.commit()
            return None

        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as temp_file:
            temp_file.write(audio_data)
            temp_path = temp_file.name

        try:
            # Transcribe using Groq Whisper
            with open(temp_path, 'rb') as audio_file:
                transcription = client.audio.transcriptions.create(
                    file=(os.path.basename(temp_path), audio_file.read()),
                    model="whisper-large-v3",
                    language="en",  # Can be made configurable for other languages
                    response_format="json"
                )

            transcribed_text = transcription.text.strip()

            # Update record
            if transcription_record:
                transcription_record.transcribed_text = transcribed_text
                transcription_record.status = 'completed'
                transcription_record.processed_at = datetime.utcnow()
                db.session.commit()

            print(f"[VOICE] Transcribed: {transcribed_text[:100]}...")
            return transcribed_text

        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

    except Exception as e:
        print(f"[ERROR] Voice transcription error: {e}")

        if transcription_record:
            try:
                transcription_record.status = 'failed'
                transcription_record.error_message = str(e)[:500]
                db.session.commit()
            except Exception:
                pass

        return None


def download_twilio_media(media_url):
    """
    Download media from Twilio (requires authentication)

    Args:
        media_url: Twilio media URL

    Returns:
        bytes: Audio data, or None if failed
    """
    if not media_url:
        return None

    try:
        # Twilio media URLs need Basic Auth with Account SID and Auth Token
        response = requests.get(
            media_url,
            auth=(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN),
            timeout=30
        )

        if response.status_code == 200:
            print(f"[VOICE] Downloaded {len(response.content)} bytes from Twilio")
            return response.content
        else:
            print(f"[ERROR] Failed to download media: HTTP {response.status_code}")
            return None

    except requests.exceptions.Timeout:
        print("[ERROR] Media download timed out")
        return None
    except Exception as e:
        print(f"[ERROR] Media download error: {e}")
        return None


def download_meta_media(media_url):
    """
    Download media from Meta WhatsApp Cloud API (requires Bearer token)

    Args:
        media_url: Meta media URL

    Returns:
        bytes: Audio data, or None if failed
    """
    if not media_url:
        return None

    try:
        headers = {
            "Authorization": f"Bearer {Config.META_WHATSAPP_TOKEN}"
        }

        response = requests.get(
            media_url,
            headers=headers,
            timeout=30
        )

        if response.status_code == 200:
            print(f"[VOICE] Downloaded {len(response.content)} bytes from Meta")
            return response.content
        else:
            print(f"[ERROR] Failed to download media from Meta: HTTP {response.status_code}")
            return None

    except requests.exceptions.Timeout:
        print("[ERROR] Meta media download timed out")
        return None
    except Exception as e:
        print(f"[ERROR] Meta media download error: {e}")
        return None


def is_voice_note(media_content_type):
    """
    Check if media is a voice note based on content type

    Args:
        media_content_type: MIME type from Twilio

    Returns:
        bool: True if it's an audio file
    """
    if not media_content_type:
        return False

    voice_types = [
        'audio/ogg',
        'audio/opus',
        'audio/mpeg',
        'audio/mp3',
        'audio/mp4',
        'audio/wav',
        'audio/x-wav',
        'audio/amr',
        'audio/aac',
        'audio/webm',
    ]

    media_type = media_content_type.lower().split(';')[0].strip()
    return any(media_type.startswith(vt) for vt in voice_types)


def is_supported_media(media_content_type):
    """
    Check if media type is supported for processing

    Args:
        media_content_type: MIME type from Twilio

    Returns:
        bool: True if supported
    """
    # Currently only support audio (voice notes)
    # Can be extended to support images, documents, etc.
    return is_voice_note(media_content_type)


def get_voice_processing_message():
    """Get the message to show while processing voice note"""
    return "Processing your voice message..."


def get_voice_error_message():
    """Get the error message when voice transcription fails"""
    return "I couldn't process that voice note. Please try again or send a text message instead."
