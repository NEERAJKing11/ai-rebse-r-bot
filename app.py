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

# 1. लॉगिंग सेटअप
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# 2. KEYS लेना
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OWNER_ID = os.environ.get("OWNER_ID")

if not GEMINI_API_KEY or not TELEGRAM_BOT_TOKEN:
    logger.critical("❌ Keys Missing! Render Environment Variables check karein.")
    sys.exit(1)

genai.configure(api_key=GEMINI_API_KEY)

# 3. 🛡️ AUTO-MODEL SELECTOR (यह एरर को रोक देगा) 🛡️
# यह कोड चेक करेगा कि कौन सा मॉडल चल रहा है, और उसे ही चुनेगा।
def get_working_model():
    models_to_try = ['gemini-1.5-flash', 'gemini-1.5-flash-latest', 'gemini-pro']
    
    for m in models_to_try:
        try:
            logger.info(f"Testing Model: {m}...")
            test_model = genai.GenerativeModel(m)
            test_model.generate_content("Hi") # टेस्ट
            logger.info(f"✅ Success! Connected to: {m}")
            return test_model
        except Exception as e:
            logger.warning(f"⚠️ {m} failed: {e}")
            continue
    
    logger.error("❌ All models failed. Using default backup.")
    return genai.GenerativeModel('gemini-1.5-flash')

model = get_working_model()
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
user_ids = set()

# 4. HINDI AI BRAIN
def get_hindi_response(user_input, image=None):
    system_instruction = """
    ROLE: Hindi Teacher for Class 12 RBSE.
    LANGUAGE: ONLY HINDI (Devanagari).
    INSTRUCTIONS:
    1. Answer strictly in Hindi language.
    2. Explain concepts clearly.
    3. Use bullet points for long answers.
    """
    try:
        if image:
            response = model.generate_content([system_instruction, user_input, image])
        else:
            response = model.generate_content(f"{system_instruction}\nStudent asks: {user_input}")
        return response.text
    except Exception as e:
        logger.error(f"Generate Error: {e}")
        # अगर फिर भी एरर आये तो मॉडल रीसेट करो
        return "⚠️ सर्वर बिजी है। कृपया 1 मिनट बाद दोबारा पूछें।"

# 5. COMMANDS
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_ids.add(message.from_user.id)
    bot.reply_to(message, "नमस्ते! 🙏\nमैं आपका हिंदी AI टीचर हूँ।\nअपना सवाल पूछें या फोटो/PDF भेजें।")

@bot.message_handler(content_types=['document'])
def handle_pdf(message):
    if 'pdf' not in message.document.mime_type:
        bot.reply_to(message, "⚠️ सिर्फ PDF भेजें।")
        return
    msg = bot.reply_to(message, "📂 PDF पढ़ रहा हूँ...")
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        reader = PdfReader(io.BytesIO(downloaded))
        text = ""
        for page in reader.pages[:5]: text += page.extract_text() + "\n"
        
        reply = get_hindi_response(f"Context: {text[:10000]}.\nQuestion: Summarize this.", None)
        bot.edit_message_text(reply[:4000], message.chat.id, msg.message_id)
    except:
        bot.edit_message_text("❌ PDF नहीं पढ़ पाया।", message.chat.id, msg.message_id)

@bot.message_handler(content_types=['photo'])
def handle_image(message):
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        file_info = bot.get_file(message.photo[-1].file_id)
        img = Image.open(io.BytesIO(bot.download_file(file_info.file_path)))
        caption = message.caption if message.caption else "Isse samjhao"
        reply = get_hindi_response(caption, img)
        bot.reply_to(message, reply)
    except:
        bot.reply_to(message, "❌ इमेज एरर।")

@bot.message_handler(func=lambda m: True)
def handle_text(m):
    user_ids.add(m.from_user.id)
    bot.send_chat_action(m.chat.id, 'typing')
    bot.reply_to(m, get_hindi_response(m.text))

# 6. RENDER SERVER (Corrected)
# यहाँ हमने 'app' नाम दिया है जो Render ढूंढता है
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is Running Live!"

def run_http():
    app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    t = Thread(target=run_http)
    t.start()
    bot.infinity_polling()
