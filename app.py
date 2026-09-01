import streamlit as st
import os
import json
import uuid
import base64
import hashlib
import math
import io
import zipfile
import random
import re
import socket
import smtplib
import subprocess
import time
import requests
import shutil
import tempfile
from email.mime.text import MIMEText
from io import BytesIO
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

try:
    import fcntl
except ImportError:
    fcntl = None

try:
    import stripe
except ImportError:
    stripe = None

st.set_page_config(page_title="panel AI.", page_icon="🎨", layout="wide", initial_sidebar_state="collapsed")

GSC = os.environ.get("GOOGLE_SITE_VERIFICATION", "")
if GSC:
    st.markdown(f'<meta name="google-site-verification" content="{GSC}">', unsafe_allow_html=True)

NAI_KEY = os.environ.get("NOVELAI_API_KEY", "")
XAI_KEY = os.environ.get("XAI_API_KEY", "")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
SITE_URL = os.environ.get("SITE_URL", "https://aistation.onrender.com")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
MAIL_FROM = os.environ.get("MAIL_FROM", os.environ.get("SMTP_FROM", ""))
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
OWNER_ACCOUNTS = [x.strip().lower() for x in os.environ.get("OWNER_ACCOUNTS", "").split(",") if x.strip()]
CONTACT_TO = "panel.com@gmail.com"
if stripe is not None and STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

NAI_URLS = ["https://image.novelai.net/ai/generate-image", "https://api.novelai.net/ai/generate-image"]
DATA_DIR = os.environ.get("DATA_DIR", os.path.abspath("data"))
os.makedirs(DATA_DIR, exist_ok=True)
DATA_FILE = os.path.join(DATA_DIR, "studio_data.json")
USERS_FILE = os.path.join(DATA_DIR, "users_data.json")
HOME_IMG = "IMG_1106.jpeg"
HEADER_IMG = "IMG_1107.jpeg"
VID_DIR = os.path.join(DATA_DIR, "video_tmp")
PHONE_W, PHONE_H = 1080, 1920
MONTHLY_PRICE, MONTHLY_POINTS, REF_SITE, SIGNUP_POINTS = 980, 1200, 10, 20
VIDEO_PT_PER_SEC = 30
JOIN_COST = 20
MAX_UPLOAD_SEC = 10
WAIT_SEC = 20
POINT_PACKS = [{"points": 300, "yen": 300}, {"points": 900, "yen": 900}, {"points": 1500, "yen": 1500}, {"points": 3000, "yen": 3000}]
ANIMALS = ["🐱", "🐶", "🐰", "🐻", "🦊", "🐼", "🐸", "🦉", "🐧", "🐯"]
LAYOUTS = {"縦4": {"cols": 1, "count": 4}, "縦3": {"cols": 1, "count": 3}, "縦2": {"cols": 1, "count": 2}, "横4": {"cols": 4, "count": 4}, "横3": {"cols": 3, "count": 3}, "横2": {"cols": 2, "count": 2}, "2×2": {"cols": 2, "count": 4}}
SIZES = {
    "横長": {"wh": (PHONE_W, PHONE_H // 4), "gen": (1216, 832), "cost": 0, "paid": False},
    "縦長": {"wh": (PHONE_H // 4, PHONE_W), "gen": (832, 1216), "cost": 0, "paid": False},
    "正方形": {"wh": (512, 512), "gen": (1024, 1024), "cost": 0, "paid": False},
    "大・横 1536×1024": {"wh": (1536, 1024), "gen": (1536, 1024), "cost": 52, "paid": True},
    "大・縦 1024×1536": {"wh": (1024, 1536), "gen": (1024, 1536), "cost": 52, "paid": True},
    "大・正 1472×1472": {"wh": (1472, 1472), "gen": (1472, 1472), "cost": 72, "paid": True},
    "壁紙・横 1920×1088": {"wh": (1920, 1088), "gen": (1920, 1088), "cost": 68, "paid": True},
    "壁紙・縦 1088×1920": {"wh": (1088, 1920), "gen": (1088, 1920), "cost": 68, "paid": True},
}
SIMPLE_SIZES = {
    "横長 1216×832": {"gen": (1216, 832), "cost": 20, "paid": False},
    "縦長 832×1216": {"gen": (832, 1216), "cost": 20, "paid": False},
    "正方形 1024×1024": {"gen": (1024, 1024), "cost": 20, "paid": False},
    "大・横 1536×1024": {"gen": (1536, 1024), "cost": 70, "paid": True},
    "大・縦 1024×1536": {"gen": (1024, 1536), "cost": 70, "paid": True},
    "大・正 1472×1472": {"gen": (1472, 1472), "cost": 96, "paid": True},
    "壁紙・横 1920×1088": {"gen": (1920, 1088), "cost": 94, "paid": True},
    "壁紙・縦 1088×1920": {"gen": (1088, 1920), "cost": 94, "paid": True},
}
BUBBLE_TYPES = ["ふきだし", "叫び", "考え", "文字だけ"]
TAILS = ["下", "下左", "下右", "左", "右"]
TEXT_DIR = ["横書き", "縦書き"]
FONT_SPECS = {
    "ゴシック": {"file": "font_gothic.otf", "urls": ["https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf", "https://cdn.jsdelivr.net/gh/notofonts/noto-cjk@main/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf"]},
    "丸文字": {"file": "font_maru.ttf", "urls": ["https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/kosugimaru/KosugiMaru-Regular.ttf"]},
    "かわいい": {"file": "font_kawaii.ttf", "urls": ["https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/hachimarupop/HachiMaruPop-Regular.ttf"]},
    "手書き風": {"file": "font_te.ttf", "urls": ["https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/yuseimagic/YuseiMagic-Regular.ttf"]},
}
os.makedirs(VID_DIR, exist_ok=True)

def video_cost(sec):
    return max(1, int(sec)) * VIDEO_PT_PER_SEC

def is_owner():
    u = str(st.session_state.get("username") or "").strip().lower()
    e = norm_mail(st.session_state.get("email"))
    return bool(OWNER_ACCOUNTS) and (u in OWNER_ACCOUNTS or e in OWNER_ACCOUNTS)

def scroll_top():
    st.markdown("""
    <script>
    const d = window.parent ? window.parent.document : document;
    const main = d.querySelector('section.main') || d.scrollingElement || d.documentElement;
    if (main) main.scrollTo(0, 0);
    window.scrollTo(0, 0);
    if (d.body) d.body.scrollTop = 0;
    </script>
    """, unsafe_allow_html=True)

def go(page):
    st.session_state.page = page
    st.session_state.menu_open = False
    st.session_state.need_top = True
    st.query_params["p"] = page

def start_wait():
    st.session_state.wait_until = time.time() + WAIT_SEC

def lock_other_buttons():
    st.markdown("""
    <style>
    section.main .block-container { pointer-events: none; }
    .wait-ok, .wait-ok * { pointer-events: auto !important; }
    </style>
    """, unsafe_allow_html=True)

def show_countdown_wait(label, key):
    lock_other_buttons()
    left = int(math.ceil(st.session_state.get("wait_until", 0) - time.time()))
    st.markdown('<div class="wait-ok">', unsafe_allow_html=True)
    if st.session_state.get("act_busy"):
        st.markdown(f'<div style="margin:8px 0;padding:12px;border-radius:14px;background:#fff0f6;color:#ff4d88;font-weight:800;">{label}… 処理中です。連打しないでください</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        return None
    if left > 0:
        st.markdown(f'<div style="margin:8px 0;padding:12px;border-radius:14px;background:#fff0f6;color:#ff4d88;font-weight:800;">{label}… {left}</div>', unsafe_allow_html=True)
        if st.button("キャンセル", key=f"can_{key}"):
            st.markdown("</div>", unsafe_allow_html=True)
            return "cancel"
        time.sleep(1)
        st.rerun()
    st.write("0になりました。確認を押してください")
    if st.button("確認する", key=f"ok_{key}"):
        st.session_state.act_busy = True
        st.markdown("</div>", unsafe_allow_html=True)
        return "confirm"
    if st.button("キャンセル", key=f"can2_{key}"):
        st.markdown("</div>", unsafe_allow_html=True)
        return "cancel"
    st.markdown("</div>", unsafe_allow_html=True)
    return None

def file_b64(path):
    if not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def norm_mail(m):
    return (m or "").strip().lower()

def valid_mail_format(m):
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", norm_mail(m)) is not None

def mail_domain_ok(m):
    try:
        socket.getaddrinfo(norm_mail(m).split("@", 1)[1], 80)
        return True
    except Exception:
        return False

def send_mail(to_addr, subject, body):
    if RESEND_API_KEY and MAIL_FROM:
        res = requests.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"}, json={"from": MAIL_FROM, "to": [to_addr], "subject": subject, "text": body}, timeout=20)
        return res.status_code in (200, 201), res.text[:200]
    if SMTP_HOST and SMTP_USER and SMTP_PASS and MAIL_FROM:
        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = MAIL_FROM
            msg["To"] = to_addr
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
                s.starttls()
                s.login(SMTP_USER, SMTP_PASS)
                s.sendmail(MAIL_FROM, [to_addr], msg.as_string())
            return True, ""
        except Exception as e:
            return False, str(e)
    return False, "メール送信設定がありません"

def send_code_mail(to_addr, code):
    return send_mail(to_addr, "panel AI. 登録確認", f"確認コード: {code}\nこのコードをサイトに入力してください。")

def _read_json_file(path):
    if not path or not os.path.exists(path) or os.path.getsize(path) <= 2:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception:
        return None

def load_json(path, default):
    data = _read_json_file(path)
    if data is not None:
        return data
    data = _read_json_file(path + ".bak")
    if data is not None:
        try:
            save_json(path, data)
        except Exception:
            pass
        return data
    old = os.path.basename(path)
    if os.path.abspath(old) != os.path.abspath(path):
        data = _read_json_file(old)
        if data is not None:
            try:
                save_json(path, data)
            except Exception:
                pass
            return data
    return default

def save_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    folder = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=folder)
    locked = None
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            if fcntl is not None:
                try:
                    locked = open(path + ".lock", "a+", encoding="utf-8")
                    fcntl.flock(locked.fileno(), fcntl.LOCK_EX)
                except Exception:
                    locked = None
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(path) and os.path.getsize(path) > 2:
            try:
                shutil.copy2(path, path + ".bak")
            except Exception:
                pass
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
        if locked is not None:
            try:
                fcntl.flock(locked.fileno(), fcntl.LOCK_UN)
                locked.close()
            except Exception:
                pass

def email_taken(users, mail):
    mail = norm_mail(mail)
    return any(isinstance(v, dict) and norm_mail(v.get("email")) == mail for v in users.values())

def find_user(users, key):
    if key in users:
        return key
    k = norm_mail(key)
    for name, v in users.items():
        if isinstance(v, dict) and (norm_mail(v.get("email")) == k or name == key):
            return name
    return None

def download_one(path, urls):
    if os.path.exists(path) and os.path.getsize(path) > 8000:
        return True
    for url in urls:
        try:
            r = requests.get(url, timeout=45)
            if r.status_code == 200 and len(r.content) > 8000:
                with open(path, "wb") as f:
                    f.write(r.content)
                try:
                    ImageFont.truetype(path, 24)
                    return True
                except Exception:
                    os.remove(path)
        except Exception:
            continue
    return False

@st.cache_resource
def prepare_fonts():
    return {name: download_one(spec["file"], spec["urls"]) for name, spec in FONT_SPECS.items()}

def load_font(size=28, kind="ゴシック"):
    size = max(12, int(size))
    spec = FONT_SPECS.get(kind) or FONT_SPECS["ゴシック"]
    for path in [spec["file"], FONT_SPECS["ゴシック"]["file"]]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()

def uploaded_to_uri(uploaded):
    return f"data:{uploaded.type or 'image/png'};base64,{base64.b64encode(uploaded.getvalue()).decode()}"

def uri_to_image(uri):
    if not uri:
        return None
    if uri.startswith("data:"):
        return Image.open(BytesIO(base64.b64decode(uri.split(",", 1)[1]))).convert("RGB")
    res = requests.get(uri, timeout=90)
    res.raise_for_status()
    return Image.open(BytesIO(res.content)).convert("RGB")

def shrink_for_video(image_uri):
    img = uri_to_image(image_uri)
    img.thumbnail((768, 768))
    buf = BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

def save_upload_mp4(uploaded):
    path = os.path.join(VID_DIR, f"up_{uuid.uuid4().hex}.mp4")
    with open(path, "wb") as f:
        f.write(uploaded.getvalue())
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        sec = float((r.stdout or "0").strip() or 0)
    except Exception:
        sec = 0
    if sec <= 0:
        os.remove(path)
        raise Exception("動画の長さが読めません。mp4にしてください")
    if sec > MAX_UPLOAD_SEC + 0.3:
        os.remove(path)
        raise Exception(f"10秒以下のmp4だけ使えます。今は {sec:.1f}秒です")
    return path

def pad_ref(uri):
    img = uri_to_image(uri).convert("RGB")
    tw, th = 1024, 1536
    canvas = Image.new("RGB", (tw, th), (0, 0, 0))
    img.thumbnail((tw, th))
    canvas.paste(img, ((tw - img.width) // 2, (th - img.height) // 2))
    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def is_premium():
    until = st.session_state.get("premium_until") or ""
    try:
        return bool(until) and datetime.fromisoformat(until) > datetime.now()
    except Exception:
        return False

def member_label():
    return "VIP" if is_premium() else "ブロンズ"

def save_user_state():
    users = load_json(USERS_FILE, {})
    name = st.session_state.get("username")
    if not name:
        return
    prev = users.get(name) if isinstance(users.get(name), dict) else {}
    users[name] = {
        "password": prev.get("password") or st.session_state.get("password_hash", ""),
        "email": st.session_state.get("email") or prev.get("email", ""),
        "icon": st.session_state.get("icon", prev.get("icon", "")),
        "characters": st.session_state.get("characters", prev.get("characters", [])),
        "points": int(st.session_state.get("points", prev.get("points", 0))),
        "premium_until": st.session_state.get("premium_until") or prev.get("premium_until", ""),
        "rank": "vip" if is_premium() else "ブロンズ",
        "history": st.session_state.get("simple_history", prev.get("history", []))[-30:],
        "library": st.session_state.get("library", prev.get("library", []))[-40:],
    }
    if not users[name]["password"] and prev.get("password"):
        users[name]["password"] = prev["password"]
    if prev.get("password") and not users[name]["password"]:
        users[name]["password"] = prev["password"]
    save_json(USERS_FILE, users)
    save_json(DATA_FILE, {"characters": st.session_state.characters})

def add_library(uri, label=""):
    if not uri:
        return
    st.session_state.library.append({"id": str(uuid.uuid4())[:8], "url": uri, "label": label or "保存画像", "time": datetime.now().strftime("%m/%d %H:%M")})
    save_user_state()

def take_points(cost):
    if is_owner() or int(cost) <= 0:
        return
    if st.session_state.points < cost:
        raise Exception(f"ポイントが足りません。必要 {cost}")
    st.session_state.points -= int(cost)
    save_user_state()

def finish_action():
    st.session_state.act_busy = False

def nai_wh(w, h):
    return max(64, min(1920, int(round(w / 64) * 64))), max(64, min(1920, int(round(h / 64) * 64)))

def nai_request(prompt, width, height, model, steps=23, scale=5.0, negative="", char_texts=None, char_refs=None, style_refs=None):
    if not NAI_KEY:
        raise Exception("NOVELAI_API_KEY がありません")
    gw, gh = nai_wh(width, height)
    char_texts = [x.strip() for x in (char_texts or []) if x and x.strip()][:3]
    char_refs = [x for x in (char_refs or []) if x.get("uri")][:3]
    style_refs = [x for x in (style_refs or []) if x.get("uri")][:3]
    char_captions, character_prompts = [], []
    xs, ys = [0.3, 0.7, 0.5], [0.5, 0.5, 0.72]
    for i, txt in enumerate(char_texts):
        char_captions.append({"char_caption": txt, "centers": [{"x": xs[i], "y": ys[i]}]})
        character_prompts.append({"prompt": txt, "uc": "", "center": {"x": xs[i], "y": ys[i]}, "enabled": True})
    parameters = {
        "params_version": 3, "width": gw, "height": gh, "scale": float(scale),
        "sampler": "k_euler_ancestral", "steps": int(steps), "n_samples": 1,
        "qualityToggle": False, "ucPreset": 0, "negative_prompt": negative or "",
        "noise_schedule": "karras", "use_coords": True, "characterPrompts": character_prompts,
        "v4_prompt": {"caption": {"base_caption": prompt or "", "char_captions": char_captions}, "use_coords": True, "use_order": True},
        "v4_negative_prompt": {"caption": {"base_caption": negative or "", "char_captions": []}, "legacy_uc": False},
    }
    if model.startswith("nai-diffusion-4-5"):
        refs, kinds = [], []
        if char_refs and style_refs:
            refs.append(pad_ref(char_refs[0]["uri"])); kinds.append("character&style")
        elif char_refs:
            refs.append(pad_ref(char_refs[0]["uri"])); kinds.append("character")
        elif style_refs:
            refs.append(pad_ref(style_refs[0]["uri"])); kinds.append("style")
        if refs:
            parameters["director_reference_images"] = refs
            parameters["director_reference_descriptions"] = [{"caption": {"base_caption": kinds[0], "char_captions": []}, "legacy_uc": False}]
            parameters["director_reference_information_extracted"] = [1]
            parameters["director_reference_strength_values"] = [1]
            parameters["director_reference_secondary_strength_values"] = [0.75]
    models = ["nai-diffusion-4-5-full", "nai-diffusion-4-5-curated"] if model == "nai-diffusion-4-5-full" else [model]
    last_err = None
    for mdl in models:
        payload = {"input": prompt or "", "model": mdl, "action": "generate", "parameters": parameters}
        for url in NAI_URLS:
            res = requests.post(url, headers={"Authorization": f"Bearer {NAI_KEY}", "Content-Type": "application/json"}, json=payload, timeout=180)
            if res.status_code == 200:
                with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
                    return "data:image/png;base64," + base64.b64encode(zf.read(zf.namelist()[0])).decode()
            last_err = f"{res.status_code}: {res.text[:400]}"
    raise Exception(last_err or "NovelAIの生成に失敗しました")

def grok_start_video(image_uri, prompt, duration=6):
    if not XAI_KEY:
        raise Exception("XAI_API_KEY がありません")
    image_uri = shrink_for_video(image_uri)
    headers = {"Authorization": f"Bearer {XAI_KEY}", "Content-Type": "application/json"}
    payload = {"model": "grok-imagine-video-1.5", "prompt": prompt or "subtle natural motion, keep the same character and style", "image": {"url": image_uri}, "duration": int(duration), "resolution": "720p"}
    res = requests.post("https://api.x.ai/v1/videos/generations", headers=headers, json=payload, timeout=30)
    if res.status_code not in (200, 201, 202):
        raise Exception(f"{res.status_code}: {res.text[:500]}")
    data = res.json()
    request_id = data.get("request_id") or data.get("id")
    if not request_id:
        raise Exception(f"request_idがありません: {str(data)[:400]}")
    return request_id

def grok_poll_video(request_id):
    headers = {"Authorization": f"Bearer {XAI_KEY}"}
    chk = requests.get(f"https://api.x.ai/v1/videos/{request_id}", headers=headers, timeout=20)
    if chk.status_code != 200:
        return "wait", chk.text[:200]
    d = chk.json()
    status = d.get("status")
    if status == "done":
        video_url = (d.get("video") or {}).get("url") or d.get("url")
        raw = requests.get(video_url, timeout=60)
        raw.raise_for_status()
        path = os.path.join(VID_DIR, f"{uuid.uuid4().hex}.mp4")
        with open(path, "wb") as f:
            f.write(raw.content)
        return "done", path
    if status in ("failed", "expired"):
        return "error", str(d)[:400]
    return "wait", status or "pending"

def probe_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return max(0.2, float((r.stdout or "0").strip() or 0))
    except Exception:
        return 3.0

def probe_wh(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        parts = (r.stdout or "").strip().split(",")
        return max(2, int(parts[0])), max(2, int(parts[1]))
    except Exception:
        return 640, 640

def even_size(n):
    n = max(2, int(round(n)))
    return n if n % 2 == 0 else n + 1

def layout_kind(layout_key, n):
    key = str(layout_key)
    if key.startswith("横"):
        return n, 1
    if key == "2×2":
        return 2, 2
    return 1, n

def panel_targets(paths, layout_key):
    n = len(paths)
    cols, rows = layout_kind(layout_key, n)
    sizes = [probe_wh(p) for p in paths]
    max_w = max(w for w, _h in sizes)
    max_h = max(h for _w, h in sizes)
    cap = 1080
    out = []
    if cols == 1:
        tw = even_size(min(cap, max_w))
        for w, h in sizes:
            out.append((tw, even_size(h * tw / max(w, 1))))
    elif rows == 1:
        th = even_size(min(cap, max_h))
        for w, h in sizes:
            out.append((even_size(w * th / max(h, 1)), th))
    else:
        tw = even_size(min(cap, max_w))
        for w, h in sizes:
            out.append((tw, even_size(h * tw / max(w, 1))))
    return cols, rows, out

def scale_filter(w, h):
    return f"fps=24,scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=white,setsar=1,format=yuv420p"

def stack_filter(cols, rows, n, labels, targets):
    joined = "".join(labels)
    if cols == 1:
        return joined + f"vstack=inputs={n}[out]"
    if rows == 1:
        return joined + f"hstack=inputs={n}[out]"
    w0, h0 = targets[0]
    w1, h1 = targets[1] if n > 1 else targets[0]
    w2, h2 = targets[2] if n > 2 else targets[0]
    layout = f"0_0|{w0}_0|0_{h0}|{w0}_{h0}"
    return joined + f"xstack=inputs={n}:layout={layout}[out]"

def concat_videos(paths, out_path):
    lst = os.path.join(VID_DIR, f"{uuid.uuid4().hex}.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for p in paths:
            f.write(f"file '{os.path.abspath(p)}'\n")
    r = subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out_path], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out_path):
        r = subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "libx264", "-pix_fmt", "yuv420p", out_path], capture_output=True, text=True)
        if r.returncode != 0:
            raise Exception(r.stderr[-400:] if r.stderr else "結合に失敗しました")
    return out_path

def compose_yonkoma_video(paths, layout_key="2×2", out_path="out.mp4", sequential=False):
    n = len(paths)
    if n < 2:
        raise Exception("2本以上必要です")
    cols, rows, targets = panel_targets(paths, layout_key)
    if not sequential:
        ins = []
        for p in paths:
            ins += ["-i", p]
        parts, labels = [], []
        for i in range(n):
            tw, th = targets[i]
            parts.append(f"[{i}:v]{scale_filter(tw, th)}[v{i}]")
            labels.append(f"[v{i}]")
        filt = ";".join(parts) + ";" + stack_filter(cols, rows, n, labels, targets)
        r = subprocess.run(["ffmpeg", "-y"] + ins + ["-filter_complex", filt, "-map", "[out]", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest", out_path], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(out_path):
            raise Exception((r.stderr or "結合失敗")[-500:])
        return out_path
    durs = [probe_duration(p) for p in paths]
    segs = []
    for k in range(n):
        ins = []
        for p in paths:
            ins += ["-i", p]
        parts, labels = [], []
        for i in range(n):
            tw, th = targets[i]
            sc = scale_filter(tw, th)
            if i == k:
                parts.append(f"[{i}:v]{sc},setpts=PTS-STARTPTS[v{i}]")
            else:
                parts.append(f"[{i}:v]trim=start=0:end=0.05,loop=-1:size=1,setpts=N/24/TB,{sc},trim=duration={durs[k]:.3f},setpts=PTS-STARTPTS[v{i}]")
            labels.append(f"[v{i}]")
        filt = ";".join(parts) + ";" + stack_filter(cols, rows, n, labels, targets)
        seg = os.path.join(VID_DIR, f"seq_{k}_{uuid.uuid4().hex}.mp4")
        r = subprocess.run(["ffmpeg", "-y"] + ins + ["-filter_complex", filt, "-map", "[out]", "-an", "-t", f"{durs[k]:.3f}", "-c:v", "libx264", "-pix_fmt", "yuv420p", seg], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(seg):
            raise Exception((r.stderr or "順番まとめ失敗")[-500:])
        segs.append(seg)
    return concat_videos(segs, out_path)

def wrap_text(text, font, max_width):
    lines, line = [], ""
    for ch in text:
        test = line + ch
        try:
            ok = font.getlength(test) <= max_width
        except Exception:
            ok = len(test) * 14 <= max_width
        if ok:
            line = test
        else:
            if line:
                lines.append(line)
            line = ch
    if line:
        lines.append(line)
    return lines or [""]

def draw_text(draw, xy, text, font, fill, bold=0):
    x, y = xy
    if bold <= 0:
        draw.text((x, y), text, font=font, fill=fill)
        return
    for dx in range(-bold, bold + 1):
        for dy in range(-bold, bold + 1):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=font, fill=fill)
    draw.text((x, y), text, font=font, fill=fill)

def paste_layer(img, layer, px, py):
    sx = max(0, -px)
    sy = max(0, -py)
    dx = max(0, px)
    dy = max(0, py)
    cw = min(layer.width - sx, img.width - dx)
    ch = min(layer.height - sy, img.height - dy)
    if cw > 0 and ch > 0:
        img.alpha_composite(layer.crop((sx, sy, sx + cw, sy + ch)), (dx, dy))
    return img

def draw_one_bubble(img, bub):
    text = (bub.get("text") or "").strip()
    if not text:
        return img
    img = img.convert("RGBA")
    size, bold, tail_size = int(bub.get("size", 28)), int(bub.get("bold", 0)), int(bub.get("tail_size", 28))
    font = load_font(size, bub.get("font", "ゴシック"))
    w, h = img.size
    kind, direction = bub.get("kind", "ふきだし"), bub.get("dir", "横書き")
    fill, color, tail = bub.get("fill", "#ffffff"), bub.get("color", "#111111"), bub.get("tail", "下")
    pad = 22 if kind == "叫び" else 16
    max_w = int(w * (0.72 if kind == "叫び" else 0.62))
    if direction == "縦書き":
        lines = list(text.replace("\n", ""))
        box_w = size + pad * 2 + bold * 2
        box_h = pad * 2 + int(size * 1.15) * len(lines) + bold * 2
    else:
        lines = wrap_text(text, font, max_w)
        try:
            text_w = max(font.getlength(x) for x in lines)
        except Exception:
            text_w = max(len(x) * size for x in lines)
        box_w = int(text_w + pad * 2 + bold * 2)
        box_h = int(pad * 2 + int(size * 1.3) * len(lines) + bold * 2)
    if kind == "叫び":
        box_w = int(box_w * 1.25)
        box_h = int(box_h * 1.28)
    extra = tail_size + 48
    layer = Image.new("RGBA", (box_w + extra * 2, box_h + extra * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x0, y0 = extra, extra
    if kind == "ふきだし":
        draw.rounded_rectangle([x0, y0, x0 + box_w, y0 + box_h], radius=22, fill=fill, outline="#222222", width=3)
        ts = tail_size
        if tail == "下":
            tpts = [(x0 + box_w * 0.38, y0 + box_h - 2), (x0 + box_w * 0.52, y0 + box_h - 2), (x0 + box_w * 0.34, y0 + box_h + ts)]
        elif tail == "下左":
            tpts = [(x0 + 18, y0 + box_h - 2), (x0 + 18 + ts * 0.7, y0 + box_h - 2), (x0 + 8, y0 + box_h + ts)]
        elif tail == "下右":
            tpts = [(x0 + box_w - 18 - ts * 0.7, y0 + box_h - 2), (x0 + box_w - 18, y0 + box_h - 2), (x0 + box_w - 8, y0 + box_h + ts)]
        elif tail == "左":
            tpts = [(x0 + 2, y0 + box_h * 0.45), (x0 + 2, y0 + box_h * 0.62), (x0 - ts, y0 + box_h * 0.58)]
        else:
            tpts = [(x0 + box_w - 2, y0 + box_h * 0.45), (x0 + box_w - 2, y0 + box_h * 0.62), (x0 + box_w + ts, y0 + box_h * 0.58)]
        draw.polygon(tpts, fill=fill)
        draw.line([tpts[0], tpts[2], tpts[1]], fill="#222222", width=3)
    elif kind == "叫び":
        pts = []
        for i in range(32):
            ang = math.pi * 2 * i / 32
            rx = box_w / 2 * (1.38 if i % 2 == 0 else 0.98)
            ry = box_h / 2 * (1.38 if i % 2 == 0 else 0.98)
            pts.append((x0 + box_w / 2 + math.cos(ang) * rx, y0 + box_h / 2 + math.sin(ang) * ry))
        draw.polygon(pts, fill=fill, outline="#222222")
    elif kind == "考え":
        draw.rounded_rectangle([x0, y0, x0 + box_w, y0 + box_h], radius=28, fill=fill, outline="#222222", width=3)
        draw.ellipse([x0 + 16, y0 + box_h + 6, x0 + 16 + tail_size * 0.5, y0 + box_h + 6 + tail_size * 0.5], fill=fill, outline="#222222")
    if direction == "縦書き":
        cy = y0 + pad
        for ch in lines:
            try:
                tw = font.getlength(ch)
            except Exception:
                tw = size
            draw_text(draw, (x0 + (box_w - tw) / 2, cy), ch, font, color, bold)
            cy += int(size * 1.15)
    else:
        ty = y0 + pad - 2
        for line in lines:
            try:
                lw = font.getlength(line)
            except Exception:
                lw = len(line) * size
            tx = x0 + (box_w - lw) / 2 if kind == "叫び" else x0 + pad
            draw_text(draw, (tx, ty), line, font, color, bold)
            ty += int(size * 1.3)
    angle = int(bub.get("angle", 0))
    if angle:
        layer = layer.rotate(-angle, expand=True, resample=Image.BICUBIC)
        px = int((w - box_w) * float(bub.get("x", 8)) / 100) - (layer.width - box_w) // 2
        py = int((h - box_h) * float(bub.get("y", 8)) / 100) - (layer.height - box_h) // 2
    else:
        px = int((w - box_w) * float(bub.get("x", 8)) / 100) - extra
        py = int((h - box_h) * float(bub.get("y", 8)) / 100) - extra
    return paste_layer(img, layer, px, py).convert("RGB")

def draw_all_bubbles(panel_img, bubbles):
    img = panel_img
    for bub in bubbles or []:
        img = draw_one_bubble(img, bub)
    return img

def combine_panels(images, cols=2):
    gap, n = 8, len(images)
    rows = (n + cols - 1) // cols
    col_w = [max((images[i].width for i in range(n) if i % cols == c), default=0) for c in range(cols)]
    row_h = [max((images[i].height for i in range(n) if i // cols == r), default=0) for r in range(rows)]
    canvas = Image.new("RGB", (sum(col_w) + gap * (cols + 1), sum(row_h) + gap * (rows + 1)), "#111111")
    for i, im in enumerate(images):
        r, c = divmod(i, cols)
        canvas.paste(im, (gap + sum(col_w[:c]) + gap * c, gap + sum(row_h[:r]) + gap * r))
    return canvas

def image_to_bytes(img):
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def char_label(ch):
    return ch.get("save_name") or ch.get("name") or "無名"

def normalize_refs(items):
    out = []
    for x in items or []:
        if isinstance(x, dict) and x.get("uri"):
            out.append({"uri": x["uri"], "strength": int(x.get("strength", 8))})
        elif isinstance(x, str):
            out.append({"uri": x, "strength": 8})
    return out

def show_header():
    if os.path.exists(HEADER_IMG):
        st.image(HEADER_IMG, use_container_width=True)

def panel_raw(i):
    raw = uri_to_image(st.session_state.panel_images[i])
    if not st.session_state.panel_upload[i]:
        raw = raw.resize(st.session_state.panel_sizes[i])
    return raw

def empty_bubble():
    return {"text": "", "x": 8, "y": 8, "angle": 0, "fill": "#ffffff", "color": "#111111", "size": 28, "bold": 0, "tail_size": 28, "kind": "ふきだし", "font": "ゴシック", "dir": "横書き", "tail": "下"}

def apply_login(name, data):
    st.session_state.logged_in = True
    st.session_state.username = name
    st.session_state.email = data.get("email", "")
    st.session_state.password_hash = data.get("password", "")
    st.session_state.icon = data.get("icon", random.choice(ANIMALS))
    st.session_state.characters = data.get("characters", [])
    st.session_state.points = int(data.get("points", 0))
    st.session_state.premium_until = data.get("premium_until", "")
    st.session_state.simple_history = data.get("history", [])
    st.session_state.library = data.get("library", [])
    save_user_state()

def render_top_menu():
    left, _ = st.columns([1, 3])
    with left:
        label = "閉じる" if st.session_state.menu_open else "メニュー"
        if st.button(label, key="panel_menu_toggle", use_container_width=True):
            st.session_state.menu_open = not st.session_state.menu_open
            st.rerun()
    if not st.session_state.menu_open:
        return
    st.markdown('<div style="background:#fff;border:3px solid #111;border-radius:20px;padding:12px;margin:8px 0 16px;">', unsafe_allow_html=True)
    st.markdown("**メニュー**")
    if st.session_state.logged_in:
        icon = st.session_state.get("icon", "🐱")
        if isinstance(icon, str) and icon.startswith("data:image"):
            st.image(icon, width=48)
        else:
            st.write(icon)
        st.write(st.session_state.get("username", ""))
        if st.button("アイコン変更", use_container_width=True):
            go("icon"); st.rerun()
        if st.button("ログアウト", use_container_width=True):
            st.session_state.logged_in = False; go("home"); st.rerun()
    else:
        if st.button("登録", use_container_width=True):
            go("register"); st.rerun()
        if st.button("ログイン", use_container_width=True):
            go("register"); st.rerun()
    st.write(f"ポイント {st.session_state.points}")
    st.write(f"会員 {member_label() if st.session_state.logged_in else '未登録'}")
    for label, page in [("画像生成モード", "simple"), ("セット", "chars"), ("4コマ", "make"), ("保存庫", "lib"), ("動画生成", "video"), ("4コマ動画", "v4"), ("ポイント購入", "shop"), ("説明書", "help"), ("月額登録", "plan"), ("お問い合わせ", "contact")]:
        if st.button(label, use_container_width=True, key=f"m_{page}"):
            go(page); st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

prepare_fonts()
usable_fonts = [k for k, ok in prepare_fonts().items() if ok] or ["ゴシック"]
defaults = {
    "logged_in": False, "page": "home", "layout": "縦4", "scenes": ["", "", "", ""],
    "scene_chars": ["セットなし"] * 4, "panel_images": [None] * 4, "panel_upload": [False] * 4,
    "panel_sizes": [SIZES["横長"]["wh"]] * 4, "panel_shape": ["横長"] * 4,
    "panel_bubbles": [[], [], [], []], "drafts": [empty_bubble() for _ in range(4)],
    "error": "", "busy_index": None, "combined": None, "points": 0, "premium_until": "",
    "simple_image": None, "simple_busy": False, "simple_history": [], "show_history": False,
    "hist_pick": None, "sq": "", "sb": "", "so": "", "sn": "", "schars": [""],
    "icon": random.choice(ANIMALS), "email": "", "pending": None, "library": [],
    "video_src": None, "video_out": None, "v4_clips": [None] * 4, "v4_prompts": ["", "", "", ""],
    "v4_durs": [5, 5, 5, 5], "v4_count": 4, "v4_layout": "2×2", "v4_play": "同時に動く",
    "v4_joined": None, "vjob": None, "v4_joining": False, "wait_until": 0, "_booted": False,
    "menu_open": False, "need_top": True, "act_busy": False, "password_hash": "",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v
if "characters" not in st.session_state:
    st.session_state.characters = load_json(DATA_FILE, {"characters": []}).get("characters", [])
if not st.session_state._booted:
    st.session_state._booted = True
    if st.query_params.get("p"):
        st.session_state.page = st.query_params.get("p")

qs = st.query_params
if st.session_state.logged_in and qs.get("checkout") == "success":
    st.session_state.premium_until = (datetime.now() + timedelta(days=30)).isoformat()
    st.session_state.points = int(st.session_state.points) + MONTHLY_POINTS
    save_user_state()
    st.query_params.clear()
    go("plan")
if st.session_state.logged_in and qs.get("buypoints"):
    try:
        add = int(str(qs.get("buypoints")))
        if add in [p["points"] for p in POINT_PACKS]:
            st.session_state.points = int(st.session_state.points) + add
            save_user_state()
    except Exception:
        pass
    st.query_params.clear()
    go("shop")

st.markdown("""
<style>
section[data-testid="stSidebar"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"],
[data-testid="stStatusWidget"],
[data-testid="stToolbar"],
[data-testid="stHeaderActionElements"],
[data-testid="stDecoration"],
#MainMenu { display: none !important; }
div[data-testid="stButton"] > button {
  background: #ffffff !important;
  color: #111111 !important;
  border: 2px solid #111111 !important;
  border-radius: 999px !important;
  font-weight: 800 !important;
  box-shadow: none !important;
}
div[data-testid="stButton"] > button[kind="primary"] {
  background: #ffffff !important;
  color: #111111 !important;
  border: 2px solid #111111 !important;
  box-shadow: none !important;
}
section.main div[data-testid="stHorizontalBlock"]:first-of-type div[data-testid="column"]:first-child div[data-testid="stButton"] > button {
  background: linear-gradient(180deg,#ffc1dc,#ff6ea8) !important;
  color: #ffffff !important;
  border: 3px solid #ffffff !important;
  box-shadow: 0 5px 0 #ff4d88 !important;
}
</style>
""", unsafe_allow_html=True)

render_top_menu()
if st.session_state.get("need_top"):
    scroll_top()
    st.session_state.need_top = False

if st.session_state.page == "home":
    b64 = file_b64(HOME_IMG)
    if b64:
        st.markdown(f'<style>.stApp{{background-image:linear-gradient(rgba(255,255,255,.18),rgba(255,255,255,.18)),url("data:image/jpeg;base64,{b64}");background-size:cover;background-position:center;}}</style>', unsafe_allow_html=True)
    st.markdown("<div style='height:28vh'></div>", unsafe_allow_html=True)
    st.markdown("""
    <div style="text-align:center;color:#ff4d88;font-size:20px;font-weight:800;line-height:1.7;
    background:rgba(255,255,255,.82);padding:16px 14px;border-radius:22px;border:3px solid #ffb6d5;">
    panel AIは<br>4コマ画像・4コマ動画<br>画像生成・動画生成<br>作成AIサイト ♡
    </div>
    """, unsafe_allow_html=True)
    mid = st.columns([1, 2, 1])
    with mid[1]:
        if st.button("panel", use_container_width=True, key="home_panel"):
            go("help"); st.rerun()
    st.stop()

show_header()

if st.session_state.error:
    st.error(st.session_state.error)
    if st.button("通知を閉じる"):
        st.session_state.error = ""; st.rerun()

if st.session_state.page == "help":
    st.markdown(f"""<div style="color:#111;background:#fff;padding:16px;border-radius:12px;">
    <h2>画像生成モード</h2><p>ポイントを消費して画像生成<br>日本語で作成可能<br>おすすめ</p>
    <h2>セット</h2><p>絵柄の登録<br>キャラの登録<br>登録したら4コマ画像生成の時、絵柄、キャラが反映される</p>
    <h2>4コマ</h2><p>セット絵柄、キャラを使えて画像生成して、会話、吹き出しをつけれるよ！<br>最後に合体させて4コマ完成！</p>
    <h2>動画生成モード</h2><p>ポイントで動画生成<br>秒数が長いほどポイントが増える<br>4コマ動画も1コマずつポイント消費<br>自分のmp4（10秒以下）を入れてまとめることもできる<br>まとめは20ポイント</p>
    <h2>月額登録</h2><p>セット機能開放<br>サイズの変更開放<br>{MONTHLY_POINTS}ポイント付与</p></div>""", unsafe_allow_html=True)
    if st.button("登録して始めよう！", type="primary", use_container_width=True):
        go("register" if not st.session_state.logged_in else "simple"); st.rerun()

elif st.session_state.page == "lib":
    st.subheader("保存庫")
    if not st.session_state.library:
        st.write("まだありません。")
    for i, item in enumerate(reversed(st.session_state.library)):
        st.image(item["url"], width=160)
        st.caption(f"{item.get('label','')} {item.get('time','')}")
        a, b = st.columns(2)
        with a:
            if st.button("動画にする", key=f"libv_{i}"):
                st.session_state.video_src = item["url"]; go("video"); st.rerun()
        with b:
            if st.button("消す", key=f"libd_{i}"):
                st.session_state.library.pop(len(st.session_state.library) - 1 - i); save_user_state(); st.rerun()

elif st.session_state.page == "video":
    st.subheader("動画生成")
    job = st.session_state.get("vjob") if isinstance(st.session_state.get("vjob"), dict) else None
    if job and job.get("kind") == "video":
        act = show_countdown_wait("生成中", "video")
        if act == "cancel":
            finish_action(); st.session_state.vjob = None; go("video"); st.rerun()
        if act == "confirm":
            try:
                state, val = grok_poll_video(job["id"])
                if state == "done":
                    st.session_state.video_out = val; st.session_state.vjob = None
                elif state == "error":
                    st.session_state.error = val; st.session_state.vjob = None
                else:
                    start_wait(); st.session_state.error = "まだ生成中です。もう一度確認してください"
            except Exception as e:
                st.session_state.error = str(e)
                start_wait()
            finally:
                finish_action()
            go("video"); st.rerun()
    up = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"])
    if up:
        st.session_state.video_src = uploaded_to_uri(up)
    if st.session_state.library:
        picks = [f"{x.get('time','')} {x.get('label','')}" for x in st.session_state.library]
        sel = st.selectbox("保存庫から選ぶ", ["選ばない"] + picks)
        if sel != "選ばない":
            st.session_state.video_src = st.session_state.library[picks.index(sel)]["url"]
    if st.session_state.video_src:
        st.image(st.session_state.video_src, width=240)
    motion = st.text_area("動きの内容", placeholder="ゆっくり瞬きする")
    dur = st.slider("秒数", 3, 10, 6)
    st.caption(f"消費ポイント {video_cost(dur)}")
    if st.button("動画にする", type="primary"):
        if not st.session_state.video_src:
            st.session_state.error = "画像を選んでください"
        else:
            try:
                take_points(video_cost(dur))
                st.session_state.vjob = {"kind": "video", "id": grok_start_video(st.session_state.video_src, motion, dur)}
                start_wait(); st.session_state.error = ""
            except Exception as e:
                st.session_state.error = str(e)
        go("video"); st.rerun()
    if st.session_state.video_out and os.path.exists(st.session_state.video_out):
        st.video(st.session_state.video_out)
        with open(st.session_state.video_out, "rb") as f:
            st.download_button("動画を保存", data=f.read(), file_name="video.mp4", mime="video/mp4")

elif st.session_state.page == "v4":
    st.subheader("4コマ動画")
    job = st.session_state.get("vjob") if isinstance(st.session_state.get("vjob"), dict) else None
    st.session_state.v4_count = st.radio("コマ数", [2, 3, 4], index=[2, 3, 4].index(int(st.session_state.v4_count)), horizontal=True)
    n = int(st.session_state.v4_count)
    layout_opts = {2: ["縦2", "横2"], 3: ["縦3", "横3"], 4: ["縦4", "横4", "2×2"]}[n]
    if st.session_state.v4_layout not in layout_opts:
        st.session_state.v4_layout = layout_opts[0]
    st.session_state.v4_layout = st.radio("並び", layout_opts, horizontal=True, index=layout_opts.index(st.session_state.v4_layout))
    st.session_state.v4_play = st.radio("再生", ["同時に動く", "順番に動く"], horizontal=True, index=0 if st.session_state.v4_play == "同時に動く" else 1)
    for i in range(n):
        with st.expander(f"コマ {i+1}", expanded=True):
            src = st.session_state.panel_images[i]
            if st.session_state.library:
                picks = ["今の4コマ画像"] + [f"{x.get('time','')} {x.get('label','')}" for x in st.session_state.library]
                sel = st.selectbox("画像", picks, key=f"v4s_{i}")
                if sel != "今の4コマ画像":
                    src = st.session_state.library[picks.index(sel) - 1]["url"]
            up = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"], key=f"v4u_{i}")
            if up:
                src = uploaded_to_uri(up)
            if src:
                st.image(src, width=180)
            vup = st.file_uploader("動画をアップロード（mp4・10秒以下）", type=["mp4"], key=f"v4vu_{i}")
            if vup is not None and st.button("この動画を使う", key=f"v4vuse_{i}"):
                try:
                    st.session_state.v4_clips[i] = save_upload_mp4(vup); st.session_state.error = ""
                except Exception as e:
                    st.session_state.error = str(e)
                go("v4"); st.rerun()
            st.session_state.v4_prompts[i] = st.text_input("動き", value=st.session_state.v4_prompts[i], key=f"v4p_{i}")
            st.session_state.v4_durs[i] = st.slider("秒数", 3, 10, int(st.session_state.v4_durs[i]), key=f"v4d_{i}")
            if job and job.get("kind") == "v4" and int(job.get("i", -1)) == i:
                act = show_countdown_wait(f"コマ{i+1} 生成中", f"p{i}")
                if act == "cancel":
                    finish_action(); st.session_state.vjob = None; go("v4"); st.rerun()
                if act == "confirm":
                    try:
                        state, val = grok_poll_video(job["id"])
                        if state == "done":
                            st.session_state.v4_clips[i] = val; st.session_state.vjob = None
                        elif state == "error":
                            st.session_state.error = val; st.session_state.vjob = None
                        else:
                            start_wait(); st.session_state.error = "まだ生成中です。もう一度確認してください"
                    except Exception as e:
                        st.session_state.error = str(e)
                        start_wait()
                    finally:
                        finish_action()
                    go("v4"); st.rerun()
            if st.button("このコマを動画にする", key=f"v4g_{i}"):
                if not src:
                    st.session_state.error = "画像がありません"
                else:
                    try:
                        take_points(video_cost(st.session_state.v4_durs[i]))
                        st.session_state.vjob = {"kind": "v4", "i": i, "id": grok_start_video(src, st.session_state.v4_prompts[i], st.session_state.v4_durs[i])}
                        start_wait(); st.session_state.error = ""
                    except Exception as e:
                        st.session_state.error = str(e)
                go("v4"); st.rerun()
            if st.session_state.v4_clips[i] and os.path.exists(st.session_state.v4_clips[i]):
                st.video(st.session_state.v4_clips[i])
    ready_clips = [st.session_state.v4_clips[i] for i in range(n) if st.session_state.v4_clips[i] and os.path.exists(st.session_state.v4_clips[i])]
    st.subheader("まとめ")
    if st.session_state.get("v4_joining"):
        act = show_countdown_wait("まとめ生成中", "join")
        if act == "cancel":
            finish_action(); st.session_state.v4_joining = False; go("v4"); st.rerun()
        if act == "confirm":
            try:
                take_points(JOIN_COST)
                out = os.path.join(VID_DIR, f"join_{uuid.uuid4().hex}.mp4")
                st.session_state.v4_joined = compose_yonkoma_video(ready_clips, st.session_state.v4_layout, out, sequential=(st.session_state.v4_play == "順番に動く"))
                st.session_state.error = ""
            except Exception as e:
                st.session_state.error = str(e)
            finally:
                finish_action()
            st.session_state.v4_joining = False; go("v4"); st.rerun()
    if st.button("漫画動画としてまとめる", type="primary"):
        if len(ready_clips) < n:
            st.session_state.error = f"{n}本そろえてください"
        else:
            st.session_state.v4_joining = True; start_wait(); st.session_state.error = ""
        go("v4"); st.rerun()
    if st.session_state.v4_joined and os.path.exists(st.session_state.v4_joined):
        st.video(st.session_state.v4_joined)
        with open(st.session_state.v4_joined, "rb") as f:
            st.download_button("漫画動画を保存", data=f.read(), file_name="manga.mp4", mime="video/mp4")

elif st.session_state.page == "icon":
    st.subheader("アイコン変更")
    if not st.session_state.logged_in:
        st.warning("ログインしてください"); st.stop()
    up = st.file_uploader("新しいアイコン", type=["png", "jpg", "jpeg"])
    if up:
        st.image(up, width=80)
    if st.button("この画像にする", type="primary") and up:
        st.session_state.icon = uploaded_to_uri(up); save_user_state(); st.rerun()
    if st.button("動物アイコンに戻す"):
        st.session_state.icon = random.choice(ANIMALS); save_user_state(); st.rerun()

elif st.session_state.page == "shop":
    st.subheader("ポイント購入")
    if not st.session_state.logged_in:
        st.warning("購入にはログインが必要です。")
    elif stripe is None or not STRIPE_SECRET_KEY:
        st.error("決済設定がまだです。")
    else:
        for pack in POINT_PACKS:
            c1, c2 = st.columns([3, 2])
            with c1:
                st.write(f"**{pack['points']}ポイント**")
            with c2:
                if st.button(f"{pack['yen']}円で買う", key=f"buy_{pack['points']}"):
                    try:
                        session = stripe.checkout.Session.create(mode="payment", line_items=[{"price_data": {"currency": "jpy", "unit_amount": pack["yen"], "product_data": {"name": f"{pack['points']}ポイント"}}, "quantity": 1}], success_url=f"{SITE_URL}/?buypoints={pack['points']}", cancel_url=f"{SITE_URL}/?buypoints=cancel", client_reference_id=st.session_state.get("username", ""))
                        st.markdown(f"[決済ページへ進む]({session.url})")
                    except Exception as e:
                        st.error(str(e))

elif st.session_state.page == "register":
    st.subheader("登録 / ログイン")
    name = st.text_input("ユーザーネーム")
    mail = st.text_input("メールアドレス")
    pw = st.text_input("パスワード", type="password")
    icon_up = st.file_uploader("アイコン（任意）", type=["png", "jpg", "jpeg"])
    if icon_up:
        st.image(icon_up, width=80)
    if st.button("確認コードを送る"):
        users = load_json(USERS_FILE, {})
        if not name or not mail or not pw:
            st.warning("全部入れてください")
        elif not valid_mail_format(mail):
            st.error("メールの形が正しくありません")
        elif not mail_domain_ok(mail):
            st.error("存在しないアドレスです")
        elif name in users:
            st.error("その名前は使われています")
        elif email_taken(users, mail):
            st.error("このメールアドレスは登録済みです")
        else:
            code = f"{random.randint(100000, 999999)}"
            ok, err = send_code_mail(norm_mail(mail), code)
            if not ok:
                st.error(f"メールを送れませんでした: {err}")
            else:
                st.session_state.pending = {"name": name, "email": norm_mail(mail), "password": hash_password(pw), "icon": uploaded_to_uri(icon_up) if icon_up else random.choice(ANIMALS), "code": code}
                st.success("確認コードを送りました。")
    if st.session_state.pending:
        code_in = st.text_input("確認コード")
        if st.button("登録する", type="primary"):
            p = st.session_state.pending
            users = load_json(USERS_FILE, {})
            if code_in.strip() != p["code"]:
                st.error("コードが違います")
            elif email_taken(users, p["email"]) or p["name"] in users:
                st.error("すでに登録されています")
            else:
                users[p["name"]] = {"password": p["password"], "email": p["email"], "icon": p["icon"], "characters": [], "points": SIGNUP_POINTS, "premium_until": "", "rank": "ブロンズ", "history": [], "library": []}
                save_json(USERS_FILE, users)
                apply_login(p["name"], users[p["name"]])
                st.session_state.pending = None
                go("simple"); st.rerun()
    st.write("ログイン")
    lu = st.text_input("メールまたはユーザーネーム", key="lu")
    lp = st.text_input("ログイン用パスワード", type="password", key="lp")
    if st.button("ログインする"):
        users = load_json(USERS_FILE, {})
        found = find_user(users, lu)
        if found and users[found]["password"] == hash_password(lp):
            apply_login(found, users[found]); go("simple"); st.rerun()
        else:
            st.error("ログインできません")

elif st.session_state.page == "contact":
    st.subheader("お問い合わせ")
    st.write(f"送信先: {CONTACT_TO}")
    cname = st.text_input("お名前")
    cmail = st.text_input("返信先メール")
    cbody = st.text_area("内容")
    if st.button("メールを送る", type="primary"):
        if not cname or not cmail or not cbody:
            st.warning("全部入れてください")
        elif not valid_mail_format(cmail):
            st.error("メールの形が正しくありません")
        else:
            ok, err = send_mail(CONTACT_TO, f"[panel AI] お問い合わせ {cname}", f"名前: {cname}\n返信先: {cmail}\nユーザー: {st.session_state.get('username','未ログイン')}\n\n{cbody}")
            st.success("送りました") if ok else st.error(f"送れませんでした: {err}")

elif st.session_state.page == "plan":
    st.subheader("月額登録")
    st.write(f"**{MONTHLY_PRICE}円 / 30日**")
    st.write(f"- {MONTHLY_POINTS}ポイント付与")
    st.write("- セット機能開放")
    st.write("- サイズの変更開放")
    if is_premium():
        st.success(f"VIPです。期限 {str(st.session_state.premium_until)[:10]}")
    elif stripe is None or not STRIPE_SECRET_KEY or not STRIPE_PRICE_ID:
        st.error("決済設定がまだです。")
    elif st.button(f"{MONTHLY_PRICE}円で登録する", type="primary"):
        try:
            session = stripe.checkout.Session.create(mode="subscription", line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}], success_url=f"{SITE_URL}/?checkout=success", cancel_url=f"{SITE_URL}/?checkout=cancel", client_reference_id=st.session_state.get("username", ""))
            st.markdown(f"[決済ページへ進む]({session.url})")
        except Exception as e:
            st.error(str(e))

elif st.session_state.page == "chars":
    st.subheader("セット")
    if not is_premium() and not is_owner():
        st.warning("セットはVIPだけです。"); st.stop()
    save_name = st.text_input("保存名", placeholder="任意")
    use_type = st.radio("種類", ["キャラだけ", "絵柄だけ", "キャラ＋絵柄"], horizontal=True)
    char_files, style_files, char_strengths, style_strengths = [], [], [], []
    if use_type != "絵柄だけ":
        char_files = st.file_uploader("キャラ（最大3）", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="char_ups")
        for i, f in enumerate((char_files or [])[:3]):
            st.image(f, width=110)
            char_strengths.append(st.slider(f"キャラ強度{i+1}", 1, 10, 8, key=f"cs_{i}"))
    if use_type != "キャラだけ":
        style_files = st.file_uploader("絵柄（最大3）", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="style_ups")
        for i, f in enumerate((style_files or [])[:3]):
            st.image(f, width=110)
            style_strengths.append(st.slider(f"絵柄強度{i+1}", 1, 10, 8, key=f"ss_{i}"))
    if st.button("保存", type="primary"):
        chars = [{"uri": uploaded_to_uri(f), "strength": char_strengths[i]} for i, f in enumerate((char_files or [])[:3])]
        styles = [{"uri": uploaded_to_uri(f), "strength": style_strengths[i]} for i, f in enumerate((style_files or [])[:3])]
        if not chars and not styles:
            st.warning("画像を入れてください")
        else:
            st.session_state.characters.append({"id": str(uuid.uuid4())[:8], "save_name": save_name.strip() or f"セット{len(st.session_state.characters)+1}", "kind": use_type, "chars": chars, "styles": styles})
            save_user_state(); st.rerun()
    for i, ch in enumerate(st.session_state.characters):
        c1, c2 = st.columns([4, 1])
        with c1:
            st.write(char_label(ch))
        with c2:
            if st.button("消去", key=f"delc_{i}"):
                st.session_state.characters.pop(i); save_user_state(); st.rerun()

elif st.session_state.page == "simple":
    st.subheader("画像生成モード")
    if st.button("履歴"):
        st.session_state.show_history = True; st.rerun()
    if st.session_state.show_history:
        if st.button("戻る"):
            st.session_state.show_history = False; st.session_state.hist_pick = None; st.rerun()
        for hi, item in enumerate(reversed(st.session_state.simple_history)):
            st.image(item["url"], width=160)
            if st.button("この画像", key=f"hpick_{hi}"):
                st.session_state.hist_pick = item; st.rerun()
        if st.session_state.hist_pick:
            st.write("反映しますか？")
            a, b = st.columns(2)
            with a:
                if st.button("はい"):
                    item = st.session_state.hist_pick
                    st.session_state.sq = item.get("quality", ""); st.session_state.sb = item.get("background", "")
                    st.session_state.so = item.get("other", ""); st.session_state.sn = item.get("negative", "")
                    st.session_state.schars = item.get("chars") or [""]; st.session_state.simple_image = item.get("url")
                    st.session_state.hist_pick = None; st.session_state.show_history = False; st.rerun()
            with b:
                if st.button("いいえ"):
                    st.session_state.hist_pick = None; st.rerun()
        st.stop()
    st.session_state.sq = st.text_area("画質プロンプト", value=st.session_state.sq)
    st.session_state.sb = st.text_area("背景プロンプト", value=st.session_state.sb)
    if st.button("➕ キャラ追加") and len(st.session_state.schars) < 3:
        st.session_state.schars.append(""); st.rerun()
    for i in range(len(st.session_state.schars)):
        a, b = st.columns([5, 1])
        with a:
            st.session_state.schars[i] = st.text_area(f"キャラクタープロンプト{i+1}", value=st.session_state.schars[i], key=f"scarea_{i}")
        with b:
            if i > 0 and st.button("消す", key=f"scdel_{i}"):
                st.session_state.schars.pop(i); st.rerun()
    st.session_state.so = st.text_area("その他プロンプト", value=st.session_state.so)
    st.session_state.sn = st.text_area("除外プロンプト", value=st.session_state.sn)
    size_opts = [k for k, v in SIMPLE_SIZES.items() if (is_premium() or is_owner() or not v["paid"])]
    size_name = st.radio("サイズ", size_opts, horizontal=True)
    spec = SIMPLE_SIZES[size_name]
    st.caption(f"{spec['gen'][0]} × {spec['gen'][1]}　{spec['cost']}ポイント")
    scale = st.slider("プロンプトガイダンス", 1.0, 10.0, 5.0, 0.1)
    if st.button("生成する", type="primary"):
        st.session_state.error = ""; st.session_state.simple_busy = True; st.rerun()
    if st.session_state.simple_busy:
        st.session_state.simple_busy = False
        chars = [x.strip() for x in st.session_state.schars if x.strip()]
        parts = [x.strip() for x in [st.session_state.sq, st.session_state.sb, st.session_state.so] if x.strip()]
        if not parts and not chars:
            st.session_state.error = "プロンプトを入れてください"
        elif spec["paid"] and not is_premium() and not is_owner():
            st.session_state.error = "このサイズはVIPだけです"
        else:
            try:
                take_points(spec["cost"])
                img = nai_request(", ".join(parts), spec["gen"][0], spec["gen"][1], "nai-diffusion-5-full", steps=20, scale=scale, negative=st.session_state.sn.strip(), char_texts=chars)
                st.session_state.simple_image = img
                st.session_state.simple_history.append({"url": img, "quality": st.session_state.sq, "background": st.session_state.sb, "chars": list(st.session_state.schars), "other": st.session_state.so, "negative": st.session_state.sn, "size": size_name, "scale": scale})
                save_user_state(); st.session_state.error = ""
            except Exception as e:
                st.session_state.error = str(e)
        go("simple"); st.rerun()
    if st.session_state.simple_image:
        st.image(st.session_state.simple_image, use_container_width=True)
        raw = uri_to_image(st.session_state.simple_image)
        st.download_button("PNG保存", data=image_to_bytes(raw), file_name="simple.png", mime="image/png")
        if st.button("保存庫に入れる"):
            add_library(st.session_state.simple_image, "画像生成"); st.success("入れました")
        if st.button("この画像を動画にする"):
            st.session_state.video_src = st.session_state.simple_image; go("video"); st.rerun()

else:
    st.subheader("4コマ")
    layout = st.radio("並べ方", list(LAYOUTS.keys()), horizontal=True)
    st.session_state.layout = layout
    n = LAYOUTS[layout]["count"]
    names = [char_label(ch) for ch in st.session_state.characters]
    size_opts = [k for k, v in SIZES.items() if (is_premium() or is_owner() or not v["paid"])]

    def set_by_name(name):
        for ch in st.session_state.characters:
            if char_label(ch) == name:
                return ch
        return None

    def make_one(i):
        scene = st.session_state.scenes[i].strip()
        if not scene:
            raise Exception("内容が空です")
        spec = SIZES.get(st.session_state.panel_shape[i], SIZES["横長"])
        if spec["paid"] and not is_premium() and not is_owner():
            raise Exception("このサイズはVIPだけです")
        chosen = st.session_state.scene_chars[i]
        if chosen != "セットなし" and not is_premium() and not is_owner():
            raise Exception("セットはVIPだけです")
        pack = {} if chosen == "セットなし" else (set_by_name(chosen) or {})
        chars, styles = normalize_refs(pack.get("chars")), normalize_refs(pack.get("styles"))
        take_points(spec["cost"] + REF_SITE * (min(3, len(chars)) + min(3, len(styles))))
        st.session_state.panel_images[i] = nai_request(scene, spec["gen"][0], spec["gen"][1], "nai-diffusion-4-5-full", steps=23, scale=5.0, char_refs=chars, style_refs=styles)
        st.session_state.panel_sizes[i] = spec["wh"]
        st.session_state.panel_upload[i] = False

    for i in range(n):
        with st.expander(f"コマ {i+1}", expanded=True):
            cur = st.session_state.panel_shape[i] if st.session_state.panel_shape[i] in size_opts else "横長"
            shape = st.selectbox("サイズ", size_opts, index=size_opts.index(cur), key=f"shape_{i}")
            st.session_state.panel_shape[i] = shape
            spec = SIZES[shape]
            if not st.session_state.panel_upload[i]:
                st.session_state.panel_sizes[i] = spec["wh"]
            st.caption(f"{spec['wh'][0]} × {spec['wh'][1]}　消費 {spec['cost']}")
            up = st.file_uploader("持っている画像を使う", type=["png", "jpg", "jpeg"], key=f"up_{i}")
            if up:
                st.session_state.panel_images[i] = uploaded_to_uri(up)
                st.session_state.panel_upload[i] = True
                st.session_state.panel_sizes[i] = uri_to_image(st.session_state.panel_images[i]).size
            st.session_state.scenes[i] = st.text_input("生成する内容", value=st.session_state.scenes[i], key=f"sc_{i}")
            options = ["セットなし"] + (names if (is_premium() or is_owner()) else [])
            curc = st.session_state.scene_chars[i]
            st.session_state.scene_chars[i] = st.selectbox("セット", options, index=options.index(curc) if curc in options else 0, key=f"ch_{i}")
            if st.session_state.get("busy_index") == i:
                st.info(f"コマ{i+1} 生成中…")
                try:
                    make_one(i)
                    st.session_state.error = ""
                except Exception as e:
                    st.session_state.error = str(e)
                st.session_state.busy_index = None
                go("make")
                st.rerun()
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("生成", key=f"gen_{i}", type="primary"):
                    st.session_state.error = ""
                    st.session_state.busy_index = i
                    st.rerun()
            with c2:
                if st.button("消す", key=f"clr_{i}"):
                    st.session_state.panel_images[i] = None
                    st.session_state.panel_bubbles[i] = []
                    st.session_state.panel_upload[i] = False
                    st.rerun()
            with c3:
                if st.session_state.panel_images[i] and st.button("保存庫へ", key=f"sv_{i}"):
                    add_library(st.session_state.panel_images[i], f"4コマ{i+1}")
                    st.success("入れました")
            if st.session_state.panel_images[i]:
                draft = st.session_state.drafts[i]
                draft["text"] = st.text_input("新しいセリフ", value=draft.get("text", ""), key=f"bt_{i}")
                d1, d2 = st.columns(2)
                with d1:
                    draft["kind"] = st.selectbox("形", BUBBLE_TYPES, key=f"bk_{i}")
                    draft["tail"] = st.selectbox("しっぽ", TAILS, key=f"tl_{i}")
                    draft["font"] = st.selectbox("フォント", usable_fonts, key=f"bfn_{i}")
                    draft["dir"] = st.selectbox("向き", TEXT_DIR, key=f"bd_{i}")
                with d2:
                    draft["size"] = st.slider("文字の大きさ", 16, 64, int(draft.get("size", 28)), key=f"bs_{i}")
                    draft["bold"] = st.slider("太さ", 0, 4, int(draft.get("bold", 0)), key=f"bb_{i}")
                    draft["tail_size"] = st.slider("しっぽの大きさ", 8, 80, int(draft.get("tail_size", 28)), key=f"bts_{i}")
                    draft["x"] = st.slider("左右", 0, 100, int(draft.get("x", 8)), key=f"bx_{i}")
                    draft["y"] = st.slider("上下", 0, 100, int(draft.get("y", 8)), key=f"by_{i}")
                    draft["angle"] = st.slider("傾き", -45, 45, int(draft.get("angle", 0)), key=f"ba_{i}")
                draft["fill"] = st.color_picker("吹き出し色", draft.get("fill", "#ffffff"), key=f"bf_{i}")
                draft["color"] = st.color_picker("文字色", draft.get("color", "#111111"), key=f"bc_{i}")
                st.session_state.drafts[i] = draft
                if st.button("このセリフを追加", key=f"addb_{i}") and draft["text"].strip():
                    st.session_state.panel_bubbles[i].append(dict(draft))
                    st.session_state.drafts[i] = empty_bubble()
                    st.rerun()
                for bi, bb in enumerate(st.session_state.panel_bubbles[i]):
                    k1, k2 = st.columns([5, 1])
                    with k1:
                        st.caption(bb.get("text", ""))
                    with k2:
                        if st.button("×", key=f"delb_{i}_{bi}"):
                            st.session_state.panel_bubbles[i].pop(bi)
                            st.rerun()
                preview = draw_all_bubbles(panel_raw(i), st.session_state.panel_bubbles[i])
                if draft["text"].strip():
                    preview = draw_one_bubble(preview, draft)
                st.image(preview, width=340)

    if st.button("1枚にまとめる", type="primary"):
        panels = []
        for i in range(n):
            if not st.session_state.panel_images[i]:
                st.error(f"コマ{i+1}がありません")
                panels = None
                break
            panels.append(draw_all_bubbles(panel_raw(i), st.session_state.panel_bubbles[i]))
        if panels:
            st.session_state.combined = combine_panels(panels, cols=LAYOUTS[layout]["cols"])
            go("make")
            st.rerun()
    if st.session_state.combined is not None:
        st.image(st.session_state.combined, use_container_width=True)
        st.download_button("PNG保存", data=image_to_bytes(st.session_state.combined), file_name="yonkoma.png", mime="image/png")
        if st.button("まとめた画像を保存庫へ"):
            buf = BytesIO()
            st.session_state.combined.save(buf, format="PNG")
            add_library("data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(), "4コマまとめ")
            st.success("入れました")
