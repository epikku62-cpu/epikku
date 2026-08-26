import streamlit as st
import random
import os
import json
import hashlib
from PIL import Image
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
            "ad_count": st.session_state.get("ad_count
