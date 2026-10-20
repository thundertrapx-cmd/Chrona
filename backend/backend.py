"""
Chrona FastAPI Backend — Full Feature
รัน: uvicorn backend:app --reload --port 8000
"""
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import os, json, time, sys, threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Optional, List
import pandas as pd
import numpy as np
import requests
from textblob import TextBlob
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import yfinance as yf
from supabase import create_client, Client
import google.generativeai as genai
from javis_brain import run_javis_brain

# ─────────────────────────────────────────────
# โหลดค่าจากไฟล์ .env (ต้องวางไฟล์นี้ไว้โฟลเดอร์เดียวกับ backend.py)
# ─────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("⚠️  ไม่พบ python-dotenv — รัน: pip install python-dotenv")

app = FastAPI(title="Chrona API", version="3.0")

# ── CORS ── ค่า default เป็น "*" (เหมือนเดิม ใช้ได้ทั้ง local dev)
# ตอน deploy จริง แนะนำตั้ง env var ALLOWED_ORIGINS เป็นโดเมน frontend ตรงๆ
# เช่น ALLOWED_ORIGINS=https://chrona.vercel.app
_allowed_origins = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = ["*"] if _allowed_origins == "*" else [o.strip() for o in _allowed_origins.split(",")]
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
# บีบอัด response (chart 1y/5y มี array เยอะ ลดขนาดได้หลายเท่า)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ── CONFIG ── อ่านจาก .env หรือ environment variable
NEWS_API_KEY      = os.getenv("NEWS_API_KEY", "YOUR_NEWS_API_KEY")
TWELVE_DATA_KEY   = os.getenv("TWELVE_DATA_API_KEY", "YOUR_TWELVE_DATA_KEY")
SUPABASE_URL      = os.getenv("SUPABASE_URL", "YOUR_SUPABASE_URL")
SUPABASE_KEY      = os.getenv("SUPABASE_KEY", "YOUR_SUPABASE_KEY")
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_KEY")

# ── ตรวจสอบค่าก่อนสร้าง client เพื่อให้ error message อ่านง่าย ──
_missing = []
if SUPABASE_URL in ("YOUR_SUPABASE_URL", "") or not SUPABASE_URL.startswith("http"):
    _missing.append("SUPABASE_URL")
if SUPABASE_KEY in ("YOUR_SUPABASE_KEY", ""):
    _missing.append("SUPABASE_KEY")

if _missing:
    print("\n" + "="*60)
    print("❌ ไม่พบค่า:", ", ".join(_missing))
    print("="*60)
    print("วิธีแก้:")
    print("  1. สร้างไฟล์ .env ในโฟลเดอร์เดียวกับ backend.py")
    print("  2. ใส่ค่าตามแบบนี้ (ไม่ต้องมีเครื่องหมายคำพูด):")
    print("     SUPABASE_URL=https://xxxxx.supabase.co")
    print("     SUPABASE_KEY=eyJxxxxx...")
    print("  3. ติดตั้ง: pip install python-dotenv")
    print("  4. รันใหม่: uvicorn backend:app --reload --port 8000")
    print("="*60 + "\n")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
if GEMINI_API_KEY != "YOUR_GEMINI_KEY":
    genai.configure(api_key=GEMINI_API_KEY)

security = HTTPBearer(auto_error=False)

# ─────────────────────────────────────────────
# CACHE + TWELVE DATA GUARD  (ตัวช่วยให้เร็วขึ้น)
# ─────────────────────────────────────────────
_cache: dict = {}
_cache_lock = threading.Lock()

def cached(key: str, ttl: float, fn, ok=lambda v: True):
    """เก็บผลลัพธ์ในหน่วยความจำ ttl วินาที — ถ้า fn ล้มเหลว (raise) หรือ ok(v)=False จะไม่ถูกเก็บ"""
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    val = fn()
    if ok(val):
        with _cache_lock:
            if len(_cache) > 600:  # กัน memory บวม (free tier แรมน้อย)
                for k in sorted(_cache, key=lambda k: _cache[k][0])[:200]:
                    _cache.pop(k, None)
            _cache[key] = (now, val)
    return val

_td_block_until = 0.0

def td_get(url: str, timeout: float = 6):
    """เรียก Twelve Data — ถ้าชน rate limit (free tier 8 req/นาที) จะพักการเรียก 60 วิ
    แล้วให้ caller ไปใช้ yfinance ทันที แทนที่จะรอ timeout/ได้ error ซ้ำๆ"""
    global _td_block_until
    if TWELVE_DATA_KEY == "YOUR_TWELVE_DATA_KEY" or time.time() < _td_block_until:
        return None
    try:
        res = requests.get(url, timeout=timeout).json()
    except Exception:
        return None
    if isinstance(res, dict) and (res.get("code") == 429 or "credits" in str(res.get("message", "")).lower()):
        _td_block_until = time.time() + 60
        return None
    return res

def _td_to_df(res) -> pd.DataFrame:
    df = pd.DataFrame(res["values"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").sort_index()
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})

_name_cache: dict = {}   # symbol -> ชื่อบริษัท (เก็บจาก fundamentals/Twelve Data)

def _yf_fast(sym: str):
    """ราคา + ราคาปิดก่อนหน้า แบบเบา (fast_info) — เร็วกว่า .info หลายเท่า"""
    info = yf.Ticker(sym).fast_info
    return float(info.last_price), float(info.previous_close)

# ─────────────────────────────────────────────
# HELPERS (ลอก logic จาก app.py ตรงๆ)
# ─────────────────────────────────────────────
def calculate_rsi(data: pd.Series, window=14):
    delta = data.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(data: pd.Series):
    exp1 = data.ewm(span=12, adjust=False).mean()
    exp2 = data.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal

def enrich_hist(raw: pd.DataFrame) -> pd.DataFrame:
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
    high_close = (h["High"] - h["Close"].shift(1)).abs()
    low_close  = (h["Low"]  - h["Close"].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    h["ATR"] = tr.rolling(14).mean()
    return h

def load_stock_data(ticker: str, period="1d") -> pd.DataFrame:
    ttl = 60 if period == "1d" else 300
    return cached(f"hist:{ticker.upper()}:{period}", ttl,
                  lambda: _load_stock_data(ticker, period), ok=lambda d: not d.empty)

def _load_stock_data(ticker: str, period="1d") -> pd.DataFrame:
    period_map = {"1d":5,"1w":7,"1m":30,"3m":90,"1y":260,"5y":1300}
    output_size = period_map.get(period, 30) + 50
    interval = "5min" if period == "1d" else "1day"

    sym_td = ticker.upper().replace("-", "/")
    res = td_get(f"https://api.twelvedata.com/time_series?symbol={sym_td}&interval={interval}&outputsize={output_size}&apikey={TWELVE_DATA_KEY}")
    if res and "values" in res:
        try: return enrich_hist(_td_to_df(res))
        except Exception: pass

    yf_period = {"1d":"1d","1w":"5d","1m":"1mo","3m":"3mo","1y":"1y","5y":"5y"}.get(period,"1mo")
    yf_interval = "5m" if period == "1d" else "1d"
    try:
        sym_yf = ticker.upper().replace("/", "-")
        df_yf = yf.Ticker(sym_yf).history(period=yf_period, interval=yf_interval)
        if not df_yf.empty:
            return enrich_hist(df_yf[["Open","High","Low","Close","Volume"]])
    except Exception: pass
    return pd.DataFrame()

def load_stock_6mo(ticker: str) -> pd.DataFrame:
    """6mo daily data สำหรับ ML/analysis/rankings — cache 5 นาที (เดิมถูกโหลดซ้ำหลายรอบต่อ 1 request)"""
    return cached(f"hist6:{ticker.upper()}", 300,
                  lambda: _load_stock_6mo(ticker), ok=lambda d: not d.empty)

def _load_stock_6mo(ticker: str) -> pd.DataFrame:
    sym_td = ticker.upper().replace("-", "/")
    res = td_get(f"https://api.twelvedata.com/time_series?symbol={sym_td}&interval=1day&outputsize=180&apikey={TWELVE_DATA_KEY}")
    if res and "values" in res:
        try: return enrich_hist(_td_to_df(res))
        except Exception: pass
    try:
        sym_yf = ticker.upper().replace("/", "-")
        df_yf = yf.Ticker(sym_yf).history(period="6mo")
        if not df_yf.empty:
            return enrich_hist(df_yf[["Open","High","Low","Close","Volume"]])
    except Exception: pass
    return pd.DataFrame()

def calculate_score(hist: pd.DataFrame) -> float:
    if len(hist) < 50: return 50.0
    latest_close = hist["Close"].iloc[-1]
    sma20 = hist["SMA_20"].iloc[-1] if "SMA_20" in hist.columns else latest_close
    sma50 = hist["SMA_50"].iloc[-1] if "SMA_50" in hist.columns else latest_close
    rsi   = hist["RSI"].iloc[-1]   if "RSI"   in hist.columns else 50
    score = 0
    if latest_close > sma20: score += 30
    if sma20 > sma50:        score += 30
    if 40 <= rsi <= 60:      score += 20
    elif rsi < 30:           score += 10
    momentum = ((latest_close - hist["Close"].iloc[-20]) / hist["Close"].iloc[-20]) * 100
    if momentum > 10: score += 20
    return round(min(score, 100), 2)

def get_recommendation(score: float) -> str:
    if score >= 80: return "Strong Buy"
    elif score >= 60: return "Buy"
    elif score >= 40: return "Hold"
    else: return "Avoid"

def calculate_momentum(hist: pd.DataFrame) -> float:
    if len(hist) < 20: return 0.0
    return round(((hist["Close"].iloc[-1] - hist["Close"].iloc[-20]) / hist["Close"].iloc[-20]) * 100, 2)

def calculate_volatility(hist: pd.DataFrame) -> float:
    if len(hist) < 2: return 0.0
    return round(hist["Close"].pct_change().std() * 100, 2)

def get_risk_level(vol: float) -> str:
    if vol < 2: return "Low"
    elif vol < 4: return "Medium"
    else: return "High"

def analyze_sentiment(text: str):
    polarity = TextBlob(text).sentiment.polarity
    if polarity > 0.1:   return "Bullish", polarity
    elif polarity < -0.1: return "Bearish", polarity
    else:                return "Neutral",  polarity

def get_user_id(creds: HTTPAuthorizationCredentials):
    if not creds:
        raise HTTPException(status_code=401, detail="No token")
    try:
        res = supabase.auth.get_user(creds.credentials)
        return res.user.id
    except:
        raise HTTPException(status_code=401, detail="Invalid token")

def safe_float(v):
    try:
        f = float(v)
        return None if (np.isnan(f) or np.isinf(f)) else round(f, 4)
    except: return None

# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────
class LoginReq(BaseModel):
    email: str; password: str

class SignupReq(BaseModel):
    email: str; password: str

@app.post("/auth/login")
def login(body: LoginReq):
    try:
        res = supabase.auth.sign_in_with_password({"email": body.email, "password": body.password})
        return {"access_token": res.session.access_token, "user": {"id": res.user.id, "email": res.user.email}}
    except:
        raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/auth/signup")
def signup(body: SignupReq):
    try:
        supabase.auth.sign_up({"email": body.email, "password": body.password})
        return {"message": "Signup successful"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/auth/logout")
def logout(creds: HTTPAuthorizationCredentials = Depends(security)):
    try: supabase.auth.sign_out()
    except: pass
    return {"message": "Logged out"}

# ─────────────────────────────────────────────
# MARKET OVERVIEW
# ─────────────────────────────────────────────
def _fast_change(sym: str):
    try:
        price, prev = _yf_fast(sym)
        chg = round(price - prev, 2)
        return price, chg, (round((chg / prev) * 100, 2) if prev else 0)
    except Exception:
        return 0, 0, 0

def _parallel_changes(symbols: dict):
    with ThreadPoolExecutor(max_workers=min(len(symbols), 9)) as ex:
        futs = {label: ex.submit(_fast_change, sym) for label, sym in symbols.items()}
        return {label: f.result() for label, f in futs.items()}

@app.get("/market/overview")
def market_overview():
    def build():
        symbols = {"NASDAQ":"^IXIC","DOW":"^DJI","S&P 500":"^GSPC","VIX":"^VIX","AAPL":"AAPL","NVDA":"NVDA","BTC":"BTC-USD","GOLD":"GC=F","MSFT":"MSFT"}
        res = _parallel_changes(symbols)
        return {"indices": [{"label": l, "price": p, "change": c, "change_pct": pct} for l, (p, c, pct) in res.items()]}
    return cached("market:overview", 60, build, ok=lambda d: any(i["price"] for i in d["indices"]))

@app.get("/market/sector-heatmap")
def sector_heatmap():
    def build():
        sector_etfs = {"TECH":"XLK","COMM":"XLC","HLTH":"XLV","FINL":"XLF","CYCL":"XLY","INDU":"XLI","ENRG":"XLE","UTIL":"XLU"}
        res = _parallel_changes(sector_etfs)
        return {"sectors": [{"sector": sec, "change_pct": float(pct), "ticker": sector_etfs[sec]} for sec, (_, _, pct) in res.items()]}
    return cached("market:sectors", 120, build, ok=lambda d: any(x["change_pct"] for x in d["sectors"]))

@app.get("/market/quotes")
def batch_quotes(symbols: str = Query("AAPL")):
    """quote หลายตัวในคำขอเดียว (ใช้กับ watchlist) — ยิงขนาน + cache แทนการยิง 5-10 request แยกจาก frontend"""
    syms = [x.strip().upper() for x in symbols.split(",") if x.strip()][:25]
    def one(sym):
        try: return sym, get_quote(sym)
        except Exception: return sym, None
    with ThreadPoolExecutor(max_workers=min(len(syms) or 1, 6)) as ex:
        out = dict(ex.map(one, syms))
    return {"quotes": {k: v for k, v in out.items() if v}}

# ─────────────────────────────────────────────
# STOCK DATA
# ─────────────────────────────────────────────
@app.get("/stock/{ticker}/quote")
def get_quote(ticker: str):
    sym = ticker.upper()
    return cached(f"quote:{sym}", 30, lambda: _fetch_quote(sym))

def _fetch_quote(sym: str):
    res = td_get(f"https://api.twelvedata.com/quote?symbol={sym.replace('-', '/')}&apikey={TWELVE_DATA_KEY}", timeout=5)
    if res and "price" in res:
        try:
            price = float(res["price"]); chg = float(res.get("change", 0)); pct = float(res.get("percent_change", 0))
            name = res.get("name", sym)
            _name_cache[sym] = name
            return {"ticker": sym, "name": name, "price": price, "change": chg, "change_pct": pct}
        except Exception: pass
    try:
        price, prev = _yf_fast(sym.replace("/", "-"))
        chg = round(price - prev, 2); pct = round((chg/prev)*100, 2) if prev else 0
        return {"ticker": sym, "name": _name_cache.get(sym, sym), "price": price, "change": chg, "change_pct": pct}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stock/{ticker}/chart")
def get_chart(ticker: str, period: str = "1d"):
    hist = load_stock_data(ticker, period)
    if hist.empty:
        raise HTTPException(status_code=404, detail=f"No data for {ticker}")
    hist = hist.replace([np.inf, -np.inf], np.nan).dropna(subset=["Close"])
    result = {
        "ticker": ticker.upper(), "period": period,
        "timestamps": [str(idx) for idx in hist.index],
        "open":   [safe_float(v) for v in hist["Open"]],
        "high":   [safe_float(v) for v in hist["High"]],
        "low":    [safe_float(v) for v in hist["Low"]],
        "close":  [safe_float(v) for v in hist["Close"]],
        "volume": [int(v) if not np.isnan(float(v)) else 0 for v in hist["Volume"]],
    }
    for col, key in [("SMA_20","sma20"),("SMA_50","sma50"),("BB_Upper","bb_upper"),("BB_Lower","bb_lower"),("MACD","macd"),("MACD_Signal","macd_signal"),("ATR","atr")]:
        if col in hist.columns:
            result[key] = [safe_float(v) for v in hist[col]]
    if "RSI" in hist.columns:
        rsi_clean = hist["RSI"].dropna()
        result["rsi"] = safe_float(rsi_clean.iloc[-1]) if not rsi_clean.empty else None
    if "Volume_SMA" in hist.columns:
        vs = hist["Volume_SMA"].dropna()
        result["volume_sma"] = safe_float(vs.iloc[-1]) if not vs.empty else None
    if "RVOL" in hist.columns:
        rv = hist["RVOL"].dropna()
        result["rvol"] = safe_float(rv.iloc[-1]) if not rv.empty else None
    score = calculate_score(hist)
    result["ai_score"]   = score
    result["ai_signal"]  = get_recommendation(score)
    result["confidence"] = "Very High" if score >= 90 else ("High" if score >= 70 else ("Medium" if score >= 50 else "Low"))
    return result

@app.get("/stock/{ticker}/analysis")
def get_analysis(ticker: str):
    hist = load_stock_6mo(ticker)
    if hist.empty: raise HTTPException(status_code=404, detail="No data")
    score    = calculate_score(hist)
    last     = hist["Close"].iloc[-1]
    sma20    = hist["SMA_20"].dropna().iloc[-1] if "SMA_20" in hist.columns and not hist["SMA_20"].dropna().empty else last
    sma50    = hist["SMA_50"].dropna().iloc[-1] if "SMA_50" in hist.columns and not hist["SMA_50"].dropna().empty else last
    rsi      = hist["RSI"].dropna().iloc[-1]    if "RSI"   in hist.columns and not hist["RSI"].dropna().empty else 50
    vol      = calculate_volatility(hist)
    momentum = calculate_momentum(hist)

    sentiment  = "Bullish" if last > sma20 else "Bearish"
    mom_str    = "Strong"  if last > sma20 > sma50 else "Weak"
    trend      = "Uptrend" if last > sma50 else "Downtrend"
    vol_str    = "Low" if vol < 2 else ("High" if vol > 4 else "Medium")

    reasons = []
    if rsi < 35:              reasons.append("RSI in oversold zone")
    elif 40 <= rsi <= 60:     reasons.append("RSI in healthy zone")
    if last > sma20 > sma50:  reasons.append("MACD bullish crossover")
    if last > sma20:          reasons.append("Strong momentum")
    if "RVOL" in hist.columns:
        rvol = hist["RVOL"].dropna()
        if not rvol.empty and rvol.iloc[-1] > 1.2: reasons.append("Volume above average")

    return {
        "ticker": ticker.upper(), "ai_score": score,
        "signal": get_recommendation(score),
        "confidence": "Very High" if score >= 90 else ("High" if score >= 70 else ("Medium" if score >= 50 else "Low")),
        "sentiment": sentiment, "momentum": mom_str, "trend": trend, "volatility": vol_str,
        "momentum_pct": momentum, "volatility_pct": vol,
        "rsi": round(rsi, 2), "sma20": round(sma20, 2), "sma50": round(sma50, 2),
        "prediction": "UP" if score >= 55 else "DOWN",
        "prediction_confidence": round(min(score + 5, 99), 1),
        "reasons": reasons[:4],
    }

@app.get("/stock/{ticker}/fundamentals")
def get_fundamentals(ticker: str):
    sym = ticker.upper().replace("/", "-")
    return cached(f"fund:{sym}", 3600, lambda: _fetch_fundamentals(sym), ok=lambda d: d.get("marketCap") is not None)

def _fetch_fundamentals(sym: str):
    data = {"longName": sym, "sector": "—", "industry": "—", "trailingPE": None, "forwardPE": None,
            "priceToSalesTrailing12Months": None, "marketCap": None, "totalRevenue": None,
            "netIncomeToCommon": None, "revenueGrowth": None, "returnOnEquity": None, "returnOnAssets": None}
    try:
        info = yf.Ticker(sym).info
        for k in data:
            data[k] = info.get(k, data[k])
        data["longName"] = info.get("longName", info.get("shortName", sym))
        _name_cache[sym] = data["longName"]
    except: pass
    return data

@app.get("/stock/{ticker}/news")
def get_news(ticker: str):
    return cached(f"news:{ticker.upper()}", 600, lambda: _fetch_news(ticker), ok=lambda d: any(n.get("url") != "#" for n in d["news"]))

def _fetch_news(ticker: str):
    if NEWS_API_KEY != "YOUR_NEWS_API_KEY":
        url = f"https://newsapi.org/v2/everything?q={ticker}+stock+financial&sortBy=publishedAt&pageSize=6&apiKey={NEWS_API_KEY}"
        try:
            res = requests.get(url, headers={"User-Agent":"ChronaDashboard/3.0"}, timeout=5).json()
            articles = res.get("articles", [])[:6]
            result = []
            for a in articles:
                sent, _ = analyze_sentiment((a.get("title","") + " " + (a.get("description") or "")))
                result.append({
                    "title": a.get("title",""), "source": a.get("source",{}).get("name",""),
                    "sentiment": sent, "url": a.get("url","#"),
                    "time": a.get("publishedAt","")[:10], "description": a.get("description","")
                })
            return {"news": result}
        except: pass
    return {"news": [
        {"title": f"{ticker} showing strong technical signals", "source": "Chrona AI", "sentiment": "Bullish", "url": "#", "time": str(date.today())},
        {"title": f"Market analysis: {ticker} in focus", "source": "Chrona AI", "sentiment": "Neutral", "url": "#", "time": str(date.today())},
    ]}

# ─────────────────────────────────────────────
# ML PREDICTION (RandomForest จาก app.py)
# ─────────────────────────────────────────────
@app.get("/stock/{ticker}/ml-prediction")
def ml_prediction(ticker: str):
    return cached(f"ml:{ticker.upper()}", 600, lambda: _ml_prediction(ticker))

def _ml_prediction(ticker: str):
    hist = load_stock_6mo(ticker)
    if hist.empty or len(hist) < 50:
        raise HTTPException(status_code=400, detail="Not enough data for ML prediction")

    required_features = ["SMA_20","SMA_50","RSI","MACD","MACD_Signal","Volume_SMA","RVOL","ATR","BB_Bandwidth","Momentum_Strength"]
    ml_data = hist.copy()
    ml_data["Target"] = (ml_data["Close"].shift(-1) > ml_data["Close"]).astype(int)
    ml_data = ml_data.dropna()

    available = [f for f in required_features if f in ml_data.columns]
    if len(available) < 4 or len(ml_data) < 30:
        raise HTTPException(status_code=400, detail=f"Not enough feature data ({len(ml_data)} rows)")

    features = ml_data[available]
    target   = ml_data["Target"]

    try:
        X_train, X_test, y_train, y_test = train_test_split(features, target, test_size=0.2, random_state=42, shuffle=False)
        model = RandomForestClassifier(n_estimators=100, max_depth=7, random_state=42)
        model.fit(X_train, y_train)
        accuracy     = accuracy_score(y_test, model.predict(X_test))
        latest_row   = features.iloc[-1:]
        prediction   = model.predict(latest_row)[0]
        confidence   = model.predict_proba(latest_row)[0][prediction] * 100
        baseline     = (target.sum() / len(target)) * 100
        feat_imp     = dict(zip(available, model.feature_importances_.tolist()))

        # Backtest (walk-forward: เทรนใหม่ทุก 5 วัน แทนที่จะเทรนใหม่ทุกวัน → เร็วขึ้น ~5 เท่า ผลใกล้เคียงเดิม)
        bt_strat, bt_market = [], []
        clf = None
        for i in range(40, min(len(ml_data)-1, 120)):
            if clf is None or (i - 40) % 5 == 0:
                chunk = ml_data.iloc[:i]
                clf = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=42)
                clf.fit(chunk[available], chunk["Target"])
            pred = clf.predict(ml_data.iloc[i:i+1][available])[0]
            ret  = (ml_data["Close"].iloc[i+1] / ml_data["Close"].iloc[i]) - 1
            bt_strat.append(ret if pred == 1 else 0)
            bt_market.append(ret)

        curve_strat  = (pd.Series(bt_strat).add(1).cumprod().tolist())  if bt_strat  else []
        curve_market = (pd.Series(bt_market).add(1).cumprod().tolist()) if bt_market else []
        final_strat  = ((curve_strat[-1]  - 1) * 100) if curve_strat  else 0
        final_market = ((curve_market[-1] - 1) * 100) if curve_market else 0

        return {
            "ticker": ticker.upper(),
            "prediction": "UP" if prediction == 1 else "DOWN",
            "confidence": round(confidence, 1),
            "accuracy": round(accuracy * 100, 1),
            "baseline": round(baseline, 1),
            "feature_importance": {k: round(v*100,1) for k,v in sorted(feat_imp.items(), key=lambda x:-x[1])},
            "backtest": {
                "strategy_curve": [round(v,4) for v in curve_strat],
                "market_curve":   [round(v,4) for v in curve_market],
                "strategy_return": round(final_strat, 2),
                "market_return":   round(final_market, 2),
                "alpha": round(final_strat - final_market, 2),
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────
# DASHBOARD (รวมข้อมูลทุกอย่างของหุ้นตัวเดียวในครั้งเดียว)
# ─────────────────────────────────────────────
@app.get("/api/dashboard/{ticker}")
def get_dashboard(ticker: str):
    hist = load_stock_6mo(ticker)
    if hist.empty:
        raise HTTPException(status_code=404, detail=f"No data for {ticker}")

    quote        = get_quote(ticker)
    analysis     = get_analysis(ticker)
    chart        = get_chart(ticker, "1m")
    news         = get_news(ticker)
    fundamentals = get_fundamentals(ticker)

    return {
        "quote": quote,
        "analysis": analysis,
        "chart": chart,
        "news": news["news"],
        "fundamentals": fundamentals,
    }

# ─────────────────────────────────────────────
# RANKINGS
# ─────────────────────────────────────────────
@app.get("/market/rankings")
def get_rankings(tickers: str = Query("AAPL,NVDA,MSFT,META,TSLA,AMZN,GOOGL,AMD,NFLX,PLTR")):
    stock_list = list(dict.fromkeys(t.strip().upper() for t in tickers.split(",") if t.strip()))[:20]

    def one(sym):
        try:
            hist = load_stock_6mo(sym)
            if hist.empty or len(hist) < 2: return None
            score    = calculate_score(hist)
            vol      = calculate_volatility(hist)
            rsi_s    = hist["RSI"].dropna() if "RSI" in hist.columns else pd.Series(dtype=float)
            return {
                "stock": sym,
                "price": round(float(hist["Close"].iloc[-1]), 2),
                "ai_score": score,
                "signal": get_recommendation(score),
                "momentum_pct": calculate_momentum(hist),
                "volatility_pct": vol,
                "risk": get_risk_level(vol),
                "rsi": round(float(rsi_s.iloc[-1]), 2) if not rsi_s.empty else None,
            }
        except Exception:
            return None

    def build():
        with ThreadPoolExecutor(max_workers=4) as ex:
            results = [r for r in ex.map(one, stock_list) if r]
        results.sort(key=lambda x: x["ai_score"], reverse=True)
        return {"rankings": results}
    return cached("rank:" + ",".join(stock_list), 300, build, ok=lambda d: len(d["rankings"]) > 0)

# ─────────────────────────────────────────────
# PORTFOLIO
# ─────────────────────────────────────────────
class PortfolioItem(BaseModel):
    ticker: str; qty: float; avg_cost: float

@app.get("/portfolio")
def get_portfolio(creds: HTTPAuthorizationCredentials = Depends(security)):
    user_id = get_user_id(creds)
    try:
        res   = supabase.table("portfolios").select("*").eq("user_id", user_id).execute()
        items = res.data or []
        rows, total_value, total_cost = [], 0, 0
        for pos in items:
            sym = pos["ticker"].upper().strip()
            qty = float(pos["qty"]); avg_cost = float(pos["avg_cost"])
            try:
                sym_yf = sym.replace("/", "-")
                info   = yf.Ticker(sym_yf).fast_info
                current_price = float(info.last_price) if hasattr(info,"last_price") else avg_cost
            except:
                current_price = avg_cost
            cost = qty * avg_cost; value = qty * current_price; pnl = value - cost
            pnl_pct = (pnl / cost) * 100 if cost > 0 else 0
            total_value += value; total_cost += cost
            rows.append({"id": pos["id"], "ticker": sym, "qty": qty, "avg_cost": avg_cost,
                         "current_price": round(current_price,2), "value": round(value,2),
                         "pnl": round(pnl,2), "pnl_pct": round(pnl_pct,2)})
        total_pnl     = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost) * 100 if total_cost > 0 else 0
        return {"positions": rows,
                "total_value": round(total_value,2), "total_cost": round(total_cost,2),
                "total_pnl": round(total_pnl,2), "total_pnl_pct": round(total_pnl_pct,2)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/portfolio")
def add_portfolio(item: PortfolioItem, creds: HTTPAuthorizationCredentials = Depends(security)):
    user_id = get_user_id(creds)
    try:
        supabase.table("portfolios").insert({"user_id": user_id, "ticker": item.ticker.upper(), "qty": item.qty, "avg_cost": item.avg_cost}).execute()
        return {"message": "Added"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/portfolio/{row_id}")
def delete_portfolio(row_id: str, creds: HTTPAuthorizationCredentials = Depends(security)):
    user_id = get_user_id(creds)
    supabase.table("portfolios").delete().eq("id", row_id).eq("user_id", user_id).execute()
    return {"message": "Deleted"}

# ─────────────────────────────────────────────
# GEMINI AI CHAT (Javis Agent)
# ─────────────────────────────────────────────
class ChatReq(BaseModel):
    message: str
    ticker: Optional[str] = "AAPL"
    history: Optional[List[dict]] = []
    user_email: Optional[str] = ""
    watchlist: Optional[List[str]] = []

# Tool Router เรียกฟังก์ชันพวกนี้ตรงๆ ในโปรเซสเดียวกัน (ไม่ต้องยิง HTTP self-call)
# ชื่อ key ต้องตรงกับ AVAILABLE_TOOLS ใน javis_brain.py
TOOL_REGISTRY = {
    "get_quote": get_quote,
    "get_analysis": get_analysis,
    "get_chart": lambda t: get_chart(t, "1m"),
    "get_fundamentals": get_fundamentals,
    "get_news": get_news,
    "ml_prediction": ml_prediction,
}

@app.post("/ai/chat")
def ai_chat(body: ChatReq, creds: HTTPAuthorizationCredentials = Depends(security)):
    if GEMINI_API_KEY == "YOUR_GEMINI_KEY":
        return {"reply": "⚠️ กรุณาตั้งค่า GEMINI_API_KEY ใน .env", "used_tools": [], "data": {}}

    # Memory: ถ้ามี token แนบมา (login อยู่) ดึงพอร์ตจาก Supabase มาให้ brain ใช้ได้
    portfolio_data = None
    if creds:
        try:
            user_id = get_user_id(creds)
            res = supabase.table("portfolios").select("*").eq("user_id", user_id).execute()
            portfolio_data = res.data or []
        except Exception:
            portfolio_data = None  # token หมดอายุ/ไม่ได้ login ก็ตอบต่อได้ แค่ไม่มี memory ส่วนนี้

    try:
        return run_javis_brain(
            message=body.message,
            ticker=body.ticker,
            history=body.history or [],
            user_email=body.user_email,
            watchlist=body.watchlist or [],
            portfolio_data=portfolio_data,
            tool_registry=TOOL_REGISTRY,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok", "version": "3.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)