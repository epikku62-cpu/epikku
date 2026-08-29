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
import requests
from io import BytesIO
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

try:
    import stripe
except ImportError:
    stripe = None

st.set_page_config(page_title="panel AI.", page_icon="🎨", layout="wide")

NAI_KEY = os.environ.get("NOVELAI_API_KEY", "")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
SITE_URL = os.environ.get("SITE_URL", "https://aistation.onrender.com")
if stripe is not None and STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

NAI_URLS = [
    "https://image.novelai.net/ai/generate-image",
    "https://api.novelai.net/ai/generate-image",
]
DATA_FILE = "studio_data.json"
USERS_FILE = "users_data.json"
HOME_IMG = "IMG_1106.jpeg"
HEADER_IMG = "IMG_1107.jpeg"
PHONE_W, PHONE_H = 1080, 1920
MONTHLY_PRICE = 980
MONTHLY_POINTS = 2000
REF_SITE = 10
V5_COST = 0
ANIMALS = ["🐱", "🐶", "🐰", "🐻", "🦊", "🐼", "🐸", "🦉", "🐧", "🐯"]

LAYOUTS = {
    "縦4": {"cols": 1, "count": 4},
    "縦3": {"cols": 1, "count": 3},
    "縦2": {"cols": 1, "count": 2},
    "横4": {"cols": 4, "count": 4},
    "横3": {"cols": 3, "count": 3},
    "横2": {"cols": 2, "count": 2},
    "2×2": {"cols": 2, "count": 4},
}
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
    "横長 1216×832": (1216, 832),
    "縦長 832×1216": (832, 1216),
    "正方形 1024×1024": (1024, 1024),
}
BUBBLE_TYPES = ["ふきだし", "叫び", "考え", "文字だけ"]
TAILS = ["下", "下左", "下右", "左", "右"]
TEXT_DIR = ["横書き", "縦書き"]
FONT_SPECS = {
    "ゴシック": {
        "file": "font_gothic.otf",
        "urls": [
            "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf",
            "https://cdn.jsdelivr.net/gh/notofonts/noto-cjk@main/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf",
        ],
    },
    "丸文字": {
        "file": "font_maru.ttf",
        "urls": ["https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/kosugimaru/KosugiMaru-Regular.ttf"],
    },
    "かわいい": {
        "file": "font_kawaii.ttf",
        "urls": ["https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/hachimarupop/HachiMaruPop-Regular.ttf"],
    },
    "手書き風": {
        "file": "font_te.ttf",
        "urls": ["https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/yuseimagic/YuseiMagic-Regular.ttf"],
    },
}

def file_b64(path):
    if not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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
    if os.path.exists(spec["file"]):
        try:
            return ImageFont.truetype(spec["file"], size)
        except Exception:
            pass
    if os.path.exists(FONT_SPECS["ゴシック"]["file"]):
        try:
            return ImageFont.truetype(FONT_SPECS["ゴシック"]["file"], size)
        except Exception:
            pass
    return ImageFont.load_default()

def uploaded_to_uri(uploaded):
    raw = uploaded.getvalue()
    mime = uploaded.type or "image/png"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"

def uri_to_image(uri):
    if not uri:
        return None
    if uri.startswith("data:"):
        return Image.open(BytesIO(base64.b64decode(uri.split(",", 1)[1]))).convert("RGB")
    res = requests.get(uri, timeout=90)
    res.raise_for_status()
    return Image.open(BytesIO(res.content)).convert("RGB")

def pad_ref(uri):
    img = uri_to_image(uri).convert("RGB")
    tw, th = 1024, 1536
    canvas = Image.new("RGB", (tw, th), (0, 0, 0))
    img.thumbnail((tw, th))
    canvas.paste(img, ((tw - img.width) // 2, (th - img.height) // 2))
    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def save_user_state():
    users = load_json(USERS_FILE, {})
    name = st.session_state.get("username")
    if name in users:
        users[name]["characters"] = st.session_state.characters
        users[name]["points"] = st.session_state.points
        users[name]["premium_until"] = st.session_state.premium_until
        users[name]["rank"] = "vip" if is_premium() else "ブロンズ"
        users[name]["icon"] = st.session_state.get("icon", "")
        save_json(USERS_FILE, users)

def is_premium():
    until = st.session_state.get("premium_until") or ""
    if not until:
        return False
    try:
        return datetime.fromisoformat(until) > datetime.now()
    except Exception:
        return False

def member_label():
    return "VIP" if is_premium() else "ブロンズ"

def nai_wh(w, h):
    w = max(64, min(1920, int(round(w / 64) * 64)))
    h = max(64, min(1920, int(round(h / 64) * 64)))
    return w, h

def nai_request(prompt, width, height, model, steps=23, scale=5.0, char_refs=None, style_refs=None):
    if not NAI_KEY:
        raise Exception("NOVELAI_API_KEY がありません")
    gw, gh = nai_wh(width, height)
    char_refs = [x for x in (char_refs or []) if x.get("uri")][:3]
    style_refs = [x for x in (style_refs or []) if x.get("uri")][:3]
    parameters = {
        "params_version": 3,
        "width": gw,
        "height": gh,
        "scale": float(scale),
        "sampler": "k_euler_ancestral",
        "steps": int(steps),
        "n_samples": 1,
        "qualityToggle": False,
        "ucPreset": 0,
        "negative_prompt": "",
        "noise_schedule": "karras",
        "v4_prompt": {
            "caption": {"base_caption": prompt, "char_captions": []},
            "use_coords": False,
            "use_order": True,
        },
        "v4_negative_prompt": {
            "caption": {"base_caption": "", "char_captions": []},
            "legacy_uc": False,
        },
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
            parameters["director_reference_descriptions"] = [
                {"caption": {"base_caption": kinds[0], "char_captions": []}, "legacy_uc": False}
            ]
            parameters["director_reference_information_extracted"] = [1]
            parameters["director_reference_strength_values"] = [1]
            parameters["director_reference_secondary_strength_values"] = [0.75]
    payload = {"input": prompt, "model": model, "action": "generate", "parameters": parameters}
    last_err = None
    for url in NAI_URLS:
        res = requests.post(
            url,
            headers={"Authorization": f"Bearer {NAI_KEY}", "Content-Type": "application/json"},
            json=payload,
            timeout=180,
        )
        if res.status_code == 200:
            with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
                png = zf.read(zf.namelist()[0])
            return "data:image/png;base64," + base64.b64encode(png).decode()
        last_err = f"{res.status_code}: {res.text[:400]}"
    raise Exception(last_err or "NovelAIの生成に失敗しました")

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

def draw_one_bubble(img, bub):
    text = (bub.get("text") or "").strip()
    if not text:
        return img
    img = img.convert("RGBA")
    size = int(bub.get("size", 28))
    bold = int(bub.get("bold", 0))
    tail_size = int(bub.get("tail_size", 28))
    font = load_font(size, bub.get("font", "ゴシック"))
    w, h = img.size
    kind = bub.get("kind", "ふきだし")
    direction = bub.get("dir", "横書き")
    fill = bub.get("fill", "#ffffff")
    color = bub.get("color", "#111111")
    tail = bub.get("tail", "下")
    pad = 16
    max_w = int(w * 0.62)
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
    extra = tail_size + 40
    layer = Image.new("RGBA", (box_w + extra * 2, box_h + extra * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x0, y0 = extra, extra
    if kind == "ふきだし":
        draw.rounded_rectangle([x0, y0, x0 + box_w, y0 + box_h], radius=22, fill=fill, outline="#222222", width=3)
        ts = tail_size
        if tail == "下":
            draw.polygon([(x0 + box_w * 0.38, y0 + box_h - 2), (x0 + box_w * 0.52, y0 + box_h - 2), (x0 + box_w * 0.34, y0 + box_h + ts)], fill=fill)
        elif tail == "下左":
            draw.polygon([(x0 + 18, y0 + box_h - 2), (x0 + 18 + ts * 0.7, y0 + box_h - 2), (x0 + 8, y0 + box_h + ts)], fill=fill)
        elif tail == "下右":
            draw.polygon([(x0 + box_w - 18 - ts * 0.7, y0 + box_h - 2), (x0 + box_w - 18, y0 + box_h - 2), (x0 + box_w - 8, y0 + box_h + ts)], fill=fill)
        elif tail == "左":
            draw.polygon([(x0 + 2, y0 + box_h * 0.45), (x0 + 2, y0 + box_h * 0.62), (x0 - ts, y0 + box_h * 0.58)], fill=fill)
        else:
            draw.polygon([(x0 + box_w - 2, y0 + box_h * 0.45), (x0 + box_w - 2, y0 + box_h * 0.62), (x0 + box_w + ts, y0 + box_h * 0.58)], fill=fill)
    elif kind == "叫び":
        pts = []
        for i in range(28):
            ang = math.pi * 2 * i / 28
            rx = box_w / 2 * (1.12 if i % 2 == 0 else 0.86)
            ry = box_h / 2 * (1.12 if i % 2 == 0 else 0.86)
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
            draw_text(draw, (x0 + pad, ty), line, font, color, bold)
            ty += int(size * 1.3)
    angle = int(bub.get("angle", 0))
    if angle:
        layer = layer.rotate(-angle, expand=True, resample=Image.BICUBIC)
    px = int(w * float(bub.get("x", 8)) / 100)
    py = int(h * float(bub.get("y", 8)) / 100)
    img.alpha_composite(layer, (max(0, min(w - layer.width, px)), max(0, min(h - layer.height, py))))
    return img.convert("RGB")

def draw_all_bubbles(panel_img, bubbles):
    img = panel_img
    for bub in bubbles or []:
        img = draw_one_bubble(img, bub)
    return img

def combine_panels(images, cols=2):
    gap = 8
    n = len(images)
    rows = (n + cols - 1) // cols
    col_w, row_h = [], []
    for c in range(cols):
        col_w.append(max((images[i].width for i in range(n) if i % cols == c), default=0))
    for r in range(rows):
        row_h.append(max((images[i].height for i in range(n) if i // cols == r), default=0))
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

def show_ad():
    st.markdown(
        """
        <div style="margin-top:24px;background:#eee;color:#111;text-align:center;padding:18px;border:1px dashed #999;">
        広告バナー（あとから貼ります）
        </div>
        """,
        unsafe_allow_html=True,
    )

def empty_bubble():
    return {
        "text": "", "x": 8, "y": 8, "angle": 0, "fill": "#ffffff", "color": "#111111",
        "size": 28, "bold": 0, "tail_size": 28, "kind": "ふきだし", "font": "ゴシック", "dir": "横書き", "tail": "下",
    }

font_ready = prepare_fonts()
usable_fonts = [k for k, ok in font_ready.items() if ok] or ["ゴシック"]

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "page" not in st.session_state:
    st.session_state.page = "home"
if "characters" not in st.session_state:
    st.session_state.characters = load_json(DATA_FILE, {"characters": []}).get("characters", [])
if "layout" not in st.session_state:
    st.session_state.layout = "縦4"
if "scenes" not in st.session_state:
    st.session_state.scenes = ["", "", "", ""]
if "scene_chars" not in st.session_state:
    st.session_state.scene_chars = ["セットなし"] * 4
if "panel_images" not in st.session_state:
    st.session_state.panel_images = [None] * 4
if "panel_sizes" not in st.session_state:
    st.session_state.panel_sizes = [SIZES["横長"]["wh"]] * 4
if "panel_shape" not in st.session_state:
    st.session_state.panel_shape = ["横長"] * 4
if "panel_bubbles" not in st.session_state:
    st.session_state.panel_bubbles = [[], [], [], []]
if "drafts" not in st.session_state:
    st.session_state.drafts = [empty_bubble() for _ in range(4)]
if "error" not in st.session_state:
    st.session_state.error = ""
if "busy_index" not in st.session_state:
    st.session_state.busy_index = None
if "combined" not in st.session_state:
    st.session_state.combined = None
if "points" not in st.session_state:
    st.session_state.points = 0
if "premium_until" not in st.session_state:
    st.session_state.premium_until = ""
if "simple_image" not in st.session_state:
    st.session_state.simple_image = None
if "simple_busy" not in st.session_state:
    st.session_state.simple_busy = False
if "icon" not in st.session_state:
    st.session_state.icon = random.choice(ANIMALS)
if "email" not in st.session_state:
    st.session_state.email = ""

qs = st.query_params
if st.session_state.logged_in and qs.get("checkout") == "success":
    st.session_state.premium_until = (datetime.now() + timedelta(days=30)).isoformat()
    st.session_state.points = int(st.session_state.points) + MONTHLY_POINTS
    save_user_state()
    st.query_params.clear()

st.markdown(
    """
    <style>
    section[data-testid="stSidebar"] { background: #ffffff !important; }
    section[data-testid="stSidebar"] * { color: #111111 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

if st.session_state.page == "home":
    b64 = file_b64(HOME_IMG)
    if b64:
        st.markdown(
            f"""
            <style>
            .stApp {{
                background-image: linear-gradient(rgba(255,255,255,.18), rgba(255,255,255,.18)),
                url("data:image/jpeg;base64,{b64}");
                background-size: cover; background-position: center;
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("<div style='height:58vh'></div>", unsafe_allow_html=True)
    mid = st.columns([1, 2, 1])
    with mid[1]:
        if st.button("生成開始", type="primary", use_container_width=True):
            st.session_state.page = "help"
            st.rerun()
    show_ad()
    st.stop()

show_header()
done = sum(1 for x in st.session_state.panel_images if x)
need = LAYOUTS[st.session_state.layout]["count"]
with st.sidebar:
    if st.session_state.logged_in:
        st.write(st.session_state.get("icon", "🐱"), st.session_state.get("username", ""))
    if st.button("登録", use_container_width=True):
        st.session_state.page = "register"; st.rerun()
    st.write(f"ポイント {st.session_state.points}")
    st.write(f"会員 {member_label() if st.session_state.logged_in else '未登録'}")
    if st.button("画像生成モード", use_container_width=True):
        st.session_state.page = "simple"; st.rerun()
    if st.button("セット", use_container_width=True):
        st.session_state.page = "chars"; st.rerun()
    if st.button("4コマ", use_container_width=True):
        st.session_state.page = "make"; st.rerun()
    if st.button("説明書", use_container_width=True):
        st.session_state.page = "help"; st.rerun()
    if st.button("月額登録", use_container_width=True):
        st.session_state.page = "plan"; st.rerun()
    if st.button("お問い合わせ", use_container_width=True):
        st.session_state.page = "contact"; st.rerun()
    st.caption(f"{done}/{need}")
    if st.session_state.logged_in and st.button("ログアウト"):
        st.session_state.logged_in = False
        st.session_state.page = "home"
        st.rerun()

if st.session_state.error:
    st.error(st.session_state.error)

if st.session_state.page == "help":
    st.markdown(
        """
        <div style="color:#111;background:#fff;padding:16px;border-radius:12px;">
        <h3>ーーー画像生成モードーーー</h3>
        <p>会員登録して画像を作ろう！4コマにも反映できるよ！</p>
        <h3>ーーーセットーーー</h3>
        <p>絵柄の登録<br>キャラの登録<br>登録したら4コマ画像生成の時に絵柄、キャラが反映される</p>
        <h3>ーーー4コマーーー</h3>
        <p>セットした絵柄、キャラを使って画像生成して文字や吹き出しをつけよう！<br>1コマずつ作れるので、最後に合体させて4コマ完成！</p>
        <h3>ーーー月額登録ーーー</h3>
        <p>細かい設定の画像生成<br>セット機能<br>サイズの変更機能<br>ポイント付与</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    show_ad()

elif st.session_state.page == "register":
    st.markdown("<div style='color:#111;background:#fff;padding:16px;'>", unsafe_allow_html=True)
    st.subheader("登録")
    name = st.text_input("ユーザーネーム")
    mail = st.text_input("メールアドレス")
    pw = st.text_input("パスワード", type="password")
    icon_up = st.file_uploader("アイコン（任意）", type=["png", "jpg", "jpeg"])
    if icon_up:
        st.image(icon_up, width=80)
    if st.button("登録する", type="primary"):
        users = load_json(USERS_FILE, {})
        if not name or not mail or not pw:
            st.warning("全部入れてください")
        elif name in users or any(u.get("email") == mail for u in users.values() if isinstance(u, dict)):
            st.error("その名前かメールは使われています")
        else:
            icon = uploaded_to_uri(icon_up) if icon_up else random.choice(ANIMALS)
            users[name] = {
                "password": hash_password(pw),
                "email": mail,
                "icon": icon,
                "characters": [],
                "points": 0,
                "premium_until": "",
                "rank": "ブロンズ",
            }
            save_json(USERS_FILE, users)
            st.session_state.logged_in = True
            st.session_state.username = name
            st.session_state.email = mail
            st.session_state.icon = icon
            st.session_state.points = 0
            st.session_state.page = "simple"
            st.rerun()
    st.write("ログイン")
    lu = st.text_input("メールまたはユーザーネーム", key="lu")
    lp = st.text_input("パスワード", type="password", key="lp")
    if st.button("ログインする"):
        users = load_json(USERS_FILE, {})
        found = None
        if lu in users:
            found = lu
        else:
            for k, v in users.items():
                if isinstance(v, dict) and v.get("email") == lu:
                    found = k
                    break
        if found and users[found]["password"] == hash_password(lp):
            st.session_state.logged_in = True
            st.session_state.username = found
            st.session_state.email = users[found].get("email", "")
            st.session_state.icon = users[found].get("icon", random.choice(ANIMALS))
            st.session_state.characters = users[found].get("characters", [])
            st.session_state.points = int(users[found].get("points", 0))
            st.session_state.premium_until = users[found].get("premium_until", "")
            st.session_state.page = "simple"
            st.rerun()
        else:
            st.error("ログインできません")
    st.markdown("</div>", unsafe_allow_html=True)
    show_ad()

elif st.session_state.page == "contact":
    st.subheader("お問い合わせ")
    st.write("広告や不具合は、あとから載せる連絡先へどうぞ。")
    st.text_area("内容")
    st.button("送信（準備中）")
    show_ad()

elif st.session_state.page == "plan":
    st.subheader("月額登録")
    st.write(f"**{MONTHLY_PRICE}円 / 30日**")
    st.write(f"- {MONTHLY_POINTS}ポイント付与")
    st.write("- 会員状態 VIP")
    st.write("- セット機能")
    st.write("- サイズの変更機能")
    if is_premium():
        st.success(f"VIPです。期限 {str(st.session_state.premium_until)[:10]}")
    elif stripe is None or not STRIPE_SECRET_KEY or not STRIPE_PRICE_ID:
        st.error("決済設定がまだです。")
    elif st.button(f"{MONTHLY_PRICE}円で登録する", type="primary"):
        try:
            session = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
                success_url=f"{SITE_URL}/?checkout=success",
                cancel_url=f"{SITE_URL}/?checkout=cancel",
                client_reference_id=st.session_state.get("username", ""),
            )
            st.markdown(f"[決済ページへ進む]({session.url})")
        except Exception as e:
            st.error(str(e))
    show_ad()

elif st.session_state.page == "chars":
    st.subheader("セット")
    if not is_premium():
        st.warning("セットはVIPだけです。")
        show_ad()
        st.stop()
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
            st.session_state.characters.append({
                "id": str(uuid.uuid4())[:8],
                "save_name": save_name.strip() or f"セット{len(st.session_state.characters)+1}",
                "kind": use_type, "chars": chars, "styles": styles,
            })
            save_user_state()
            st.success("保存しました")
            st.rerun()
    for i, ch in enumerate(st.session_state.characters):
        c1, c2 = st.columns([4, 1])
        with c1:
            st.write(char_label(ch))
        with c2:
            if st.button("削除", key=f"delc_{i}"):
                st.session_state.characters.pop(i)
                save_user_state()
                st.rerun()
    show_ad()

elif st.session_state.page == "simple":
    st.subheader("画像生成モード")
    quality = st.text_area("画質プロンプト")
    background = st.text_area("背景プロンプト")
    character = st.text_area("キャラクタープロンプト")
    other = st.text_area("その他プロンプト")
    size_name = st.radio("サイズ", list(SIMPLE_SIZES.keys()), horizontal=True)
    scale = st.slider("プロンプトガイダンス", 1.0, 10.0, 5.0, 0.1)
    if st.button("生成する", type="primary"):
        st.session_state.simple_busy = True
        st.rerun()
    if st.session_state.simple_busy:
        st.session_state.simple_busy = False
        parts = [x.strip() for x in [quality, background, character, other] if x.strip()]
        if not parts:
            st.session_state.error = "プロンプトを入れてください"
        else:
            try:
                w, h = SIMPLE_SIZES[size_name]
                prompt = ", ".join(parts)
                with st.spinner("生成中..."):
                    st.session_state.simple_image = nai_request(
                        prompt, w, h, "nai-diffusion-5-full", steps=20, scale=scale
                    )
                if V5_COST > 0:
                    st.session_state.points -= V5_COST
                    save_user_state()
                st.session_state.error = ""
            except Exception as e:
                st.session_state.error = str(e)
        st.rerun()
    if st.session_state.simple_image:
        st.image(st.session_state.simple_image, use_container_width=True)
        raw = uri_to_image(st.session_state.simple_image)
        st.download_button("PNG保存", data=image_to_bytes(raw), file_name="simple.png", mime="image/png")
    show_ad()

else:
    st.subheader("4コマ")
    layout = st.radio("並べ方", list(LAYOUTS.keys()), horizontal=True)
    st.session_state.layout = layout
    n = LAYOUTS[layout]["count"]
    names = [char_label(ch) for ch in st.session_state.characters]
    size_opts = [k for k, v in SIZES.items() if (is_premium() or not v["paid"])]

    def set_by_name(name):
        for ch in st.session_state.characters:
            if char_label(ch) == name:
                return ch
        return None

    def make_one(i):
        scene = st.session_state.scenes[i].strip()
        if not scene:
            raise Exception("内容が空です")
        shape = st.session_state.panel_shape[i]
        spec = SIZES.get(shape, SIZES["横長"])
        if spec["paid"] and not is_premium():
            raise Exception("このサイズはVIPだけです")
        chosen = st.session_state.scene_chars[i]
        if chosen != "セットなし" and not is_premium():
            raise Exception("セットはVIPだけです")
        pack = {} if chosen == "セットなし" else (set_by_name(chosen) or {})
        chars = normalize_refs(pack.get("chars"))
        styles = normalize_refs(pack.get("styles"))
        ref_n = min(3, len(chars)) + min(3, len(styles))
        cost = spec["cost"] + REF_SITE * ref_n
        if cost > 0 and st.session_state.points < cost:
            raise Exception(f"ポイントが足りません。必要 {cost}")
        gw, gh = spec["gen"]
        st.session_state.panel_images[i] = nai_request(
            scene, gw, gh, "nai-diffusion-4-5-full", steps=23, scale=5.0,
            char_refs=chars, style_refs=styles
        )
        st.session_state.panel_sizes[i] = spec["wh"]
        if cost > 0:
            st.session_state.points -= cost
            save_user_state()

    for i in range(n):
        with st.expander(f"コマ {i+1}", expanded=True):
            cur = st.session_state.panel_shape[i]
            if cur not in size_opts:
                cur = "横長"
            shape = st.selectbox("サイズ", size_opts, index=size_opts.index(cur), key=f"shape_{i}")
            st.session_state.panel_shape[i] = shape
            spec = SIZES[shape]
            st.session_state.panel_sizes[i] = spec["wh"]
            st.caption(f"{spec['wh'][0]} × {spec['wh'][1]}　消費 {spec['cost']}（セットは1枚+{REF_SITE}）")
            up = st.file_uploader("持っている画像を使う", type=["png", "jpg", "jpeg"], key=f"up_{i}")
            if up:
                st.session_state.panel_images[i] = uploaded_to_uri(up)
            st.session_state.scenes[i] = st.text_input("生成する内容", value=st.session_state.scenes[i], key=f"sc_{i}")
            options = ["セットなし"] + (names if is_premium() else [])
            curc = st.session_state.scene_chars[i]
            idx = options.index(curc) if curc in options else 0
            st.session_state.scene_chars[i] = st.selectbox("セット", options, index=idx, key=f"ch_{i}")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("生成", key=f"gen_{i}", type="primary"):
                    st.session_state.busy_index = i
                    st.rerun()
            with c2:
                if st.button("消す", key=f"clr_{i}"):
                    st.session_state.panel_images[i] = None
                    st.session_state.panel_bubbles[i] = []
                    st.rerun()
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
                    draft["x"] = st.slider("左右", 0, 80, int(draft.get("x", 8)), key=f"bx_{i}")
                    draft["y"] = st.slider("上下", 0, 80, int(draft.get("y", 8)), key=f"by_{i}")
                    draft["angle"] = st.slider("傾き", -45, 45, int(draft.get("angle", 0)), key=f"ba_{i}")
                draft["fill"] = st.color_picker("吹き出し色", draft.get("fill", "#ffffff"), key=f"bf_{i}")
                draft["color"] = st.color_picker("文字色", draft.get("color", "#111111"), key=f"bc_{i}")
                st.session_state.drafts[i] = draft
                if st.button("このセリフを追加", key=f"addb_{i}"):
                    if draft["text"].strip():
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
                raw = uri_to_image(st.session_state.panel_images[i]).resize(st.session_state.panel_sizes[i])
                preview = draw_all_bubbles(raw, st.session_state.panel_bubbles[i])
                if draft["text"].strip():
                    preview = draw_one_bubble(preview, draft)
                st.image(preview, width=340)

    busy = st.session_state.get("busy_index")
    if busy is not None:
        st.session_state.busy_index = None
        try:
            with st.spinner("生成中..."):
                make_one(int(busy))
            st.session_state.error = ""
        except Exception as e:
            st.session_state.error = str(e)
        st.rerun()

    st.markdown("---")
    if st.button("1枚にまとめる", type="primary"):
        panels = []
        for i in range(n):
            if not st.session_state.panel_images[i]:
                st.error(f"コマ{i+1}がありません")
                panels = None
                break
            raw = uri_to_image(st.session_state.panel_images[i]).resize(st.session_state.panel_sizes[i])
            panels.append(draw_all_bubbles(raw, st.session_state.panel_bubbles[i]))
        if panels:
            st.session_state.combined = combine_panels(panels, cols=LAYOUTS[layout]["cols"])
            st.rerun()
    if st.session_state.combined is not None:
        st.image(st.session_state.combined, use_container_width=True)
        st.download_button("PNG保存", data=image_to_bytes(st.session_state.combined), file_name="yonkoma.png", mime="image/png")
    show_ad()
