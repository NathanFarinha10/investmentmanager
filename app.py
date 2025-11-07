import os
import io
import time
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# --- Optional fallback data source
try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None

# --- Try import OpenBB SDK
OPENBB_AVAILABLE = True
try:
    from openbb import obb  # Newer OpenBB SDK entry point (v4+ consolidations)
except Exception:
    try:
        # Older import style
        from openbb_terminal.sdk import openbb as obb  # type: ignore
    except Exception:
        OPENBB_AVAILABLE = False
        obb = None

st.set_page_config(
    page_title="Athena – Investment Platform",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================
# Helpers & Adapters
# =============================

def _warn_openbb():
    if not OPENBB_AVAILABLE:
        st.warning(
            "OpenBB SDK não foi importado. Alguns recursos usarão um fallback (yfinance) ou ficarão indisponíveis.\n"
            "Verifique se o pacote e as credenciais de provedores estão configurados no ambiente."
        )

@st.cache_data(show_spinner=False)
def get_price_history(ticker: str, period: str = "3y", interval: str = "1d") -> pd.DataFrame:
    """Fetch historical prices using OpenBB when available; fallback to yfinance."""
    ticker = ticker.upper().strip()
    if OPENBB_AVAILABLE:
        try:
            # Newer OpenBB price route (v4+): obb.equity.price.historical
            if hasattr(obb, "equity") and hasattr(obb.equity, "price"):
                df = obb.equity.price.historical(symbol=ticker, provider="yfinance", period=period, interval=interval)
                if isinstance(df, pd.DataFrame) and not df.empty:
                    return df.rename(columns={"close": "Close", "open": "Open", "high": "High", "low": "Low", "volume": "Volume"})
        except Exception:
            pass
        try:
            # Older OpenBB
            df = obb.stocks.load(ticker, start=None, end=None, interval=interval)
            if isinstance(df, pd.DataFrame) and not df.empty:
                return df.rename(columns=str.title)
        except Exception:
            pass
    # Fallback to yfinance
    if yf is None:
        return pd.DataFrame()
    y = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
    y = y.reset_index().rename(columns={"Date": "date"})
    return y

@st.cache_data(show_spinner=False)
def get_quote(ticker: str) -> Dict:
    ticker = ticker.upper().strip()
    if OPENBB_AVAILABLE:
        try:
            if hasattr(obb, "equity") and hasattr(obb.equity, "price"):
                q = obb.equity.price.quote(symbol=ticker, provider="yfinance")
                if isinstance(q, dict) and q:
                    return q
        except Exception:
            pass
        try:
            # Older
            q = obb.stocks.quote([ticker])
            if isinstance(q, pd.DataFrame) and not q.empty:
                return q.iloc[0].to_dict()
        except Exception:
            pass
    if yf is None:
        return {}
    info = yf.Ticker(ticker).fast_info if hasattr(yf.Ticker(ticker), "fast_info") else {}
    return dict(info)

@st.cache_data(show_spinner=False)
def screen_equities(country: str = "United States", sector: Optional[str] = None, limit: int = 50) -> pd.DataFrame:
    """Very simple screener using OpenBB; fallback returns empty."""
    if OPENBB_AVAILABLE:
        try:
            if hasattr(obb, "equity") and hasattr(obb.equity, "screener"):
                df = obb.equity.screener.run(country=country, sector=sector, limit=limit)
                if isinstance(df, pd.DataFrame):
                    return df
        except Exception:
            pass
        try:
            df = obb.stocks.screener.preset(preset="top_gainers")
            if isinstance(df, pd.DataFrame):
                return df
        except Exception:
            pass
    return pd.DataFrame()

@st.cache_data(show_spinner=False)
def get_macro_series(series_id: str, start_date: Optional[str] = None) -> pd.DataFrame:
    """Fetch macro series via OpenBB (e.g., FRED)."""
    if OPENBB_AVAILABLE:
        try:
            if hasattr(obb, "economy") and hasattr(obb.economy, "fred"):
                df = obb.economy.fred(series=series_id, start_date=start_date)
                if isinstance(df, pd.DataFrame) and not df.empty:
                    return df
        except Exception:
            pass
    return pd.DataFrame()

# =============================
# UI Components
# =============================

def kpi_card(label: str, value: str, delta: Optional[str] = None, helptext: Optional[str] = None):
    c = st.container()
    with c:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"**{label}**")
            st.markdown(f"<div style='font-size: 28px; font-weight: 700'>{value}</div>", unsafe_allow_html=True)
        with col2:
            if delta is not None:
                st.metric(label="Δ", value=delta)
        if helptext:
            st.caption(helptext)

# =============================
# Portfolio Utilities
# =============================

@dataclass
class Position:
    ticker: str
    quantity: float
    cost_basis: float  # per-share

@st.cache_data(show_spinner=False)
def portfolio_from_csv(file_bytes: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(file_bytes))
    # Expected columns: ticker, quantity, cost_basis
    df.columns = [c.strip().lower() for c in df.columns]
    assert set(["ticker", "quantity", "cost_basis"]).issubset(set(df.columns)), "CSV deve conter as colunas: ticker, quantity, cost_basis"
    df["ticker"] = df["ticker"].str.upper().str.strip()
    return df[["ticker", "quantity", "cost_basis"]]

@st.cache_data(show_spinner=False)
def build_portfolio_valuation(positions: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for t, qty, cb in positions.itertuples(index=False):
        hist = get_price_history(t, period="2y", interval="1d")
        if hist is None or hist.empty:
            continue
        if "date" not in hist.columns:
            hist = hist.reset_index().rename(columns={hist.index.name or "index": "date"})
        price = float(hist.iloc[-1]["Close"]) if "Close" in hist.columns else float(hist.iloc[-1]["close"])
        mktval = qty * price
        pnl = (price - cb) * qty
        rows.append({"ticker": t, "quantity": qty, "last_price": price, "market_value": mktval, "cost_basis": cb, "unrealized_pnl": pnl})
    summary = pd.DataFrame(rows)
    if summary.empty:
        return summary, pd.DataFrame()
    # Timeseries of portfolio equity curve (value-weighted)
    all_hist = []
    for t, qty, _ in positions.itertuples(index=False):
        h = get_price_history(t, period="2y", interval="1d")
        if h is None or h.empty:
            continue
        series = h[["date", "Close"]].copy()
        series["mv"] = series["Close"] * qty
        series["ticker"] = t
        all_hist.append(series)
    eq = pd.concat(all_hist, ignore_index=True)
    eq = eq.groupby("date")["mv"].sum().to_frame("portfolio_value").reset_index()
    eq["returns"] = eq["portfolio_value"].pct_change().fillna(0.0)
    return summary, eq

# =============================
# Pages
# =============================

PAGES = [
    "📊 Dashboard",
    "💼 Portfólio",
    "🔎 Screener",
    "🧮 Risco & Fatores",
    "🧪 Backtest",
    "🌐 Macro",
]

with st.sidebar:
    st.title("Athena")
    st.caption("OpenBB + Streamlit")
    page = st.radio("Navegação", PAGES, index=0)
    st.divider()
    default_ticker = st.text_input("Ticker (ex: AAPL, MSFT)", value="AAPL")
    benchmark = st.text_input("Benchmark (ex: ^GSPC, IVV)", value="^GSPC")
    _warn_openbb()

# ---------- Dashboard ----------
if page == "📊 Dashboard":
    st.subheader("Visão Geral")
    tabs = st.tabs(["Resumo", "Preço", "Técnicos"])  # type: ignore

    with tabs[0]:
        q = get_quote(default_ticker)
        last = q.get("lastPrice") or q.get("regularMarketPrice") or q.get("price")
        chg = q.get("change") or q.get("regularMarketChange")
        chg_pct = q.get("changePercent") or q.get("regularMarketChangePercent")
        k1, k2, k3 = st.columns(3)
        with k1: kpi_card("Preço", f"{last:.2f}" if last else "—", delta=(f"{chg:+.2f}" if chg else None))
        with k2: kpi_card("Var %", f"{(chg_pct*100 if chg_pct and abs(chg_pct) < 5 else chg_pct):+.2f}%" if chg_pct else "—")
        with k3: kpi_card("Fonte", "OpenBB / yfinance", helptext="Quote provider")

    with tabs[1]:
        hist = get_price_history(default_ticker, period="3y", interval="1d")
        if hist is not None and not hist.empty:
            fig = px.area(hist, x="date", y="Close", title=f"{default_ticker} – Histórico")
            fig.update_traces(hovertemplate="%{x}<br>Close: %{y:.2f}")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem dados de preço.")

    with tabs[2]:
        hist = get_price_history(default_ticker, period="1y", interval="1d")
        if hist is not None and not hist.empty:
            df = hist.copy()
            df["SMA20"] = df["Close"].rolling(20).mean()
            df["SMA50"] = df["Close"].rolling(50).mean()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df["date"], y=df["Close"], name="Close"))
            fig.add_trace(go.Scatter(x=df["date"], y=df["SMA20"], name="SMA20"))
            fig.add_trace(go.Scatter(x=df["date"], y=df["SMA50"], name="SMA50"))
            fig.update_layout(title="Médias móveis", legend=dict(orientation="h"))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem dados técnicos.")

# ---------- Portfolio ----------
if page == "💼 Portfólio":
    st.subheader("Análise de Portfólio")
    up = st.file_uploader("Envie CSV com colunas: ticker, quantity, cost_basis", type=["csv"])
    if up is not None:
        try:
            pf = portfolio_from_csv(up.read())
            st.dataframe(pf, use_container_width=True)
            summary, curve = build_portfolio_valuation(pf)
            if summary.empty:
                st.info("Não foi possível avaliar o portfólio.")
            else:
                c1, c2 = st.columns([2, 1])
                with c1:
                    fig = px.bar(summary.sort_values("market_value", ascending=False), x="ticker", y="market_value", title="Alocação por Ativo")
                    st.plotly_chart(fig, use_container_width=True)
                with c2:
                    kpi_card("Valor", f"${summary['market_value'].sum():,.0f}")
                    kpi_card("PnL", f"${summary['unrealized_pnl'].sum():+,.0f}")
                st.divider()
                if not curve.empty:
                    fig = px.line(curve, x="date", y="portfolio_value", title="Equity Curve")
                    st.plotly_chart(fig, use_container_width=True)
                    st.caption("Retornos diários e métricas")
                    ret = curve["returns"]
                    ann_ret = (1 + ret.mean()) ** 252 - 1
                    ann_vol = ret.std() * np.sqrt(252)
                    sharpe = (ann_ret - 0.03) / ann_vol if ann_vol > 0 else np.nan
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Retorno Anualizado", f"{ann_ret*100:.2f}%")
                    m2.metric("Vol Anualizada", f"{ann_vol*100:.2f}%")
                    m3.metric("Sharpe (rf=3%)", f"{sharpe:.2f}")
        except Exception as e:
            st.error(f"Erro ao processar CSV: {e}")
    else:
        st.info("Envie o arquivo para começar.")

# ---------- Screener ----------
if page == "🔎 Screener":
    st.subheader("Equity Screener")
    country = st.selectbox("País", ["United States", "Brazil", "Canada", "United Kingdom"], index=0)
    sector = st.text_input("Setor (opcional)") or None
    limit = st.slider("Qtde", 10, 200, 50, step=10)
    df = screen_equities(country=country, sector=sector, limit=limit)
    if df is not None and not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum resultado do screener ou OpenBB indisponível.")

# ---------- Risk & Factors ----------
if page == "🧮 Risco & Fatores":
    st.subheader("Beta vs Benchmark e VaR")
    hist = get_price_history(default_ticker, period="3y", interval="1d")
    bench = get_price_history(benchmark, period="3y", interval="1d")
    if hist is None or hist.empty or bench is None or bench.empty:
        st.info("Sem dados suficientes.")
    else:
        df = pd.merge(hist[["date", "Close"]], bench[["date", "Close"]], on="date", suffixes=("_asset", "_bench"))
        df["r_a"] = df["Close_asset"].pct_change()
        df["r_b"] = df["Close_bench"].pct_change()
        df = df.dropna()
        # OLS beta
        x = df[["r_b"]].values
        y = df["r_a"].values
        beta = float(np.cov(y, x.T)[0, 1] / np.var(x)) if np.var(x) > 0 else np.nan
        alpha = float(y.mean() - beta * x.mean())
        st.metric("Beta", f"{beta:.2f}")
        st.metric("Alpha (diário)", f"{alpha:.5f}")
        # VaR (histórico) 95%
        var_95 = np.percentile(df["r_a"], 5)
        st.metric("VaR 95% (1d)", f"{var_95:.2%}")
        fig = px.scatter(df, x="r_b", y="r_a", trendline="ols", title=f"{default_ticker} vs {benchmark}")
        st.plotly_chart(fig, use_container_width=True)

# ---------- Backtest ----------
if page == "🧪 Backtest":
    st.subheader("Momentum Simples (SMA Crossover)")
    sma_fast = st.slider("SMA Rápida", 5, 50, 20)
    sma_slow = st.slider("SMA Lenta", 20, 200, 50)
    hist = get_price_history(default_ticker, period="5y", interval="1d")
    if hist is None or hist.empty:
        st.info("Sem dados")
    else:
        df = hist.copy()
        df["SMAf"] = df["Close"].rolling(sma_fast).mean()
        df["SMAs"] = df["Close"].rolling(sma_slow).mean()
        df["signal"] = (df["SMAf"] > df["SMAs"]).astype(int)
        df["ret"] = df["Close"].pct_change().fillna(0)
        df["strat"] = df["signal"].shift(1).fillna(0) * df["ret"]
        eq = (1 + df[["ret", "strat"]]).cumprod()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["date"], y=eq["ret"], name="Buy & Hold"))
        fig.add_trace(go.Scatter(x=df["date"], y=eq["strat"], name="SMA Strategy"))
        fig.update_layout(title="Backtest – Crossover")
        st.plotly_chart(fig, use_container_width=True)
        # Metrics
        def ann_metrics(series: pd.Series) -> Tuple[float, float, float]:
            r = series.pct_change().fillna(0)
            ann_ret = (1 + r.mean()) ** 252 - 1
            ann_vol = r.std() * np.sqrt(252)
            sharpe = (ann_ret - 0.03) / ann_vol if ann_vol > 0 else np.nan
            return ann_ret, ann_vol, sharpe
        ar_bh, av_bh, sh_bh = ann_metrics(eq["ret"])  # type: ignore
        ar_st, av_st, sh_st = ann_metrics(eq["strat"])  # type: ignore
        c1, c2, c3 = st.columns(3)
        c1.metric("Ret Anual (BH)", f"{ar_bh*100:.2f}%")
        c2.metric("Ret Anual (Strat)", f"{ar_st*100:.2f}%")
        c3.metric("Sharpe (Strat)", f"{sh_st:.2f}")

# ---------- Macro ----------
if page == "🌐 Macro":
    st.subheader("Séries Macro – FRED (OpenBB)")
    sid = st.text_input("ID da Série (ex: DGS10, GDP)", value="DGS10")
    start = st.text_input("Data inicial (YYYY-MM-DD)", value="2010-01-01")
    if st.button("Carregar Série"):
        df = get_macro_series(sid, start)
        if df is not None and not df.empty:
            # Try to standardize columns
            if "date" not in df.columns:
                df = df.reset_index().rename(columns={df.index.name or "index": "date"})
            value_col = [c for c in df.columns if c.lower() not in ("date", "index")][0]
            fig = px.line(df, x="date", y=value_col, title=f"{sid} – Série Macro")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df.tail(12), use_container_width=True)
        else:
            st.info("Sem dados ou OpenBB indisponível.")

st.caption("© Athena – Demo educacional. Não constitui recomendação de investimento.")
