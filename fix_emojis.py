#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Fix Unicode emoji issues in source files"""

import os

# Emoji replacements
emoji_map = {
    '✅': '[OK]',
    '❌': '[ERROR]',
    '⚠️': '[WARNING]',
    '📩': '[MSG]',
    '📚': '[HELP]',
    '📝': '[SETUP]',
    '📢': '[BROADCAST]',
    '❓': '[QUESTION]',
    '🤷‍♂️': '',
    '🤷': '',
    '💡': '[INFO]',
    '🔗': '[LINK]',
    '⏰': '[SCHEDULED]',
    '🤖': '[AI]',
    '✋': '[STOP]',
    '👋': '',
    '🧠': '[*]',
    '📊': '[STATS]',
}

def fix_emojis_in_file(filepath):
    """Replace emojis in a file with ASCII alternatives"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        original = content
        for emoji, replacement in emoji_map.items():
            content = content.replace(emoji, replacement)

        if content != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Fixed: {filepath}")
            return True
        else:
            print(f"No changes: {filepath}")
            return False
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False

if __name__ == '__main__':
    files_to_fix = ['app.py', 'bot_handler.py', 'ai_engine.py']

    for filename in files_to_fix:
        filepath = os.path.join(os.path.dirname(__file__), filename)
        if os.path.exists(filepath):
            fix_emojis_in_file(filepath)
        else:
            print(f"File not found: {filepath}")

    print("\nDone!")
