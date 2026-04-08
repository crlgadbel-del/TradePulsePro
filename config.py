"""
Configuration for Intraday Trading Signal Platform
"""
import os
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=env_path)

# API Keys
NEWS_API_KEY = os.getenv('NEWS_API_KEY', '')
ALPHA_VANTAGE_KEY = os.getenv('ALPHA_VANTAGE_KEY', '')
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')

# Market Configuration
INDIAN_STOCKS = [
    'RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'INFY.NS', 'ICICIBANK.NS',
    'HINDUNILVR.NS', 'SBIN.NS', 'BHARTIARTL.NS', 'ITC.NS', 'KOTAKBANK.NS',
    'LT.NS', 'AXISBANK.NS', 'BAJFINANCE.NS', 'ASIANPAINT.NS', 'MARUTI.NS',
    'TITAN.NS', 'SUNPHARMA.NS', 'TATAMOTORS.NS', 'WIPRO.NS', 'HCLTECH.NS',
    'ULTRACEMCO.NS', 'NESTLEIND.NS', 'BAJAJFINSV.NS', 'NTPC.NS', 'POWERGRID.NS',
    'M&M.NS', 'TATASTEEL.NS', 'ONGC.NS', 'JSWSTEEL.NS', 'ADANIENT.NS',
    'DIVISLAB.NS', 'DRREDDY.NS', 'CIPLA.NS', 'TECHM.NS', 'GRASIM.NS',
    'HEROMOTOCO.NS', 'APOLLOHOSP.NS', 'EICHERMOT.NS', 'SBILIFE.NS', 'BPCL.NS',
    'COALINDIA.NS', 'BRITANNIA.NS', 'TATACONSUM.NS', 'HINDALCO.NS', 'INDUSINDBK.NS',
    'BAJAJ-AUTO.NS', 'UPL.NS', 'ADANIPORTS.NS', 'HDFC.NS', 'VEDL.NS'
]

US_STOCKS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA',
    'META', 'TSLA', 'BRK-B', 'UNH', 'JNJ',
    'V', 'XOM', 'JPM', 'PG', 'MA',
    'HD', 'CVX', 'MRK', 'ABBV', 'LLY',
    'PEP', 'KO', 'AVGO', 'COST', 'TMO',
    'WMT', 'MCD', 'CRM', 'CSCO', 'ACN',
    'AMD', 'INTC', 'ADBE', 'NFLX', 'PYPL',
    'DIS', 'NKE', 'BA', 'GS', 'UBER'
]

CRYPTO_PAIRS = [
    'BTC-USD', 'ETH-USD', 'BNB-USD', 'XRP-USD', 'SOL-USD',
    'ADA-USD', 'DOGE-USD', 'DOT-USD', 'AVAX-USD', 'MATIC-USD',
    'LINK-USD', 'UNI-USD', 'ATOM-USD', 'LTC-USD', 'ETC-USD',
    'FIL-USD', 'NEAR-USD', 'APT-USD', 'ARB-USD', 'OP-USD',
    'SHIB-USD', 'INJ-USD', 'SUI-USD', 'SEI-USD', 'TIA-USD',
    'PEPE-USD', 'FET-USD', 'RENDER-USD', 'IMX-USD', 'MANA-USD'
]

# Risk Level Parameters
RISK_LEVELS = {
    'safe': {
        'name': 'Safe Mode',
        'emoji': '🟢',
        'min_indicators': 7,       # Need 7+ indicators agreeing
        'min_confidence': 0.75,    # 75%+ confidence required
        'target_profit': (0.5, 1.5),  # 0.5% - 1.5% profit target
        'stop_loss_pct': 0.5,      # 0.5% stop loss
        'risk_reward_min': 2.0,    # Minimum 1:2 risk-reward
        'volume_threshold': 1.2,    # 20% above average volume
        'sentiment_weight': 0.15,   # Low weight on sentiment
        'description': 'Conservative approach with high win rate and smaller profits'
    },
    'medium': {
        'name': 'Medium Mode',
        'emoji': '🟡',
        'min_indicators': 5,       # Need 5+ indicators agreeing
        'min_confidence': 0.60,    # 60%+ confidence required
        'target_profit': (1.5, 3.0),  # 1.5% - 3% profit target
        'stop_loss_pct': 1.0,      # 1% stop loss
        'risk_reward_min': 1.5,    # Minimum 1:1.5 risk-reward
        'volume_threshold': 1.0,    # Average volume OK
        'sentiment_weight': 0.25,   # Moderate weight on sentiment
        'description': 'Balanced approach with moderate risk and decent profits'
    },
    'aggressive': {
        'name': 'Aggressive Mode',
        'emoji': '🔴',
        'min_indicators': 3,       # Need 3+ indicators agreeing
        'min_confidence': 0.45,    # 45%+ confidence required
        'target_profit': (3.0, 8.0),  # 3% - 8% profit target
        'stop_loss_pct': 2.0,      # 2% stop loss
        'risk_reward_min': 1.0,    # Minimum 1:1 risk-reward
        'volume_threshold': 0.8,    # Can trade lower volume
        'sentiment_weight': 0.35,   # Higher weight on sentiment
        'description': 'Aggressive approach with higher risk but bigger rewards'
    }
}

# Technical Indicator Parameters
INDICATOR_PARAMS = {
    'rsi_period': 14,
    'rsi_overbought': 70,
    'rsi_oversold': 30,
    'macd_fast': 12,
    'macd_slow': 26,
    'macd_signal': 9,
    'bb_period': 20,
    'bb_std': 2,
    'sma_short': 9,
    'sma_medium': 21,
    'sma_long': 50,
    'ema_short': 9,
    'ema_medium': 21,
    'ema_long': 50,
    'stoch_k': 14,
    'stoch_d': 3,
    'atr_period': 14,
    'adx_period': 14,
    'cci_period': 20,
    'williams_period': 14,
    'mfi_period': 14,
    'obv_sma_period': 20,
    'vwap_period': 14,
    'ichimoku_tenkan': 9,
    'ichimoku_kijun': 26,
    'ichimoku_senkou': 52,
}

# 2026 NSE/BSE Market Holidays (Official Calendar)
# Format: (month, day, name)
MARKET_HOLIDAYS_2026 = [
    (1, 26, "Republic Day"),
    (2, 17, "Mahashivratri"),  
    (3, 10, "Holi"),
    (3, 31, "Id-Ul-Fitr (Ramadan Eid)"),
    (4, 3, "Good Friday"),
    (4, 14, "Dr. Ambedkar Jayanti"),
    (5, 1, "Maharashtra Day"),
    (6, 7, "Id-Ul-Adha (Bakri Eid)"),
    (7, 7, "Muharram"),
    (8, 15, "Independence Day"),
    (8, 21, "Janmashtami"),  
    (9, 5, "Milad-Un-Nabi (Prophet Mohammad Birthday)"),
    (10, 2, "Mahatma Gandhi Jayanti"),
    (10, 20, "Dussehra"),
    (11, 9, "Diwali (Laxmi Puja)"),
    (11, 10, "Diwali (Balipratipada)"),
    (11, 5, "Guru Nanak Jayanti"),
    (12, 25, "Christmas"),
]

# News Configuration  
NEWS_RESULTS_LIMIT = 10
NEWS_CACHE_TTL = 600  # 10 minutes

# Cache Settings
CACHE_TTL = 300  # 5 minutes cache
MAX_CACHE_SIZE = 1000

# Server Settings
HOST = '0.0.0.0'
PORT = 5000
DEBUG = True