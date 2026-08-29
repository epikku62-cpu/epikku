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
FONT_SANS = "NotoSansJP-Regular.otf"
FONT_SERIF = "NotoSerifJP-Regular.otf"

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
POSITIONS = ["上左", "上中央", "上右", "中左", "中右", "下左", "下中央", "下右"]
BUBBLE_TYPES = ["丸四角", "楕円", "叫び", "考え", "文字だけ"]
TEXT_DIR = ["横書き", "縦書き", "斜め"]
FONTS = ["ゴシック", "明朝"]

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

def download_font(path, urls):
    if os.path.exists(path) and os.path.getsize(path) > 10000:
        return path
    for url in urls:
        try:
            r = requests.get(url, timeout=60)
            if r.status_code == 200 and len(r.content) > 10000:
                with open(path, "wb") as f:
                    f.write(r.content)
                return path
        except Exception:
            pass
    return None

def ensure_fonts():
    download_font(FONT_SANS, [
        "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf",
    ])
    download_font(FONT_SERIF, [
        "https://github.com/googlefonts/noto-cjk/raw/main/Serif/OTF/Japanese/NotoSerifCJKjp-Regular.otf",
    ])

def load_font(size=28, kind="ゴシック"):
    ensure_fonts()
    path = FONT_SERIF if kind == "明朝" and os.path.exists(FONT_SERIF) else FONT_SANS
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
        if font.getlength(test) <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = ch
    if line:
        lines.append(line)
    return lines or [""]

def bubble_xy(pos, img_w, img_h, box_w, box_h):
    pad = 16
    return {
        "上左": (pad, pad),
        "上中央": ((img_w - box_w) // 2, pad),
        "上右": (img_w - box_w - pad, pad),
        "中左": (pad, (img_h - box_h) // 2),
        "中右": (img_w - box_w - pad, (img_h - box_h) // 2),
        "下左": (pad, img_h - box_h - pad),
        "下中央": ((img_w - box_w) // 2, img_h - box_h - pad),
        "下右": (img_w - box_w - pad, img_h - box_h - pad),
    }.get(pos, (pad, pad))

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
    img = panel_img.copy()
    draw = ImageDraw.Draw(img)
    size = int(bub.get("size", 28))
    font = load_font(size, bub.get("font", "ゴシック"))
    w, h = img.size
    kind = bub.get("kind", "丸四角")
    direction = bub.get("dir", "横書き")
    fill = bub.get("fill", "#ffffff")
    color = bub.get("color", "#111111")
    pad = 18

    if direction == "縦書き":
        chars = list(text.replace("\n", ""))
        line_h = int(size * 1.15)
        box_w = min(w - 20, size + pad * 2)
        box_h = min(h - 20, pad * 2 + line_h * len(chars))
        x, y = bubble_xy(bub.get("pos", "上左"), w, h, box_w, box_h)
        if kind != "文字だけ":
            draw.rounded_rectangle([x, y, x + box_w, y + box_h], radius=16, fill=fill, outline="#222", width=3)
        cy = y + pad
        for ch in chars:
            tw = font.getlength(ch)
            draw.text((x + (box_w - tw) / 2, cy), ch, font=font, fill=color)
            cy += line_h
        return img

    max_w = int(w * 0.62)
    lines = wrap_text(text, font, max_w)
    line_h = int(size * 1.3)
    text_w = max(font.getlength(x) for x in lines)
    box_w = int(min(w - 24, text_w + pad * 2))
    box_h = int(min(h - 24, pad * 2 + line_h * len(lines)))
    x, y = bubble_xy(bub.get("pos", "上左"), w, h, box_w, box_h)
    if kind == "丸四角":
        draw.rounded_rectangle([x, y, x + box_w, y + box_h], radius=16, fill=fill, outline="#222", width=3)
    elif kind == "楕円":
        draw.ellipse([x, y, x + box_w, y + box_h + 8], fill=fill, outline="#222", width=3)
    elif kind == "叫び":
        draw.polygon(jagged_polygon(x - 6, y - 6, box_w + 12, box_h + 12), fill=fill, outline="#222")
    elif kind == "考え":
        draw.rounded_rectangle([x, y, x + box_w, y + box_h], radius=28, fill=fill, outline="#222", width=3)
    if direction == "斜め":
        tmp = Image.new("RGBA", (box_w + 40, box_h + 40), (0, 0, 0, 0))
        td = ImageDraw.Draw(tmp)
        ty = 10
        for line in lines:
            td.text((10, ty), line, font=font, fill=color)
            ty += line_h
        tmp = tmp.rotate(-18, expand=True, resample=Image.BICUBIC)
        img.paste(tmp, (x - 8, y - 8), tmp)
    else:
        ty = y + pad - 4
        for line in lines:
            draw.text((x + pad, ty), line, font=font, fill=color)
            ty += line_h
    return img

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
        x = gap + sum(col_w[:c]) + gap * c
        y = gap + sum(row_h[:r]) + gap * r
        canvas.paste(im, (x, y))
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
        if isinstance(x, dict):
            out.append({"uri": x.get("uri", ""), "strength": int(x.get("strength", 8))})
        elif isinstance(x, str):
            out.append({"uri": x, "strength": 8})
    return [x for x in out if x.get("uri")]

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
        {"text": "", "pos": "上左", "fill": "#ffffff", "color": "#111111", "size": 28, "kind": "丸四角", "font": "ゴシック", "dir": "横書き"}
        for _ in range(4)
    ]
if "mode" not in st.session_state:
    st.session_state.mode = "chars"
if "error" not in st.session_state:
    st.session_state.error = ""
if "busy_index" not in st.session_state:
    st.session_state.busy_index = None
if "combined" not in st.session_state:
    st.session_state.combined = None

with st.sidebar:
    st.title("4コマ工房")
    if st.button("1. キャラを固定", use_container_width=True):
        st.session_state.mode = "chars"; st.rerun()
    if st.button("2. 4コマを作る", use_container_width=True):
        st.session_state.mode = "comic"; st.rerun()
    if st.button("3. 吹き出し", use_container_width=True):
        st.session_state.mode = "bubble"; st.rerun()

if st.session_state.error:
    st.error(st.session_state.error)

mode = st.session_state.mode

if mode == "chars":
    st.header("固定セット")
    st.caption("保存名は一覧用です。生成の文章には使いません。キャラだけ、絵柄だけ、両方、どれでも保存できます。")
    save_name = st.text_input("保存名（任意）", placeholder="例: 赤ずきんセット")
    use_type = st.radio("このセットの種類", ["キャラだけ", "絵柄だけ", "キャラ＋絵柄"], horizontal=True)

    char_files = []
    style_files = []
    char_strengths = []
    style_strengths = []

    if use_type in ["キャラだけ", "キャラ＋絵柄"]:
        char_files = st.file_uploader("キャラ参照（最大3）", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="char_ups")
        for i, f in enumerate((char_files or [])[:3]):
            st.image(f, width=140)
            char_strengths.append(st.slider(f"キャラ参照{i+1}の強度", 1, 10, 8, key=f"cs_{i}"))

    if use_type in ["絵柄だけ", "キャラ＋絵柄"]:
        style_files = st.file_uploader("絵柄参照（最大3）", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="style_ups")
        for i, f in enumerate((style_files or [])[:3]):
            st.image(f, width=140)
            style_strengths.append(st.slider(f"絵柄参照{i+1}の強度", 1, 10, 8, key=f"ss_{i}"))

    if st.button("このセットを保存する", type="primary"):
        chars = [{"uri": uploaded_to_uri(f), "strength": char_strengths[i]} for i, f in enumerate((char_files or [])[:3])]
        styles = [{"uri": uploaded_to_uri(f), "strength": style_strengths[i]} for i, f in enumerate((style_files or [])[:3])]
        if use_type == "キャラだけ" and not chars:
            st.warning("キャラ参照を1枚以上入れてください")
        elif use_type == "絵柄だけ" and not styles:
            st.warning("絵柄参照を1枚以上入れてください")
        elif use_type == "キャラ＋絵柄" and (not chars or not styles):
            st.warning("キャラ参照と絵柄参照の両方を入れてください")
        else:
            item = {
                "id": str(uuid.uuid4())[:8],
                "save_name": save_name.strip() or f"セット{len(st.session_state.characters)+1}",
                "kind": use_type,
                "chars": chars,
                "styles": styles,
            }
            st.session_state.characters.append(item)
            save_data({"characters": st.session_state.characters})
            st.success("保存しました")
            st.rerun()

    st.markdown("### 保存済み")
    if not st.session_state.characters:
        st.info("まだありません")
    else:
        for i, ch in enumerate(st.session_state.characters):
            cols = st.columns([4, 1])
            with cols[0]:
                st.write(f"**{char_label(ch)}**　({ch.get('kind', 'セット')})")
                thumbs = normalize_refs(ch.get("chars")) + normalize_refs(ch.get("styles"))
                if thumbs:
                    st.image(thumbs[0]["uri"], width=140)
            with cols[1]:
                if st.button("削除", key=f"delc_{i}"):
                    st.session_state.characters.pop(i)
                    save_data({"characters": st.session_state.characters})
                    st.rerun()

elif mode == "comic":
    st.header("4コマを作る")
    layout = st.radio("並び", list(LAYOUTS.keys()), horizontal=True)
    st.session_state.layout = layout
    n = LAYOUTS[layout]["count"]
    names = [char_label(ch) for ch in st.session_state.characters]

    st.markdown("### コマサイズ")
    preset = st.radio("基本の形", list(ASPECTS.keys()) + ["数字で指定"], horizontal=True)
    if preset in ASPECTS:
        bw, bh = ASPECTS[preset]
        st.caption(f"{bw} × {bh}")
    else:
        a, b = st.columns(2)
        with a:
            bw = st.number_input("幅", 512, 2048, 1024, 64, key="base_w")
        with b:
            bh = st.number_input("高さ", 512, 2048, 1024, 64, key="base_h")
        st.caption(f"{int(bw)} × {int(bh)}")
    if st.button("このサイズを全コマにコピー", type="primary"):
        size = (int(bw), int(bh))
        st.session_state.panel_sizes = [size, size, size, size]
        st.success(f"全コマを {size[0]}×{size[1]} にしました")
        st.rerun()

    if not names:
        st.warning("先にセットを保存してください")
    else:
        for i in range(n):
            st.markdown(f"---\n### コマ {i+1}　今のサイズ {st.session_state.panel_sizes[i][0]}×{st.session_state.panel_sizes[i][1]}")
            shape = st.selectbox("このコマの形", list(ASPECTS.keys()) + ["数字で指定"], key=f"shape_{i}")
            if shape in ASPECTS:
                st.session_state.panel_sizes[i] = ASPECTS[shape]
                st.caption(f"{ASPECTS[shape][0]} × {ASPECTS[shape][1]}")
            else:
                c1, c2 = st.columns(2)
                with c1:
                    pw = st.number_input("幅", 512, 2048, st.session_state.panel_sizes[i][0], 64, key=f"pw_{i}")
                with c2:
                    ph = st.number_input("高さ", 512, 2048, st.session_state.panel_sizes[i][1], 64, key=f"ph_{i}")
                st.session_state.panel_sizes[i] = (int(pw), int(ph))

            st.session_state.scenes[i] = st.text_input("このコマの内容", value=st.session_state.scenes[i], key=f"sc_{i}")
            current = st.session_state.scene_chars[i] if st.session_state.scene_chars[i] in names else names[0]
            st.session_state.scene_chars[i] = st.selectbox("使うセット", names, index=names.index(current), key=f"ch_{i}")
            b1, b2 = st.columns(2)
            with b1:
                if st.button(f"コマ{i+1}を生成", key=f"gen_{i}", type="primary"):
                    st.session_state.busy_index = i
                    st.rerun()
            with b2:
                if st.button(f"コマ{i+1}だけ消す", key=f"clr_{i}"):
                    st.session_state.panel_images[i] = None
                    st.rerun()
            if st.session_state.panel_images[i]:
                st.image(st.session_state.panel_images[i], width=280)

        if st.button("空いているコマをまとめて生成"):
            st.session_state.busy_index = "all"
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
        chars = normalize_refs(pack.get("chars"))
        styles = normalize_refs(pack.get("styles"))
        refs = []
        extra = []
        if i > 0 and st.session_state.panel_images[0]:
            refs.append(st.session_state.panel_images[0])
            extra.append("Use panel 1 as consistency reference.")
        for item in chars:
            refs.append(item["uri"])
            extra.append(f"CHARACTER REFERENCE strength {item['strength']}/10: keep identity, face, hair, outfit.")
        for item in styles:
            refs.append(item["uri"])
            extra.append(f"STYLE REFERENCE strength {item['strength']}/10: use only art style, not the character unless also a character ref.")
        prompt = (
            "Manga comic panel, clean illustration, no speech bubbles, no text, no letters. "
            f"Scene: {scene}. " + " ".join(extra)
        )
        st.session_state.panel_images[i] = generate_panel(prompt, refs[:3], w, h)

    busy = st.session_state.get("busy_index")
    if busy is not None:
        st.session_state.busy_index = None
        if not grok_key:
            st.session_state.error = "XAI_API_KEY がありません"
        else:
            try:
                nnow = LAYOUTS[st.session_state.layout]["count"]
                if busy == "all":
                    with st.spinner("生成中..."):
                        for i in range(nnow):
                            if not st.session_state.panel_images[i]:
                                make_one(i)
                else:
                    with st.spinner(f"コマ{int(busy)+1}を生成中..."):
                        make_one(int(busy))
                st.session_state.error = ""
            except Exception as e:
                st.session_state.error = str(e)
        st.rerun()

elif mode == "bubble":
    st.header("吹き出し")
    n = LAYOUTS[st.session_state.layout]["count"]
    if not any(st.session_state.panel_images[:n]):
        st.warning("先にコマを作ってください")
    else:
        for i in range(n):
            if not st.session_state.panel_images[i]:
                st.markdown(f"### コマ {i+1} は未生成")
                continue
            st.markdown(f"### コマ {i+1}")
            bub = st.session_state.bubbles[i]
            bub["text"] = st.text_area("セリフ", value=bub["text"], key=f"bt_{i}", height=70)
            a, b = st.columns(2)
            with a:
                bub["kind"] = st.selectbox("吹き出し", BUBBLE_TYPES, key=f"bk_{i}")
                bub["pos"] = st.selectbox("位置", POSITIONS, key=f"bp_{i}")
                bub["dir"] = st.selectbox("向き", TEXT_DIR, key=f"bd_{i}")
            with b:
                bub["font"] = st.selectbox("フォント", FONTS, key=f"bfn_{i}")
                bub["size"] = st.slider("文字サイズ", 16, 64, bub["size"], key=f"bs_{i}")
                bub["fill"] = st.color_picker("吹き出し色", bub["fill"], key=f"bf_{i}")
                bub["color"] = st.color_picker("文字色", bub["color"], key=f"bc_{i}")
            raw = uri_to_image(st.session_state.panel_images[i]).resize(st.session_state.panel_sizes[i])
            st.image(draw_bubble(raw, bub), width=360)
            st.session_state.bubbles[i] = bub

        if st.button("4コマにまとめる", type="primary"):
            panels = []
            for i in range(n):
                if not st.session_state.panel_images[i]:
                    st.error(f"コマ{i+1}がありません")
                    panels = None
                    break
                raw = uri_to_image(st.session_state.panel_images[i]).resize(st.session_state.panel_sizes[i])
                panels.append(draw_bubble(raw, st.session_state.bubbles[i]))
            if panels:
                st.session_state.combined = combine_panels(panels, cols=LAYOUTS[st.session_state.layout]["cols"])
                st.rerun()
        if st.session_state.combined is not None:
            st.markdown("### 完成")
            st.image(st.session_state.combined, use_container_width=True)
            st.download_button("PNGで保存", data=image_to_bytes(st.session_state.combined), file_name="yonkoma.png", mime="image/png")
