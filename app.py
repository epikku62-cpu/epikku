import streamlit as st
import os
import json
import hashlib
import base64
import requests
import uuid
from io import BytesIO
from datetime import datetime
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(page_title="4コマ工房", page_icon="漫画", layout="wide")

USERS_FILE = "users_data.json"
grok_key = os.environ.get("XAI_API_KEY", "")
client = OpenAI(api_key=grok_key, base_url="https://api.x.ai/v1")

PANEL_W, PANEL_H = 768, 768
FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/msgothic.ttc",
]

def load_font(size=28):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def save_current_user_data():
    if not st.session_state.get("username"):
        return
    users = load_users()
    name = st.session_state.username
    if name in users:
        users[name]["data"] = {
            "characters": st.session_state.get("characters", []),
            "works": st.session_state.get("works", [])[-20:],
            "points": st.session_state.get("points", 80),
        }
        save_users(users)

def uploaded_to_uri(uploaded):
    raw = uploaded.getvalue()
    mime = uploaded.type or "image/png"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"

def uri_to_image(uri):
    if not uri:
        return None
    if uri.startswith("data:"):
        b64 = uri.split(",", 1)[1]
        return Image.open(BytesIO(base64.b64decode(b64))).convert("RGB")
    res = requests.get(uri, timeout=60)
    return Image.open(BytesIO(res.content)).convert("RGB")

def generate_panel(prompt, ref_uris):
    extra = {
        "aspect_ratio": "1:1",
        "resolution": "1k",
        "quality": "low",
    }
    if not ref_uris:
        response = client.images.generate(
            model="grok-imagine-image-2.0",
            prompt=prompt,
            n=1,
            extra_body=extra,
        )
        return response.data[0].url

    payload = {
        "model": "grok-imagine-image-2.0",
        "prompt": prompt,
        "aspect_ratio": "1:1",
        "resolution": "1k",
        "quality": "low",
        "response_format": "url",
    }
    if len(ref_uris) == 1:
        payload["image"] = {"url": ref_uris[0], "type": "image_url"}
    else:
        payload["images"] = [{"url": u, "type": "image_url"} for u in ref_uris[:3]]
    res = requests.post(
        "https://api.x.ai/v1/images/edits",
        headers={"Authorization": f"Bearer {grok_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=180,
    )
    data = res.json()
    if res.status_code != 200:
        raise Exception(data)
    return data["data"][0]["url"]

def wrap_text(text, font, max_width):
    lines, line = [], ""
    for ch in text:
        test = line + ch
        if font.getlength(test) <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = ch
    if line:
        lines.append(line)
    return lines or [""]

def draw_bubble(panel_img, text, pos="上", fill="#ffffff", font_color="#111111"):
    if not text.strip():
        return panel_img
    img = panel_img.copy()
    draw = ImageDraw.Draw(img)
    font = load_font(28)
    w, h = img.size
    max_w = int(w * 0.7)
    lines = wrap_text(text.strip(), font, max_w - 24)
    line_h = 34
    box_h = 20 + line_h * len(lines)
    box_w = min(max_w, int(max(font.getlength(x) for x in lines) + 36))
    if pos == "上":
        x, y = 20, 20
    elif pos == "上右":
        x, y = w - box_w - 20, 20
    else:
        x, y = 20, h - box_h - 20
    draw.rounded_rectangle([x, y, x + box_w, y + box_h], radius=18, fill=fill, outline="#222222", width=3)
    ty = y + 10
    for line in lines:
        draw.text((x + 16, ty), line, font=font, fill=font_color)
        ty += line_h
    return img

def combine_panels(images, cols=2):
    imgs = [im.resize((PANEL_W, PANEL_H)) for im in images]
    n = len(imgs)
    if n <= 2:
        cols = 1
        rows = n
    else:
        rows = (n + cols - 1) // cols
    gap = 16
    canvas = Image.new("RGB", (cols * PANEL_W + gap * (cols + 1), rows * PANEL_H + gap * (rows + 1)), "#111111")
    for i, im in enumerate(imgs):
        r, c = divmod(i, cols)
        canvas.paste(im, (gap + c * (PANEL_W + gap), gap + r * (PANEL_H + gap)))
    return canvas

def image_to_bytes(img):
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "characters" not in st.session_state:
    st.session_state.characters = []
if "works" not in st.session_state:
    st.session_state.works = []
if "points" not in st.session_state:
    st.session_state.points = 80
if "mode" not in st.session_state:
    st.session_state.mode = "chars"
if "panel_count" not in st.session_state:
    st.session_state.panel_count = 4
if "scenes" not in st.session_state:
    st.session_state.scenes = ["", "", "", ""]
if "scene_chars" not in st.session_state:
    st.session_state.scene_chars = [None, None, None, None]
if "panel_images" not in st.session_state:
    st.session_state.panel_images = [None, None, None, None]
if "bubbles" not in st.session_state:
    st.session_state.bubbles = [{"text": "", "pos": "上", "fill": "#ffffff", "color": "#111111"} for _ in range(4)]

if not st.session_state.logged_in:
    st.title("4コマ工房")
    tab1, tab2 = st.tabs(["ログイン", "新規登録"])
    with tab1:
        u = st.text_input("ユーザー名", key="login_user")
        p = st.text_input("パスワード", type="password", key="login_pass")
        if st.button("ログイン", type="primary"):
            users = load_users()
            if u in users and users[u]["password"] == hash_password(p):
                data = users[u].get("data", {})
                st.session_state.logged_in = True
                st.session_state.username = u
                st.session_state.characters = data.get("characters", [])
                st.session_state.works = data.get("works", [])
                st.session_state.points = data.get("points", 80)
                st.rerun()
            else:
                st.error("ログインできません")
    with tab2:
        u = st.text_input("新しいユーザー名", key="reg_user")
        p = st.text_input("パスワード", type="password", key="reg_pass")
        if st.button("登録", type="primary"):
            users = load_users()
            if not u or not p:
                st.warning("入力してください")
            elif u in users:
                st.error("その名前は使われています")
            else:
                users[u] = {"password": hash_password(p), "data": {"characters": [], "works": [], "points": 80}}
                save_users(users)
                st.session_state.logged_in = True
                st.session_state.username = u
                st.session_state.points = 80
                st.rerun()
    st.stop()

with st.sidebar:
    st.write(f"**{st.session_state.username}**")
    st.write(f"ポイント: {st.session_state.points} pt")
    st.caption("1コマ 10pt")
    if st.button("キャラ固定", use_container_width=True):
        st.session_state.mode = "chars"; st.rerun()
    if st.button("4コマを作る", use_container_width=True):
        st.session_state.mode = "comic"; st.rerun()
    if st.button("吹き出し", use_container_width=True):
        st.session_state.mode = "bubble"; st.rerun()
    if st.button("作品", use_container_width=True):
        st.session_state.mode = "works"; st.rerun()
    if st.button("ログアウト"):
        save_current_user_data()
        st.session_state.logged_in = False
        st.rerun()

mode = st.session_state.mode

if mode == "chars":
    st.header("固定キャラ")
    st.write("絵柄とキャラの参照を登録すると、4コマの各コマに割り当てできます。複数登録できます。")
    name = st.text_input("キャラ名")
    c1, c2 = st.columns(2)
    with c1:
        char_file = st.file_uploader("キャラ参照", type=["png", "jpg", "jpeg"], key="char_up")
        if char_file:
            st.image(char_file, width=180)
    with c2:
        style_file = st.file_uploader("絵柄参照（任意）", type=["png", "jpg", "jpeg"], key="style_up")
        if style_file:
            st.image(style_file, width=180)
    if st.button("このキャラを固定する", type="primary"):
        if not name.strip() or not char_file:
            st.warning("名前とキャラ参照は必須です")
        else:
            st.session_state.characters.append({
                "id": str(uuid.uuid4())[:8],
                "name": name.strip(),
                "char": uploaded_to_uri(char_file),
                "style": uploaded_to_uri(style_file) if style_file else "",
            })
            save_current_user_data()
            st.success(f"{name} を固定しました")
            st.rerun()

    if not st.session_state.characters:
        st.info("まだ固定キャラはありません")
    else:
        for i, ch in enumerate(st.session_state.characters):
            box = st.container()
            with box:
                a, b, c = st.columns([2, 2, 1])
                with a:
                    st.write(f"**{ch['name']}**")
                    st.image(ch["char"], width=140)
                with b:
                    if ch.get("style"):
                        st.caption("絵柄")
                        st.image(ch["style"], width=140)
                with c:
                    if st.button("削除", key=f"delc_{i}"):
                        st.session_state.characters.pop(i)
                        save_current_user_data()
                        st.rerun()

elif mode == "comic":
    st.header("4コマシーン")
    st.caption("精度優先のため、1コマ目を作ってから、それを見本に2コマ目以降を作ります。")
    count = st.radio("コマ数", [2, 3, 4], index=2, horizontal=True)
    if count != st.session_state.panel_count:
        st.session_state.panel_count = count
        st.rerun()
    n = st.session_state.panel_count
    names = [ch["name"] for ch in st.session_state.characters] or ["（先にキャラを固定）"]

    for i in range(n):
        st.markdown(f"### コマ {i+1}")
        st.session_state.scenes[i] = st.text_input("このコマの内容", value=st.session_state.scenes[i], key=f"sc_{i}")
        if st.session_state.characters:
            pick = st.selectbox(
                "使う固定キャラ",
                names,
                index=min(i, len(names) - 1) if st.session_state.scene_chars[i] is None else max(names.index(st.session_state.scene_chars[i]) if st.session_state.scene_chars[i] in names else 0, 0),
                key=f"ch_{i}",
            )
            st.session_state.scene_chars[i] = pick
        if st.session_state.panel_images[i]:
            st.image(st.session_state.panel_images[i], width=240)

    cost = 10 * n
    st.write(f"全部作ると {cost} pt（所持 {st.session_state.points} pt）")

    def char_by_name(name):
        for ch in st.session_state.characters:
            if ch["name"] == name:
                return ch
        return None

    def build_prompt(i, scene, char_name):
        return (
            "Manga comic panel, clean illustration, no speech bubbles, no text, no letters, no captions. "
            f"Character: {char_name}. "
            f"Scene {i+1}: {scene}. "
            "Keep the same face, hair, outfit and art style. "
            "One character unless the scene needs two."
        )

    def make_one(i):
        scene = st.session_state.scenes[i].strip()
        if not scene:
            raise Exception(f"コマ{i+1}の内容が空です")
        ch = char_by_name(st.session_state.scene_chars[i])
        refs = []
        if ch:
            if ch.get("char"):
                refs.append(ch["char"])
            if ch.get("style"):
                refs.append(ch["style"])
        if i > 0 and st.session_state.panel_images[0]:
            refs.insert(0, st.session_state.panel_images[0])
        url = generate_panel(build_prompt(i, scene, st.session_state.scene_chars[i] or "girl"), refs[:3])
        st.session_state.panel_images[i] = url
        return url

    colx, coly = st.columns(2)
    with colx:
        if st.button("1コマ目だけ作る", type="primary"):
            if st.session_state.points < 10:
                st.error("ポイント不足")
            elif not grok_key:
                st.error("XAI_API_KEY がありません")
            else:
                try:
                    with st.spinner("1コマ目を生成中..."):
                        make_one(0)
                    st.session_state.points -= 10
                    save_current_user_data()
                    st.rerun()
                except Exception as e:
                    st.error(e)
    with coly:
        if st.button("残りコマを1コマ目に寄せて作る"):
            if not st.session_state.panel_images[0]:
                st.warning("先に1コマ目を作ってください")
            elif st.session_state.points < 10 * (n - 1):
                st
