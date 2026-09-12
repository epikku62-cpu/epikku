import streamlit as st
import html as html_lib
import os
import json
import uuid
import base64
import hashlib
import math
import io
import zipfile
import random
import re
import secrets
import socket
import smtplib
import subprocess
import time
import requests
import shutil
import tempfile
from email.mime.text import MIMEText
from io import BytesIO
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

try:
    import fcntl
except ImportError:
    fcntl = None

try:
    import stripe
except ImportError:
    stripe = None

st.set_page_config(page_title="panel AI.", page_icon="🎨", layout="wide", initial_sidebar_state="collapsed")

GSC = os.environ.get("GOOGLE_SITE_VERIFICATION", "")
if GSC:
    st.markdown(f'<meta name="google-site-verification" content="{GSC}">', unsafe_allow_html=True)

NAI_KEY = os.environ.get("NOVELAI_API_KEY", "")
XAI_KEY = os.environ.get("XAI_API_KEY", "")
MINIMAX_KEY = os.environ.get("MINIMAX_API_KEY", "")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
SITE_URL = os.environ.get("SITE_URL", "https://panelai.jp")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
MAIL_FROM = os.environ.get("MAIL_FROM", os.environ.get("SMTP_FROM", ""))
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
OWNER_ACCOUNTS = [x.strip().lower() for x in os.environ.get("OWNER_ACCOUNTS", "").split(",") if x.strip()]
CONTACT_TO = "panel.com@gmail.com"
if stripe is not None and STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

def stripe_ref():
    return str(st.session_state.get("username") or st.session_state.get("email") or "").strip()

def stripe_checkout(mode, line_items, success_url=None, cancel_url=None, metadata=None):
    # Payment Linkの「hosted_confirmation」を使い、決済後にPanelAIへ戻さない。
    # 1回の購入につき1つのPayment Linkを作り、1回だけ利用可能にする。
    if stripe is None:
        raise Exception("Stripeが設定されていません")

    items = []
    for item in line_items or []:
        row = dict(item)
        price_data = row.pop("price_data", None)
        if price_data:
            # Payment Linkのprice_dataはStripe APIバージョンによって利用できない場合があるため、
            # 互換性を優先してPriceを先に作成してからPayment Linkへ渡す。
            price = stripe.Price.create(**price_data)
            row["price"] = str(sget(price, "id") or "")
        if not row.get("price"):
            raise Exception("Stripeの価格情報を作成できませんでした")
        items.append(row)

    payload = {
        "line_items": items,
        "after_completion": {
            "type": "hosted_confirmation",
            "hosted_confirmation": {
                "custom_message": "決済が完了しました。\nこの画面を閉じて、元のpanel AI.の画面に戻ってください。戻るボタンは押さなくて大丈夫です。",
            },
        },
        "restrictions": {
            "completed_sessions": {"limit": 1},
        },
        "inactive_message": "この決済リンクは使用済みです。元のpanel AI.の画面に戻ってください。",
    }
    if metadata:
        payload["metadata"] = {str(k): str(v) for k, v in metadata.items()}
    if mode not in ("payment", "subscription"):
        raise Exception(f"未対応の決済モードです: {mode}")
    return stripe.PaymentLink.create(**payload)

def sget(obj, key, default=""):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    try:
        return obj[key]
    except Exception:
        return getattr(obj, key, default)

def mark_paid_session(session_id):
    paid = load_json(PAID_FILE, {})
    if not isinstance(paid, dict):
        paid = {}
    if session_id in paid:
        return False
    paid[session_id] = datetime.now().isoformat()
    save_json(PAID_FILE, paid)
    return True

def _subscription_value(sub, key, default=""):
    value = getattr(sub, key, None)
    if value is None and isinstance(sub, dict):
        value = sub.get(key)
    return value if value is not None else default

def _latest_invoice_paid(sub):
    """現在の請求書が実際にpaidかをStripeで確認する。確認できない場合はFalse。"""
    invoice_ref = _subscription_value(sub, "latest_invoice", "")
    if not invoice_ref:
        return False
    try:
        if isinstance(invoice_ref, dict):
            invoice = invoice_ref
        else:
            invoice = stripe.Invoice.retrieve(str(invoice_ref))
    except Exception:
        return False
    status = str(sget(invoice, "status") or "").lower()
    paid = sget(invoice, "paid", False)
    return status == "paid" or paid is True

def _clear_vip_state():
    """Stripe上で契約継続を確認できない場合、VIPを即時終了する。"""
    st.session_state.premium_until = ""
    save_user_state()

def sync_subscription(force=False):
    if stripe is None or not st.session_state.get("logged_in"):
        return
    sub_id = str(st.session_state.get("stripe_sub") or "").strip()
    if not sub_id:
        return
    now = time.time()
    last_check = float(st.session_state.get("_stripe_sync_at") or 0)
    if not force and now - last_check < 30:
        return
    st.session_state._stripe_sync_at = now
    try:
        sub = stripe.Subscription.retrieve(sub_id)
    except Exception:
        return

    status = str(_subscription_value(sub, "status", "")).lower()
    # 解約・支払い失敗など、継続を確認できない状態ならVIPを続けない。
    if status not in ("active", "trialing"):
        _clear_vip_state()
        return

    # 「自動決済が確認できた場合だけ」次の1200ポイントを付与する。
    # 初回決済もCheckout Session側でpaid確認済みだが、ここでも最新Invoiceを確認する。
    if not _latest_invoice_paid(sub):
        _clear_vip_state()
        return

    end_ts = _subscription_value(sub, "current_period_end", None)
    start_ts = _subscription_value(sub, "current_period_start", None)
    try:
        if end_ts:
            st.session_state.premium_until = datetime.fromtimestamp(int(end_ts)).isoformat()
        # 初回と自動更新で同じキーを使い、二重付与を防止する。
        period = str(int(start_ts)) if start_ts else ""
    except Exception:
        period = ""
    if not period:
        _clear_vip_state()
        return

    if st.session_state.get("stripe_period") != period:
        st.session_state.points = int(st.session_state.points or 0) + MONTHLY_POINTS
        st.session_state.stripe_period = period
    save_user_state()

def cancel_subscription_now():
    """Stripe上の月額契約を即時解約し、同時にPanel AI.のVIPも終了する。"""
    if stripe is None:
        return False, "Stripeが設定されていません"
    sub_id = str(st.session_state.get("stripe_sub") or "").strip()
    if not sub_id:
        return False, "月額契約情報がありません"
    try:
        # cancel_at_period_endではなく即時解約。途中解約なら、その時点でVIPを終了する。
        stripe.Subscription.cancel(sub_id)
    except AttributeError:
        try:
            stripe.Subscription.delete(sub_id)
        except Exception as e:
            return False, str(e)
    except Exception as e:
        return False, str(e)
    st.session_state.premium_until = ""
    st.session_state.stripe_sub = ""
    st.session_state.stripe_customer = ""
    save_user_state()
    return True, "月額VIPを解約しました。VIPはここで終了しました。"

def credit_pending_checkouts(force=False):
    if stripe is None or not st.session_state.get("logged_in"):
        return
    now = time.time()
    last_check = float(st.session_state.get("_stripe_checkout_at") or 0)
    if not force and now - last_check < 10:
        return
    st.session_state._stripe_checkout_at = now
    name = str(st.session_state.get("username") or "").strip()
    mail = str(st.session_state.get("email") or "").strip()
    if not name:
        return
    try:
        listed = stripe.checkout.Session.list(limit=40)
        rows = listed.data if hasattr(listed, "data") else []
    except Exception:
        return
    for ses in rows:
        meta = sget(ses, "metadata") or {}
        if not isinstance(meta, dict):
            meta = {}
        ref = str(sget(ses, "client_reference_id") or "")
        user = str(meta.get("user") or "")
        details = sget(ses, "customer_details") or {}
        det_mail = str(sget(details, "email") or "")
        keys = [x.strip() for x in (ref, user, det_mail) if str(x).strip()]
        if not keys:
            continue
        if name not in keys and mail not in keys:
            continue
        pay = str(sget(ses, "payment_status") or "")
        stt = str(sget(ses, "status") or "")
        if pay != "paid" and stt != "complete":
            continue
        sid = str(sget(ses, "id") or "")
        if sid:
            apply_checkout_session(sid)

def apply_checkout_session(session_id):
    if not session_id or stripe is None:
        return "決済を確認できません"
    try:
        ses = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        return str(e)
    pay = str(sget(ses, "payment_status") or "")
    stt = str(sget(ses, "status") or "")
    if pay not in ("paid", "no_payment_required") and stt != "complete":
        return "まだ支払いが完了していません"
    meta = sget(ses, "metadata") or {}
    if not isinstance(meta, dict):
        meta = {}
    mode = str(sget(ses, "mode") or meta.get("kind") or "")

    # 月額VIPはCheckout Sessionのsubscriptionを保存し、
    # 実際のcurrent_period_startを基準にsync_subscription()だけで
    # 1200ポイントを1回だけ付与する。
    # apply側とsync側で判定形式を変えないのが重要。
    if mode == "subscription" or str(meta.get("kind") or "") == "plan":
        sub_id = str(sget(ses, "subscription") or "").strip()
        if not sub_id:
            return "月額契約情報を取得できませんでした。少し待ってから再読み込みしてください"
        st.session_state.stripe_sub = sub_id
        st.session_state.stripe_customer = str(sget(ses, "customer") or "")
        save_user_state()
        before = int(st.session_state.get("points") or 0)
        old_period = str(st.session_state.get("stripe_period") or "")
        sync_subscription(force=True)
        after = int(st.session_state.get("points") or 0)
        if after > before:
            return f"月額を反映しました。+{after - before}ポイント"
        if str(st.session_state.get("stripe_period") or "") == old_period and old_period:
            return "月額VIPはすでに反映済みです"
        return "月額VIPを確認しました"

    # ポイント購入
    sid = str(sget(ses, "id") or session_id)
    if not mark_paid_session(sid):
        return "この決済は反映済みです"
    pts = 0
    try:
        pts = int(meta.get("points") or 0)
    except Exception:
        pts = 0
    if pts <= 0:
        amt = int(sget(ses, "amount_total") or 0)
        for pack in POINT_PACKS:
            if pack["yen"] == amt:
                pts = pack["points"]
                break
    if pts <= 0:
        return "ポイント数を判別できませんでした。管理者に連絡してください"
    st.session_state.points = int(st.session_state.points) + pts
    save_user_state()
    return f"{pts}ポイントを追加しました"

NAI_URLS = ["https://image.novelai.net/ai/generate-image", "https://api.novelai.net/ai/generate-image"]
DATA_DIR = os.environ.get("DATA_DIR", os.path.abspath("data"))
os.makedirs(DATA_DIR, exist_ok=True)
DATA_FILE = os.path.join(DATA_DIR, "studio_data.json")
USERS_FILE = os.path.join(DATA_DIR, "users_data.json")
TOKENS_FILE = os.path.join(DATA_DIR, "login_tokens.json")
PAID_FILE = os.path.join(DATA_DIR, "paid_sessions.json")
STATS_FILE = os.path.join(DATA_DIR, "visit_stats.json")
BOARD_FILE = os.path.join(DATA_DIR, "board_data.json")
BOARD_DIR = os.path.join(DATA_DIR, "board")
os.makedirs(BOARD_DIR, exist_ok=True)
BOARD_MAX_POSTS = 80
BOARD_MAX_COMMENTS = 40
HOME_IMG = "IMG_1106.jpeg"
HEADER_IMG = "IMG_1107.jpeg"
HOME_EXAMPLE_1 = "data:image/jpeg;base64,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"
HOME_EXAMPLE_2 = "data:image/jpeg;base64,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"
HOME_EXAMPLE_3 = "data:image/jpeg;base64,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0hxpxtzKFpPUEUtbhstcUtgHvrzB9HjU98i64j6biyVLs0lt6Q/GXxSyQngpB5p44GBwOa9SjkK8p0xjLoAABRRRViQooooAooooAooooAooooAooooAooooAooooAooooAooooAooooAooooAooooAqrvpC6ocseiPqyMtSJV7dEJKx91vGXDnxSMe+rRqrfpG2UXLZw/NSgF61yGpiFdQN7dV8lfKi7B52bbSyhLaBhKRgVtQCFAEdRmivXXXBDCiiipICiiigwFFFFCQrBrVbqGxla0pHia2abkSf9niyHR3pRgfE1aMJS+1ZKSnGPbLL2X6pQ5B/k7KXh+MFKikn+kazkpHik54dxqfC4t4P85UpWCAkJ61QTNivKlIda7GG4hQWhxThK0HvG7yNTy0a0uttS21eY5nIQc+lw0+tn9ts/mk+6vJ1not+XZXHg3o9Sp+yUixBOU4kKQytYI4HIGaTuzX0uBJaQA5+NzgMUwJ1/Yt3CJzCAAfVcStKhwyPV3c8+FNt01u7MQWrPFU4SCBIkNlDSOPMA+so46cBXm0+n6i2WyMHk656ymEdzkhBtP1LvR27MgJS6+UuvpTyS2n2R/EePkKrznUid0w1Kfcky7hPekOnedcKwN9Xfy5eFaK0lGA9SbMT5qSr9K+t0not1NeMcnh2+q1TlkYKKeV6UcH9HcT5ONA/MUnd07cms7gjvgfgWUk+41rLQ3R7iTHW0y8jbTZckYez3gU7SI8iL/tEd1kd6k8PiOFN1wwtCFjB5jINclkJR4kjojOMlmLHXZbcPqraZpmVvbqTMDCj4OJKP1r2mOVeC4ko2+4QpoO6qLJafB7t1YNe8WnEutpcQcpWAoHvBrzL19RojeiiisSQooooAooooAooooAooooAooooAqP7QLsLDoq+XMq3THgvLSf2t0gfMipBVVfSUu31fsykREqwu4yWYoA5kb2+r5JouweW7M2R6OlXMDJp/pstTY7ZRH3U4p0616tawirMVglOPW9nIz5ZratVp3klPeMVMllNBHqD0lCdwpKQgMoCfLn/AKVs1KSpSsHiBy5Goto+7m9aftktJBWllKHATj10eqR8s++n8yFEgLTuqPjn35r5CxNSaZ60VwbpkOLWSN4q3vaz6uO6syHPtcjqONJxuJVvpGCe48K5LcaKipa+Oce1jlVCyQodIUnl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"
VID_DIR = os.path.join(DATA_DIR, "video_tmp")
PHONE_W, PHONE_H = 1080, 1920
MONTHLY_PRICE, MONTHLY_POINTS, REF_SITE, SIGNUP_POINTS = 980, 1200, 10, 20
VIDEO_PT_PER_SEC = 30
JOIN_COST = 20
MAX_UPLOAD_SEC = 10
WAIT_SEC = 60
POINT_PACKS = [{"points": 300, "yen": 300}, {"points": 900, "yen": 900}, {"points": 1500, "yen": 1500}, {"points": 3000, "yen": 3000}]
ANIMALS = ["🐱", "🐶", "🐰", "🐻", "🦊", "🐼", "🐸", "🦉", "🐧", "🐯"]
LAYOUTS = {"縦4": {"cols": 1, "count": 4}, "縦3": {"cols": 1, "count": 3}, "縦2": {"cols": 1, "count": 2}, "横4": {"cols": 4, "count": 4}, "横3": {"cols": 3, "count": 3}, "横2": {"cols": 2, "count": 2}, "2×2": {"cols": 2, "count": 4}}
SIZES = {
    "横長": {"wh": (PHONE_W, PHONE_H // 4), "gen": (1216, 832), "cost": 0, "paid": False},
    "縦長": {"wh": (PHONE_H // 4, PHONE_W), "gen": (832, 1216), "cost": 0, "paid": False},
    "正方形": {"wh": (512, 512), "gen": (1024, 1024), "cost": 0, "paid": False},
    "大・横 1536×1024": {"wh": (1536, 1024), "gen": (1536, 1024), "cost": 52, "paid": True},
    "大・縦 1024×1536": {"wh": (1024, 1536), "gen": (1024, 1536), "cost": 52, "paid": True},
    "大・正 1472×1472": {"wh": (1472, 1472), "gen": (1472, 1472), "cost": 72, "paid": True},
    "壁紙・横 1920×1088": {"wh": (1920, 1088), "gen": (1920, 1088), "cost": 68, "paid": True},
    "壁紙・縦 1088×1920": {"wh": (1088, 1920), "gen": (1088, 1920), "cost": 68, "paid": True},
}
SIMPLE_SIZES = {
    "横長 1216×832": {"gen": (1216, 832), "cost": 10, "paid": False},
    "縦長 832×1216": {"gen": (832, 1216), "cost": 10, "paid": False},
    "正方形 1024×1024": {"gen": (1024, 1024), "cost": 10, "paid": False},
    "大・横 1536×1024": {"gen": (1536, 1024), "cost": 60, "paid": True},
    "大・縦 1024×1536": {"gen": (1024, 1536), "cost": 60, "paid": True},
    "大・正 1472×1472": {"gen": (1472, 1472), "cost": 86, "paid": True},
    "壁紙・横 1920×1088": {"gen": (1920, 1088), "cost": 84, "paid": True},
    "壁紙・縦 1088×1920": {"gen": (1088, 1920), "cost": 84, "paid": True},
}
BUBBLE_TYPES = ["ふきだし", "叫び", "考え", "文字だけ"]
TAILS = ["下", "下左", "下右", "左", "右"]
TEXT_DIR = ["横書き", "縦書き"]
FONT_SPECS = {
    "ゴシック": {"file": "font_gothic.otf", "urls": ["https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf", "https://cdn.jsdelivr.net/gh/notofonts/noto-cjk@main/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf"]},
    "丸文字": {"file": "font_maru.ttf", "urls": ["https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/kosugimaru/KosugiMaru-Regular.ttf"]},
    "かわいい": {"file": "font_kawaii.ttf", "urls": ["https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/hachimarupop/HachiMaruPop-Regular.ttf"]},
    "手書き風": {"file": "font_te.ttf", "urls": ["https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/yuseimagic/YuseiMagic-Regular.ttf"]},
}
os.makedirs(VID_DIR, exist_ok=True)

def video_cost(sec):
    return max(1, int(sec)) * VIDEO_PT_PER_SEC

def is_owner():
    u = str(st.session_state.get("username") or "").strip().lower()
    e = norm_mail(st.session_state.get("email"))
    return bool(OWNER_ACCOUNTS) and (u in OWNER_ACCOUNTS or e in OWNER_ACCOUNTS)

def mark_visit():
    now = datetime.now()
    now_ts = now.timestamp()
    last = float(st.session_state.get("_visit_at") or 0)
    if now_ts - last < 600:
        return
    st.session_state._visit_at = now.timestamp()
    data = load_json(STATS_FILE, {"total": 0, "days": {}, "last": ""})
    if not isinstance(data, dict):
        data = {"total": 0, "days": {}, "last": ""}
    day = now.strftime("%Y/%m/%d")
    days = data.get("days") if isinstance(data.get("days"), dict) else {}
    days[day] = int(days.get(day, 0)) + 1
    if len(days) > 60:
        days = dict(sorted(days.items())[-60:])
    data["days"] = days
    data["total"] = int(data.get("total", 0)) + 1
    data["last"] = now.strftime("%Y/%m/%d %H:%M")
    save_json(STATS_FILE, data)
    if st.session_state.get("logged_in") and st.session_state.get("username"):
        touch_user_seen(st.session_state.get("username"))

def touch_user_seen(name):
    users = load_json(USERS_FILE, {})
    if name in users and isinstance(users[name], dict):
        users[name]["last_seen"] = datetime.now().strftime("%Y/%m/%d %H:%M")
        save_json(USERS_FILE, users)

def scroll_top():
    st.markdown("""
    <script>
    const d = window.parent ? window.parent.document : document;
    const main = d.querySelector('section.main') || d.scrollingElement || d.documentElement;
    if (main) main.scrollTo(0, 0);
    window.scrollTo(0, 0);
    if (d.body) d.body.scrollTop = 0;
    </script>
    """, unsafe_allow_html=True)

def go(page):
    st.session_state.page = page
    st.session_state.menu_open = False
    st.session_state.need_top = True
    st.query_params["p"] = page
    tok = str(st.session_state.get("auth_token") or "")
    if tok:
        st.query_params["auth"] = tok

def load_tokens():
    data = load_json(TOKENS_FILE, {})
    return data if isinstance(data, dict) else {}

def save_tokens(data):
    save_json(TOKENS_FILE, data)

def issue_login_token(name):
    tokens = {k: v for k, v in load_tokens().items() if v != name}
    token = uuid.uuid4().hex
    tokens[token] = name
    save_tokens(tokens)
    st.session_state.auth_token = token
    st.query_params["auth"] = token
    return token

def clear_login_token(name=""):
    tok = str(st.session_state.get("auth_token") or st.query_params.get("auth") or "")
    tokens = load_tokens()
    if tok in tokens:
        tokens.pop(tok, None)
    if name:
        tokens = {k: v for k, v in tokens.items() if v != name}
    save_tokens(tokens)
    st.session_state.auth_token = ""
    if "auth" in st.query_params:
        del st.query_params["auth"]

def restore_login():
    if st.session_state.get("logged_in") and st.session_state.get("username"):
        return
    token = str(st.query_params.get("auth") or st.session_state.get("auth_token") or "")
    if not token:
        return
    name = load_tokens().get(token)
    users = load_json(USERS_FILE, {})
    if name and name in users:
        st.session_state.auth_token = token
        # 初期表示時は保存・Stripe確認を行わず、画面表示を優先する。
        apply_login(name, users[name], persist=False, sync=False, pending=False)

def start_wait():
    st.session_state.wait_until = time.time() + WAIT_SEC

def lock_other_buttons():
    st.markdown("""
    <style>
    section.main .block-container { pointer-events: none; }
    .wait-ok, .wait-ok * { pointer-events: auto !important; }
    </style>
    """, unsafe_allow_html=True)

def show_countdown_wait(label, key):
    left = int(math.ceil(st.session_state.get("wait_until", 0) - time.time()))
    if st.session_state.get("act_busy"):
        st.markdown(f'<div style="margin:8px 0;padding:12px;border-radius:14px;background:#fff0f6;color:#ff4d88;font-weight:800;">{label}… 処理中です。触らないでください</div>', unsafe_allow_html=True)
        return None
    if left > 0:
        st.markdown(f'<div style="margin:8px 0;padding:12px;border-radius:14px;background:#fff0f6;color:#ff4d88;font-weight:800;">{label}… {left}</div>', unsafe_allow_html=True)
        if st.button("キャンセル", key=f"can_{key}"):
            return "cancel"
        time.sleep(1)
        st.rerun()
    st.markdown(f'<div style="margin:8px 0;padding:12px;border-radius:14px;background:#fff0f6;color:#ff4d88;font-weight:800;">{label}… 結果を確認しています</div>', unsafe_allow_html=True)
    return "confirm"

@st.cache_data(show_spinner=False)
def file_b64(path):
    if not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def norm_mail(m):
    return (m or "").strip().lower()

def valid_mail_format(m):
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", norm_mail(m)) is not None

def mail_domain_ok(m):
    try:
        socket.getaddrinfo(norm_mail(m).split("@", 1)[1], 80)
        return True
    except Exception:
        return False

def send_mail(to_addr, subject, body):
    if RESEND_API_KEY and MAIL_FROM:
        res = requests.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"}, json={"from": MAIL_FROM, "to": [to_addr], "subject": subject, "text": body}, timeout=20)
        return res.status_code in (200, 201), res.text[:200]
    if SMTP_HOST and SMTP_USER and SMTP_PASS and MAIL_FROM:
        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = MAIL_FROM
            msg["To"] = to_addr
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
                s.starttls()
                s.login(SMTP_USER, SMTP_PASS)
                s.sendmail(MAIL_FROM, [to_addr], msg.as_string())
            return True, ""
        except Exception as e:
            return False, str(e)
    return False, "メール送信設定がありません"

def send_code_mail(to_addr, code):
    return send_mail(to_addr, "panel AI. 登録確認", f"確認コード: {code}\nこのコードをサイトに入力してください。")

def _read_json_file(path):
    if not path or not os.path.exists(path) or os.path.getsize(path) <= 2:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception:
        return None

def load_json(path, default):
    data = _read_json_file(path)
    if data is not None:
        return data
    data = _read_json_file(path + ".bak")
    if data is not None:
        try:
            save_json(path, data)
        except Exception:
            pass
        return data
    old = os.path.basename(path)
    if os.path.abspath(old) != os.path.abspath(path):
        data = _read_json_file(old)
        if data is not None:
            try:
                save_json(path, data)
            except Exception:
                pass
            return data
    return default

def save_json(path, data, backup=True):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    folder = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=folder)
    locked = None
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            if fcntl is not None:
                try:
                    locked = open(path + ".lock", "a+", encoding="utf-8")
                    fcntl.flock(locked.fileno(), fcntl.LOCK_EX)
                except Exception:
                    locked = None
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        if backup and os.path.exists(path) and os.path.getsize(path) > 2:
            try:
                shutil.copy2(path, path + ".bak")
            except Exception:
                pass
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
        if locked is not None:
            try:
                fcntl.flock(locked.fileno(), fcntl.LOCK_UN)
                locked.close()
            except Exception:
                pass

def email_taken(users, mail):
    mail = norm_mail(mail)
    return any(isinstance(v, dict) and norm_mail(v.get("email")) == mail for v in users.values())

def find_user(users, key):
    if key in users:
        return key
    k = norm_mail(key)
    for name, v in users.items():
        if isinstance(v, dict) and (norm_mail(v.get("email")) == k or name == key):
            return name
    return None

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
    return {name: download_one(spec["file"], spec["urls"]) for name, spec in FONT_SPECS.items()}

def load_font(size=28, kind="ゴシック"):
    size = max(12, int(size))
    spec = FONT_SPECS.get(kind) or FONT_SPECS["ゴシック"]
    for path in [spec["file"], FONT_SPECS["ゴシック"]["file"]]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()

def uploaded_to_uri(uploaded):
    return f"data:{uploaded.type or 'image/png'};base64,{base64.b64encode(uploaded.getvalue()).decode()}"

def uri_to_image(uri):
    if not uri:
        return None
    if uri.startswith("data:"):
        return Image.open(BytesIO(base64.b64decode(uri.split(",", 1)[1]))).convert("RGB")
    res = requests.get(uri, timeout=90)
    res.raise_for_status()
    return Image.open(BytesIO(res.content)).convert("RGB")

def shrink_for_video(image_uri):
    img = uri_to_image(image_uri)
    img.thumbnail((768, 768))
    buf = BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

def save_upload_mp4(uploaded):
    path = os.path.join(VID_DIR, f"up_{uuid.uuid4().hex}.mp4")
    with open(path, "wb") as f:
        f.write(uploaded.getvalue())
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        sec = float((r.stdout or "0").strip() or 0)
    except Exception:
        sec = 0
    if sec <= 0:
        os.remove(path)
        raise Exception("動画の長さが読めません。mp4にしてください")
    if sec > MAX_UPLOAD_SEC + 0.3:
        os.remove(path)
        raise Exception(f"10秒以下のmp4だけ使えます。今は {sec:.1f}秒です")
    return path

def file_to_data_uri(path, mime="video/mp4"):
    with open(path, "rb") as f:
        raw = f.read()
    if len(raw) > 45 * 1024 * 1024:
        raise Exception("ファイルが大きすぎます")
    return f"data:{mime};base64," + base64.b64encode(raw).decode()

def pad_ref(uri):
    img = uri_to_image(uri).convert("RGB")
    tw, th = 1024, 1536
    canvas = Image.new("RGB", (tw, th), (0, 0, 0))
    img.thumbnail((tw, th))
    canvas.paste(img, ((tw - img.width) // 2, (th - img.height) // 2))
    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def is_premium():
    until = st.session_state.get("premium_until") or ""
    try:
        return bool(until) and datetime.fromisoformat(until) > datetime.now()
    except Exception:
        return False

def member_label():
    return "VIP" if is_premium() else "ブロンズ"

def save_user_state():
    users = load_json(USERS_FILE, {})
    name = st.session_state.get("username")
    if not name:
        return
    prev = users.get(name) if isinstance(users.get(name), dict) else {}
    users[name] = {
        "password": prev.get("password") or st.session_state.get("password_hash", ""),
        "email": st.session_state.get("email") or prev.get("email", ""),
        "icon": st.session_state.get("icon", prev.get("icon", "")),
        "characters": st.session_state.get("characters", prev.get("characters", [])),
        "points": int(st.session_state.get("points", prev.get("points", 0))),
        "signup_points_remaining": (int(st.session_state.get("signup_points_remaining"))
                                    if "signup_points_remaining" in st.session_state
                                    else prev.get("signup_points_remaining")),
        "community_seen_at": float(st.session_state.get("community_seen_at", prev.get("community_seen_at", 0)) or 0),
        "premium_until": st.session_state.get("premium_until") or prev.get("premium_until", ""),
        "rank": "vip" if is_premium() else "ブロンズ",
        "history": st.session_state.get("simple_history", prev.get("history", []))[-30:],
        "library": st.session_state.get("library", prev.get("library", []))[-40:],
        "last_seen": datetime.now().strftime("%Y/%m/%d %H:%M") if st.session_state.get("logged_in") else prev.get("last_seen", ""),
        "stripe_sub": st.session_state.get("stripe_sub") or prev.get("stripe_sub", ""),
        "stripe_customer": st.session_state.get("stripe_customer") or prev.get("stripe_customer", ""),
        "stripe_period": st.session_state.get("stripe_period") or prev.get("stripe_period", ""),
    }
    if not users[name]["password"] and prev.get("password"):
        users[name]["password"] = prev["password"]
    if prev.get("password") and not users[name]["password"]:
        users[name]["password"] = prev["password"]
    save_json(USERS_FILE, users, backup=False)
    save_json(DATA_FILE, {"characters": st.session_state.characters})

def load_board():
    data = load_json(BOARD_FILE, {"posts": []})
    if not isinstance(data, dict):
        data = {"posts": []}
    data["posts"] = [p for p in data.get("posts", []) if isinstance(p, dict)]
    return data

def board_last_activity(data=None):
    data = data if isinstance(data, dict) else load_board()
    latest = float(data.get("updated_at") or 0)
    for post in data.get("posts", []):
        try:
            latest = max(latest, float(post.get("updated_at") or post.get("ts") or 0))
        except Exception:
            pass
        for c in post.get("comments") or []:
            try:
                latest = max(latest, float(c.get("ts") or 0))
            except Exception:
                pass
    return latest

def community_unread_count():
    if not st.session_state.get("logged_in"):
        return 0
    seen = float(st.session_state.get("community_seen_at") or 0)
    latest = board_last_activity()
    return 1 if latest > seen else 0

def mark_community_seen():
    if not st.session_state.get("logged_in") or not st.session_state.get("username"):
        return
    latest = board_last_activity()
    st.session_state.community_seen_at = latest
    users = load_json(USERS_FILE, {})
    name = st.session_state.get("username")
    if name in users and isinstance(users[name], dict):
        users[name]["community_seen_at"] = latest
        save_json(USERS_FILE, users, backup=False)

def save_board(data):
    posts = data.get("posts", [])[-BOARD_MAX_POSTS:]
    data_out = {"posts": posts, "updated_at": float(data.get("updated_at") or 0)}
    save_json(BOARD_FILE, data_out)

def board_image_path(pid):
    return os.path.join(BOARD_DIR, f"{pid}.jpg")

def save_board_image(uri, pid):
    img = uri_to_image(uri).convert("RGB")
    img.thumbnail((1280, 1280))
    path = board_image_path(pid)
    img.save(path, format="JPEG", quality=82)
    return path

def board_image_uri(post):
    path = post.get("image") or ""
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    return post.get("url") or ""

def add_library(uri, label="", extra=None):
    if not uri:
        return
    item = {"id": str(uuid.uuid4())[:8], "url": uri, "label": label or "保存画像"}
    if extra:
        item.update(extra)
    item["time"] = datetime.now().strftime("%Y/%m/%d %H:%M")
    st.session_state.library.append(item)
    save_user_state()

def site_work_kind(item):
    label = str((item or {}).get("label") or "")
    if label.startswith("画像生成") or (item or {}).get("kind") == "simple":
        return "simple"
    if "4コマ" in label:
        return "yonkoma"
    return ""

def prompt_from_history(url):
    for item in reversed(st.session_state.get("simple_history") or []):
        if item.get("url") == url:
            return item
    for item in reversed(st.session_state.get("library") or []):
        if item.get("url") == url and site_work_kind(item) == "simple":
            return item
    return {}

def apply_simple_settings(item):
    """履歴・作品投稿から画像生成モードの全設定を復元する。"""
    item = item or {}
    chars = list(item.get("chars") or [""]) or [""]
    st.session_state.sq = item.get("quality") or ""
    st.session_state.sb = item.get("background") or ""
    st.session_state.so = item.get("other") or ""
    st.session_state.sn = item.get("negative") or ""
    st.session_state.schars = chars[:3]
    bubbles = list(item.get("bubbles") or [])
    while len(bubbles) < len(st.session_state.schars):
        bubbles.append("")
    st.session_state.sbubbles = bubbles[:len(st.session_state.schars)]
    for i in range(3):
        st.session_state[f"scarea_{i}"] = st.session_state.schars[i] if i < len(st.session_state.schars) else ""
        st.session_state[f"sbb_{i}"] = st.session_state.sbubbles[i] if i < len(st.session_state.sbubbles) else ""
    st.session_state.simple_seed = "" if item.get("seed") is None else str(item.get("seed"))
    st.session_state.simple_size = str(item.get("size") or "")
    try:
        st.session_state.simple_scale = max(1.0, min(10.0, float(item.get("scale", 5.0))))
    except Exception:
        st.session_state.simple_scale = 5.0
    try:
        st.session_state.simple_steps = max(1, min(28, int(item.get("steps", 20))))
    except Exception:
        st.session_state.simple_steps = 20
    st.session_state.simple_sampler = str(item.get("sampler") or "Euler Ancestral")

def take_points(cost):
    if is_owner() or int(cost) <= 0:
        return
    if st.session_state.points < cost:
        raise Exception(f"ポイントが足りません。必要 {cost}")
    cost = int(cost)
    st.session_state.points -= cost
    # 新規登録特典20ポイントの残量を追跡（既存ユーザーには後付けしない）
    if "signup_points_remaining" in st.session_state:
        st.session_state.signup_points_remaining = max(0, int(st.session_state.get("signup_points_remaining") or 0) - cost)
    save_user_state()

def finish_action():
    st.session_state.act_busy = False

def nai_wh(w, h):
    return max(64, min(1920, int(round(w / 64) * 64))), max(64, min(1920, int(round(h / 64) * 64)))

def nai_request(prompt, width, height, model, steps=23, scale=5.0, negative="", char_texts=None, char_refs=None, style_refs=None, sampler="k_euler_ancestral", seed=None):
    if not NAI_KEY:
        raise Exception("NOVELAI_API_KEY がありません")
    gw, gh = nai_wh(width, height)
    char_texts = [x.strip() for x in (char_texts or []) if x and x.strip()][:3]
    char_refs = [x for x in (char_refs or []) if x.get("uri")][:3]
    style_refs = [x for x in (style_refs or []) if x.get("uri")][:3]
    char_captions, character_prompts = [], []
    xs, ys = [0.3, 0.7, 0.5], [0.5, 0.5, 0.72]
    for i, txt in enumerate(char_texts):
        char_captions.append({"char_caption": txt, "centers": [{"x": xs[i], "y": ys[i]}]})
        character_prompts.append({"prompt": txt, "uc": "", "center": {"x": xs[i], "y": ys[i]}, "enabled": True})
    parameters = {
        "params_version": 3, "width": gw, "height": gh, "scale": float(scale),
        "sampler": str(sampler or "k_euler_ancestral"), "steps": int(steps), "n_samples": 1,
        "qualityToggle": False, "ucPreset": 0, "negative_prompt": negative or "",
        "noise_schedule": "karras", "use_coords": True, "characterPrompts": character_prompts,
        "v4_prompt": {"caption": {"base_caption": prompt or "", "char_captions": char_captions}, "use_coords": True, "use_order": True},
        "v4_negative_prompt": {"caption": {"base_caption": negative or "", "char_captions": []}, "legacy_uc": False},
    }
    if seed is not None:
        parameters["seed"] = int(seed)
    base_input = (prompt or "").strip()
    if not base_input and char_texts:
        base_input = char_texts[0]
    if not base_input:
        raise Exception("プロンプトを入れてください")
    parameters["v4_prompt"]["caption"]["base_caption"] = base_input
    if model.startswith("nai-diffusion-4-5") or model.startswith("nai-diffusion-5"):
        refs, kinds = [], []
        if char_refs and style_refs:
            refs.append(pad_ref(char_refs[0]["uri"])); kinds.append("character&style")
        elif char_refs:
            refs.append(pad_ref(char_refs[0]["uri"])); kinds.append("character")
        elif style_refs:
            refs.append(pad_ref(style_refs[0]["uri"])); kinds.append("style")
        if refs:
            parameters["director_reference_images"] = refs
            parameters["director_reference_descriptions"] = [{"caption": {"base_caption": kinds[0], "char_captions": []}, "legacy_uc": False}]
            parameters["director_reference_information_extracted"] = [1]
            parameters["director_reference_strength_values"] = [1]
            parameters["director_reference_secondary_strength_values"] = [0.75]
    models = [model]
    if model.startswith("nai-diffusion-5"):
        parameters["params_version"] = 4
    last_err = None
    for mdl in models:
        payload = {"input": base_input, "model": mdl, "action": "generate", "parameters": parameters}
        for url in NAI_URLS:
            res = requests.post(url, headers={"Authorization": f"Bearer {NAI_KEY}", "Content-Type": "application/json"}, json=payload, timeout=180)
            if res.status_code == 200:
                with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
                    return "data:image/png;base64," + base64.b64encode(zf.read(zf.namelist()[0])).decode()
            last_err = f"{res.status_code}: {res.text[:400]}"
    raise Exception(last_err or "NovelAIの生成に失敗しました")

def mm_headers():
    if not MINIMAX_KEY:
        raise Exception("MINIMAX_API_KEY がありません")
    return {"Authorization": f"Bearer {MINIMAX_KEY}", "Content-Type": "application/json"}

def mm_upload_path(path, filename):
    if not MINIMAX_KEY:
        raise Exception("MINIMAX_API_KEY がありません")
    with open(path, "rb") as f:
        res = requests.post(
            "https://api.minimax.io/v1/files/upload",
            headers={"Authorization": f"Bearer {MINIMAX_KEY}"},
            data={"purpose": "video_generation_input"},
            files={"file": (filename, f)},
            timeout=120,
        )
    if res.status_code not in (200, 201):
        raise Exception(f"アップロード失敗 {res.status_code}: {res.text[:400]}")
    data = res.json()
    fid = (data.get("file") or {}).get("file_id") or data.get("file_id")
    if fid is None:
        raise Exception(f"file_idがありません: {str(data)[:400]}")
    return f"mm_file://{fid}"

def mm_upload_image_uri(image_uri):
    raw = image_uri
    if "," in raw and str(raw).startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        blob = base64.b64decode(raw)
    except Exception:
        raise Exception("画像を送れません")
    path = os.path.join(VID_DIR, f"mm_{uuid.uuid4().hex}.jpg")
    with open(path, "wb") as f:
        f.write(blob)
    try:
        return mm_upload_path(path, "ref.jpg")
    finally:
        try:
            os.remove(path)
        except Exception:
            pass

def mm_create_video(payload):
    res = requests.post("https://api.minimax.io/v2/video_generation", headers=mm_headers(), json=payload, timeout=60)
    if res.status_code not in (200, 201, 202):
        raise Exception(f"{res.status_code}: {res.text[:500]}")
    data = res.json()
    task_id = data.get("task_id") or (data.get("task") or {}).get("id")
    if not task_id:
        raise Exception(f"task_idがありません: {str(data)[:400]}")
    return task_id

def grok_start_video(image_uri, prompt, duration=6):
    img = mm_upload_image_uri(shrink_for_video(image_uri))
    dur = max(5, min(15, int(duration)))
    payload = {
        "model": "MiniMax-H3-Max",
        "content": [
            {"type": "text", "text": prompt or "subtle natural motion, keep the same character and style"},
            {"type": "image_url", "image_url": {"url": img}, "role": "first_frame"},
        ],
        "resolution": "768P",
        "duration": dur,
    }
    return mm_create_video(payload)

def mm_start_move(image_uri, video_path, prompt, duration=6):
    img = mm_upload_image_uri(shrink_for_video(image_uri))
    vid = mm_upload_path(video_path, "ref.mp4")
    dur = max(4, min(15, int(duration)))
    payload = {
        "model": "MiniMax-H3",
        "content": [
            {"type": "text", "text": prompt or "The character from the reference image performs the same motion as the reference video."},
            {"type": "image_url", "image_url": {"url": img}, "role": "reference_image"},
            {"type": "video_url", "video_url": {"url": vid}, "role": "reference_video"},
        ],
        "resolution": "768P",
        "duration": dur,
    }
    return mm_create_video(payload)

def grok_poll_video(request_id):
    chk = requests.get(f"https://api.minimax.io/v2/query/video_generation/{request_id}", headers=mm_headers(), timeout=20)
    if chk.status_code != 200:
        return "wait", chk.text[:200]
    d = chk.json()
    task = d.get("task") if isinstance(d.get("task"), dict) else d
    status = str(task.get("status") or d.get("status") or "").lower()
    if status in ("succeeded", "success", "done"):
        content = task.get("content") if isinstance(task.get("content"), dict) else {}
        video_url = content.get("url") or task.get("url") or task.get("file_id") or d.get("file_id")
        if video_url is not None and not str(video_url).startswith("http"):
            rec = requests.get(
                "https://api.minimax.io/v1/files/retrieve",
                headers={"Authorization": f"Bearer {MINIMAX_KEY}"},
                params={"file_id": str(video_url).replace("mm_file://", "")},
                timeout=20,
            )
            if rec.status_code == 200:
                video_url = ((rec.json().get("file") or {}).get("download_url")) or video_url
        if not video_url or not str(video_url).startswith("http"):
            return "error", str(d)[:500]
        raw = requests.get(str(video_url), timeout=90)
        raw.raise_for_status()
        path = os.path.join(VID_DIR, f"{uuid.uuid4().hex}.mp4")
        with open(path, "wb") as f:
            f.write(raw.content)
        return "done", path
    if status in ("failed", "fail", "cancelled", "canceled"):
        return "error", str(task.get("error") or d.get("error_message") or d)[:400]
    return "wait", status or "pending"

def grok_wait_video(request_id, tries=24, gap=5):
    last = "wait"
    for _ in range(int(tries)):
        state, val = grok_poll_video(request_id)
        if state in ("done", "error"):
            return state, val
        last = val
        time.sleep(int(gap))
    return "wait", last

def probe_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return max(0.2, float((r.stdout or "0").strip() or 0))
    except Exception:
        return 3.0

def probe_wh(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        parts = (r.stdout or "").strip().split(",")
        return max(2, int(parts[0])), max(2, int(parts[1]))
    except Exception:
        return 640, 640

def even_size(n):
    n = max(2, int(round(n)))
    return n if n % 2 == 0 else n + 1

def layout_kind(layout_key, n):
    key = str(layout_key)
    if key.startswith("横"):
        return n, 1
    if key == "2×2":
        return 2, 2
    return 1, n

def panel_targets(paths, layout_key):
    n = len(paths)
    cols, rows = layout_kind(layout_key, n)
    sizes = [probe_wh(p) for p in paths]
    max_w = max(w for w, _h in sizes)
    max_h = max(h for _w, h in sizes)
    cap = 1080
    out = []
    if cols == 1:
        tw = even_size(min(cap, max_w))
        for w, h in sizes:
            out.append((tw, even_size(h * tw / max(w, 1))))
    elif rows == 1:
        th = even_size(min(cap, max_h))
        for w, h in sizes:
            out.append((even_size(w * th / max(h, 1)), th))
    else:
        tw = even_size(min(cap, max_w))
        for w, h in sizes:
            out.append((tw, even_size(h * tw / max(w, 1))))
    return cols, rows, out

def scale_filter(w, h):
    return f"fps=24,scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=white,setsar=1,format=yuv420p"

def stack_filter(cols, rows, n, labels, targets):
    joined = "".join(labels)
    if cols == 1:
        return joined + f"vstack=inputs={n}[out]"
    if rows == 1:
        return joined + f"hstack=inputs={n}[out]"
    w0, h0 = targets[0]
    w1, h1 = targets[1] if n > 1 else targets[0]
    w2, h2 = targets[2] if n > 2 else targets[0]
    layout = f"0_0|{w0}_0|0_{h0}|{w0}_{h0}"
    return joined + f"xstack=inputs={n}:layout={layout}[out]"

def has_audio(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "csv=p=0", path], capture_output=True, text=True)
    return bool((r.stdout or "").strip())

def concat_videos(paths, out_path, keep_audio=False):
    lst = os.path.join(VID_DIR, f"{uuid.uuid4().hex}.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for p in paths:
            f.write(f"file '{os.path.abspath(p)}'\n")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if keep_audio:
        cmd += ["-c:a", "aac", "-b:a", "128k"]
    else:
        cmd += ["-an"]
    cmd.append(out_path)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out_path):
        raise Exception(r.stderr[-400:] if r.stderr else "結合に失敗しました")
    return out_path

def run_compose_ffmpeg(ins, filt, out_path, keep_audio=False, extra=None, audio_map=None):
    cmd = ["ffmpeg", "-y"] + ins + ["-filter_complex", filt, "-map", "[out]"]
    if keep_audio and audio_map:
        cmd += ["-map", audio_map, "-c:a", "aac", "-b:a", "128k"]
    else:
        cmd += ["-an"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if extra:
        cmd += extra
    cmd.append(out_path)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out_path):
        raise Exception((r.stderr or "結合失敗")[-500:])
    return out_path

def compose_yonkoma_video(paths, layout_key="2×2", out_path="out.mp4", sequential=False, keep_audio=False):
    n = len(paths)
    if n < 2:
        raise Exception("2本以上必要です")
    cols, rows, targets = panel_targets(paths, layout_key)
    audio_flags = [has_audio(p) for p in paths]
    if not sequential:
        ins = []
        for p in paths:
            ins += ["-i", p]
        parts, labels = [], []
        for i in range(n):
            tw, th = targets[i]
            parts.append(f"[{i}:v]{scale_filter(tw, th)}[v{i}]")
            labels.append(f"[v{i}]")
        filt = ";".join(parts) + ";" + stack_filter(cols, rows, n, labels, targets)
        audio_map = None
        if keep_audio and any(audio_flags):
            a_parts, alabels = [], []
            for i, ok in enumerate(audio_flags):
                if ok:
                    a_parts.append(f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a{i}]")
                    alabels.append(f"[a{i}]")
            if len(alabels) == 1:
                filt = filt + ";" + a_parts[0]
                audio_map = alabels[0]
            elif len(alabels) > 1:
                filt = filt + ";" + ";".join(a_parts) + ";" + "".join(alabels) + f"amix=inputs={len(alabels)}:duration=shortest:dropout_transition=0[aout]"
                audio_map = "[aout]"
        return run_compose_ffmpeg(ins, filt, out_path, keep_audio=keep_audio, extra=["-shortest"], audio_map=audio_map)
    durs = [probe_duration(p) for p in paths]
    segs = []
    for k in range(n):
        ins = []
        for p in paths:
            ins += ["-i", p]
        parts, labels = [], []
        for i in range(n):
            tw, th = targets[i]
            sc = scale_filter(tw, th)
            if i == k:
                parts.append(f"[{i}:v]{sc},setpts=PTS-STARTPTS[v{i}]")
            else:
                parts.append(f"[{i}:v]trim=start=0:end=0.05,loop=-1:size=1,setpts=N/24/TB,{sc},trim=duration={durs[k]:.3f},setpts=PTS-STARTPTS[v{i}]")
            labels.append(f"[v{i}]")
        filt = ";".join(parts) + ";" + stack_filter(cols, rows, n, labels, targets)
        audio_map = None
        if keep_audio and audio_flags[k]:
            filt += f";[{k}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,atrim=duration={durs[k]:.3f},asetpts=PTS-STARTPTS[aout]"
            audio_map = "[aout]"
        seg = os.path.join(VID_DIR, f"seq_{k}_{uuid.uuid4().hex}.mp4")
        run_compose_ffmpeg(ins, filt, seg, keep_audio=keep_audio, extra=["-t", f"{durs[k]:.3f}"], audio_map=audio_map)
        segs.append(seg)
    return concat_videos(segs, out_path, keep_audio=keep_audio)

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

def draw_text(draw, xy, text, font, fill, bold=0):
    x, y = xy
    if bold <= 0:
        draw.text((x, y), text, font=font, fill=fill)
        return
    for dx in range(-bold, bold + 1):
        for dy in range(-bold, bold + 1):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=font, fill=fill)
    draw.text((x, y), text, font=font, fill=fill)

def paste_layer(img, layer, px, py):
    sx = max(0, -px)
    sy = max(0, -py)
    dx = max(0, px)
    dy = max(0, py)
    cw = min(layer.width - sx, img.width - dx)
    ch = min(layer.height - sy, img.height - dy)
    if cw > 0 and ch > 0:
        img.alpha_composite(layer.crop((sx, sy, sx + cw, sy + ch)), (dx, dy))
    return img

def draw_one_bubble(img, bub):
    text = (bub.get("text") or "").strip()
    if not text:
        return img
    img = img.convert("RGBA")
    size, bold, tail_size = int(bub.get("size", 28)), int(bub.get("bold", 0)), int(bub.get("tail_size", 28))
    font = load_font(size, bub.get("font", "ゴシック"))
    w, h = img.size
    kind, direction = bub.get("kind", "ふきだし"), bub.get("dir", "横書き")
    fill, color, tail = bub.get("fill", "#ffffff"), bub.get("color", "#111111"), bub.get("tail", "下")
    pad = 22 if kind == "叫び" else 16
    max_w = int(w * (0.72 if kind == "叫び" else 0.62))
    if direction == "縦書き":
        lines = list(text.replace("\n", ""))
        box_w = size + pad * 2 + bold * 2
        box_h = pad * 2 + int(size * 1.15) * len(lines) + bold * 2
    else:
        lines = wrap_text(text, font, max_w)
        try:
            text_w = max(font.getlength(x) for x in lines)
        except Exception:
            text_w = max(len(x) * size for x in lines)
        box_w = int(text_w + pad * 2 + bold * 2)
        box_h = int(pad * 2 + int(size * 1.3) * len(lines) + bold * 2)
    if kind == "叫び":
        box_w = int(box_w * 1.25)
        box_h = int(box_h * 1.28)
    extra = tail_size + 48
    layer = Image.new("RGBA", (box_w + extra * 2, box_h + extra * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x0, y0 = extra, extra
    if kind == "ふきだし":
        draw.rounded_rectangle([x0, y0, x0 + box_w, y0 + box_h], radius=22, fill=fill, outline="#222222", width=3)
        ts = tail_size
        if tail == "下":
            tpts = [(x0 + box_w * 0.38, y0 + box_h - 2), (x0 + box_w * 0.52, y0 + box_h - 2), (x0 + box_w * 0.34, y0 + box_h + ts)]
        elif tail == "下左":
            tpts = [(x0 + 18, y0 + box_h - 2), (x0 + 18 + ts * 0.7, y0 + box_h - 2), (x0 + 8, y0 + box_h + ts)]
        elif tail == "下右":
            tpts = [(x0 + box_w - 18 - ts * 0.7, y0 + box_h - 2), (x0 + box_w - 18, y0 + box_h - 2), (x0 + box_w - 8, y0 + box_h + ts)]
        elif tail == "左":
            tpts = [(x0 + 2, y0 + box_h * 0.45), (x0 + 2, y0 + box_h * 0.62), (x0 - ts, y0 + box_h * 0.58)]
        else:
            tpts = [(x0 + box_w - 2, y0 + box_h * 0.45), (x0 + box_w - 2, y0 + box_h * 0.62), (x0 + box_w + ts, y0 + box_h * 0.58)]
        draw.polygon(tpts, fill=fill)
        draw.line([tpts[0], tpts[2], tpts[1]], fill="#222222", width=3)
    elif kind == "叫び":
        pts = []
        for i in range(32):
            ang = math.pi * 2 * i / 32
            rx = box_w / 2 * (1.38 if i % 2 == 0 else 0.98)
            ry = box_h / 2 * (1.38 if i % 2 == 0 else 0.98)
            pts.append((x0 + box_w / 2 + math.cos(ang) * rx, y0 + box_h / 2 + math.sin(ang) * ry))
        draw.polygon(pts, fill=fill, outline="#222222")
    elif kind == "考え":
        draw.rounded_rectangle([x0, y0, x0 + box_w, y0 + box_h], radius=28, fill=fill, outline="#222222", width=3)
        draw.ellipse([x0 + 16, y0 + box_h + 6, x0 + 16 + tail_size * 0.5, y0 + box_h + 6 + tail_size * 0.5], fill=fill, outline="#222222")
    if direction == "縦書き":
        cy = y0 + pad
        for ch in lines:
            try:
                tw = font.getlength(ch)
            except Exception:
                tw = size
            draw_text(draw, (x0 + (box_w - tw) / 2, cy), ch, font, color, bold)
            cy += int(size * 1.15)
    else:
        ty = y0 + pad - 2
        for line in lines:
            try:
                lw = font.getlength(line)
            except Exception:
                lw = len(line) * size
            tx = x0 + (box_w - lw) / 2 if kind == "叫び" else x0 + pad
            draw_text(draw, (tx, ty), line, font, color, bold)
            ty += int(size * 1.3)
    angle = int(bub.get("angle", 0))
    if angle:
        layer = layer.rotate(-angle, expand=True, resample=Image.BICUBIC)
        px = int((w - box_w) * float(bub.get("x", 8)) / 100) - (layer.width - box_w) // 2
        py = int((h - box_h) * float(bub.get("y", 8)) / 100) - (layer.height - box_h) // 2
    else:
        px = int((w - box_w) * float(bub.get("x", 8)) / 100) - extra
        py = int((h - box_h) * float(bub.get("y", 8)) / 100) - extra
    return paste_layer(img, layer, px, py).convert("RGB")

def draw_all_bubbles(panel_img, bubbles):
    img = panel_img
    for bub in bubbles or []:
        img = draw_one_bubble(img, bub)
    return img

def combine_panels(images, cols=2):
    gap, n = 8, len(images)
    rows = (n + cols - 1) // cols
    col_w = [max((images[i].width for i in range(n) if i % cols == c), default=0) for c in range(cols)]
    row_h = [max((images[i].height for i in range(n) if i // cols == r), default=0) for r in range(rows)]
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

def show_header():
    if os.path.exists(HEADER_IMG):
        st.image(HEADER_IMG, use_container_width=True)

def panel_raw(i):
    raw = uri_to_image(st.session_state.panel_images[i])
    if not st.session_state.panel_upload[i]:
        raw = raw.resize(st.session_state.panel_sizes[i])
    return raw

def empty_bubble():
    return {"text": "", "x": 8, "y": 8, "angle": 0, "fill": "#ffffff", "color": "#111111", "size": 28, "bold": 0, "tail_size": 28, "kind": "ふきだし", "font": "ゴシック", "dir": "横書き", "tail": "下"}

def apply_login(name, data, persist=True, sync=True, pending=True):
    st.session_state.logged_in = True
    st.session_state.username = name
    st.session_state.email = data.get("email", "")
    st.session_state.password_hash = data.get("password", "")
    st.session_state.icon = data.get("icon", random.choice(ANIMALS))
    st.session_state.characters = data.get("characters", [])
    st.session_state.points = int(data.get("points", 0))
    if "signup_points_remaining" in data:
        st.session_state.signup_points_remaining = int(data.get("signup_points_remaining") or 0)
    else:
        st.session_state.pop("signup_points_remaining", None)
    # 既存ユーザーは、最初のログイン時点より前の投稿を未読扱いにしない。
    if "community_seen_at" in data:
        st.session_state.community_seen_at = float(data.get("community_seen_at") or 0)
    else:
        st.session_state.community_seen_at = board_last_activity()
    st.session_state.premium_until = data.get("premium_until", "")
    st.session_state.simple_history = data.get("history", [])
    st.session_state.library = data.get("library", [])
    st.session_state.stripe_sub = data.get("stripe_sub", "")
    st.session_state.stripe_customer = data.get("stripe_customer", "")
    st.session_state.stripe_period = data.get("stripe_period", "")
    if not st.session_state.get("auth_token"):
        issue_login_token(name)
    if persist:
        save_user_state()
    if sync:
        sync_subscription()
    if pending:
        credit_pending_checkouts()

def render_top_menu():
    left, _ = st.columns([1, 3])
    with left:
        label = "閉じる" if st.session_state.menu_open else "メニュー"
        if st.button(label, key="panel_menu_toggle", use_container_width=True):
            st.session_state.menu_open = not st.session_state.menu_open
            st.rerun()
    if not st.session_state.menu_open:
        return
    st.markdown('<div style="background:#fff;border:3px solid #111;border-radius:20px;padding:12px;margin:8px 0 16px;">', unsafe_allow_html=True)
    st.markdown("**メニュー**")
    if st.session_state.logged_in:
        icon = st.session_state.get("icon", "🐱")
        if isinstance(icon, str) and icon.startswith("data:image"):
            st.image(icon, width=48)
        else:
            st.write(icon)
        st.write(st.session_state.get("username", ""))
        if st.button("アイコン変更", use_container_width=True):
            go("icon"); st.rerun()
        if st.button("ログアウト", use_container_width=True):
            clear_login_token(st.session_state.get("username") or "")
            st.session_state.logged_in = False
            st.session_state.username = ""
            go("home"); st.rerun()
    else:
        if st.button("登録", use_container_width=True):
            go("register"); st.rerun()
        if st.button("ログイン", use_container_width=True):
            go("register"); st.rerun()
        st.markdown(
            '<div style="background:#fff0f6;border:2px solid #ff6ea8;border-radius:16px;padding:10px 12px;margin:10px 0;text-align:center;color:#ff4d88;font-weight:800;line-height:1.5;">'
            '🎁 新規登録で<strong>20ポイント</strong>プレゼント！<br>'
            '登録後すぐに画像生成を試せます。'
            '</div>',
            unsafe_allow_html=True,
        )
    st.write(f"ポイント {st.session_state.points}")
    st.write(f"会員 {member_label() if st.session_state.logged_in else '未登録'}")
    community_badge = " 🔴" if community_unread_count() else ""
    menu_items = [(f"👥 コミュニティ{community_badge}", "board"), ("画像生成モード", "simple"), ("セット", "chars"), ("4コマ", "make"), ("保存庫", "lib"), ("動画生成", "video"), ("4コマ動画", "v4"), ("動画を移す", "vmove"), ("ポイント購入", "shop"), ("説明書", "help"), ("月額登録", "plan"), ("お問い合わせ", "contact")]
    if is_owner():
        menu_items.append(("来場", "stats"))
    for label, page in menu_items:
        if st.button(label, use_container_width=True, key=f"m_{page}"):
            go(page); st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

def get_usable_fonts():
    font_status = prepare_fonts()
    return [k for k, ok in font_status.items() if ok] or ["ゴシック"]
defaults = {
    "logged_in": False, "page": "home", "auth_token": "", "layout": "縦4", "scenes": ["", "", "", ""],
    "scene_chars": ["セットなし"] * 4, "panel_images": [None] * 4, "panel_upload": [False] * 4,
    "panel_sizes": [SIZES["横長"]["wh"]] * 4, "panel_shape": ["横長"] * 4,
    "panel_bubbles": [[], [], [], []], "drafts": [empty_bubble() for _ in range(4)],
    "error": "", "busy_index": None, "combined": None, "points": 0, "premium_until": "",
    "simple_image": None, "simple_busy": False, "simple_history": [], "show_history": False, "simple_size": "", "simple_scale": 5.0, "simple_steps": 20, "simple_sampler": "Euler Ancestral",
    "hist_pick": None, "sq": "", "sb": "", "so": "", "sn": "", "schars": [""], "sbubbles": [""],
    "icon": random.choice(ANIMALS), "email": "", "pending": None, "library": [], "signup_just_completed": False,
    "video_src": None, "video_out": None, "v4_clips": [None] * 4, "v4_prompts": ["", "", "", ""],
    "v4_durs": [5, 5, 5, 5], "v4_count": 4, "v4_layout": "2×2", "v4_play": "同時に動く",
    "v4_joined": None, "vjob": None, "v4_joining": False, "do_join": False, "v4_audio": "音声を消す", "board_id": "", "community_seen_at": 0, "wait_until": 0, "_booted": False,
    "menu_open": False, "need_top": True, "act_busy": False, "password_hash": "", "characters": [],
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v
if not st.session_state._booted:
    st.session_state._booted = True
    if st.query_params.get("p"):
        st.session_state.page = st.query_params.get("p")
    if st.query_params.get("bid"):
        st.session_state.board_id = str(st.query_params.get("bid"))
        st.session_state.page = "board"

qs = st.query_params
restore_login()
mark_visit()
if qs.get("bid"):
    st.session_state.board_id = str(qs.get("bid"))
    st.session_state.page = "board"
if qs.get("session_id"):
    if st.session_state.logged_in:
        st.session_state.error = apply_checkout_session(str(qs.get("session_id")))
    else:
        st.session_state.error = "ログインしてから同じ決済ページを開き直してください"
    if "session_id" in st.query_params:
        del st.query_params["session_id"]
    go("shop")
if "checkout" in qs:
    if "checkout" in st.query_params:
        del st.query_params["checkout"]
if "buypoints" in qs:
    if "buypoints" in st.query_params:
        del st.query_params["buypoints"]

st.markdown("""
<style>
section[data-testid="stSidebar"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"],
[data-testid="stStatusWidget"],
[data-testid="stToolbar"],
[data-testid="stHeaderActionElements"],
[data-testid="stDecoration"],
#MainMenu { display: none !important; }
div[data-testid="stButton"] > button {
  background: #ffffff !important;
  color: #111111 !important;
  border: 2px solid #111111 !important;
  border-radius: 999px !important;
  font-weight: 800 !important;
  box-shadow: none !important;
}
div[data-testid="stButton"] > button[kind="primary"] {
  background: #ffffff !important;
  color: #111111 !important;
  border: 2px solid #111111 !important;
  box-shadow: none !important;
}
section.main div[data-testid="stHorizontalBlock"]:first-of-type div[data-testid="column"]:first-child div[data-testid="stButton"] > button {
  background: linear-gradient(180deg,#ffc1dc,#ff6ea8) !important;
  color: #ffffff !important;
  border: 3px solid #ffffff !important;
  box-shadow: 0 5px 0 #ff4d88 !important;
}
</style>
""", unsafe_allow_html=True)

render_top_menu()
if st.session_state.get("need_top"):
    scroll_top()
    st.session_state.need_top = False

if st.session_state.page == "home":
    b64 = file_b64(HOME_IMG)
    if b64:
        st.markdown(f'<style>.stApp{{background-image:linear-gradient(rgba(255,255,255,.18),rgba(255,255,255,.18)),url("data:image/jpeg;base64,{b64}");background-size:cover;background-position:center;}}</style>', unsafe_allow_html=True)
    st.markdown("<div style='height:28vh'></div>", unsafe_allow_html=True)
    st.markdown("""
    <div style="text-align:center;color:#ff4d88;font-size:20px;font-weight:800;line-height:1.7;
    background:rgba(255,255,255,.82);padding:16px 14px;border-radius:22px;border:3px solid #ffb6d5;">
    panel AIは<br>4コマ画像・4コマ動画<br>画像生成・動画生成<br>作成AIサイト ♡
    </div>
    """, unsafe_allow_html=True)
    if not st.session_state.logged_in:
        st.markdown("""
        <div style="text-align:center;color:#ff4d88;font-size:19px;font-weight:800;line-height:1.6;
        background:rgba(255,240,246,.96);padding:12px 14px;margin:12px 0 8px;border-radius:18px;border:3px solid #ff6ea8;">
        🎁 新規登録で<strong>20ポイント</strong>プレゼント！<br>
        登録後すぐに画像を作れます
        </div>
        """, unsafe_allow_html=True)
        mid_cta = st.columns([1, 2, 1])
        with mid_cta[1]:
            if st.button("無料で20ポイントGET", type="primary", use_container_width=True, key="home_signup_cta"):
                go("register"); st.rerun()
    st.markdown("<div style='text-align:center;color:#ff4d88;font-size:18px;font-weight:800;margin:12px 0 8px;'>作品例</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='display:flex;gap:8px;justify-content:center;align-items:flex-start;overflow:hidden;margin:0 0 14px;'>"
        f"<img src='{HOME_EXAMPLE_1}' style='width:32%;height:190px;object-fit:cover;border-radius:14px;border:2px solid #fff;'>"
        f"<img src='{HOME_EXAMPLE_2}' style='width:32%;height:190px;object-fit:cover;border-radius:14px;border:2px solid #fff;'>"
        f"<img src='{HOME_EXAMPLE_3}' style='width:32%;height:190px;object-fit:cover;border-radius:14px;border:2px solid #fff;'>"
        f"</div>", unsafe_allow_html=True
    )
    mid = st.columns([1, 2, 1])
    with mid[1]:
        if st.button("👥 コミュニティ", use_container_width=True, key="home_community"):
            go("board"); st.rerun()
        if st.button("panel", use_container_width=True, key="home_panel"):
            go("help"); st.rerun()
    st.stop()

show_header()

if st.session_state.error:
    st.error(st.session_state.error)
    if st.button("通知を閉じる"):
        st.session_state.error = ""; st.rerun()

if st.session_state.page == "help":
    st.markdown(f"""<div style="color:#111;background:#fff;padding:16px;border-radius:12px;">
    <h2>画像生成モード</h2><p>ポイントを消費して画像生成<br>日本語で作成可能<br>おすすめ</p>
    <h2>セット</h2><p>絵柄の登録<br>キャラの登録<br>登録したら4コマ画像生成の時、絵柄、キャラが反映される</p>
    <h2>4コマ</h2><p>セット絵柄、キャラを使えて画像生成して、会話、吹き出しをつけれるよ！<br>最後に合体させて4コマ完成！</p>
    <h2>動画生成モード</h2><p>ポイントで動画生成<br>秒数が長いほどポイントが増える<br>4コマ動画も1コマずつポイント消費<br>自分のmp4（10秒以下）を入れてまとめることもできる<br>まとめは20ポイント</p>
    <h2>月額登録</h2><p>セット機能開放<br>サイズの変更開放<br>{MONTHLY_POINTS}ポイント付与</p></div>""", unsafe_allow_html=True)
    if st.button("登録して始めよう！", type="primary", use_container_width=True):
        go("register" if not st.session_state.logged_in else "simple"); st.rerun()

elif st.session_state.page == "lib":
    st.subheader("保存庫")
    if not st.session_state.library:
        st.write("まだありません。")
    for i, item in enumerate(reversed(st.session_state.library)):
        st.image(item["url"], width=160)
        st.caption(f"{item.get('label','')} {item.get('time','')}")
        a, b = st.columns(2)
        with a:
            if st.button("動画にする", key=f"libv_{i}"):
                st.session_state.video_src = item["url"]; go("video"); st.rerun()
        with b:
            if st.button("消す", key=f"libd_{i}"):
                st.session_state.library.pop(len(st.session_state.library) - 1 - i); save_user_state(); st.rerun()

elif st.session_state.page == "video":
    st.subheader("動画生成")
    job = st.session_state.get("vjob") if isinstance(st.session_state.get("vjob"), dict) else None
    if job and job.get("kind") == "video":
        act = show_countdown_wait("生成中", "video")
        if act == "cancel":
            finish_action(); st.session_state.vjob = None; go("video"); st.rerun()
        if act == "confirm":
            try:
                state, val = grok_wait_video(job["id"])
                if state == "done":
                    st.session_state.video_out = val; st.session_state.vjob = None
                elif state == "error":
                    st.session_state.error = val; st.session_state.vjob = None
                else:
                    st.session_state.error = "まだ生成中です。確認をもう一度押してください"
            except Exception as e:
                st.session_state.error = str(e)
                start_wait()
            finally:
                finish_action()
            go("video"); st.rerun()
    up = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"])
    if up:
        st.session_state.video_src = uploaded_to_uri(up)
    if st.session_state.library:
        picks = [f"{x.get('time','')} {x.get('label','')}" for x in st.session_state.library]
        sel = st.selectbox("保存庫から選ぶ", ["選ばない"] + picks)
        if sel != "選ばない":
            st.session_state.video_src = st.session_state.library[picks.index(sel)]["url"]
    if st.session_state.video_src:
        st.image(st.session_state.video_src, width=240)
    motion = st.text_area("動きの内容", placeholder="ゆっくり瞬きする")
    dur = st.slider("秒数", 5, 10, 6)
    st.caption(f"消費ポイント {video_cost(dur)}")
    if st.button("動画にする", type="primary"):
        if not st.session_state.video_src:
            st.session_state.error = "画像を選んでください"
        else:
            try:
                take_points(video_cost(dur))
                st.session_state.vjob = {"kind": "video", "id": grok_start_video(st.session_state.video_src, motion, dur)}
                start_wait(); st.session_state.error = ""
            except Exception as e:
                st.session_state.error = str(e)
        go("video"); st.rerun()
    if st.session_state.video_out and os.path.exists(st.session_state.video_out):
        st.video(st.session_state.video_out)
        with open(st.session_state.video_out, "rb") as f:
            st.download_button("動画を保存", data=f.read(), file_name="video.mp4", mime="video/mp4")

elif st.session_state.page == "vmove":
    st.subheader("動画を移す")
    st.markdown("＊確認が押せないように見えますが押せています。生成には10分以上かかる場合があります。気長に待ってください。再読み込みなど、画面を変えると生成できなくて、ポイントだけ失う可能性があります。そのままの状態で待ってください。失敗しても保証はいたしません。NSFWはできません。")
    job = st.session_state.get("vjob") if isinstance(st.session_state.get("vjob"), dict) else None
    vup = st.file_uploader("動きの動画", type=["mp4", "mov"])
    if vup is not None and st.button("この動画を使う"):
        try:
            st.session_state.vmove_vid = save_upload_mp4(vup)
            st.session_state.error = ""
        except Exception as e:
            st.session_state.error = str(e)
        go("vmove"); st.rerun()
    if st.session_state.get("vmove_vid") and os.path.exists(st.session_state.vmove_vid):
        st.video(st.session_state.vmove_vid)
    iup = st.file_uploader("キャラの画像", type=["png", "jpg", "jpeg"])
    if iup:
        st.session_state.vmove_img = uploaded_to_uri(iup)
    if st.session_state.library:
        picks = [f"{x.get('time','')} {x.get('label','')}" for x in st.session_state.library]
        sel = st.selectbox("保存庫から選ぶ", ["選ばない"] + picks, key="vmove_lib")
        if sel != "選ばない":
            st.session_state.vmove_img = st.session_state.library[picks.index(sel)]["url"]
    if st.session_state.get("vmove_img"):
        st.image(st.session_state.vmove_img, width=240)
    motion = st.text_area("動きの内容", placeholder="参考動画と同じ動きをする", key="vmove_txt")
    dur = st.slider("秒数", 5, 10, 6, key="vmove_dur")
    ref_sec = probe_duration(st.session_state.vmove_vid) if st.session_state.get("vmove_vid") and os.path.exists(st.session_state.vmove_vid) else 0
    cost = video_cost(dur) + video_cost(max(1, int(round(ref_sec)))) if ref_sec else video_cost(dur)
    st.caption(f"消費ポイント {cost}")
    if job and job.get("kind") == "vmove":
        act = show_countdown_wait("生成中", "vmove")
        if act == "cancel":
            finish_action(); st.session_state.vjob = None; go("vmove"); st.rerun()
        if act == "confirm":
            try:
                state, val = grok_wait_video(job["id"])
                if state == "done":
                    st.session_state.vmove_out = val; st.session_state.vjob = None
                elif state == "error":
                    st.session_state.error = val; st.session_state.vjob = None
                else:
                    time.sleep(5)
            except Exception as e:
                st.session_state.error = str(e)
                st.session_state.vjob = None
            finally:
                finish_action()
            go("vmove"); st.rerun()
    elif st.button("動画を移す", type="primary"):
        if not st.session_state.get("vmove_vid") or not os.path.exists(st.session_state.vmove_vid):
            st.session_state.error = "動きの動画を入れてください"
        elif not st.session_state.get("vmove_img"):
            st.session_state.error = "キャラの画像を選んでください"
        else:
            try:
                take_points(cost)
                st.session_state.vjob = {"kind": "vmove", "id": mm_start_move(st.session_state.vmove_img, st.session_state.vmove_vid, motion, dur)}
                start_wait(); st.session_state.error = ""
            except Exception as e:
                st.session_state.error = str(e)
        go("vmove"); st.rerun()
    if st.session_state.get("vmove_out") and os.path.exists(st.session_state.vmove_out):
        st.video(st.session_state.vmove_out)
        with open(st.session_state.vmove_out, "rb") as f:
            st.download_button("動画を保存", data=f.read(), file_name="move.mp4", mime="video/mp4")

elif st.session_state.page == "v4":
    st.subheader("4コマ動画")
    job = st.session_state.get("vjob") if isinstance(st.session_state.get("vjob"), dict) else None
    st.session_state.v4_count = st.radio("コマ数", [2, 3, 4], index=[2, 3, 4].index(int(st.session_state.v4_count)), horizontal=True)
    n = int(st.session_state.v4_count)
    layout_opts = {2: ["縦2", "横2"], 3: ["縦3", "横3"], 4: ["縦4", "横4", "2×2"]}[n]
    if st.session_state.v4_layout not in layout_opts:
        st.session_state.v4_layout = layout_opts[0]
    st.session_state.v4_layout = st.radio("並び", layout_opts, horizontal=True, index=layout_opts.index(st.session_state.v4_layout))
    st.session_state.v4_play = st.radio("再生", ["同時に動く", "順番に動く"], horizontal=True, index=0 if st.session_state.v4_play == "同時に動く" else 1)
    audio_opts = ["音声を消す", "音声を残す"]
    if st.session_state.get("v4_audio") not in audio_opts:
        st.session_state.v4_audio = "音声を消す"
    st.session_state.v4_audio = st.radio("音声", audio_opts, horizontal=True, index=audio_opts.index(st.session_state.v4_audio))
    for i in range(n):
        with st.expander(f"コマ {i+1}", expanded=True):
            src = st.session_state.panel_images[i]
            if st.session_state.library:
                picks = ["今の4コマ画像"] + [f"{x.get('time','')} {x.get('label','')}" for x in st.session_state.library]
                sel = st.selectbox("画像", picks, key=f"v4s_{i}")
                if sel != "今の4コマ画像":
                    src = st.session_state.library[picks.index(sel) - 1]["url"]
            up = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"], key=f"v4u_{i}")
            if up:
                src = uploaded_to_uri(up)
            if src:
                st.image(src, width=180)
            vup = st.file_uploader("動画をアップロード（mp4・10秒以下）", type=["mp4"], key=f"v4vu_{i}")
            if vup is not None and st.button("この動画を使う", key=f"v4vuse_{i}"):
                try:
                    st.session_state.v4_clips[i] = save_upload_mp4(vup); st.session_state.error = ""
                except Exception as e:
                    st.session_state.error = str(e)
                go("v4"); st.rerun()
            st.session_state.v4_prompts[i] = st.text_input("動き", value=st.session_state.v4_prompts[i], key=f"v4p_{i}")
            st.session_state.v4_durs[i] = st.slider("秒数", 5, 10, max(5, int(st.session_state.v4_durs[i])), key=f"v4d_{i}")
            if job and job.get("kind") == "v4" and int(job.get("i", -1)) == i:
                act = show_countdown_wait(f"コマ{i+1} 生成中", f"p{i}")
                if act == "cancel":
                    finish_action(); st.session_state.vjob = None; go("v4"); st.rerun()
                if act == "confirm":
                    try:
                        state, val = grok_wait_video(job["id"])
                        if state == "done":
                            st.session_state.v4_clips[i] = val; st.session_state.vjob = None
                        elif state == "error":
                            st.session_state.error = val; st.session_state.vjob = None
                        else:
                            start_wait(); st.session_state.error = "まだ生成中です。もう一度確認してください"
                    except Exception as e:
                        st.session_state.error = str(e)
                        start_wait()
                    finally:
                        finish_action()
                    go("v4"); st.rerun()
            if st.button("このコマを動画にする", key=f"v4g_{i}"):
                if not src:
                    st.session_state.error = "画像がありません"
                else:
                    try:
                        take_points(video_cost(st.session_state.v4_durs[i]))
                        st.session_state.vjob = {"kind": "v4", "i": i, "id": grok_start_video(src, st.session_state.v4_prompts[i], st.session_state.v4_durs[i])}
                        start_wait(); st.session_state.error = ""
                    except Exception as e:
                        st.session_state.error = str(e)
                go("v4"); st.rerun()
            if st.session_state.v4_clips[i] and os.path.exists(st.session_state.v4_clips[i]):
                st.video(st.session_state.v4_clips[i])
    ready_clips = [st.session_state.v4_clips[i] for i in range(n) if st.session_state.v4_clips[i] and os.path.exists(st.session_state.v4_clips[i])]
    st.subheader("まとめ")
    st.session_state.v4_joining = False
    if st.session_state.get("do_join"):
        st.markdown('<div style="margin:8px 0;padding:14px;border-radius:14px;background:#fff0f6;color:#ff4d88;font-weight:800;">動画をまとめています。画面を触らず、そのまま待ってください。</div>', unsafe_allow_html=True)
        try:
            take_points(JOIN_COST)
            out = os.path.join(VID_DIR, f"join_{uuid.uuid4().hex}.mp4")
            st.session_state.v4_joined = compose_yonkoma_video(ready_clips, st.session_state.v4_layout, out, sequential=(st.session_state.v4_play == "順番に動く"), keep_audio=(st.session_state.v4_audio == "音声を残す"))
            st.session_state.error = ""
        except Exception as e:
            st.session_state.error = str(e)
        st.session_state.do_join = False
        st.session_state.act_busy = False
        go("v4")
        st.rerun()
    if st.button("漫画動画としてまとめる", type="primary"):
        if len(ready_clips) < n:
            st.session_state.error = f"{n}本そろえてください"
        else:
            st.session_state.do_join = True
            st.session_state.vjob = None
            st.session_state.act_busy = False
            st.session_state.error = ""
        go("v4")
        st.rerun()
    if st.session_state.v4_joined and os.path.exists(st.session_state.v4_joined):
        st.video(st.session_state.v4_joined)
        with open(st.session_state.v4_joined, "rb") as f:
            st.download_button("漫画動画を保存", data=f.read(), file_name="manga.mp4", mime="video/mp4")

elif st.session_state.page == "icon":
    st.subheader("アイコン変更")
    if not st.session_state.logged_in:
        st.warning("ログインしてください"); st.stop()
    up = st.file_uploader("新しいアイコン", type=["png", "jpg", "jpeg"])
    if up:
        st.image(up, width=80)
    if st.button("この画像にする", type="primary") and up:
        st.session_state.icon = uploaded_to_uri(up); save_user_state(); st.rerun()
    if st.button("動物アイコンに戻す"):
        st.session_state.icon = random.choice(ANIMALS); save_user_state(); st.rerun()

elif st.session_state.page == "shop":
    if st.session_state.logged_in:
        credit_pending_checkouts(force=True)
    if st.session_state.logged_in:
        credit_pending_checkouts()
    st.subheader("ポイント購入")
    if not st.session_state.logged_in:
        st.warning("購入にはログインが必要です。")
    elif stripe is None or not STRIPE_SECRET_KEY:
        st.error("決済設定がまだです。")
    else:
        for pack in POINT_PACKS:
            c1, c2 = st.columns([3, 2])
            with c1:
                st.write(f"**{pack['points']}ポイント**")
            with c2:
                if st.button(f"{pack['yen']}円で買う", key=f"buy_{pack['points']}"):
                    try:
                        session = stripe_checkout(
                            "payment",
                            [{"price_data": {"currency": "jpy", "unit_amount": pack["yen"], "product_data": {"name": f"{pack['points']}ポイント"}}, "quantity": 1}],
                            None,
                            None,
                            {"kind": "points", "points": pack["points"], "user": st.session_state.get("username") or ""},
                        )
                        st.markdown(f"[決済ページへ進む]({session.url})")
                    except Exception as e:
                        st.error(str(e))

elif st.session_state.page == "register":
    st.subheader("登録 / ログイン")
    name = st.text_input("ユーザーネーム")
    mail = st.text_input("メールアドレス")
    pw = st.text_input("パスワード", type="password")
    icon_up = st.file_uploader("アイコン（任意）", type=["png", "jpg", "jpeg"])
    if icon_up:
        st.image(icon_up, width=80)
    if st.button("確認コードを送る"):
        users = load_json(USERS_FILE, {})
        if not name or not mail or not pw:
            st.warning("全部入れてください")
        elif not valid_mail_format(mail):
            st.error("メールの形が正しくありません")
        elif not mail_domain_ok(mail):
            st.error("存在しないアドレスです")
        elif name in users:
            st.error("その名前は使われています")
        elif email_taken(users, mail):
            st.error("このメールアドレスは登録済みです")
        else:
            code = f"{random.randint(100000, 999999)}"
            ok, err = send_code_mail(norm_mail(mail), code)
            if not ok:
                st.error(f"メールを送れませんでした: {err}")
            else:
                st.session_state.pending = {"name": name, "email": norm_mail(mail), "password": hash_password(pw), "icon": uploaded_to_uri(icon_up) if icon_up else random.choice(ANIMALS), "code": code}
                st.success("確認コードを送りました。")
    if st.session_state.pending:
        code_in = st.text_input("確認コード")
        if st.button("登録する", type="primary"):
            p = st.session_state.pending
            users = load_json(USERS_FILE, {})
            if code_in.strip() != p["code"]:
                st.error("コードが違います")
            elif email_taken(users, p["email"]) or p["name"] in users:
                st.error("すでに登録されています")
            else:
                users[p["name"]] = {"password": p["password"], "email": p["email"], "icon": p["icon"], "characters": [], "points": SIGNUP_POINTS, "signup_points_remaining": SIGNUP_POINTS, "community_seen_at": board_last_activity(), "premium_until": "", "rank": "ブロンズ", "history": [], "library": []}
                save_json(USERS_FILE, users)
                apply_login(p["name"], users[p["name"]])
                st.session_state.pending = None
                st.session_state.signup_just_completed = True
                go("simple"); st.rerun()
    st.write("ログイン")
    lu = st.text_input("メールまたはユーザーネーム", key="lu")
    lp = st.text_input("ログイン用パスワード", type="password", key="lp")
    if st.button("ログインする"):
        users = load_json(USERS_FILE, {})
        found = find_user(users, lu)
        if found and users[found]["password"] == hash_password(lp):
            apply_login(found, users[found]); go("simple"); st.rerun()
        else:
            st.error("ログインできません")

elif st.session_state.page == "contact":
    st.subheader("お問い合わせ")
    st.write(f"送信先: {CONTACT_TO}")
    cname = st.text_input("お名前")
    cmail = st.text_input("返信先メール")
    cbody = st.text_area("内容")
    if st.button("メールを送る", type="primary"):
        if not cname or not cmail or not cbody:
            st.warning("全部入れてください")
        elif not valid_mail_format(cmail):
            st.error("メールの形が正しくありません")
        else:
            ok, err = send_mail(CONTACT_TO, f"[panel AI] お問い合わせ {cname}", f"名前: {cname}\n返信先: {cmail}\nユーザー: {st.session_state.get('username','未ログイン')}\n\n{cbody}")
            st.success("送りました") if ok else st.error(f"送れませんでした: {err}")

elif st.session_state.page == "stats":
    st.subheader("来場・利用状況")
    if not is_owner():
        st.warning("管理者だけです")
        st.stop()
    data = load_json(STATS_FILE, {"total": 0, "days": {}, "last": ""})
    days = data.get("days") if isinstance(data.get("days"), dict) else {}
    today = datetime.now().strftime("%Y/%m/%d")
    yday = (datetime.now() - timedelta(days=1)).strftime("%Y/%m/%d")
    st.write(f"累計来場 {int(data.get('total', 0))}")
    st.write(f"今日 {int(days.get(today, 0))}")
    st.write(f"昨日 {int(days.get(yday, 0))}")
    st.write(f"最後 {data.get('last') or 'なし'}")

    users = load_json(USERS_FILE, {})
    valid_users = [(name, u) for name, u in users.items() if isinstance(u, dict)]
    registered = len(valid_users)
    image_users = []
    image_zero = []
    total_image_generations = 0
    signup_tracked = 0
    signup_remaining_zero = 0
    signup_remaining_positive = 0

    for name, u in valid_users:
        history = u.get("history") or []
        if not isinstance(history, list):
            history = []
        # historyには画像生成履歴が保存されているため、1件以上あれば画像生成経験あり。
        gen_count = len(history)
        total_image_generations += gen_count
        if gen_count > 0:
            image_users.append((name, gen_count, u))
        else:
            image_zero.append((name, u))

        if "signup_points_remaining" in u:
            signup_tracked += 1
            remaining = int(u.get("signup_points_remaining") or 0)
            if remaining <= 0:
                signup_remaining_zero += 1
            else:
                signup_remaining_positive += 1

    st.markdown("### 登録者の利用状況")
    st.write(f"登録者 {registered}人")
    st.write(f"画像生成した人 {len(image_users)}人")
    st.write(f"画像生成していない人 {len(image_zero)}人")
    st.write(f"画像生成回数（保存履歴ベース） {total_image_generations}回")

    if registered:
        st.write(f"登録 → 画像生成率 {len(image_users) / registered * 100:.1f}%")
    else:
        st.write("登録 → 画像生成率 -")

    st.markdown("### 新規登録20ポイントの利用状況")
    if signup_tracked:
        st.write(f"追跡対象 {signup_tracked}人")
        st.write(f"新規特典20ポイントを使い切った人 {signup_remaining_zero}人")
        st.write(f"新規特典ポイントが残っている人 {signup_remaining_positive}人")
        st.caption("※この項目は追跡機能追加後に登録したユーザーが対象です。購入ポイントなどが混ざるため、既存ユーザーの20ポイント消費状況は推測していません。")
    else:
        st.write("まだ追跡対象の登録者はいません")

    with st.expander("画像生成した登録者"):
        if image_users:
            for name, gen_count, _u in sorted(image_users, key=lambda x: x[1], reverse=True):
                st.write(f"{name}　画像生成 {gen_count}回")
        else:
            st.write("まだ画像生成した登録者はいません")

    with st.expander("画像生成していない登録者"):
        if image_zero:
            for name, _u in image_zero:
                st.write(name)
        else:
            st.write("全員が1回以上画像生成しています")

    st.markdown("### ポイント手動付与")
    grant_name = st.text_input("ポイントを足す相手", value=str(st.session_state.get("username") or ""))
    grant_pts = st.number_input("追加ポイント", min_value=1, max_value=10000, value=300, step=1)
    if st.button("ポイントを手動で足す"):
        users2 = load_json(USERS_FILE, {})
        if grant_name not in users2:
            st.error("そのユーザーはいません")
        else:
            users2[grant_name]["points"] = int(users2[grant_name].get("points") or 0) + int(grant_pts)
            save_json(USERS_FILE, users2)
            if grant_name == st.session_state.get("username"):
                st.session_state.points = int(users2[grant_name]["points"])
            st.success(f"{grant_name} に {int(grant_pts)} ポイント足しました")

    now = datetime.now()
    online = []
    recent = []
    for name, u in valid_users:
        seen = str(u.get("last_seen") or "")
        if not seen:
            continue
        try:
            t = datetime.strptime(seen, "%Y/%m/%d %H:%M")
        except Exception:
            continue
        mins = (now - t).total_seconds() / 60
        row = f"{name}　{seen}"
        if mins <= 30:
            online.append(row)
        recent.append((t, row))
    st.write("ログイン中（30分以内）")
    if online:
        for row in online:
            st.write(row)
    else:
        st.write("なし")
    st.write("最近ログイン")
    for _t, row in sorted(recent, reverse=True)[:30]:
        st.write(row)

elif st.session_state.page == "simple":
    st.subheader("画像生成モード")
    if st.session_state.get("signup_just_completed"):
        st.success(f"🎉 登録ありがとうございます！新規登録特典として **{SIGNUP_POINTS}ポイント** プレゼントしました。")
        st.markdown(
            '<div style="background:#fff0f6;border:2px solid #ff6ea8;border-radius:16px;padding:10px 12px;margin:8px 0 14px;text-align:center;color:#ff4d88;font-weight:800;">'
            'このまま下のフォームから、まずは画像を1枚作ってみてください！'
            '</div>',
            unsafe_allow_html=True,
        )
        st.session_state.signup_just_completed = False
    if st.button("履歴"):
        st.session_state.show_history = True; st.rerun()
    if st.session_state.show_history:
        pick = st.session_state.get("hist_pick")
        if pick:
            st.markdown("### 履歴の内容")
            st.caption(pick.get("time") or "日時不明")
            st.write("画質: " + (pick.get("quality") or "なし"))
            st.write("背景: " + (pick.get("background") or "なし"))
            for i, c in enumerate(pick.get("chars") or []):
                if str(c).strip():
                    st.write(f"キャラ{i+1}: {c}")
            for i, btxt in enumerate(pick.get("bubbles") or []):
                if str(btxt).strip():
                    st.write(f'キャラ{i+1}吹き出し: {btxt}')
            st.write("その他: " + (pick.get("other") or "なし"))
            st.write("除外: " + (pick.get("negative") or "なし"))
            st.write("サイズ: " + (pick.get("size") or "なし"))
            st.write("プロンプトガイダンス: " + str(pick.get("scale", 5.0)))
            st.write("ステップ: " + str(pick.get("steps", 20)))
            st.write("サンプラー: " + str(pick.get("sampler", "Euler Ancestral")))
            st.write("シード値: " + (str(pick.get("seed")) if pick.get("seed") is not None else "ランダム"))
            a, b = st.columns(2)
            with a:
                if st.button("この設定を使う", type="primary"):
                    apply_simple_settings(pick)
                    st.session_state.hist_pick = None
                    st.session_state.show_history = False
                    st.rerun()
            with b:
                if st.button("戻る"):
                    st.session_state.hist_pick = None
                    st.rerun()
        else:
            if st.button("履歴を閉じる"):
                st.session_state.show_history = False
                st.rerun()
            if not st.session_state.simple_history:
                st.write("履歴はまだありません")
            else:
                st.caption("生成した日時を押すと、そのときの設定を確認できます")
                for hi, item in enumerate(reversed(st.session_state.simple_history)):
                    hist_time = item.get("time") or "日時不明"
                    if st.button(hist_time, key=f"hpick_{hi}", use_container_width=True):
                        st.session_state.hist_pick = item
                        st.rerun()
        st.stop()
    st.text_area("画質プロンプト", key="sq")
    st.text_area("背景プロンプト", key="sb")
    if st.button("➕ キャラ追加") and len(st.session_state.schars) < 3:
        st.session_state.schars.append("")
        st.session_state.sbubbles.append("")
        idx = len(st.session_state.schars) - 1
        st.session_state[f"scarea_{idx}"] = ""
        st.session_state[f"sbb_{idx}"] = ""
        st.rerun()
    if len(st.session_state.get("sbubbles") or []) < len(st.session_state.schars):
        st.session_state.sbubbles = list(st.session_state.get("sbubbles") or []) + [""] * (len(st.session_state.schars) - len(st.session_state.get("sbubbles") or []))
    for i in range(len(st.session_state.schars)):
        a, b = st.columns([5, 1])
        with a:
            st.text_area(f"キャラクタープロンプト{i+1}", key=f"scarea_{i}")
            st.session_state.schars[i] = st.session_state.get(f"scarea_{i}", "")
            st.text_input(f"キャラ{i+1} 吹き出し（吹き出しの中の言葉）", key=f"sbb_{i}")
            st.session_state.sbubbles[i] = st.session_state.get(f"sbb_{i}", "")
        with b:
            if i > 0 and st.button("消す", key=f"scdel_{i}"):
                st.session_state.schars.pop(i)
                if i < len(st.session_state.sbubbles):
                    st.session_state.sbubbles.pop(i)
                st.rerun()
    st.text_area("その他プロンプト", key="so")
    st.text_area("除外プロンプト", key="sn")
    size_opts = [k for k, v in SIMPLE_SIZES.items() if (is_premium() or is_owner() or not v["paid"])]
    current_size = st.session_state.get("simple_size") or (size_opts[0] if size_opts else "")
    if current_size not in size_opts:
        current_size = size_opts[0]
        st.session_state.simple_size = current_size
    size_name = st.radio("サイズ", size_opts, index=size_opts.index(current_size), horizontal=True, key="simple_size")
    spec = SIMPLE_SIZES[size_name]
    st.caption(f"{spec['gen'][0]} × {spec['gen'][1]}　{spec['cost']}ポイント")
    scale = st.slider("プロンプトガイダンス", 1.0, 10.0, float(st.session_state.get("simple_scale", 5.0)), 0.1, key="simple_scale")
    with st.expander("詳細な生成設定", expanded=False):
        steps = st.slider("ステップ", 1, 28, int(st.session_state.get("simple_steps", 20)), 1, key="simple_steps")
        sampler_labels = {
            "Euler Ancestral": "k_euler_ancestral",
            "Euler": "k_euler",
            "DPM++ 2M": "k_dpmpp_2m",
            "DPM++ SDE": "k_dpmpp_sde",
            "DPM++ 2M SDE": "k_dpmpp_2m_sde",
            "DPM++ 2S Ancestral": "k_dpmpp_2s_ancestral",
            "DDIM V3": "ddim_v3",
        }
        sampler_options = list(sampler_labels.keys())
        current_sampler = st.session_state.get("simple_sampler") or sampler_options[0]
        if current_sampler not in sampler_options:
            current_sampler = sampler_options[0]
            st.session_state.simple_sampler = current_sampler
        sampler_name = st.selectbox("サンプラー", sampler_options, index=sampler_options.index(current_sampler), key="simple_sampler")
        seed_text = st.text_input("シード値", key="simple_seed", placeholder="空欄ならランダム")
        if seed_text.strip():
            try:
                seed_value = int(seed_text.strip())
                if not (0 <= seed_value <= 4294967295):
                    raise ValueError
            except ValueError:
                st.error("シード値は0～4294967295の整数で入力してください")
                seed_value = None
        else:
            seed_value = None
    if st.button("生成する", type="primary"):
        st.session_state.error = ""; st.session_state.simple_busy = True; st.rerun()
    if st.session_state.simple_busy:
        st.markdown('<div style="margin:8px 0;padding:14px;border-radius:14px;background:#fff0f6;color:#ff4d88;font-weight:800;text-align:center;">生成中…</div>', unsafe_allow_html=True)
        char_texts = []
        bubbles = list(st.session_state.get("sbubbles") or [])
        for i, raw in enumerate(st.session_state.schars):
            body = (raw or "").strip()
            bub = (bubbles[i] if i < len(bubbles) else "").strip()
            if bub.startswith('speech bubble,"') and bub.endswith('"'):
                bub = bub[len('speech bubble,"'):-1]
            elif bub.startswith("speech bubble,"):
                bub = bub.split(",", 1)[-1].strip().strip('"')
            extra = f'speech bubble,"{bub}"' if bub else ""
            line = ", ".join([x for x in [body, extra] if x])
            if line:
                char_texts.append(line)
        chars = char_texts
        parts = [x.strip() for x in [st.session_state.sq, st.session_state.sb, st.session_state.so] if x.strip()]
        if not parts and not chars:
            st.session_state.error = "プロンプトを入れてください"
        elif spec["paid"] and not is_premium() and not is_owner():
            st.session_state.error = "このサイズはVIPだけです"
        else:
            try:
                with st.spinner("生成中…"):
                    take_points(spec["cost"])
                    used_seed = seed_value if seed_value is not None else secrets.randbelow(4294967296)
                    img = nai_request(
                        ", ".join(parts), spec["gen"][0], spec["gen"][1], "nai-diffusion-5-full",
                        steps=steps, scale=scale, negative=st.session_state.sn.strip(), char_texts=chars,
                        sampler=sampler_labels[sampler_name], seed=used_seed,
                    )
                st.session_state.simple_image = img
                st.session_state.simple_history.append({"url": img, "time": datetime.now().strftime("%Y/%m/%d %H:%M"), "quality": st.session_state.sq, "background": st.session_state.sb, "chars": list(st.session_state.schars), "bubbles": list(st.session_state.get("sbubbles") or []), "other": st.session_state.so, "negative": st.session_state.sn, "size": size_name, "scale": scale, "steps": steps, "sampler": sampler_name, "seed": used_seed})
                save_user_state(); st.session_state.error = ""
            except Exception as e:
                st.session_state.error = str(e)
        st.session_state.simple_busy = False
        go("simple"); st.rerun()
    if st.session_state.simple_image:
        st.image(st.session_state.simple_image, use_container_width=True)
        raw = uri_to_image(st.session_state.simple_image)
        last_simple = (st.session_state.get("simple_history") or [])[-1] if st.session_state.get("simple_history") else {}
        if last_simple.get("seed") is not None:
            st.caption(f"シード値: {last_simple.get('seed')}　ステップ: {last_simple.get('steps', 20)}　サンプラー: {last_simple.get('sampler', 'Euler Ancestral')}")
        st.download_button("PNG保存", data=image_to_bytes(raw), file_name="simple.png", mime="image/png")
        if st.button("保存庫に入れる"):
            add_library(st.session_state.simple_image, "画像生成", {
                "kind": "simple",
                "quality": st.session_state.sq,
                "background": st.session_state.sb,
                "chars": list(st.session_state.schars),
                "bubbles": list(st.session_state.get("sbubbles") or []),
                "other": st.session_state.so,
                "negative": st.session_state.sn,
                "size": st.session_state.get("simple_size", ""),
                "scale": st.session_state.get("simple_scale", 5.0),
                "steps": st.session_state.get("simple_steps", 20),
                "sampler": st.session_state.get("simple_sampler", "Euler Ancestral"),
                "seed": ((st.session_state.get("simple_history") or [])[-1].get("seed") if st.session_state.get("simple_history") else None),
            }); st.success("入れました")
        if st.button("この画像を動画にする"):
            st.session_state.video_src = st.session_state.simple_image; go("video"); st.rerun()

elif st.session_state.page == "board":
    st.subheader("👥 コミュニティ")
    st.caption("質問・相談・要望・作品について、ユーザー同士や管理者で会話できます。")
    board = load_board()
    posts_all = list(reversed(board.get("posts", [])))
    view_id = str(st.session_state.get("board_id") or "")

    if view_id:
        post = next((p for p in board.get("posts", []) if p.get("id") == view_id), None)
        if st.button("← 一覧へ戻る", use_container_width=True):
            st.session_state.board_id = ""
            st.query_params["p"] = "board"
            if "bid" in st.query_params:
                del st.query_params["bid"]
            go("board"); st.rerun()
        if not post:
            st.warning("このスレッドはありません")
            st.session_state.board_id = ""
        else:
            category = post.get("category") or ("作品" if post.get("image") else "その他")
            st.caption(f"【{category}】")
            st.markdown(f"## {post.get('title') or '無題'}")
            author = post.get("user") or "名無し"
            author_label = f"{author}　👑管理者" if post.get("is_owner") else author
            st.caption(f"{author_label}　{post.get('time','')}")
            body = str(post.get("body") or "").strip()
            if body:
                st.markdown(body)

            img = board_image_uri(post)
            if img:
                st.image(img, use_container_width=True)

            if post.get("kind") == "simple" and post.get("show_prompt"):
                st.divider()
                st.write("**この作品のプロンプト**")
                st.write("画質: " + (post.get("quality") or "なし"))
                st.write("背景: " + (post.get("background") or "なし"))
                for i, c in enumerate(post.get("chars") or []):
                    if str(c).strip():
                        st.write(f"キャラ{i+1}: {c}")
                for i, btxt in enumerate(post.get("bubbles") or []):
                    if str(btxt).strip():
                        st.write(f"キャラ{i+1}吹き出し: {btxt}")
                st.write("その他: " + (post.get("other") or "なし"))
                st.write("除外: " + (post.get("negative") or "なし"))
                st.write("サイズ: " + (post.get("size") or "なし"))
                st.write("プロンプトガイダンス: " + str(post.get("scale", 5.0)))
                st.write("ステップ: " + str(post.get("steps", 20)))
                st.write("サンプラー: " + str(post.get("sampler", "Euler Ancestral")))
                st.write("シード値: " + (str(post.get("seed")) if post.get("seed") is not None else "ランダム"))
                if st.button("このプロンプトを使う", type="primary"):
                    apply_simple_settings(post)
                    go("simple"); st.rerun()
            elif post.get("kind") == "simple" and not body:
                st.caption("プロンプトは非表示です")

            st.divider()
            comments = post.get("comments") or []
            st.markdown(f"### 返信 {len(comments)}")
            if comments:
                for idx, c in enumerate(comments):
                    cu = c.get("user") or "名無し"
                    badge = " 👑管理者" if c.get("is_owner") else ""
                    st.markdown(f"**{cu}{badge}**　{c.get('time','')}")
                    st.write(c.get("text", ""))
                    if st.session_state.logged_in and (st.session_state.get("username") == c.get("user") or is_owner()):
                        if st.button("この返信を削除", key=f"delc_{view_id}_{idx}"):
                            comments.pop(idx)
                            post["comments"] = comments
                            save_board(board)
                            st.rerun()
                    if idx < len(comments) - 1:
                        st.markdown("---")
            else:
                st.caption("まだ返信はありません。最初の返信を書いてみましょう。")

            if st.session_state.logged_in:
                msg = st.text_area("返信を書く", key="board_cmt", max_chars=500, placeholder="質問への回答、感想、アドバイスなど")
                if st.button("返信する", type="primary", use_container_width=True):
                    if not msg.strip():
                        st.session_state.error = "返信を書いてください"
                    elif len(comments) >= BOARD_MAX_COMMENTS:
                        st.session_state.error = "返信がいっぱいです"
                    else:
                        comments.append({
                            "user": st.session_state.get("username") or "名無し",
                            "is_owner": bool(is_owner()),
                            "text": msg.strip()[:500],
                            "time": datetime.now().strftime("%m/%d %H:%M"),
                            "ts": time.time(),
                        })
                        post["comments"] = comments
                        save_board(board)
                        st.session_state.error = ""
                    go("board"); st.rerun()
            else:
                st.caption("返信するにはログインが必要です")

            if st.session_state.logged_in and (st.session_state.get("username") == post.get("user") or is_owner()):
                st.divider()
                if st.button("このスレッドを削除", type="secondary"):
                    path = post.get("image") or ""
                    board["posts"] = [p for p in board.get("posts", []) if p.get("id") != view_id]
                    if path and os.path.exists(path):
                        try:
                            os.remove(path)
                        except Exception:
                            pass
                    save_board(board)
                    st.session_state.board_id = ""
                    go("board"); st.rerun()
    else:
        # コミュニティを「スレッド」と「作品投稿」に分離。
        tab_thread, tab_work = st.tabs(["🗨️ スレッド", "🖼️ 作品投稿"])

        with tab_thread:
            if st.session_state.logged_in:
                with st.expander("📝 新しいスレッドを作る", expanded=False):
                    st.caption("質問・相談・要望・雑談など、自由に投稿できます。")
                    t_title = st.text_input("タイトル", max_chars=60, key="thread_title", placeholder="例：このプロンプトについて質問です")
                    t_cat = st.selectbox("カテゴリ", ["質問・相談", "要望", "不具合", "雑談", "その他"], key="thread_category")
                    t_body = st.text_area("内容", max_chars=1000, key="thread_body", placeholder="みんなに聞きたいことを書いてください")
                    if st.button("スレッドを作成", type="primary", use_container_width=True):
                        if len(board.get("posts", [])) >= BOARD_MAX_POSTS:
                            st.session_state.error = "掲示板がいっぱいです"
                        elif not t_title.strip() or not t_body.strip():
                            st.session_state.error = "タイトルと内容を入力してください"
                        else:
                            pid = uuid.uuid4().hex[:10]
                            board.setdefault("posts", []).append({
                                "id": pid,
                                "user": st.session_state.get("username") or "名無し",
                                "is_owner": bool(is_owner()),
                                "title": t_title.strip()[:60],
                                "category": t_cat,
                                "body": t_body.strip()[:1000],
                                "image": "",
                                "kind": "thread",
                                "show_prompt": False,
                                "comments": [],
                                "time": datetime.now().strftime("%Y/%m/%d %H:%M"),
                                "ts": time.time(),
                                "updated_at": time.time(),
                            })
                            save_board(board)
                            st.session_state.board_id = pid
                            st.session_state.error = ""
                        go("board"); st.rerun()
            else:
                st.caption("投稿・返信にはログインが必要です")

            q = st.text_input("スレッドを検索", key="board_thread_q", placeholder="タイトル・名前・内容")
            thread_posts = [p for p in posts_all if not (p.get("image") or p.get("category") == "作品")]
            if q and q.strip():
                w = q.strip().lower()
                thread_posts = [p for p in thread_posts if w in str(p.get("title") or "").lower() or w in str(p.get("user") or "").lower() or w in str(p.get("body") or "").lower()]
            if not thread_posts:
                st.caption("まだスレッドはありません")
            else:
                for p in thread_posts:
                    title = str(p.get("title") or "無題").strip() or "無題"
                    if st.button(title[:60], key=f"plist_thread_{p.get('id')}", use_container_width=True):
                        st.session_state.board_id = p.get("id")
                        go("board"); st.rerun()

        with tab_work:
            if st.session_state.logged_in:
                with st.expander("🖼️ 作品を投稿する", expanded=False):
                    title = st.text_input("タイトル", max_chars=40, key="board_work_title")
                    choices = []
                    if st.session_state.simple_image:
                        choices.append({"label": "今の画像生成", "url": st.session_state.simple_image, "kind": "simple"})
                    for item in reversed(st.session_state.get("simple_history") or []):
                        if item.get("url"):
                            choices.append({"label": f"履歴 {item.get('time','')}", "url": item["url"], "kind": "simple", "meta": item})
                    for item in reversed(st.session_state.get("library") or []):
                        if item.get("url"):
                            kind = site_work_kind(item) or item.get("kind") or "library"
                            choices.append({"label": f"保存庫 {item.get('time','')} {item.get('label','') or '保存画像'}", "url": item["url"], "kind": kind, "meta": item})
                    seen, uniq = set(), []
                    for c in choices:
                        if c["url"] in seen:
                            continue
                        seen.add(c["url"]); uniq.append(c)
                    if not uniq:
                        st.write("サイトで作った画像がまだありません")
                    else:
                        names = [c["label"] for c in uniq]
                        pick = st.selectbox("サイト内の作品", names, key="board_work_pick")
                        chosen = uniq[names.index(pick)]
                        st.image(chosen["url"], width=220)
                        show_p = "非表示"
                        if chosen["kind"] == "simple":
                            show_p = st.radio("プロンプト", ["表示する", "非表示"], horizontal=True, key="board_show_prompt")
                        else:
                            st.caption("画像生成モード以外はプロンプトを出せません")
                        if st.button("作品を投稿する", type="primary", use_container_width=True):
                            if len(board.get("posts", [])) >= BOARD_MAX_POSTS:
                                st.session_state.error = "掲示板がいっぱいです"
                            else:
                                pid = uuid.uuid4().hex[:10]
                                meta = chosen.get("meta") or prompt_from_history(chosen["url"])
                                try:
                                    path = save_board_image(chosen["url"], pid)
                                    board.setdefault("posts", []).append({
                                        "id": pid,
                                        "user": st.session_state.get("username") or "名無し",
                                        "is_owner": bool(is_owner()),
                                        "title": (title or "無題").strip()[:40],
                                        "category": "作品",
                                        "body": "",
                                        "image": path,
                                        "kind": chosen["kind"],
                                        "show_prompt": chosen["kind"] == "simple" and show_p == "表示する",
                                        "quality": meta.get("quality", "") if chosen["kind"] == "simple" else "",
                                        "background": meta.get("background", "") if chosen["kind"] == "simple" else "",
                                        "bubbles": list(meta.get("bubbles") or []) if chosen["kind"] == "simple" else [],
                                        "other": meta.get("other", "") if chosen["kind"] == "simple" else "",
                                        "negative": meta.get("negative", "") if chosen["kind"] == "simple" else "",
                                        "size": meta.get("size", "") if chosen["kind"] == "simple" else "",
                                        "scale": meta.get("scale", 5.0) if chosen["kind"] == "simple" else 5.0,
                                        "steps": meta.get("steps", 20) if chosen["kind"] == "simple" else 20,
                                        "sampler": meta.get("sampler", "Euler Ancestral") if chosen["kind"] == "simple" else "Euler Ancestral",
                                        "seed": meta.get("seed") if chosen["kind"] == "simple" else None,
                                        "chars": list(meta.get("chars") or [])[:3] if chosen["kind"] == "simple" else [],
                                        "comments": [],
                                        "time": datetime.now().strftime("%Y/%m/%d %H:%M"),
                                        "ts": time.time(),
                                        "updated_at": time.time(),
                                    })
                                    save_board(board)
                                    st.session_state.error = ""
                                    st.session_state.board_id = pid
                                except Exception as e:
                                    st.session_state.error = str(e)
                            go("board"); st.rerun()
            else:
                st.caption("作品投稿にはログインが必要です")

            q = st.text_input("作品を検索", key="board_work_q", placeholder="タイトル・名前")
            work_posts = [p for p in posts_all if p.get("image") or p.get("category") == "作品"]
            if q and q.strip():
                w = q.strip().lower()
                work_posts = [p for p in work_posts if w in str(p.get("title") or "").lower() or w in str(p.get("user") or "").lower()]
            if not work_posts:
                st.caption("まだ作品投稿はありません")
            else:
                for p in work_posts:
                    title = str(p.get("title") or "無題").strip() or "無題"
                    if st.button(title[:60], key=f"plist_work_{p.get('id')}", use_container_width=True):
                        st.session_state.board_id = p.get("id")
                        go("board"); st.rerun()

    # コミュニティを開いた時点までを既読にする。
    mark_community_seen()

else:
    usable_fonts = get_usable_fonts()
    st.subheader("4コマ")
    layout = st.radio("並べ方", list(LAYOUTS.keys()), horizontal=True)
    st.session_state.layout = layout
    n = LAYOUTS[layout]["count"]
    names = [char_label(ch) for ch in st.session_state.characters]
    size_opts = [k for k, v in SIZES.items() if (is_premium() or is_owner() or not v["paid"])]

    def set_by_name(name):
        for ch in st.session_state.characters:
            if char_label(ch) == name:
                return ch
        return None

    def make_one(i):
        scene = st.session_state.scenes[i].strip()
        if not scene:
            raise Exception("内容が空です")
        spec = SIZES.get(st.session_state.panel_shape[i], SIZES["横長"])
        if spec["paid"] and not is_premium() and not is_owner():
            raise Exception("このサイズはVIPだけです")
        chosen = st.session_state.scene_chars[i]
        if chosen != "セットなし" and not is_premium() and not is_owner():
            raise Exception("セットはVIPだけです")
        pack = {} if chosen == "セットなし" else (set_by_name(chosen) or {})
        chars, styles = normalize_refs(pack.get("chars")), normalize_refs(pack.get("styles"))
        take_points(spec["cost"] + REF_SITE * (min(3, len(chars)) + min(3, len(styles))))
        st.session_state.panel_images[i] = nai_request(scene, spec["gen"][0], spec["gen"][1], "nai-diffusion-4-5-full", steps=23, scale=5.0, char_refs=chars, style_refs=styles)
        st.session_state.panel_sizes[i] = spec["wh"]
        st.session_state.panel_upload[i] = False

    for i in range(n):
        with st.expander(f"コマ {i+1}", expanded=True):
            cur = st.session_state.panel_shape[i] if st.session_state.panel_shape[i] in size_opts else "横長"
            shape = st.selectbox("サイズ", size_opts, index=size_opts.index(cur), key=f"shape_{i}")
            st.session_state.panel_shape[i] = shape
            spec = SIZES[shape]
            if not st.session_state.panel_upload[i]:
                st.session_state.panel_sizes[i] = spec["wh"]
            st.caption(f"{spec['wh'][0]} × {spec['wh'][1]}　消費 {spec['cost']}")
            up = st.file_uploader("持っている画像を使う", type=["png", "jpg", "jpeg"], key=f"up_{i}")
            if up:
                st.session_state.panel_images[i] = uploaded_to_uri(up)
                st.session_state.panel_upload[i] = True
                st.session_state.panel_sizes[i] = uri_to_image(st.session_state.panel_images[i]).size
            st.session_state.scenes[i] = st.text_input("生成する内容", value=st.session_state.scenes[i], key=f"sc_{i}")
            options = ["セットなし"] + (names if (is_premium() or is_owner()) else [])
            curc = st.session_state.scene_chars[i]
            st.session_state.scene_chars[i] = st.selectbox("セット", options, index=options.index(curc) if curc in options else 0, key=f"ch_{i}")
            if st.session_state.get("busy_index") == i:
                st.info(f"コマ{i+1} 生成中…")
                try:
                    make_one(i)
                    st.session_state.error = ""
                except Exception as e:
                    st.session_state.error = str(e)
                st.session_state.busy_index = None
                go("make")
                st.rerun()
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("生成", key=f"gen_{i}", type="primary"):
                    st.session_state.error = ""
                    st.session_state.busy_index = i
                    st.rerun()
            with c2:
                if st.button("消す", key=f"clr_{i}"):
                    st.session_state.panel_images[i] = None
                    st.session_state.panel_bubbles[i] = []
                    st.session_state.panel_upload[i] = False
                    st.rerun()
            with c3:
                if st.session_state.panel_images[i] and st.button("保存庫へ", key=f"sv_{i}"):
                    add_library(st.session_state.panel_images[i], f"4コマ{i+1}")
                    st.success("入れました")
            if st.session_state.panel_images[i]:
                draft = st.session_state.drafts[i]
                draft["text"] = st.text_input("新しいセリフ", value=draft.get("text", ""), key=f"bt_{i}")
                d1, d2 = st.columns(2)
                with d1:
                    draft["kind"] = st.selectbox("形", BUBBLE_TYPES, key=f"bk_{i}")
                    draft["tail"] = st.selectbox("しっぽ", TAILS, key=f"tl_{i}")
                    draft["font"] = st.selectbox("フォント", usable_fonts, key=f"bfn_{i}")
                    draft["dir"] = st.selectbox("向き", TEXT_DIR, key=f"bd_{i}")
                with d2:
                    draft["size"] = st.slider("文字の大きさ", 16, 64, int(draft.get("size", 28)), key=f"bs_{i}")
                    draft["bold"] = st.slider("太さ", 0, 4, int(draft.get("bold", 0)), key=f"bb_{i}")
                    draft["tail_size"] = st.slider("しっぽの大きさ", 8, 80, int(draft.get("tail_size", 28)), key=f"bts_{i}")
                    draft["x"] = st.slider("左右", 0, 100, int(draft.get("x", 8)), key=f"bx_{i}")
                    draft["y"] = st.slider("上下", 0, 100, int(draft.get("y", 8)), key=f"by_{i}")
                    draft["angle"] = st.slider("傾き", -45, 45, int(draft.get("angle", 0)), key=f"ba_{i}")
                draft["fill"] = st.color_picker("吹き出し色", draft.get("fill", "#ffffff"), key=f"bf_{i}")
                draft["color"] = st.color_picker("文字色", draft.get("color", "#111111"), key=f"bc_{i}")
                st.session_state.drafts[i] = draft
                if st.button("このセリフを追加", key=f"addb_{i}") and draft["text"].strip():
                    st.session_state.panel_bubbles[i].append(dict(draft))
                    st.session_state.drafts[i] = empty_bubble()
                    st.rerun()
                for bi, bb in enumerate(st.session_state.panel_bubbles[i]):
                    k1, k2 = st.columns([5, 1])
                    with k1:
                        st.caption(bb.get("text", ""))
                    with k2:
                        if st.button("×", key=f"delb_{i}_{bi}"):
                            st.session_state.panel_bubbles[i].pop(bi)
                            st.rerun()
                preview = draw_all_bubbles(panel_raw(i), st.session_state.panel_bubbles[i])
                if draft["text"].strip():
                    preview = draw_one_bubble(preview, draft)
                st.image(preview, width=340)

    if st.button("1枚にまとめる", type="primary"):
        panels = []
        for i in range(n):
            if not st.session_state.panel_images[i]:
                st.error(f"コマ{i+1}がありません")
                panels = None
                break
            panels.append(draw_all_bubbles(panel_raw(i), st.session_state.panel_bubbles[i]))
        if panels:
            st.session_state.combined = combine_panels(panels, cols=LAYOUTS[layout]["cols"])
            go("make")
            st.rerun()
    if st.session_state.combined is not None:
        st.image(st.session_state.combined, use_container_width=True)
        st.download_button("PNG保存", data=image_to_bytes(st.session_state.combined), file_name="yonkoma.png", mime="image/png")
        if st.button("まとめた画像を保存庫へ"):
            buf = BytesIO()
            st.session_state.combined.save(buf, format="PNG")
            add_library("data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(), "4コマまとめ")
            st.success("入れました")
