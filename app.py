"""
Flask API Server for Intraday Trading Signal Platform
"""
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import pandas as pd
import numpy as np
import yfinance as yf
import os
import requests
import logging
import warnings
import time as time_mod
from config import *
from datetime import datetime, timedelta

warnings.filterwarnings("ignore", category=FutureWarning)
from market_data import (
    get_stock_data, get_stock_info, get_market_status, search_symbol, get_news_for_stock
)
from technical_analysis import compute_all_indicators, analyze_indicators, get_indicator_summary
from sentiment_analysis import get_news_for_symbol, analyze_sentiment
from signal_generator import generate_signal, scan_market

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/api/health')
def health():
    return jsonify({'status': 'ok'})


@app.route('/api/market-status')
def market_status():
    return jsonify(get_market_status())


@app.route('/api/symbols')
def get_symbols():
    market = request.args.get('market', 'all')
    result = {}
    if market in ['all', 'indian']:
        result['indian'] = [{'symbol': s, 'name': s.replace('.NS', '')} for s in INDIAN_STOCKS]
    if market in ['all', 'us']:
        result['us'] = [{'symbol': s, 'name': s} for s in US_STOCKS]
    if market in ['all', 'crypto']:
        result['crypto'] = [{'symbol': s, 'name': s.replace('-USD', '')} for s in CRYPTO_PAIRS]
    return jsonify(result)


@app.route('/api/search')
def search():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
    results = search_symbol(query)
    return jsonify(results)


@app.route('/api/stock-info/<symbol>')
def stock_info(symbol):
    info = get_stock_info(symbol)
    return jsonify(info)


# ============ REAL-TIME PRICE ENDPOINT ============
@app.route('/api/realtime/<symbol>')
def realtime_price(symbol):
    """Get real-time price for a symbol - fast lightweight endpoint"""
    try:
        ticker = yf.Ticker(symbol)
        
        # Get last 1d, 1m data for the most recent price
        price = 0
        prev_close = 0
        day_high = 0
        day_low = 0
        volume = 0
        
        try:
            info = ticker.info
            if info:
                price = info.get('currentPrice', info.get('regularMarketPrice', 0))
                prev_close = info.get('previousClose', info.get('regularMarketPreviousClose', 0))
                day_high = info.get('dayHigh', info.get('regularMarketDayHigh', 0))
                day_low = info.get('dayLow', info.get('regularMarketDayLow', 0))
                volume = info.get('volume', info.get('regularMarketVolume', 0))
        except Exception:
            pass
            
        if not price or price == 0:
            # Fallback: get last 5 days of 5m data if 1d 1m is missing (after hours/weekends)
            hist = ticker.history(period='5d', interval='5m')
            if hist is not None and not hist.empty:
                last = hist.iloc[-1]
                price = float(last['Close'])
                day_high = float(hist['High'].max())
                day_low = float(hist['Low'].min())
                volume = int(hist['Volume'].sum())
                
                # Use actual previous close
                if len(hist) > 1:
                    prev_close = float(hist.iloc[0]['Open']) 
        
        change = price - prev_close if prev_close else 0
        change_pct = (change / prev_close * 100) if prev_close else 0
        
        return jsonify({
            'symbol': symbol,
            'price': round(float(price), 4) if price else 0,
            'change': round(float(change), 4),
            'change_pct': round(float(change_pct), 2),
            'high': round(float(day_high), 4) if day_high else 0,
            'low': round(float(day_low), 4) if day_low else 0,
            'volume': int(volume) if volume else 0,
            'prev_close': round(float(prev_close), 4) if prev_close else 0,
            'timestamp': int(time_mod.time()),
        })
    except Exception as e:
        logger.error(f"Realtime error for {symbol}: {e}")
        return jsonify({'symbol': symbol, 'price': 0, 'error': str(e)})


@app.route('/api/stock-data/<symbol>')
def stock_data(symbol):
    period = request.args.get('period', '5d')
    interval = request.args.get('interval', '5m')
    markers_req = request.args.get('markers', 'false').lower() == 'true'

    df = get_stock_data(symbol, period, interval)
    if df is None or df.empty:
        return jsonify({'error': 'No data available'}), 404
        
    markers = []
    if markers_req:
        try:
            from technical_analysis import compute_all_indicators, analyze_indicators
            import pandas as pd
            df_analyzed = compute_all_indicators(df)
            if df_analyzed is not None and not df_analyzed.empty:
                analysis = analyze_indicators(df_analyzed)
                overall_signal = analysis.get('overall', 'HOLD')
                last_idx = df_analyzed.index[-1]
                
                if overall_signal == 'BUY':
                    markers.append({
                        'time': int(last_idx.timestamp()),
                        'position': 'belowBar',
                        'color': '#10b981',
                        'shape': 'arrowUp',
                        'text': 'BUY'
                    })
                elif overall_signal == 'SELL':
                    markers.append({
                        'time': int(last_idx.timestamp()),
                        'position': 'aboveBar',
                        'color': '#ef4444',
                        'shape': 'arrowDown',
                        'text': 'SELL'
                    })
        except Exception as e:
            logger.error(f"Failed to generate markers: {e}")

    has_indicators = markers_req and df_analyzed is not None and not df_analyzed.empty

    data = []
    for idx, row in df.iterrows():
        point = {
            'time': int(idx.timestamp()),
            'open': round(float(row['Open']), 4),
            'high': round(float(row['High']), 4),
            'low': round(float(row['Low']), 4),
            'close': round(float(row['Close']), 4),
            'volume': int(row['Volume']),
        }
        
        if has_indicators and idx in df_analyzed.index:
            arow = df_analyzed.loc[idx]
            if pd.notna(arow.get('RSI')): point['rsi'] = round(float(arow['RSI']), 2)
            if pd.notna(arow.get('MACD')): point['macd'] = round(float(arow['MACD']), 4)
            if pd.notna(arow.get('MACD_Signal')): point['macd_signal'] = round(float(arow['MACD_Signal']), 4)
            if pd.notna(arow.get('MACD_Histogram')): point['macd_hist'] = round(float(arow['MACD_Histogram']), 4)
            
        data.append(point)
    res = {'symbol': symbol, 'data': data}
    if markers_req:
        res['markers'] = markers
    return jsonify(res)


@app.route('/api/indicators/<symbol>')
def indicators(symbol):
    period = request.args.get('period', '5d')
    interval = request.args.get('interval', '5m')
    df = get_stock_data(symbol, period, interval)
    if df is None:
        return jsonify({'error': 'No data available'}), 404
    df_analyzed = compute_all_indicators(df)
    if df_analyzed is None:
        return jsonify({'error': 'Failed to compute indicators'}), 500
    analysis = analyze_indicators(df_analyzed)
    summary = get_indicator_summary(df_analyzed)
    return jsonify({'symbol': symbol, 'analysis': analysis, 'summary': summary})


@app.route('/api/sentiment/<symbol>')
def sentiment(symbol):
    articles = get_news_for_symbol(symbol, NEWS_API_KEY)
    analysis = analyze_sentiment(articles)
    return jsonify({'symbol': symbol, 'sentiment': analysis})


@app.route('/api/holidays')
def holidays():
    """Get market holidays for 2026"""
    status = get_market_status()
    return jsonify({
        'holidays': status.get('holidays', []),
        'is_holiday_today': status['indian'].get('is_holiday', False),
        'holiday_name': status['indian'].get('holiday_name', ''),
    })


@app.route('/api/news/<symbol>')
def news(symbol):
    """Get news articles for a stock"""
    articles = get_news_for_stock(symbol, NEWS_API_KEY)
    return jsonify({'symbol': symbol, 'articles': articles})


@app.route('/api/signal/<symbol>')
def get_signal(symbol):
    risk_level = request.args.get('risk', 'medium')
    interval = request.args.get('interval', '5m')
    period = request.args.get('period', '5d')
    if risk_level not in RISK_LEVELS:
        return jsonify({'error': 'Invalid risk level. Use: safe, medium, aggressive'}), 400
    df = get_stock_data(symbol, period=period, interval=interval)
    if df is None:
        return jsonify({'error': 'No data available'}), 404
    signal = generate_signal(df, symbol, risk_level, NEWS_API_KEY)
    return jsonify(signal)


@app.route('/api/scan')
def scan():
    market = request.args.get('market', 'indian')
    risk_level = request.args.get('risk', 'medium')
    limit = int(request.args.get('limit', 20))
    
    if market == 'indian':
        symbols = INDIAN_STOCKS
    elif market == 'us':
        symbols = US_STOCKS
    elif market == 'crypto':
        symbols = CRYPTO_PAIRS
    elif market == 'all':
        symbols = INDIAN_STOCKS[:15] + US_STOCKS[:10] + CRYPTO_PAIRS[:10]
    else:
        symbols = INDIAN_STOCKS[:10]
    
    results = scan_market(symbols, risk_level, NEWS_API_KEY)
    return jsonify({
        'market': market,
        'risk_level': risk_level,
        'total_scanned': len(symbols),
        'signals': results[:limit],
    })


@app.route('/api/risk-levels')
def risk_levels():
    return jsonify(RISK_LEVELS)


@app.route('/api/chart-data/<symbol>')
def chart_data(symbol):
    """Get clean chart data with integrated signal markers"""
    period = request.args.get('period', '5d')
    interval = request.args.get('interval', '5m')
    
    # Smarter default periods
    if interval in ['1d', '1wk']: period = '1y' if period == '5d' else period
    if interval in ['1m', '2m']: period = '1d' if period == '5d' else period

    df = get_stock_data(symbol, period, interval)
    if df is None or df.empty:
        return jsonify({'error': 'No data available'}), 404
    
    df_analyzed = compute_all_indicators(df)
    sig_summary = generate_signal(df_analyzed, symbol)
    entry_price = sig_summary.get('entry_price', 0)
    current_signal = sig_summary.get('signal', 'HOLD')
    
    candles, volumes, rsi_data, macd_data = [], [], [], []
    support_levels, resistance_levels = [], []
    advanced_patterns = []
    rsi_data = []
    macd_data = []
    
    support_levels = []
    resistance_levels = []
    advanced_patterns = []
    
    prev_ts = 0
    for i, (idx, row) in enumerate(df_analyzed.iterrows()):
        ts = int(idx.timestamp())
        if ts <= prev_ts:
            ts = prev_ts + 1
        prev_ts = ts
        
        candles.append({
            'time': ts,
            'open': round(float(row['Open']), 4),
            'high': round(float(row['High']), 4),
            'low': round(float(row['Low']), 4),
            'close': round(float(row['Close']), 4),
        })
        
        volumes.append({
            'time': ts,
            'value': int(row['Volume']),
            'color': 'rgba(38, 166, 154, 0.5)' if row['Close'] >= row['Open'] else 'rgba(239, 83, 80, 0.5)'
        })
        
        if not pd.isna(row.get('RSI', float('nan'))):
            rsi_data.append({'time': ts, 'value': round(float(row['RSI']), 2)})
        if not pd.isna(row.get('MACD', float('nan'))):
            macd_data.append({
                'time': ts,
                'macd': round(float(row['MACD']), 4),
                'signal': round(float(row.get('MACD_Signal', 0)), 4) if not pd.isna(row.get('MACD_Signal', float('nan'))) else 0,
                'histogram': round(float(row.get('MACD_Histogram', 0)), 4) if not pd.isna(row.get('MACD_Histogram', float('nan'))) else 0,
            })
            
        if not pd.isna(row.get('Support_Level', float('nan'))):
            support_levels.append({'time': ts, 'value': round(float(row['Support_Level']), 4)})
        if not pd.isna(row.get('Resistance_Level', float('nan'))):
            resistance_levels.append({'time': ts, 'value': round(float(row['Resistance_Level']), 4)})
            
        if row.get('Pattern_Hammer', False):
            advanced_patterns.append({'time': ts, 'type': 'Hammer', 'position': 'belowBar', 'color': '#10b981', 'shape': 'arrowUp'})
        if row.get('Pattern_3BlackCrows', False):
            advanced_patterns.append({'time': ts, 'type': '3 Crows', 'position': 'aboveBar', 'color': '#ef4444', 'shape': 'arrowDown'})
        if row.get('Pattern_Triangle_Breakout_Up', False):
            advanced_patterns.append({'time': ts, 'type': 'Tri Brk Up', 'position': 'belowBar', 'color': '#3b82f6', 'shape': 'arrowUp'})
        if row.get('Pattern_Triangle_Breakout_Down', False):
            advanced_patterns.append({'time': ts, 'type': 'Tri Brk Dn', 'position': 'aboveBar', 'color': '#ef4444', 'shape': 'arrowDown'})
        if row.get('Pattern_H_and_S', False):
            advanced_patterns.append({'time': ts, 'type': 'H&S', 'position': 'aboveBar', 'color': '#f59e0b', 'shape': 'circle'})
            
    # Add Signal Markers (Last few candles)
    if current_signal == 'BUY':
        advanced_patterns.append({
            'time': int(df_analyzed.index[-1].timestamp()),
            'text': f'BUY @ {round(entry_price, 2)}',
            'position': 'belowBar',
            'color': '#10b981',
            'shape': 'arrowUp',
            'size': 2
        })
    elif current_signal == 'SELL':
        advanced_patterns.append({
            'time': int(df_analyzed.index[-1].timestamp()),
            'text': f'SELL @ {round(entry_price, 2)}',
            'position': 'aboveBar',
            'color': '#ef4444',
            'shape': 'arrowDown',
            'size': 2
        })
    
    return jsonify({
        'symbol': symbol,
        'interval': interval,
        'candles': candles,
        'volumes': volumes,
        'rsi': rsi_data,
        'macd': macd_data,
        'support': support_levels,
        'resistance': resistance_levels,
        'patterns': advanced_patterns,
        'summary': sig_summary
    })



@app.route('/api/ai-analysis/<symbol>')
def ai_analysis(symbol):
    """AI Sentiment & News Analysis using Groq and NewsAPI"""
    strategy = request.args.get('strategy', 'intraday').upper()
    risk = request.args.get('risk', 'medium').upper()
    
    if not GROQ_API_KEY:
        return jsonify({'error': 'AI engine not configured (GROQ_API_KEY missing)'}), 500
    
    clean_sym = symbol.replace('.NS', '').replace('-USD', '')
    
    # 1. Fetch News
    news_headlines = []
    if NEWS_API_KEY:
        try:
            url = f"https://newsapi.org/v2/everything?q={clean_sym}&sortBy=publishedAt&pageSize=5&apiKey={NEWS_API_KEY}"
            res = requests.get(url, timeout=5)
            data = res.json()
            if data.get('articles'):
                news_headlines = [f"- {a['title']} ({a['source']['name']})" for a in data['articles']]
        except Exception as e:
            logger.error(f"News error for {symbol}: {e}")
            
    news_text = "\n".join(news_headlines) if news_headlines else "No recent specific news found."
    
    # 2. Tech Signal Context
    sig_data = {}
    from signal_generator import generate_signal
    try:
        df = get_stock_data(symbol, period='5d', interval='15m')
        if df is not None and not df.empty:
             sig = generate_signal(df, symbol)
             sig_data = sig
    except Exception as e:
        logger.error(f"Signal context error: {e}")
        pass

    # 3. Call Groq
    prompt = f"""
    Act as a professional financial analyst for {strategy} trading with {risk} risk profile. 
    Analyze {symbol} based on:
    
    RECENT NEWS:
    {news_text}
    
    TECHNICAL SUMMARY (Intraday):
    Trend Signal: {sig_data.get('signal', 'HOLD')}
    Market Confidence: {round(sig_data.get('confidence', 0)*100, 1)}%
    Price: {sig_data.get('current_price', 'Unknown')}
    Indicators: {sig_data.get('indicator_summary', 'Neutral')}
    
    Provide a professional summary with:
    - SENTIMENT VERDICT (Bullish/Bearish/Neutral)
    - RISK LEVEL assessment
    - STRATEGIC RECOMMENDATION
    Keep it concise and punchy. Use Markdown for formatting.
    """
    
    try:
        groq_url = "https://api.groq.com/openai/v1/chat/completions"
        headers = { "Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json" }
        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5,
            "max_tokens": 400
        }
        resp = requests.post(groq_url, json=payload, headers=headers, timeout=12)
        
        if resp.status_code != 200:
            try:
                err_data = resp.json()
                err_msg = err_data.get('error', {}).get('message', f"HTTP {resp.status_code}")
                return jsonify({'error': f"Brain says: {err_msg}"}), resp.status_code
            except:
                return jsonify({'error': f"Central Brain returned HTTP {resp.status_code}"}), 500

        ai_resp = resp.json()
        if 'choices' in ai_resp and len(ai_resp['choices']) > 0:
            analysis = ai_resp['choices'][0]['message']['content']
            return jsonify({
                'symbol': symbol,
                'ai_report': analysis,
                'news_analyzed': len(news_headlines)
            })
        else:
            return jsonify({'error': "Brain is thinking but couldn't find words (Empty Response)"}), 500

    except Exception as e:
        logger.error(f"Groq API connection error: {e}")
        return jsonify({'error': f"Brain Connection Timeout: {str(e)}"}), 500

# ============ EXPERT ANALYSIS (Integrated from Stock-Market_Search) ============

# Import both modules from the Stock-Market_Search backend
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'Stock-Market_Search', 'backend'))
from expert_engine import run_expert_analysis
from analyzer import get_market_data as get_watchlist_data, analyze_market as analyze_watchlist

WATCHLIST = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "SBIN.NS",
    "ADANIENT.NS", "TATAMOTORS.NS", "BAJFINANCE.NS", "AXISBANK.NS",
    "ICICIBANK.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS",
    "WIPRO.NS", "ASIANPAINT.NS", "BHARTIARTL.NS", "ITC.NS"
]


@app.route('/api/expert-analysis/<symbol>')
def expert_analysis(symbol):
    """Run full expert-based analysis with profit/loss projections."""
    investment = float(request.args.get('investment', 10000))
    if not symbol.endswith(".NS") and not symbol.endswith(".BO") and not symbol.endswith("-USD"):
        ticker = f"{symbol}.NS"
    else:
        ticker = symbol
    result = run_expert_analysis(ticker, investment)
    return jsonify(result)


@app.route('/api/watchlist-status')
def watchlist_status():
    """Get market data and analysis for the watchlist (intraday opportunities)."""
    data = get_watchlist_data(WATCHLIST)
    if data is None:
        return jsonify({"error": "Failed to fetch data"})
    analysis = analyze_watchlist(data, WATCHLIST)
    opportunities = [x for x in analysis if x['signal'] in ['STRONG BUY', 'BUY', 'SELL']]
    return jsonify({
        "market_data": analysis,
        "top_picks": opportunities[:5]
    })


if __name__ == '__main__':
    print("=" * 60)
    print("  📊 TradePulse AI — Unified Trading Platform")
    print("  🌐 Open: http://localhost:5000")
    print("=" * 60)
    app.run(host=HOST, port=PORT, debug=DEBUG)
