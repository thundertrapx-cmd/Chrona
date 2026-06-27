import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import requests
import numpy as np
import os
import json
import time
from datetime import date
from textblob import TextBlob
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from supabase import create_client, Client
import google.generativeai as genai
import yfinance as yf

# ─────────────────────────────────────────────
# CONFIG & PAGE SETUP (ต้องอยู่บนสุดเสมอ)
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Chrona",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# API Keys สำหรับ Production (ดึงจาก st.secrets)
NEWS_API_KEY = st.secrets.get("NEWS_API_KEY")
TWELVE_DATA_API_KEY = st.secrets.get("TWELVE_DATA_API_KEY")

# สร้างลิสต์หุ้นเก็บไว้ในหน่วยความจำชั่วคราว เพื่อให้เพิ่มหุ้นใหม่ได้
if "stock_list" not in st.session_state:
    st.session_state.stock_list = ["AAPL", "MSFT", "NVDA", "TSLA", "BTC/USD"]

STOCK_LIST = st.session_state.stock_list

# ─────────────────────────────────────────────
# SUPABASE CONNECTION & AUTHENTICATION GATE
# ─────────────────────────────────────────────
try:
    supabase_url = st.secrets["SUPABASE_URL"]
    supabase_key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(supabase_url, supabase_key)
except Exception as e:
    st.error("❌ ไม่สามารถดึงค่า Supabase Config จาก secrets.toml ได้ กรุณาตรวจสอบไฟล์")
    st.stop()

if "user" not in st.session_state:
    st.session_state.user = None

def logout_user():
    try:
        supabase.auth.sign_out()
    except:
        pass
    keys_to_clear = ["user", "messages", "javis_chat_session", "ticker", "daily_ai_count", "last_reset_date"]
    for key in keys_to_clear:
        st.session_state.pop(key, None)
    st.rerun()

def show_login_page():
    st.markdown("""
        <style>
        .login-box { background: #111318; padding: 30px; border-radius: 10px; border: 1px solid #1e2230; }
        </style>
    """, unsafe_allow_html=True)
    
    st.title("📈 Chrona")
    st.subheader("🔒 Please Log In to Continue")
    
    tab_login, tab_signup = st.tabs(["🔐 Log In", "📝 Sign Up"])
    
    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email Address", placeholder="your@email.com")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            login_submitted = st.form_submit_button("Sign In 🚀", use_container_width=True)
            
            if login_submitted:
                if not email or not password:
                    st.error("กรุณากรอกข้อมูลให้ครบถ้วน")
                else:
                    with st.spinner("กำลังยืนยันตัวตน..."):
                        try:
                            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                            st.session_state.user = res.user
                            st.success("เข้าสู่ระบบสำเร็จ!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ เข้าสู่ระบบล้มเหลว: อีเมลหรือรหัสผ่านไม่ถูกต้อง")
                            
    with tab_signup:
        with st.form("signup_form"):
            new_email = st.text_input("Email Address", placeholder="your@email.com")
            new_password = st.text_input("Password (ขั้นต่ำ 6 ตัวอักษร)", type="password", placeholder="••••••••")
            signup_submitted = st.form_submit_button("Create Account ✨", use_container_width=True)
            
            if signup_submitted:
                if not new_email or not new_password:
                    st.error("กรุณากรอกข้อมูลให้ครบถ้วน")
                elif len(new_password) < 6:
                    st.error("รหัสผ่านต้องมีความยาวอย่างน้อย 6 ตัวอักษร")
                else:
                    with st.spinner("กำลังสร้างบัญชีผู้ใช้..."):
                        try:
                            res = supabase.auth.sign_up({"email": new_email, "password": new_password})
                            st.success("🎉 สมัครสมาชิกสำเร็จ! คุณสามารถใช้บัญชีนี้เข้าสู่ระบบได้ทันที")
                        except Exception as e:
                            st.error(f"❌ สมัครสมาชิกล้มเหลว: {str(e)}")

if st.session_state.user is None:
    show_login_page()
    st.stop()

# ─────────────────────────────────────────────
# CUSTOM CSS — Dark terminal-finance aesthetic
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght=400;700&family=DM+Sans:wght=300;400;600&display=swap');

:root {
    --bg: #0a0c10; --card: #111318; --border: #1e2230; --accent: #00d4aa;
    --accent2: #ff6b6b; --accent3: #ffd93d; --text: #e2e8f0; --muted: #64748b;
    --up: #00d4aa; --down: #ff6b6b;
}
html, body, [data-testid="stAppViewContainer"] { background-color: var(--bg) !important; color: var(--text) !important; font-family: 'DM Sans', sans-serif; }
[data-testid="stSidebar"] { background-color: var(--card) !important; border-right: 1px solid var(--border); }
h1, h2, h3, h4 { font-family: 'Space Mono', monospace !important; letter-spacing: -0.5px; }
h1 { color: var(--accent) !important; font-size: 1.8rem !important; }
h2 { color: var(--text) !important; font-size: 1.3rem !important; border-bottom: 1px solid var(--border); padding-bottom: 8px; margin-bottom: 16px; }
h3 { color: var(--accent3) !important; font-size: 1.1rem !important; }
[data-testid="metric-container"] { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 16px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
[data-testid="stDataFrame"] { border: 1px solid var(--border) !important; border-radius: 8px; }
.stAlert { border-radius: 8px !important; }
div[data-testid="stTabs"] button { font-family: 'Space Mono', monospace; font-size: 0.9rem; color: var(--muted); }
div[data-testid="stTabs"] button[aria-selected="true"] { color: var(--accent) !important; border-bottom: 2px solid var(--accent) !important; }
.stSelectbox > div > div, .stTextInput > div > div > input, .stNumberInput > div > div > input { background: var(--bg) !important; border: 1px solid var(--border) !important; color: var(--text) !important; border-radius: 6px !important; }
.block-container { padding: 2rem 3rem !important; }
.tag-up { color: var(--up); font-weight: 700; font-family: 'Space Mono', monospace; }
.tag-down { color: var(--down); font-weight: 700; font-family: 'Space Mono', monospace; }
hr { border-color: var(--border) !important; margin: 2rem 0; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# HELPERS & DB FUNCTIONS
# ─────────────────────────────────────────────
def load_user_portfolio():
    user_id = st.session_state.user.id
    try:
        response = supabase.table("portfolios").select("*").eq("user_id", user_id).execute()
        return pd.DataFrame(response.data)
    except:
        return pd.DataFrame()

def delete_stock_from_portfolio(row_id):
    try:
        supabase.table("portfolios").delete().eq("id", row_id).execute()
        st.toast("🗑️ ลบหุ้นออกจากพอร์ตแล้ว", icon="✅")
        st.rerun()
    except Exception as e:
        st.error(f"ไม่สามารถลบได้: {str(e)}")

def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_macd(data):
    exp1 = data.ewm(span=12, adjust=False).mean()
    exp2 = data.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal

def calculate_score(hist):
    if len(hist) < 50 or "SMA_20" not in hist.columns or "SMA_50" not in hist.columns or "RSI" not in hist.columns: 
        return 50.0
    latest_close = hist["Close"].iloc[-1]
    sma20 = hist["SMA_20"].iloc[-1]
    sma50 = hist["SMA_50"].iloc[-1]
    rsi = hist["RSI"].iloc[-1]
    score = 0
    if latest_close > sma20: score += 30
    if sma20 > sma50: score += 30
    if 40 <= rsi <= 60: score += 20
    elif rsi < 30: score += 10
    momentum = ((latest_close - hist["Close"].iloc[-20]) / hist["Close"].iloc[-20]) * 100
    if momentum > 10: score += 20
    return round(score, 2)

def get_recommendation(score):
    if score >= 80: return "Strong Buy 🚀"
    elif score >= 60: return "Buy 📈"
    elif score >= 40: return "Hold 🤝"
    else: return "Avoid ⚠️"

def calculate_momentum(hist):
    if len(hist) < 20: return 0.0
    return round(((hist["Close"].iloc[-1] - hist["Close"].iloc[-20]) / hist["Close"].iloc[-20]) * 100, 2)

def calculate_volatility(hist):
    if len(hist) < 2: return 0.0
    return round(hist["Close"].pct_change().std() * 100, 2)

def get_risk_level(volatility):
    if volatility < 2: return "Low 🟢"
    elif volatility < 4: return "Medium 🟡"
    else: return "High 🔴"

@st.cache_data(ttl=900)
def get_stock_news(ticker):
    query = f"{ticker} stock financial"
    url = f"https://newsapi.org/v2/everything?q={query}&sortBy=publishedAt&apiKey={NEWS_API_KEY}"
    try:
        headers = {"User-Agent": "ChronaFinanceDashboard/1.0"}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            return response.json().get("articles", [])[:5]
        return []
    except:
        return []

def analyze_sentiment(text):
    polarity = TextBlob(text).sentiment.polarity
    if polarity > 0: return "Bullish 🚀", polarity
    elif polarity < 0: return "Bearish 📉", polarity
    else: return "Neutral 🤝", polarity

def prepare_features(hist):
    hist = hist.copy()
    hist["Target"] = (hist["Close"].shift(-1) > hist["Close"]).astype(int)
    hist = hist.dropna()
    features = hist[["RSI", "SMA_20", "SMA_50", "MACD", "RVOL", "Momentum_Strength"]]
    target = hist["Target"]
    return features, target

def enrich_hist(raw):
    if raw.empty: return raw
    h = raw.copy()
    
    h["SMA_20"] = h["Close"].rolling(20).mean()
    h["SMA_50"] = h["Close"].rolling(50).mean()
    h["RSI"] = calculate_rsi(h["Close"])
    h["MACD"], h["MACD_Signal"] = calculate_macd(h["Close"])
    h["Volume_SMA"] = h["Volume"].rolling(20).mean()
    h["RVOL"] = h["Volume"] / h["Volume_SMA"]
    h["Return"] = h["Close"].pct_change()
    h["Momentum_Strength"] = h["Return"] * h["RVOL"]
    
    h["Std_20"] = h["Close"].rolling(20).std()
    h["BB_Upper"] = h["SMA_20"] + (2 * h["Std_20"])
    h["BB_Lower"] = h["SMA_20"] - (2 * h["Std_20"])
    h["BB_Bandwidth"] = ((h["BB_Upper"] - h["BB_Lower"]) / h["SMA_20"]) * 100
    
    high_low = h["High"] - h["Low"]
    high_close_prev = (h["High"] - h["Close"].shift(1)).abs()
    low_close_prev = (h["Low"] - h["Close"].shift(1)).abs()
    
    tr = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
    h["ATR"] = tr.rolling(window=14).mean()
    
    return h

# ─────────────────────────────────────────────
# DATA LOADERS 
# ─────────────────────────────────────────────
@st.cache_data(ttl=900)
def load_stock_twelve(t, period):
    symbol_td = t.upper().strip().replace("-", "/")
    interval = "1day"
    output_size = 260 if period == "1y" else (130 if period == "6mo" else (70 if period == "3mo" else 30))
    output_size += 50 
    
    url = f"https://api.twelvedata.com/time_series?symbol={symbol_td}&interval={interval}&outputsize={output_size}&apikey={TWELVE_DATA_API_KEY}"
    try:
        res = requests.get(url, timeout=7).json()
        if "values" in res:
            df = pd.DataFrame(res["values"])
            df["datetime"] = pd.to_datetime(df["datetime"])
            df = df.set_index("datetime").sort_index()
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col])
            df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
            return enrich_hist(df)
    except:
        pass

    try:
        symbol_yf = t.upper().strip().replace("/", "-")
        ticker_data = yf.Ticker(symbol_yf)
        yf_period = "1y" if period == "1y" else ("6mo" if period == "6mo" else ("3mo" if period == "3mo" else "1mo"))
        df_yf = ticker_data.history(period=yf_period)
        if not df_yf.empty:
            df_yf = df_yf[['Open', 'High', 'Low', 'Close', 'Volume']]
            return enrich_hist(df_yf)
    except:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=3600)
def load_fundamentals_twelve(t):
    symbol = t.upper().strip().replace("/", "-")
    data = {
        "longName": t, "sector": "—", "industry": "—", "trailingPE": None, "forwardPE": None,
        "priceToSalesTrailing12Months": None, "marketCap": None, "totalRevenue": None,
        "netIncomeToCommon": None, "revenueGrowth": None, "returnOnEquity": None, "returnOnAssets": None
    }
    try:
        ticker_data = yf.Ticker(symbol)
        info = ticker_data.info
        data["longName"] = info.get("longName", info.get("shortName", t))
        data["sector"] = info.get("sector", "—")
        data["industry"] = info.get("industry", "—")
        data["trailingPE"] = info.get("trailingPE")
        data["forwardPE"] = info.get("forwardPE")
        data["priceToSalesTrailing12Months"] = info.get("priceToSalesTrailing12Months")
        data["marketCap"] = info.get("marketCap")
        data["totalRevenue"] = info.get("totalRevenue")
        data["netIncomeToCommon"] = info.get("netIncomeToCommon")
        data["revenueGrowth"] = info.get("revenueGrowth")
        data["returnOnEquity"] = info.get("returnOnEquity")
        data["returnOnAssets"] = info.get("returnOnAssets")
    except:
        pass
    return data

@st.cache_data(ttl=600)
def get_all_rankings(stocks):
    results = []
    for symbol in stocks:
        try:
            data = load_stock_twelve(symbol, "6mo")
            if data.empty or len(data) < 2: continue
            score = calculate_score(data)
            momentum = calculate_momentum(data)
            volatility = calculate_volatility(data)
            results.append({
                "Stock": symbol, "Price": f"${data['Close'].iloc[-1]:.2f}",
                "Momentum %": momentum, "Volatility %": volatility,
                "Risk": get_risk_level(volatility), "AI Score": score, "Signal": get_recommendation(score),
            })
            time.sleep(1.0)
        except: pass
    return results

@st.cache_data(ttl=900)
def get_cached_rankings():
    return get_all_rankings(STOCK_LIST)

@st.cache_data(ttl=300)
def get_cached_price(symbol):
    symbol_td = symbol.upper().strip().replace("-", "/")
    url = f"https://api.twelvedata.com/price?symbol={symbol_td}&apikey={TWELVE_DATA_API_KEY}"
    try:
        res = requests.get(url, timeout=4).json()
        if "price" in res:
            return {"price": float(res["price"]), "source": "twelvedata"}
    except:
        pass
        
    try:
        symbol_yf = symbol.upper().strip().replace("/", "-")
        ticker_data = yf.Ticker(symbol_yf)
        latest_data = ticker_data.history(period="1d")
        if not latest_data.empty:
            return {"price": float(latest_data["Close"].iloc[-1]), "source": "yfinance"}
    except:
        pass
    return {}

# ─────────────────────────────────────────────
# 🤖 JAVIS AI AGENT CORE LOGIC
# ─────────────────────────────────────────────
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")

def get_stock_realtime_data(ticker_input):
    symbol = ticker_input.upper().strip()
    try:
        symbol_td = symbol.replace("-", "/")
        url = f"https://api.twelvedata.com/price?symbol={symbol_td}&apikey={TWELVE_DATA_API_KEY}"
        res = requests.get(url, timeout=4).json()
        if "price" in res:
            return {"symbol": symbol_td, "current_price": float(res["price"]), "market_status": "ดึงข้อมูลสำเร็จผ่าน Twelve Data"}
    except:
        pass
    try:
        symbol_yf = symbol.replace("/", "-")
        ticker_data = yf.Ticker(symbol_yf)
        latest_data = ticker_data.history(period="1d")
        if not latest_data.empty:
            return {"symbol": symbol_yf, "current_price": float(latest_data["Close"].iloc[-1]), "market_status": "ดึงข้อมูลสำเร็จผ่าน Yahoo Finance"}
    except Exception as ex:
        return f"ระบบไม่สามารถดึงข้อมูลของ {ticker_input} ได้: {str(ex)}"
    return f"ไม่พบข้อมูลราคาล่าสุดของ {ticker_input}"

def get_my_portfolio_data():
    df_p = load_user_portfolio()
    if df_p.empty:
        return "พอร์ตโฟลิโอปัจจุบันว่างเปล่า ไม่มีข้อมูลหุ้นที่บันทึกไว้"
    return df_p[["ticker", "qty", "avg_cost"]].to_dict(orient="records")

def run_javis_agent(user_query):
    if not GEMINI_API_KEY:
        return "❌ กรุณาตั้งค่า GEMINI_API_KEY ใน secrets.toml ก่อนใช้งาน"
        
    clean_key = str(GEMINI_API_KEY).strip().replace('"', '').replace("'", "")
    genai.configure(api_key=clean_key)
    
    system_context = """
คุณคือ Javis AI ของ Chrona เป็นผู้ช่วยด้าน: Stock Analysis, Quantitative Finance, Portfolio Analysis
ตอบภาษาไทยเสมอ ใช้ Bullet Points สรุปท้ายทุกครั้ง ห้ามการันตีกำไร และอธิบายความเสี่ยงเสมอ
หากผู้ใช้ถามเรื่องพอร์ต ให้เรียกใช้ get_my_portfolio_data()
หากผู้ใช้ถามเรื่องหุ้น ให้เรียกใช้ get_stock_realtime_data()
"""
    if "javis_chat_session" not in st.session_state:
        model = genai.GenerativeModel(model_name='gemini-flash-latest', system_instruction=system_context, tools=[get_stock_realtime_data, get_my_portfolio_data])
        st.session_state.javis_chat_session = model.start_chat(history=[], enable_automatic_function_calling=True)
        
    try:
        response = st.session_state.javis_chat_session.send_message(user_query)
        return response.text
    except Exception as e:
        return f"❌ Javis เกิดข้อผิดพลาด: {str(e)}"

# ─────────────────────────────────────────────
# SIDEBAR CONTROL
# ─────────────────────────────────────────────
if "ticker" not in st.session_state:
    st.session_state.ticker = "AAPL"
if "daily_ai_count" not in st.session_state:
    st.session_state.daily_ai_count = 0

with st.sidebar:
    st.markdown(f"👤 **User:** `{st.session_state.user.email}`")
    if st.button("🚪 Log Out", use_container_width=True):
        logout_user()
        
    st.markdown("## ⚙️ Settings")
    st.markdown("### 📌 Available Stocks")
    col_a, col_b = st.columns(2)
    for idx, symbol in enumerate(STOCK_LIST):
        target_col = col_a if idx % 2 == 0 else col_b
        if target_col.button(f"▫️ {symbol}", key=f"btn_{symbol}", use_container_width=True):
            st.session_state.ticker = symbol

    # 🟢 เพิ่ม Tooltip ให้ส่วนตั้งค่า
    ticker = st.text_input("Stock Ticker", value=st.session_state.ticker, help="💡 พิมพ์ชื่อย่อหุ้นต่างประเทศ หรือคริปโต (เช่น TSLA, GOOGL, BTC/USD)").upper()
    st.session_state.ticker = ticker
    
    timeframe = st.selectbox(
        "Timeframe", ["1mo", "3mo", "6mo", "1y"], index=2,
        help="📅 เลือกระยะเวลาย้อนหลังของกราฟและชุดข้อมูลสถิติ"
    )
    st.markdown("---")
    
    st.markdown("## 💼 Portfolio Tracker")
    st.caption("Add positions to track live P&L")
    remaining = max(0, 10 - st.session_state.daily_ai_count)

    st.info(f"🧠 Javis Remaining Today: {remaining}/10")
    with st.form("add_position", clear_on_submit=True):
        col1, col2 = st.columns(2)
        p_ticker = col1.text_input("Ticker", placeholder="AAPL", help="ชื่อย่อหุ้นที่ต้องการบันทึก")
        p_qty = col2.number_input("Qty", min_value=0.01, value=10.0, step=1.0, help="จำนวนหุ้นที่มี")
        p_price = st.number_input("Avg Cost ($)", min_value=0.01, value=100.0, help="ราคาต้นทุนเฉลี่ยต่อหุ้น")
        submitted = st.form_submit_button("➕ Save to Supabase")
        if submitted and p_ticker:
            portfolio_data = {
                "user_id": st.session_state.user.id, "ticker": p_ticker.upper().strip(),
                "qty": float(p_qty), "avg_cost": float(p_price)
            }
            try:
                supabase.table("portfolios").insert(portfolio_data).execute()
                st.success(f"บันทึก {p_ticker.upper()} สำเร็จ!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ เกิดข้อผิดพลาด: {str(e)}")

# ─────────────────────────────────────────────
# MAIN DASHBOARD CONTROL 
# ─────────────────────────────────────────────
st.markdown("## 🔎 ค้นหาและจัดการหุ้น")

col_search, col_add_port, col_add_list = st.columns([2, 1, 1])

with col_search:
    # 🟢 เพิ่ม Tooltip แบบละเอียดยิบในช่องค้นหาหลัก
    new_ticker = st.text_input(
        "ระบุชื่อหุ้นหรือคริปโต (เช่น AAPL, NVDA, BTC/USD)", 
        value=st.session_state.ticker,
        help="💡 **ฟังก์ชันนี้คืออะไร:** ช่องสำหรับค้นหาราคาหุ้น กราฟเทคนิค และข้อมูลพื้นฐานแบบ Real-time\n\n🎯 **ใครควรใช้:** นักลงทุนทุกคนที่ต้องการเช็กกราฟและข้อมูลงบการเงินก่อนตัดสินใจซื้อขาย"
    ).upper().strip()
    
    if new_ticker != st.session_state.ticker:
        st.session_state.ticker = new_ticker
        st.rerun()

with col_add_port:
    with st.expander(f"💼 เพิ่ม {st.session_state.ticker} เข้าพอร์ต", expanded=False):
        with st.form("dashboard_add_position", clear_on_submit=True):
            p_qty = st.number_input("จำนวน (Qty)", min_value=0.01, value=10.0, step=1.0)
            p_price = st.number_input("ราคาต้นทุน ($)", min_value=0.01, value=100.0)
            submitted = st.form_submit_button("บันทึกข้อมูล 💾", use_container_width=True)
            if submitted:
                portfolio_data = {
                    "user_id": st.session_state.user.id, "ticker": st.session_state.ticker,
                    "qty": float(p_qty), "avg_cost": float(p_price)
                }
                try:
                    supabase.table("portfolios").insert(portfolio_data).execute()
                    st.success(f"บันทึกสำเร็จ!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ เกิดข้อผิดพลาด: {str(e)}")

with col_add_list:
    if st.button(f"📌 แปะ {st.session_state.ticker} ไว้ที่ Sidebar", use_container_width=True, help="บันทึกหุ้นตัวนี้ไว้ในเมนูด้านซ้าย เพื่อความรวดเร็วในการกดดูครั้งหน้า"):
        if st.session_state.ticker not in st.session_state.stock_list:
            st.session_state.stock_list.append(st.session_state.ticker)
            st.rerun()
        else:
            st.info("มีหุ้นตัวนี้ใน Sidebar อยู่แล้วครับ")
            
st.markdown("<hr/>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# LOAD MAIN DATA & HEADER
# ─────────────────────────────────────────────
hist = load_stock_twelve(ticker, timeframe)
info = load_fundamentals_twelve(ticker)

st.markdown(f"# 📈 Chrona Terminal")
company_name = info.get("longName", ticker) if info else ticker
sector_info = info.get('sector', '—') if info else '—'
industry_info = info.get('industry', '—') if info else '—'
st.markdown(f"**{company_name}** &nbsp;·&nbsp; {sector_info} &nbsp;·&nbsp; {industry_info}", unsafe_allow_html=True)

if not hist.empty and len(hist) >= 2:
    latest_close = hist["Close"].iloc[-1]
    prev_close = hist["Close"].iloc[-2]
    if pd.isna(latest_close) or pd.isna(prev_close):
        latest_close, change, change_pct, arrow, color_cls = 0.0, 0.0, 0.0, "—", "tag-up"
    else:
        change = latest_close - prev_close
        change_pct = (change / prev_close) * 100
        arrow = "▲" if change >= 0 else "▼"
        color_cls = "tag-up" if change >= 0 else "tag-down"
else:
    latest_close, change, change_pct, arrow, color_cls = 0.0, 0.0, 0.0, "—", "tag-up"

st.markdown(
    f"<span style='font-family:Space Mono;font-size:2.5rem;font-weight:700;color:{'#00d4aa' if change >= 0 else '#ff6b6b'}'>"
    f"${latest_close:.2f}</span> &nbsp;"
    f"<span class='{color_cls}' style='font-size:1.2rem;'>{arrow} {abs(change):.2f} ({abs(change_pct):.2f}%)</span>",
    unsafe_allow_html=True
)

st.markdown("<br/>", unsafe_allow_html=True)

# ─── 💬 JAVIS EXPANDER IN MAIN AREA ───
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_reset_date" not in st.session_state:
    st.session_state.last_reset_date = date.today()
if st.session_state.last_reset_date != date.today():
    st.session_state.daily_ai_count = 0
    st.session_state.last_reset_date = date.today()
    
with st.expander("💬 TALK TO JAVIS AI CO-PILOT", expanded=False):
    st.caption("🤖 Powered by Chrona — ถามราคาหุ้น หรือวิเคราะห์พอร์ตโฟลิโอของคุณต่อเนื่องสดๆ จาก Supabase ได้ทันที")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["text"])
    if user_input := st.chat_input("คุยกับ Javis..."):
        with st.chat_message("user"):
            st.write(user_input)
        st.session_state.messages.append({"role": "user", "text": user_input})
        with st.chat_message("assistant"):
            if st.session_state.daily_ai_count >= 10:
                response_text = "🚫 **Daily Limit Reached**\n\nคุณใช้ Javis ครบ 10 ครั้งแล้วในวันนี้ โปรดลองใหม่ในวันพรุ่งนี้"
            else:
                with st.spinner("Javis กำลังวิเคราะห์ข้อมูล..."):
                    try:
                        response_text = run_javis_agent(user_input)
                        st.session_state.daily_ai_count += 1
                    except Exception as e:
                        response_text = f"❌ Javis Error\n\n{str(e)}"
            st.write(response_text)
            st.session_state.messages.append({"role": "assistant", "text": response_text})

# ─────────────────────────────────────────────
# TABS SYSTEM
# ─────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Chart & Technicals", "🏦 Fundamentals", "🤖 AI Prediction", "📰 News & Sentiment", "💼 Portfolio", "🏆 Rankings"
])

# TAB 1 — CHART & TECHNICALS
with tab1:
    if hist.empty:
        st.warning("ไม่มีข้อมูลประวัติราคาสำหรับหุ้นตัวนี้ในการสร้างกราฟ")
    else:
        # 🟢 ใช้ Tooltip ที่ Subheader เพื่อบอกความหมายกราฟ
        st.subheader("📊 Advanced Quant Candlestick Chart", help="กราฟแท่งเทียนแสดงการเคลื่อนไหวของราคา พร้อมเส้นค่าเฉลี่ย SMA และกรอบความผันผวน Bollinger Bands")
        
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=hist.index, open=hist["Open"], high=hist["High"], low=hist["Low"], close=hist["Close"], name="Price",
            increasing_line_color="#00d4aa", decreasing_line_color="#ff6b6b",
        ))
        if "BB_Upper" in hist.columns and "BB_Lower" in hist.columns:
            fig.add_trace(go.Scatter(x=hist.index, y=hist["BB_Upper"], name="BB Upper (2σ)", line=dict(color="#64748b", width=1, dash="dash")))
            fig.add_trace(go.Scatter(x=hist.index, y=hist["BB_Lower"], name="BB Lower (2σ)", line=dict(color="#64748b", width=1, dash="dash"), fill='tonexty', fillcolor='rgba(100, 116, 139, 0.03)'))
        if "SMA_20" in hist.columns:
            fig.add_trace(go.Scatter(x=hist.index, y=hist["SMA_20"], name="SMA 20", line=dict(color="#ffd93d", width=1.5)))
        if "SMA_50" in hist.columns:
            fig.add_trace(go.Scatter(x=hist.index, y=hist["SMA_50"], name="SMA 50", line=dict(color="#a78bfa", width=1.5, dash="dash")))
            
        fig.update_layout(
            paper_bgcolor="#0a0c10", plot_bgcolor="#0a0c10", font=dict(color="#e2e8f0"),
            xaxis=dict(gridcolor="#1e2230", showgrid=True), yaxis=dict(gridcolor="#1e2230", showgrid=True),
            legend=dict(bgcolor="#111318", bordercolor="#1e2230"), xaxis_rangeslider_visible=False, height=500, margin=dict(l=0, r=0, t=30, b=0)
        )
        st.plotly_chart(fig, use_container_width=True)

        # 🟢 เพิ่ม st.popover สำหรับคำอธิบายดัชนีทางเทคนิค (กดแล้วเด้งหน้าต่างสวยๆ)
        col_title1, col_pop1 = st.columns([5, 1])
        with col_title1:
            st.subheader("📐 Statistical Quant Metrics")
        with col_pop1:
            with st.popover("ℹ️ อ่านค่าเหล่านี้อย่างไร?", use_container_width=True):
                st.markdown("### 📘 คู่มืออ่านดัชนีทางเทคนิค")
                st.markdown("**1. RSI (Relative Strength Index):** วัดความแรงของการซื้อขาย (ถ้าเกิน 70 = ซื้อมากไป ระวังลง, ถ้าน้อยกว่า 30 = ขายมากไป ระวังเด้ง)")
                st.markdown("**2. RVOL (Relative Volume):** ปริมาณการซื้อขายเทียบกับค่าเฉลี่ยปกติ (ถ้า > 1.5 แสดงว่าวันนี้มีเจ้ามือหรือรายใหญ่เข้า)")
                st.markdown("**3. ATR (Average True Range):** ความผันผวนของราคาระหว่างวัน (ยิ่งสูง แปลว่าหุ้นสวิงแรงใน 1 วัน)")
                st.markdown("**4. BB Bandwidth:** ความกว้างของกรอบราคา (ถ้าน้อยกว่า 5% แปลว่าหุ้นกำลังบีบตัวและอาจระเบิดแรงเร็วๆ นี้)")
                st.info("เหมาะสำหรับ: สายเทรดเก็งกำไรระยะสั้น (Day/Swing Trade)")

        col1, col2, col3, col4, col5 = st.columns(5)
        rsi_val = hist['RSI'].iloc[-1] if "RSI" in hist.columns and not pd.isna(hist['RSI'].iloc[-1]) else 50.0
        rvol_val = hist['RVOL'].iloc[-1] if "RVOL" in hist.columns and not pd.isna(hist['RVOL'].iloc[-1]) else 1.0
        atr_val = hist['ATR'].iloc[-1] if "ATR" in hist.columns and not pd.isna(hist['ATR'].iloc[-1]) else 0.0
        bb_bw = hist['BB_Bandwidth'].iloc[-1] if "BB_Bandwidth" in hist.columns and not pd.isna(hist['BB_Bandwidth'].iloc[-1]) else 0.0
        volatility = calculate_volatility(hist)
        
        col1.metric("RSI (14)", f"{rsi_val:.1f}", "Overbought" if rsi_val > 70 else ("Oversold" if rsi_val < 30 else "Normal"))
        col2.metric("Rel. Volume (RVOL)", f"{rvol_val:.2f}x", "High Activity" if rvol_val > 1.5 else "Standard")
        col3.metric("ATR (14)", f"${atr_val:.2f}", "Market Range")
        col4.metric("BB Bandwidth", f"{bb_bw:.2f}%", "Squeeze (Low Vol)" if bb_bw < 5 else "Expanded")
        col5.metric("Historical Volatility", f"{volatility:.2f}%", get_risk_level(volatility))

        st.markdown("<hr/>", unsafe_allow_html=True)
        
        # 🟢 เพิ่ม Tooltip ให้ส่วนคำนวณความเสี่ยง
        st.subheader("🧮 Volatility-Based Position Sizing Calculator", help="ระบบจะประเมินความผันผวน (ATR) ณ วันนี้ เพื่อบอกว่าคุณควรซื้อหุ้นจำนวนกี่หุ้นถึงจะไม่เสี่ยงขาดทุนหนักเกินไป")
        
        calc_col1, calc_col2, calc_col3 = st.columns(3)
        with calc_col1:
            capital = st.number_input("เงินทุนในพอร์ตจำลอง ($)", min_value=100.0, value=10000.0, step=500.0, help="ขนาดเงินทุนรวมทั้งหมดที่คุณตั้งใจจะนำมาเทรด")
        with calc_col2:
            risk_pct = st.number_input("ความเสี่ยงที่ยอมรับได้ต่อไม้ (%)", min_value=0.1, max_value=10.0, value=1.0, step=0.5, help="ยอมรับการขาดทุนได้สูงสุดกี่เปอร์เซ็นต์ของเงินทุน (แนะนำ 1-2%)")
        with calc_col3:
            atr_multiplier = st.number_input("ระยะ Stop Loss (เท่าของ ATR)", min_value=1.0, max_value=5.0, value=2.0, step=0.5, help="เผื่อระยะตัดขาดทุนให้กว้างกว่าความสวิงปกติของราคา (แนะนำ 2 เท่า)")
            
        if atr_val > 0:
            current_stock_price = hist["Close"].iloc[-1]
            risk_amount = capital * (risk_pct / 100)
            stop_loss_distance = atr_val * atr_multiplier
            shares_to_buy = risk_amount / stop_loss_distance
            total_investment = shares_to_buy * current_stock_price
            stop_loss_price = current_stock_price - stop_loss_distance
            
            res_col1, res_col2, res_col3 = st.columns(3)
            res_col1.metric("จำนวนหุ้นที่ควรซื้อ", f"{shares_to_buy:.2f} หุ้น")
            res_col2.metric("จุดตัดขาดทุน (Stop Loss)", f"${stop_loss_price:.2f}", f"-${stop_loss_distance:.2f} จากราคาปัจจุบัน")
            res_col3.metric("เงินลงทุนไม้นี้", f"${total_investment:,.2f}", f"{ (total_investment/capital)*100 :.1f}% ของพอร์ต")

# TAB 2 — FUNDAMENTALS
with tab2:
    st.subheader("🏦 Fundamental Analysis", help="สรุปข้อมูลพื้นฐาน งบการเงิน และอัตราส่วนทางการเงินของบริษัท เพื่อวิเคราะห์ความถูกแพงและพื้นฐานกิจการ")
    def fmt(val, prefix="", suffix="", divisor=1, decimals=2):
        if val is None or val != val: return "—"
        return f"{prefix}{val/divisor:,.{decimals}f}{suffix}"
    def fmt_b(val):
        if not val or val != val: return "—"
        if abs(val) >= 1e9: return f"${val/1e9:.2f}B"
        return f"${val/1e6:.2f}M"

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**📊 Valuation (ความถูกแพง)**", help="P/E ยิ่งต่ำยิ่งคืนทุนเร็ว")
        st.metric("P/E Ratio", fmt(info.get("trailingPE")))
        st.metric("Forward P/E", fmt(info.get("forwardPE")))
        st.metric("P/S Ratio", fmt(info.get("priceToSalesTrailing12Months")))
    with col2:
        st.markdown("**💰 Financials (ขนาดธุรกิจ)**")
        st.metric("Market Cap", fmt_b(info.get("marketCap")))
        st.metric("Revenue (TTM)", fmt_b(info.get("totalRevenue")))
        st.metric("Net Income", fmt_b(info.get("netIncomeToCommon")))
    with col3:
        st.markdown("**📈 Growth & Returns (การเติบโต)**")
        st.metric("Revenue Growth", fmt(info.get("revenueGrowth"), suffix="%", divisor=0.01))
        st.metric("ROE (ผลตอบแทนผู้ถือหุ้น)", fmt(info.get("returnOnEquity"), suffix="%", divisor=0.01))
        st.metric("ROA (ผลตอบแทนสินทรัพย์)", fmt(info.get("returnOnAssets"), suffix="%", divisor=0.01))

# TAB 3 — AI PREDICTION
with tab3:
    col_title_ai, col_pop_ai = st.columns([5, 1])
    with col_title_ai:
        st.subheader("🤖 Advanced ML Price Prediction", help="ใช้ Machine Learning เพื่อทำนายแนวโน้มราคาหุ้นในวันพรุ่งนี้")
    with col_pop_ai:
        with st.popover("ℹ️ AI ทำงานอย่างไร?", use_container_width=True):
            st.markdown("### 🧠 กลไกการทำนาย")
            st.markdown("ระบบนี้ใช้ **Random Forest Classifier** ซึ่งเป็นโมเดล AI ที่เรียนรู้จากประวัติศาสตร์ความผันผวน โมเมนตัม และวอลลุ่มของหุ้นตัวนี้ (Quant Features) จากนั้นจึงทำนายความน่าจะเป็นของวันพรุ่งนี้ว่าจะ 'ปิดบวก' หรือ 'ปิดลบ'")
            st.warning("คำเตือน: โมเดลมีไว้เพื่อประกอบการตัดสินใจทางสถิติเท่านั้น ไม่ใช่การแนะนำการลงทุน")
            
    ml_data = hist.dropna() if not hist.empty else pd.DataFrame()
    required_features = ["RSI", "SMA_20", "SMA_50", "MACD", "RVOL", "Momentum_Strength", "ATR", "BB_Bandwidth"]
    
    if ml_data.empty or not all(col in ml_data.columns for col in required_features):
        st.warning(" โครงสร้างข้อมูลทางเทคนิคอลและข้อมูล Quant ไม่เพียงพอสำหรับการประมวลผลโมเดล ML ณ เวลานี้")
    else:
        def prepare_quant_features(df_input):
            df = df_input.copy()
            df["Target"] = (df["Close"].shift(-1) > df["Close"]).astype(int)
            df = df.dropna()
            X = df[required_features]
            y = df["Target"]
            return X, y

        features, target = prepare_quant_features(ml_data)
        
        if len(features) < 30:
            st.warning(f" ข้อมูลดิบมีจำนวนแถวน้อยเกินไป (มี {len(features)} แถว แต่ต้องการขั้นต่ำ 30 แถวเพื่อป้องกัน Overfitting)")
        else:
            X_train, X_test, y_train, y_test = train_test_split(features, target, test_size=0.2, random_state=42, shuffle=False)
            model = RandomForestClassifier(n_estimators=100, max_depth=7, random_state=42)
            model.fit(X_train, y_train)
            
            accuracy = accuracy_score(y_test, model.predict(X_test))
            latest_row = features.iloc[-1:]
            prediction = model.predict(latest_row)[0]
            prediction_proba = model.predict_proba(latest_row)[0]
            confidence = prediction_proba[prediction] * 100

            pred_col1, pred_col2, pred_col3 = st.columns(3)
            if prediction == 1:
                pred_col1.metric("Tomorrow's Call", "📈 Long / Buy (UP)", f"Confidence: {confidence:.1f}%")
            else:
                pred_col1.metric("Tomorrow's Call", "📉 Short / Sell (DOWN)", f"Confidence: {confidence:.1f}%")
                
            pred_col2.metric("Model Predictive Accuracy", f"{accuracy:.1%}", "ความแม่นยำย้อนหลัง")
            
            baseline_win_rate = (target.sum() / len(target)) * 100
            pred_col3.metric("Market Long Baseline", f"{baseline_win_rate:.1f}%", "สัดส่วนวันเขียวในตลาด")

            st.markdown("<hr/>", unsafe_allow_html=True)
            st.subheader("📉 Strategy Equity Curve Backtest", help="กราฟเปรียบเทียบว่าหากเราเทรดซื้อขายตามที่ AI บอกทุกวัน (เส้นสีเขียว) เทียบกับเราซื้อหุ้นเก็บไว้เฉยๆ ไม่ขายเลย (เส้นประ) แบบไหนกำไรเยอะกว่ากัน")
            
            with st.spinner("กำลังรันระบบ Backtest เชิงลึก..."):
                def run_advanced_backtest(df_hist):
                    df = df_hist.copy().dropna()
                    preds, actual_returns = [], []
                    for i in range(40, len(df) - 1):
                        train_chunk = df.iloc[:i]
                        X_bt, y_bt = prepare_quant_features(train_chunk)
                        if len(X_bt) < 15: continue
                        clf = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=42)
                        clf.fit(X_bt, y_bt)
                        current_feat = df.iloc[i:i+1][required_features]
                        preds.append(clf.predict(current_feat)[0])
                        actual_returns.append((df["Close"].iloc[i+1] / df["Close"].iloc[i]) - 1)
                        
                    strat_returns = [ret if pred == 1 else 0 for pred, ret in zip(preds, actual_returns)]
                    curve_strat = pd.Series(strat_returns).add(1).cumprod()
                    curve_market = pd.Series(actual_returns).add(1).cumprod()
                    return pd.DataFrame({"Quant AI Strategy": curve_strat.values, "Market Benchmark": curve_market.values})

                backtest_results = run_advanced_backtest(ml_data)
                
            if not backtest_results.empty:
                bt_fig = go.Figure()
                bt_fig.add_trace(go.Scatter(x=backtest_results.index, y=backtest_results["Quant AI Strategy"], name="Chrona AI Strategy", line=dict(color="#00d4aa", width=2.5)))
                bt_fig.add_trace(go.Scatter(x=backtest_results.index, y=backtest_results["Market Benchmark"], name="Buy & Hold Market", line=dict(color="#a78bfa", width=1.5, dash="dot")))
                
                bt_fig.update_layout(
                    paper_bgcolor="#0a0c10", plot_bgcolor="#0a0c10", font=dict(color="#e2e8f0"),
                    xaxis=dict(gridcolor="#1e2230", showgrid=True, title="Trading Bars ย้อนหลัง"), 
                    yaxis=dict(gridcolor="#1e2230", showgrid=True, title="ตัวคูณพอร์ต (Growth Multiplier)"),
                    legend=dict(bgcolor="#111318", bordercolor="#1e2230"),
                    height=450, margin=dict(l=0, r=0, t=20, b=0)
                )
                st.plotly_chart(bt_fig, use_container_width=True)
                
                final_strat_perf = (backtest_results["Quant AI Strategy"].iloc[-1] - 1) * 100
                final_market_perf = (backtest_results["Market Benchmark"].iloc[-1] - 1) * 100
                alpha = final_strat_perf - final_market_perf
                
                if alpha > 0:
                    st.success(f"🔥 **Quant Alpha Detected:** กลยุทธ์ AI ทำผลงานชนะตลาดช็อตนี้อยู่ +{alpha:.2f}%")
                else:
                    st.warning(f"⚠️ **Underperformance:** โมเดลในช่วงนี้ยังแพ้การซื้อถือเฉยๆ อยู่ {alpha:.2f}% แนะนำให้ปรับ Timeframe เพิ่มเติม")

# TAB 4 — NEWS
with tab4:
    st.subheader(f"📰 Latest News — {ticker}", help="รวมข่าวสารล่าสุดที่ส่งผลกระทบต่อราคาหุ้นตัวนี้ พร้อมวิเคราะห์อารมณ์ตลาด (Sentiment) จากเนื้อหาข่าว")
    news = get_stock_news(ticker)
    if not news: 
        st.info("ไม่พบข่าวสารล่าสุดของสินทรัพย์นี้ในปัจจุบัน")
    for article in news:
        title, desc = article.get("title", ""), article.get("description", "")
        sentiment, polarity = analyze_sentiment(title + " " + (desc or ""))
        st.markdown(f"**{title}** ({sentiment})")
        st.caption(f"[Read Article →]({article.get('url', '')})")
        st.markdown("---")

# TAB 5 — PORTFOLIO TRACKER
with tab5:
    st.subheader("💼 Portfolio Tracker (Live DB)", help="ระบบจำลองพอร์ตที่เชื่อมต่อฐานข้อมูล Supabase อัปเดตมูลค่าแบบเรียลไทม์ตามราคาตลาดปัจจุบัน")
    df_portfolio = load_user_portfolio()

    if df_portfolio.empty:
        st.info("ยังไม่มีข้อมูลหุ้นในพอร์ตโฟลิโอของคุณ เพิ่มรายการได้ทันทีจากเมนูฟอร์มบนฝั่งซ้าย ←")
    else:
        rows, total_value, total_cost = [], 0, 0
        for _, pos in df_portfolio.iterrows():
            ticker_sym = pos["ticker"]
            qty = float(pos["qty"])
            avg_cost = float(pos["avg_cost"])
            row_id = pos["id"]
            
            try:
                symbol_formatted = ticker_sym.upper().strip().replace("-", "/")
                price_res = get_cached_price(symbol_formatted)
                current_price = float(price_res["price"]) if "price" in price_res else avg_cost
            except:
                current_price = avg_cost

            cost = qty * avg_cost
            value = qty * current_price
            pnl = value - cost
            pnl_pct = (pnl / cost) * 100 if cost > 0 else 0
            total_value += value
            total_cost += cost

            rows.append({
                "id": row_id, "Ticker": ticker_sym, "Qty": qty, "Avg Cost": f"${avg_cost:.2f}",
                "Current": f"${current_price:.2f}", "Value": f"${value:,.2f}",
                "P&L": f"${pnl:+,.2f}", "P&L %": f"{pnl_pct:+.2f}%", "_val": value
            })

        total_pnl = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost) * 100 if total_cost > 0 else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Value (มูลค่าปัจจุบัน)", f"${total_value:,.2f}")
        c2.metric("Total Cost (ต้นทุนรวม)", f"${total_cost:,.2f}")
        c3.metric("Total P&L (กำไร/ขาดทุนรวม)", f"${total_pnl:+,.2f}", f"{total_pnl_pct:+.2f}%")

        st.markdown("### 📋 สินทรัพย์ในพอร์ตปัจจุบัน")
        display_df = pd.DataFrame(rows).drop(columns=["id", "_val"])
        st.dataframe(display_df, hide_index=True, use_container_width=True)

        st.markdown("### 🗑️ บันทึกการถอน/ลบรายการหุ้น")
        for r in rows:
            col_t, col_btn = st.columns([8, 2])
            col_t.write(f"**{r['Ticker']}** ({r['Qty']} หุ้น) | ต้นทุน {r['Avg Cost']} | มูลค่าตลาด {r['Value']}")
            if col_btn.button("❌ ลบรายการ", key=f"del_{r['id']}", use_container_width=True):
                delete_stock_from_portfolio(r["id"])

        alloc_fig = go.Figure(go.Pie(
            labels=[r["Ticker"] for r in rows], values=[r["_val"] for r in rows], hole=0.5,
            marker=dict(colors=["#00d4aa", "#ffd93d", "#ff6b6b", "#a78bfa", "#60a5fa"])
        ))
        alloc_fig.update_layout(paper_bgcolor="#0a0c10", font=dict(color="#e2e8f0"), height=400, title="Portfolio Allocation")
        st.plotly_chart(alloc_fig, use_container_width=True)

# TAB 6 — AI RANKINGS
with tab6:
    st.subheader("🏆 AI Stock Rankings", help="จัดอันดับความน่าสนใจของหุ้นที่คุณบันทึกไว้ทั้งหมด (ในเมนูซ้ายมือ) โดยนำดัชนีทางเทคนิคมาให้คะแนนเต็ม 100")
    
    if st.button("🚀 เริ่มต้นคำนวณและจัดอันดับหุ้นทั้งหมด", use_container_width=True):
        with st.spinner("กำลังวิเคราะห์และคำนวณค่าทางสถิติเชิงปริมาณ..."):
            results = get_cached_rankings()

        if not results:
            st.warning("ไม่สามารถประมวลผลข้อมูลจัดอันดับหุ้นได้ในขณะนี้เนื่องจากปัญหาการดึงข้อมูลจากภายนอก")
        else:
            ranking_df = pd.DataFrame(results).sort_values("AI Score", ascending=False)

            rank_fig = go.Figure(go.Bar(
                x=ranking_df["Stock"], y=ranking_df["AI Score"],
                marker=dict(color=ranking_df["AI Score"], colorscale=[[0, "#ff6b6b"], [0.5, "#ffd93d"], [1, "#00d4aa"]], showscale=False),
                text=ranking_df["AI Score"].astype(str), textposition="outside",
            ))
            rank_fig.update_layout(
                paper_bgcolor="#0a0c10", plot_bgcolor="#0a0c10", font=dict(color="#e2e8f0"),
                xaxis=dict(gridcolor="#1e2230"), yaxis=dict(gridcolor="#1e2230", range=[0, 110]), height=400, margin=dict(l=0, r=0, t=10, b=0)
            )
            st.plotly_chart(rank_fig, use_container_width=True)
            st.dataframe(ranking_df, hide_index=True, use_container_width=True)

            st.subheader("🗺️ Market Heatmap", help="แผนที่แสดงความแข็งแกร่งของหุ้น ยิ่งสีเขียวสว่างแปลว่าโมเมนตัมยิ่งดี")
            heatmap_fig = px.treemap(
                ranking_df, path=["Stock"], values="AI Score", color="Momentum %",
                color_continuous_scale=[[0, "#ff6b6b"], [0.5, "#111318"], [1, "#00d4aa"]],
            )
            heatmap_fig.update_layout(paper_bgcolor="#0a0c10", font=dict(color="#e2e8f0"), margin=dict(l=0, r=0, t=30, b=0), height=400)
            st.plotly_chart(heatmap_fig, use_container_width=True)