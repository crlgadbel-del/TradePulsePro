import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf
from datetime import datetime, timedelta
import time
import requests
import os

# Import local modules
from config import *
from market_data import get_stock_data, get_stock_info, get_market_status, search_symbol
from technical_analysis import compute_all_indicators, analyze_indicators, get_indicator_summary
from sentiment_analysis import get_news_for_symbol, analyze_sentiment
from signal_generator import generate_signal, scan_market

# Set page configuration
st.set_page_config(
    page_title="Intraday Trading Signal AI",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for premium look
st.markdown("""
<style>
    .main {
        background-color: #0e1117;
    }
    .stApp {
        color: #fafafa;
    }
    .stMetric {
        background-color: #1e2130;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .signal-buy {
        color: #00ff00;
        font-weight: bold;
        font-size: 24px;
        background-color: rgba(0, 255, 0, 0.1);
        padding: 10px;
        border-radius: 5px;
        border-left: 5px solid #00ff00;
    }
    .signal-sell {
        color: #ff4b4b;
        font-weight: bold;
        font-size: 24px;
        background-color: rgba(255, 75, 75, 0.1);
        padding: 10px;
        border-radius: 5px;
        border-left: 5px solid #ff4b4b;
    }
    .signal-hold {
        color: #ffa500;
        font-weight: bold;
        font-size: 24px;
        background-color: rgba(255, 165, 0, 0.1);
        padding: 10px;
        border-radius: 5px;
        border-left: 5px solid #ffa500;
    }
    .prediction-card {
        background: linear-gradient(135deg, #2b32b2 0%, #1488cc 100%);
        padding: 20px;
        border-radius: 15px;
        color: white;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# Currency Helper
def get_currency_symbol(symbol, market_type):
    if market_type == "Indian Stocks" or symbol.endswith(".NS"):
        return "₹"
    return "$"

# Helper function for AI Analysis
def get_ai_analysis(symbol, strategy='intraday', risk='medium'):
    # Try to get from st.secrets first (for Streamlit Cloud), then config.py
    api_key = st.secrets.get("GROQ_API_KEY", GROQ_API_KEY)
    news_key = st.secrets.get("NEWS_API_KEY", NEWS_API_KEY)
    
    if not api_key:
        return "GROQ_API_KEY is missing. Please set it in Streamlit Secrets or your .env file."
    
    clean_sym = symbol.replace('.NS', '').replace('-USD', '')
    
    # Fetch News
    news_headlines = []
    if news_key:
        try:
            url = f"https://newsapi.org/v2/everything?q={clean_sym}&sortBy=publishedAt&pageSize=5&apiKey={news_key}"
            res = requests.get(url, timeout=5)
            data = res.json()
            if data.get('articles'):
                news_headlines = [f"- {a['title']} ({a['source']['name']})" for a in data['articles']]
        except Exception:
            pass
            
    news_text = "\n".join(news_headlines) if news_headlines else "No recent specific news found."
    
    # Get Signal Context
    sig_data = {}
    try:
        df = get_stock_data(symbol, period='5d', interval='15m')
        if df is not None and not df.empty:
             sig_data = generate_signal(df, symbol)
    except Exception:
        pass

    prompt = f"""
    Act as an elite Wall Street financial analyst specializing in {strategy} trading with a {risk} risk profile. 
    Analyze {symbol} for an immediate trade.
    
    RECENT NEWS CONTEXT:
    {news_text}
    
    TECHNICAL INDICATOR DATA:
    - Trend Signal: {sig_data.get('signal', 'HOLD')}
    - Quantitative Confidence: {round(sig_data.get('confidence', 0)*100, 1)}%
    - Last Price: {sig_data.get('current_price', 'Unknown')}
    - Technical Summary: {sig_data.get('indicator_summary', 'Neutral')}
    
    Provide an INTELLIGENT PREDICTION:
    1. **Short-term Price Target**: Where do you see it heading in the next 1-4 hours?
    2. **Sentiment Analysis**: How is the news impacting the psychology?
    3. **Actionable Trade Idea**: Specific entry, exit, and stop-loss logic.
    4. **Probability Score**: Your expert gut feeling (0-100%).
    
    Format with bold headers and clear bullet points. Keep it professional but punchy.
    """
    
    try:
        groq_url = "https://api.groq.com/openai/v1/chat/completions"
        headers = { "Authorization": f"Bearer {api_key}", "Content-Type": "application/json" }
        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5,
            "max_tokens": 600
        }
        resp = requests.post(groq_url, json=payload, headers=headers, timeout=12)
        if resp.status_code == 200:
            return resp.json()['choices'][0]['message']['content']
        else:
            return f"AI analysis failed: {resp.text}"
    except Exception as e:
        return f"Error connecting to AI engine: {e}"

# Sidebar
st.sidebar.title("🚀 Trade AI Pro")
market_type = st.sidebar.selectbox("Select Market", ["Indian Stocks", "US Stocks", "Crypto"])

available_symbols = []
if market_type == "Indian Stocks":
    available_symbols = INDIAN_STOCKS
elif market_type == "US Stocks":
    available_symbols = US_STOCKS
else:
    available_symbols = CRYPTO_PAIRS

selected_symbol = st.sidebar.selectbox("Select Symbol", available_symbols)
time_interval = st.sidebar.selectbox("Interval", ["1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "1wk"], index=2)
period = st.sidebar.selectbox("Period", ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"], index=1)
risk_profile = st.sidebar.selectbox("Risk Profile", list(RISK_LEVELS.keys()), index=1)

currency = get_currency_symbol(selected_symbol, market_type)

st.sidebar.divider()
if st.sidebar.button("Refresh Data"):
    st.rerun()

# --- Main Layout ---
col1, col2, col3, col4 = st.columns(4)

# Load data
with st.spinner(f"Analyzing {selected_symbol}..."):
    df = get_stock_data(selected_symbol, period=period, interval=time_interval)
    stock_info_data = get_stock_info(selected_symbol)

if df is not None and not df.empty:
    # Top Bar Metrics
    last_row = df.iloc[-1]
    prev_close = df.iloc[-2]['Close'] if len(df) > 1 else last_row['Open']
    change = last_row['Close'] - prev_close
    change_pct = (change / prev_close) * 100
    
    col1.metric("Current Price", f"{currency} {last_row['Close']:.2f}", f"{change_pct:.2f}%")
    col2.metric("Day High", f"{currency} {df['High'].max():.2f}")
    col3.metric("Day Low", f"{currency} {df['Low'].min():.2f}")
    col4.metric("Volume", f"{int(last_row['Volume']):,}")

    # Main Tabs
    tab_chart, tab_analysis, tab_prediction = st.tabs(["📈 Technical Chart", "🔍 Tech Analysis", "🔮 AI Prediction"])

    with tab_chart:
        # Compute indicators for charting
        df_indicators = compute_all_indicators(df)
        
        # Create Plotly Chart
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                           vertical_spacing=0.03, row_heights=[0.7, 0.3])

        # Candlestick
        fig.add_trace(go.Candlestick(
            x=df_indicators.index,
            open=df_indicators['Open'],
            high=df_indicators['High'],
            low=df_indicators['Low'],
            close=df_indicators['Close'],
            name="Price"
        ), row=1, col=1)

        # EMAs
        fig.add_trace(go.Scatter(x=df_indicators.index, y=df_indicators['EMA_9'], name='EMA 9', line=dict(color='cyan', width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_indicators.index, y=df_indicators['EMA_21'], name='EMA 21', line=dict(color='magenta', width=1.5)), row=1, col=1)
        
        # Bollinger Bands - FIXED KEY 'BB_Upper'
        fig.add_trace(go.Scatter(x=df_indicators.index, y=df_indicators['BB_Upper'], name='BB Upper', line=dict(color='rgba(255, 255, 255, 0.2)', width=1), fill=None), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_indicators.index, y=df_indicators['BB_Lower'], name='BB Lower', line=dict(color='rgba(255, 255, 255, 0.2)', width=1), fill='tonexty'), row=1, col=1)

        # Volume
        v_colors = ['#ef4444' if row['Open'] > row['Close'] else '#10b981' for i, row in df_indicators.iterrows()]
        fig.add_trace(go.Bar(x=df_indicators.index, y=df_indicators['Volume'], name='Volume', marker_color=v_colors), row=2, col=1)

        fig.update_layout(
            template='plotly_dark',
            xaxis_rangeslider_visible=False,
            height=700,
            showlegend=True,
            margin=dict(l=10, r=10, t=10, b=10)
        )
        st.plotly_chart(fig, use_container_width=True)

    with tab_analysis:
        news_key = st.secrets.get("NEWS_API_KEY", NEWS_API_KEY)
        signal_data = generate_signal(df, selected_symbol, risk_profile, news_key)
        
        c1, c2 = st.columns([1, 2])
        
        with c1:
            st.subheader("Signal Summary")
            sig = signal_data['signal']
            sig_class = f"signal-{sig.lower()}"
            st.markdown(f'<div class="{sig_class}">{sig} Signal</div>', unsafe_allow_html=True)
            
            st.write(f"**Confidence Score:** {signal_data['confidence']*100:.1f}%")
            st.write(f"**Optimal Entry:** {currency} {signal_data['entry_price']:.2f}")
            st.write(f"**Target 1 (Take Profit):** {currency} {signal_data['target_1']:.2f}")
            st.write(f"**Target 2 (Aggressive):** {currency} {signal_data['target_2']:.2f}")
            st.write(f"**Hard Stop Loss:** {currency} {signal_data['stop_loss']:.2f}")
            st.write(f"**Risk/Reward Ratio:** {signal_data['risk_reward']:.2f}")

        with c2:
            st.subheader("Indicator Matrix")
            df_ind = compute_all_indicators(df)
            indicator_summary = get_indicator_summary(df_ind)
            
            cols = st.columns(3)
            with cols[0]:
                st.metric("RSI (14)", f"{indicator_summary['rsi']:.1f}" if indicator_summary['rsi'] else "N/A")
                st.caption("Overbought > 70, Oversold < 30")
            with cols[1]:
                st.metric("MACD", f"{indicator_summary['macd']:.4f}" if indicator_summary['macd'] else "N/A")
                st.caption("Positive = Bullish Cross")
            with cols[2]:
                st.metric("ADX", f"{indicator_summary['adx']:.1f}" if indicator_summary['adx'] else "N/A")
                st.caption("> 25 indicates strong trend")
            
            st.divider()
            st.write("**Price Action Observations**")
            p_cols = st.columns(2)
            with p_cols[0]:
                if indicator_summary['price'] > indicator_summary['vwap'] if indicator_summary['vwap'] else False:
                    st.success("✅ Above VWAP (Strong)")
                else:
                    st.warning("⚠️ Below VWAP (Weak)")
            with p_cols[1]:
                if indicator_summary['volume_ratio'] and indicator_summary['volume_ratio'] > 1.2:
                    st.success(f"🚀 High Volume ({indicator_summary['volume_ratio']:.1f}x)")
                else:
                    st.info("📉 Normal Volume")

    with tab_prediction:
        st.markdown("""
        <div class="prediction-card">
            <h3>🔮 Smart AI Prediction Engine</h3>
            <p>Combining Technical Indicators, Real-time News, and LLM Analysis for High-Probability Predictions.</p>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("🌟 Generate Intelligent Prediction"):
            with st.spinner("Synthesizing market data and news sentiment..."):
                report = get_ai_analysis(selected_symbol, risk=risk_profile)
                st.markdown(report)
                
                # Simple logic-based prediction for quick reference
                st.divider()
                st.subheader("Algorithmic Verdict")
                if signal_data['confidence'] > 0.7 and signal_data['signal'] == 'BUY':
                    st.success("STORM ALERT: High momentum detected. Possible breakout imminent.")
                elif signal_data['confidence'] > 0.7 and signal_data['signal'] == 'SELL':
                    st.error("DANGER: Heavy distribution detected. Possible dump imminent.")
                else:
                    st.info("Market is currently in range. Wait for clearer volume confirmation.")
        else:
            st.info("Click the button to activate the AI Prediction model for this asset.")

    # News Section
    st.divider()
    st.subheader(f"🌐 Live Feed: {selected_symbol}")
    news_key = st.secrets.get("NEWS_API_KEY", NEWS_API_KEY)
    news_articles = get_news_for_symbol(selected_symbol, news_key)
    if news_articles:
        for article in news_articles[:5]:
            with st.expander(f"{article['title']}"):
                st.write(f"**Source:** {article['source']['name']} | **Published:** {article['publishedAt'][:10]}")
                st.write(article['description'])
                st.write(f"[Source Link]({article['url']})")
    else:
        st.write("No specific news impact found for this period.")

else:
    st.error(f"Failed to fetch data for {selected_symbol}. This could be due to invalid ticker or API limits.")

# Market Scanner
with st.sidebar.expander("🔍 Global Scanner"):
    scan_m = st.selectbox("Market", ["Indian", "US", "Crypto"], key="s_m")
    if st.button("Run Quick Scan"):
        syms = []
        if scan_m == "Indian": syms = INDIAN_STOCKS[:10]
        elif scan_m == "US": syms = US_STOCKS[:10]
        else: syms = CRYPTO_PAIRS[:10]
        
        with st.spinner("Scanning..."):
            res = scan_market(syms, risk_profile, st.secrets.get("NEWS_API_KEY", NEWS_API_KEY))
            if res:
                st.dataframe(pd.DataFrame(res)[['symbol', 'signal', 'confidence', 'current_price']])
            else:
                st.write("No immediate signals.")

st.sidebar.markdown("---")
st.sidebar.caption("© 2026 Intraday AI Pro | Premium Signal Engine")
