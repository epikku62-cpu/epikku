import streamlit as st
import os
import json
import uuid
import base64
import math
import requests
from io import BytesIO
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(page_title="4コマ工房", page_icon="🎨", layout="wide")

grok_key = os.environ.get("XAI_API_KEY", "")
client = OpenAI(api_key=grok_key, base_url="https://api.x.ai/v1")
DATA_FILE = "studio_data.json"

LAYOUTS = {
    "縦4": {"cols": 1, "count": 4},
    "縦3": {"cols": 1, "count": 3},
    "縦2": {"cols": 1, "count": 2},
    "横4": {"cols": 4, "count": 4},
    "横3": {"cols": 3, "count": 3},
    "横2": {"cols": 2, "count": 2},
    "2×2": {"cols": 2, "count": 4},
}
ASPECTS = {
    "正方形（1024×1024）": (1024, 1024),
    "縦長（768×1344）": (768, 1344),
    "横長（1344×768）": (1344, 768),
}
BUBBLE_TYPES = ["丸四角", "楕円", "叫び", "考え", "文字だけ"]
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
        "urls": [
            "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/kosugimaru/KosugiMaru-Regular.ttf",
            "https://github.com/google/fonts/raw/main/ofl/kosugimaru/KosugiMaru-Regular.ttf",
        ],
    },
    "かわいい": {
        "file": "font_kawaii.ttf",
        "urls": [
            "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/hachimarupop/HachiMaruPop-Regular.ttf",
            "https://github.com/google/fonts/raw/main/ofl/hachimarupop/HachiMaruPop-Regular.ttf",
        ],
    },
    "手書き風": {
        "file": "font_te.ttf",
        "urls": [
            "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/yuseimagic/YuseiMagic-Regular.ttf",
            "https://github.com/google/fonts/raw/main/ofl/yuseimagic/YuseiMagic-Regular.ttf",
        ],
    },
}

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"characters": []}
    return {"characters": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
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
    ready = {}
    for name, spec in FONT_SPECS.items():
        ready[name] = download_one(spec["file"], spec["urls"])
    return ready

def load_font(size=28, kind="ゴシック"):
    size = max(12, int(size))
    spec = FONT_SPECS.get(kind) or FONT_SPECS["ゴシック"]
    path = spec["file"]
    if os.path.exists(path):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    if kind != "ゴシック" and os.path.exists(FONT_SPECS["ゴシック"]["file"]):
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

def ratio_from_size(w, h):
    r = w / max(h, 1)
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
            model="grok-imagine-image-2.0", prompt=prompt, n=1, extra_body=extra
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

def jagged_polygon(x, y, w, h, spikes=14):
    pts = []
    steps = spikes * 2
    for i in range(steps):
        ang = (math.pi * 2) * i / steps
        rx = w / 2 * (1.1 if i % 2 == 0 else 0.84)
        ry = h / 2 * (1.1 if i % 2 == 0 else 0.84)
        pts.append((x + w / 2 + math.cos(ang) * rx, y + h / 2 + math.sin(ang) * ry))
    return pts

def draw_bubble(panel_img, bub):
    text = (bub.get("text") or "").strip()
    if not text:
        return panel_img
    img = panel_img.convert("RGBA")
    size = int(bub.get("size", 28))
    font = load_font(size, bub.get("font", "ゴシック"))
    w, h = img.size
    kind = bub.get("kind", "丸四角")
    direction = bub.get("dir", "横書き")
    fill = bub.get("fill", "#ffffff")
    color = bub.get("color", "#111111")
    pad = 16
    max_w = int(w * 0.55)
    if direction == "縦書き":
        chars = list(text.replace("\n", ""))
        line_h = int(size * 1.15)
        box_w = size + pad * 2
        box_h = pad * 2 + line_h * len(chars)
        lines = chars
    else:
        lines = wrap_text(text, font, max_w)
        line_h = int(size * 1.3)
        try:
            text_w = max(font.getlength(x) for x in lines)
        except Exception:
            text_w = max(len(x) * size for x in lines)
        box_w = int(text_w + pad * 2)
        box_h = int(pad * 2 + line_h * len(lines))
    layer = Image.new("RGBA", (box_w + 40, box_h + 40), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x0, y0 = 20, 20
    if kind == "丸四角":
        draw.rounded_rectangle([x0, y0, x0 + box_w, y0 + box_h], radius=16, fill=fill, outline="#222222", width=3)
    elif kind == "楕円":
        draw.ellipse([x0, y0, x0 + box_w, y0 + box_h + 6], fill=fill, outline="#222222", width=3)
    elif kind == "叫び":
        draw.polygon(jagged_polygon(x0 - 4, y0 - 4, box_w + 8, box_h + 8), fill=fill, outline="#222222")
    elif kind == "考え":
        draw.rounded_rectangle([x0, y0, x0 + box_w, y0 + box_h], radius=26, fill=fill, outline="#222222", width=3)
    if direction == "縦書き":
        cy = y0 + pad
        for ch in lines:
            try:
                tw = font.getlength(ch)
            except Exception:
                tw = size
            draw.text((x0 + (box_w - tw) / 2, cy), ch, font=font, fill=color)
            cy += int(size * 1.15)
    else:
        ty = y0 + pad - 2
        for line in lines:
            draw.text((x0 + pad, ty), line, font=font, fill=color)
            ty += int(size * 1.3)
    angle = int(bub.get("angle", 0))
    if angle:
        layer = layer.rotate(-angle, expand=True, resample=Image.BICUBIC)
    px = int(w * float(bub.get("x", 8)) / 100)
    py = int(h * float(bub.get("y", 8)) / 100)
    img.alpha_composite(layer, (max(0, min(w - layer.width, px)), max(0, min(h - layer.height, py))))
    return img.convert("RGB")

def combine_panels(images, cols=2):
    gap = 16
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

font_ready = prepare_fonts()
usable_fonts = [k for k, ok in font_ready.items() if ok] or ["ゴシック"]

if "characters" not in st.session_state:
    st.session_state.characters = load_data().get("characters", [])
if "layout" not in st.session_state:
    st.session_state.layout = "縦4"
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
        {"text": "", "x": 6, "y": 6, "angle": 0, "fill": "#ffffff", "color": "#111111",
         "size": 28, "kind": "丸四角", "font": "ゴシック", "dir": "横書き"}
        for _ in range(4)
    ]
if "mode" not in st.session_state:
    st.session_state.mode = "make"
if "error" not in st.session_state:
    st.session_state.error = ""
if "busy_index" not in st.session_state:
    st.session_state.busy_index = None
if "combined" not in st.session_state:
    st.session_state.combined = None

done = sum(1 for x in st.session_state.panel_images if x)
need = LAYOUTS[st.session_state.layout]["count"]

with st.sidebar:
    st.markdown("## 4コマ工房")
    st.markdown("**使い方**")
    st.markdown("1. セットを保存\n2. コマを1つずつ作る\n3. セリフを付ける\n4. 下で1枚にまとめる")
    st.progress(min(done / max(need, 1), 1.0))
    st.caption(f"できたコマ {done} / {need}")
    if st.button("① セット保存", use_container_width=True):
        st.session_state.mode = "chars"; st.rerun()
    if st.button("② 4コマを作る", use_container_width=True):
        st.session_state.mode = "make"; st.rerun()
    st.caption("使える文字: " + " / ".join(usable_fonts))

if st.session_state.error:
    st.error(st.session_state.error)

if st.session_state.mode == "chars":
    st.header("① セット保存")
    st.write("4コマで使う顔や絵柄を、ここで先に登録します。保存名はメモです。絵の中には出ません。")
    save_name = st.text_input("保存名（任意）", placeholder="例: 赤ずきん")
    use_type = st.radio("何を保存する？", ["キャラだけ", "絵柄だけ", "キャラ＋絵柄"], horizontal=True)
    char_files, style_files, char_strengths, style_strengths = [], [], [], []
    if use_type != "絵柄だけ":
        char_files = st.file_uploader("キャラの画像（最大3）", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="char_ups")
        for i, f in enumerate((char_files or [])[:3]):
            st.image(f, width=120)
            char_strengths.append(st.slider(f"キャラ{i+1}の強度", 1, 10, 8, key=f"cs_{i}"))
    if use_type != "キャラだけ":
        style_files = st.file_uploader("絵柄の画像（最大3）", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="style_ups")
        for i, f in enumerate((style_files or [])[:3]):
            st.image(f, width=120)
            style_strengths.append(st.slider(f"絵柄{i+1}の強度", 1, 10, 8, key=f"ss_{i}"))
    if st.button("セットを保存する", type="primary"):
        chars = [{"uri": uploaded_to_uri(f), "strength": char_strengths[i]} for i, f in enumerate((char_files or [])[:3])]
        styles = [{"uri": uploaded_to_uri(f), "strength": style_strengths[i]} for i, f in enumerate((style_files or [])[:3])]
        if not chars and not styles:
            st.warning("画像を1枚以上入れてください")
        else:
            st.session_state.characters.append({
                "id": str(uuid.uuid4())[:8],
                "save_name": save_name.strip() or f"セット{len(st.session_state.characters)+1}",
                "kind": use_type,
                "chars": chars,
                "styles": styles,
            })
            save_data({"characters": st.session_state.characters})
            st.success("保存しました。左の「② 4コマを作る」を押してください。")
    st.markdown("### 保存済み")
    if not st.session_state.characters:
        st.info("まだありません")
    else:
        for i, ch in enumerate(st.session_state.characters):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.write(f"**{char_label(ch)}**")
            with c2:
                if st.button("削除", key=f"delc_{i}"):
                    st.session_state.characters.pop(i)
                    save_data({"characters": st.session_state.characters})
                    st.rerun()

else:
    st.header("② 4コマを作る")
    st.write("上から順に、コマを作ってください。セリフもこの画面で付けます。全部できたら一番下でまとめます。")
    layout = st.radio("並べ方", list(LAYOUTS.keys()), horizontal=True)
    st.session_state.layout = layout
    n = LAYOUTS[layout]["count"]
    names = [char_label(ch) for ch in st.session_state.characters]
    preset = st.radio("コマの大きさ", list(ASPECTS.keys()) + ["数字で指定"], horizontal=True)
    if preset in ASPECTS:
        bw, bh = ASPECTS[preset]
        st.caption(f"{bw} × {bh}")
    else:
        a, b = st.columns(2)
        with a:
            bw = st.number_input("幅", 512, 2048, 1024, 64, key="base_w")
        with b:
            bh = st.number_input("高さ", 512, 2048, 1024, 64, key="base_h")
    if st.button("この大きさを全部のコマに使う"):
        st.session_state.panel_sizes = [(int(bw), int(bh))] * 4
        st.rerun()

    def set_by_name(name):
        for ch in st.session_state.characters:
            if char_label(ch) == name:
                return ch
        return None

    def make_one(i):
        scene = st.session_state.scenes[i].strip()
        if not scene:
            raise Exception(f"コマ{i+1}の内容が空です")
        w, h = st.session_state.panel_sizes[i]
        pack = set_by_name(st.session_state.scene_chars[i]) or {}
        refs, extra = [], []
        if i > 0 and st.session_state.panel_images[0]:
            refs.append(st.session_state.panel_images[0])
        for item in normalize_refs(pack.get("chars")):
            refs.append(item["uri"])
            extra.append(f"CHARACTER REFERENCE strength {item['strength']}/10.")
        for item in normalize_refs(pack.get("styles")):
            refs.append(item["uri"])
            extra.append(f"STYLE REFERENCE strength {item['strength']}/10.")
        prompt = "Manga panel, no text, no speech bubbles. Scene: " + scene + " " + " ".join(extra)
        st.session_state.panel_images[i] = generate_panel(prompt, refs[:3], w, h)

    if not names:
        st.warning("まだセットがありません。左の「① セット保存」から画像を登録してください。")
    else:
        for i in range(n):
            with st.expander(f"コマ {i+1}　{'完成' if st.session_state.panel_images[i] else '未作成'}", expanded=not st.session_state.panel_images[i]):
                st.session_state.scenes[i] = st.text_input("このコマで何が起きる？", value=st.session_state.scenes[i], key=f"sc_{i}")
                current = st.session_state.scene_chars[i] if st.session_state.scene_chars[i] in names else names[0]
                st.session_state.scene_chars[i] = st.selectbox("使うセット", names, index=names.index(current), key=f"ch_{i}")
                shape = st.selectbox("このコマの大きさ", list(ASPECTS.keys()) + ["数字で指定"], key=f"shape_{i}")
                if shape in ASPECTS:
                    st.session_state.panel_sizes[i] = ASPECTS[shape]
                else:
                    c1, c2 = st.columns(2)
                    with c1:
                        pw = st.number_input("幅", 512, 2048, st.session_state.panel_sizes[i][0], 64, key=f"pw_{i}")
                    with c2:
                        ph = st.number_input("高さ", 512, 2048, st.session_state.panel_sizes[i][1], 64, key=f"ph_{i}")
                    st.session_state.panel_sizes[i] = (int(pw), int(ph))
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("このコマを生成", key=f"gen_{i}", type="primary"):
                        st.session_state.busy_index = i
                        st.rerun()
                with b2:
                    if st.button("このコマを消す", key=f"clr_{i}"):
                        st.session_state.panel_images[i] = None
                        st.rerun()
                if st.session_state.panel_images[i]:
                    bub = st.session_state.bubbles[i]
                    st.markdown("**セリフ**")
                    bub["text"] = st.text_input("文字", value=bub.get("text", ""), key=f"bt_{i}")
                    bub["font"] = st.selectbox("フォント", usable_fonts, key=f"bfn_{i}")
                    bub["kind"] = st.selectbox("吹き出しの形", BUBBLE_TYPES, key=f"bk_{i}")
                    bub["dir"] = st.selectbox("横書き / 縦書き", TEXT_DIR, key=f"bd_{i}")
                    bub["size"] = st.slider("文字の大きさ", 16, 64, int(bub.get("size", 28)), key=f"bs_{i}")
                    bub["x"] = st.slider("左右", 0, 80, int(bub.get("x", 6)), key=f"bx_{i}")
                    bub["y"] = st.slider("上下", 0, 80, int(bub.get("y", 6)), key=f"by_{i}")
                    bub["angle"] = st.slider("傾き", -45, 45, int(bub.get("angle", 0)), key=f"ba_{i}")
                    bub["fill"] = st.color_picker("吹き出し色", bub.get("fill", "#ffffff"), key=f"bf_{i}")
                    bub["color"] = st.color_picker("文字色", bub.get("color", "#111111"), key=f"bc_{i}")
                    raw = uri_to_image(st.session_state.panel_images[i]).resize(st.session_state.panel_sizes[i])
                    st.image(draw_bubble(raw, bub), width=320)
                    st.session_state.bubbles[i] = bub

    busy = st.session_state.get("busy_index")
    if busy is not None:
        st.session_state.busy_index = None
        if not grok_key:
            st.session_state.error = "XAI_API_KEY がありません"
        else:
            try:
                with st.spinner(f"コマ{int(busy)+1}を作っています..."):
                    make_one(int(busy))
                st.session_state.error = ""
            except Exception as e:
                st.session_state.error = str(e)
        st.rerun()

    st.markdown("---")
    st.header("③ 1枚にまとめる")
    st.write("コマが全部できたら、ここを押します。")
    if st.button("まとめて完成画像にする", type="primary"):
        panels = []
        for i in range(n):
            if not st.session_state.panel_images[i]:
                st.error(f"コマ{i+1}がまだありません")
                panels = None
                break
            raw = uri_to_image(st.session_state.panel_images[i]).resize(st.session_state.panel_sizes[i])
            panels.append(draw_bubble(raw, st.session_state.bubbles[i]))
        if panels:
            st.session_state.combined = combine_panels(panels, cols=LAYOUTS[layout]["cols"])
            st.rerun()
    if st.session_state.combined is not None:
        st.image(st.session_state.combined, use_container_width=True)
        st.download_button("PNGを保存", data=image_to_bytes(st.session_state.combined), file_name="yonkoma.png", mime="image/png")
