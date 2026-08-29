import streamlit as st
import os
import json
import uuid
import base64
import hashlib
import math
import io
import zipfile
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(page_title="panel AI.", page_icon="🎨", layout="wide")

NAI_KEY = os.environ.get("NOVELAI_API_KEY", "")
NAI_URLS = [
    "https://image.novelai.net/ai/generate-image",
    "https://api.novelai.net/ai/generate-image",
]
DATA_FILE = "studio_data.json"
USERS_FILE = "users_data.json"
HOME_IMG = "IMG_1106.jpeg"
HEADER_IMG = "IMG_1107.jpeg"

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
    "横長": (1216, 832),
    "縦長": (832, 1216),
    "正方形": (1024, 1024),
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

def uri_to_b64(uri):
    img = uri_to_image(uri)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def nai_generate(prompt, width, height, char_refs=None, style_refs=None):
    if not NAI_KEY:
        raise Exception("NOVELAI_API_KEY がありません")
    if width >= height:
        width, height = 1216, 832
    elif height > width * 1.2:
        width, height = 832, 1216
    else:
        width, height = 1024, 1024
    char_refs = [x for x in (char_refs or []) if x.get("uri")]
    style_refs = [x for x in (style_refs or []) if x.get("uri")]
    parameters = {
        "params_version": 3,
        "width": width,
        "height": height,
        "scale": 5.0,
        "sampler": "k_euler_ancestral",
        "steps": 23,
        "n_samples": 1,
        "qualityToggle": False,
        "ucPreset": 0,
        "negative_prompt": "",
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
    refs = []
    kinds = []
    strengths = []
    for x in char_refs[:3]:
        refs.append(uri_to_b64(x["uri"]))
        kinds.append("character")
        strengths.append(max(0.3, min(1.0, x.get("strength", 8) / 10)))
    for x in style_refs[:3]:
        refs.append(uri_to_b64(x["uri"]))
        kinds.append("style")
        strengths.append(max(0.3, min(1.0, x.get("strength", 8) / 10)))
    if refs:
        parameters["director_reference_images"] = refs
        parameters["director_reference_descriptions"] = [
            {"caption": {"base_caption": k, "char_captions": []}, "legacy_uc": False}
            for k in kinds
        ]
        parameters["director_reference_information_extracted"] = [1] * len(refs)
        parameters["director_reference_strength_values"] = strengths
        parameters["director_reference_secondary_strength_values"] = [0.75] * len(refs)
    last_err = None
    for model in ["nai-diffusion-4-5-full", "nai-diffusion-4-5-curated", "nai-diffusion-4-full"]:
        payload = {
            "input": prompt,
            "model": model,
            "action": "generate",
            "parameters": parameters,
        }
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
            last_err = f"{model} / {res.status_code}: {res.text[:300]}"
            if "enum" in (res.text or ""):
                break
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
        line_h = int(size * 1.15)
        box_w = size + pad * 2 + bold * 2
        box_h = pad * 2 + line_h * len(lines) + bold * 2
    else:
        lines = wrap_text(text, font, max_w)
        line_h = int(size * 1.3)
        try:
            text_w = max(font.getlength(x) for x in lines)
        except Exception:
            text_w = max(len(x) * size for x in lines)
        box_w = int(text_w + pad * 2 + bold * 2)
        box_h = int(pad * 2 + line_h * len(lines) + bold * 2)
    layer = Image.new("RGBA", (box_w + 80, box_h + 80), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x0, y0 = 40, 28
    if kind == "ふきだし":
        draw.rounded_rectangle([x0, y0, x0 + box_w, y0 + box_h], radius=22, fill=fill, outline="#222222", width=3)
        if tail == "下":
            draw.polygon([(x0 + box_w * 0.38, y0 + box_h - 2), (x0 + box_w * 0.52, y0 + box_h - 2), (x0 + box_w * 0.34, y0 + box_h + 28)], fill=fill)
        elif tail == "下左":
            draw.polygon([(x0 + 18, y0 + box_h - 2), (x0 + 48, y0 + box_h - 2), (x0 + 8, y0 + box_h + 28)], fill=fill)
        elif tail == "下右":
            draw.polygon([(x0 + box_w - 48, y0 + box_h - 2), (x0 + box_w - 18, y0 + box_h - 2), (x0 + box_w - 8, y0 + box_h + 28)], fill=fill)
        elif tail == "左":
            draw.polygon([(x0 + 2, y0 + box_h * 0.45), (x0 + 2, y0 + box_h * 0.62), (x0 - 26, y0 + box_h * 0.58)], fill=fill)
        else:
            draw.polygon([(x0 + box_w - 2, y0 + box_h * 0.45), (x0 + box_w - 2, y0 + box_h * 0.62), (x0 + box_w + 26, y0 + box_h * 0.58)], fill=fill)
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
        draw.ellipse([x0 + 16, y0 + box_h + 6, x0 + 34, y0 + box_h + 24], fill=fill, outline="#222222")
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

def empty_bubble():
    return {
        "text": "", "x": 8, "y": 8, "angle": 0, "fill": "#ffffff", "color": "#111111",
        "size": 28, "bold": 0, "kind": "ふきだし", "font": "ゴシック", "dir": "横書き", "tail": "下",
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
    st.session_state.scene_chars = ["", "", "", ""]
if "panel_images" not in st.session_state:
    st.session_state.panel_images = [None, None, None, None]
if "panel_sizes" not in st.session_state:
    st.session_state.panel_sizes = [SIZES["横長"]] * 4
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

if not st.session_state.logged_in:
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
        top = st.columns([6, 2])
        with top[1]:
            if st.button("ログイン"):
                st.session_state.page = "login"; st.rerun()
        st.markdown("<div style='height:58vh'></div>", unsafe_allow_html=True)
        mid = st.columns([1, 2, 1])
        with mid[1]:
            if st.button("会員登録してはじめる", type="primary", use_container_width=True):
                st.session_state.page = "register"; st.rerun()
        st.stop()

    show_header()
    if st.session_state.page == "login":
        st.subheader("ログイン")
        u = st.text_input("ユーザー名")
        p = st.text_input("パスワード", type="password")
        if st.button("ログインする", type="primary"):
            users = load_json(USERS_FILE, {})
            if u in users and users[u]["password"] == hash_password(p):
                st.session_state.logged_in = True
                st.session_state.username = u
                st.session_state.characters = users[u].get("characters", st.session_state.characters)
                st.session_state.page = "make"
                st.rerun()
            else:
                st.error("ログインできません")
        if st.button("ホームへ"):
            st.session_state.page = "home"; st.rerun()
        st.stop()
    st.subheader("会員登録")
    u = st.text_input("ユーザー名")
    p = st.text_input("パスワード", type="password")
    if st.button("登録する", type="primary"):
        users = load_json(USERS_FILE, {})
        if not u or not p:
            st.warning("入力してください")
        elif u in users:
            st.error("その名前は使われています")
        else:
            users[u] = {"password": hash_password(p), "characters": []}
            save_json(USERS_FILE, users)
            st.session_state.logged_in = True
            st.session_state.username = u
            st.session_state.page = "make"
            st.rerun()
    if st.button("ホームへ"):
        st.session_state.page = "home"; st.rerun()
    st.stop()

show_header()
done = sum(1 for x in st.session_state.panel_images if x)
need = LAYOUTS[st.session_state.layout]["count"]
with st.sidebar:
    st.write(st.session_state.get("username", ""))
    if st.button("セット", use_container_width=True):
        st.session_state.page = "chars"; st.rerun()
    if st.button("4コマ", use_container_width=True):
        st.session_state.page = "make"; st.rerun()
    st.caption(f"{done}/{need}")
    if st.button("ログアウト"):
        st.session_state.logged_in = False
        st.session_state.page = "home"
        st.rerun()

if st.session_state.error:
    st.error(st.session_state.error)

if st.session_state.page == "chars":
    st.subheader("セット")
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
            save_json(DATA_FILE, {"characters": st.session_state.characters})
            users = load_json(USERS_FILE, {})
            if st.session_state.get("username") in users:
                users[st.session_state.username]["characters"] = st.session_state.characters
                save_json(USERS_FILE, users)
            st.success("保存しました")
            st.rerun()
    for i, ch in enumerate(st.session_state.characters):
        c1, c2 = st.columns([4, 1])
        with c1:
            st.write(char_label(ch))
        with c2:
            if st.button("削除", key=f"delc_{i}"):
                st.session_state.characters.pop(i)
                save_json(DATA_FILE, {"characters": st.session_state.characters})
                st.rerun()

else:
    st.subheader("4コマ")
    layout = st.radio("並べ方", list(LAYOUTS.keys()), horizontal=True)
    st.session_state.layout = layout
    n = LAYOUTS[layout]["count"]
    names = [char_label(ch) for ch in st.session_state.characters]

    def set_by_name(name):
        for ch in st.session_state.characters:
            if char_label(ch) == name:
                return ch
        return None

    def make_one(i):
        scene = st.session_state.scenes[i].strip()
        if not scene:
            raise Exception("内容が空です")
        w, h = st.session_state.panel_sizes[i]
        pack = set_by_name(st.session_state.scene_chars[i]) or {}
        chars = normalize_refs(pack.get("chars"))
        styles = normalize_refs(pack.get("styles"))
        st.session_state.panel_images[i] = nai_generate(scene, w, h, chars, styles)

    for i in range(n):
        with st.expander(f"コマ {i+1}", expanded=True):
            shape = st.selectbox("サイズ", list(SIZES.keys()) + ["数字"], key=f"shape_{i}")
            if shape in SIZES:
                st.session_state.panel_sizes[i] = SIZES[shape]
                st.caption(f"{SIZES[shape][0]} × {SIZES[shape][1]}")
            else:
                a, b = st.columns(2)
                with a:
                    pw = st.number_input("幅", 256, 2048, st.session_state.panel_sizes[i][0], 16, key=f"pw_{i}")
                with b:
                    ph = st.number_input("高さ", 256, 2048, st.session_state.panel_sizes[i][1], 16, key=f"ph_{i}")
                st.session_state.panel_sizes[i] = (int(pw), int(ph))
            up = st.file_uploader("持っている画像を使う", type=["png", "jpg", "jpeg"], key=f"up_{i}")
            if up:
                st.session_state.panel_images[i] = uploaded_to_uri(up)
            st.session_state.scenes[i] = st.text_input("生成する内容", value=st.session_state.scenes[i], key=f"sc_{i}")
            if names:
                current = st.session_state.scene_chars[i] if st.session_state.scene_chars[i] in names else names[0]
                st.session_state.scene_chars[i] = st.selectbox("セット", names, index=names.index(current), key=f"ch_{i}")
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
                    draft["size"] = st.slider("大きさ", 16, 64, int(draft.get("size", 28)), key=f"bs_{i}")
                    draft["bold"] = st.slider("太さ", 0, 4, int(draft.get("bold", 0)), key=f"bb_{i}")
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
