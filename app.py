import telebot
import google.generativeai as genai
import os
import io
import sys
import logging
import time
from flask import Flask
from threading import Thread
from PIL import Image
from PyPDF2 import PdfReader

# ================= 1. प्रोफेशनल लॉगिंग (Professional Logging) =================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# ================= 2. KEYS और सुरक्षा (Security) =================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OWNER_ID = os.environ.get("OWNER_ID")

# अगर Keys नहीं मिलीं तो बॉट बंद हो जाएगा (Safety)
if not GEMINI_API_KEY or not TELEGRAM_BOT_TOKEN:
    logger.critical("❌ CRITICAL ERROR: Keys Missing! Check Render Environment Variables.")
    sys.exit(1)

genai.configure(api_key=GEMINI_API_KEY)

# ================= 3. 🛡️ AUTO-MODEL FIXER (जादुई कोड) 🛡️ =================
# यह अपने आप सही मॉडल ढूंढेगा ताकि 404 Error कभी न आए
def get_working_model():
    models_to_try = ['gemini-1.5-flash', 'gemini-1.5-flash-latest', 'gemini-pro']
    
    for m in models_to_try:
        try:
            logger.info(f"Testing Model Connection: {m}...")
            test_model = genai.GenerativeModel(m)
            test_model.generate_content("Hello") # छोटा टेस्ट
            logger.info(f"✅ Success! Bot connected to: {m}")
            return test_model
        except Exception as e:
            logger.warning(f"⚠️ Model {m} failed. Trying next...")
            continue
    
    logger.error("❌ All models failed. Using backup.")
    return genai.GenerativeModel('gemini-1.5-flash')

# मॉडल सेट हो गया
model = get_working_model()
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# ब्रॉडकास्ट के लिए यूजर लिस्ट
user_ids = set()

# ================= 4. हिंदी टीचर का दिमाग (HINDI BRAIN) =================
def get_hindi_response(user_input, image=None):
    # यह प्रॉम्प्ट बॉट को सिर्फ हिंदी बोलने पर मजबूर करेगा
    system_instruction = """
    ROLE: Expert Teacher for Class 12 RBSE (Rajasthan Board).
    LANGUAGE: STRICTLY HINDI (Devanagari Script).
    
    INSTRUCTIONS:
    1. छात्र के हर सवाल का जवाब शुद्ध हिंदी में दें।
    2. अगर सवाल इंग्लिश में भी हो, तो भी जवाब हिंदी में ही दें।
    3. जवाब विस्तार से (Detailed) और बुलेट पॉइंट्स में दें।
    4. छात्र को प्यार से समझाएं।
    """
    
    try:
        if image:
            response = model.generate_content([system_instruction, user_input, image])
        else:
            response = model.generate_content(f"{system_instruction}\nStudent Question: {user_input}")
        return response.text
    except Exception as e:
        logger.error(f"AI Generation Error: {e}")
        return "⚠️ सर्वर बिजी है या की (Key) में दिक्कत है। कृपया थोड़ी देर बाद प्रयास करें।"

# ================= 5. बॉट फीचर्स (FEATURES) =================

# --- स्टार्ट कमांड ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_ids.add(message.from_user.id)
    welcome_msg = (
        "नमस्ते विद्यार्थी! 🙏\n\n"
        "मैं आपका **Class 12 RBSE Hindi Bot** हूँ।\n"
        "मैं आपकी पढ़ाई में मदद करूँगा।\n\n"
        "📚 **सुविधाएं:**\n"
        "👉 अपना सवाल लिखकर पूछें।\n"
        "👉 अपनी किताब का फोटो भेजें।\n"
        "👉 अपने नोट्स की PDF भेजें।\n\n"
        "मैं सब कुछ **हिंदी** में समझाऊंगा। चलिए शुरू करते हैं!"
    )
    bot.reply_to(message, welcome_msg, parse_mode='Markdown')

# --- PDF हैंडलर (Pro Feature) ---
@bot.message_handler(content_types=['document'])
def handle_pdf(message):
    if 'pdf' not in message.document.mime_type:
        bot.reply_to(message, "⚠️ कृपया सिर्फ PDF फाइल भेजें।")
        return
    
    msg = bot.reply_to(message, "📂 **PDF स्कैन हो रही है...** (कृपया प्रतीक्षा करें)")
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        reader = PdfReader(io.BytesIO(downloaded))
        
        text = ""
        # स्पीड के लिए पहले 5 पेज
        for page in reader.pages[:5]:
            text += page.extract_text() + "\n"
            
        if len(text) < 50:
            bot.edit_message_text("❌ PDF खाली है या पढ़ी नहीं जा रही।", message.chat.id, msg.message_id)
            return

        user_query = message.caption if message.caption else "इस PDF का हिंदी सारांश (Summary) बताओ।"
        prompt = f"Context from PDF: {text[:15000]}.\nTask: {user_query}"
        
        reply = get_hindi_response(prompt)
        
        # बड़े जवाब को टुकड़ों में भेजना
        if len(reply) > 4000:
            bot.send_message(message.chat.id, reply[:4000], parse_mode='Markdown')
        else:
            bot.edit_message_text(reply, chat_id=message.chat.id, message_id=msg.message_id, parse_mode='Markdown')
            
    except Exception as e:
        bot.edit_message_text(f"❌ PDF Error: {e}", chat_id=message.chat.id, message_id=msg.message_id)

# --- फोटो हैंडलर (Image Feature) ---
@bot.message_handler(content_types=['photo'])
def handle_image(message):
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        file_info = bot.get_file(message.photo[-1].file_id)
        img_data = bot.download_file(file_info.file_path)
        image = Image.open(io.BytesIO(img_data))
        
        caption = message.caption if message.caption else "इस चित्र को हिंदी में समझाओ।"
        reply = get_hindi_response(caption, image)
        
        bot.reply_to(message, reply, parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, "❌ फोटो लोड नहीं हो पाई।")

# --- ब्रॉडकास्ट (Sirf Owner Ke Liye) ---
@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    # चेक करें कि क्या मैसेज भेजने वाला Owner है
    if str(message.from_user.id) != OWNER_ID:
        bot.reply_to(message, "⛔ यह कमांड सिर्फ एडमिन के लिए है।")
        return
    
    msg_text = message.text.replace("/broadcast", "").strip()
    if not msg_text:
        bot.reply_to(message, "⚠️ लिखें: `/broadcast आपका संदेश`")
        return
    
    count = 0
    for uid in user_ids:
        try:
            bot.send_message(uid, f"📢 **महत्वपूर्ण सूचना:**\n\n{msg_text}", parse_mode='Markdown')
            count += 1
        except:
            pass # अगर किसी ने ब्लॉक किया है तो छोड़ दो
            
    bot.reply_to(message, f"✅ संदेश {count} छात्रों को सफलतापूर्वक भेज दिया गया।")

# --- टेक्स्ट हैंडलर ---
@bot.message_handler(func=lambda m: True)
def handle_text(m):
    user_ids.add(m.from_user.id)
    bot.send_chat_action(m.chat.id, 'typing')
    reply = get_hindi_response(m.text)
    bot.reply_to(m, reply, parse_mode='Markdown')

# ================= 6. रेंडर सर्वर (RENDER SERVER FIX) =================
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Hindi Pro Bot is Live & Running!"

def run_http():
    # यह पोर्ट लाइन Render के लिए सबसे ज़रूरी है
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    t = Thread(target=run_http)
    t.start()
    bot.infinity_polling()
