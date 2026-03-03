"""Quick script to check/register lecturer"""
from app import app
from models import db, Lecturer

with app.app_context():
    # Check for lecturers
    lecturers = Lecturer.query.all()

    print(f"\n{'='*50}")
    print(f"REGISTERED LECTURERS: {len(lecturers)}")
    print(f"{'='*50}\n")

    if lecturers:
        for lec in lecturers:
            print(f"Name: {lec.name}")
            print(f"Phone: {lec.phone_number}")
            print(f"Email: {lec.email}")
            print("-" * 50)
    else:
        print("No lecturers found! Let's register you.\n")

        phone = input("Enter your WhatsApp number (with country code, e.g., +234...): ").strip()
        if not phone.startswith('whatsapp:'):
            phone = 'whatsapp:' + phone

        name = input("Enter your name: ").strip()
        email = input("Enter your email (optional, press Enter to skip): ").strip() or None

        lecturer = Lecturer(
            phone_number=phone,
            name=name,
            email=email
        )

        db.session.add(lecturer)
        db.session.commit()

        print(f"\n[OK] Registered {name} with phone {phone}")
        print("You can now chat with the AI on WhatsApp!")
