import streamlit as st
import os
import uuid
import base64
import requests
from io import BytesIO
from datetime import datetime
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
import math

st.set_page_config(page_title="4コマ工房", page_icon="🎨", layout="wide")

grok_key = os.environ.get("XAI_API_KEY", "")
client = OpenAI(api_key=grok_key, base_url="https://api.x.ai/v1")
FONT_FILE = "NotoSansJP-Regular.otf"

LAYOUTS = {
    "縦に4つ": {"cols": 1, "count": 4},
    "正方形に4つ": {"cols": 2, "count": 4},
    "横に4つ": {"cols": 4, "count": 4},
    "縦に3つ": {"cols": 1, "count": 3},
    "縦に2つ": {"cols": 1, "count": 2},
    "横に2つ": {"cols": 2, "count": 2},
}

ASPECT_PRESETS = {
    "正方形": (1024, 1024),
    "縦長": (768, 1344),
    "横長": (1344, 768),
}

POSITIONS = ["上左", "上中央", "上右", "中左", "中右", "下左", "下中央", "下右"]
BUBBLE_TYPES = ["丸四角", "楕円", "叫び", "考え", "文字だけ"]

def ensure_font():
    if os.path.exists(FONT_FILE) and os.path.getsize(FONT_FILE) > 10000:
        return FONT_FILE
    urls = [
        "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf",
        "https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf",
    ]
    for url in urls:
        try:
            r = requests.get(url, timeout=60)
            if r.status_code == 200 and len(r.content) > 10000:
                with open(FONT_FILE, "wb") as f:
                    f.write(r.content)
                return FONT_FILE
        except Exception:
            pass
    return None

def load_font(size=28):
    path = ensure_font()
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    for p in [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "C:/Windows/Fonts/msgothic.ttc",
        "C:/Windows/Fonts/YuGothR.ttc",
    ]:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
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

def ratio_from_size(w, h):
    r = w / h
    choices = {"1:1": 1.0, "3:4": 0.75, "4:3": 1.33, "9:16": 0.5625, "16:9": 1.777, "2:3": 0.666, "3:2": 1.5}
    return min(choices.items(), key=lambda x: abs(x[1] - r))[0]

def generate_panel(prompt, ref_uris, w, h):
    extra = {
        "aspect_ratio": ratio_from_size(w, h),
        "resolution": "1k" if max(w, h) < 1536 else "2k",
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
        "aspect_ratio": extra["aspect_ratio"],
        "resolution": extra["resolution"],
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
        try:
            ok = font.getlength(test) <= max_width
        except Exception:
            ok = len(test) * 16 <= max_width
        if ok:
            line = test
        else:
            if line:
                lines.append(line)
            line = ch
    if line:
        lines.append(line)
    return lines or [""]

def jagged_polygon(x, y, w, h, spikes=14):
    pts = []
    steps = spikes * 2
    for i in range(steps):
        ang = (math.pi * 2) * i / steps
        rx = w / 2 * (1.08 if i % 2 == 0 else 0.86)
        ry = h / 2 * (1.08 if i % 2 == 0 else 0.86)
        pts.append((x + w / 2 + math.cos(ang) * rx, y + h / 2 + math.sin(ang) * ry))
    return pts

def cloud_polygon(x, y, w, h):
    pts = []
    for i in range(16):
        ang = (math.pi * 2) * i / 16
        bump = 1 + 0.12 * math.sin(i * 2.2)
        pts.append((x + w / 2 + math.cos(ang) * w / 2 * bump, y + h / 2 + math.sin(ang) * h / 2 * bump))
    return pts

def bubble_xy(pos, img_w, img_h, box_w, box_h):
    pad = 18
    table = {
        "上左": (pad, pad),
        "上中央": ((img_w - box_w) // 2, pad),
        "上右": (img_w - box_w - pad, pad),
        "中左": (pad, (img_h - box_h) // 2),
        "中右": (img_w - box_w - pad, (img_h - box_h) // 2),
        "下左": (pad, img_h - box_h - pad),
        "下中央": ((img_w - box_w) // 2, img_h - box_h - pad),
        "下右": (img_w - box_w - pad, img_h - box_h - pad),
    }
    return table.get(pos, (pad, pad))

def draw_bubble(panel_img, text, pos="上左", fill="#ffffff", font_color="#111111", size=28, kind="丸四角"):
    if not text.strip():
        return panel_img
    img = panel_img.copy()
    draw = ImageDraw.Draw(img)
    font = load_font(size)
    w, h = img.size
    max_w = int(w * 0.72)
    lines = wrap_text(text.strip(), font, max_w - 24)
    line_h = int(size * 1.25)
    box_h = 20 + line_h * len(lines)
    try:
        tw = max(font.getlength(x) for x in lines)
    except Exception:
        tw = max(len(x) * size for x in lines)
    box_w = min(max_w, int(tw + 36))
    x, y = bubble_xy(pos, w, h, box_w, box_h)
    if kind == "丸四角":
        draw.rounded_rectangle([x, y, x + box_w, y + box_h], radius=18, fill=fill, outline="#222222", width=3)
    elif kind == "楕円":
        draw.ellipse([x, y, x + box_w, y + box_h], fill=fill, outline="#222222", width=3)
    elif kind == "叫び":
        draw.polygon(jagged_polygon(x, y, box_w, box_h), fill=fill, outline="#222222")
    elif kind == "考え":
        draw.polygon(cloud_polygon(x, y, box_w, box_h), fill=fill, outline="#222222")
        draw.ellipse([x + 16, y + box_h - 6, x + 34, y + box_h + 14], fill=fill, outline="#222222")
        draw.ellipse([x + 36, y + box_h + 10, x + 48, y + box_h + 22], fill=fill, outline="#222222")
    ty = y + 10
    for line in lines:
        draw.text((x + 16, ty), line, font=font, fill=font_color)
        ty += line_h
    return img

def combine_panels(images, cols=2):
    gap = 16
    widths = [im.width for im in images]
    heights = [im.height for im in images]
    n = len(images)
    rows = (n + cols - 1) // cols
    col_w = []
    row_h = []
    for c in range(cols):
        col_w.append(max((images[i].width for i in range(n) if i % cols == c), default=0))
    for r in range(rows):
        row_h.append(max((images[i].height for i in range(n) if i // cols == r), default=0))
    canvas_w = sum(col_w) + gap * (cols + 1)
    canvas_h = sum(row_h) + gap * (rows + 1)
    canvas = Image.new("RGB", (canvas_w, canvas_h), "#111111")
    for i, im in enumerate(images):
        r, c = divmod(i, cols)
        x = gap + sum(col_w[:c]) + gap * c
        y = gap + sum(row_h[:r]) + gap * r
        canvas.paste(im, (x, y))
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
    st.session_state.layout = "縦に4つ"
if "scenes" not in st.session_state:
    st.session_state.scenes = ["", "", "", ""]
if "scene_chars" not in st.session_state:
    st.session_state.scene_chars = ["", "", "", ""]
if "panel_images" not in st.session_state:
    st.session_state.panel_images = [None, None, None, None]
if "panel_sizes" not in st.session_state:
    st.session_state.panel_sizes = [(1344, 768)] * 4
if "bubbles" not in st.session_state:
    st.session_state.bubbles = [
        {"text": "", "pos": "上左", "fill": "#ffffff", "color": "#111111", "size": 28, "kind": "丸四角"}
        for _ in range(4)
    ]
if "mode" not in st.session_state:
    st.session_state.mode = "chars"
if "error" not in st.session_state:
    st.session_state.error = ""
if "busy_index" not in st.session_state:
    st.session_state.busy_index = None

with st.sidebar:
    st.title("4コマ工房")
    if st.button("1. キャラを固定", use_container_width=True):
        st.session_state.mode = "chars"; st.rerun()
    if st.button("2. 4コマを作る", use_container_width=True):
        st.session_state.mode = "comic"; st.rerun()
    if st.button("3. 吹き出し", use_container_width=True):
        st.session_state.mode = "bubble"; st.rerun()
    st.caption("テスト用。登録なし。")

if st.session_state.error:
    st.error(st.session_state.error)

mode = st.session_state.mode

if mode == "chars":
    st.header("固定キャラ")
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
    layout = st.radio("並び", list(LAYOUTS.keys()), horizontal=True)
    st.session_state.layout = layout
    n = LAYOUTS[layout]["count"]
    st.session_state.panel_count = n
    names = [ch["name"] for ch in st.session_state.characters]

    st.markdown("### 全コマの基本サイズ")
    preset = st.radio("基本の形", list(ASPECT_PRESETS.keys()) + ["数字で指定"], horizontal=True)
    if preset != "数字で指定":
        bw, bh = ASPECT_PRESETS[preset]
    else:
        bw = st.number_input("基本の幅", 512, 2048, 1344, 64)
        bh = st.number_input("基本の高さ", 512, 2048, 768, 64)
    if st.button("このサイズを全コマにコピー"):
        for i in range(4):
            st.session_state.panel_sizes[i] = (int(bw), int(bh))
        st.rerun()

    if not names:
        st.warning("先にキャラを固定してください")
    else:
        for i in range(n):
            st.markdown(f"### コマ {i+1}")
            s1, s2, s3 = st.columns(3)
            with s1:
                shape = st.selectbox("このコマの形", list(ASPECT_PRESETS.keys()) + ["数字"], key=f"shape_{i}")
            if shape in ASPECT_PRESETS:
                st.session_state.panel_sizes[i] = ASPECT_PRESETS[shape]
                st.caption(f"{st.session_state.panel_sizes[i][0]} × {st.session_state.panel_sizes[i][1]}")
            else:
                with s2:
                    pw = st.number_input("幅", 512, 2048, st.session_state.panel_sizes[i][0], 64, key=f"pw_{i}")
                with s3:
                    ph = st.number_input("高さ", 512, 2048, st.session_state.panel_sizes[i][1], 64, key=f"ph_{i}")
                st.session_state.panel_sizes[i] = (int(pw), int(ph))

            st.session_state.scenes[i] = st.text_input("このコマの内容", value=st.session_state.scenes[i], key=f"sc_{i}")
            current = st.session_state.scene_chars[i] if st.session_state.scene_chars[i] in names else names[0]
            st.session_state.scene_chars[i] = st.selectbox("使う固定キャラ", names, index=names.index(current), key=f"ch_{i}")
            if st.session_state.panel_images[i]:
                st.image(st.session_state.panel_images[i], width=260)
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
        w, h = st.session_state.panel_sizes[i]
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
            "Manga comic panel, clean illustration, no speech bubbles, no text, no letters, no captions. "
            f"Character: {st.session_state.scene_chars[i]}. "
            f"Scene: {scene}. "
            "Keep the same face, hair, outfit, linework and coloring as the reference."
        )
        url = generate_panel(prompt, refs[:3], w, h)
        st.session_state.panel_images[i] = url

    busy = st.session_state.get("busy_index")
    if busy is not None:
        st.session_state.busy_index = None
        if not grok_key:
            st.session_state.error = "XAI_API_KEY がありません"
        else:
            try:
                if busy == "all":
                    with st.spinner("生成中..."):
                        for i in range(n):
                            if not st.session_state.panel_images[i]:
                                make_one(i)
                else:
                    with st.spinner(f"コマ{int(busy)+1}を生成中..."):
                        make_one(int(busy))
                st.session_state.error = ""
            except Exception as e:
                st.session_state.error = str(e)
        st.rerun()

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
                st.session_state.bubbles[i]["text"] = st.text_area("セリフ", value=st.session_state.bubbles[i]["text"], key=f"bt_{i}", height=70)
                st.session_state.bubbles[i]["kind"] = st.selectbox("吹き出しの種類", BUBBLE_TYPES, key=f"bk_{i}")
                st.session_state.bubbles[i]["pos"] = st.selectbox("位置", POSITIONS, key=f"bp_{i}")
                st.session_state.bubbles[i]["size"] = st.slider("文字サイズ", 16, 72, st.session_state.bubbles[i]["size"], key=f"bs_{i}")
                st.session_state.bubbles[i]["fill"] = st.color_picker("吹き出し色", st.session_state.bubbles[i]["fill"], key=f"bf_{i}")
                st.session_state.bubbles[i]["color"] = st.color_picker("文字色", st.session_state.bubbles[i]["color"], key=f"bc_{i}")
            raw = uri_to_image(st.session_state.panel_images[i])
            w, h = st.session_state.panel_sizes[i]
            raw = raw.resize((w, h))
            bub = st.session_state.bubbles[i]
            panels.append(draw_bubble(raw, bub["text"], bub["pos"], bub["fill"], bub["color"], bub["size"], bub["kind"]))
        comic = combine_panels(panels, cols=layout["cols"])
        st.image(comic, use_container_width=True)
        st.download_button("PNGで保存", data=image_to_bytes(comic), file_name="yonkoma.png", mime="image/png")
