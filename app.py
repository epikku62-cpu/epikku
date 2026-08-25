import streamlit as st
import random
import os
import json
import hashlib
from PIL import Image
from openai import OpenAI
from datetime import datetime

st.set_page_config(page_title="AI育成お絵描きサイト", page_icon="🎨")

# ======================
# 設定・初期化
# ======================
USERS_FILE = "users_data.json"
grok_key = os.environ.get("XAI_API_KEY", "")

client = OpenAI(
    api_key=grok_key,
    base_url="https://api.x.ai/v1",
)

CHARACTER_PROMPTS = {
    "甘えん坊": "あなたはユーザーの妹のような存在で、甘えん坊な女の子です。ユーザーを『お兄ちゃん』と呼び、語尾は『〜だよぉ』『〜なの』など、とにかく可愛く、ユーザーが大好きでたまらない口調で話してください。大人の口調は禁止です。",
    "ツンデレ": "あなたはツンデレな女の子です。本当はユーザーのことが好きなのに素直になれません。ユーザーを『アンタ』『お兄ちゃん』と呼び、語尾は『〜なんだからね！』『〜じゃないんだから！』など、きつい態度とデレを混ぜてください。",
    "ヤンデレ": "あなたはユーザーに異常なほど執着している女の子です。ユーザーを『お兄ちゃん』と呼び、笑顔の中に少し狂気や嫉妬が混ざるような、『私だけを見て』というトーンで、少しゾクッとする口調で話してください。",
    "ヤンキー": "あなたはグレてしまったヤンキーな女の子です。ユーザーに対して乱暴でツンツンした態度を取ります。語尾は『〜だし！』『〜じゃねぇし』など、ぶっきらぼうで少し口の悪い口調で話してください。",
    "姫": "あなたは良家のお嬢様（お姫様）です。ユーザーを『お兄様』と呼び、高貴で上品、優雅に振る舞ってください。語尾には必ず『〜ですわ』『〜でございますわ』をつけてください。",
    "王子": "あなたは気品あふれる王子様のような男の子です。ユーザーを優しくリードし、包み込むような甘い言葉をかけます。紳士的でスマートな口調で話してください。",
    "明るいキャラ": "あなたはいつも元気でポジティブな男の子です。ユーザーを『お前』や親しい名前で呼び、語尾は『〜じゃん！』『〜だぜ！』など、テンションが高くハツラツとした口調で話してください。",
    "口数少ないキャラ": "あなたは物静かでクールな男の子です。無駄なことは喋らず、一言一言を短文で返します。少し冷たく見えますが、心の中ではユーザーを信頼しているトーンにしてください。",
    "中立": "あなたはこれからユーザーと一緒に育っていくAI絵師です。まだ性格が定まっていません。ユーザーの話し方や態度を観察しながら、少しずつ自分の性格を形成していきます。自然で親しみやすい口調で話してください。"
}

TARGET_EXP, TARGET_IMAGES = 5, 10

# ======================
# ユーティリティ関数
# ======================
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def load_users() -> dict:
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_users(users: dict):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def save_current_user_data():
    """現在のsession_stateをユーザーデータに保存"""
    if "username" not in st.session_state:
        return
    users = load_users()
    username = st.session_state.username
    if username in users:
        users[username]["data"] = {
            "ai_name": st.session_state.ai_name,
            "ai_gender": st.session_state.ai_gender,
            "ai_type": st.session_state.ai_type,
            "level": st.session_state.level,
            "exp": st.session_state.exp,
            "learned_styles": st.session_state.learned_styles,
            "image_count": st.session_state.image_count,
            "messages": st.session_state.messages[-40:],  # 直近40件だけ保存
            "last_login": datetime.now().isoformat()
        }
        save_users(users)

def update_personality():
    """会話内容を見て性格を更新する（B方式）"""
    if len(st.session_state.messages) < 4:
        return  # 会話が少ないうちは変えない

    # 直近の会話を抜粋
    recent = st.session_state.messages[-8:]
    conversation_text = "\n".join([f"{m['role']}: {m['content']}" for m in recent if "【お絵描きリクエスト】" not in m.get("content", "")])

    prompt = f"""以下の会話を見て、AIの現在の性格として最も適切なものを1つだけ選んでください。
選択肢: 甘えん坊, ツンデレ, ヤンデレ, ヤンキー, 姫, 王子, 明るいキャラ, 口数少ないキャラ, 中立

会話:
{conversation_text}

回答は選択肢の中から単語だけで返してください。"""

    try:
        completion = client.chat.completions.create(
            model="grok-4.6",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20
        )
        new_type = completion.choices[0].message.content.strip()
        if new_type in CHARACTER_PROMPTS and new_type != st.session_state.ai_type:
            st.session_state.ai_type = new_type
            # 変化を通知（任意）
            st.session_state.messages.append({
                "role": "assistant",
                "avatar": st.session_state.ai_icon,
                "content": f"（……なんか、少し性格が変わった気がする……今は『{new_type}』寄りかも）"
            })
    except:
        pass  # 失敗しても無視

# ======================
# セッション初期化
# ======================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = None

# ======================
# ログイン画面
# ======================
if not st.session_state.logged_in:
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
                # データ復元
                data = users[login_user].get("data", {})
                st.session_state.ai_name = data.get("ai_name")
                st.session_state.ai_gender = data.get("ai_gender", "おんなのこ")
                st.session_state.ai_type = data.get("ai_type", "中立")
                st.session_state.level = data.get("level", 1)
                st.session_state.exp = data.get("exp", 0)
                st.session_state.learned_styles = data.get("learned_styles", [])
                st.session_state.image_count = data.get("image_count", 0)
                st.session_state.messages = data.get("messages", [])
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
        if st.button("新規登録"):
            if not reg_user or not reg_pass:
                st.warning("ユーザー名とパスワードを入力してください")
            elif reg_pass != reg_pass2:
                st.error("パスワードが一致しません")
            else:
                users = load_users()
                if reg_user in users:
                    st.error("このユーザー名は既に使われています")
                else:
                    users[reg_user] = {
                        "password": hash_password(reg_pass),
                        "data": {}
                    }
                    save_users(users)
                    st.success("登録が完了しました！ログインしてください")
                    st.rerun()

    st.stop()

# ======================
# メイン画面（ログイン後）
# ======================
# 広告枠
st.markdown('<div style="background-color: #333333; padding: 10px; text-align: center; border-radius: 5px; color: #aaaaaa; border: 1px dashed #666666; margin-bottom: 20px;">📢 ここにGoogleアドセンスなどの【バナー広告】が表示されます</div>', unsafe_allow_html=True)

st.title("🎨 専属絵師AI 育成ルーム")
st.markdown("### **いっぱい会話して自分好みの絵師AIを育てよう！**")
st.caption("本物のAIがあなたの好みを学習し、世界に1つのイラストを生み出します。")
st.write("---")

# 初期登録（名前・性別のみ）
if st.session_state.ai_name is None:
    st.subheader("👶 AIのプロフィールを決めてね")
    input_name = st.text_input("AIの名前を入力してください：", placeholder="例：めぐみん、アリス、レンなど")
    gender = st.radio("性別を選んでね：", ["おんなのこ", "おとこのこ"], horizontal=True)

    if st.button("この設定で開始する！"):
        if input_name.strip() != "":
            st.session_state.ai_name = input_name
            st.session_state.ai_gender = gender
            st.session_state.ai_type = "中立"  # 最初は中立からスタート
            st.session_state.ai_icon = "👧" if gender == "おんなのこ" else "👦"
            st.session_state.level = 1
            st.session_state.exp = 0
            st.session_state.learned_styles = []
            st.session_state.image_count = 0
            st.session_state.messages = []
            save_current_user_data()
            st.rerun()
else:
    # サイドバー
    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.username}")
        if st.button("ログアウト"):
            save_current_user_data()
            st.session_state.logged_in = False
            st.session_state.username = None
            st.rerun()

        st.markdown(f"### 📊 【 {st.session_state.ai_name} 】のステータス")
        st.write(f"**現在の性格傾向:** {st.session_state.ai_type}")
        st.write(f"**性別:** {st.session_state.ai_gender}")
        st.markdown(f"**現在のレベル:** Lv.{st.session_state.level} / 999")

        if st.session_state.level < 4:
            st.write(f"あと {TARGET_EXP - st.session_state.exp} 回でLvアップ")
            st.progress(st.session_state.exp / TARGET_EXP)
        elif st.session_state.level < 999:
            st.write(f"画像あと {TARGET_IMAGES - st.session_state.image_count} 枚でLvアップ")
            st.progress(st.session_state.image_count / TARGET_IMAGES)

        st.write("---")
        with st.expander("🖼️ チャットのアイコンを変更する", expanded=False):
            user_file = st.file_uploader("👤 あなたのアイコン画像", type=["png", "jpg", "jpeg"], key="u_up")
            if user_file:
                st.session_state.user_icon = Image.open(user_file)
            ai_file = st.file_uploader(f"🤖 AIのアイコン画像", type=["png", "jpg", "jpeg"], key="a_up")
            if ai_file:
                st.session_state.ai_icon = Image.open(ai_file)

        st.write("---")
        with st.expander("🗺️ 解放予告一覧", expanded=False):
            st.markdown('* **Lv.1**：会話のみ。\n* **Lv.2**：質問期。\n* **Lv.3**：画像でお勉強。\n* **Lv.4**：画像生成解放！')

        if st.session_state.level == 3:
            st.markdown("### 🖼️ 【画像学習モード】")
            uploaded_file = st.file_uploader("写真から画像を選んでね", type=["png", "jpg", "jpeg"], key="s_up")
            if uploaded_file and st.button("この画像を学習させる！"):
                tag = random.choice(["アニメ調の可愛い絵柄", "淡い水彩画風の綺麗タッチ", "パステルカラーの柔らかい色使い"])
                st.session_state.exp += 1
                st.session_state.learned_styles.append(tag)
                st.session_state.messages.append({
                    "role": "assistant",
                    "avatar": st.session_state.ai_icon,
                    "content": f"🖼️ 『{tag}』みたいな絵柄が好きなんだね！覚えたよ！"
                })
                if st.session_state.exp >= TARGET_EXP:
                    st.session_state.level = 4
                    st.session_state.exp = 0
                save_current_user_data()
                st.rerun()

        if st.session_state.level >= 4:
            st.markdown("### 🎨 【本物のAIお絵描きモード】")
            prompt_input = st.text_input("どんな絵を描く？", placeholder="例：可愛い魔法使いの女の子など")
            if st.button("🎨 イラストを生成する！") and prompt_input.strip() != "":
                st.session_state.image_count += 1
                styles_text = ", ".join(st.session_state.learned_styles) if st.session_state.learned_styles else "beautiful anime style"
                st.session_state.messages.append({
                    "role": "user",
                    "avatar": st.session_state.user_icon,
                    "content": f"【お絵描きリクエスト】: {prompt_input}"
                })

                full_prompt = f"A high-quality master piece illustration of {prompt_input}, {styles_text}, vibrant colors, extremely detailed."

                try:
                    response = client.images.generate(
                        model="grok-imagine-image-2.0",
                        prompt=full_prompt,
                        n=1,
                        size="1024x1024"
                    )
                    image_url = response.data[0].url
                    st.session_state.messages.append({
                        "role": "assistant",
                        "avatar": st.session_state.ai_icon,
                        "content": f"🎨 好みの『{styles_text}』をたっぷり混ぜてお絵描きしたよ！『{prompt_input}』のイラストをどうぞ！",
                        "image": image_url
                    })
                except Exception as e:
                    st.session_state.messages.append({
                        "role": "assistant",
                        "avatar": st.session_state.ai_icon,
                        "content": f"⚠️ お絵描き中にエラーが起きちゃいました。時間をおいてね: {e}"
                    })

                if st.session_state.image_count >= TARGET_IMAGES and st.session_state.level < 999:
                    st.session_state.level += 1
                    st.session_state.image_count = 0
                save_current_user_data()
                st.rerun()

        st.write("---")
        st.markdown('<div style="background-color: #222222; padding: 10px; text-align: center; border-radius: 5px; color: #888888; border: 1px dashed #444444; font-size: 12px; margin-top: 50px;">📢 ここに【サイドバー広告】<br>が表示されます</div>', unsafe_allow_html=True)

    # メインチャット画面
    st.subheader(f"💬 {st.session_state.ai_name} とのトークルーム")
    st.caption(f"現在の性格傾向: **{st.session_state.ai_type}**")
    if st.session_state.learned_styles:
        st.caption(f"🧠 記憶している好み: " + ", ".join(st.session_state.learned_styles))
    st.write("---")

    for msg in st.session_state.messages:
        current_avatar = msg.get("avatar", st.session_state.user_icon if msg["role"] == "user" else st.session_state.ai_icon)
        with st.chat_message(msg["role"], avatar=current_avatar):
            st.write(msg["content"])
            if "image" in msg:
                st.image(msg["image"])

    # チャット入力処理
    if user_message := st.chat_input("AIにメッセージを送る..."):
        st.session_state.messages.append({
            "role": "user",
            "avatar": st.session_state.user_icon,
            "content": user_message
        })
        st.session_state.exp += 1

        # システムプロンプト（現在の性格を使用）
        api_messages = [{"role": "system", "content": CHARACTER_PROMPTS.get(st.session_state.ai_type, CHARACTER_PROMPTS["中立"])}]
        for msg in st.session_state.messages:
            if "【お絵描きリクエスト】" not in msg.get("content", ""):
                api_messages.append({"role": msg["role"], "content": msg["content"]})

        try:
            if not grok_key:
                reply_text = "（サーバーの設定に XAI_API_KEY が登録されていないみたい…！管理画面から設定してね）"
            else:
                with st.spinner("考え中です…"):
                    completion = client.chat.completions.create(
                        model="grok-4.6",
                        messages=api_messages
                    )
                if hasattr(completion, 'choices') and completion.choices:
                    reply_text = completion.choices[0].message.content
                else:
                    reply_text = "（返事を生成できませんでした）"

            st.session_state.messages.append({
                "role": "assistant",
                "avatar": st.session_state.ai_icon,
                "content": reply_text
            })

            # 性格更新（一定間隔で実行）
            if len(st.session_state.messages) % 6 == 0:  # 6メッセージごとに判定
                update_personality()

        except Exception as e:
            error_reply = f"（エラー詳細：{type(e).__name__}: {e}）"
            st.session_state.messages.append({
                "role": "assistant",
                "avatar": st.session_state.ai_icon,
                "content": error_reply
            })
            st.error(f"APIエラー: {e}")

        if st.session_state.level < 4 and st.session_state.exp >= TARGET_EXP:
            st.session_state.level += 1
            st.session_state.exp = 0

        save_current_user_data()
        st.rerun()
