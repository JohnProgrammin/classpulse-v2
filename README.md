# ClassPulse v2 - AI-Powered Course Communication System

## 🚀 What This Does
ClassPulse automates communication between lecturers and students using WhatsApp and AI. Lecturers can:
- Send broadcast announcements
- Schedule messages
- Let AI answer student questions
- Manage FAQs via web dashboard

## 📋 Prerequisites
- Python 3.8 or higher
- Twilio account (free tier works)
- Groq API key (optional but recommended)
- ngrok for local development

## 🔧 Installation Steps

### 1. Setup Virtual Environment
```bash
# Navigate to project folder
cd classpulse_v2

# Create virtual environment
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install flask twilio apscheduler sqlalchemy flask-sqlalchemy flask-login groq python-dotenv sentence-transformers
```

### 3. Get API Keys

#### Twilio (WhatsApp):
1. Go to https://console.twilio.com
2. Sign up for free account
3. Get your **Account SID** and **Auth Token**
4. Enable WhatsApp Sandbox: https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn
5. Note the sandbox number (e.g., `whatsapp:+14155238886`)

#### Groq (AI):
1. Go to https://console.groq.com
2. Sign up (free)
3. Create an API key
4. Copy it

### 4. Configure Environment Variables
Edit the `.env` file:
```bash
TWILIO_ACCOUNT_SID=your_actual_sid_here
TWILIO_AUTH_TOKEN=your_actual_token_here
TWILIO_PHONE_NUMBER=whatsapp:+14155238886
GROQ_API_KEY=your_groq_key_here
SECRET_KEY=change-this-to-random-string
```

### 5. Run the Application
```bash
python app.py
```

The app will run on `http://localhost:5000`

### 6. Setup ngrok (For Twilio Webhook)
In a new terminal:
```bash
# Download ngrok from https://ngrok.com
ngrok http 5000
```

Copy the HTTPS URL (e.g., `https://abc123.ngrok.io`)

### 7. Configure Twilio Webhook
1. Go to Twilio Console → WhatsApp Sandbox Settings
2. Under "When a message comes in", paste:
   ```
   https://your-ngrok-url.ngrok.io/bot
   ```
3. Set method to **POST**
4. Save

## 📱 How to Use

### For Lecturers:

#### 1. Register Your Course
Send to the Twilio WhatsApp number:
```
Register: Prof John, CSC302, Computer Networks
```

#### 2. Link Your WhatsApp Group
Add ClassPulse bot to your course group, then DM the bot:
```
/link +2349039517423
```
(Use any student number from the group)

#### 3. Available Commands (via WhatsApp DM):

**Broadcast Message:**
```
Broadcast: Class is cancelled tomorrow
```

**Schedule Message:**
```
Schedule 14:30: Reminder about assignment deadline
```

**Answer Student Question:**
```
Answer: The exam is on Friday at 10am in LT1
```

**Get Help:**
```
help
```

### For Students:
Students just ask questions in the WhatsApp group. The AI will:
1. Try to answer from FAQ database
2. Try to answer using Groq AI
3. Forward to lecturer if unsure

### Web Dashboard:
1. Go to `http://localhost:5000`
2. Click "Login"
3. Enter your WhatsApp number (e.g., `+2348155985292`)
4. Manage FAQs, view analytics, see pending questions

## 📊 Dashboard Features
- **Overview**: Statistics on messages, questions, FAQs
- **Knowledge Base**: Add/edit/delete FAQs
- **Pending Questions**: See what students asked
- **Scheduled Messages**: View and cancel scheduled posts
- **Message History**: See all sent messages
- **Analytics** (coming soon): Charts and insights

## 🐛 Troubleshooting

### Messages not sending?
- Check Twilio credentials in `.env`
- Verify ngrok is running
- Confirm webhook URL in Twilio console

### Database errors?
```bash
# Delete old database and restart
rm classpulse.db
python app.py
```

### AI not responding?
- Check Groq API key in `.env`
- Verify you're not hitting rate limits
- Check console logs for errors

### Can't login to dashboard?
- Make sure you registered via WhatsApp first
- Use exact phone number format: `+2348155985292`

## 🚀 Deployment (Production)

### Option 1: Render.com (Recommended)
1. Push code to GitHub
2. Connect to Render.com
3. Set environment variables
4. Deploy!

### Option 2: Railway.app
1. Connect GitHub repo
2. Add environment variables
3. Deploy

### Important for Production:
- Switch to PostgreSQL database
- Use proper domain instead of ngrok
- Enable HTTPS
- Add authentication with passwords
- Rate limit API endpoints

## 📂 Project Structure
```
classpulse_v2/
├── app.py              # Main Flask app
├── models.py           # Database models
├── config.py           # Configuration
├── bot_handler.py      # WhatsApp message logic
├── ai_engine.py        # Groq AI integration
├── .env                # Environment variables (SECRET!)
├── .gitignore          # Don't commit secrets
├── requirements.txt    # Dependencies
├── templates/          # HTML templates
│   ├── layout.html
│   ├── index.html
│   ├── login.html
│   ├── dashboard.html
│   └── course_detail.html
└── static/            # CSS/JS files
```

## 🔐 Security Notes
- **NEVER** commit `.env` file to GitHub
- `.gitignore` protects your secrets
- Use strong SECRET_KEY in production
- Enable password authentication later

## 🎯 Next Steps
1. ✅ Get system running locally
2. ✅ Test with one course
3. ⏳ Add password authentication
4. ⏳ Deploy to production
5. ⏳ Add advanced analytics
6. ⏳ Multi-language support
7. ⏳ Mobile app integration

## 💡 Tips
- Test with a small group first
- Answer questions to build FAQ database
- Schedule announcements ahead of time
- Check dashboard regularly for pending questions

## 🆘 Need Help?
- Check logs in terminal for errors
- Twilio console shows message logs
- Test webhook with Postman
- Review this README carefully

---

**Built with ❤️ for better education communication**