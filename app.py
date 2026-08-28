import streamlit as st
import os
import uuid
import base64
import requests
from io import BytesIO
from datetime import datetime
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(page_title="4コマ工房", page_icon="🎨", layout="wide")

PANEL_W, PANEL_H = 768, 768
grok_key = os.environ.get("XAI_API_KEY", "")
client = OpenAI(api_key=grok_key, base_url="https://api.x.ai/v1")

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

LAYOUTS = {
    "縦に4つ": {"cols": 1, "count": 4},
    "正方形に4つ": {"cols": 2, "count": 4},
    "横に4つ": {"cols": 4, "count": 4},
    "縦に2つ": {"cols": 1, "count": 2},
    "横に2つ": {"cols": 2, "count": 2},
    "縦に3つ": {"cols": 1, "count": 3},
}

def load_font(size=28):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
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

def generate_panel(prompt, ref_uris):
    extra = {"aspect_ratio": "1:1", "resolution": "1k", "quality": "low"}
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
    max_w = int(w * 0.72)
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

def load_font(size=28):
    for path in [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()

def combine_panels(images, cols=2):
    imgs = [im.resize((768, 768)) for im in images]
    n = len(imgs)
    rows = (n + cols - 1) // cols
    gap = 16
    canvas = Image.new(
        "RGB",
        (cols * 768 + gap * (cols + 1), rows * 768 + gap * (rows + 1)),
        "#111111",
    )
    for i, im in enumerate(imgs):
        r, c = divmod(i, cols)
        canvas.paste(im, (gap + c * (768 + gap), gap + r * (768 + gap)))
    return canvas

def image_to_bytes(img):
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

if "characters" not in st.session_state:
    st.session_state.characters = []
if "panel_count" not in st.session_state:
    st.session_state.panel_count = 4
if "layout" not in st.session_state:
    st.session_state.layout = "正方形に4つ"
if "scenes" not in st.session_state:
    st.session_state.scenes = ["", "", "", ""]
if "scene_chars" not in st.session_state:
    st.session_state.scene_chars = ["", "", "", ""]
if "panel_images" not in st.session_state:
    st.session_state.panel_images = [None, None, None, None]
if "bubbles" not in st.session_state:
    st.session_state.bubbles = [
        {"text": "", "pos": "上", "fill": "#ffffff", "color": "#111111"} for _ in range(4)
    ]
if "works" not in st.session_state:
    st.session_state.works = []
if "mode" not in st.session_state:
    st.session_state.mode = "chars"
if "error" not in st.session_state:
    st.session_state.error = ""
if "busy" not in st.session_state:
    st.session_state.busy = False

LAYOUTS = {
    "縦に4つ": {"cols": 1, "count": 4},
    "正方形に4つ": {"cols": 2, "count": 4},
    "横に4つ": {"cols": 4, "count": 4},
    "縦に3つ": {"cols": 1, "count": 3},
    "縦に2つ": {"cols": 1, "count": 2},
    "横に2つ": {"cols": 2, "count": 2},
}

with st.sidebar:
    st.title("4コマ工房")
    if st.button("1. キャラを固定", use_container_width=True):
        st.session_state.mode = "chars"; st.rerun()
    if st.button("2. 4コマを作る", use_container_width=True):
        st.session_state.mode = "comic"; st.rerun()
    if st.button("3. 吹き出し", use_container_width=True):
        st.session_state.mode = "bubble"; st.rerun()
    if st.button("作品", use_container_width=True):
        st.session_state.mode = "works"; st.rerun()
    st.caption("テスト用。登録画面なし。")

if st.session_state.error:
    st.error(st.session_state.error)

mode = st.session_state.mode

if mode == "chars":
    st.header("固定キャラ")
    st.write("キャラ参照と絵柄参照を登録します。複数登録できます。4コマの各コマに割り当てます。")
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
            st.success(f"{name} を固定しました")
            st.rerun()

    if not st.session_state.characters:
        st.info("まだ固定キャラはありません")
    else:
        for i, ch in enumerate(st.session_state.characters):
            a, b, c = st.columns([2, 2, 1])
            with a:
                st.write(f"**{ch['name']}**")
                st.image(ch["char"], width=160)
            with b:
                if ch.get("style"):
                    st.caption("絵柄")
                    st.image(ch["style"], width=160)
            with c:
                if st.button("削除", key=f"delc_{i}"):
                    st.session_state.characters.pop(i)
                    st.rerun()

elif mode == "comic":
    st.header("4コマシーン")
    st.write("精度優先のため、1コマずつ作ります。2コマ目以降は1コマ目を見本にします。")
    layout = st.radio("並び", list(LAYOUTS.keys()), horizontal=True)
    st.session_state.layout = layout
    n = LAYOUTS[layout]["count"]
    st.session_state.panel_count = n
    names = [ch["name"] for ch in st.session_state.characters]

    if not names:
        st.warning("先にキャラを固定してください")
    else:
        for i in range(n):
            st.markdown(f"### コマ {i+1}")
            st.session_state.scenes[i] = st.text_input(
                "このコマの内容",
                value=st.session_state.scenes[i],
                key=f"sc_{i}",
            )
            current = st.session_state.scene_chars[i] if st.session_state.scene_chars[i] in names else names[0]
            st.session_state.scene_chars[i] = st.selectbox(
                "使う固定キャラ",
                names,
                index=names.index(current),
                key=f"ch_{i}",
            )
            if st.session_state.panel_images[i]:
                st.image(st.session_state.panel_images[i], width=240)
            if st.button(f"コマ{i+1}を生成", key=f"gen_{i}", type="primary" if i == 0 else "secondary"):
                st.session_state.busy_index = i
                st.rerun()

        if st.button("空いているコマをまとめて生成"):
            st.session_state.busy_index = "all"
            st.rerun()

    def char_by_name(name):
        for ch in st.session_state.characters:
            if ch["name"] == name:
                return ch
        return None

    def make_one(i):
        scene = st.session_state.scenes[i].strip()
        if not scene:
            raise Exception(f"コマ{i+1}の内容が空です")
        ch = char_by_name(st.session_state.scene_chars[i])
        refs = []
        if i > 0 and st.session_state.panel_images[0]:
            refs.append(st.session_state.panel_images[0])
        if ch:
            if ch.get("char"):
                refs.append(ch["char"])
            if ch.get("style"):
                refs.append(ch["style"])
        prompt = (
            "Square manga comic panel, clean illustration, no speech bubbles, no text, no letters, no captions. "
            f"Character: {st.session_state.scene_chars[i]}. "
            f"Scene: {scene}. "
            "Keep the same face, hair, outfit, linework and coloring as the reference. "
            "One character unless the scene needs two."
        )
        url = generate_panel(prompt, refs[:3])
        st.session_state.panel_images[i] = url
        return url

    busy = st.session_state.get("busy_index")
    if busy is not None:
        st.session_state.busy_index = None
        if not grok_key:
            st.session_state.error = "XAI_API_KEY がありません"
        else:
            try:
                if busy == "all":
                    with st.spinner("コマを生成中..."):
                        for i in range(n):
                            if not st.session_state.panel_images[i]:
                                make_one(i)
                    st.session_state.error = ""
                else:
                    with st.spinner(f"コマ{busy+1}を生成中..."):
                        make_one(int(busy))
                    st.session_state.error = ""
            except Exception as e:
                st.session_state.error = str(e)
        st.rerun()

    n = LAYOUTS[st.session_state.layout]["count"]
    if all(st.session_state.panel_images[:n]):
        st.success("全コマそろいました")
        if st.button("吹き出し編集へ", type="primary"):
            st.session_state.mode = "bubble"
            st.rerun()

elif mode == "bubble":
    st.header("吹き出しと文字")
    n = st.session_state.panel_count
    layout = LAYOUTS[st.session_state.layout]
    if not all(st.session_state.panel_images[:n]):
        st.warning("先にコマを全部作ってください")
    else:
        panels = []
        cols = st.columns(2)
        for i in range(n):
            with cols[i % 2]:
                st.markdown(f"**コマ {i+1}**")
                st.session_state.bubbles[i]["text"] = st.text_area(
                    "セリフ", value=st.session_state.bubbles[i]["text"], key=f"bt_{i}", height=70
                )
                st.session_state.bubbles[i]["pos"] = st.selectbox("位置", ["上", "上右", "下"], key=f"bp_{i}")
                st.session_state.bubbles[i]["fill"] = st.color_picker("吹き出し色", st.session_state.bubbles[i]["fill"], key=f"bf_{i}")
                st.session_state.bubbles[i]["color"] = st.color_picker("文字色", st.session_state.bubbles[i]["color"], key=f"bc_{i}")
            raw = uri_to_image(st.session_state.panel_images[i])
            bub = st.session_state.bubbles[i]
            panels.append(draw_bubble(raw, bub["text"], bub["pos"], bub["fill"], bub["color"]))
        comic = combine_panels(panels, cols=layout["cols"])
        st.image(comic, use_container_width=True)
        st.download_button("PNGで保存", data=image_to_bytes(comic), file_name="yonkoma.png", mime="image/png")

elif mode == "works":
    st.header("作品")
    st.write("まだ保存機能はテスト用に省略しています。吹き出し画面からPNG保存してください。")
