
import streamlit as st
import random
import os
from PIL import Image
from openai import OpenAI

st.set_page_config(page_title="AI育成お絵描きサイト", page_icon="🎨")

# 🌟 獲得したGrokのAPIキーをここに組み込んでいます
GROK_API_KEY = ""

# 本番サーバーからは、細工なしの公式ルートで100%安全にGrokに接続できます
client = OpenAI(
    api_key=GROK_API_KEY,
    base_url="https://x.ai",
)

# 画面最上部 広告枠
st.markdown('<div style="background-color: #333333; padding: 10px; text-align: center; border-radius: 5px; color: #aaaaaa; border: 1px dashed #666666; margin-bottom: 20px;">📢 ここにGoogleアドセンスなどの【バナー広告】が表示されます</div>', unsafe_allow_html=True)

st.title("🎨 専属絵師AI 育成ルーム")
st.markdown("### **いっぱい会話して自分好みの絵師AIを育てよう！**")
st.caption("本物のAIがあなたの好みを学習し、世界に1つのイラストを生み出します。")
st.write("---")

if "ai_name" not in st.session_state: st.session_state.ai_name = None  
if "level" not in st.session_state: st.session_state.level = 1
if "exp" not in st.session_state: st.session_state.exp = 0
if "messages" not in st.session_state: st.session_state.messages = []
if "learned_styles" not in st.session_state: st.session_state.learned_styles = [] 
if "image_count" not in st.session_state: st.session_state.image_count = 0 
if "user_icon" not in st.session_state: st.session_state.user_icon = "👤"
if "ai_icon" not in st.session_state: st.session_state.ai_icon = "🤖"

TARGET_EXP, TARGET_IMAGES = 5, 10

if st.session_state.ai_name is None:
    st.subheader("👶 まだ名前がありません")
    input_name = st.text_input("AIの名前を入力してください：", placeholder="例：めぐみん、アリスなど")
    if st.button("この名前に決定する！"):
        if input_name.strip() != "":
            st.session_state.ai_name = input_name
            st.rerun() 
else:
    with st.sidebar:
        st.markdown(f"### 📊 【 {st.session_state.ai_name} 】のステータス")
        st.metric(label="現在のレベル", value=f"Lv.{st.session_state.level} / 999")
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
                st.session_state.messages.append({"role": "assistant", "avatar": st.session_state.ai_icon, "content": f"🖼️ お兄ちゃんは『{tag}』みたいな絵柄が好きなんだね！覚えたよ！"})
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
                        model="grok-2-image-gen",
                        prompt=full_prompt,
                        n=1,
                        size="1024x1024"
                    )
                    image_url = response.data.url
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "avatar": st.session_state.ai_icon, 
                        "content": f"🎨 お兄ちゃんの好みの『{styles_text}』をたっぷり混ぜてお絵描きしたよ！『{prompt_input}』のイラストをどうぞ！",
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
            
    if user_message := st.chat_input("AIにメッセージを送る..."):
        st.session_state.messages.append({"role": "user", "avatar": st.session_state.user_icon, "content": user_message})
        st.session_state.exp += 1
        level_up_flag = False
        
        if st.session_state.level < 4:
            if st.session_state.exp >= TARGET_EXP:
                st.session_state.level += 1
                st.session_state.exp = 0
                level_up_flag = True

        if st.session_state.level == 1: reply_text = "ばぶー！"
        elif st.session_state.level == 2: reply_text = "きみの好きなアニメやタイプを教えて！"
        elif st.session_state.level == 3: reply_text = "左のメニューから『画像』をアップロードしてね！"
        else: reply_text = f"今のボクのレベルは【Lv.{st.session_state.level}】だよ！お絵描きを頼んでね！"

        try:
            completion = client.chat.completions.create(
                model="grok-2",
                messages=[
                    {"role": "system", "content": reply_text},
                    {"role": "user", "content": user_message}
                ]
            )
            grok_reply = completion.choices.message.content
        except Exception as e:
            grok_reply = f"（通信エラーが発生しました: {e}）"

        st.session_state.messages.append({"role": "assistant", "avatar": st.session_state.ai_icon, "content": grok_reply})
        st.rerun()
