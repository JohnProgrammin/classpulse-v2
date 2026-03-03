"""
Meta WhatsApp Cloud API Integration for ClassPulse
Handles sending and receiving WhatsApp messages via Meta's API
"""

import requests
from config import Config


def send_whatsapp_message(to_number, message_text):
    """
    Send a WhatsApp message via Meta Cloud API

    Args:
        to_number: Recipient phone number (with or without whatsapp: prefix)
        message_text: Message content

    Returns:
        bool: True if sent successfully, False otherwise
    """
    # Clean the phone number - remove 'whatsapp:' prefix if present
    phone = to_number.replace('whatsapp:', '').replace('+', '').strip()

    # Ensure we have required config
    if not Config.META_WHATSAPP_TOKEN or not Config.META_PHONE_NUMBER_ID:
        print("[ERROR] Meta WhatsApp credentials not configured")
        return False

    url = f"https://graph.facebook.com/v18.0/{Config.META_PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {Config.META_WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    # Truncate message if too long
    if len(message_text) > Config.WHATSAPP_CHAR_LIMIT:
        message_text = message_text[:Config.WHATSAPP_CHAR_LIMIT - 30]
        message_text += "\n\n[Message truncated]"

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": message_text
        }
    }

    print(f"[SEND] Sending to: {phone}")
    print(f"[SEND] Message length: {len(message_text)} chars")

    try:
        response = requests.post(url, headers=headers, json=payload)
        result = response.json()

        if response.status_code == 200 and "messages" in result:
            message_id = result["messages"][0]["id"]
            print(f"[OK] Message sent! ID: {message_id}")
            return True
        else:
            print(f"[ERROR] Meta API error: {result}")
            return False

    except Exception as e:
        print(f"[ERROR] Failed to send message: {e}")
        return False


def verify_webhook(request_args):
    """
    Verify Meta webhook subscription

    Args:
        request_args: Flask request.args

    Returns:
        tuple: (response_text, status_code)
    """
    mode = request_args.get("hub.mode")
    token = request_args.get("hub.verify_token")
    challenge = request_args.get("hub.challenge")

    if mode == "subscribe" and token == Config.META_VERIFY_TOKEN:
        print("[OK] Webhook verified successfully")
        return challenge, 200
    else:
        print("[ERROR] Webhook verification failed")
        return "Forbidden", 403


def parse_incoming_message(data):
    """
    Parse incoming webhook data from Meta

    Args:
        data: JSON data from webhook

    Returns:
        dict with: sender, message_text, message_type, media_url, media_type
        or None if not a message
    """
    try:
        # Navigate Meta's nested structure
        entry = data.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})

        # Check if this is a message
        messages = value.get("messages", [])
        if not messages:
            return None

        message = messages[0]
        sender = message.get("from", "")
        message_type = message.get("type", "text")

        result = {
            "sender": f"whatsapp:+{sender}",
            "message_text": "",
            "message_type": message_type,
            "media_url": None,
            "media_type": None
        }

        # Extract message content based on type
        if message_type == "text":
            result["message_text"] = message.get("text", {}).get("body", "")

        elif message_type == "audio":
            # Voice note
            audio = message.get("audio", {})
            result["media_url"] = audio.get("id")  # This is a media ID, need to fetch
            result["media_type"] = audio.get("mime_type", "audio/ogg")
            result["message_type"] = "voice"

        elif message_type == "image":
            image = message.get("image", {})
            result["media_url"] = image.get("id")
            result["media_type"] = image.get("mime_type", "image/jpeg")
            result["message_text"] = image.get("caption", "")

        elif message_type == "document":
            doc = message.get("document", {})
            result["media_url"] = doc.get("id")
            result["media_type"] = doc.get("mime_type")
            result["message_text"] = doc.get("caption", "")

        return result

    except Exception as e:
        print(f"[ERROR] Failed to parse message: {e}")
        return None


def get_media_url(media_id):
    """
    Get the actual URL for a media file from its ID

    Args:
        media_id: Meta media ID

    Returns:
        str: Media URL or None
    """
    if not media_id:
        return None

    url = f"https://graph.facebook.com/v18.0/{media_id}"
    headers = {
        "Authorization": f"Bearer {Config.META_WHATSAPP_TOKEN}"
    }

    try:
        response = requests.get(url, headers=headers)
        result = response.json()
        return result.get("url")
    except Exception as e:
        print(f"[ERROR] Failed to get media URL: {e}")
        return None


def download_media(media_url):
    """
    Download media file from Meta's servers

    Args:
        media_url: URL from get_media_url()

    Returns:
        bytes: Media content or None
    """
    if not media_url:
        return None

    headers = {
        "Authorization": f"Bearer {Config.META_WHATSAPP_TOKEN}"
    }

    try:
        response = requests.get(media_url, headers=headers)
        if response.status_code == 200:
            return response.content
        return None
    except Exception as e:
        print(f"[ERROR] Failed to download media: {e}")
        return None
