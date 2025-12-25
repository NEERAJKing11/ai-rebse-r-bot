import telebot
import google.generativeai as genai
import os
import io
import sys
import logging
from flask import Flask
from threading import Thread
from PIL import Image
from PyPDF2 import PdfReader

# ================= 1. SETUP & LOGGING =================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OWNER_ID = os.environ.get("OWNER_ID")

if not GEMINI_API_KEY or not TELEGRAM_BOT_TOKEN:
    logger.critical("❌ ERROR: Keys Missing! Check Render Settings.")
    sys.exit(1)

genai.configure(api_key=GEMINI_API_KEY)

# --- FIX IS HERE: Updated Model Name ---
# हमने यहाँ नाम बदलकर 'gemini-1.5-flash-latest' कर दिया है जो हमेशा काम करता है
try:
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
except:
    # अगर वह भी काम न करे, तो यह बैकअप मॉडल है
    model = genai.GenerativeModel('gemini-1.5-flash-001')

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
user_ids = set()

# ================= 2. AI BRAIN =================
def get_ai_response(prompt, image=None):
    try:
        if image:
            response = model.generate_content([prompt, image])
        else:
            response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"⚠️ Error: {str(e)}\n(Try asking again in 1 minute)"

# ================= 3. FEATURES =================

@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_ids.add(message.from_user.id)
    welcome_text = (
        "🎓 **RBSE Pro Bot is Ready!**\n\n"
        "🟢 Status: Online\n"
        "⚡ Model: Gemini 1.5 Flash\n\n"
        "Send Text, Photo or PDF."
    )
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(content_types=['document'])
def handle_pdf(message):
    if 'pdf' not in message.document.mime_type:
        bot.reply_to(message, "❌ Only PDF files please.")
        return
    
    msg = bot.reply_to(message, "📂 **Reading PDF...**")
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        reader = PdfReader(io.BytesIO(downloaded))
        
        text = ""
        # Read first 5 pages for speed
        for page in reader.pages[:5]:
            text += page.extract_text() + "\n"
            
        user_query = message.caption if message.caption else "Summarize this."
        prompt = f"Role: Teacher. Context: {text[:20000]}.\nQuestion: {user_query}"
        
        reply = get_ai_response(prompt)
        
        if len(reply) > 4000:
            for x in range(0, len(reply), 4000):
                bot.send_message(message.chat.id, reply[x:x+4000], parse_mode='Markdown')
        else:
            bot.edit_message_text(reply, chat_id=message.chat.id, message_id=msg.message_id, parse_mode='Markdown')
            
    except Exception as e:
        bot.edit_message_text(f"❌ Error: {e}", chat_id=message.chat.id, message_id=msg.message_id)

@bot.message_handler(content_types=['photo'])
def handle_image(message):
    bot.send_chat_action(message.chat.id, 'typing')
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        img_data = bot.download_file(file_info.file_path)
        image = Image.open(io.BytesIO(img_data))
        
        query = message.caption if message.caption else "Explain this image."
        reply = get_ai_response(query, image)
        bot.reply_to(message, reply, parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    if str(message.from_user.id) != OWNER_ID: return
    msg = message.text.replace("/broadcast", "").strip()
    if msg:
        for uid in user_ids:
            try: bot.send_message(uid, f"📢 {msg}")
            except: pass
        bot.reply_to(message, "Sent!")

@bot.message_handler(func=lambda m: True)
def handle_text(m):
    user_ids.add(m.from_user.id)
    bot.send_chat_action(m.chat.id, 'typing')
    reply = get_ai_response(f"Student: {m.text}\nTeacher (RBSE):")
    bot.reply_to(m, reply, parse_mode='Markdown')

# ================= 4. RENDER SERVER =================
app = Flask('')

@app.route('/')
def home():
    return "Bot is Running! (Fixed Version)"

def run_http():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    Thread(target=run_http).start()
    bot.infinity_polling()
