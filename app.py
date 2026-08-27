import streamlit as st
import os
import json
import hashlib
import base64
import requests
from openai import OpenAI
from datetime import datetime
from PIL import Image
import io

st.set_page_config(page_title="AI育成お絵描きサイト", page_icon="🎨", layout="wide")

USERS_FILE = "users_data.json"
grok_key = os.environ.get("XAI_API_KEY", "")

client = OpenAI(
    api_key=grok_key,
    base_url="https://api.x.ai/v1",
)

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
            "image_count": st.session_state.get("image_count", 0),
            "messages": st.session_state.get("messages", [])[-40:],
            "points": st.session_state.get("points", 0),
            "is_premium": st.session_state.get("is_premium", False),
            "ad_count": st.session_state.get("ad_count", 0),
            "generated_history": st.session_state.get("generated_history", [])[-30:],
            "user_icon": st.session_state.get("user_icon", "👤"),
            "ai_icon": st.session_state.get("ai_icon", "👤"),
            "last_login": datetime.now().isoformat()
        }
        save_users(users)

def file_to_data_uri(uploaded_file):
    raw = uploaded_file.getvalue()
    mime = uploaded_file.type or "image/png"
    b64 = base64.b64encode(raw).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def generate_text_image(prompt, model_name, aspect_ratio, resolution):
    response = client.images.generate(
        model=model_name,
        prompt=prompt,
        n=1,
        extra_body={
            "aspect_ratio": aspect_ratio,
            "resolution": resolution
        }
    )
    return response.data[0].url

def generate_with_references(prompt, model_name, aspect_ratio, resolution, image_uris):
    payload = {
        "model": model_name,
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "response_format": "url"
    }
    if len(image_uris) == 1:
        payload["image"] = {"url": image_uris[0], "type": "image_url"}
    else:
        payload["images"] = [{"url": uri, "type": "image_url"} for uri in image_uris[:3]]

    res = requests.post(
        "https://api.x.ai/v1/images/edits",
        headers={
            "Authorization": f"Bearer {grok_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=180
    )
    data = res.json()
    if res.status_code != 200:
        raise Exception(data)
    return data["data"][0]["url"]

def update_personality():
    if len(st.session_state.messages) < 8:
        return
    recent = st.session_state.messages[-6:]
    conversation_text = "\n".join([f"{m['role']}: {m['content']}" for m in recent])
    prompt = f"会話を見て性格を1つ選んで。選択肢: 甘えん坊, ツンデレ, ヤンデレ, ヤンキー, 姫, 王子, 明るいキャラ, 口数少ないキャラ, 中立\n\n{conversation_text}\n単語だけ。"
    try:
        completion = client.chat.completions.create(
            model="grok-4-fast",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=15
        )
        new_type = completion.choices[0].message.content.strip()
        if new_type in CHARACTER_PROMPTS and new_type != st.session_state.ai_type:
            st.session_state.ai_type = new_type
    except:
        pass

def extract_preferences_from_conversation():
    if len(st.session_state.messages) < 6:
        return
    recent = st.session_state.messages[-10:]
    conversation_text = "\n".join([f"{m['role']}: {m['content']}" for m in recent])
    prompt = f"会話から絵やキャラの好みだけ短いフレーズで。なければなし。\n{conversation_text}"
    try:
        completion = client.chat.completions.create(
            model="grok-4-fast",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80
        )
        result = completion.choices[0].message.content.strip()
        if result and result != "なし" and result not in st.session_state.learned_preferences:
            st.session_state.learned_preferences.append(result)
            st.session_state.learned_preferences = st.session_state.learned_preferences[-15:]
    except:
        pass

def analyze_image_style(uploaded_file):
    try:
        image = Image.open(uploaded_file)
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode()
        completion = client.chat.completions.create(
            model="grok-4-fast",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "この絵のタッチ、塗り、線、雰囲気を短い日本語1文で。"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
                ]
            }],
            max_tokens=80
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        return f"分析失敗（{e}）"

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = None
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

if not st.session_state.logged_in:
    st.title("🎨 専属絵師AI 育成ルーム")
    tab1, tab2 = st.tabs(["ログイン", "新規登録"])
    with tab1:
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
                    "image_count": 0, "messages": [], "points": 0, "is_premium": False,
                    "ad_count": 0, "generated_history": [], "user_icon": "👤", "ai_icon": "👤"
                }
                for k, v in defaults.items():
                    st.session_state[k] = data.get(k, v)
                st.session_state.current_mode = "chat"
                st.rerun()
            else:
                st.error("ユーザー名またはパスワードが違います")
    with tab2:
        reg_user = st.text_input("新しいユーザー名", key="reg_user")
        reg_pass = st.text_input("パスワード", type="password", key="reg_pass")
        reg_pass2 = st.text_input("パスワード（確認）", type="password", key="reg_pass2")
        if st.button("新規登録", type="primary"):
            if not reg_user or not reg_pass:
                st.warning("入力してください")
            elif reg_pass != reg_pass2:
                st.error("パスワードが一致しません")
            else:
                users = load_users()
                users[reg_user] = {"password": hash_password(reg_pass), "data": {}}
                save_users(users)
                st.session_state.logged_in = True
                st.session_state.username = reg_user
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
                st.session_state.ad_count = 0
                st.session_state.generated_history = []
                st.session_state.user_icon = "👤"
                st.session_state.ai_icon = "👤"
                st.session_state.current_mode = "chat"
                st.rerun()
    st.stop()

st.title("🎨 専属絵師AI 育成ルーム")

if st.session_state.ai_name is None:
    input_name = st.text_input("AIの名前")
    gender = st.radio("性別", ["おんなのこ", "おとこのこ"], horizontal=True)
    if st.button("この設定で開始する！", type="primary") and input_name.strip():
        st.session_state.ai_name = input_name.strip()
        st.session_state.ai_gender = gender
        st.session_state.messages = [{
            "role": "assistant",
            "content": f"はじめまして！わたしは「{input_name.strip()}」だよ。好きな絵柄やキャラを教えてね。"
        }]
        save_current_user_data()
        st.rerun()
else:
    with st.sidebar:
        st.write(f"**{st.session_state.username}**")
        st.write(f"ポイント: {st.session_state.points} pt")
        st.write(f"レベル: Lv.{st.session_state.level}")
        if st.button("💬 トークルーム", use_container_width=True):
            st.session_state.current_mode = "chat"; st.rerun()
        if st.button("🖼️ 学習モード", use_container_width=True):
            st.session_state.current_mode = "learn"; st.rerun()
        if st.button("🎨 画像生成モード", use_container_width=True):
            st.session_state.current_mode = "generate"; st.rerun()
        if st.button("📂 生成履歴", use_container_width=True):
            st.session_state.current_mode = "history"; st.rerun()
        if st.button("ログアウト"):
            save_current_user_data()
            st.session_state.logged_in = False
            st.rerun()

    mode = st.session_state.current_mode

    if mode == "chat":
        st.subheader(f"💬 {st.session_state.ai_name}")
        for msg in st.session_state.messages:
            role = msg["role"]
            with st.chat_message(role, avatar=st.session_state.user_icon if role == "user" else st.session_state.ai_icon):
                st.write(msg["content"])
                if "image" in msg:
                    st.image(msg["image"], use_container_width=True)
        if user_message := st.chat_input("メッセージを送る..."):
            st.session_state.messages.append({"role": "user", "content": user_message})
            st.session_state.exp += 1
            if st.session_state.level < 4 and st.session_state.exp >= 5:
                st.session_state.level += 1
                st.session_state.exp = 0
                if st.session_state.level == 4:
                    st.session_state.points += 80
            elif st.session_state.level >= 4 and st.session_state.exp >= 20:
                st.session_state.level += 1
                st.session_state.exp = 0
                st.session_state.points += 5
            base = CHARACTER_PROMPTS.get(st.session_state.ai_type, CHARACTER_PROMPTS["中立"])
            system_prompt = f"あなたは{st.session_state.ai_name}。{base}同じ質問を繰り返さない。短く自然に。"
            api_messages = [{"role": "system", "content": system_prompt}] + [
                {"role": m["role"], "content": m["content"]} for m in st.session_state.messages[-8:]
            ]
            try:
                with st.spinner("考え中..."):
                    completion = client.chat.completions.create(model="grok-4-fast", messages=api_messages, max_tokens=220)
                st.session_state.messages.append({"role": "assistant", "content": completion.choices[0].message.content})
                if len(st.session_state.messages) % 5 == 0:
                    extract_preferences_from_conversation()
                    update_personality()
            except Exception as e:
                st.session_state.messages.append({"role": "assistant", "content": f"（エラー: {e}）"})
            save_current_user_data()
            st.rerun()

    elif mode == "learn":
        st.subheader("🖼️ 学習モード")
        if st.session_state.level < 3:
            st.warning("レベル3で解放")
        else:
            uploaded_file = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"], key="learn_upload")
            if uploaded_file and st.button("この画像を学習させる", type="primary"):
                desc = analyze_image_style(uploaded_file)
                if desc not in st.session_state.learned_styles:
                    st.session_state.learned_styles.append(desc)
                save_current_user_data()
                st.success(desc)
            for s in st.session_state.learned_styles:
                st.write(s)
            if st.button("学習リセット"):
                st.session_state.learned_styles = []
                st.session_state.learned_preferences = []
                save_current_user_data()
                st.rerun()

    elif mode == "generate":
        st.subheader("🎨 画像生成モード")
        if st.session_state.level < 4:
            st.warning("レベル4で解放")
        else:
            prompt_input = st.text_area("何を描く？（キャラ名、ポーズ、状況など）", height=100, placeholder="例：座っている、腕を上げる、別の服")

            st.markdown("### 参照画像")
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

            quality = st.radio("画質", ["低画質（10pt / 1K）", "高画質（20pt / 2K）"])
            size_category = st.radio("サイズ", ["スマホサイズ", "PCサイズ", "ポスターサイズ"])
            aspect = st.radio("構図", ["正方形", "縦長", "横長"], horizontal=True)

            aspect_map = {"正方形": "1:1", "縦長": "9:16", "横長": "16:9"}
            aspect_ratio = aspect_map[aspect]
            if size_category == "PCサイズ" and aspect == "縦長":
                aspect_ratio = "3:4"
            elif size_category == "PCサイズ" and aspect == "横長":
                aspect_ratio = "4:3"

            if "低画質" in quality:
                model_name = "grok-imagine-image"
                resolution = "1k"
                cost = 10
                res_text = "1K"
            else:
                model_name = "grok-imagine-image-quality"
                resolution = "2k"
                cost = 20
                res_text = "2K"
            if size_category == "PCサイズ":
                cost += 5
            elif size_category == "ポスターサイズ":
                cost += 10
                resolution = "2k"
                res_text = "2K"
            ref_count = sum(1 for x in [style_ref, char_ref] if x)
            cost += ref_count * 5

            st.info(f"{model_name} / {resolution} / {aspect_ratio}")
            st.write(f"**消費ポイント: {cost} pt**（所持: {st.session_state.points} pt）")

            if st.button("🎨 イラストを生成する", type="primary", use_container_width=True):
                if not prompt_input.strip():
                    st.warning("何を描くかを入力してください")
                elif st.session_state.points < cost:
                    st.error("ポイントが足りません")
                else:
                    st.session_state.points -= cost
                    st.session_state.exp += 2
                    try:
                        with st.spinner("生成中..."):
                            refs = []
                            extra = []

                            extra.append("The user text is a DRAWING INSTRUCTION, not text to write on the image.")
                            extra.append("Do not render letters, captions, watermarks, or names onto the image.")

                            if style_ref:
                                refs.append(file_to_data_uri(style_ref))
                                extra.append(
                                    f"STYLE REFERENCE strength {style_strength}/10: "
                                    "Use ONLY the linework, coloring, shading and overall art style of the style reference image. "
                                    "Do NOT copy the character, face, outfit, pose or composition from the style reference."
                                )
                            if char_ref:
                                refs.append(file_to_data_uri(char_ref))
                                extra.append(
                                    f"CHARACTER REFERENCE strength {char_strength}/10: "
                                    "Keep the same character identity from the character reference (face, hair, body type, outfit features). "
                                    "Change pose, camera and composition according to the user instruction. "
                                    "Do NOT copy the original pose or background exactly."
                                )

                            if st.session_state.learned_styles:
                                extra.append("Also keep learned styles: " + " / ".join(st.session_state.learned_styles[-2:]))
                            if st.session_state.learned_preferences:
                                extra.append("User preferences: " + " / ".join(st.session_state.learned_preferences[-2:]))

                            full_prompt = f"Draw this: {prompt_input}\n" + "\n".join(extra)

                            if refs:
                                image_url = generate_with_references(full_prompt, model_name, aspect_ratio, resolution, refs)
                            else:
                                image_url = generate_text_image(full_prompt, model_name, aspect_ratio, resolution)

                        st.session_state.last_generated_image = {
                            "url": image_url,
                            "prompt": prompt_input,
                            "cost": cost,
                            "resolution": f"{res_text} / {aspect_ratio}"
                        }
                        st.session_state.generated_history.insert(0, {
                            "prompt": prompt_input,
                            "url": image_url,
                            "cost": cost,
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "resolution": f"{res_text} / {aspect_ratio}"
                        })
                        if st.session_state.exp >= 20:
                            st.session_state.level += 1
                            st.session_state.exp = 0
                            st.session_state.points += 5
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
        for item in st.session_state.generated_history:
            with st.expander(f"{item['time']} - {item['prompt'][:40]}"):
                st.image(item["url"], use_container_width=True)
