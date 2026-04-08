"""
Market Data Engine - Fetches real-time and historical data for stocks and crypto
"""
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from cachetools import TTLCache
import logging

logger = logging.getLogger(__name__)

# Cache for market data (5 min TTL)
data_cache = TTLCache(maxsize=500, ttl=300)


def get_stock_data(symbol, period='5d', interval='5m'):
    """Fetch intraday stock/crypto data"""
    cache_key = f"{symbol}_{period}_{interval}"
    
    if cache_key in data_cache:
        return data_cache[cache_key]
    
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        
        if df.empty:
            logger.warning(f"No data returned for {symbol}")
            return None
        
        # Clean data
        df = df.dropna()
        df.index = pd.to_datetime(df.index)
        
        # Add returns
        df['Returns'] = df['Close'].pct_change()
        df['Log_Returns'] = np.log(df['Close'] / df['Close'].shift(1))
        
        data_cache[cache_key] = df
        return df
        
    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {e}")
        return None


def get_stock_info(symbol):
    """Get stock/crypto basic info"""
    cache_key = f"info_{symbol}"
    
    if cache_key in data_cache:
        return data_cache[cache_key]
    
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        # Enhance with Logo Discovery
        logo_url = ''
        website = info.get('website', '')
        domain = website.split('//')[-1].split('/')[0].replace('www.', '') if website else ''
        
        # Curated Official Map for Indian/US symbols (Speed & Accuracy)
        # Using Clearbit as a professional alternative to TradingView
        symbol_logos = {
            'RELIANCE.NS': 'https://logo.clearbit.com/ril.com',
            'TCS.NS': 'https://logo.clearbit.com/tcs.com',
            'HDFCBANK.NS': 'https://logo.clearbit.com/hdfcbank.com',
            'INFY.NS': 'https://logo.clearbit.com/infosys.com',
            'HINDUNILVR.NS': 'https://logo.clearbit.com/hul.co.in',
            'ICICIBANK.NS': 'https://logo.clearbit.com/icicibank.com',
            'AAPL': 'https://logo.clearbit.com/apple.com',
            'MSFT': 'https://logo.clearbit.com/microsoft.com',
            'GOOGL': 'https://logo.clearbit.com/google.com',
            'AMZN': 'https://logo.clearbit.com/amazon.com',
            'TSLA': 'https://logo.clearbit.com/tesla.com',
            'BTC-USD': 'https://coinicons-api.vercel.app/api/icon/btc',
            'ETH-USD': 'https://coinicons-api.vercel.app/api/icon/eth',
            'BNB-USD': 'https://coinicons-api.vercel.app/api/icon/bnb',
            'SOL-USD': 'https://coinicons-api.vercel.app/api/icon/sol'
        }
        
        logo_url = symbol_logos.get(symbol, '')
        if not logo_url and domain:
             logo_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=64"
             
        if not logo_url:
             # Generic Guess for stocks
             host = symbol.split('.')[0].lower()
             logo_url = f"https://logo.clearbit.com/{host}.com"

        result = {
            'symbol': symbol,
            'name': info.get('shortName', info.get('longName', symbol)),
            'price': info.get('currentPrice', info.get('regularMarketPrice', 0)),
            'change': info.get('regularMarketChange', 0),
            'change_pct': info.get('regularMarketChangePercent', 0),
            'volume': info.get('regularMarketVolume', info.get('volume', 0)),
            'avg_volume': info.get('averageDailyVolume10Day', info.get('averageVolume', 0)),
            'market_cap': info.get('marketCap', 0),
            'high': info.get('dayHigh', info.get('regularMarketHigh', 0)),
            'low': info.get('dayLow', info.get('regularMarketLow', 0)),
            'open': info.get('open', info.get('regularMarketOpen', 0)),
            'prev_close': info.get('previousClose', info.get('regularMarketPreviousClose', 0)),
            'sector': info.get('sector', 'N/A'),
            'industry': info.get('industry', 'N/A'),
            'currency': info.get('currency', 'INR' if symbol.endswith('.NS') else 'USD'),
            'exchange': info.get('exchange', 'NSE' if symbol.endswith('.NS') else 'NASDAQ'),
            'logo_url': logo_url
        }
        
        data_cache[cache_key] = result
        return result
        
    except Exception as e:
        logger.error(f"Error fetching info for {symbol}: {e}")
        return {
            'symbol': symbol,
            'name': symbol.replace('.NS', '').replace('-USD', ''),
            'price': 0,
            'change': 0,
            'change_pct': 0,
            'volume': 0,
            'logo_url': ''
        }


def get_multiple_stocks_data(symbols, period='5d', interval='5m'):
    """Fetch data for multiple symbols"""
    results = {}
    for symbol in symbols:
        data = get_stock_data(symbol, period, interval)
        if data is not None:
            results[symbol] = data
    return results


def get_daily_data(symbol, period='3mo'):
    """Get daily data for longer-term analysis"""
    cache_key = f"daily_{symbol}_{period}"
    
    if cache_key in data_cache:
        return data_cache[cache_key]
    
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval='1d')
        
        if df.empty:
            return None
        
        df = df.dropna()
        df['Returns'] = df['Close'].pct_change()
        
        data_cache[cache_key] = df
        return df
        
    except Exception as e:
        logger.error(f"Error fetching daily data for {symbol}: {e}")
        return None


def search_symbol(query):
    """Search for stock/crypto symbols"""
    try:
        results = []
        # Try direct ticker lookup
        ticker = yf.Ticker(query.upper())
        info = ticker.info
        if info and info.get('shortName'):
            results.append({
                'symbol': query.upper(),
                'name': info.get('shortName', query),
                'type': 'stock'
            })
        
        # Try with .NS suffix for Indian stocks
        ticker_ns = yf.Ticker(f"{query.upper()}.NS")
        info_ns = ticker_ns.info
        if info_ns and info_ns.get('shortName'):
            results.append({
                'symbol': f"{query.upper()}.NS",
                'name': info_ns.get('shortName', query),
                'type': 'indian_stock'
            })
        
        # Try with -USD suffix for crypto
        ticker_crypto = yf.Ticker(f"{query.upper()}-USD")
        info_crypto = ticker_crypto.info
        if info_crypto and info_crypto.get('shortName'):
            results.append({
                'symbol': f"{query.upper()}-USD",
                'name': info_crypto.get('shortName', query),
                'type': 'crypto'
            })
        
        return results
        
    except Exception as e:
        logger.error(f"Error searching for {query}: {e}")
        return []


def get_market_status():
    """Check if markets are open, with holiday awareness and countdown timer"""
    import pytz
    from config import MARKET_HOLIDAYS_2026
    
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    today = now.date()
    
    # Check if today is a holiday
    is_holiday = False
    holiday_name = ''
    for m, d, name in MARKET_HOLIDAYS_2026:
        try:
            holiday_date = today.replace(month=m, day=d)
            if today == holiday_date:
                is_holiday = True
                holiday_name = name
                break
        except ValueError:
            continue
    
    # Indian market hours (9:15 AM - 3:30 PM IST, Mon-Fri)
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    is_weekday = now.weekday() < 5
    indian_is_open = is_weekday and not is_holiday and market_open <= now <= market_close
    
    # Countdown timer
    timer_label = ''
    timer_seconds = 0
    
    if is_holiday:
        timer_label = f'Holiday: {holiday_name}'
        timer_seconds = 0
    elif not is_weekday:
        timer_label = 'Weekend'
        timer_seconds = 0
    elif now < market_open:
        # Before market open
        diff = (market_open - now).total_seconds()
        timer_label = 'Opens in'
        timer_seconds = int(diff)
    elif now > market_close:
        # After market close
        timer_label = 'Closed'
        timer_seconds = 0
    else:
        # Market is open
        diff = (market_close - now).total_seconds()
        timer_label = 'Closes in'
        timer_seconds = int(diff)
    
    # US market hours (9:30 AM - 4:00 PM ET)
    try:
        et = pytz.timezone('US/Eastern')
        now_et = now.astimezone(et)
        us_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        us_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        us_is_open = now_et.weekday() < 5 and us_open <= now_et <= us_close
    except Exception:
        us_is_open = False
    
    # Crypto is always open
    crypto_is_open = True
    
    # Get all holidays for the year
    holidays_list = []
    for m, d, name in MARKET_HOLIDAYS_2026:
        try:
            hdate = today.replace(month=m, day=d)
            holidays_list.append({
                'date': hdate.strftime('%Y-%m-%d'),
                'day': hdate.strftime('%A'),
                'name': name,
                'passed': hdate < today
            })
        except ValueError:
            continue
    
    return {
        'indian': {
            'is_open': indian_is_open,
            'name': 'NSE/BSE',
            'timer_label': timer_label,
            'timer_seconds': timer_seconds,
            'is_holiday': is_holiday,
            'holiday_name': holiday_name,
        },
        'us': {'is_open': us_is_open, 'name': 'NYSE/NASDAQ'},
        'crypto': {'is_open': crypto_is_open, 'name': 'Crypto Market'},
        'holidays': holidays_list,
        'server_time': now.strftime('%Y-%m-%d %H:%M:%S IST'),
    }


def get_news_for_stock(symbol, api_key=''):
    """Fetch news for a stock symbol with multiple fallbacks"""
    cache_key = f"news_stock_{symbol}"
    if cache_key in data_cache:
        return data_cache[cache_key]
    
    clean = symbol.replace('.NS', '').replace('-USD', '').replace('.', ' ')
    articles = []
    
    # 1. Try NewsAPI
    if api_key:
        try:
            url = 'https://newsapi.org/v2/everything'
            params = {
                'q': f'{clean} stock',
                'language': 'en',
                'sortBy': 'publishedAt',
                'pageSize': 8,
                'apiKey': api_key,
                'from': (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            }
            resp = requests.get(url, params=params, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                for a in data.get('articles', []):
                    if a.get('title') and a['title'] != '[Removed]':
                        articles.append({
                            'title': a['title'],
                            'description': a.get('description', ''),
                            'source': a.get('source', {}).get('name', 'Unknown'),
                            'url': a.get('url', '#'),
                            'published': a.get('publishedAt', ''),
                            'image': a.get('urlToImage', ''),
                        })
        except Exception as e:
            logger.error(f"NewsAPI error for {symbol}: {e}")
    
    # 2. Fallback: Google News RSS
    if not articles:
        try:
            import xml.etree.ElementTree as ET
            rss_url = f"https://news.google.com/rss/search?q={clean}+stock+market&hl=en-IN&gl=IN&ceid=IN:en"
            resp = requests.get(rss_url, timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                for item in root.findall('.//item')[:8]:
                    title = item.find('title')
                    link = item.find('link')
                    pub_date = item.find('pubDate')
                    source = item.find('source')
                    if title is not None and title.text:
                        articles.append({
                            'title': title.text,
                            'description': '',
                            'source': source.text if source is not None else 'Google News',
                            'url': link.text if link is not None else '#',
                            'published': pub_date.text if pub_date is not None else '',
                            'image': '',
                        })
        except Exception as e:
            logger.error(f"Google News RSS error for {symbol}: {e}")
    
    # 3. Final fallback
    if not articles:
        articles = [{
            'title': f'No recent news found for {clean}',
            'description': 'Try searching with a different term or check back later.',
            'source': 'System',
            'url': '#',
            'published': datetime.now().isoformat(),
            'image': '',
        }]
    
    data_cache[cache_key] = articles
    return articles

