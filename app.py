import streamlit as st
import os
import json
import hashlib
import random
import base64
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

def update_personality():
    if len(st.session_state.messages) < 8:
        return
    recent = st.session_state.messages[-6:]
    conversation_text = "\n".join([f"{m['role']}: {m['content']}" for m in recent if "【お絵描きリクエスト】" not in m.get("content", "")])
    
    prompt = f"会話を見て性格を1つ選んで。選択肢: 甘えん坊, ツンデレ, ヤンデレ, ヤンキー, 姫, 王子, 明るいキャラ, 口数少ないキャラ, 中立\n\n{conversation_text}\n\n単語だけで答えて。"
    
    try:
        completion = client.chat.completions.create(
            model="grok-4-fast",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=15
        )
        new_type = completion.choices[0].message.content.strip()
        if new_type in CHARACTER_PROMPTS and new_type != st.session_state.ai_type:
            st.session_state.ai_type = new_type
            st.session_state.messages.append({
                "role": "assistant",
                "avatar": st.session_state.ai_icon,
                "content": f"（……なんか性格が変わった気がする。今は『{new_type}』寄りかも）"
            })
    except:
        pass

def extract_preferences_from_conversation():
    """会話から好みを抽出して学習する"""
    if len(st.session_state.messages) < 6:
        return
    
    recent = st.session_state.messages[-10:]
    conversation_text = "\n".join([f"{m['role']}: {m['content']}" for m in recent if "【お絵描きリクエスト】" not in m.get("content", "")])
    
    prompt = f"""以下の会話から、ユーザーの「絵やキャラに関する好み」を抽出してください。
好きなキャラ、好きな絵柄、好きな雰囲気、好きな色、描いてほしいものなどを短いフレーズでまとめてください。
複数ある場合は「 / 」で区切ってください。
好みが見つからない場合は「なし」とだけ答えてください。

会話:
{conversation_text}
"""
    
    try:
        completion = client.chat.completions.create(
            model="grok-4-fast",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80
        )
        result = completion.choices[0].message.content.strip()
        
        if result and result != "なし" and result not in st.session_state.learned_preferences:
            st.session_state.learned_preferences.append(result)
            # 多すぎる場合は古いものを削除
            if len(st.session_state.learned_preferences) > 15:
                st.session_state.learned_preferences = st.session_state.learned_preferences[-15:]
    except:
        pass

def analyze_image_style(uploaded_file):
    try:
        image = Image.open(uploaded_file)
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode()

        prompt = """このイラストの絵柄を詳しく分析して、短い日本語で説明してください。
線のタッチ、塗り方、色の雰囲気、全体の画風を含めて1文でまとめてください。
例：「丁寧で細い線のアニメ塗り、鮮やかな色使い」"""

        completion = client.chat.completions.create(
            model="grok-4-fast",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_base64}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=100
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        return f"分析に失敗しました（{e}）"

# セッション初期化
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

# ログイン画面
if not st.session_state.logged_in:
    st.markdown('<div style="background-color:#222;padding:12px;text-align:center;border-radius:8px;color:#aaa;border:1px dashed #555;margin-bottom:20px;font-size:14px;">📢 ここにGoogleアドセンスなどのバナー広告を表示します</div>', unsafe_allow_html=True)

    st.title("🎨 専属絵師AI 育成ルーム")
    st.markdown("### ログイン / 新規登録")

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
                st.session_state.ai_name = data.get("ai_name")
                st.session_state.ai_gender = data.get("ai_gender", "おんなのこ")
                st.session_state.ai_type = data.get("ai_type", "中立")
                st.session_state.level = data.get("level", 1)
                st.session_state.exp = data.get("exp", 0)
                st.session_state.learned_styles = data.get("learned_styles", [])
                st.session_state.learned_preferences = data.get("learned_preferences", [])
                st.session_state.image_count = data.get("image_count", 0)
                st.session_state.messages = data.get("messages", [])
                st.session_state.points = data.get("points", 0)
                st.session_state.is_premium = data.get("is_premium", False)
                st.session_state.ad_count = data.get("ad_count", 0)
                st.session_state.generated_history = data.get("generated_history", [])
                st.session_state.user_icon = data.get("user_icon", "👤")
                st.session_state.ai_icon = data.get("ai_icon", "👤")
                st.session_state.current_mode = "chat"
                st.success("ログインしました！")
                st.rerun()
            else:
                st.error("ユーザー名またはパスワードが違います")

    with tab2:
        reg_user = st.text_input("新しいユーザー名", key="reg_user")
        reg_pass = st.text_input("パスワード", type="password", key="reg_pass")
        reg_pass2 = st.text_input("パスワード（確認）", type="password", key="reg_pass2")

        if st.button("新規登録", type="primary"):
            if not reg_user or not reg_pass:
                st.warning("ユーザー名とパスワードを入力してください")
            elif reg_pass != reg_pass2:
                st.error("パスワードが一致しません")
            else:
                try:
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
                    st.session_state.image_count = 0
                    st.session_state.messages = []
                    st.session_state.points = 0
                    st.session_state.is_premium = False
                    st.session_state.ad_count = 0
                    st.session_state.generated_history = []
                    st.session_state.user_icon = "👤"
                    st.session_state.ai_icon = "👤"
                    st.session_state.current_mode = "chat"

                    st.success("登録完了！自動でログインしました")
                    st.rerun()
                except Exception as e:
                    st.error(f"登録に失敗しました。（{e}）")

    st.stop()

# ======================
# メイン画面
# ======================
st.markdown('<div style="background-color:#222;padding:12px;text-align:center;border-radius:8px;color:#aaa;border:1px dashed #555;margin-bottom:20px;font-size:14px;">📢 ここにGoogleアドセンスなどのバナー広告を表示します</div>', unsafe_allow_html=True)

st.title("🎨 専属絵師AI 育成ルーム")

if st.session_state.ai_name is None:
    st.subheader("👶 AIのプロフィールを決めてね")
    input_name = st.text_input("AIの名前を入力してください：", placeholder="例：めぐみん、アリスなど")
    gender = st.radio("性別を選んでね：", ["おんなのこ", "おとこのこ"], horizontal=True)

    if st.button("この設定で開始する！", type="primary"):
        if input_name.strip():
            st.session_state.ai_name = input_name.strip()
            st.session_state.ai_gender = gender
            st.session_state.ai_type = "中立"
            st.session_state.ai_icon = "👤"
            st.session_state.user_icon = "👤"
            
            st.session_state.messages = [{
                "role": "assistant",
                "avatar": st.session_state.ai_icon,
                "content": f"【{st.session_state.ai_name}｜Lv.1】\n\nはじめまして！わたしは「{input_name.strip()}」だよ！\n\n今はまだレベル1で、何も知らない真っ白な状態なんだ。\n\nあなたといっぱい話して、好きなキャラや絵柄を教えてもらいながら、少しずつ成長していくよ。\n\nまずは好きなキャラクターや、好きなアニメ・絵柄を教えてくれる？\n一緒に、あなた好みの絵が描けるAIに育てていこうね！"
            }]
            save_current_user_data()
            st.rerun()
else:
    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.username}")
        st.write(f"**ポイント:** {st.session_state.points} pt")
        st.write(f"**レベル:** Lv.{st.session_state.level}")
        st.write(f"**性格:** {st.session_state.ai_type}")
        
        if st.session_state.level < 4:
            st.progress(st.session_state.exp / 5)
            st.caption(f"次のレベルまであと {5 - st.session_state.exp} 回")
        else:
            st.progress(min(st.session_state.exp / 20, 1.0))
            st.caption(f"次のレベルまであと {20 - st.session_state.exp} カウント")

        st.markdown("---")
        st.markdown("### メニュー")

        if st.button("💬 トークルーム", use_container_width=True):
            st.session_state.current_mode = "chat"
            st.rerun()
        if st.button("🖼️ 学習モード", use_container_width=True):
            st.session_state.current_mode = "learn"
            st.rerun()
        if st.button("🎨 画像生成モード", use_container_width=True):
            st.session_state.current_mode = "generate"
            st.rerun()
        if st.button("📂 生成履歴", use_container_width=True):
            st.session_state.current_mode = "history"
            st.rerun()

        if st.session_state.level >= 10:
            st.markdown("---")
            st.markdown("### アイコン変更（Lv.10）")
            new_user_icon = st.text_input("ユーザーアイコン", value=st.session_state.user_icon)
            new_ai_icon = st.text_input("AIアイコン", value=st.session_state.ai_icon)
            if st.button("変更する"):
                st.session_state.user_icon = new_user_icon if new_user_icon else "👤"
                st.session_state.ai_icon = new_ai_icon if new_ai_icon else "👤"
                save_current_user_data()
                st.success("変更しました")
                st.rerun()
        else:
            st.caption("アイコン変更はLv.10で解放")

        st.markdown("---")
        if st.button("ログアウト"):
            save_current_user_data()
            st.session_state.logged_in = False
            st.session_state.username = None
            st.rerun()

        st.markdown("---")
        st.markdown('<div style="background-color:#1a1a1a;padding:12px;text-align:center;border-radius:8px;color:#888;border:1px dashed #444;font-size:13px;">📢 サイドバー広告枠</div>', unsafe_allow_html=True)

    mode = st.session_state.current_mode

    # ---------- トークルーム ----------
    if mode == "chat":
        st.subheader(f"💬 {st.session_state.ai_name} とのトークルーム")
        
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

        if user_message := st.chat_input("メッセージを送る..."):
            st.session_state.messages.append({
                "role": "user",
                "avatar": st.session_state.user_icon,
                "content": user_message
            })

            st.session_state.exp += 1
            st.session_state.ad_count += 1

            leveled_up = False
            unlock_message = ""

            if st.session_state.level < 4:
                if st.session_state.exp >= 5:
                    st.session_state.level += 1
                    st.session_state.exp = 0
                    leveled_up = True
                    
                    if st.session_state.level == 2:
                        unlock_message = "🎉 レベル2になりました！\nAIがあなたの好みを積極的に聞いてくるようになります。"
                    elif st.session_state.level == 3:
                        unlock_message = "🎉 レベル3になりました！\n【学習モード】が解放されました！"
                    elif st.session_state.level == 4:
                        st.session_state.points += 80
                        unlock_message = "🎉 レベル4になりました！\n【画像生成モード】が解放されました！\n80ポイントをプレゼントします！"
            else:
                if st.session_state.exp >= 20:
                    st.session_state.level += 1
                    st.session_state.exp = 0
                    st.session_state.points += 5
                    leveled_up = True
                    unlock_message = f"🎉 レベルアップ！ Lv.{st.session_state.level} になりました！\n5ポイントをプレゼントします！"

            if leveled_up and unlock_message:
                st.session_state.messages.append({
                    "role": "assistant",
                    "avatar": st.session_state.ai_icon,
                    "content": unlock_message
                })
                st.success(unlock_message)

            base = CHARACTER_PROMPTS.get(st.session_state.ai_type, CHARACTER_PROMPTS["中立"])
            gender_note = "女の子らしい可愛い口調で話して。" if st.session_state.ai_gender == "おんなのこ" else "男の子らしい口調で話して。"
            
            if st.session_state.level < 4:
                level_note = f"まだレベル{st.session_state.level}。絵は描けない。"
            else:
                level_note = "レベル4以上。絵を描ける。"

            system_prompt = f"""あなたは「{st.session_state.ai_name}」。{base}
{gender_note}
{level_note}
ユーザーの好きなキャラ・アニメ・絵柄を自然に聞いて。
短く自然に会話して。"""

            recent_messages = st.session_state.messages[-6:]
            api_messages = [{"role": "system", "content": system_prompt}]
            for msg in recent_messages:
                if "【お絵描きリクエスト】" not in msg.get("content", ""):
                    api_messages.append({"role": msg["role"], "content": msg["content"]})

            try:
                if not grok_key:
                    reply = "（APIキーが設定されていません）"
                else:
                    with st.spinner("考え中..."):
                        completion = client.chat.completions.create(
                            model="grok-4-fast",
                            messages=api_messages,
                            max_tokens=250
                        )
                    reply = completion.choices[0].message.content

                st.session_state.messages.append({
                    "role": "assistant",
                    "avatar": st.session_state.ai_icon,
                    "content": reply
                })

                # 一定間隔で会話から好みを学習
                if len(st.session_state.messages) % 5 == 0:
                    extract_preferences_from_conversation()
                    update_personality()

            except Exception as e:
                st.session_state.messages.append({
                    "role": "assistant",
                    "avatar": st.session_state.ai_icon,
                    "content": f"（エラー: {e}）"
                })

            if not st.session_state.is_premium and st.session_state.ad_count >= 10:
                st.session_state.ad_count = 0
                st.warning("📢 動画広告の時間です")

            save_current_user_data()
            st.rerun()

    # ---------- 学習モード ----------
    elif mode == "learn":
        st.subheader("🖼️ 学習モード")
        
        if st.session_state.level < 3:
            st.warning("この機能はレベル3で解放されます。")
            st.write(f"現在のレベル: **Lv.{st.session_state.level}**")
        else:
            st.write("好きな絵柄の画像をアップロードして、AIに強く学習させます。")
            st.caption("※学習しても経験値は入りません")
            
            uploaded_file = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"], key="learn_upload")
            
            if uploaded_file is not None:
                st.image(uploaded_file, width=300)
                
                if st.button("この画像を学習させる", type="primary"):
                    with st.spinner("画像を分析しています..."):
                        style_description = analyze_image_style(uploaded_file)
                    
                    if style_description not in st.session_state.learned_styles:
                        st.session_state.learned_styles.append(style_description)
                        st.success(f"強く学習しました！\n\n**覚えた内容：**\n{style_description}")
                    else:
                        st.info("この絵柄はすでに学習済みです。")
                    
                    save_current_user_data()
                    st.rerun()

            st.markdown("---")
            st.subheader("覚えている絵柄（画像から）")
            if st.session_state.learned_styles:
                for i, style in enumerate(st.session_state.learned_styles):
                    st.write(f"{i+1}. {style}")
                
                if st.button("画像の学習をリセット", type="secondary"):
                    st.session_state.learned_styles = []
                    save_current_user_data()
                    st.success("リセットしました")
                    st.rerun()
            else:
                st.write("まだ画像からは何も覚えていません")

            st.markdown("---")
            st.subheader("会話から覚えた好み")
            if st.session_state.learned_preferences:
                for i, pref in enumerate(st.session_state.learned_preferences):
                    st.write(f"{i+1}. {pref}")
                
                if st.button("会話の学習をリセット", type="secondary"):
                    st.session_state.learned_preferences = []
                    save_current_user_data()
                    st.success("リセットしました")
                    st.rerun()
            else:
                st.write("まだ会話からは何も覚えていません")

    # ---------- 画像生成モード ----------
    elif mode == "generate":
        st.subheader("🎨 画像生成モード")
        
        if st.session_state.level < 4:
            st.warning("この機能はレベル4で解放されます。")
            st.write(f"現在のレベル: **Lv.{st.session_state.level}**")
        else:
            st.write("あなたが育てたAIにイラストを描いてもらおう")
            
            # 学習状況を表示
            if st.session_state.learned_styles or st.session_state.learned_preferences:
                with st.expander("現在の学習状況を見る"):
                    if st.session_state.learned_styles:
                        st.write("**画像から学習した絵柄:**")
                        for s in st.session_state.learned_styles[-3:]:
                            st.write(f"- {s}")
                    if st.session_state.learned_preferences:
                        st.write("**会話から学習した好み:**")
                        for p in st.session_state.learned_preferences[-3:]:
                            st.write(f"- {p}")
            
            prompt_input = st.text_area("何を描く？（詳しく書くほど良い結果になりやすい）", height=120, placeholder="例：赤い瞳の魔法少女が爆発魔法を唱えているシーン、ダイナミックな構図")
            
            col1, col2 = st.columns(2)
            
            with col1:
                quality = st.radio("画質", ["低画質（10pt）", "高画質（20pt）"])
            
            with col2:
                size_category = st.radio("サイズカテゴリ", ["スマホサイズ", "PCサイズ", "ポスターサイズ"])
            
            aspect = st.radio("構図", ["正方形", "縦長", "横長"], horizontal=True)
            
            resolution_map = {
                ("スマホサイズ", "正方形"): ("1024 × 1024", 0),
                ("スマホサイズ", "縦長"): ("768 × 1344", 0),
                ("スマホサイズ", "横長"): ("1344 × 768", 0),
                ("PCサイズ", "正方形"): ("1280 × 1280", 5),
                ("PCサイズ", "縦長"): ("1024 × 1536", 5),
                ("PCサイズ", "横長"): ("1536 × 1024", 5),
                ("ポスターサイズ", "正方形"): ("1536 × 1536", 10),
                ("ポスターサイズ", "縦長"): ("1200 × 1800", 10),
                ("ポスターサイズ", "横長"): ("1800 × 1200", 10),
            }
            
            res_text, size_cost = resolution_map.get((size_category, aspect), ("1024 × 1024", 0))
            
            cost = 10 if "低画質" in quality else 20
            cost += size_cost
            
            st.info(f"選択中の解像度: **{res_text}**")
            st.write(f"**消費ポイント: {cost} pt**（所持: {st.session_state.points} pt）")
            
            if st.button("🎨 イラストを生成する", type="primary", use_container_width=True):
                if not prompt_input.strip():
                    st.warning("描く内容を入力してください")
                elif st.session_state.points < cost:
                    st.error(f"ポイントが足りません（必要: {cost}pt）")
                else:
                    st.session_state.points -= cost
                    st.session_state.exp += 2
                    
                    # ===== 学習内容を強く反映 =====
                    style_parts = []
                    
                    if st.session_state.learned_styles:
                        recent_styles = st.session_state.learned_styles[-3:]
                        style_parts.append("Strictly follow these art styles: " + " / ".join(recent_styles))
                    
                    if st.session_state.learned_preferences:
                        recent_prefs = st.session_state.learned_preferences[-3:]
                        style_parts.append("User preferences: " + " / ".join(recent_prefs))
                    
                    if style_parts:
                        style_instruction = ". ".join(style_parts) + ". Match the style, linework, coloring and atmosphere as closely as possible."
                    else:
                        style_instruction = "beautiful anime style, high quality"
                    
                    aspect_prompt = ""
                    if aspect == "縦長":
                        aspect_prompt = ", vertical composition, portrait orientation"
                    elif aspect == "横長":
                        aspect_prompt = ", horizontal composition, landscape orientation"
                    else:
                        aspect_prompt = ", square composition"
                    
                    full_prompt = f"{style_instruction}, {prompt_input}{aspect_prompt}, highly detailed, masterpiece"
                    
                    model_name = "grok-imagine-image" if "低画質" in quality else "grok-imagine-image-quality"
                    
                    try:
                        with st.spinner("生成中です...しばらくお待ちください"):
                            response = client.images.generate(
                                model=model_name,
                                prompt=full_prompt,
                                n=1
                            )
                            image_url = response.data[0].url
                        
                        st.session_state.last_generated_image = {
                            "url": image_url,
                            "prompt": prompt_input,
                            "cost": cost,
                            "resolution": res_text
                        }
                        
                        st.session_state.generated_history.insert(0, {
                            "prompt": prompt_input,
                            "url": image_url,
                            "cost": cost,
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "resolution": res_text
                        })
                        
                        st.session_state.messages.append({
                            "role": "assistant",
                            "avatar": st.session_state.ai_icon,
                            "content": f"できたよ！『{prompt_input}』（{cost}pt消費）",
                            "image": image_url
                        })
                        
                        if st.session_state.exp >= 20:
                            st.session_state.level += 1
                            st.session_state.exp = 0
                            st.session_state.points += 5
                            st.success(f"レベルアップ！ Lv.{st.session_state.level}")
                        
                        save_current_user_data()
                        st.rerun()
                        
                    except Exception as e:
                        st.session_state.points += cost
                        st.error(f"生成に失敗しました。ポイントは戻しました。\n{e}")

            if st.session_state.last_generated_image:
                st.markdown("---")
                st.subheader("最新の生成結果")
                st.caption(f"プロンプト: {st.session_state.last_generated_image['prompt']}")
                st.caption(f"解像度: {st.session_state.last_generated_image.get('resolution', '')} ｜ 消費: {st.session_state.last_generated_image['cost']}pt")
                st.image(st.session_state.last_generated_image["url"], use_container_width=True)

    # ---------- 生成履歴 ----------
    elif mode == "history":
        st.subheader("📂 生成した画像の履歴")
        
        if not st.session_state.generated_history:
            st.write("まだ生成した画像がありません")
        else:
            for item in st.session_state.generated_history:
                with st.expander(f"{item['time']} - {item['prompt'][:40]}..."):
                    st.write(f"プロンプト: {item['prompt']}")
                    st.write(f"解像度: {item.get('resolution', '不明')} ｜ 消費ポイント: {item['cost']}pt")
                    st.image(item["url"], use_container_width=True)
