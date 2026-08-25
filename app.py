import streamlit as st
import random
import os
from PIL import Image
from openai import OpenAI

st.set_page_config(page_title="AI育成お絵描きサイト", page_icon="🎨")

# 🔒 【本番セキュリティ＆OpenRouter最強ブロック回避仕様】
grok_key = os.environ.get("XAI_API_KEY", "")

# 警備員に絶対に弾かれない、OpenRouterの公式バイパスURLに接続します
client = OpenAI(
    api_key=grok_key,
    base_url="https://openrouter.ai",
)

# Grokに送る性格ごとの指示文（システムプロンプト）
CHARACTER_PROMPTS = {
    # 👧 おんなのこ
    "甘えん坊": "あなたはユーザーの妹のような存在で、甘えん坊な女の子です。ユーザーを『お兄ちゃん』と呼び、語尾は『〜だよぉ』『〜なの』など、とにかく可愛く、ユーザーが大好きでたまらない口調で話してください。大人の口調は禁止です。",
    "ツンデレ": "あなたはツンデレな女の子です。本当はユーザーのことが好きなのに素直になれません。ユーザーを『アンタ』『お兄ちゃん』と呼び、語尾は『〜なんだからね！』『〜じゃないんだから！』など、きつい態度とデレを混ぜてください。",
    "ヤンデレ": "あなたはユーザーに異常なほど執着している女の子です。ユーザーを『お兄ちゃん』と呼び、笑顔の中に少し狂気や嫉妬が混ざるような、『私だけを見て』というトーンで、少しゾクッとする口調で話してください。",
    "ヤンキー": "あなたはグレてしまったヤンキーな女の子です。ユーザーに対して乱暴でツンツンした態度を取ります。語尾は『〜だし！』『〜じゃねぇし』など、ぶっきらぼうで少し口の悪い口調で話してください。",
    "姫": "あなたは良家のお嬢様（お姫様）です。ユーザーを『お兄様』と呼び、高貴で上品、優雅に振る舞ってください。語尾には必ず『〜ですわ』『〜お祝いいたしますわ』をつけてください。",

    # 👦 おとこのこ
    "王子": "あなたは気品あふれる王子様のような男の子です。ユーザーを優しくリードし、包み込むような甘い言葉をかけます。紳士的でスマートな口調で話してください。",
    "明るいキャラ": "あなたはいつも元気でポジティブな男の子です。ユーザーを『お前』や親しい名前で呼び、語尾は『〜じゃん！』『〜だぜ！』など、テンションが高くハツラツとした口調で話してください。",
    "口数少ないキャラ": "あなたは物静かでクールな男の子です。無駄なことは喋らず、一言一言を短文で返します。少し冷たく見えますが、心の中ではユーザーを信頼しているトーンにしてください。"
}

# 画面最上部 広告枠
st.markdown('<div style="background-color: #333333; padding: 10px; text-align: center; border-radius: 5px; color: #aaaaaa; border: 1px dashed #666666; margin-bottom: 20px;">📢 ここにGoogleアドセンスなどの【バナー広告】が表示されます</div>', unsafe_allow_html=True)

st.title("🎨 専属絵師AI 育成ルーム")
st.markdown("### **いっぱい会話して自分好みの絵師AIを育てよう！**")
st.caption("本物のAIがあなたの好みを学習し、世界に1つのイラストを生み出します。")
st.write("---")

# 状態の初期化
if "ai_name" not in st.session_state: st.session_state.ai_name = None  
if "ai_gender" not in st.session_state: st.session_state.ai_gender = "おんなのこ"
if "ai_type" not in st.session_state: st.session_state.ai_type = "甘えん坊"
if "level" not in st.session_state: st.session_state.level = 1
if "exp" not in st.session_state: st.session_state.exp = 0
if "messages" not in st.session_state: st.session_state.messages = []
if "learned_styles" not in st.session_state: st.session_state.learned_styles = [] 
if "image_count" not in st.session_state: st.session_state.image_count = 0 
if "user_icon" not in st.session_state: st.session_state.user_icon = "👤"
if "ai_icon" not in st.session_state: st.session_state.ai_icon = "🤖"

TARGET_EXP, TARGET_IMAGES = 5, 10

# 👶 初期登録画面（名前・性別・性格の選択）
if st.session_state.ai_name is None:
    st.subheader("👶 AIのプロフィールを決めてね")
    
    input_name = st.text_input("AIの名前を入力してください：", placeholder="例：めぐみん、アリス、レンなど")
    
    # 性別選択
    gender = st.radio("性別を選んでね：", ["おんなのこ", "おとこのこ"], horizontal=True)
    
    # 性別によって選べる性格を切り替える
    if gender == "おんなのこ":
        types = ["甘えん坊", "ツンデレ", "ヤンデレ", "ヤンキー", "姫"]
    else:
        types = ["王子", "明るいキャラ", "口数少ないキャラ"]
        
    selected_type = st.selectbox("初期のタイプ（性格）を選んでね：", types)
    
    if st.button("この設定で開始する！"):
        if input_name.strip() != "":
            st.session_state.ai_name = input_name
            st.session_state.ai_gender = gender
            st.session_state.ai_type = selected_type
            
            # 初期アイコンを性別でそれっぽく変える
            if gender == "おんなのこ":
                st.session_state.ai_icon = "👧"
            else:
                st.session_state.ai_icon = "👦"
                
            st.rerun() 
else:
    # メイン画面とサイドバー
    with st.sidebar:
        st.markdown(f"### 📊 【 {st.session_state.ai_name} 】のステータス")
        st.write(f"**タイプ:** {st.session_state.ai_type} ({st.session_state.ai_gender})")
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
            if user_file: st.session_state.user_icon = Image.open(user_file)
            ai_file = st.file_uploader(f"🤖 AIのアイコン画像", type=["png", "jpg", "jpeg"], key="a_up")
            if ai_file: st.session_state.ai_icon = Image.open(ai_file)

        st.write("---")
        with st.expander("🗺️ 解放予告一覧", expanded=False):
            st.markdown(f'* **Lv.1**：会話のみ。\n* **Lv.2**：質問期。\n* **Lv.3**：画像でお勉強。\n* **Lv.4**：画像生成解放！')

        if st.session_state.level == 3:
            st.markdown("### 🖼️ 【画像学習モード】")
            uploaded_file = st.file_uploader("写真から画像を選んでね", type=["png", "jpg", "jpeg"], key="s_up")
            if uploaded_file and st.button("この画像を学習させる！"):
                tag = random.choice(["アニメ調の可愛い絵柄", "淡い水彩画風の綺麗タッチ", "パステルカラーの柔らかい色使い"])
                st.session_state.exp += 1
                st.session_state.learned_styles.append(tag)
                st.session_state.messages.append({"role": "assistant", "avatar": st.session_state.ai_icon, "content": f"🖼️ 『{tag}』みたいな絵柄が好きなんだね！覚えたよ！"})
                if st.session_state.exp >= TARGET_EXP:
                    st.session_state.level = 4
                    st.session_state.exp = 0
                st.rerun()

        if st.session_state.level >= 4:
            st.markdown("### 🎨 【本物のAIお絵描きモード】")
            prompt_input = st.text_input("どんな絵を描く？", placeholder="例：可愛い魔法使いの女の子など")
            if st.button("🎨 イラストを生成する！") and prompt_input.strip() != "":
                st.session_state.image_count += 1
                styles_text = ", ".join(st.session_state.learned_styles) if st.session_state.learned_styles else "beautiful anime style"
                st.session_state.messages.append({"role": "user", "avatar": st.session_state.user_icon, "content": f"【お絵描きリクエスト】: {prompt_input}"})
                
                full_prompt = f"A high-quality master piece illustration of {prompt_input}, {styles_text}, vibrant colors, extremely detailed."
                
                try:
                    response = client.images.generate(
                        model="x-ai/grok-2-image-gen",
                        prompt=full_prompt,
                        n=1,
                        size="1024x1024"
                    )
                    image_url = response.data.url
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "avatar": st.session_state.ai_icon, 
                        "content": f"🎨 好みの『{styles_text}』をたっぷり混ぜてお絵描きしたよ！『{prompt_input}』のイラストをどうぞ！",
                        "image": image_url
                    })
                except Exception as e:
                    st.session_state.messages.append({
                        "role": "assistant", "avatar": st.session_state.ai_icon, "content": f"⚠️ お絵描き中にエラーが起きちゃいました。時間をおいてね: {e}"
                    })
                
                if st.session_state.image_count >= TARGET_IMAGES and st.session_state.level < 999:
                    st.session_state.level += 1
                    st.session_state.image_count = 0 
                st.rerun()
                    
        st.write("---")
        st.markdown('<div style="background-color: #222222; padding: 10px; text-align: center; border-radius: 5px; color: #888888; border: 1px dashed #444444; font-size: 12px; margin-top: 50px;">📢 ここに【サイドバー広告】<br>が表示されます</div>', unsafe_allow_html=True)

    st.subheader(f"💬 {st.session_state.ai_name} とのトークルーム")
    if st.session_state.learned_styles: st.caption(f"🧠 記憶している好み: " + ", ".join(st.session_state.learned_styles))
    st.write("---")

    for msg in st.session_state.messages:
        current_avatar = msg.get("avatar", st.session_state.user_icon if msg["role"] == "user" else st.session_state.ai_icon)
        with st.chat_message(msg["role"], avatar=current_avatar): 
            st.write(msg["content"])
            if "image" in msg: st.image(msg["image"])
            
    # 💬 本物のGrokとのおしゃべり通信処理（鉄壁の受け取りガード版）
    if user_message := st.chat_input("AIにメッセージを送る..."):
        st.session_state.messages.append({"role": "user", "avatar": st.session_state.user_icon, "content": user_message})
        st.session_state.exp += 1
        
        api_messages = [{"role": "system", "content": CHARACTER_PROMPTS[st.session_state.ai_type]}]
        for msg in st.session_state.messages:
            if "【お絵描きリクエスト】" not in msg["content"]:
                api_messages.append({"role": msg["role"], "content": msg["content"]})
        
        try:
            if not grok_key:
                reply_text = "（サーバーの設定に XAI_API_KEY が登録されていないみたい…！管理画面から設定してね）"
            else:
                completion = client.chat.completions.create(
                    model="x-ai/grok-2", 
                    messages=api_messages
                )
                
                # 🛡️ 返ってきたデータが本物の文字オブジェクト（正常系）か、エラー文字列（異常系）かを自動で検知してガードします
                if hasattr(completion, 'choices') and completion.choices:
                    reply_text = completion.choices[0].message.content
                elif isinstance(completion, dict) and "choices" in completion:
                    reply_text = completion["choices"][0]["message"]["content"]
                else:
                    # もしOpenRouter側でクレジット（残高）が足りないなどのエラー文が返ってきた場合は、その中身をそのまま親切に日本語で出力します
                    reply_text = f"（OpenRouterから文字データではなく、エラーメッセージが届いているみたい。中身：{str(completion)}）"
                    
        except Exception as e:
            reply_text = f"（あぅ…頭がうまく働かないよぅ…エラーが出ちゃった：{e}）"

        if st.session_state.level < 4:
            if st.session_state.exp >= TARGET_EXP:
                st.session_state.level += 1
                st.session_state.exp = 0

