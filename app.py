"""
Flask API Server for Intraday Trading Signal Platform
"""
from flask import Flask, jsonify, redirect, request, send_from_directory
from flask_cors import CORS
import pandas as pd
import numpy as np
import yfinance as yf
import os
import requests
import logging
import warnings
import time as time_mod
import re
from config import *
from datetime import datetime, timedelta

warnings.filterwarnings("ignore", category=FutureWarning)
from market_data import (
    get_stock_data, get_stock_info, get_market_status, search_symbol,
    get_news_for_stock, get_display_name, resolve_stock_symbol
)
from technical_analysis import compute_all_indicators, analyze_indicators, get_indicator_summary
from sentiment_analysis import get_news_for_symbol, analyze_sentiment
from signal_generator import generate_signal, scan_market

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)
STOCK_SEARCH_STATIC_DIR = os.path.join(os.path.dirname(__file__), 'Stock-Market_Search', 'static')


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/stock-search')
def stock_search_redirect():
    return redirect('/#stock-research')


@app.route('/stock-search/')
def stock_search_index():
    return redirect('/#stock-research')


@app.route('/stock-search/<path:filename>')
def stock_search_static(filename):
    return send_from_directory(STOCK_SEARCH_STATIC_DIR, filename)


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
        result['indian'] = [{'symbol': s, 'name': get_display_name(s)} for s in INDIAN_STOCKS]
    return jsonify(result)


@app.route('/api/search')
def search():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
    results = search_symbol(query)
    return jsonify(results)


def _tradingview_to_yfinance_symbol(item):
    symbol = re.sub(r'<[^>]+>', '', item.get('symbol') or item.get('ticker') or '').upper().strip()
    exchange = (item.get('exchange') or '').upper().strip()
    if not symbol:
        return ''
    clean = symbol.split(':')[-1].replace('!', '')
    if exchange == 'NSE':
        return f'{clean}.NS'
    if exchange == 'BSE':
        return f'{clean}.BO'
    if exchange in {'BINANCE', 'COINBASE', 'KRAKEN'} and clean.endswith('USD'):
        return clean.replace('USD', '-USD')
    return clean


@app.route('/api/tradingview-search')
def tradingview_search():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])

    results = []
    try:
        resp = requests.get(
            'https://symbol-search.tradingview.com/symbol_search/',
            params={
                'text': query,
                'hl': 1,
                'exchange': '',
                'lang': 'en',
                'type': '',
                'domain': 'production',
            },
            headers={
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
                'Referer': 'https://www.tradingview.com/',
                'Origin': 'https://www.tradingview.com',
                'Accept': 'application/json,text/plain,*/*',
            },
            timeout=5,
        )
        resp.raise_for_status()
        for item in resp.json()[:20]:
            yf_symbol = _tradingview_to_yfinance_symbol(item)
            if not yf_symbol:
                continue
            exchange = item.get('exchange') or ''
            description = re.sub(r'<[^>]+>', '', item.get('description') or item.get('symbol') or yf_symbol)
            results.append({
                'symbol': yf_symbol,
                'name': description,
                'exchange': exchange,
                'type': f'TradingView {exchange}'.strip(),
                'tv_symbol': re.sub(r'<[^>]+>', '', item.get('symbol') or ''),
                'source': 'TradingView',
            })
    except Exception as exc:
        logger.warning(f"TradingView search failed for {query}: {exc}")

    if not results:
        results = search_symbol(query)

    seen = set()
    unique = []
    for item in results:
        symbol = item.get('symbol')
        if symbol and symbol not in seen:
            unique.append(item)
            seen.add(symbol)
    return jsonify(unique[:12])


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
    # Chart BUY/SELL markers are now sourced from /api/signal so the chart,
    # dashboard, and expert panel agree. Keep technical markers opt-in only for
    # older debugging flows that explicitly request markers=technical.
    markers_req = request.args.get('markers', 'false').lower() == 'technical'
    indicators_req = request.args.get('indicators', 'true').lower() != 'false'

    df = get_stock_data(symbol, period, interval)
    if df is None or df.empty:
        return jsonify({'error': 'No data available'}), 404
        
    markers = []
    df_analyzed = None
    if markers_req or indicators_req:
        try:
            from technical_analysis import compute_all_indicators, analyze_indicators
            import pandas as pd
            df_analyzed = compute_all_indicators(df)
            if markers_req and df_analyzed is not None and not df_analyzed.empty:
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

    has_indicators = indicators_req and df_analyzed is not None and not df_analyzed.empty

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

    ticker = resolve_stock_symbol(symbol)
    expert_interval = interval if interval in {'1m', '3m', '5m', '15m', '30m', '1h', '1d', '10d'} else '5m'
    try:
        expert_result = _run_expert_analysis(ticker, 10000, preferred_interval=expert_interval)
        if not expert_result.get('error'):
            return jsonify(_expert_result_to_signal_payload(ticker, expert_result, risk_level))
    except Exception as e:
        logger.error(f"Expert signal fallback for {symbol}: {e}")

    df = get_stock_data(ticker, period=period, interval=interval)
    if df is None:
        return jsonify({'error': 'No data available'}), 404
    signal = generate_signal(df, ticker, risk_level, NEWS_API_KEY)
    signal.setdefault('expert_interval', expert_interval)
    signal.setdefault('timestamp', int(time_mod.time()))
    return jsonify(signal)


@app.route('/api/scan')
def scan():
    market = request.args.get('market', 'indian')
    risk_level = request.args.get('risk', 'medium')
    limit = int(request.args.get('limit', 20))
    
    symbols = INDIAN_STOCKS

    data = get_watchlist_data(symbols)
    if data is None:
        return jsonify({'error': 'Failed to fetch scan data', 'signals': []}), 500

    results = [_fast_stock_to_dashboard_signal(stock) for stock in analyze_watchlist(data, symbols)]

    results.sort(
        key=lambda x: (abs(x.get('expert_net_score', 0)), x.get('confidence', 0)),
        reverse=True
    )
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
    if interval == '10d': period = '10d'
    if interval in ['1d', '1wk']: period = '1y' if period == '5d' else period
    if interval in ['1m', '2m', '3m']: period = '1d' if period == '5d' else period

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
        if row.get('Pattern_Trendline_Breakout_Up', False):
            advanced_patterns.append({'time': ts, 'type': 'Trend Brk Up', 'position': 'belowBar', 'color': '#00b386', 'shape': 'arrowUp'})
        if row.get('Pattern_Trendline_Breakout_Down', False):
            advanced_patterns.append({'time': ts, 'type': 'Trend Brk Dn', 'position': 'aboveBar', 'color': '#ef4444', 'shape': 'arrowDown'})
        if row.get('Pattern_Fib_Bounce_Buy', False):
            advanced_patterns.append({'time': ts, 'type': 'Fib Bounce', 'position': 'belowBar', 'color': '#00b386', 'shape': 'circle'})
        if row.get('Pattern_Fib_Rejection_Sell', False):
            advanced_patterns.append({'time': ts, 'type': 'Fib Reject', 'position': 'aboveBar', 'color': '#f59e0b', 'shape': 'circle'})
        if row.get('Pattern_Double_Bottom', False):
            advanced_patterns.append({'time': ts, 'type': 'Double Bottom', 'position': 'belowBar', 'color': '#00b386', 'shape': 'arrowUp'})
        if row.get('Pattern_Double_Top', False):
            advanced_patterns.append({'time': ts, 'type': 'Double Top', 'position': 'aboveBar', 'color': '#ef4444', 'shape': 'arrowDown'})
            
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
from analyzer import (
    get_market_data as get_watchlist_data,
    analyze_market as analyze_watchlist,
    get_stock_history_for_chart,
    get_prediction_trajectory,
)
from ai_layer import get_keys_status as get_tradeai_keys_status, set_api_key as set_tradeai_api_key

WATCHLIST = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "SBIN.NS",
    "ADANIENT.NS", "TATAMOTORS.NS", "BAJFINANCE.NS", "AXISBANK.NS",
    "ICICIBANK.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS",
    "WIPRO.NS", "ASIANPAINT.NS", "BHARTIARTL.NS", "ITC.NS"
]


def _run_expert_analysis(*args, **kwargs):
    try:
        import inspect
        from expert_engine import run_expert_analysis
    except ModuleNotFoundError as exc:
        raise RuntimeError(f"Missing Python dependency: {exc.name}. Run pip install -r requirements.txt") from exc
    params = inspect.signature(run_expert_analysis).parameters
    compatible_kwargs = {key: value for key, value in kwargs.items() if key in params}
    if len(compatible_kwargs) != len(kwargs):
        skipped = sorted(set(kwargs) - set(compatible_kwargs))
        logger.info(f"Expert engine does not support options {skipped}; using default engine settings")
    return run_expert_analysis(*args, **compatible_kwargs)


def _tradeai_candidate_tickers(symbol):
    sym = (symbol or '').upper().strip().replace(' ', '')
    if not sym:
        return []
    if sym.endswith(('.NS', '.BO')) or sym.startswith('^') or sym.endswith('-USD'):
        return [sym]
    base = sym.replace('.NS', '').replace('.BO', '')
    return [f"{base}.NS", f"{base}.BO", base]


def _tradeai_search_stock(symbol):
    attempted = []

    for ticker in _tradeai_candidate_tickers(symbol):
        attempted.append(ticker)
        try:
            quote = yf.Ticker(ticker)
            exchange = "BSE" if ticker.endswith(".BO") else "NSE"
            currency = "INR" if ticker.endswith((".NS", ".BO")) else "USD"
            price = None

            try:
                fast_info = quote.fast_info
                price = (
                    fast_info.get("lastPrice")
                    or fast_info.get("regularMarketPrice")
                    or fast_info.get("previousClose")
                    or fast_info.get("regularMarketPreviousClose")
                )
                exchange = fast_info.get("exchange") or exchange
                currency = fast_info.get("currency") or currency
            except Exception:
                pass

            if not price:
                history = quote.history(period="5d")
                if history is not None and not history.empty and "Close" in history:
                    close = history["Close"].dropna()
                    if not close.empty:
                        price = close.iloc[-1]

            if price and float(price) > 0:
                return {
                    "valid": True,
                    "ticker": ticker,
                    "name": get_display_name(ticker),
                    "price": round(float(price), 2),
                    "sector": "",
                    "industry": "",
                    "exchange": exchange,
                    "currency": currency,
                }
        except Exception as exc:
            logger.error(f"Search lookup failed for {ticker}: {exc}")

    tried = ", ".join(attempted) if attempted else "no tickers"
    return {"valid": False, "error": f"'{symbol}' not found. Tried: {tried}."}


def _fast_stock_to_dashboard_signal(stock):
    symbol = stock.get('symbol', '')
    price = float(stock.get('price') or 0)
    score = float(stock.get('score') or 0)
    trades = stock.get('trades') or {}
    trade = trades.get('5m') or trades.get('3m') or trades.get('1m') or {}
    entry = float(trade.get('entry') or price or 0)
    target = float(trade.get('target') or price or 0)
    stop_loss = float(trade.get('stop_loss') or price or 0)
    expected_profit_pct = abs((target - entry) / entry * 100) if entry and target else 0
    max_loss_pct = abs((entry - stop_loss) / entry * 100) if entry and stop_loss else 0
    risk_reward = round(expected_profit_pct / max_loss_pct, 2) if max_loss_pct else 0

    return {
        **stock,
        'symbol': symbol,
        'name': get_display_name(symbol),
        'price': round(price, 2),
        'change_pct': stock.get('change', 0),
        'confidence': min(abs(score) / 100, 0.95),
        'entry_price': round(entry, 2) if entry else price,
        'target_price': round(target, 2) if target else price,
        'stop_loss': round(stop_loss, 2) if stop_loss else price,
        'expected_profit_pct': round(expected_profit_pct, 2),
        'risk_reward_ratio': risk_reward,
        'expert_net_score': score,
    }


def _verdict_direction(verdict):
    value = (verdict or 'HOLD').upper()
    if 'BUY' in value:
        return 'BUY'
    if 'SELL' in value:
        return 'SELL'
    return 'HOLD'


def _verdict_to_prediction(verdict):
    direction = _verdict_direction(verdict)
    if direction == 'BUY':
        return 'UP'
    if direction == 'SELL':
        return 'DOWN'
    return 'NEUTRAL'


def _timeframe_trade(tf):
    direction = _verdict_direction(tf.get('verdict'))
    action = 'BUY' if direction == 'BUY' else ('SELL' if direction == 'SELL' else 'WAIT')
    return {
        'action': action,
        'entry': round(float(tf.get('entry') or tf.get('current_price') or 0), 2),
        'target': round(float(tf.get('target') or tf.get('current_price') or 0), 2),
        'stop_loss': round(float(tf.get('stop_loss') or 0), 2),
    }


def _expert_reason(verdict):
    rules = verdict.get('rules_fired') or []
    directional = [
        rule.get('rule', '')
        for rule in rules
        if rule.get('type') in {'BUY', 'SELL'} and rule.get('rule')
    ]
    return ', '.join(directional[:2]) if directional else 'Expert rule consensus'


def _expert_result_to_dashboard_signal(symbol, result):
    verdict = result.get('expert_verdict', {}) or {}
    profit_loss = result.get('profit_loss', {}) or {}
    scenarios = profit_loss.get('scenarios') or []
    first_target = scenarios[0] if scenarios else {}
    price = float(result.get('current_price') or 0)
    change_pct = float(result.get('day_change') or 0)
    prev_price = price / (1 + change_pct / 100) if price and change_pct != -100 else price
    change = price - prev_price if price else 0
    timeframes = result.get('timeframes') or []
    predictions = {tf.get('interval'): _verdict_to_prediction(tf.get('verdict')) for tf in timeframes}
    trades = {tf.get('interval'): _timeframe_trade(tf) for tf in timeframes}

    return {
        'symbol': symbol,
        'name': get_display_name(symbol),
        'price': round(price, 2),
        'change': round(change, 2),
        'change_pct': round(change_pct, 2),
        'signal': verdict.get('verdict', 'HOLD'),
        'confidence': round(float(verdict.get('confidence') or 0) / 100, 3),
        'entry_price': profit_loss.get('entry', price),
        'target_price': first_target.get('target', price),
        'stop_loss': profit_loss.get('stop_loss', price),
        'expected_profit_pct': first_target.get('profit_pct', 0),
        'risk_reward_ratio': profit_loss.get('risk_reward', 0),
        'expert_net_score': verdict.get('net_score', 0),
        'expert_interval': result.get('primary_interval', '5m'),
        'score': round(float(verdict.get('net_score') or 0), 1),
        'reason': _expert_reason(verdict),
        'time_predictions': predictions,
        'trades': trades,
    }


def _expert_result_to_signal_payload(symbol, result, risk_level='medium'):
    verdict = result.get('expert_verdict', {}) or {}
    profit_loss = result.get('profit_loss', {}) or {}
    scenarios = profit_loss.get('scenarios') or []
    first_target = scenarios[0] if scenarios else {}
    direction = _verdict_direction(verdict.get('verdict'))
    confidence = round(float(verdict.get('confidence') or 0) / 100, 3)

    return {
        'symbol': symbol,
        'name': get_display_name(symbol),
        'timestamp': result.get('last_updated'),
        'current_price': result.get('current_price', 0),
        'price': result.get('current_price', 0),
        'day_change': result.get('day_change', 0),
        'change_pct': result.get('day_change', 0),
        'risk_level': risk_level,
        'signal': verdict.get('verdict', 'HOLD'),
        'signal_strength': 'Expert consensus',
        'confidence': confidence,
        'confidence_pct': f"{confidence * 100:.1f}%",
        'entry_price': profit_loss.get('entry', result.get('current_price', 0)),
        'target_price': first_target.get('target', result.get('current_price', 0)),
        'stop_loss': profit_loss.get('stop_loss', result.get('current_price', 0)),
        'expected_profit_pct': first_target.get('profit_pct', 0),
        'max_loss_pct': profit_loss.get('max_loss_pct', 0),
        'risk_reward_ratio': profit_loss.get('risk_reward', 0),
        'holding_period': result.get('primary_interval', '5m'),
        'expert_interval': result.get('primary_interval') or result.get('requested_interval') or '5m',
        'sentiment_label': 'Aligned with expert engine',
        'buy_count': 1 if direction == 'BUY' else 0,
        'sell_count': 1 if direction == 'SELL' else 0,
        'neutral_count': 1 if direction == 'HOLD' else 0,
        'technical_score': verdict.get('net_score', 0),
        'composite_score': verdict.get('net_score', 0),
        'expert_verdict': verdict,
        'profit_loss': profit_loss,
        'recommendation': {
            'action': verdict.get('verdict', 'HOLD'),
            'summary': profit_loss.get('recommendation', 'Expert engine did not find a clear trade setup.'),
            'details': [_expert_reason(verdict)],
            'risk_warning': f"Risk mode: {risk_level}",
        },
    }


@app.route('/api/expert-analysis/<symbol>')
@app.route('/stock-search/api/expert-analysis/<symbol>')
def expert_analysis(symbol):
    """Run full expert-based analysis with profit/loss projections."""
    investment = float(request.args.get('investment', 10000))
    interval = request.args.get('interval', '5m')
    preferred_interval = interval if interval in {'1m', '3m', '5m', '15m', '30m', '1h', '1d', '10d'} else '5m'
    ticker = resolve_stock_symbol(symbol)
    result = _run_expert_analysis(ticker, investment, preferred_interval=preferred_interval)
    if isinstance(result, dict) and not result.get('error'):
        result.setdefault('requested_interval', preferred_interval)
        result.setdefault('primary_interval', preferred_interval)
    return jsonify(result)


@app.route('/api/search-stock/<symbol>')
@app.route('/stock-search/api/search-stock/<symbol>')
def search_stock_compat(symbol):
    return jsonify(_tradeai_search_stock(symbol))


@app.route('/stock-search/api/stock-history/<symbol>')
def stock_search_history(symbol):
    ticker = symbol if symbol.upper().endswith((".NS", ".BO")) else f"{symbol}.NS"
    history = get_stock_history_for_chart(WATCHLIST, ticker)
    if history is None:
        return jsonify({"error": "Failed to fetch history"}), 404
    return jsonify(history)


@app.route('/stock-search/api/predict-trajectory/<symbol>')
def stock_search_predict_trajectory(symbol):
    ticker = symbol if symbol.upper().endswith((".NS", ".BO")) else f"{symbol}.NS"
    contexts = request.args.get('contexts', '')
    ctx_list = [ctx for ctx in contexts.split(',') if ctx]
    return jsonify(get_prediction_trajectory(ticker, ctx_list))


@app.route('/stock-search/api/config/status')
def stock_search_config_status():
    return jsonify(get_tradeai_keys_status())


@app.route('/stock-search/api/config/keys', methods=['POST'])
def stock_search_save_config():
    payload = request.get_json(silent=True) or {}
    if payload.get("anthropic_key"):
        set_tradeai_api_key("anthropic", payload["anthropic_key"])
    if payload.get("groq_key"):
        set_tradeai_api_key("groq", payload["groq_key"])
    return jsonify({"status": "saved", **get_tradeai_keys_status()})


@app.route('/stock-search/api/market-status')
@app.route('/api/watchlist-status')
def watchlist_status():
    """Get market data and analysis for the watchlist (intraday opportunities)."""
    data = get_watchlist_data(WATCHLIST)
    analysis = [_fast_stock_to_dashboard_signal(stock) for stock in analyze_watchlist(data, WATCHLIST)] if data is not None else []

    if not analysis:
        return jsonify({"error": "Failed to fetch data"})

    analysis.sort(
        key=lambda x: (abs(x.get('expert_net_score', 0)), x.get('confidence', 0)),
        reverse=True
    )
    opportunities = [x for x in analysis if _verdict_direction(x.get('signal')) in ['BUY', 'SELL']]
    return jsonify({
        "market_data": analysis,
        "top_picks": opportunities[:5]
    })


if __name__ == '__main__':
    import socket

    def find_free_port(start=5000, end=5010):
        for port in range(start, end):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                try:
                    sock.bind((HOST, port))
                    return port
                except OSError:
                    continue
        return start

    run_port = find_free_port(PORT, PORT + 10)
    print("=" * 60)
    print("  📊 TradePulse AI — Unified Trading Platform")
    print(f"  🌐 Open: http://localhost:{run_port}")
    if run_port != PORT:
        print(f"  ℹ️  Port {PORT} was busy, using {run_port} instead")
    print("=" * 60)
    app.run(host=HOST, port=run_port, debug=DEBUG)
