import sqlite3
import os

db_path = os.path.join('c:\\Users\\HP\\Documents\\classpulse_v2', 'instance', 'classpulse.db')
if not os.path.exists(db_path):
    # Check current directory
    db_path = 'c:\\Users\\HP\\Documents\\classpulse_v2\\classpulse.db'

print(f"Checking database at: {db_path}")
try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lecturers';")
    result = cursor.fetchone()
    if result:
        print("[OK] 'lecturers' table found!")
    else:
        print("[ERROR] 'lecturers' table still missing.")
    conn.close()
except Exception as e:
    print(f"[ERROR] {e}")
