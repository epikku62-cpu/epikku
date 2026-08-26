import streamlit as st
import os
import json
import hashlib
import random
from openai import OpenAI
from datetime import datetime
from PIL import Image

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
            "image_count": st.session_state.get("image_count", 0),
            "messages": st.session_state.get("messages", [])[-40:],
            "points": st.session_state.get("points", 0),
            "is_premium": st.session_state.get("is_premium", False),
            "ad_count": st.session_state.get("ad_count", 0),
            "generated_history": st.session_state.get("generated_history", [])[-30:],
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

# セッション初期化
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = None
if "generated_history" not in st.session_state:
    st.session_state.generated_history = []

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
                st.session_state.image_count = data.get("image_count", 0)
                st.session_state.messages = data.get("messages", [])
                st.session_state.points = data.get("points", 0)
                st.session_state.is_premium = data.get("is_premium", False)
                st.session_state.ad_count = data.get("ad_count", 0)
                st.session_state.generated_history = data.get("generated_history", [])
                st.session_state.user_icon = "👤"
                st.session_state.ai_icon = "👧" if st.session_state.ai_gender == "おんなのこ" else "👦"
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
                    st.session_state.image_count = 0
                    st.session_state.messages = []
                    st.session_state.points = 0
                    st.session_state.is_premium = False
                    st.session_state.ad_count = 0
                    st.session_state.generated_history = []
                    st.session_state.user_icon = "👤"
                    st.session_state.ai_icon = "👧"

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

# プロフィール未設定
if st.session_state.ai_name is None:
    st.subheader("👶 AIのプロフィールを決めてね")
    input_name = st.text_input("AIの名前を入力してください：", placeholder="例：めぐみん、アリスなど")
    gender = st.radio("性別を選んでね：", ["おんなのこ", "おとこのこ"], horizontal=True)

    if st.button("この設定で開始する！", type="primary"):
        if input_name.strip():
            st.session_state.ai_name = input_name.strip()
            st.session_state.ai_gender = gender
            st.session_state.ai_type = "中立"
            st.session_state.ai_icon = "👧" if gender == "おんなのこ" else "👦"
            
            st.session_state.messages = [{
                "role": "assistant",
                "avatar": st.session_state.ai_icon,
                "content": f"はじめまして！わたしは「{input_name.strip()}」だよ！\n\n今はまだレベル1で、何も知らない真っ白な状態なんだ。\n\nあなたといっぱい話して、好きなキャラや絵柄を教えてもらいながら、少しずつ成長していくよ。\n\nまずは好きなキャラクターや、好きなアニメ・絵柄を教えてくれる？\n一緒に、あなた好みの絵が描けるAIに育てていこうね！"
            }]
            save_current_user_data()
            st.rerun()
else:
    # サイドバー（ステータス）
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

        if st.button("ログアウト"):
            save_current_user_data()
            st.session_state.logged_in = False
            st.session_state.username = None
            st.rerun()

        st.markdown("---")
        st.markdown('<div style="background-color:#1a1a1a;padding:12px;text-align:center;border-radius:8px;color:#888;border:1px dashed #444;font-size:13px;">📢 サイドバー広告枠</div>', unsafe_allow_html=True)

    # ===== タブ構成 =====
    tab_chat, tab_learn, tab_generate, tab_history = st.tabs([
        "💬 トークルーム",
        "🖼️ 学習モード",
        "🎨 画像生成モード",
        "📂 生成履歴"
    ])

    # ---------- トークルーム ----------
    with tab_chat:
        st.subheader(f"{st.session_state.ai_name} とのトークルーム")
        
        for msg in st.session_state.messages:
            avatar = msg.get("avatar", st.session_state.user_icon if msg["role"] == "user" else st.session_state.ai_icon)
            with st.chat_message(msg["role"], avatar=avatar):
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
            if st.session_state.level < 4:
                if st.session_state.exp >= 5:
                    st.session_state.level += 1
                    st.session_state.exp = 0
                    leveled_up = True
                    if st.session_state.level == 4:
                        st.session_state.points += 80
                        st.session_state.messages.append({
                            "role": "assistant",
                            "avatar": st.session_state.ai_icon,
                            "content": "🎉 レベル4になったよ！画像生成ができるようになった！80ptプレゼント！"
                        })
            else:
                if st.session_state.exp >= 20:
                    st.session_state.level += 1
                    st.session_state.exp = 0
                    st.session_state.points += 5
                    leveled_up = True
                    st.session_state.messages.append({
                        "role": "assistant",
                        "avatar": st.session_state.ai_icon,
                        "content": f"🎉 レベルアップ！Lv.{st.session_state.level}！5ptプレゼント！"
                    })

            if leveled_up:
                st.balloons()
                st.success(f"レベルアップ！ Lv.{st.session_state.level}")

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

                if len(st.session_state.messages) % 8 == 0:
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
    with tab_learn:
        st.subheader("🖼️ 学習モード")
        
        if st.session_state.level < 3:
            st.info("レベル3になると画像学習ができるようになります。")
            st.write("今のレベル:", st.session_state.level)
        else:
            st.write("好きな絵柄の画像をアップロードして、AIに覚えさせよう。")
            
            uploaded_file = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"], key="learn_upload")
            
            if uploaded_file is not None:
                st.image(uploaded_file, width=300)
                if st.button("この画像を学習させる", type="primary"):
                    # 簡易タグ（後でVisionで改善可能）
                    tags = [
                        "アニメ調の線が綺麗な絵柄",
                        "柔らかく淡い色使いのタッチ",
                        "コントラストが強めの鮮やかな絵柄",
                        "繊細で丁寧な線画タッチ",
                        "厚塗りっぽい塗り方の絵柄"
                    ]
                    tag = random.choice(tags)
                    st.session_state.learned_styles.append(tag)
                    st.session_state.exp += 1
                    
                    st.success(f"『{tag}』として覚えました！")
                    
                    if st.session_state.level == 3 and st.session_state.exp >= 5:
                        st.session_state.level = 4
                        st.session_state.exp = 0
                        st.session_state.points += 80
                        st.balloons()
                        st.success("レベル4になりました！画像生成が解放されました（80pt付与）")
                    
                    save_current_user_data()
                    st.rerun()

            st.markdown("---")
            st.subheader("覚えている絵柄")
            if st.session_state.learned_styles:
                for i, style in enumerate(st.session_state.learned_styles):
                    st.write(f"{i+1}. {style}")
                
                if st.button("学習した絵柄をすべてリセット", type="secondary"):
                    st.session_state.learned_styles = []
                    save_current_user_data()
                    st.success("リセットしました")
                    st.rerun()
            else:
                st.write("まだ何も覚えていません")

    # ---------- 画像生成モード ----------
    with tab_generate:
        st.subheader("🎨 画像生成モード")
        
        if st.session_state.level < 4:
            st.info("レベル4になると画像生成ができるようになります。")
            st.write("今のレベル:", st.session_state.level)
        else:
            st.write("あなたが育てたAIにイラストを描いてもらおう")
            
            prompt_input = st.text_area("何を描く？（詳しく書くほど良い結果になりやすい）", height=100, placeholder="例：赤い瞳の魔法少女が爆発魔法を唱えているシーン、ダイナミックな構図")
            
            col1, col2 = st.columns(2)
            with col1:
                quality = st.radio("画質", ["低画質（10pt）", "高画質（20pt）"])
            with col2:
                size = st.radio("サイズ", ["スマホサイズ（+0pt）", "PCサイズ（+5pt）", "ポスターサイズ（+10pt）"])
            
            # ポイント計算
            cost = 0
            if "低画質" in quality:
                cost += 10
                model_name = "grok-imagine-image"
            else:
                cost += 20
                model_name = "grok-imagine-image-quality"
            
            if "PCサイズ" in size:
                cost += 5
            elif "ポスターサイズ" in size:
                cost += 10
            
            st.write(f"**消費ポイント: {cost} pt**（所持: {st.session_state.points} pt）")
            
            if st.button("🎨 イラストを生成する", type="primary", use_container_width=True):
                if not prompt_input.strip():
                    st.warning("描く内容を入力してください")
                elif st.session_state.points < cost:
                    st.error(f"ポイントが足りません（必要: {cost}pt）")
                else:
                    st.session_state.points -= cost
                    st.session_state.exp += 2
                    
                    styles_text = ", ".join(st.session_state.learned_styles[-3:]) if st.session_state.learned_styles else "beautiful anime style"
                    full_prompt = f"{prompt_input}, {styles_text}, high quality, detailed illustration"
                    
                    try:
                        with st.spinner("描いています...しばらく待ってね"):
                            response = client.images.generate(
                                model=model_name,
                                prompt=full_prompt,
                                n=1
                            )
                            image_url = response.data[0].url
                        
                        # 履歴に追加
                        st.session_state.generated_history.insert(0, {
                            "prompt": prompt_input,
                            "url": image_url,
                            "cost": cost,
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M")
                        })
                        
                        st.session_state.messages.append({
                            "role": "assistant",
                            "avatar": st.session_state.ai_icon,
                            "content": f"できたよ！『{prompt_input}』（{cost}pt消費）",
                            "image": image_url
                        })
                        
                        st.success("生成完了！")
                        st.image(image_url, use_container_width=True)
                        
                    except Exception as e:
                        st.session_state.points += cost
                        st.error(f"生成に失敗しました。ポイントは戻しました。\n{e}")
                    
                    if st.session_state.exp >= 20:
                        st.session_state.level += 1
                        st.session_state.exp = 0
                        st.session_state.points += 5
                        st.balloons()
                        st.success(f"レベルアップ！ Lv.{st.session_state.level}")
                    
                    save_current_user_data()
                    st.rerun()

    # ---------- 生成履歴 ----------
    with tab_history:
        st.subheader("📂 生成した画像の履歴")
        
        if not st.session_state.generated_history:
            st.write("まだ生成した画像がありません")
        else:
            for i, item in enumerate(st.session_state.generated_history):
                with st.expander(f"{item['time']} - {item['prompt'][:30]}..."):
                    st.write(f"プロンプト: {item['prompt']}")
                    st.write(f"消費ポイント: {item['cost']}pt")
                    st.image(item["url"], use_container_width=True)
