# 🚀 คู่มือ Deploy Chrona ให้ใช้งานจริง (ไม่ใช่แค่ localhost)

## ต่างจาก Streamlit ตรงไหน?

Streamlit เป็นแอปตัวเดียว → push ขึ้น GitHub → เชื่อมกับ Streamlit Community Cloud → จบ

Chrona มี **2 ส่วนแยกกัน** ที่ต้องคุยกันผ่าน HTTP:
- **Frontend** (Next.js) — สิ่งที่ผู้ใช้เห็น
- **Backend** (FastAPI + Python) — ทำ logic, เรียก API ภายนอก, ต่อ Supabase

เพราะงั้นต้อง deploy **2 ที่แยกกัน** แล้วบอก frontend ว่า backend อยู่ที่ไหน (แทนที่จะเป็น `localhost:8000`)

แนวทางที่ใกล้เคียง Streamlit Cloud มากที่สุด (ฟรี, เชื่อม GitHub แล้ว auto-deploy ทุกครั้งที่ push):
- Frontend → **Vercel** (บริษัทเดียวกับที่ทำ Next.js)
- Backend → **Render** (รองรับ Python/FastAPI ตรงๆ)

---

## ⚠️ อ่านก่อนทำอะไรทั้งหมด: เรื่อง API Keys

ไฟล์ `.env` ที่แนบมาในโปรเจกต์มี key จริงอยู่ (News API, Twelve Data, Supabase, Gemini) ซึ่งตอนนี้อยู่ในมือหลายที่แล้ว (เครื่องคุณ + ที่อัปโหลดมาคุยกับ Claude) — เพื่อความปลอดภัย:

1. **ห้าม commit ไฟล์ `.env` ขึ้น GitHub เด็ดขาด** (มี `.gitignore` กันไว้ให้แล้ว ดูหัวข้อถัดไป)
2. แนะนำให้ **ไปหมุน (regenerate) key ใหม่ทุกตัว** ก่อน deploy จริง โดยเฉพาะถ้าเป็นไปได้ว่าไฟล์นี้เคยถูกแชร์ที่ไหนมาก่อน:
   - News API: newsapi.org → Account → regenerate key
   - Twelve Data: twelvedata.com → API Keys
   - Google Gemini: aistudio.google.com → API keys → delete + create new
   - Supabase: ถ้าคีย์ที่เห็นคือ **anon/public key** (ใช้คู่กับ Row Level Security ตามที่ README ตั้งไว้) ถือว่าออกแบบมาให้เปิดเผยได้ระดับหนึ่งอยู่แล้ว แต่ถ้าเผลอเอา **service_role key** มาใส่ผิดช่อง ต้อง regenerate ทันทีเพราะตัวนั้น bypass RLS ทั้งหมด — เช็คใน Supabase Dashboard → Settings → API ว่าคีย์ที่ใช้อยู่คือตัวไหน
3. ค่าใหม่ทั้งหมด **ไม่ต้องแก้ในโค้ด** — ไปกรอกใน dashboard ของ Render ตอน deploy (ขั้นตอนด้านล่าง)

---

## สิ่งที่แก้ให้แล้วในโปรเจกต์นี้

- เพิ่ม `.gitignore` — กัน `node_modules/`, `.next/`, `__pycache__/`, `.env` หลุดขึ้น GitHub (ก่อนหน้านี้ไม่มีไฟล์นี้เลย ถ้า push ตอนนั้นจะเอา node_modules 257MB + key จริงขึ้นไปด้วย)
- เพิ่ม `backend/requirements.txt` — ก่อนหน้านี้ไม่มี ทำให้ Render ไม่รู้ต้องลง Python package อะไรบ้าง (README มีคำสั่ง pip install แต่ไม่มีไฟล์ requirements.txt จริง และ`python-dotenv`ที่โค้ดใช้จริงก็ตกหล่นจากลิสต์เดิม)
- แก้ `frontend/app/page.tsx` — เปลี่ยนจาก `const API = 'http://localhost:8000'` ตายตัว เป็นอ่านจาก environment variable `NEXT_PUBLIC_API_URL` (fallback เป็น localhost เหมือนเดิมตอนรัน dev) เพื่อให้ frontend ที่ deploy จริงชี้ไปหา backend จริงได้
- แก้ `backend/backend.py` — CORS เดิม hardcode เป็น `*` (เปิดหมด) ยังใช้งานได้ปกติ แต่เพิ่ม env var `ALLOWED_ORIGINS` ให้ตั้งเป็นโดเมนของคุณได้ทีหลังโดยไม่ต้องแก้โค้ด
- เพิ่ม `render.yaml` — ให้ Render อ่านค่า config อัตโนมัติ (deploy ง่ายขึ้นในขั้นตอนที่ 2)
- เพิ่ม `.env.example` ทั้ง 2 ฝั่ง — เป็น template ไม่มี key จริง

**⚠️ พบไฟล์ frontend ซ้ำกัน 2 ชุดในไฟล์ zip ที่ส่งมา:** ตัวที่อยู่ใน `chrona/app/` (นอก `frontend/`) เป็นเวอร์ชันใหม่กว่า (มีฟีเจอร์ watchlist ในแชทกับแสดง tools ที่ AI ใช้ ที่อีกชุดไม่มี) ส่วนตัวที่อยู่ใน `chrona/frontend/app/` เป็นเวอร์ชันเก่ากว่า 6 วัน แต่เป็นตัวที่มี `node_modules`/build จริงอยู่ด้วย — ผมรวมให้แล้วโดยใช้โค้ดฝั่ง `frontend/` เป็นหลัก (ตรงกับโครงสร้างที่ README อธิบายไว้) แล้วเอาเนื้อหาใหม่กว่าจาก `app/` มาแทนที่ ถ้าคุณเคยแก้อะไรที่ `frontend/app/page.tsx` โดยเฉพาะ (ไม่ได้แก้ที่ root) หลังวันที่ 29 มิ.ย. ให้เช็คอีกทีว่าของที่ merge มาครบไหม

---

## ขั้นที่ 1 — เตรียม GitHub repo

จากเครื่องคุณเอง (โฟลเดอร์ที่แตกไฟล์ zip อันใหม่นี้):

```bash
cd chrona
git init
git add .
git status   # เช็คก่อน commit ว่าไม่มี .env หรือ node_modules โผล่มาในลิสต์!
git commit -m "Initial commit - ready to deploy"
```

สร้าง repo ใหม่บน GitHub (github.com/new) แล้ว push:

```bash
git remote add origin https://github.com/<your-username>/chrona.git
git branch -M main
git push -u origin main
```

---

## ขั้นที่ 2 — Deploy Backend (FastAPI) บน Render

1. ไปที่ [render.com](https://render.com) → สมัคร/login ด้วย GitHub
2. **New → Blueprint** → เลือก repo `chrona` (Render จะเจอ `render.yaml` อัตโนมัติ)
3. ตอน deploy จะมีช่องให้กรอก env vars ที่ตั้ง `sync: false` ไว้ — กรอกค่า **key ใหม่ที่หมุนแล้ว**:
   - `NEWS_API_KEY`, `TWELVE_DATA_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, `GEMINI_API_KEY`
   - `ALLOWED_ORIGINS` — ใส่ `*` ไปก่อนได้ (จะกลับมาแก้เป็นโดเมนจริงในขั้นที่ 4)
4. กด Deploy Blueprint รอ build เสร็จ (สัก 2-5 นาที)
5. จะได้ URL แบบ `https://chrona-backend.onrender.com` → เก็บไว้ใช้ขั้นถัดไป
6. เช็คว่ารันจริง: เปิด `https://chrona-backend.onrender.com/health` ควรได้ `{"status":"ok"}`

**ข้อควรรู้ (free tier ของ Render ปี 2026):** service จะ "หลับ" ถ้าไม่มีคนเรียกใน 15 นาที แล้วตื่นใหม่ตอนมีคนเปิด (รอประมาณ 30-60 วินาทีตอน cold start) — เหมาะกับโปรเจกต์ส่วนตัว/เดโม ถ้าอยากให้ไม่หลับต้องอัปเป็นแผนเสียเงิน (~$6-7/เดือน)

หาก Blueprint ใช้ไม่ได้ (เช่นไม่เจอไฟล์) ให้ deploy มือแทน: New → Web Service → เลือก repo → Root Directory ใส่ `backend` → Build Command: `pip install -r requirements.txt` → Start Command: `uvicorn backend:app --host 0.0.0.0 --port $PORT` → ใส่ env vars ตามข้อ 3 → Create Web Service

---

## ขั้นที่ 3 — Deploy Frontend (Next.js) บน Vercel

1. ไปที่ [vercel.com](https://vercel.com) → สมัคร/login ด้วย GitHub
2. **Add New → Project** → เลือก repo `chrona`
3. ⚠️ **สำคัญ**: ในหน้า Configure Project ตรง **Root Directory** ให้กด Edit แล้วเลือก `frontend` (ไม่งั้น Vercel จะพยายาม build จาก repo root ซึ่งไม่มี Next.js app อยู่ตรงนั้นแล้ว)
4. ตรง **Environment Variables** เพิ่ม:
   - `NEXT_PUBLIC_API_URL` = URL backend จาก Render ที่ได้จากขั้นที่ 2 (เช่น `https://chrona-backend.onrender.com`)
5. กด Deploy รอสัก 1-2 นาที
6. จะได้โดเมนแบบ `https://chrona-xxxx.vercel.app`

Vercel free (Hobby) plan: ใช้ฟรีได้เต็มที่สำหรับโปรเจกต์ส่วนตัว/ไม่แสวงกำไรโดยตรง — ถ้าจะทำเป็นธุรกิจ/เก็บเงินผู้ใช้ ต้องอัปเป็น Pro ($20/เดือน)

---

## ขั้นที่ 4 — เชื่อมสองฝั่งให้ปลอดภัยขึ้น (ทำหลัง deploy เสร็จทั้งคู่)

กลับไปที่ Render → service `chrona-backend` → Environment → แก้ `ALLOWED_ORIGINS` จาก `*` เป็นโดเมน Vercel จริง เช่น:

```
ALLOWED_ORIGINS=https://chrona-xxxx.vercel.app
```

Save แล้ว Render จะ redeploy backend ให้เอง — ตอนนี้ backend จะรับ request จากโดเมนของคุณเท่านั้น ปลอดภัยกว่าเปิดรับทุกที่ (`*`)

---

## เช็คลิสต์ก่อนบอกว่า "deploy เสร็จแล้ว"

- [ ] เปิดโดเมน Vercel แล้วหน้าเว็บขึ้น ไม่ error
- [ ] ลอง search หุ้น / ดูกราฟ ได้ (เรียก backend ผ่านเน็ตจริง ไม่ใช่ localhost)
- [ ] Login/Signup (Supabase auth) ทำงาน
- [ ] เปิด browser console (F12) เช็คว่าไม่มี CORS error สีแดง
- [ ] `git status` ไม่มี `.env` หรือ `node_modules` ติดไปใน repo (เช็คได้ที่หน้า GitHub repo ของคุณด้วยตาเปล่า)
- [ ] หมุน API key ใหม่แล้วอย่างน้อยตัวที่สำคัญ (Gemini, Supabase service key ถ้ามี)

---

## ทางเลือกอื่นนอกจาก Render/Vercel

- **Railway** — DX ดีคล้าย Render แต่ปี 2026 ไม่มี free tier แท้แล้ว (ต่ำสุด ~$5/เดือน)
- **Fly.io** — ยืดหยุ่นกว่า แต่ setup ด้วย CLI/Docker ซับซ้อนกว่า Render พอสมควร
- ถ้าอยากรวบเป็นที่เดียว: บาง provider (เช่น Render เอง) รองรับ deploy static export ของ Next.js เป็น Static Site ได้ แต่ฟีเจอร์ที่ต้องเรียก API ยังต้องมี backend แยกอยู่ดี — สำหรับแอปนี้แนะนำ Vercel + Render ตามข้างบนเพราะง่ายสุดและรองรับ Next.js App Router เต็มรูปแบบ

## หมายเหตุทางเทคนิคเพิ่มเติม

`google-generativeai` (ที่ `javis_brain.py` ใช้อยู่) ถูก Google ประกาศเลิกดูแลแล้ว (deprecated) แนะนำให้ย้ายไป SDK ใหม่ `google-genai` ในอนาคต แต่ยังใช้งานได้อยู่ตอนนี้ ไม่กระทบการ deploy รอบนี้ — เป็นเรื่องที่ทำทีหลังได้
