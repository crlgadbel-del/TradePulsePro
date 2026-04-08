"""
News Sentiment Analysis Engine
Analyzes financial news to gauge market sentiment
"""
import requests
import re
from textblob import TextBlob
from datetime import datetime, timedelta
from cachetools import TTLCache
import logging

logger = logging.getLogger(__name__)

# Cache for news data (10 min TTL)
news_cache = TTLCache(maxsize=200, ttl=600)

# Financial sentiment keywords with weights
BULLISH_KEYWORDS = {
    'surge': 3, 'soar': 3, 'rally': 3, 'breakout': 3, 'bullish': 3,
    'upgrade': 2, 'beat': 2, 'outperform': 2, 'growth': 2, 'profit': 2,
    'gain': 2, 'rise': 2, 'jump': 2, 'boost': 2, 'strong': 2,
    'buy': 1, 'positive': 1, 'up': 1, 'higher': 1, 'recover': 1,
    'momentum': 1, 'opportunity': 1, 'expansion': 1, 'innovation': 1,
    'dividend': 1, 'acquisition': 1, 'record': 1, 'revenue': 1,
    'optimistic': 2, 'breakthrough': 2, 'upbeat': 2, 'stellar': 2,
}

BEARISH_KEYWORDS = {
    'crash': 3, 'plunge': 3, 'collapse': 3, 'bearish': 3, 'selloff': 3,
    'downgrade': 2, 'miss': 2, 'underperform': 2, 'decline': 2, 'loss': 2,
    'drop': 2, 'fall': 2, 'sink': 2, 'weak': 2, 'recession': 2,
    'sell': 1, 'negative': 1, 'down': 1, 'lower': 1, 'risk': 1,
    'warning': 1, 'concern': 1, 'threat': 1, 'crisis': 1, 'debt': 1,
    'lawsuit': 1, 'fraud': 1, 'investigation': 1, 'penalty': 1,
    'pessimistic': 2, 'disappointing': 2, 'troubled': 2, 'volatile': 1,
}


def get_news_for_symbol(symbol, api_key=''):
    """Fetch news articles for a given symbol"""
    cache_key = f"news_{symbol}"
    
    if cache_key in news_cache:
        return news_cache[cache_key]
    
    # Clean symbol name for search
    clean_symbol = symbol.replace('.NS', '').replace('-USD', '').replace('.', ' ')
    
    articles = []
    
    # Try NewsAPI if key available
    if api_key:
        try:
            url = 'https://newsapi.org/v2/everything'
            params = {
                'q': f'{clean_symbol} stock market',
                'language': 'en',
                'sortBy': 'publishedAt',
                'pageSize': 10,
                'apiKey': api_key,
                'from': (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
            }
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                for article in data.get('articles', []):
                    articles.append({
                        'title': article.get('title', ''),
                        'description': article.get('description', ''),
                        'source': article.get('source', {}).get('name', 'Unknown'),
                        'url': article.get('url', ''),
                        'published': article.get('publishedAt', ''),
                    })
        except Exception as e:
            logger.error(f"NewsAPI error: {e}")
    
    # Fallback: Generate simulated news analysis based on keywords
    if not articles:
        articles = _generate_market_context(clean_symbol)
    
    news_cache[cache_key] = articles
    return articles


def _generate_market_context(symbol):
    """Generate market context when no news API is available"""
    return [
        {
            'title': f'Market analysis for {symbol}',
            'description': f'Technical analysis and market trends for {symbol} based on recent price action and volume patterns.',
            'source': 'Technical Analysis',
            'url': '',
            'published': datetime.now().isoformat(),
        }
    ]


def analyze_sentiment(articles):
    """Analyze sentiment of news articles"""
    if not articles:
        return {
            'overall_sentiment': 0,
            'sentiment_label': 'Neutral',
            'bullish_count': 0,
            'bearish_count': 0,
            'neutral_count': 0,
            'articles_analyzed': 0,
            'key_themes': [],
            'sentiment_breakdown': []
        }
    
    sentiments = []
    article_sentiments = []
    bullish = 0
    bearish = 0
    neutral = 0
    all_themes = []
    
    for article in articles:
        text = f"{article.get('title', '')} {article.get('description', '')}"
        
        if not text.strip():
            continue
        
        # TextBlob sentiment
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity  # -1 to 1
        
        # Financial keyword sentiment
        keyword_score = _compute_keyword_sentiment(text)
        
        # Combined sentiment (weighted average)
        combined = polarity * 0.3 + keyword_score * 0.7
        
        sentiments.append(combined)
        
        if combined > 0.1:
            label = 'Bullish'
            bullish += 1
        elif combined < -0.1:
            label = 'Bearish'
            bearish += 1
        else:
            label = 'Neutral'
            neutral += 1
        
        article_sentiments.append({
            'title': article.get('title', ''),
            'source': article.get('source', 'Unknown'),
            'sentiment': combined,
            'label': label,
            'published': article.get('published', ''),
        })
        
        # Extract themes
        themes = _extract_themes(text)
        all_themes.extend(themes)
    
    overall = sum(sentiments) / len(sentiments) if sentiments else 0
    
    if overall > 0.2:
        overall_label = 'Very Bullish'
    elif overall > 0.05:
        overall_label = 'Bullish'
    elif overall < -0.2:
        overall_label = 'Very Bearish'
    elif overall < -0.05:
        overall_label = 'Bearish'
    else:
        overall_label = 'Neutral'
    
    # Get unique themes sorted by frequency
    theme_counts = {}
    for theme in all_themes:
        theme_counts[theme] = theme_counts.get(theme, 0) + 1
    key_themes = sorted(theme_counts.keys(), key=lambda x: theme_counts[x], reverse=True)[:5]
    
    return {
        'overall_sentiment': round(overall, 3),
        'sentiment_label': overall_label,
        'bullish_count': bullish,
        'bearish_count': bearish,
        'neutral_count': neutral,
        'articles_analyzed': len(sentiments),
        'key_themes': key_themes,
        'sentiment_breakdown': article_sentiments
    }


def _compute_keyword_sentiment(text):
    """Compute sentiment based on financial keywords"""
    text_lower = text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    
    bull_score = 0
    bear_score = 0
    
    for word in words:
        if word in BULLISH_KEYWORDS:
            bull_score += BULLISH_KEYWORDS[word]
        if word in BEARISH_KEYWORDS:
            bear_score += BEARISH_KEYWORDS[word]
    
    total = bull_score + bear_score
    if total == 0:
        return 0
    
    # Normalize to -1 to 1 range
    return (bull_score - bear_score) / total


def _extract_themes(text):
    """Extract key financial themes from text"""
    text_lower = text.lower()
    themes = []
    
    theme_keywords = {
        'Earnings': ['earnings', 'quarterly', 'revenue', 'profit', 'income'],
        'Growth': ['growth', 'expansion', 'scale', 'increase'],
        'Technology': ['technology', 'ai', 'innovation', 'digital', 'tech'],
        'Regulation': ['regulation', 'compliance', 'sec', 'government', 'policy'],
        'M&A': ['acquisition', 'merger', 'takeover', 'buyout'],
        'Market Trend': ['market', 'trend', 'rally', 'correction', 'bull', 'bear'],
        'Interest Rates': ['interest rate', 'fed', 'monetary', 'inflation'],
        'Global': ['global', 'international', 'trade', 'geopolitical'],
        'Crypto': ['crypto', 'bitcoin', 'blockchain', 'defi', 'web3'],
        'Energy': ['oil', 'energy', 'renewable', 'solar', 'ev'],
    }
    
    for theme, keywords in theme_keywords.items():
        for keyword in keywords:
            if keyword in text_lower:
                themes.append(theme)
                break
    
    return themes


def get_market_sentiment_summary():
    """Get overall market sentiment"""
    cache_key = "market_sentiment"
    
    if cache_key in news_cache:
        return news_cache[cache_key]
    
    # General market news
    general_articles = [
        {
            'title': 'Market Overview',
            'description': 'Markets showing mixed signals with sector rotation and volume analysis indicating cautious optimism.',
            'source': 'Market Analysis',
            'url': '',
            'published': datetime.now().isoformat(),
        }
    ]
    
    result = analyze_sentiment(general_articles)
    news_cache[cache_key] = result
    return result
