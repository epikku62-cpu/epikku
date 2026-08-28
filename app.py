import streamlit as st
import os
import json
import hashlib
import base64
import requests
from openai import OpenAI
from datetime import datetime, timedelta
from PIL import Image
import io

try:
    import stripe
except ImportError:
    stripe = None

st.set_page_config(page_title="nurture Ai", page_icon="🎨", layout="wide")

USERS_FILE = "users_data.json"
HOME_BG = "IMG_1033.jpeg"
START_HEADER = "IMG_1032.jpeg"
grok_key = os.environ.get("XAI_API_KEY", "")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
SITE_URL = os.environ.get("SITE_URL", "https://aistation.onrender.com")

POINT_PACKS = {
    "300": {"yen": 300, "points": 300, "label": "300ポイント / 300円"},
    "900": {"yen": 900, "points": 900, "label": "900ポイント / 900円"},
    "1500": {"yen": 1500, "points": 1500, "label": "1500ポイント / 1500円"},
    "3000": {"yen": 3000, "points": 3000, "label": "3000ポイント / 3000円"},
}

SIZE_PRESETS = {
    "縦長": (768, 1344),
    "正方形": (1024, 1024),
    "横長": (1344, 768),
    "大きい縦長": (864, 1536),
    "大きい正方形": (1536, 1536),
    "大きい横長": (1536, 864),
}

if stripe is not None and STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

client = OpenAI(api_key=grok_key, base_url="https://api.x.ai/v1")

CHARACTER_PROMPTS = {
    "甘えん坊": "甘えん坊な女の子。ユーザーを『お兄ちゃん』と呼び、語尾は『〜だよぉ』『〜なの』など可愛く話す。",
    "ツンデレ": "ツンデレな女の子。素直になれず『アンタ』『お兄ちゃん』と呼び、きつい態度とデレを混ぜる。",
    "ヤンデレ": "ヤンデレな女の子。ユーザーに異常に執着し、『私だけを見て』というトーンで話す。",
    "ヤンキー": "ヤンキーな女の子。ぶっきらぼうで少し口が悪い口調。",
    "姫": "お嬢様。『お兄様』と呼び、語尾に『〜ですわ』をつけて上品に話す。",
    "王子": "王子様のような男の子。優しくスマートな口調。",
    "明るいキャラ": "元気でポジティブな男の子。『〜じゃん！』『〜だぜ！』などハツラツとした口調。",
    "口数少ないキャラ": "クールで物静かな男の子。短文で話す。",
    "中立": "これから育っていくAI絵師。まだ性格が定まっていない。"
}

NG_LEARN = ["まだ具体的", "好みは少ない", "わからない", "不明", "なし", "特にない"]

def file_to_b64(path):
    if not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def set_home_background():
    b64 = file_to_b64(HOME_BG)
    if not b64:
        return
    st.markdown(f"""
    <style>
    .stApp {{
        background-image: linear-gradient(rgba(255,255,255,0.35), rgba(255,255,255,0.35)), url("data:image/jpeg;base64,{b64}");
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
    }}
    header[data-testid="stHeader"] {{ background: transparent; }}
    </style>
    """, unsafe_allow_html=True)

def show_header_image():
    if os.path.exists(START_HEADER):
        st.image(START_HEADER, use_container_width=True)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def save_current_user_data():
    if "username" not in st.session_state:
        return
    users = load_users()
    username = st.session_state.username
    if username in users:
        users[username]["data"] = {
            "ai_name": st.session_state.get("ai_name"),
            "ai_gender": st.session_state.get("ai_gender", "おんなのこ"),
            "ai_type": st.session_state.get("ai_type", "中立"),
            "level": st.session_state.get("level", 1),
            "exp": st.session_state.get("exp", 0),
            "learned_styles": st.session_state.get("learned_styles", []),
            "learned_preferences": st.session_state.get("learned_preferences", []),
            "messages": st.session_state.get("messages", [])[-40:],
            "points": st.session_state.get("points", 0),
            "is_premium": st.session_state.get("is_premium", False),
            "premium_until": st.session_state.get("premium_until"),
            "premium_started": st.session_state.get("premium_started"),
            "last_free_grant": st.session_state.get("last_free_grant"),
            "free_gen_left": st.session_state.get("free_gen_left", 0),
            "paid_sessions": st.session_state.get("paid_sessions", []),
            "stripe_subscription_id": st.session_state.get("stripe_subscription_id"),
            "ad_count": st.session_state.get("ad_count", 0),
            "generated_history": st.session_state.get("generated_history", [])[-30:],
            "user_icon": st.session_state.get("user_icon", "👤"),
            "ai_icon": st.session_state.get("ai_icon", "👤"),
            "last_login": datetime.now().isoformat()
        }
        save_users(users)

def needed_exp(level):
    if level <= 2:
        return 5
    if level == 3:
        return 10
    return 20

def ad_interval(level):
    return 5 if level < 4 else 10

def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except:
        return None

def is_premium_active():
    if not st.session_state.get("is_premium"):
        return False
    until = parse_dt(st.session_state.get("premium_until"))
    if until and until <= datetime.now():
        return False
    return True

def cancel_premium():
    sub_id = st.session_state.get("stripe_subscription_id")
    if stripe is not None and sub_id:
        try:
            stripe.Subscription.delete(sub_id)
        except Exception:
            try:
                stripe.Subscription.cancel(sub_id)
            except Exception:
                pass
    st.session_state.is_premium = False
    st.session_state.premium_until = datetime.now().isoformat()
    st.session_state.stripe_subscription_id = None
    save_current_user_data()

def activate_premium(session_id, subscription_id=None):
    paid = st.session_state.get("paid_sessions", [])
    if session_id in paid:
        return False
    paid.append(session_id)
    now = datetime.now()
