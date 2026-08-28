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
    st.session_state.paid_sessions = paid[-50:]
    st.session_state.is_premium = True
    st.session_state.premium_started = now.isoformat()
    st.session_state.premium_until = (now + timedelta(days=30)).isoformat()
    st.session_state.last_free_grant = now.isoformat()
    st.session_state.points += 1200
    st.session_state.free_gen_left = 50
    if subscription_id:
        st.session_state.stripe_subscription_id = subscription_id
    save_current_user_data()
    return True

def activate_points(session_id, points):
    paid = st.session_state.get("paid_sessions", [])
    if session_id in paid:
        return False
    paid.append(session_id)
    st.session_state.paid_sessions = paid[-50:]
    st.session_state.points += int(points)
    save_current_user_data()
    return True

def grant_free_gens_if_needed():
    if not is_premium_active():
        return
    now = datetime.now()
    last = parse_dt(st.session_state.get("last_free_grant"))
    if last is None:
        st.session_state.last_free_grant = now.isoformat()
        st.session_state.free_gen_left = 50
        if not st.session_state.get("premium_started"):
            st.session_state.premium_started = now.isoformat()
        save_current_user_data()
        return
    renewed = False
    while last + timedelta(days=30) <= now:
        last = last + timedelta(days=30)
        st.session_state.free_gen_left = 50
        renewed = True
    if renewed:
        st.session_state.last_free_grant = last.isoformat()
        st.session_state.premium_until = (now + timedelta(days=30)).isoformat()
        save_current_user_data()

def calc_generation_cost(quality, width, height, ref_count, use_free=False):
    is_2k = max(width, height) >= 1536
    resolution = "2k" if (is_2k or quality == "medium") else "1k"
    cost = 10 if quality == "low" else 20
    size_add = 5 if is_2k else 0
    ref_add = 5 * ref_count
    cost = size_add + ref_add if use_free else cost + size_add + ref_add
    return cost, resolution, size_add, ref_add

def file_to_data_uri(uploaded_file):
    raw = uploaded_file.getvalue()
    mime = uploaded_file.type or "image/png"
    return f"data:{mime};base64,{base64.b64encode(raw).decode('utf-8')}"

def ratio_from_size(w, h):
    if w <= 0 or h <= 0:
        return "1:1"
    r = w / h
    choices = {"1:1": 1.0, "3:4": 0.75, "4:3": 1.33, "9:16": 0.5625, "16:9": 1.777, "2:3": 0.666, "3:2": 1.5}
    return min(choices.items(), key=lambda x: abs(x[1] - r))[0]

def generate_text_image(prompt, aspect_ratio, resolution, quality):
    response = client.images.generate(
        model="grok-imagine-image-2.0",
        prompt=prompt,
        n=1,
        extra_body={"aspect_ratio": aspect_ratio, "resolution": resolution, "quality": quality}
    )
    return response.data[0].url

def generate_with_references(prompt, aspect_ratio, resolution, quality, image_uris):
    payload = {
        "model": "grok-imagine-image-2.0",
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "quality": quality,
        "response_format": "url"
    }
    if len(image_uris) == 1:
        payload["image"] = {"url": image_uris[0], "type": "image_url"}
    else:
        payload["images"] = [{"url": uri, "type": "image_url"} for uri in image_uris[:3]]
    res = requests.post(
        "https://api.x.ai/v1/images/edits",
        headers={"Authorization": f"Bearer {grok_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=180
    )
    data = res.json()
    if res.status_code != 200:
        raise Exception(data)
    return data["data"][0]["url"]

def analyze_image_style(uploaded_file):
    try:
        image = Image.open(uploaded_file)
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode()
        completion = client.chat.completions.create(
            model="grok-4-fast",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "この絵のタッチ、塗り、線、雰囲気を短い日本語1文で。"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
            ]}],
            max_tokens=80
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        return f"分析失敗（{e}）"

def init_new_user_state(username):
    st.session_state.logged_in = True
    st.session_state.username = username
    st.session_state.ai_name = None
    st.session_state.ai_gender = "おんなのこ"
    st.session_state.ai_type = "中立"
    st.session_state.level = 1
    st.session_state.exp = 0
    st.session_state.learned_styles = []
    st.session_state.learned_preferences = []
    st.session_state.messages = []
    st.session_state.points = 0
    st.session_state.is_premium = False
    st.session_state.premium_until = None
    st.session_state.premium_started = None
    st.session_state.last_free_grant = None
    st.session_state.paid_sessions = []
    st.session_state.ad_count = 0
    st.session_state.generated_history = []
    st.session_state.user_icon = "👤"
    st.session_state.ai_icon = "👤"
    st.session_state.free_gen_left = 0
    st.session_state.stripe_subscription_id = None
    st.session_state.current_mode = "chat"
    st.session_state.auth_page = "setup"
    st.session_state.waiting_for_ai = False

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = None
if "auth_page" not in st.session_state:
    st.session_state.auth_page = "home"
if "generated_history" not in st.session_state:
    st.session_state.generated_history = []
if "user_icon" not in st.session_state:
    st.session_state.user_icon = "👤"
if "ai_icon" not in st.session_state:
    st.session_state.ai_icon = "👤"
if "current_mode" not in st.session_state:
    st.session_state.current_mode = "chat"
if "last_generated_image" not in st.session_state:
    st.session_state.last_generated_image = None
if "learned_preferences" not in st.session_state:
    st.session_state.learned_preferences = []
if "learned_styles" not in st.session_state:
    st.session_state.learned_styles = []
if "is_premium" not in st.session_state:
    st.session_state.is_premium = False
if "premium_until" not in st.session_state:
    st.session_state.premium_until = None
if "premium_started" not in st.session_state:
    st.session_state.premium_started = None
if "last_free_grant" not in st.session_state:
    st.session_state.last_free_grant = None
if "paid_sessions" not in st.session_state:
    st.session_state.paid_sessions = []
if "free_gen_left" not in st.session_state:
    st.session_state.free_gen_left = 0
if "stripe_subscription_id" not in st.session_state:
    st.session_state.stripe_subscription_id = None
if "gen_w" not in st.session_state:
    st.session_state.gen_w = 1024
if "gen_h" not in st.session_state:
    st.session_state.gen_h = 1024
if "waiting_for_ai" not in st.session_state:
    st.session_state.waiting_for_ai = False

query = st.query_params
if st.session_state.get("logged_in") and stripe is not None and query.get("session_id"):
    session_id = query.get("session_id")
    try:
        checkout = stripe.checkout.Session.retrieve(session_id)
        if checkout.get("client_reference_id") == st.session_state.get("username") and checkout.get("status") in ["complete", "paid"]:
            kind = (checkout.get("metadata") or {}).get("kind", "premium")
            if kind == "points":
                pts = int((checkout.get("metadata") or {}).get("points", "0"))
                if activate_points(session_id, pts):
                    st.success(f"ポイント購入完了。{pts}pt を付与しました。")
            else:
                if activate_premium(session_id, checkout.get("subscription")):
                    st.success("月額会員になりました。1200pt と画像生成50回無料を付与しました。")
        st.query_params.clear()
    except Exception as e:
        st.error(f"決済確認に失敗しました: {e}")

if not st.session_state.logged_in:
    if st.session_state.auth_page == "home":
        set_home_background()
        top = st.columns([5, 1])
        with top[1]:
            if st.button("ログイン", use_container_width=True):
                st.session_state.auth_page = "login"
                st.rerun()
        st.markdown("<div style='height:58vh'></div>", unsafe_allow_html=True)
        mid = st.columns([1, 2, 1])
        with mid[1]:
            if st.button("登録して始める", type="primary", use_container_width=True):
                st.session_state.auth_page = "register"
                st.rerun()
        st.stop()

    if st.session_state.auth_page == "login":
        if st.button("← ホームへ"):
            st.session_state.auth_page = "home"
            st.rerun()
        st.title("ログイン")
        login_user = st.text_input("ユーザー名", key="login_user")
        login_pass = st.text_input("パスワード", type="password", key="login_pass")
        if st.button("ログイン", type="primary"):
            users = load_users()
            if login_user in users and users[login_user]["password"] == hash_password(login_pass):
                st.session_state.logged_in = True
                st.session_state.username = login_user
                data = users[login_user].get("data", {})
                defaults = {
                    "ai_name": None, "ai_gender": "おんなのこ", "ai_type": "中立",
                    "level": 1, "exp": 0, "learned_styles": [], "learned_preferences": [],
                    "messages": [], "points": 0, "is_premium": False, "premium_until": None,
                    "premium_started": None, "last_free_grant": None,
                    "paid_sessions": [], "ad_count": 0, "generated_history": [],
                    "user_icon": "👤", "ai_icon": "👤", "free_gen_left": 0,
                    "stripe_subscription_id": None
                }
                for k, v in defaults.items():
                    st.session_state[k] = data.get(k, v)
                st.session_state.current_mode = "chat"
                st.session_state.auth_page = "app"
                st.session_state.waiting_for_ai = False
                st.rerun()
            else:
                st.error("ユーザー名またはパスワードが違います")
        st.stop()

    if st.session_state.auth_page == "register":
        if st.button("← ホームへ"):
            st.session_state.auth_page = "home"
            st.rerun()
        st.title("新規登録")
        reg_user = st.text_input("新しいユーザー名", key="reg_user")
        reg_pass = st.text_input("パスワード", type="password", key="reg_pass")
        reg_pass2 = st.text_input("パスワード（確認）", type="password", key="reg_pass2")
        if st.button("登録してスタート", type="primary"):
            if not reg_user or not reg_pass:
                st.warning("入力してください")
            elif reg_pass != reg_pass2:
                st.error("パスワードが一致しません")
            else:
                users = load_users()
                if reg_user in users:
                    st.error("そのユーザー名は使われています")
                else:
                    users[reg_user] = {"password": hash_password(reg_pass), "data": {}}
                    save_users(users)
                    init_new_user_state(reg_user)
                    st.rerun()
        st.stop()

if st.session_state.get("logged_in"):
    grant_free_gens_if_needed()

if st.session_state.ai_name is None:
    show_header_image()
    input_name = st.text_input("AIの名前")
    gender = st.radio("性別", ["おんなのこ", "おとこのこ"], horizontal=True)
    if st.button("この設定で開始する！", type="primary") and input_name.strip():
        st.session_state.ai_name = input_name.strip()
        st.session_state.ai_gender = gender
        st.session_state.messages = [{"role": "assistant", "content": f"はじめまして！わたしは「{input_name.strip()}」だよ。好きなキャラや絵柄を教えて育てていこうね。"}]
        save_current_user_data()
        st.rerun()
    st.stop()

need = needed_exp(st.session_state.level)
premium = is_premium_active()
with st.sidebar:
    st.markdown(f"### {st.session_state.username}")
    st.write(f"**プラン:** {'月額会員' if premium else '無料'}")
    st.write(f"**ポイント:** {st.session_state.points} pt")
    if premium:
        st.write(f"**無料生成残:** {st.session_state.get('free_gen_left', 0)} / 50")
    st.write(f"**レベル:** Lv.{st.session_state.level}")
    st.write(f"**タイプ:** {st.session_state.ai_type}")
    st.progress(min(st.session_state.exp / need, 1.0))
    st.caption(f"次のレベルまで 会話 {max(need - st.session_state.exp, 0)} 回")
    st.markdown("---")
    if st.button("💬 トークルーム", use_container_width=True):
        st.session_state.current_mode = "chat"; st.rerun()
    if st.button("🖼️ 学習モード", use_container_width=True):
        st.session_state.current_mode = "learn"; st.rerun()
    if st.button("🎨 画像生成モード", use_container_width=True):
        st.session_state.current_mode = "generate"; st.rerun()
    if st.button("📂 生成履歴", use_container_width=True):
        st.session_state.current_mode = "history"; st.rerun()
    if st.button("💎 月額プラン", use_container_width=True):
        st.session_state.current_mode = "plan"; st.rerun()
    if st.button("🪙 ポイント購入", use_container_width=True):
        st.session_state.current_mode = "shop"; st.rerun()
    if st.button("ログアウト"):
        save_current_user_data()
        st.session_state.logged_in = False
        st.session_state.auth_page = "home"
        st.session_state.waiting_for_ai = False
        st.rerun()

mode = st.session_state.current_mode
if mode != "generate":
    show_header_image()

if mode == "chat":
    st.subheader(f"💬 {st.session_state.ai_name}")
    st.caption("経験値は会話だけです。画像生成では増えません。")
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            with st.chat_message("user", avatar=st.session_state.user_icon):
                st.markdown(f"**{st.session_state.username}**")
                st.write(msg["content"])
        else:
            with st.chat_message("assistant", avatar=st.session_state.ai_icon):
                st.markdown(f"**{st.session_state.ai_name}｜Lv.{st.session_state.level}**")
                st.write(msg["content"])
                if "image" in msg:
                    st.image(msg["image"], use_container_width=True)

    user_message = st.chat_input(
        "考え中です..." if st.session_state.waiting_for_ai else "メッセージを送る...",
        disabled=st.session_state.waiting_for_ai
    )

    if user_message and not st.session_state.waiting_for_ai:
        st.session_state.messages.append({"role": "user", "content": user_message})
        st.session_state.waiting_for_ai = True
        save_current_user_data()
        st.rerun()

    if st.session_state.waiting_for_ai and st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
        gender_note = "女の子らしい口調で。" if st.session_state.ai_gender == "おんなのこ" else "男の子らしい口調で。"
        base = CHARACTER_PROMPTS.get(st.session_state.ai_type, CHARACTER_PROMPTS["中立"])
        prefs = " / ".join(st.session_state.learned_preferences[-3:]) if st.session_state.learned_preferences else "まだ少ない"
        system_prompt = (
            f"あなたは「{st.session_state.ai_name}」。{base}{gender_note}"
            "短く自然に返す。同じ質問を繰り返さない。"
            f"覚えている好み: {prefs}"
        )
        api_messages = [{"role": "system", "content": system_prompt}] + [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.messages[-6:]
        ]
        try:
            with st.spinner("考え中..."):
                completion = client.chat.completions.create(
                    model="grok-4-fast",
                    messages=api_messages,
                    max_tokens=90
                )
            reply = completion.choices[0].message.content
        except Exception as e:
            reply = f"（エラー: {e}）"

        st.session_state.messages.append({"role": "assistant", "content": reply})
        st.session_state.exp += 1
        if not is_premium_active():
            st.session_state.ad_count += 1

        need_now = needed_exp(st.session_state.level)
        if st.session_state.exp >= need_now:
            st.session_state.level += 1
            st.session_state.exp = 0
            if st.session_state.level == 4:
                st.session_state.points += 50
            elif st.session_state.level > 4:
                st.session_state.points += 5
            unlock = ""
            if st.session_state.level == 3:
                unlock = "学習モードが解放されました。"
            elif st.session_state.level == 4:
                unlock = "画像生成モードが解放されました。50ptプレゼント！"
            notice = f"🎉 レベルアップ！ Lv.{st.session_state.level}"
            if unlock:
                notice += f"\n{unlock}"
            st.session_state.messages.append({"role": "assistant", "content": notice})

        if not is_premium_active() and st.session_state.ad_count >= ad_interval(st.session_state.level):
            st.session_state.ad_count = 0
            st.warning("📢 動画広告の時間です")

        st.session_state.waiting_for_ai = False
        save_current_user_data()
        st.rerun()

elif mode == "learn":
    st.subheader("🖼️ 学習モード")
    if st.session_state.level < 3:
        st.warning("画像学習はレベル3で解放されます。")
    else:
        uploaded_file = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"], key="learn_upload")
        if uploaded_file:
            st.image(uploaded_file, width=280)
            if st.button("この画像を学習させる", type="primary"):
                desc = analyze_image_style(uploaded_file)
                if desc not in st.session_state.learned_styles:
                    st.session_state.learned_styles.append(desc)
                save_current_user_data()
                st.success(desc)
    st.markdown("### 画像から覚えた絵柄")
    if st.session_state.learned_styles:
        for i, s in enumerate(st.session_state.learned_styles, 1):
            st.write(f"{i}. {s}")
        if st.button("画像の学習をリセット"):
            st.session_state.learned_styles = []; save_current_user_data(); st.rerun()
    else:
        st.write("まだありません")
    st.markdown("### 会話から覚えた好み")
    if st.session_state.learned_preferences:
        for i, p in enumerate(st.session_state.learned_preferences, 1):
            st.write(f"{i}. {p}")
        if st.button("会話の学習をリセット"):
            st.session_state.learned_preferences = []; save_current_user_data(); st.rerun()
    else:
        st.write("まだありません")

elif mode == "generate":
    st.subheader("🎨 画像生成モード")
    if st.session_state.level < 4:
        st.warning("レベル4で解放されます。")
    else:
        st.markdown("### サイズ")
        st.caption("よく使うサイズ")
        r1 = st.columns(3)
        for i, name in enumerate(["縦長", "正方形", "横長"]):
            with r1[i]:
                if st.button(name, use_container_width=True):
                    st.session_state.gen_w, st.session_state.gen_h = SIZE_PRESETS[name]
                    st.rerun()
        st.caption("大きいサイズ（2K / +5pt）")
        r2 = st.columns(3)
        for i, name in enumerate(["大きい縦長", "大きい正方形", "大きい横長"]):
            with r2[i]:
                if st.button(name, use_container_width=True):
                    st.session_state.gen_w, st.session_state.gen_h = SIZE_PRESETS[name]
                    st.rerun()
        c1, c2 = st.columns(2)
        with c1:
            st.number_input("幅", min_value=512, max_value=2048, step=64, key="gen_w")
        with c2:
            st.number_input("高さ", min_value=512, max_value=2048, step=64, key="gen_h")
        gen_w = int(st.session_state.gen_w)
        gen_h = int(st.session_state.gen_h)
        st.write(f"今のサイズ: {gen_w} × {gen_h}")
        aspect_ratio = ratio_from_size(gen_w, gen_h)
        st.markdown("### 画質")
        quality_choice = st.radio("画質", ["低画質（10pt / 1K）", "高画質（20pt / 2K）"])
        quality = "low" if "低画質" in quality_choice else "medium"
        st.markdown("### 参照")
        col_a, col_b = st.columns(2)
        with col_a:
            style_ref = st.file_uploader("絵柄参照", type=["png", "jpg", "jpeg"], key="style_ref")
            style_strength = st.slider("絵柄の強度", 1, 10, 8, key="style_str")
            if style_ref:
                st.image(style_ref, width=180)
        with col_b:
            char_ref = st.file_uploader("キャラ参照", type=["png", "jpg", "jpeg"], key="char_ref")
            char_strength = st.slider("キャラの強度", 1, 10, 8, key="char_str")
            if char_ref:
                st.image(char_ref, width=180)
        prompt_input = st.text_area("何を描く？", height=100)
        ref_count = sum(1 for x in [style_ref, char_ref] if x)
        can_free = (
            is_premium_active()
            and st.session_state.get("free_gen_left", 0) > 0
            and quality == "low"
            and max(gen_w, gen_h) < 1536
        )
        cost, resolution, size_add, ref_add = calc_generation_cost(quality, gen_w, gen_h, ref_count, use_free=can_free)
        if can_free:
            st.info(f"月額特典：低画質1Kの無料生成を使います（残り {st.session_state.free_gen_left} / 50）")
        if max(gen_w, gen_h) >= 1536:
            st.caption("1536以上は2Kになるため +5pt です")
        st.write(f"サイズ加算: {size_add}pt ／ 参照加算: {ref_add}pt")
        st.write(f"**消費ポイント: {cost} pt**（所持: {st.session_state.points} pt）")
        if st.button("🎨 イラストを生成する", type="primary", use_container_width=True):
            if not prompt_input.strip():
                st.warning("何を描くかを入力してください")
            elif st.session_state.points < cost:
                st.error("ポイントが足りません")
            else:
                st.session_state.points -= cost
                try:
                    with st.spinner("生成中..."):
                        refs = []
                        extra = [
                            "The user text is a DRAWING INSTRUCTION, not text to write on the image.",
                            "Do not render letters, captions, watermarks, or names onto the image."
                        ]
                        if style_ref:
                            refs.append(file_to_data_uri(style_ref))
                            extra.append(f"STYLE REFERENCE strength {style_strength}/10: use ONLY art style.")
                        if char_ref:
                            refs.append(file_to_data_uri(char_ref))
                            extra.append(f"CHARACTER REFERENCE strength {char_strength}/10: keep the same character, change pose by the prompt.")
                        if st.session_state.learned_styles:
                            extra.append("Learned image styles: " + " / ".join(st.session_state.learned_styles[-3:]))
                        if st.session_state.learned_preferences:
                            extra.append("Learned chat preferences: " + " / ".join(st.session_state.learned_preferences[-3:]))
                        full_prompt = f"Draw this: {prompt_input}\n" + "\n".join(extra)
                        if refs:
                            image_url = generate_with_references(full_prompt, aspect_ratio, resolution, quality, refs)
                        else:
                            image_url = generate_text_image(full_prompt, aspect_ratio, resolution, quality)
                    if can_free:
                        st.session_state.free_gen_left = max(st.session_state.free_gen_left - 1, 0)
                    st.session_state.last_generated_image = {"url": image_url, "prompt": prompt_input, "cost": cost}
                    st.session_state.generated_history.insert(0, {
                        "prompt": prompt_input, "url": image_url, "cost": cost,
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M")
                    })
                    save_current_user_data()
                    st.rerun()
                except Exception as e:
                    st.session_state.points += cost
                    st.error(f"失敗しました。ポイントは戻しました。\n{e}")
        if st.session_state.last_generated_image:
            st.markdown("---")
            st.subheader("最新の生成結果")
            st.caption(st.session_state.last_generated_image["prompt"])
            st.image(st.session_state.last_generated_image["url"], use_container_width=True)

elif mode == "history":
    st.subheader("📂 生成履歴")
    if not st.session_state.generated_history:
        st.write("まだありません")
    else:
        for item in st.session_state.generated_history:
            with st.expander(f"{item['time']} - {item['prompt'][:40]}"):
                st.image(item["url"], use_container_width=True)

elif mode == "plan":
    st.subheader("💎 月額プラン")
    st.write("**月額 980円**")
    st.write("- 登録時に 1200ポイント付与")
    st.write("- 毎月 画像生成 50回無料")
    st.write("- 広告除去")
    if is_premium_active():
        st.success(f"月額会員です。期限: {str(st.session_state.premium_until)[:10]}")
        st.write(f"無料生成の残り: {st.session_state.get('free_gen_left', 0)} / 50")
        if st.button("月額を解約する"):
            cancel_premium()
            st.warning("解約しました。これ以降の無料回数の更新はありません。")
            st.rerun()
    else:
        if stripe is None or not STRIPE_SECRET_KEY or not STRIPE_PRICE_ID:
            st.error("決済設定を確認してください。")
        elif st.button("980円で月額登録する", type="primary"):
            try:
                session = stripe.checkout.Session.create(
                    mode="subscription",
                    line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
                    success_url=f"{SITE_URL}/?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
                    cancel_url=f"{SITE_URL}/?checkout=cancel",
                    client_reference_id=st.session_state.username,
                    metadata={"kind": "premium", "username": st.session_state.username},
                )
                st.markdown(f"[決済ページへ進む]({session.url})")
            except Exception as e:
                st.error(f"決済ページを作れませんでした: {e}")

elif mode == "shop":
    st.subheader("🪙 ポイント購入")
    st.write("1ポイント = 1円")
    pack_key = st.radio("購入するパック", list(POINT_PACKS.keys()), format_func=lambda k: POINT_PACKS[k]["label"])
    pack = POINT_PACKS[pack_key]
    if stripe is None or not STRIPE_SECRET_KEY:
        st.error("決済設定を確認してください。")
    elif st.button(f"{pack['yen']}円で {pack['points']}pt 買う", type="primary"):
        try:
            session = stripe.checkout.Session.create(
                mode="payment",
                line_items=[{
                    "price_data": {
                        "currency": "jpy",
                        "product_data": {"name": f"{pack['points']}ポイント"},
                        "unit_amount": pack["yen"],
                    },
                    "quantity": 1,
                }],
                success_url=f"{SITE_URL}/?checkout=points&session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{SITE_URL}/?checkout=cancel",
                client_reference_id=st.session_state.username,
                metadata={"kind": "points", "username": st.session_state.username, "points": str(pack["points"])},
            )
            st.markdown(f"[決済ページへ進む]({session.url})")
        except Exception as e:
            st.error(f"決済ページを作れませんでした: {e}")
