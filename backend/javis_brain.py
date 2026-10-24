"""
Chrona Brain — เวอร์ชัน implement จริงจาก flowchart ที่ออกแบบไว้

แต่ละกล่องในไดอะแกรม map เข้ากับฟังก์ชันในไฟล์นี้ตรงๆ ดังนี้:

    Natural Language Input       -> body.message (ส่งมาจาก backend.py)
    Intent Understanding Engine  -> understand_intent()
    Planner / Orchestrator       -> อยู่ใน tools_needed ที่ understand_intent() ตัดสินใจ
                                     + ลำดับการเรียกใน run_javis_brain()
    Memory                       -> portfolio_data + watchlist (backend.py ส่งเข้ามาให้)
    Tool Router                  -> run_tools()
    Knowledge Router             -> get_knowledge_snippets()
    Context Merger               -> merge_context()
    Response Generation (LLM)    -> generate_response()
    Response Formatter           -> dict ที่ return จาก run_javis_brain()

backend.py เป็นคนเรียก run_javis_brain() ตัวเดียว แล้วส่ง tool_registry (dict ของฟังก์ชันจริง
เช่น get_analysis, ml_prediction) เข้ามา เพื่อไม่ให้ไฟล์นี้ต้อง import backend.py กลับ (circular import)
"""
import json
import google.generativeai as genai

# โมเดลเดียวกับที่ backend.py เคยใช้ — แยกชื่อไว้ 2 ตัวเผื่ออนาคตอยากใช้โมเดลเล็ก/เร็ว
# สำหรับ intent และโมเดลที่แม่นกว่าสำหรับ final answer ก็แค่เปลี่ยนค่าตรงนี้ที่เดียว
INTENT_MODEL_NAME = "gemini-3.1-flash-lite"
REASONING_MODEL_NAME = "gemini-3.1-flash-lite"

# ต้องตรงกับ key ใน TOOL_REGISTRY ที่ backend.py สร้างไว้
AVAILABLE_TOOLS = ["get_quote", "get_analysis", "get_chart", "get_fundamentals", "get_news", "ml_prediction"]

MAX_CONTEXT_CHARS = 6000  # กันไม่ให้ context บวมจนกิน token/ค่าใช้จ่ายเกินจำเป็น


# ─────────────────────────────────────────────
# KNOWLEDGE ROUTER — ฐานความรู้แบบ static (ฟรี ไม่ต้องมี vector DB)
# ─────────────────────────────────────────────
KNOWLEDGE_BASE = {
    "RSI": "RSI (Relative Strength Index) วัดว่าราคาซื้อมากไป (เกิน 70) หรือขายมากไป (ต่ำกว่า 30) ในช่วง 14 วันล่าสุด",
    "MACD": "MACD วัด momentum จากส่วนต่างเส้นค่าเฉลี่ย EMA 12 กับ 26 วัน ใช้ดูจังหวะกลับตัวของเทรนด์",
    "SMA": "SMA (Simple Moving Average) คือราคาเฉลี่ยย้อนหลัง ใช้ดูทิศทางเทรนด์หลัก",
    "BOLLINGER": "Bollinger Bands คือแถบราคาบน-ล่างที่กว้างขึ้นเมื่อความผันผวนสูง ใช้ดูว่าราคาสุดโต่งไปหรือยัง",
    "ATR": "ATR (Average True Range) วัดความผันผวนเฉลี่ยของราคา นิยมใช้ตั้งจุด stop loss ให้เหมาะกับความผันผวนจริง",
    "PE": "P/E Ratio คือราคาหุ้นหารกำไรต่อหุ้น ใช้ประเมินว่าหุ้นแพงหรือถูกเทียบกับกำไรที่ทำได้",
    "MARKET CAP": "Market Cap คือมูลค่าตลาดรวมของบริษัท (ราคาหุ้นคูณจำนวนหุ้นทั้งหมด)",
    "VOLATILITY": "Volatility คือความผันผวนของราคา ยิ่งสูงยิ่งเสี่ยงและโอกาสกำไร/ขาดทุนไวขึ้น",
    "POSITION SIZE": "Position Sizing คือการคำนวณว่าควรซื้อกี่หุ้น โดยอิงจากเงินทุนและระดับความเสี่ยงที่รับได้",
    "STOP LOSS": "Stop Loss คือจุดตัดขาดทุนที่ตั้งไว้ล่วงหน้า เพื่อจำกัดความเสียหายถ้าราคาผิดทาง",
}

# ศัพท์ไทยที่พบบ่อย แม็ปกลับไปหา key ใน KNOWLEDGE_BASE — เพิ่มเองได้เรื่อยๆ ตามที่เจอจริง
KNOWLEDGE_ALIASES = {
    "ค่าเฉลี่ยเคลื่อนที่": "SMA",
    "เส้นค่าเฉลี่ย": "SMA",
    "พีอี": "PE",
    "มูลค่าตลาด": "MARKET CAP",
    "ความผันผวน": "VOLATILITY",
    "ตัดขาดทุน": "STOP LOSS",
    "ขนาดการลงทุน": "POSITION SIZE",
}


def get_knowledge_snippets(message: str, topics: list) -> str:
    """Knowledge Router: หาคำนิยาม/หลักการที่เกี่ยวข้องกับคำถาม ไม่ต้องเรียก LLM เพิ่ม (ฟรี, เร็ว)"""
    text_upper = (message or "").upper()
    matched = set()

    for key in KNOWLEDGE_BASE:
        if key in text_upper:
            matched.add(key)

    for alias, key in KNOWLEDGE_ALIASES.items():
        if alias in (message or ""):
            matched.add(key)

    for topic in (topics or []):
        topic_upper = str(topic).upper().strip()
        if topic_upper in KNOWLEDGE_BASE:
            matched.add(topic_upper)

    if not matched:
        return ""
    return "\n".join(f"- {k}: {KNOWLEDGE_BASE[k]}" for k in sorted(matched))


# ─────────────────────────────────────────────
# INTENT UNDERSTANDING ENGINE + PLANNER
# (สองกล่องนี้รวมเป็นการเรียก Gemini ครั้งเดียว: ผลลัพธ์ JSON ที่ได้ "คือ" แผนการทำงาน)
# ─────────────────────────────────────────────
def understand_intent(message: str, ticker: str, history: list) -> dict:
    fallback = {
        "target_ticker": (ticker or "AAPL").upper(),
        "tools_needed": [],
        "needs_portfolio": False,
        "needs_watchlist": False,
        "knowledge_topics": [],
        "reasoning": "fallback",
    }
    try:
        model = genai.GenerativeModel(
            model_name=INTENT_MODEL_NAME,
            system_instruction=(
                "คุณคือ Intent Understanding Engine ของ Chrona AI หน้าที่เดียวคือวิเคราะห์ข้อความล่าสุด"
                "ของผู้ใช้ แล้วตอบกลับเป็น JSON เท่านั้น ห้ามมีข้อความอื่นนอก JSON เด็ดขาด\n\n"
                "โครงสร้างที่ต้องตอบ:\n"
                "{\n"
                '  "target_ticker": "สัญลักษณ์หุ้นตัวพิมพ์ใหญ่ที่ผู้ใช้กำลังถามถึง ถ้าไม่ชัดเจนให้ใช้ค่าปัจจุบันที่ให้มา",\n'
                f'  "tools_needed": ["เลือกจากลิสต์นี้เท่านั้น: {AVAILABLE_TOOLS} เอาเฉพาะที่จำเป็นจริงๆ"],\n'
                '  "needs_portfolio": true หรือ false (true ถ้าถามเกี่ยวกับพอร์ตตัวเอง เช่น กำไรขาดทุน ถือหุ้นอะไรอยู่),\n'
                '  "needs_watchlist": true หรือ false (true ถ้าถามภาพรวมหุ้นที่ติดตามทั้งหมด),\n'
                '  "knowledge_topics": ["ศัพท์การเงิน/indicator ที่ผู้ใช้พูดถึงหรือควรอธิบายประกอบ"]\n'
                "}"
            ),
            generation_config=genai.GenerationConfig(response_mime_type="application/json"),
        )
        recent_history = (history or [])[-6:]
        history_text = "\n".join(f'{h.get("role", "user")}: {h.get("content", "")}' for h in recent_history)
        prompt = (
            f"หุ้นที่ผู้ใช้กำลังดูอยู่ตอนนี้: {ticker or 'ไม่ระบุ'}\n"
            f"บทสนทนาล่าสุด:\n{history_text}\n\n"
            f"ข้อความล่าสุดของผู้ใช้: {message}"
        )
        response = model.generate_content(prompt)
        parsed = json.loads(response.text)
        tools = [t for t in parsed.get("tools_needed", []) if t in AVAILABLE_TOOLS]
        return {
            "target_ticker": str(parsed.get("target_ticker") or ticker or "AAPL").upper(),
            "tools_needed": tools,
            "needs_portfolio": bool(parsed.get("needs_portfolio", False)),
            "needs_watchlist": bool(parsed.get("needs_watchlist", False)),
            "knowledge_topics": parsed.get("knowledge_topics", []) or [],
            "reasoning": "ok",
        }
    except Exception as e:
        fallback["reasoning"] = f"fallback: {e}"
        return fallback


# ─────────────────────────────────────────────
# TOOL ROUTER
# ─────────────────────────────────────────────
def summarize_tool_result(name: str, data):
    """ตัด field ที่ยาวเกินไป (เช่น array ราคาย้อนหลังทั้งชุด) ก่อนยัดเข้า context ของ LLM
    เพื่อประหยัด token — ไม่กระทบ endpoint เดิมที่ frontend ใช้ทำกราฟ เพราะนี่คนละชุดข้อมูล"""
    if not isinstance(data, dict):
        return data
    if name == "get_chart":
        closes = data.get("close") or []
        return {
            "ticker": data.get("ticker"),
            "period": data.get("period"),
            "latest_close": closes[-1] if closes else None,
            "rsi": data.get("rsi"),
            "ai_score": data.get("ai_score"),
            "ai_signal": data.get("ai_signal"),
        }
    if name == "ml_prediction":
        bt = data.get("backtest", {})
        return {
            "ticker": data.get("ticker"),
            "prediction": data.get("prediction"),
            "confidence": data.get("confidence"),
            "accuracy": data.get("accuracy"),
            "alpha_vs_market": bt.get("alpha"),
        }
    if name == "get_news":
        return {"news": (data.get("news") or [])[:4]}
    return data


def run_tools(tools_needed: list, ticker: str, tool_registry: dict) -> dict:
    """เรียกฟังก์ชันจริงใน backend.py ตามที่ Planner บอกว่าต้องใช้
    ครอบ try/except แยกรายตัว กัน 1 tool พังแล้วทั้งคำตอบล่มไปด้วย"""
    results = {}
    for tool_name in tools_needed:
        fn = tool_registry.get(tool_name)
        if not fn:
            continue
        try:
            results[tool_name] = summarize_tool_result(tool_name, fn(ticker))
        except Exception as e:
            results[tool_name] = {"error": str(e)}
    return results


# ─────────────────────────────────────────────
# CONTEXT MERGER
# ─────────────────────────────────────────────
def merge_context(ticker, portfolio_data, watchlist, watchlist_quotes, tool_results, knowledge_text) -> str:
    parts = [f"หุ้นที่กำลังดูอยู่ตอนนี้: {ticker}"]

    if portfolio_data:
        lines = [f"- {p.get('ticker')}: {p.get('qty')} หุ้น ต้นทุนเฉลี่ย {p.get('avg_cost')}" for p in portfolio_data[:10]]
        parts.append("พอร์ตของผู้ใช้ (Memory):\n" + "\n".join(lines))

    if watchlist_quotes:
        lines = [f"- {q.get('ticker')}: {q.get('price')} ({q.get('change_pct')}%)" for q in watchlist_quotes]
        parts.append("Watchlist ของผู้ใช้ (Memory):\n" + "\n".join(lines))
    elif watchlist:
        parts.append("Watchlist ของผู้ใช้ (Memory): " + ", ".join(watchlist[:10]))

    for name, data in (tool_results or {}).items():
        parts.append(f"ผลจาก tool [{name}]:\n{json.dumps(data, ensure_ascii=False, default=str)}")

    if knowledge_text:
        parts.append("ความรู้ประกอบ (Knowledge Router):\n" + knowledge_text)

    full_context = "\n\n".join(parts)
    if len(full_context) > MAX_CONTEXT_CHARS:
        full_context = full_context[:MAX_CONTEXT_CHARS] + "\n...(ตัดข้อมูลส่วนเกินเพื่อประหยัด token)"
    return full_context


# ─────────────────────────────────────────────
# RESPONSE GENERATION (LLM)
# ─────────────────────────────────────────────
def generate_response(message: str, user_email: str, history: list, merged_context: str) -> str:
    model = genai.GenerativeModel(
        model_name=REASONING_MODEL_NAME,
        system_instruction=(
            f"คุณคือ Javis ผู้ช่วยวิเคราะห์หุ้นของ Chrona สำหรับ {user_email or 'นักลงทุน'} "
            "ตอบเป็นภาษาไทย กระชับ ตรงประเด็น สรุปด้วย bullet points เสมอ ห้ามการันตีกำไร "
            "ถ้ามีข้อมูลจาก tool/portfolio/watchlist แนบมาใน [ข้อมูลประกอบ] ให้ใช้ตัวเลขจากตรงนั้นจริงๆ "
            "ห้ามเดาตัวเลขเอง ถ้าถามเรื่องหุ้นให้บอก sentiment, trend และ risk เสมอ"
        ),
    )
    history_fmt = [{"role": h.get("role", "user"), "parts": [h.get("content", "")]} for h in (history or [])]
    chat = model.start_chat(history=history_fmt)
    full_message = f"[ข้อมูลประกอบ]\n{merged_context}\n\n[คำถามผู้ใช้]\n{message}"
    response = chat.send_message(full_message)
    return response.text


# ─────────────────────────────────────────────
# ORCHESTRATOR — ไล่ตามลูกศรในไดอะแกรมทีละกล่อง
# ─────────────────────────────────────────────
def run_javis_brain(message: str, ticker: str, history: list, user_email: str,
                     watchlist: list, portfolio_data, tool_registry: dict) -> dict:
    # 1) Intent Understanding Engine + Planner
    intent = understand_intent(message, ticker, history)
    target_ticker = intent["target_ticker"]

    # 2) Memory
    portfolio_ctx = portfolio_data if intent["needs_portfolio"] else None
    watchlist_quotes = []
    if intent["needs_watchlist"] and watchlist:
        get_quote_fn = tool_registry.get("get_quote")
        if get_quote_fn:
            for sym in watchlist[:8]:
                try:
                    watchlist_quotes.append(get_quote_fn(sym))
                except Exception:
                    pass  # หุ้นตัวไหนดึงไม่ได้ก็ข้าม ไม่ให้ทั้งคำตอบล่ม

    # 3) Tool Router
    tool_results = run_tools(intent["tools_needed"], target_ticker, tool_registry)

    # 4) Knowledge Router
    knowledge_text = get_knowledge_snippets(message, intent["knowledge_topics"])

    # 5) Context Merger
    merged_context = merge_context(target_ticker, portfolio_ctx, watchlist, watchlist_quotes, tool_results, knowledge_text)

    # 6) Response Generation
    try:
        reply_text = generate_response(message, user_email, history, merged_context)
    except Exception as e:
        reply_text = f"⚠️ เกิดข้อผิดพลาดตอนสร้างคำตอบ: {e}"

    # 7) Response Formatter
    return {
        "reply": reply_text,
        "used_tools": intent["tools_needed"],
        "target_ticker": target_ticker,
        "data": tool_results,
        "intent": intent,
    }