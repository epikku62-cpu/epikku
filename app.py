import streamlit as st
import os
import json
import hashlib
from openai import OpenAI
from datetime import datetime

st.set_page_config(page_title="AI育成お絵描きサイト", page_icon="🎨", layout="wide")

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
            "messages": st.session_state.get("messages", [])[-50:],
            "points": st.session_state.get("points", 0),
            "is_premium": st.session_state.get("is_premium", False),
            "ad_count": st.session_state.get("ad_count", 0),
            "last_login": datetime.now().isoformat()
        }
        save_users(users)

def update_personality():
    if len(st.session_state.messages) < 6:
        return
    recent = st.session_state.messages[-8:]
    conversation_text = "\n".join([f"{m['role']}: {m['content']}" for m in recent if "【お絵描きリクエスト】" not in m.get("content", "")])
    
    prompt = "以下の会話を見て、AIの現在の性格として最も適切なものを1つだけ選んでください。選択肢: 甘えん坊, ツンデレ, ヤンデレ, ヤンキー, 姫, 王子, 明るいキャラ, 口数少ないキャラ, 中立\n\n会話:\n" + conversation_text + "\n\n回答は選択肢の中から単語だけで返してください。"
    
    try:
        completion = client.chat.completions.create(
            model="grok-4.6",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20
        )
        new_type = completion.choices[0].message.content.strip()
        if new_type in CHARACTER_PROMPTS and new_type != st.session_state.ai_type:
            st.session_state.ai_type = new_type
            st.session_state.messages.append({
                "role": "assistant",
                "avatar": st.session_state.ai_icon,
                "content": f"（……なんか、少し性格が変わった気がする……今は『{new_type}』寄りかも）"
            })
    except:
        pass

# セッション初期化
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = None

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
                    users[reg_user] = {
                        "password": hash_password(reg_pass),
                        "data": {}
                    }
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
                    st.session_state.points = 0          # ← 新規登録ボーナスなし
                    st.session_state.is_premium = False
                    st.session_state.ad_count = 0
                    st.session_state.user_icon = "👤"
                    st.session_state.ai_icon = "👧"

                    st.success("登録完了！自動でログインしました")
                    st.rerun()
                except Exception as e:
                    st.error(f"登録に失敗しました。（{e}）")

    st.stop()

# メイン画面
st.markdown('<div style="background-color:#222;padding:12px;text-align:center;border-radius:8px;color:#aaa;border:1px dashed #555;margin-bottom:20px;font-size:14px;">📢 ここにGoogleアドセンスなどのバナー広告を表示します</div>', unsafe_allow_html=True)

st.title("🎨 専属絵師AI 育成ルーム")
st.caption("本物のAIがあなたの好みを学習し、世界に1つのイラストを生み出します。")

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
            save_current_user_data()
            st.rerun()
else:
    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.username}")
        st.write(f"**ポイント:** {st.session_state.points} pt")
        if st.session_state.is_premium:
            st.success("月額会員")
        else:
            st.info("無料会員")

        if st.button("ログアウト"):
            save_current_user_data()
            st.session_state.logged_in = False
            st.session_state.username = None
            st.rerun()

        st.markdown("---")
        st.markdown(f"### 📊 【{st.session_state.ai_name}】")
        st.write(f"**性格傾向:** {st.session_state.ai_type}")
        st.write(f"**レベル:** Lv.{st.session_state.level}")
        
        if st.session_state.level < 4:
            st.write(f"次のレベルまであと {5 - st.session_state.exp} 回会話")
            st.progress(st.session_state.exp / 5)
        else:
            need = 20
            st.write(f"次のレベルまであと {need - st.session_state.exp} カウント")
            st.progress(min(st.session_state.exp / need, 1.0))

        st.markdown("---")
        with st.expander("解放状況"):
            st.write("- Lv.1：会話のみ")
            st.write("- Lv.2：AIが好みを聞き始める")
            st.write("- Lv.3：画像学習可能")
            st.write("- Lv.4：画像生成解放")

        st.markdown('<div style="background-color:#1a1a1a;padding:12px;text-align:center;border-radius:8px;color:#888;border:1px dashed #444;font-size:13px;margin-top:40px;">📢 サイドバー広告枠</div>', unsafe_allow_html=True)

    st.subheader(f"💬 {st.session_state.ai_name} とのトークルーム")
    st.caption(f"現在の性格: **{st.session_state.ai_type}** ｜ ポイント: **{st.session_state.points} pt**")

    for msg in st.session_state.messages:
        avatar = msg.get("avatar", st.session_state.user_icon if msg["role"] == "user" else st.session_state.ai_icon)
        with st.chat_message(msg["role"], avatar=avatar):
            st.write(msg["content"])
            if "image" in msg:
                st.image(msg["image"])

    if user_message := st.chat_input("メッセージを送る..."):
        st.session_state.messages.append({
            "role": "user",
            "avatar": st.session_state.user_icon,
            "content": user_message
        })

        st.session_state.exp += 1
        st.session_state.ad_count += 1

        if st.session_state.level < 4:
            if st.session_state.exp >= 5:
                st.session_state.level += 1
                st.session_state.exp = 0
                if st.session_state.level == 4:
                    st.session_state.points += 80  # ← レベル4到達ボーナス80pt
                    st.session_state.messages.append({
                        "role": "assistant",
                        "avatar": st.session_state.ai_icon,
                        "content": "🎉 レベル4になったよ！画像生成ができるようになった！おめでとうポイント80ptプレゼント！"
                    })
        else:
            if st.session_state.exp >= 20:
                st.session_state.level += 1
                st.session_state.exp = 0
                st.session_state.points += 5
                st.session_state.messages.append({
                    "role": "assistant",
                    "avatar": st.session_state.ai_icon,
                    "content": f"レベルが上がったよ！Lv.{st.session_state.level}になった！ポイント5ptプレゼント！"
                })

        api_messages = [{"role": "system", "content": CHARACTER_PROMPTS.get(st.session_state.ai_type, CHARACTER_PROMPTS["中立"])}]
        for msg in st.session_state.messages:
            if "【お絵描きリクエスト】" not in msg.get("content", ""):
                api_messages.append({"role": msg["role"], "content": msg["content"]})

        try:
            if not grok_key:
                reply = "（APIキーが設定されていません）"
            else:
                with st.spinner("考え中..."):
                    completion = client.chat.completions.create(
                        model="grok-4.6",
                        messages=api_messages
                    )
                reply = completion.choices[0].message.content

            st.session_state.messages.append({
                "role": "assistant",
                "avatar": st.session_state.ai_icon,
                "content": reply
            })

            if len(st.session_state.messages) % 6 == 0:
                update_personality()

        except Exception as e:
            st.session_state.messages.append({
                "role": "assistant",
                "avatar": st.session_state.ai_icon,
                "content": f"（エラー: {e}）"
            })

        if not st.session_state.is_premium and st.session_state.ad_count >= 10:
            st.session_state.ad_count = 0
            st.warning("📢 動画広告の時間です（実際の広告は後で実装）")

        save_current_user_data()
        st.rerun()
