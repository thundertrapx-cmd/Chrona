# 📈 Chrona — Stock Intelligence Dashboard

UI เหมือน screenshot เป๊ะ ทุกฟีเจอร์ใช้งานได้จริง รันบน `localhost:3000`

---

## 🚀 วิธีรัน (ทำทีละขั้น)

### ขั้นที่ 1 — ตั้งค่า Environment Variables ของ Backend

แก้ไขไฟล์ `backend/backend.py` บรรทัดที่ CONFIG:

```python
NEWS_API_KEY      = os.getenv("NEWS_API_KEY",   "ใส่ key ของคุณ")
TWELVE_DATA_KEY   = os.getenv("TWELVE_DATA_API_KEY", "ใส่ key ของคุณ")
SUPABASE_URL      = os.getenv("SUPABASE_URL",   "ใส่ url ของคุณ")
SUPABASE_KEY      = os.getenv("SUPABASE_KEY",   "ใส่ key ของคุณ")
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY",  "ใส่ key ของคุณ")
```

หรือ export เป็น env vars:

```bash
export NEWS_API_KEY="your_key"
export TWELVE_DATA_API_KEY="your_key"
export SUPABASE_URL="https://xxx.supabase.co"
export SUPABASE_KEY="your_anon_key"
export GEMINI_API_KEY="your_key"
```

### ขั้นที่ 2 — รัน Backend (FastAPI)

```bash
cd backend

# ติดตั้ง Python deps
pip install fastapi uvicorn pydantic pandas numpy requests textblob \
  scikit-learn yfinance supabase google-generativeai

# รัน server
uvicorn backend:app --reload --port 8000
```

ตรวจสอบ: เปิด http://localhost:8000/health → ควรได้ `{"status":"ok"}`
API Docs: http://localhost:8000/docs

### ขั้นที่ 3 — รัน Frontend (Next.js)

```bash
cd frontend

# ติดตั้ง Node deps
npm install

# รัน dev server
npm run dev
```

เปิด **http://localhost:3000** 🎉

---

## ✅ ฟีเจอร์ทั้งหมดที่ใช้งานได้

| ฟีเจอร์ | สถานะ | Backend Endpoint |
|---------|--------|-----------------|
| 📈 Live Ticker Bar | ✅ | `/market/overview` |
| 🔍 Search stocks | ✅ | `/stock/{ticker}/quote` |
| 📊 Interactive Chart (Lightweight Charts) | ✅ | `/stock/{ticker}/chart` |
| — MA(20), MA(50), Bollinger Bands | ✅ | included in chart data |
| 📐 Technicals: RSI, RVOL, ATR, MACD | ✅ | `/stock/{ticker}/chart` |
| 🤖 AI Analysis (Sentiment, Trend, Signal) | ✅ | `/stock/{ticker}/analysis` |
| 🧮 Position Sizing Calculator | ✅ | (frontend, uses ATR) |
| 🏦 Fundamentals (P/E, Market Cap, ROE) | ✅ | `/stock/{ticker}/fundamentals` |
| 🧠 ML Prediction (Random Forest) | ✅ | `/stock/{ticker}/ml-prediction` |
| 📉 Backtest Equity Curve | ✅ | included in ml-prediction |
| 📰 News + Sentiment | ✅ | `/stock/{ticker}/news` |
| 💼 Portfolio Tracker (Supabase) | ✅ | `/portfolio` |
| 🏆 AI Stock Rankings | ✅ | `/market/rankings` |
| 🗺️ Market Heatmap | ✅ | included in rankings |
| 🌡️ Sector Heatmap | ✅ | `/market/sector-heatmap` |
| 💬 Chrona AI Chat (Gemini) | ✅ | `/ai/chat` |
| 🔐 Auth (Login/Signup via Supabase) | ✅ | `/auth/login`, `/auth/signup` |
| 📌 Watchlist (add/remove) | ✅ | (frontend state) |

---

## 📁 โครงสร้างไฟล์

```
chrona/
├── frontend/           ← Next.js App
│   ├── app/
│   │   ├── layout.tsx
│   │   └── page.tsx    ← หน้าหลัก (Chrona Dashboard)
│   ├── package.json
│   ├── next.config.js
│   └── tsconfig.json
├── backend/
│   └── backend.py      ← FastAPI server
├── start.sh            ← รันทั้ง 2 พร้อมกัน
└── README.md
```

---

## 🔑 API Keys ที่ต้องการ

| Service | ใช้สำหรับ | ลิงค์ |
|---------|----------|-------|
| [News API](https://newsapi.org) | ข่าวหุ้น | newsapi.org |
| [Twelve Data](https://twelvedata.com) | ราคาหุ้น real-time | twelvedata.com |
| [Supabase](https://supabase.com) | Database + Auth | supabase.com |
| [Google Gemini](https://aistudio.google.com) | AI Chat | aistudio.google.com |

> **Note:** ถ้าไม่มี Twelve Data → ใช้ yfinance (free, ช้ากว่านิดหน่อย)
> ถ้าไม่มี Supabase → Portfolio และ Auth จะใช้ไม่ได้

---

## 🛠️ Supabase Setup

สร้าง table `portfolios` ใน Supabase SQL Editor:

```sql
create table portfolios (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users(id),
  ticker text not null,
  qty float not null,
  avg_cost float not null,
  created_at timestamp default now()
);

alter table portfolios enable row level security;

create policy "Users can manage own portfolio"
  on portfolios for all
  using (auth.uid() = user_id);
```
