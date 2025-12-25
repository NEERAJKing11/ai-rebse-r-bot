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

# ================= 1. SETUP & CONFIGURATION =================
# लॉगिंग सेटअप (ताकि एरर का पता चले)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Render से Keys लेना
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OWNER_ID = os.environ.get("OWNER_ID")

# अगर Keys नहीं हैं तो बॉट स्टार्ट नहीं होगा
if not GEMINI_API_KEY or not TELEGRAM_BOT_TOKEN:
    logger.critical("❌ ERROR: Keys Missing! Render Environment Variables check karein.")
    sys.exit(1)

genai.configure(api_key=GEMINI_API_KEY)

# --- MODEL FIX (सबसे ज़रूरी हिस्सा) ---
# यह कोड चेक करेगा कि Google का कौन सा मॉडल काम कर रहा है
valid_models = ['gemini-1.5-flash', 'gemini-1.5-flash-latest', 'gemini-pro']
model = None

for m in valid_models:
    try:
        # टेस्ट कर रहे हैं
        test_m = genai.GenerativeModel(m)
        test_m.generate_content("Test")
        model = test_m
        logger.info(f"✅ Selected Model: {m}")
        break
    except:
        continue

# अगर कोई मॉडल न मिले तो डिफ़ॉल्ट
if not model:
    model = genai.GenerativeModel('gemini-1.5-flash')

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
user_ids = set() # ब्रॉडकास्ट के लिए डेटाबेस

# ================= 2. HINDI AI BRAIN =================
def get_hindi_response(user_input, image=None):
    # यह प्रॉम्प्ट बॉट को "हिंदी टीचर" बनाता है
    system_instruction = """
    ROLE: You are an expert Class 12 RBSE Tutor.
    LANGUAGE: STRICTLY HINDI (Devanagari Script).
    INSTRUCTIONS:
    1. छात्र के हर सवाल का जवाब शुद्ध और सरल हिंदी में दो।
    2. अगर सवाल इंग्लिश में भी हो, तो भी जवाब हिंदी में ही देना है।
    3. जवाब में महत्वपूर्ण बिंदुओं (Key Points) को बुलेट पॉइंट्स में लिखो।
    4. छात्र को "बेटा" या "दोस्त" कहकर संबोधित करो।
    
    Question:
    """
    
    try:
        if image:
            response = model.generate_content([system_instruction, user_input, image])
        else:
            response = model.generate_content(f"{system_instruction}\n{user_input}")
        return response.text
    except Exception as e:
        logger.error(f"AI Error: {e}")
        return "क्षमा करें, तकनीकी समस्या के कारण जवाब नहीं आ रहा। कृपया पुनः प्रयास करें।"

# ================= 3. BOT COMMANDS =================

@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_ids.add(message.from_user.id)
    welcome_msg = (
        "नमस्ते विद्यार्थी! 🙏\n\n"
        "मैं आपका **हिंदी AI टीचर** हूँ।\n"
        "मैं कक्षा 12वीं (RBSE) की पढ़ाई में आपकी मदद करूँगा।\n\n"
        "आप मुझे भेज सकते हैं:\n"
        "📝 **सवाल:** अपना प्रश्न लिखकर भेजें।\n"
        "📸 **फोटो:** किताब के पेज की फोटो भेजें।\n"
        "📂 **PDF:** अपने नोट्स की PDF फाइल भेजें।\n\n"
        "मैं आपको सबकुछ **हिंदी में** समझाऊंगा। चलिए शुरू करते हैं!"
    )
    bot.reply_to(message, welcome_msg, parse_mode='Markdown')

# --- PDF HANDLER ---
@bot.message_handler(content_types=['document'])
def handle_pdf(message):
    if 'pdf' not in message.document.mime_type:
        bot.reply_to(message, "⚠️ कृपया सिर्फ PDF फाइल ही भेजें।")
        return
    
    msg = bot.reply_to(message, "📂 **PDF पढ़ी जा रही है...** (कृपया प्रतीक्षा करें)")
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        reader = PdfReader(io.BytesIO(downloaded))
        
        text = ""
        # पहले 10 पेज पढ़ेगा
        for page in reader.pages[:10]:
            text += page.extract_text() + "\n"
            
        user_query = message.caption if message.caption else "इस PDF का सारांश (Summary) बताओ।"
        prompt = f"Context: {text[:20000]}.\nTask: {user_query}\nAnswer in HINDI."
        
        reply = get_hindi_response(prompt)
        
        if len(reply) > 4000:
            for x in range(0, len(reply), 4000):
                bot.send_message(message.chat.id, reply[x:x+4000], parse_mode='Markdown')
        else:
            bot.edit_message_text(reply, chat_id=message.chat.id, message_id=msg.message_id, parse_mode='Markdown')
            
    except Exception as e:
        bot.edit_message_text("❌ PDF पढ़ने में त्रुटि हुई। फाइल सही नहीं है।", chat_id=message.chat.id, message_id=msg.message_id)

# --- IMAGE HANDLER ---
@bot.message_handler(content_types=['photo'])
def handle_image(message):
    bot.send_chat_action(message.chat.id, 'typing')
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        img_data = bot.download_file(file_info.file_path)
        image = Image.open(io.BytesIO(img_data))
        
        query = message.caption if message.caption else "इस चित्र (Image) को विस्तार से समझाओ।"
        reply = get_hindi_response(query, image)
        
        bot.reply_to(message, reply, parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, "❌ चित्र लोड नहीं हो पाया।")

# --- BROADCAST (Owner Only) ---
@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    if str(message.from_user.id) != OWNER_ID:
        return
    
    msg = message.text.replace("/broadcast", "").strip()
    if msg:
        count = 0
        for uid in user_ids:
            try:
                bot.send_message(uid, f"📢 **महत्वपूर्ण सूचना:**\n\n{msg}", parse_mode='Markdown')
                count += 1
            except: pass
        bot.reply_to(message, f"✅ संदेश {count} छात्रों को भेज दिया गया।")

# --- TEXT HANDLER ---
@bot.message_handler(func=lambda m: True)
def handle_text(m):
    user_ids.add(m.from_user.id)
    bot.send_chat_action(m.chat.id, 'typing')
    reply = get_hindi_response(m.text)
    bot.reply_to(m, reply, parse_mode='Markdown')

# ================= 4. RENDER SERVER =================
app = Flask('')

@app.route('/')
def home():
    return "Hindi Bot is Running! Jai Hind. 🇮🇳"

def run_http():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    Thread(target=run_http).start()
    bot.infinity_polling()
