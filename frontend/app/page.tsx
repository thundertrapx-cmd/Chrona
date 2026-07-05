// @ts-nocheck
'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';

// อ่านจาก env var ตอน build (ตั้งใน Vercel: NEXT_PUBLIC_API_URL=https://your-backend.onrender.com)
// ถ้าไม่ตั้งไว้ (เช่นตอนรัน local) จะ fallback ไป localhost:8000 เหมือนเดิม
const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ── Color tokens ──────────────────────────────────────────────────────────────
const UP = '#3bba86';
const DOWN = '#f06b6b';
const ACCENT = '#C47B4A';
const BG = '#0a0c10';
const SURF = '#0f1117';
const CARD = '#111318';
const BDR = '#1e2230';
const MUT = '#64748b';
const TXT = '#e2e8f0';

// ── Helpers ───────────────────────────────────────────────────────────────────
const fmt = (n, dec = 2) => (n != null ? Number(n).toFixed(dec) : '—');
const fmtUSD = (n) => n != null ? '$' + Number(n).toLocaleString('en', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—';
const fmtK = (n) => {
  if (!n) return '—';
  if (Math.abs(n) >= 1e12) return '$' + (n / 1e12).toFixed(2) + 'T';
  if (Math.abs(n) >= 1e9) return '$' + (n / 1e9).toFixed(2) + 'B';
  if (Math.abs(n) >= 1e6) return '$' + (n / 1e6).toFixed(2) + 'M';
  return '$' + n.toLocaleString();
};
const scoreColor = (s) => s >= 70 ? UP : s >= 40 ? '#ffd93d' : DOWN;
const sentColor = (s) => s === 'Bullish' ? UP : s === 'Bearish' ? DOWN : MUT;
const card = (extra = {}) => ({
  background: CARD, border: `1px solid ${BDR}`, borderRadius: 10, padding: '14px 16px', ...extra,
});

// ── Lightweight Charts wrapper ─────────────────────────────────────────────────
function ChronaChart({ chartData, period }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRefs = useRef({});

  useEffect(() => {
    let chart = null;
    const init = async () => {
      if (!containerRef.current) return;
      const lc = await import('lightweight-charts');
      if (chartRef.current) { try { chartRef.current.remove(); } catch {} chartRef.current = null; }

      chart = lc.createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height: 320,
        layout: { background: { color: CARD }, textColor: MUT },
        grid: { vertLines: { color: BDR }, horzLines: { color: BDR } },
        crosshair: { mode: 1 },
        rightPriceScale: { borderColor: BDR },
        timeScale: { borderColor: BDR, timeVisible: true, secondsVisible: false },
        handleScroll: true,
        handleScale: true,
      });
      chartRef.current = chart;

      const areaSeries = chart.addAreaSeries({
        lineColor: UP, topColor: UP + '44', bottomColor: UP + '00', lineWidth: 2,
      });
      const sma20Series = chart.addLineSeries({ color: '#ffd93d', lineWidth: 1, title: 'MA20' });
      const sma50Series = chart.addLineSeries({ color: '#a78bfa', lineWidth: 1, lineStyle: 2, title: 'MA50' });
      const bb_upper = chart.addLineSeries({ color: BDR, lineWidth: 1, lineStyle: 2 });
      const bb_lower = chart.addLineSeries({ color: BDR, lineWidth: 1, lineStyle: 2 });

      seriesRefs.current = { area: areaSeries, sma20: sma20Series, sma50: sma50Series, bb_upper, bb_lower };

      const handleResize = () => {
        if (containerRef.current && chart) chart.applyOptions({ width: containerRef.current.clientWidth });
      };
      window.addEventListener('resize', handleResize);
      return () => window.removeEventListener('resize', handleResize);
    };
    init();
    return () => { if (chartRef.current) { try { chartRef.current.remove(); } catch {} chartRef.current = null; } };
  }, []);

  useEffect(() => {
    if (!chartData || !seriesRefs.current.area) return;
    const { timestamps, close, sma20, sma50, bb_upper, bb_lower } = chartData;
    if (!timestamps?.length) return;

    const toTime = (ts) => Math.floor(new Date(ts).getTime() / 1000);

    const mkSeries = (vals) => {
      if (!vals) return [];
      const seen = new Set();
      return timestamps
        .map((ts, i) => ({ time: toTime(ts), value: vals[i] }))
        .filter(d => d.value != null && !seen.has(d.time) && seen.add(d.time))
        .sort((a, b) => a.time - b.time);
    };

    try {
      seriesRefs.current.area?.setData(mkSeries(close));
      if (sma20) seriesRefs.current.sma20?.setData(mkSeries(sma20));
      if (sma50) seriesRefs.current.sma50?.setData(mkSeries(sma50));
      if (bb_upper) seriesRefs.current.bb_upper?.setData(mkSeries(bb_upper));
      if (bb_lower) seriesRefs.current.bb_lower?.setData(mkSeries(bb_lower));
      chartRef.current?.timeScale().fitContent();
    } catch (e) { console.warn('Chart update error', e); }
  }, [chartData]);

  return <div ref={containerRef} style={{ width: '100%', minHeight: 320, borderRadius: 8, overflow: 'hidden' }} />;
}

// ── ML Backtest Chart ──────────────────────────────────────────────────────────
function BacktestChart({ mlData }) {
  const ref = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    let chart = null;
    const init = async () => {
      if (!ref.current || !mlData?.backtest?.strategy_curve?.length) return;
      const lc = await import('lightweight-charts');
      if (chartRef.current) { try { chartRef.current.remove(); } catch {} }
      chart = lc.createChart(ref.current, {
        width: ref.current.clientWidth, height: 260,
        layout: { background: { color: CARD }, textColor: MUT },
        grid: { vertLines: { color: BDR }, horzLines: { color: BDR } },
        rightPriceScale: { borderColor: BDR },
        timeScale: { borderColor: BDR },
      });
      chartRef.current = chart;

      const stratSeries = chart.addLineSeries({ color: UP, lineWidth: 2, title: 'AI Strategy' });
      const mktSeries = chart.addLineSeries({ color: '#a78bfa', lineWidth: 1, lineStyle: 2, title: 'Buy & Hold' });

      const mkData = (arr) => arr.map((v, i) => ({ time: (i + 1) * 86400 + 1700000000, value: v }));
      stratSeries.setData(mkData(mlData.backtest.strategy_curve));
      mktSeries.setData(mkData(mlData.backtest.market_curve));
      chart.timeScale().fitContent();
    };
    init();
    return () => { if (chartRef.current) { try { chartRef.current.remove(); } catch {} } };
  }, [mlData]);

  return <div ref={ref} style={{ width: '100%', minHeight: 260, borderRadius: 8, overflow: 'hidden' }} />;
}

// ── Sector Heatmap Mini ────────────────────────────────────────────────────────
function SectorHeatmap({ sectors }) {
  if (!sectors?.length) return null;
  return (
    <div style={card({ padding: 16 })}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase', color: MUT }}>SECTOR HEATMAP</div>
        <span style={{ fontSize: 11, color: MUT }}>Live</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 6 }}>
        {sectors.map((s, i) => {
          const up = (s.change_pct ?? 0) >= 0;
          return (
            <div key={i} style={{ background: up ? UP + '22' : DOWN + '22', border: `1px solid ${up ? UP : DOWN}44`, borderRadius: 8, padding: '10px 0', textAlign: 'center' }}>
              <div style={{ fontSize: 9, fontWeight: 700, color: MUT, letterSpacing: '.06em' }}>{s.sector}</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: up ? UP : DOWN, fontFamily: 'DM Mono,monospace', marginTop: 2 }}>{up ? '+' : ''}{s.change_pct?.toFixed(2)}%</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Ticker Bar ────────────────────────────────────────────────────────────────
function TickerBar({ indices }) {
  const items = indices.length > 0 ? indices : [
    { label: 'SPY', price: 524, change_pct: 1.1 }, { label: 'QQQ', price: 456, change_pct: 1.35 },
    { label: 'BTC', price: 67890, change_pct: 2.1 }, { label: 'VIX', price: 12.4, change_pct: -2.3 },
    { label: 'GOLD', price: 2393, change_pct: 0.34 }, { label: 'MSFT', price: 415, change_pct: 1.4 },
  ];
  const all = [...items, ...items, ...items, ...items];
  return (
    <div style={{ height: 32, background: SURF, borderBottom: `1px solid ${BDR}`, overflow: 'hidden', display: 'flex', alignItems: 'center', flexShrink: 0 }}>
      <div style={{ display: 'inline-flex', gap: 36, animation: 'ticker 35s linear infinite', whiteSpace: 'nowrap', padding: '0 20px' }}>
        {all.map((it, i) => (
          <span key={i} style={{ display: 'inline-flex', gap: 8, alignItems: 'center', fontSize: 11, fontFamily: 'DM Mono,monospace' }}>
            <span style={{ color: MUT }}>{it.label}</span>
            <span style={{ color: TXT, fontWeight: 500 }}>{it.price ? '$' + Number(it.price).toLocaleString('en', { maximumFractionDigits: 2 }) : '—'}</span>
            <span style={{ color: (it.change_pct ?? 0) >= 0 ? UP : DOWN, fontSize: 10 }}>
              {(it.change_pct ?? 0) >= 0 ? '+' : ''}{it.change_pct?.toFixed(2)}%
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}

// ── Main Dashboard ─────────────────────────────────────────────────────────────
export default function ChronaDashboard() {
  const [ticker, setTicker] = useState('AAPL');
  const [period, setPeriod] = useState('1d');
  const [tab, setTab] = useState('chart');
  const [watchlist, setWatchlist] = useState(['AAPL', 'NVDA', 'MSFT', 'META', 'TSLA']);
  const [wlInput, setWlInput] = useState('');
  const [showWlAdd, setShowWlAdd] = useState(false);
  const [search, setSearch] = useState('');
  const [sideOpen, setSideOpen] = useState(true);

  // Data state
  const [quote, setQuote] = useState(null);
  const [chartData, setChartData] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [news, setNews] = useState([]);
  const [sectors, setSectors] = useState([]);
  const [indices, setIndices] = useState([]);
  const [portfolio, setPortfolio] = useState(null);
  const [wlQuotes, setWlQuotes] = useState({});
  const [mlData, setMlData] = useState(null);
  const [fundamentals, setFundamentals] = useState(null);
  const [rankings, setRankings] = useState(null);
  const [loadingRankings, setLoadingRankings] = useState(false);

  // Auth state
  const [token, setToken] = useState(null);
  const [user, setUser] = useState(null);
  const [authEmail, setAuthEmail] = useState('');
  const [authPass, setAuthPass] = useState('');
  const [authErr, setAuthErr] = useState('');
  const [authTab, setAuthTab] = useState('login');

  // Chat state
  const [msgs, setMsgs] = useState([{ role: 'model', content: '👋 Hi Bear Bear!\nI\'m Chrona AI. How can I help you analyze the market today?' }]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef(null);

  // Portfolio form
  const [portForm, setPortForm] = useState({ ticker: '', qty: '', cost: '' });
  const [portMsg, setPortMsg] = useState('');

  // Position sizing calculator
  const [calcCapital, setCalcCapital] = useState(10000);
  const [calcRisk, setCalcRisk] = useState(1);
  const [calcAtrMult, setCalcAtrMult] = useState(2);

  const [loading, setLoading] = useState(false);
  const [backendOk, setBackendOk] = useState(null);

  // ── API fetch ────────────────────────────────────────────────────────────────
  const apiFetch = useCallback(async (path, opts = {}) => {
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(`${API}${path}`, { ...opts, headers: { ...headers, ...(opts.headers || {}) } });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
  }, [token]);

  // ── Check backend health ─────────────────────────────────────────────────────
  useEffect(() => {
    fetch(`${API}/health`).then(r => r.json()).then(() => setBackendOk(true)).catch(() => setBackendOk(false));
  }, []);

  // ── Load ticker data ─────────────────────────────────────────────────────────
  useEffect(() => {
    setLoading(true);
    setChartData(null); setAnalysis(null); setNews([]); setFundamentals(null); setMlData(null);
    Promise.all([
      apiFetch(`/stock/${ticker}/quote`).then(setQuote).catch(() => {}),
      apiFetch(`/stock/${ticker}/chart?period=${period}`).then(setChartData).catch(() => {}),
      apiFetch(`/stock/${ticker}/analysis`).then(setAnalysis).catch(() => {}),
      apiFetch(`/stock/${ticker}/news`).then(d => setNews(d.news || [])).catch(() => {}),
      apiFetch(`/stock/${ticker}/fundamentals`).then(setFundamentals).catch(() => {}),
    ]).finally(() => setLoading(false));
  }, [ticker, period, apiFetch]);

  // ── Market overview ──────────────────────────────────────────────────────────
  useEffect(() => {
    apiFetch('/market/overview').then(d => setIndices(d.indices || [])).catch(() => {});
    apiFetch('/market/sector-heatmap').then(d => setSectors(d.sectors || [])).catch(() => {});
  }, [apiFetch]);

  // ── Watchlist prices ─────────────────────────────────────────────────────────
  useEffect(() => {
    watchlist.forEach(sym => {
      apiFetch(`/stock/${sym}/quote`).then(q => setWlQuotes(p => ({ ...p, [sym]: q }))).catch(() => {});
    });
  }, [watchlist, apiFetch]);

  // ── Portfolio ────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!token) return;
    apiFetch('/portfolio').then(setPortfolio).catch(() => {});
  }, [token, apiFetch]);

  // ── Chat scroll ──────────────────────────────────────────────────────────────
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [msgs]);

  // ── Send chat ────────────────────────────────────────────────────────────────
  const sendChat = async () => {
    const text = chatInput.trim();
    if (!text || chatLoading) return;
    setChatInput('');
    setMsgs(p => [...p, { role: 'user', content: text }]);
    setChatLoading(true);
    try {
      const d = await apiFetch('/ai/chat', {
        method: 'POST',
        body: JSON.stringify({
          message: text,
          ticker,
          history: msgs.map(m => ({ role: m.role, content: m.content })),
          user_email: user?.email || '',
          watchlist,
        }),
      });
      setMsgs(p => [...p, { role: 'model', content: d.reply, tools: d.used_tools || [] }]);
    } catch { setMsgs(p => [...p, { role: 'model', content: '❌ Connection error. Make sure GEMINI_API_KEY is set in backend.' }]); }
    setChatLoading(false);
  };

  // ── Auth ─────────────────────────────────────────────────────────────────────
  const doLogin = async () => {
    setAuthErr('');
    try {
      const d = await apiFetch('/auth/login', { method: 'POST', body: JSON.stringify({ email: authEmail, password: authPass }) });
      setToken(d.access_token); setUser(d.user); setTab('chart');
    } catch { setAuthErr('อีเมลหรือ password ไม่ถูกต้อง'); }
  };
  const doSignup = async () => {
    setAuthErr('');
    try {
      await apiFetch('/auth/signup', { method: 'POST', body: JSON.stringify({ email: authEmail, password: authPass }) });
      setAuthErr('✅ สมัครสำเร็จ! กรุณา login');
    } catch (e) { setAuthErr(e.message); }
  };

  // ── Portfolio CRUD ───────────────────────────────────────────────────────────
  const addPosition = async () => {
    if (!portForm.ticker || !portForm.qty || !portForm.cost) { setPortMsg('กรุณากรอกข้อมูลให้ครบ'); return; }
    try {
      await apiFetch('/portfolio', { method: 'POST', body: JSON.stringify({ ticker: portForm.ticker.toUpperCase(), qty: +portForm.qty, avg_cost: +portForm.cost }) });
      setPortForm({ ticker: '', qty: '', cost: '' });
      setPortMsg('✅ บันทึกสำเร็จ');
      apiFetch('/portfolio').then(setPortfolio).catch(() => {});
    } catch (e) { setPortMsg('❌ ' + e.message); }
  };
  const delPosition = async (id) => {
    try {
      await apiFetch(`/portfolio/${id}`, { method: 'DELETE' });
      apiFetch('/portfolio').then(setPortfolio).catch(() => {});
    } catch {}
  };

  // ── ML Prediction ────────────────────────────────────────────────────────────
  const loadML = async () => {
    if (mlData) return;
    try {
      const d = await apiFetch(`/stock/${ticker}/ml-prediction`);
      setMlData(d);
    } catch (e) { setMlData({ error: e.message }); }
  };

  // ── Rankings ─────────────────────────────────────────────────────────────────
  const loadRankings = async () => {
    setLoadingRankings(true);
    try {
      const tickers = watchlist.join(',');
      const d = await apiFetch(`/market/rankings?tickers=${tickers},AMZN,GOOGL,AMD`);
      setRankings(d.rankings || []);
    } catch (e) { setRankings([]); }
    setLoadingRankings(false);
  };

  // Derived values
  const isUp = (quote?.change ?? 0) >= 0;
  const priceColor = isUp ? UP : DOWN;
  const atrVal = chartData?.atr ?? 0;
  const rsiVal = chartData?.rsi ?? 50;
  const rvolVal = chartData?.rvol ?? 1;

  // Position sizing calculation
  const posRiskAmt = calcCapital * (calcRisk / 100);
  const posStopDist = atrVal * calcAtrMult;
  const posShares = posStopDist > 0 ? posRiskAmt / posStopDist : 0;
  const posInvestment = posShares * (quote?.price ?? 0);
  const posStopPrice = (quote?.price ?? 0) - posStopDist;

  const greetingHour = new Date().getHours();
  const greeting = greetingHour < 12 ? 'Good morning' : greetingHour < 17 ? 'Good afternoon' : 'Good evening';
  const userName = user?.email?.split('@')[0] || 'Bear Bear';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: BG, color: TXT, fontFamily: "'DM Sans',system-ui,sans-serif", overflow: 'hidden' }}>
      <style>{`
        @keyframes ticker{from{transform:translateX(0)}to{transform:translateX(-50%)}}
        @keyframes fadeIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
        @keyframes spin{to{transform:rotate(360deg)}}
        @keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
        *{box-sizing:border-box;margin:0;padding:0;}
        ::-webkit-scrollbar{width:4px;height:4px;}
        ::-webkit-scrollbar-track{background:${BG};}
        ::-webkit-scrollbar-thumb{background:${BDR};border-radius:2px;}
        .nav-item:hover{background:${ACCENT}18!important;color:${ACCENT}!important;}
        .wl-item:hover{background:${SURF}!important;}
        .tab-btn:hover{color:${TXT}!important;}
        .kpi-card:hover{border-color:${ACCENT}!important;}
        input,button,select{font-family:inherit;}
        button{cursor:pointer;}
        input:focus{outline:none;border-color:${ACCENT}!important;}
        .news-card:hover{border-color:${ACCENT}44!important;}
        .ranking-row:hover{background:${SURF}!important;}
      `}</style>

      {/* ── TICKER BAR ── */}
      <TickerBar indices={indices} />

      {/* ── TOP NAV ── */}
      <header style={{ borderBottom: `1px solid ${BDR}`, padding: '0 20px', height: 52, display: 'flex', alignItems: 'center', gap: 12, background: BG, flexShrink: 0 }}>
        <button onClick={() => setSideOpen(!sideOpen)} style={{ background: 'none', border: 'none', color: MUT, fontSize: 20, padding: '4px 6px' }}>☰</button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 28, height: 28, background: ACCENT, borderRadius: 7, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white', fontWeight: 800, fontSize: 14 }}>C</div>
          <span style={{ fontWeight: 700, fontSize: 16, letterSpacing: '-0.02em' }}>Chrona</span>
        </div>

        {/* Search */}
        <div style={{ position: 'relative', flex: 1, maxWidth: 400 }}>
          <span style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: MUT, fontSize: 14, pointerEvents: 'none' }}>🔍</span>
          <input value={search} onChange={e => setSearch(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && search.trim()) { setTicker(search.trim().toUpperCase()); setSearch(''); setTab('chart'); } }}
            placeholder="Search stocks, ETFs, crypto..."
            style={{ width: '100%', background: SURF, border: `1px solid ${BDR}`, borderRadius: 8, color: TXT, padding: '7px 12px 7px 36px', fontSize: 13 }}
          />
        </div>

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
          {/* Backend status */}
          {backendOk === false && (
            <span style={{ fontSize: 10, color: DOWN, background: DOWN + '22', padding: '3px 8px', borderRadius: 4, fontWeight: 700 }}>⚠ Backend Offline</span>
          )}
          {backendOk === true && (
            <span style={{ fontSize: 10, color: UP, background: UP + '22', padding: '3px 8px', borderRadius: 4, fontWeight: 700 }}>● API Live</span>
          )}
          <button style={{ background: 'none', border: 'none', color: MUT, fontSize: 20 }}>🔔</button>
          <button style={{ background: 'none', border: 'none', color: MUT, fontSize: 20 }}>📌</button>
          {user ? (
            <div style={{ width: 32, height: 32, borderRadius: '50%', background: ACCENT, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}
              onClick={() => setTab('login')}>
              {user.email?.[0]?.toUpperCase()}
            </div>
          ) : (
            <button onClick={() => setTab('login')} style={{ background: ACCENT, border: 'none', borderRadius: 7, color: 'white', padding: '6px 14px', fontSize: 12, fontWeight: 600 }}>Sign In</button>
          )}
        </div>
      </header>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>

        {/* ── SIDEBAR ── */}
        {sideOpen && (
          <aside style={{ width: 195, background: CARD, borderRight: `1px solid ${BDR}`, display: 'flex', flexDirection: 'column', flexShrink: 0, overflowY: 'auto' }}>
            {/* Nav */}
            <nav style={{ padding: '8px' }}>
              <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: MUT, padding: '10px 4px 4px' }}>MENU</div>
              {[
                { id: 'chart', icon: '⊞', label: 'Dashboard' },
                { id: 'markets', icon: '📊', label: 'Markets' },
                { id: 'portfolio', icon: '💼', label: 'Portfolio' },
                { id: 'screener', icon: '🔍', label: 'Screener' },
                { id: 'ai', icon: '✦', label: 'Chrona AI', badge: 'NEW' },
                { id: 'news', icon: '📰', label: 'News' },
                { id: 'calendar', icon: '📅', label: 'Calendar' },
              ].map(n => (
                <div key={n.id} className="nav-item"
                  onClick={() => setTab(n.id)}
                  style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 8px', borderRadius: 7, marginBottom: 2, fontSize: 13, cursor: 'pointer', transition: 'all .12s',
                    background: tab === n.id ? ACCENT + '18' : 'transparent',
                    color: tab === n.id ? ACCENT : TXT,
                    borderLeft: tab === n.id ? `3px solid ${ACCENT}` : '3px solid transparent',
                    fontWeight: tab === n.id ? 600 : 400,
                  }}>
                  <span style={{ fontSize: 14 }}>{n.icon}</span>
                  <span style={{ flex: 1 }}>{n.label}</span>
                  {n.badge && <span style={{ fontSize: 8, fontWeight: 800, background: ACCENT, color: 'white', padding: '1px 5px', borderRadius: 4 }}>{n.badge}</span>}
                </div>
              ))}
            </nav>

            <div style={{ height: 1, background: BDR, margin: '2px 12px' }} />

            {/* Watchlist */}
            <div style={{ padding: '0 8px', flex: 1, overflowY: 'auto' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 4px 4px' }}>
                <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: MUT }}>WATCHLIST</div>
                <button onClick={() => setShowWlAdd(!showWlAdd)} style={{ background: 'none', border: 'none', color: MUT, fontSize: 18, lineHeight: 1, padding: '0 2px', cursor: 'pointer' }}>+</button>
              </div>
              {showWlAdd && (
                <div style={{ display: 'flex', gap: 4, marginBottom: 6 }}>
                  <input value={wlInput} onChange={e => setWlInput(e.target.value.toUpperCase())}
                    onKeyDown={e => { if (e.key === 'Enter' && wlInput && !watchlist.includes(wlInput)) { setWatchlist(p => [...p, wlInput]); setWlInput(''); setShowWlAdd(false); } }}
                    placeholder="AAPL"
                    style={{ flex: 1, background: SURF, border: `1px solid ${BDR}`, borderRadius: 6, color: TXT, padding: '4px 7px', fontSize: 11 }}
                  />
                  <button onClick={() => { if (wlInput && !watchlist.includes(wlInput)) { setWatchlist(p => [...p, wlInput]); setWlInput(''); setShowWlAdd(false); } }}
                    style={{ background: ACCENT, border: 'none', borderRadius: 6, color: 'white', padding: '4px 8px', fontSize: 11 }}>+</button>
                </div>
              )}
              {watchlist.map(sym => {
                const q = wlQuotes[sym];
                const up = (q?.change ?? 0) >= 0;
                return (
                  <div key={sym} className="wl-item"
                    onClick={() => { setTicker(sym); setTab('chart'); }}
                    style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '7px 8px', borderRadius: 7, marginBottom: 2,
                      background: sym === ticker ? ACCENT + '18' : 'transparent',
                      borderLeft: sym === ticker ? `2px solid ${ACCENT}` : '2px solid transparent', cursor: 'pointer', transition: 'all .1s',
                    }}>
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 700, fontFamily: 'DM Mono,monospace', color: TXT }}>{sym}</div>
                      <div style={{ fontSize: 9, color: MUT }}>{q?.name?.split(' ').slice(0, 2).join(' ') ?? sym}</div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: 11, fontFamily: 'DM Mono,monospace', fontWeight: 600, color: TXT }}>
                        {q?.price ? '$' + Number(q.price).toLocaleString('en', { maximumFractionDigits: 2 }) : '—'}
                      </div>
                      <div style={{ fontSize: 10, fontFamily: 'DM Mono,monospace', color: up ? UP : DOWN }}>
                        {q ? `${up ? '+' : ''}${q.change_pct?.toFixed(2)}%` : '—'}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Pro Banner */}
            <div style={{ margin: '8px', background: ACCENT + '18', border: `1px solid ${ACCENT}44`, borderRadius: 10, padding: '10px 12px' }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: ACCENT, letterSpacing: '.07em', textTransform: 'uppercase' }}>PRO PLAN</div>
              <div style={{ fontSize: 10, color: MUT, marginBottom: 8 }}>Unlimited AI · Real-time data</div>
              <button style={{ width: '100%', background: ACCENT, border: 'none', borderRadius: 6, color: 'white', padding: '6px 0', fontSize: 11, fontWeight: 600 }}>Manage Plan</button>
            </div>
          </aside>
        )}

        {/* ── MAIN CONTENT ── */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

            {/* ── CENTER PANEL ── */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '18px 20px' }}>

              {/* Greeting */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
                <div>
                  <div style={{ fontSize: 20, fontWeight: 700, fontFamily: 'Sora,sans-serif' }}>{greeting}, {userName} 👋</div>
                  <div style={{ fontSize: 12, color: MUT, marginTop: 3 }}>Here's what's happening with your portfolio today.</div>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button style={{ background: SURF, border: `1px solid ${BDR}`, borderRadius: 8, color: TXT, padding: '7px 14px', fontSize: 12 }}>⊙ Customize</button>
                  <button style={{ background: ACCENT, border: 'none', borderRadius: 8, color: 'white', padding: '7px 14px', fontSize: 12, fontWeight: 600 }}>+ Add Widget</button>
                </div>
              </div>

              {/* ── Summary Cards ── */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12, marginBottom: 16 }}>
                <div className="kpi-card" style={card({ transition: 'border-color .15s' })}>
                  <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: MUT, marginBottom: 6 }}>PORTFOLIO VALUE</div>
                  <div style={{ fontSize: 22, fontWeight: 700, color: TXT, fontFamily: 'DM Mono,monospace' }}>{portfolio ? fmtUSD(portfolio.total_value) : '$—'}</div>
                  {portfolio && <div style={{ fontSize: 11, color: UP, marginTop: 4, fontFamily: 'DM Mono,monospace' }}>+{fmtUSD(portfolio.total_pnl)} · +{portfolio.total_pnl_pct?.toFixed(2)}%</div>}
                  {!portfolio && <div style={{ fontSize: 11, color: MUT, marginTop: 4 }}>Sign in to view portfolio</div>}
                </div>
                <div className="kpi-card" style={card({ transition: 'border-color .15s' })}>
                  <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: MUT, marginBottom: 6 }}>TODAY'S P&L</div>
                  <div style={{ fontSize: 22, fontWeight: 700, color: portfolio ? ((portfolio.total_pnl ?? 0) >= 0 ? UP : DOWN) : TXT, fontFamily: 'DM Mono,monospace' }}>
                    {portfolio ? `${(portfolio.total_pnl ?? 0) >= 0 ? '+' : ''}${fmtUSD(portfolio.total_pnl)}` : '—'}
                  </div>
                  {portfolio && <div style={{ fontSize: 11, color: MUT, marginTop: 4, fontFamily: 'DM Mono,monospace' }}>{portfolio.total_pnl_pct?.toFixed(2)}% today</div>}
                </div>
                <div className="kpi-card" style={card({ transition: 'border-color .15s' })}>
                  <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: MUT, marginBottom: 6 }}>AI PORTFOLIO SCORE</div>
                  <div style={{ fontSize: 36, fontWeight: 800, color: scoreColor(analysis?.ai_score ?? chartData?.ai_score ?? 50), fontFamily: 'DM Mono,monospace', lineHeight: 1 }}>
                    {analysis?.ai_score ?? chartData?.ai_score ?? '—'}
                  </div>
                  <div style={{ marginTop: 6 }}>
                    <div style={{ width: '100%', height: 4, background: BDR, borderRadius: 2, overflow: 'hidden' }}>
                      <div style={{ width: `${analysis?.ai_score ?? chartData?.ai_score ?? 0}%`, height: '100%', background: scoreColor(analysis?.ai_score ?? chartData?.ai_score ?? 50), borderRadius: 2, transition: 'width .5s' }} />
                    </div>
                  </div>
                  {(analysis?.signal || chartData?.ai_signal) && (
                    <span style={{ display: 'inline-block', marginTop: 6, fontSize: 11, fontWeight: 700, color: UP, background: UP + '22', padding: '2px 8px', borderRadius: 4 }}>
                      {(analysis?.signal ?? chartData?.ai_signal)?.toUpperCase()}
                    </span>
                  )}
                </div>
              </div>

              {/* ── Stock Header ── */}
              <div style={card({ padding: '14px 18px', marginBottom: 12 })}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                      <span style={{ fontWeight: 700, fontSize: 16, fontFamily: 'Sora,sans-serif' }}>{ticker} ⭐</span>
                      <span style={{ fontSize: 12, color: MUT }}>{quote?.name ?? ticker}</span>
                      {loading && <span style={{ fontSize: 10, color: MUT, animation: 'pulse 1s infinite' }}>Loading...</span>}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
                      <span style={{ fontSize: 30, fontWeight: 800, fontFamily: 'DM Mono,monospace' }}>
                        {quote?.price ? '$' + Number(quote.price).toLocaleString('en', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}
                      </span>
                      <span style={{ fontSize: 14, fontWeight: 600, color: priceColor, fontFamily: 'DM Mono,monospace' }}>
                        {isUp ? '+' : ''}{quote?.change?.toFixed(2)} ({isUp ? '+' : ''}{quote?.change_pct?.toFixed(2)}%)
                      </span>
                    </div>
                  </div>
                  {/* Timeframe */}
                  <div style={{ display: 'flex', gap: 4 }}>
                    {[['1d', '1D'], ['1w', '1W'], ['1m', '1M'], ['3m', '3M'], ['1y', '1Y'], ['5y', '5Y']].map(([v, l]) => (
                      <button key={v} onClick={() => setPeriod(v)}
                        style={{ background: period === v ? ACCENT + '22' : SURF, border: `1px solid ${period === v ? ACCENT : BDR}`, borderRadius: 6, color: period === v ? ACCENT : MUT, padding: '4px 10px', fontSize: 11, fontWeight: period === v ? 600 : 400 }}>
                        {l}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* ── Tabs ── */}
              <div style={{ borderBottom: `1px solid ${BDR}`, display: 'flex', marginBottom: 18, overflowX: 'auto' }}>
                {[
                  { id: 'chart', label: '📊 Chart & Technicals' },
                  { id: 'analysis', label: '🤖 AI Analysis' },
                  { id: 'fundamentals', label: '🏦 Fundamentals' },
                  { id: 'ml', label: '🧠 ML Prediction' },
                  { id: 'news', label: '📰 News' },
                  { id: 'portfolio', label: '💼 Portfolio' },
                  { id: 'rankings', label: '🏆 Rankings' },
                  { id: 'login', label: user ? `👤 ${user.email?.split('@')[0]}` : '🔐 Sign In' },
                ].map(t => (
                  <button key={t.id} className="tab-btn" onClick={() => { setTab(t.id); if (t.id === 'ml') loadML(); if (t.id === 'rankings' && !rankings) loadRankings(); }}
                    style={{ background: tab === t.id ? ACCENT + '18' : 'transparent', border: 'none', borderBottom: `2px solid ${tab === t.id ? ACCENT : 'transparent'}`,
                      color: tab === t.id ? ACCENT : MUT, padding: '10px 16px', fontSize: 12, fontWeight: tab === t.id ? 600 : 400, whiteSpace: 'nowrap', transition: 'all .15s' }}>
                    {t.label}
                  </button>
                ))}
              </div>

              {/* ══ TAB: Chart & Technicals ══ */}
              {tab === 'chart' && (
                <div style={{ animation: 'fadeIn .2s ease' }}>
                  {/* KPI row */}
                  {chartData && (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 10, marginBottom: 14 }}>
                      {[
                        { label: 'RSI (14)', value: rsiVal != null ? fmt(rsiVal, 1) : '—', sub: rsiVal > 70 ? 'Overbought' : rsiVal < 30 ? 'Oversold' : 'Normal ✓', sc: rsiVal > 70 ? DOWN : UP },
                        { label: 'Rel. Volume', value: rvolVal != null ? fmt(rvolVal, 2) + '×' : '—', sub: rvolVal > 1.5 ? 'High Activity' : 'Standard', sc: rvolVal > 1.5 ? UP : MUT },
                        { label: 'ATR (14)', value: atrVal ? '$' + fmt(atrVal, 2) : '—', sub: 'Daily Range', sc: MUT },
                        { label: 'AI Score', value: chartData.ai_score != null ? `${chartData.ai_score}/100` : '—', sub: chartData.ai_signal ?? '—', sc: scoreColor(chartData.ai_score ?? 50) },
                        { label: 'MACD', value: chartData.macd != null ? fmt(chartData.macd, 3) : '—', sub: 'Signal', sc: MUT },
                      ].map(k => (
                        <div key={k.label} className="kpi-card" style={card({ transition: 'border-color .15s' })}>
                          <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase', color: MUT, marginBottom: 5 }}>{k.label}</div>
                          <div style={{ fontSize: 18, fontWeight: 700, fontFamily: 'DM Mono,monospace', color: TXT }}>{k.value}</div>
                          <div style={{ fontSize: 10, color: k.sc, marginTop: 3, fontFamily: 'DM Mono,monospace' }}>{k.sub}</div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Chart */}
                  <div style={card({ padding: 16, marginBottom: 14 })}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                      <div style={{ fontSize: 14, fontWeight: 700 }}>{ticker} — {period.toUpperCase()} Chart</div>
                      <div style={{ display: 'flex', gap: 14, fontSize: 11, fontFamily: 'DM Mono,monospace', color: MUT }}>
                        {[{ color: UP, label: 'Price' }, { color: '#ffd93d', label: 'MA(20)' }, { color: '#a78bfa', label: 'MA(50)' }, { color: BDR, label: 'BB Bands' }].map(l => (
                          <div key={l.label} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                            <div style={{ width: 16, height: 2, background: l.color, borderRadius: 1 }} />
                            <span>{l.label}</span>
                          </div>
                        ))}
                        {chartData && <span>RSI(14) {rsiVal?.toFixed(1) ?? '—'}</span>}
                        {chartData && <span>Vol {chartData.volume_sma ? (chartData.volume_sma / 1e6).toFixed(2) + 'M' : '—'}</span>}
                      </div>
                    </div>
                    {loading && <div style={{ color: MUT, textAlign: 'center', padding: 40, fontSize: 13 }}>⏳ Loading real-time data...</div>}
                    <ChronaChart chartData={chartData} period={period} />
                  </div>

                  {/* Position Sizing Calculator */}
                  <div style={card({ padding: 16, marginBottom: 14 })}>
                    <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>🧮 Position Sizing Calculator</div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12, marginBottom: 14 }}>
                      {[
                        { label: 'Total Capital ($)', val: calcCapital, set: setCalcCapital, step: 500, min: 100 },
                        { label: 'Risk per Trade (%)', val: calcRisk, set: setCalcRisk, step: 0.5, min: 0.1, max: 10 },
                        { label: 'Stop Loss (×ATR)', val: calcAtrMult, set: setCalcAtrMult, step: 0.5, min: 1, max: 5 },
                      ].map(f => (
                        <div key={f.label}>
                          <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.07em', textTransform: 'uppercase', color: MUT, marginBottom: 5 }}>{f.label}</div>
                          <input type="number" value={f.val} onChange={e => f.set(+e.target.value)} step={f.step} min={f.min} max={f.max}
                            style={{ width: '100%', background: SURF, border: `1px solid ${BDR}`, borderRadius: 7, color: TXT, padding: '8px 10px', fontSize: 13 }} />
                        </div>
                      ))}
                    </div>
                    {atrVal > 0 ? (
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10 }}>
                        {[
                          { label: 'Shares to Buy', value: posShares.toFixed(2) + ' shares' },
                          { label: 'Stop Loss Price', value: '$' + posStopPrice.toFixed(2), sub: `-$${posStopDist.toFixed(2)}` },
                          { label: 'Total Investment', value: fmtUSD(posInvestment), sub: `${(posInvestment / calcCapital * 100).toFixed(1)}% of portfolio` },
                        ].map(r => (
                          <div key={r.label} className="kpi-card" style={card({ transition: 'border-color .15s' })}>
                            <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.07em', textTransform: 'uppercase', color: MUT, marginBottom: 4 }}>{r.label}</div>
                            <div style={{ fontSize: 16, fontWeight: 700, fontFamily: 'DM Mono,monospace', color: TXT }}>{r.value}</div>
                            {r.sub && <div style={{ fontSize: 10, color: MUT, fontFamily: 'DM Mono,monospace', marginTop: 2 }}>{r.sub}</div>}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div style={{ color: MUT, fontSize: 12 }}>ATR data not available for this symbol</div>
                    )}
                  </div>

                  {/* Sector Heatmap */}
                  <SectorHeatmap sectors={sectors} />
                </div>
              )}

              {/* ══ TAB: AI Analysis ══ */}
              {tab === 'analysis' && (
                <div style={{ animation: 'fadeIn .2s ease' }}>
                  <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 14 }}>🤖 AI Analysis — {ticker}</div>
                  {analysis ? (
                    <>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 12, marginBottom: 16 }}>
                        <div style={card()}>
                          <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: MUT, marginBottom: 6 }}>AI PREDICTION · TOMORROW</div>
                          <div style={{ fontSize: 40, fontWeight: 900, color: analysis.prediction === 'UP' ? UP : DOWN, fontFamily: 'DM Mono,monospace', lineHeight: 1 }}>{analysis.prediction}</div>
                          <div style={{ fontSize: 14, color: TXT, marginTop: 6 }}>{analysis.prediction_confidence}% <span style={{ fontSize: 11, color: MUT }}>Confidence</span></div>
                          {analysis.reasons?.length > 0 && (
                            <ul style={{ listStyle: 'none', marginTop: 10, display: 'flex', flexDirection: 'column', gap: 5 }}>
                              {analysis.reasons.map((r, i) => (
                                <li key={i} style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, color: TXT }}>
                                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: ACCENT, display: 'inline-block', flexShrink: 0 }} />
                                  {r}
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                        <div style={card()}>
                          <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: MUT, marginBottom: 6 }}>AI SIGNAL</div>
                          <div style={{ fontSize: 26, fontWeight: 700, color: scoreColor(analysis.ai_score) }}>{analysis.signal}</div>
                          <div style={{ fontSize: 13, color: MUT, marginTop: 4 }}>Score: <span style={{ color: scoreColor(analysis.ai_score), fontFamily: 'DM Mono,monospace', fontWeight: 700 }}>{analysis.ai_score}/100</span></div>
                          <div style={{ marginTop: 8, width: '100%', height: 6, background: BDR, borderRadius: 3, overflow: 'hidden' }}>
                            <div style={{ width: `${analysis.ai_score}%`, height: '100%', background: scoreColor(analysis.ai_score), borderRadius: 3, transition: 'width .5s' }} />
                          </div>
                          <div style={{ fontSize: 11, color: MUT, marginTop: 4 }}>{analysis.confidence} Confidence</div>
                        </div>
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10, marginBottom: 16 }}>
                        {[
                          { label: 'SENTIMENT', value: analysis.sentiment, color: sentColor(analysis.sentiment) },
                          { label: 'MOMENTUM', value: analysis.momentum, color: analysis.momentum === 'Strong' ? UP : MUT },
                          { label: 'TREND', value: analysis.trend, color: analysis.trend === 'Uptrend' ? UP : DOWN },
                          { label: 'VOLATILITY', value: analysis.volatility, color: analysis.volatility === 'Low' ? UP : analysis.volatility === 'High' ? DOWN : MUT },
                        ].map(k => (
                          <div key={k.label} className="kpi-card" style={card({ transition: 'border-color .15s' })}>
                            <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase', color: MUT, marginBottom: 5 }}>{k.label}</div>
                            <div style={{ fontSize: 16, fontWeight: 700, color: k.color }}>{k.value}</div>
                          </div>
                        ))}
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10 }}>
                        {[
                          { label: 'RSI (14)', value: analysis.rsi != null ? fmt(analysis.rsi, 1) : '—' },
                          { label: 'SMA 20', value: analysis.sma20 != null ? '$' + fmt(analysis.sma20) : '—' },
                          { label: 'SMA 50', value: analysis.sma50 != null ? '$' + fmt(analysis.sma50) : '—' },
                          { label: 'Momentum', value: analysis.momentum_pct != null ? `${analysis.momentum_pct > 0 ? '+' : ''}${fmt(analysis.momentum_pct)}%` : '—', color: analysis.momentum_pct >= 0 ? UP : DOWN },
                          { label: 'Volatility', value: analysis.volatility_pct != null ? fmt(analysis.volatility_pct) + '%' : '—' },
                        ].map(k => (
                          <div key={k.label} className="kpi-card" style={card({ transition: 'border-color .15s' })}>
                            <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.07em', textTransform: 'uppercase', color: MUT, marginBottom: 4 }}>{k.label}</div>
                            <div style={{ fontSize: 16, fontWeight: 700, fontFamily: 'DM Mono,monospace', color: k.color ?? TXT }}>{k.value}</div>
                          </div>
                        ))}
                      </div>
                    </>
                  ) : <div style={{ color: MUT, textAlign: 'center', padding: 60, fontSize: 13 }}>
                    {loading ? '⏳ Loading AI analysis...' : '⚠️ No analysis data. Check backend connection.'}
                  </div>}
                </div>
              )}

              {/* ══ TAB: Fundamentals ══ */}
              {tab === 'fundamentals' && (
                <div style={{ animation: 'fadeIn .2s ease' }}>
                  <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 14 }}>🏦 Fundamental Analysis — {ticker}</div>
                  {fundamentals ? (
                    <>
                      <div style={{ marginBottom: 14 }}>
                        <div style={{ fontSize: 16, fontWeight: 700, color: TXT }}>{fundamentals.longName}</div>
                        <div style={{ fontSize: 12, color: MUT, marginTop: 3 }}>{fundamentals.sector} · {fundamentals.industry}</div>
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 14 }}>
                        {/* Valuation */}
                        <div style={card({ padding: '16px' })}>
                          <div style={{ fontSize: 11, fontWeight: 700, color: ACCENT, letterSpacing: '.07em', textTransform: 'uppercase', marginBottom: 12 }}>📊 Valuation</div>
                          {[
                            { label: 'P/E Ratio', value: fundamentals.trailingPE != null ? fmt(fundamentals.trailingPE) : '—' },
                            { label: 'Forward P/E', value: fundamentals.forwardPE != null ? fmt(fundamentals.forwardPE) : '—' },
                            { label: 'P/S Ratio', value: fundamentals.priceToSalesTrailing12Months != null ? fmt(fundamentals.priceToSalesTrailing12Months) : '—' },
                          ].map(r => (
                            <div key={r.label} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: `1px solid ${BDR}` }}>
                              <span style={{ fontSize: 12, color: MUT }}>{r.label}</span>
                              <span style={{ fontSize: 13, fontWeight: 600, fontFamily: 'DM Mono,monospace', color: TXT }}>{r.value}</span>
                            </div>
                          ))}
                        </div>
                        {/* Financials */}
                        <div style={card({ padding: '16px' })}>
                          <div style={{ fontSize: 11, fontWeight: 700, color: ACCENT, letterSpacing: '.07em', textTransform: 'uppercase', marginBottom: 12 }}>💰 Financials</div>
                          {[
                            { label: 'Market Cap', value: fmtK(fundamentals.marketCap) },
                            { label: 'Revenue (TTM)', value: fmtK(fundamentals.totalRevenue) },
                            { label: 'Net Income', value: fmtK(fundamentals.netIncomeToCommon) },
                          ].map(r => (
                            <div key={r.label} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: `1px solid ${BDR}` }}>
                              <span style={{ fontSize: 12, color: MUT }}>{r.label}</span>
                              <span style={{ fontSize: 13, fontWeight: 600, fontFamily: 'DM Mono,monospace', color: TXT }}>{r.value}</span>
                            </div>
                          ))}
                        </div>
                        {/* Growth */}
                        <div style={card({ padding: '16px' })}>
                          <div style={{ fontSize: 11, fontWeight: 700, color: ACCENT, letterSpacing: '.07em', textTransform: 'uppercase', marginBottom: 12 }}>📈 Growth & Returns</div>
                          {[
                            { label: 'Revenue Growth', value: fundamentals.revenueGrowth != null ? fmt(fundamentals.revenueGrowth * 100) + '%' : '—', color: fundamentals.revenueGrowth >= 0 ? UP : DOWN },
                            { label: 'ROE', value: fundamentals.returnOnEquity != null ? fmt(fundamentals.returnOnEquity * 100) + '%' : '—', color: fundamentals.returnOnEquity >= 0 ? UP : DOWN },
                            { label: 'ROA', value: fundamentals.returnOnAssets != null ? fmt(fundamentals.returnOnAssets * 100) + '%' : '—', color: fundamentals.returnOnAssets >= 0 ? UP : DOWN },
                          ].map(r => (
                            <div key={r.label} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: `1px solid ${BDR}` }}>
                              <span style={{ fontSize: 12, color: MUT }}>{r.label}</span>
                              <span style={{ fontSize: 13, fontWeight: 600, fontFamily: 'DM Mono,monospace', color: r.color ?? TXT }}>{r.value}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </>
                  ) : <div style={{ color: MUT, textAlign: 'center', padding: 60 }}>
                    {loading ? '⏳ Loading fundamentals...' : '⚠️ No fundamental data available'}
                  </div>}
                </div>
              )}

              {/* ══ TAB: ML Prediction ══ */}
              {tab === 'ml' && (
                <div style={{ animation: 'fadeIn .2s ease' }}>
                  <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 4 }}>🧠 ML Price Prediction — {ticker}</div>
                  <div style={{ fontSize: 11, color: MUT, marginBottom: 16 }}>Random Forest Classifier · Trained on RSI, MACD, Momentum, ATR, Bollinger Bands</div>
                  {!mlData && (
                    <div style={{ textAlign: 'center', padding: 40 }}>
                      <div style={{ color: MUT, marginBottom: 12 }}>Click to run ML prediction model</div>
                      <button onClick={loadML} style={{ background: ACCENT, border: 'none', borderRadius: 8, color: 'white', padding: '10px 24px', fontSize: 13, fontWeight: 600 }}>🚀 Run ML Model</button>
                    </div>
                  )}
                  {mlData?.error && (
                    <div style={{ background: DOWN + '18', border: `1px solid ${DOWN}44`, borderRadius: 10, padding: 16, color: DOWN, fontSize: 13 }}>❌ {mlData.error}</div>
                  )}
                  {mlData && !mlData.error && (
                    <>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12, marginBottom: 16 }}>
                        <div style={card()}>
                          <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: MUT, marginBottom: 6 }}>TOMORROW'S CALL</div>
                          <div style={{ fontSize: 32, fontWeight: 900, color: mlData.prediction === 'UP' ? UP : DOWN, fontFamily: 'DM Mono,monospace', lineHeight: 1 }}>{mlData.prediction}</div>
                          <div style={{ fontSize: 12, color: MUT, marginTop: 6 }}>Confidence: <span style={{ color: TXT, fontWeight: 600 }}>{mlData.confidence}%</span></div>
                        </div>
                        <div style={card()}>
                          <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: MUT, marginBottom: 6 }}>MODEL ACCURACY</div>
                          <div style={{ fontSize: 32, fontWeight: 900, color: scoreColor(mlData.accuracy), fontFamily: 'DM Mono,monospace', lineHeight: 1 }}>{mlData.accuracy}%</div>
                          <div style={{ fontSize: 12, color: MUT, marginTop: 6 }}>Historical accuracy</div>
                        </div>
                        <div style={card()}>
                          <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: MUT, marginBottom: 6 }}>MARKET BASELINE</div>
                          <div style={{ fontSize: 32, fontWeight: 900, color: MUT, fontFamily: 'DM Mono,monospace', lineHeight: 1 }}>{mlData.baseline}%</div>
                          <div style={{ fontSize: 12, color: MUT, marginTop: 6 }}>Green days ratio</div>
                        </div>
                      </div>

                      {/* Feature Importance */}
                      {mlData.feature_importance && (
                        <div style={card({ marginBottom: 16 })}>
                          <div style={{ fontSize: 12, fontWeight: 700, color: MUT, letterSpacing: '.07em', textTransform: 'uppercase', marginBottom: 12 }}>FEATURE IMPORTANCE</div>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                            {Object.entries(mlData.feature_importance).slice(0, 6).map(([feat, imp]) => (
                              <div key={feat} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                <div style={{ width: 100, fontSize: 10, color: MUT, fontFamily: 'DM Mono,monospace', textAlign: 'right' }}>{feat}</div>
                                <div style={{ flex: 1, height: 6, background: BDR, borderRadius: 3, overflow: 'hidden' }}>
                                  <div style={{ width: `${imp}%`, height: '100%', background: ACCENT, borderRadius: 3 }} />
                                </div>
                                <div style={{ width: 36, fontSize: 11, color: TXT, fontFamily: 'DM Mono,monospace' }}>{imp}%</div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Backtest chart */}
                      {mlData.backtest?.strategy_curve?.length > 0 && (
                        <div style={card({ padding: 16 })}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                            <div style={{ fontSize: 13, fontWeight: 700 }}>📉 Strategy vs Buy & Hold Backtest</div>
                            <div style={{ display: 'flex', gap: 14, fontSize: 11, fontFamily: 'DM Mono,monospace' }}>
                              <span style={{ color: UP }}>— AI Strategy: {mlData.backtest.strategy_return > 0 ? '+' : ''}{mlData.backtest.strategy_return}%</span>
                              <span style={{ color: '#a78bfa' }}>-- Market: {mlData.backtest.market_return > 0 ? '+' : ''}{mlData.backtest.market_return}%</span>
                            </div>
                          </div>
                          <BacktestChart mlData={mlData} />
                          <div style={{ marginTop: 10 }}>
                            {mlData.backtest.alpha > 0 ? (
                              <div style={{ background: UP + '18', border: `1px solid ${UP}44`, borderRadius: 8, padding: '8px 12px', fontSize: 12, color: UP }}>
                                🔥 Alpha: AI strategy outperformed market by +{mlData.backtest.alpha}%
                              </div>
                            ) : (
                              <div style={{ background: DOWN + '18', border: `1px solid ${DOWN}44`, borderRadius: 8, padding: '8px 12px', fontSize: 12, color: DOWN }}>
                                ⚠️ Underperformance: {mlData.backtest.alpha}% vs Buy & Hold
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}

              {/* ══ TAB: News ══ */}
              {tab === 'news' && (
                <div style={{ animation: 'fadeIn .2s ease' }}>
                  <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 14 }}>📰 Latest News — {ticker}</div>
                  {news.length === 0 ? (
                    <div style={{ color: MUT, textAlign: 'center', padding: 60 }}>
                      {loading ? '⏳ Loading news...' : 'No news found. Check NEWS_API_KEY in backend.'}
                    </div>
                  ) : news.map((n, i) => (
                    <a key={i} href={n.url || '#'} target="_blank" rel="noopener noreferrer" style={{ textDecoration: 'none' }}>
                      <div className="news-card" style={{ ...card({ marginBottom: 10, padding: '14px 16px', display: 'flex', gap: 12, alignItems: 'flex-start', cursor: 'pointer', transition: 'border-color .15s' }) }}>
                        <div style={{ width: 36, height: 36, borderRadius: 8, background: SURF, border: `1px solid ${BDR}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, flexShrink: 0 }}>
                          {n.sentiment === 'Bullish' ? '📈' : n.sentiment === 'Bearish' ? '📉' : '📊'}
                        </div>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: 13, fontWeight: 600, color: TXT, lineHeight: 1.4, marginBottom: 5 }}>{n.title}</div>
                          {n.description && <div style={{ fontSize: 11, color: MUT, marginBottom: 5, lineHeight: 1.4 }}>{n.description?.slice(0, 120)}…</div>}
                          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <span style={{ fontSize: 10, color: MUT }}>{n.time} · {n.source}</span>
                            <span style={{ fontSize: 9, fontWeight: 700, color: sentColor(n.sentiment), background: sentColor(n.sentiment) + '22', padding: '1px 7px', borderRadius: 4 }}>{n.sentiment}</span>
                          </div>
                        </div>
                        <span style={{ color: MUT, fontSize: 14 }}>→</span>
                      </div>
                    </a>
                  ))}
                </div>
              )}

              {/* ══ TAB: Portfolio ══ */}
              {tab === 'portfolio' && (
                <div style={{ animation: 'fadeIn .2s ease' }}>
                  <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 14 }}>💼 Portfolio Tracker</div>
                  {!token ? (
                    <div style={card({ textAlign: 'center', padding: 40 })}>
                      <div style={{ color: MUT, marginBottom: 12 }}>กรุณา Sign In เพื่อดู Portfolio</div>
                      <button onClick={() => setTab('login')} style={{ background: ACCENT, border: 'none', borderRadius: 8, color: 'white', padding: '8px 20px', fontSize: 13, fontWeight: 600 }}>Sign In →</button>
                    </div>
                  ) : (
                    <>
                      {portfolio && (
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12, marginBottom: 14 }}>
                          {[
                            { label: 'Total Value', value: fmtUSD(portfolio.total_value) },
                            { label: 'Total Cost', value: fmtUSD(portfolio.total_cost) },
                            { label: 'Total P&L', value: `${(portfolio.total_pnl ?? 0) >= 0 ? '+' : ''}${fmtUSD(portfolio.total_pnl)}`, color: (portfolio.total_pnl ?? 0) >= 0 ? UP : DOWN, sub: `${portfolio.total_pnl_pct?.toFixed(2)}%` },
                          ].map(c => (
                            <div key={c.label} className="kpi-card" style={card({ transition: 'border-color .15s' })}>
                              <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: MUT, marginBottom: 6 }}>{c.label}</div>
                              <div style={{ fontSize: 20, fontWeight: 600, fontFamily: 'DM Mono,monospace', color: c.color || TXT }}>{c.value}</div>
                              {c.sub && <div style={{ fontSize: 11, color: c.color || MUT, marginTop: 3, fontFamily: 'DM Mono,monospace' }}>{c.sub}</div>}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Add form */}
                      <div style={card({ padding: 14, marginBottom: 14 })}>
                        <div style={{ fontSize: 11, fontWeight: 600, color: MUT, letterSpacing: '.07em', textTransform: 'uppercase', marginBottom: 10 }}>ADD POSITION</div>
                        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
                          {[{ k: 'ticker', p: 'Ticker', w: '20%' }, { k: 'qty', p: 'Qty', w: '16%', t: 'number' }, { k: 'cost', p: 'Avg Cost ($)', w: '22%', t: 'number' }].map(f => (
                            <div key={f.k} style={{ width: f.w }}>
                              <div style={{ fontSize: 9, color: MUT, marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.06em', fontWeight: 600 }}>{f.p}</div>
                              <input type={f.t || 'text'} placeholder={f.p} value={portForm[f.k]}
                                onChange={e => setPortForm(p => ({ ...p, [f.k]: e.target.value }))}
                                style={{ width: '100%', background: SURF, border: `1px solid ${BDR}`, borderRadius: 7, color: TXT, padding: '7px 10px', fontSize: 12 }}
                              />
                            </div>
                          ))}
                          <button onClick={addPosition} style={{ background: ACCENT, border: 'none', borderRadius: 7, color: 'white', padding: '7px 16px', fontSize: 12, fontWeight: 600, height: 35 }}>➕ Save</button>
                        </div>
                        {portMsg && <div style={{ fontSize: 11, color: portMsg.startsWith('✅') ? UP : DOWN, marginTop: 8 }}>{portMsg}</div>}
                      </div>

                      {/* Portfolio table */}
                      {portfolio?.positions?.length > 0 ? (
                        <div style={{ background: CARD, border: `1px solid ${BDR}`, borderRadius: 12, overflow: 'hidden', marginBottom: 14 }}>
                          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                            <thead>
                              <tr style={{ borderBottom: `1px solid ${BDR}` }}>
                                {['Ticker', 'Qty', 'Avg Cost', 'Current', 'Value', 'P&L', 'P&L %', ''].map(h => (
                                  <th key={h} style={{ padding: '10px 12px', textAlign: 'left', fontSize: 9, fontWeight: 700, letterSpacing: '.07em', textTransform: 'uppercase', color: MUT }}>{h}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {portfolio.positions.map(p => (
                                <tr key={p.id} className="ranking-row" style={{ borderBottom: `1px solid ${BDR}`, transition: 'background .1s' }}>
                                  <td style={{ padding: '10px 12px', fontWeight: 700, color: TXT, fontFamily: 'DM Mono,monospace' }}>{p.ticker}</td>
                                  <td style={{ padding: '10px 12px', fontFamily: 'DM Mono,monospace', color: MUT }}>{p.qty}</td>
                                  <td style={{ padding: '10px 12px', fontFamily: 'DM Mono,monospace', color: MUT }}>${p.avg_cost?.toFixed(2)}</td>
                                  <td style={{ padding: '10px 12px', fontFamily: 'DM Mono,monospace', color: TXT }}>${p.current_price?.toFixed(2)}</td>
                                  <td style={{ padding: '10px 12px', fontFamily: 'DM Mono,monospace', color: TXT }}>${p.value?.toLocaleString('en', { maximumFractionDigits: 0 })}</td>
                                  <td style={{ padding: '10px 12px', fontFamily: 'DM Mono,monospace', color: p.pnl >= 0 ? UP : DOWN }}>{p.pnl >= 0 ? '+' : ''}${p.pnl?.toFixed(2)}</td>
                                  <td style={{ padding: '10px 12px', fontFamily: 'DM Mono,monospace', color: p.pnl_pct >= 0 ? UP : DOWN }}>{p.pnl_pct >= 0 ? '+' : ''}{p.pnl_pct?.toFixed(2)}%</td>
                                  <td style={{ padding: '10px 12px' }}>
                                    <button onClick={() => delPosition(p.id)} style={{ background: 'none', border: `1px solid ${BDR}`, borderRadius: 5, color: DOWN, padding: '2px 7px', fontSize: 11 }}>✕</button>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : <div style={{ color: MUT, textAlign: 'center', padding: 32, fontSize: 13 }}>ยังไม่มี position — เพิ่มด้านบน</div>}
                    </>
                  )}
                </div>
              )}

              {/* ══ TAB: Rankings ══ */}
              {tab === 'rankings' && (
                <div style={{ animation: 'fadeIn .2s ease' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                    <div style={{ fontSize: 15, fontWeight: 700 }}>🏆 AI Stock Rankings</div>
                    <button onClick={loadRankings} disabled={loadingRankings}
                      style={{ background: ACCENT, border: 'none', borderRadius: 8, color: 'white', padding: '8px 16px', fontSize: 12, fontWeight: 600, opacity: loadingRankings ? 0.6 : 1 }}>
                      {loadingRankings ? '⏳ Analyzing...' : '🚀 Refresh Rankings'}
                    </button>
                  </div>
                  {!rankings && !loadingRankings && (
                    <div style={{ color: MUT, textAlign: 'center', padding: 60 }}>Click Refresh Rankings to start</div>
                  )}
                  {loadingRankings && (
                    <div style={{ color: MUT, textAlign: 'center', padding: 60 }}>⏳ Analyzing all stocks... this may take a moment</div>
                  )}
                  {rankings && !loadingRankings && (
                    <>
                      {/* Score bars */}
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
                        {rankings.map((r, i) => (
                          <div key={r.stock} onClick={() => { setTicker(r.stock); setTab('chart'); }}
                            style={{ ...card({ display: 'flex', alignItems: 'center', gap: 14, cursor: 'pointer', padding: '12px 16px' }) }}>
                            <div style={{ fontSize: 16, fontWeight: 800, color: MUT, width: 24, textAlign: 'center' }}>#{i + 1}</div>
                            <div style={{ width: 60, fontWeight: 700, fontFamily: 'DM Mono,monospace', color: TXT }}>{r.stock}</div>
                            <div style={{ flex: 1 }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                <span style={{ fontSize: 10, color: MUT }}>AI Score</span>
                                <span style={{ fontSize: 11, fontFamily: 'DM Mono,monospace', color: scoreColor(r.ai_score) }}>{r.ai_score}/100</span>
                              </div>
                              <div style={{ height: 5, background: BDR, borderRadius: 3, overflow: 'hidden' }}>
                                <div style={{ width: `${r.ai_score}%`, height: '100%', background: scoreColor(r.ai_score), borderRadius: 3 }} />
                              </div>
                            </div>
                            <div style={{ textAlign: 'right', minWidth: 80 }}>
                              <div style={{ fontSize: 13, fontWeight: 600, fontFamily: 'DM Mono,monospace', color: TXT }}>${r.price}</div>
                              <div style={{ fontSize: 10, color: r.momentum_pct >= 0 ? UP : DOWN, fontFamily: 'DM Mono,monospace' }}>{r.momentum_pct >= 0 ? '+' : ''}{r.momentum_pct}%</div>
                            </div>
                            <div style={{ minWidth: 80, textAlign: 'right' }}>
                              <span style={{ fontSize: 10, fontWeight: 700, color: r.signal === 'Strong Buy' ? UP : r.signal === 'Avoid' ? DOWN : '#ffd93d', background: (r.signal === 'Strong Buy' ? UP : r.signal === 'Avoid' ? DOWN : '#ffd93d') + '22', padding: '2px 8px', borderRadius: 4 }}>{r.signal}</span>
                            </div>
                            <div style={{ minWidth: 60, textAlign: 'right' }}>
                              <span style={{ fontSize: 10, color: r.risk === 'Low' ? UP : r.risk === 'High' ? DOWN : '#ffd93d' }}>{r.risk} Risk</span>
                            </div>
                          </div>
                        ))}
                      </div>
                      {/* Heatmap grid */}
                      <div style={card({ padding: 16 })}>
                        <div style={{ fontSize: 12, fontWeight: 700, color: MUT, letterSpacing: '.07em', textTransform: 'uppercase', marginBottom: 12 }}>🗺️ Market Heatmap</div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 6 }}>
                          {rankings.map(r => (
                            <div key={r.stock} onClick={() => { setTicker(r.stock); setTab('chart'); }}
                              style={{ background: scoreColor(r.ai_score) + '22', border: `1px solid ${scoreColor(r.ai_score)}44`, borderRadius: 8, padding: '10px 6px', textAlign: 'center', cursor: 'pointer' }}>
                              <div style={{ fontSize: 11, fontWeight: 700, color: TXT, fontFamily: 'DM Mono,monospace' }}>{r.stock}</div>
                              <div style={{ fontSize: 13, fontWeight: 700, color: scoreColor(r.ai_score), fontFamily: 'DM Mono,monospace', marginTop: 2 }}>{r.ai_score}</div>
                              <div style={{ fontSize: 9, color: r.momentum_pct >= 0 ? UP : DOWN, fontFamily: 'DM Mono,monospace' }}>{r.momentum_pct >= 0 ? '+' : ''}{r.momentum_pct}%</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </>
                  )}
                </div>
              )}

              {/* ══ TAB: Screener ══ */}
              {tab === 'screener' && (
                <div style={{ animation: 'fadeIn .2s ease' }}>
                  <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 14 }}>🔍 Stock Screener</div>
                  <div style={card({ padding: 20, textAlign: 'center' })}>
                    <div style={{ fontSize: 40, marginBottom: 12 }}>🔍</div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: TXT, marginBottom: 8 }}>Screen from Watchlist</div>
                    <div style={{ fontSize: 12, color: MUT, marginBottom: 16 }}>Use Rankings tab to compare and screen stocks by AI score, momentum, and risk.</div>
                    <button onClick={() => { setTab('rankings'); if (!rankings) loadRankings(); }} style={{ background: ACCENT, border: 'none', borderRadius: 8, color: 'white', padding: '10px 24px', fontSize: 13, fontWeight: 600 }}>Go to Rankings →</button>
                  </div>
                </div>
              )}

              {/* ══ TAB: Markets ══ */}
              {tab === 'markets' && (
                <div style={{ animation: 'fadeIn .2s ease' }}>
                  <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 14 }}>📊 Market Overview</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10, marginBottom: 20 }}>
                    {indices.map((idx, i) => (
                      <div key={i} className="kpi-card" style={card({ transition: 'border-color .15s', cursor: 'pointer' })}
                        onClick={() => { if (!['NASDAQ', 'DOW', 'S&P 500', 'VIX'].includes(idx.label)) { setTicker(idx.label); setTab('chart'); } }}>
                        <div style={{ fontSize: 10, fontWeight: 700, color: MUT, letterSpacing: '.07em', textTransform: 'uppercase', marginBottom: 6 }}>{idx.label}</div>
                        <div style={{ fontSize: 18, fontWeight: 700, fontFamily: 'DM Mono,monospace', color: TXT }}>${Number(idx.price).toLocaleString('en', { maximumFractionDigits: 2 })}</div>
                        <div style={{ fontSize: 12, fontFamily: 'DM Mono,monospace', color: (idx.change_pct ?? 0) >= 0 ? UP : DOWN, marginTop: 3 }}>
                          {(idx.change_pct ?? 0) >= 0 ? '+' : ''}{idx.change_pct?.toFixed(2)}%
                        </div>
                      </div>
                    ))}
                  </div>
                  <SectorHeatmap sectors={sectors} />
                </div>
              )}

              {/* ══ TAB: AI ══ */}
              {tab === 'ai' && (
                <div style={{ animation: 'fadeIn .2s ease' }}>
                  <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 4 }}>✦ Chrona AI</div>
                  <div style={{ fontSize: 12, color: MUT, marginBottom: 16 }}>Powered by Gemini — Ask anything about stocks, markets, and your portfolio</div>
                  <div style={{ ...card({ padding: 0, overflow: 'hidden' }), display: 'flex', flexDirection: 'column', height: 500 }}>
                    <div style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                      {msgs.map((m, i) => (
                        <div key={i} style={{ alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start', maxWidth: '85%',
                          background: m.role === 'user' ? ACCENT + '22' : SURF,
                          border: `1px solid ${m.role === 'user' ? ACCENT : BDR}`,
                          borderRadius: 10, padding: '10px 13px', fontSize: 13, color: TXT, lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
                          {m.content}
                          {m.tools && m.tools.length > 0 && (
                            <div style={{ marginTop: 6, fontSize: 10, color: MUT }}>🔧 {m.tools.join(', ')}</div>
                          )}
                        </div>
                      ))}
                      {chatLoading && <div style={{ alignSelf: 'flex-start', background: SURF, border: `1px solid ${BDR}`, borderRadius: 10, padding: '8px 12px', fontSize: 12, color: MUT }}>✦ Analyzing...</div>}
                      <div ref={chatEndRef} />
                    </div>
                    <div style={{ padding: '10px 12px', borderTop: `1px solid ${BDR}`, display: 'flex', gap: 8 }}>
                      <input value={chatInput} onChange={e => setChatInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && sendChat()}
                        placeholder="Ask about stocks, e.g. 'What's the outlook for NVDA?'"
                        style={{ flex: 1, background: SURF, border: `1px solid ${BDR}`, borderRadius: 8, color: TXT, padding: '9px 13px', fontSize: 13 }} />
                      <button onClick={sendChat} style={{ background: ACCENT, border: 'none', borderRadius: 8, color: 'white', width: 38, height: 38, fontSize: 18, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>➤</button>
                    </div>
                  </div>
                </div>
              )}

              {/* ══ TAB: News (standalone) ══ */}
              {tab === 'calendar' && (
                <div style={{ animation: 'fadeIn .2s ease', textAlign: 'center', padding: 60 }}>
                  <div style={{ fontSize: 40, marginBottom: 12 }}>📅</div>
                  <div style={{ fontSize: 16, fontWeight: 600, color: TXT, marginBottom: 8 }}>Earnings Calendar</div>
                  <div style={{ fontSize: 12, color: MUT }}>Coming soon — track upcoming earnings dates and analyst estimates</div>
                </div>
              )}

              {/* ══ TAB: Auth ══ */}
              {tab === 'login' && (
                <div style={{ animation: 'fadeIn .2s ease', maxWidth: 400, margin: '0 auto' }}>
                  {user ? (
                    <div style={card({ textAlign: 'center', padding: 32 })}>
                      <div style={{ fontSize: 40, marginBottom: 12 }}>👤</div>
                      <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>{user.email}</div>
                      <div style={{ color: MUT, fontSize: 13, marginBottom: 20 }}>Logged in</div>
                      <button onClick={() => { setToken(null); setUser(null); setPortfolio(null); setTab('chart'); }}
                        style={{ background: DOWN + '22', border: `1px solid ${DOWN}44`, borderRadius: 8, color: DOWN, padding: '8px 20px', fontSize: 13, fontWeight: 600 }}>🚪 Logout</button>
                    </div>
                  ) : (
                    <div style={card({ padding: 28 })}>
                      <div style={{ textAlign: 'center', marginBottom: 24 }}>
                        <div style={{ width: 44, height: 44, background: ACCENT, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white', fontSize: 20, fontWeight: 800, margin: '0 auto 10px' }}>C</div>
                        <div style={{ fontWeight: 700, fontSize: 18, fontFamily: 'Sora,sans-serif' }}>Chrona</div>
                        <div style={{ fontSize: 12, color: MUT, marginTop: 3 }}>Stock Intelligence Platform</div>
                      </div>
                      <div style={{ display: 'flex', borderBottom: `1px solid ${BDR}`, marginBottom: 20 }}>
                        {(['login', 'signup']).map(k => (
                          <button key={k} onClick={() => setAuthTab(k)} style={{ flex: 1, background: 'none', border: 'none', borderBottom: `2px solid ${authTab === k ? ACCENT : 'transparent'}`, color: authTab === k ? ACCENT : MUT, padding: '8px 0', fontSize: 13, fontWeight: authTab === k ? 600 : 400 }}>
                            {k === 'login' ? '🔐 Log In' : '📝 Sign Up'}
                          </button>
                        ))}
                      </div>
                      {[{ p: 'Email', v: authEmail, s: setAuthEmail, t: 'email' }, { p: 'Password', v: authPass, s: setAuthPass, t: 'password' }].map(f => (
                        <div key={f.p} style={{ marginBottom: 14 }}>
                          <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '.07em', textTransform: 'uppercase', color: MUT, marginBottom: 6 }}>{f.p}</div>
                          <input type={f.t} placeholder={f.t === 'email' ? 'your@email.com' : '••••••••'} value={f.v} onChange={e => f.s(e.target.value)}
                            onKeyDown={e => e.key === 'Enter' && (authTab === 'login' ? doLogin() : doSignup())}
                            style={{ width: '100%', background: SURF, border: `1px solid ${BDR}`, borderRadius: 8, color: TXT, padding: '9px 12px', fontSize: 13 }} />
                        </div>
                      ))}
                      {authErr && <div style={{ fontSize: 12, color: authErr.startsWith('✅') ? UP : DOWN, marginBottom: 12, background: (authErr.startsWith('✅') ? UP : DOWN) + '11', borderRadius: 7, padding: '7px 12px' }}>{authErr}</div>}
                      <button onClick={authTab === 'login' ? doLogin : doSignup}
                        style={{ width: '100%', background: ACCENT, border: 'none', borderRadius: 8, color: 'white', padding: '11px 0', fontSize: 14, fontWeight: 600 }}>
                        {authTab === 'login' ? 'Sign In →' : 'Create Account →'}
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* ── RIGHT PANEL: Chrona AI ── */}
            <aside style={{ width: 300, borderLeft: `1px solid ${BDR}`, background: SURF, display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
              {/* Header */}
              <div style={{ padding: '14px 16px 10px', borderBottom: `1px solid ${BDR}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 14 }}>✦ Chrona AI</div>
                <span style={{ fontSize: 9, fontWeight: 800, background: ACCENT, color: 'white', padding: '2px 7px', borderRadius: 4 }}>NEW</span>
              </div>

              {/* AI Insight */}
              {(analysis || chartData) && (
                <div style={{ padding: '12px 14px', borderBottom: `1px solid ${BDR}`, flexShrink: 0 }}>
                  <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase', color: MUT, marginBottom: 8 }}>AI INSIGHT · {ticker}</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
                    <div style={{ fontSize: 40, fontWeight: 900, color: scoreColor(analysis?.ai_score ?? chartData?.ai_score ?? 50), fontFamily: 'DM Mono,monospace', lineHeight: 1 }}>
                      {analysis?.ai_score ?? chartData?.ai_score ?? '—'}
                    </div>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 700, color: scoreColor(analysis?.ai_score ?? chartData?.ai_score ?? 50) }}>{analysis?.signal ?? chartData?.ai_signal ?? '—'}</div>
                      <div style={{ fontSize: 10, color: MUT }}>{analysis?.confidence ?? 'Medium'} Confidence</div>
                    </div>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 5 }}>
                    {[
                      { label: 'SENTIMENT', value: analysis?.sentiment ?? '—' },
                      { label: 'MOMENTUM', value: analysis?.momentum ?? '—' },
                      { label: 'TREND', value: analysis?.trend ?? '—' },
                      { label: 'VOLATILITY', value: analysis?.volatility ?? '—' },
                    ].map(({ label, value }) => (
                      <div key={label} style={{ background: CARD, borderRadius: 7, padding: '7px 9px', border: `1px solid ${BDR}` }}>
                        <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: '.07em', textTransform: 'uppercase', color: MUT, marginBottom: 2 }}>{label}</div>
                        <div style={{ fontSize: 12, fontWeight: 600, color: TXT }}>{value}</div>
                      </div>
                    ))}
                  </div>
                  <button onClick={() => setTab('analysis')} style={{ marginTop: 10, fontSize: 11, color: ACCENT, background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}>View Full Analysis →</button>
                </div>
              )}

              {/* Top News */}
              {news.length > 0 && (
                <div style={{ padding: '10px 14px', borderBottom: `1px solid ${BDR}`, flexShrink: 0 }}>
                  <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase', color: MUT, marginBottom: 8 }}>TOP NEWS</div>
                  {news.slice(0, 4).map((n, i) => (
                    <a key={i} href={n.url || '#'} target="_blank" rel="noopener noreferrer" style={{ textDecoration: 'none' }}>
                      <div style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'flex-start', cursor: 'pointer' }}>
                        <div style={{ width: 28, height: 28, borderRadius: 6, background: CARD, border: `1px solid ${BDR}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, flexShrink: 0 }}>
                          {n.sentiment === 'Bullish' ? '📈' : n.sentiment === 'Bearish' ? '📉' : '📊'}
                        </div>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: 11, fontWeight: 600, color: TXT, lineHeight: 1.3, marginBottom: 2 }}>{n.title?.slice(0, 60)}{n.title?.length > 60 ? '…' : ''}</div>
                          <div style={{ display: 'flex', gap: 6 }}>
                            <span style={{ fontSize: 9, color: MUT }}>{n.time} · {n.source}</span>
                            <span style={{ fontSize: 8, fontWeight: 700, color: sentColor(n.sentiment), background: sentColor(n.sentiment) + '22', padding: '1px 5px', borderRadius: 3 }}>{n.sentiment}</span>
                          </div>
                        </div>
                      </div>
                    </a>
                  ))}
                </div>
              )}

              {/* Chat */}
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
                <div style={{ flex: 1, overflowY: 'auto', padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {msgs.map((m, i) => (
                    <div key={i} style={{ alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start', maxWidth: '95%',
                      background: m.role === 'user' ? ACCENT + '22' : CARD,
                      border: `1px solid ${m.role === 'user' ? ACCENT : BDR}`,
                      borderRadius: 10, padding: '8px 11px', fontSize: 12, color: TXT, lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
                      {m.content}
                      {m.tools && m.tools.length > 0 && (
                        <div style={{ marginTop: 5, fontSize: 9, color: MUT }}>🔧 {m.tools.join(', ')}</div>
                      )}
                    </div>
                  ))}
                  {chatLoading && (
                    <div style={{ alignSelf: 'flex-start', background: CARD, border: `1px solid ${BDR}`, borderRadius: 10, padding: '8px 12px', fontSize: 12, color: MUT }}>
                      ✦ Analyzing...
                    </div>
                  )}
                  <div ref={chatEndRef} />
                </div>
                <div style={{ padding: '10px 12px', borderTop: `1px solid ${BDR}`, display: 'flex', gap: 8, flexShrink: 0 }}>
                  <input value={chatInput} onChange={e => setChatInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && sendChat()}
                    placeholder="Ask anything about stocks..."
                    style={{ flex: 1, background: CARD, border: `1px solid ${BDR}`, borderRadius: 8, color: TXT, padding: '7px 11px', fontSize: 12 }} />
                  <button onClick={sendChat} style={{ background: ACCENT, border: 'none', borderRadius: 8, color: 'white', width: 34, height: 34, fontSize: 16, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>➤</button>
                </div>
              </div>
            </aside>

          </div>
        </div>
      </div>
    </div>
  );
}