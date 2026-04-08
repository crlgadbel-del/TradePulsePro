"""
Signal Generator Engine
Generates BUY/SELL signals with entry, exit, stop-loss based on risk level
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from config import RISK_LEVELS
from technical_analysis import compute_all_indicators, analyze_indicators, get_indicator_summary
from sentiment_analysis import get_news_for_symbol, analyze_sentiment
import logging

logger = logging.getLogger(__name__)


def generate_signal(df, symbol, risk_level='medium', news_api_key=''):
    """
    Generate trading signal for a given stock/crypto
    
    Args:
        df: DataFrame with OHLCV data
        symbol: Stock/crypto symbol
        risk_level: 'safe', 'medium', or 'aggressive'
        news_api_key: Optional API key for news
    
    Returns:
        Signal dictionary with entry, exit, stop-loss, confidence etc.
    """
    if df is None or df.empty or len(df) < 30:
        return _no_signal(symbol, "Insufficient data for analysis")
    
    risk_params = RISK_LEVELS.get(risk_level, RISK_LEVELS['medium'])
    
    # Step 1: Compute all technical indicators
    df_analyzed = compute_all_indicators(df)
    if df_analyzed is None:
        return _no_signal(symbol, "Failed to compute indicators")
    
    # Step 2: Get indicator signals
    indicator_analysis = analyze_indicators(df_analyzed)
    
    # Step 3: Get news sentiment
    articles = get_news_for_symbol(symbol, news_api_key)
    sentiment = analyze_sentiment(articles)
    
    # Step 4: Calculate composite score
    composite = _calculate_composite_score(indicator_analysis, sentiment, risk_params)
    
    # Step 5: Determine signal direction
    last = df_analyzed.iloc[-1]
    current_price = float(last['Close'])
    atr = float(last.get('ATR', current_price * 0.02)) if not pd.isna(last.get('ATR', np.nan)) else current_price * 0.02
    
    signal = _determine_signal(
        composite, current_price, atr, risk_params, indicator_analysis
    )
    
    # Step 6: Calculate entry/exit points
    entry_exit = _calculate_entry_exit(
        signal['direction'], current_price, atr, risk_params, df_analyzed
    )
    
    # Step 7: Determine best time windows
    time_windows = _analyze_time_windows(df_analyzed, symbol)
    
    # Step 8: Get indicator summary
    ind_summary = get_indicator_summary(df_analyzed)
    
    # Build result
    result = {
        'symbol': symbol,
        'timestamp': datetime.now().isoformat(),
        'current_price': current_price,
        'risk_level': risk_level,
        'risk_name': risk_params['name'],
        'risk_emoji': risk_params['emoji'],
        
        # Signal
        'signal': signal['direction'],
        'signal_strength': signal['strength'],
        'confidence': signal['confidence'],
        'confidence_pct': f"{signal['confidence'] * 100:.1f}%",
        
        # Entry/Exit
        'entry_price': entry_exit['entry'],
        'target_price': entry_exit['target'],
        'stop_loss': entry_exit['stop_loss'],
        'expected_profit_pct': entry_exit['profit_pct'],
        'max_loss_pct': entry_exit['loss_pct'],
        'risk_reward_ratio': entry_exit['risk_reward'],
        
        # Timing
        'best_entry_time': time_windows.get('best_entry', 'Market Open'),
        'best_exit_time': time_windows.get('best_exit', 'Before Close'),
        'holding_period': time_windows.get('suggested_holding', '1-4 hours'),
        
        # Analysis
        'technical_signals': indicator_analysis['signals'],
        'buy_count': sum(1 for s in indicator_analysis['signals'] if s['signal'] == 'BUY'),
        'sell_count': sum(1 for s in indicator_analysis['signals'] if s['signal'] == 'SELL'),
        'neutral_count': sum(1 for s in indicator_analysis['signals'] if s['signal'] == 'NEUTRAL'),
        'total_indicators': indicator_analysis['total_signals'],
        
        # Sentiment
        'sentiment': sentiment,
        'sentiment_score': sentiment['overall_sentiment'],
        'sentiment_label': sentiment['sentiment_label'],
        
        # Indicators
        'indicators': ind_summary,
        
        # Score breakdown
        'technical_score': composite['technical_score'],
        'sentiment_score_weighted': composite['sentiment_score'],
        'composite_score': composite['total_score'],
        
        # Recommendation
        'recommendation': _generate_recommendation(signal, entry_exit, risk_params, sentiment),
    }
    
    return result


def _calculate_composite_score(indicator_analysis, sentiment, risk_params):
    """Calculate composite trading score"""
    # Technical score (weighted buy vs sell)
    buy_score = indicator_analysis['buy_pct'] / 100
    sell_score = indicator_analysis['sell_pct'] / 100
    
    # Convert to -1 to 1 range where positive = bullish
    tech_score = buy_score - sell_score
    
    # Sentiment score
    sent_score = sentiment['overall_sentiment']
    
    # Weight based on risk level
    sent_weight = risk_params['sentiment_weight']
    tech_weight = 1 - sent_weight
    
    total = tech_score * tech_weight + sent_score * sent_weight
    
    return {
        'technical_score': round(tech_score, 3),
        'sentiment_score': round(sent_score, 3),
        'total_score': round(total, 3),
        'tech_weight': tech_weight,
        'sent_weight': sent_weight,
    }


def _determine_signal(composite, current_price, atr, risk_params, indicator_analysis):
    """Determine the trading signal based on composite score"""
    score = composite['total_score']
    
    # Count strong signals
    buy_strong = sum(1 for s in indicator_analysis['signals'] 
                     if s['signal'] == 'BUY' and s['strength'] in ['strong', 'moderate'])
    sell_strong = sum(1 for s in indicator_analysis['signals'] 
                      if s['signal'] == 'SELL' and s['strength'] in ['strong', 'moderate'])
    
    min_indicators = risk_params['min_indicators']
    min_confidence = risk_params['min_confidence']
    
    # Calculate confidence
    total_signals = indicator_analysis['total_signals']
    if total_signals == 0:
        confidence = 0
    else:
        agreement = max(buy_strong, sell_strong) / total_signals
        confidence = min(agreement + abs(score) * 0.3, 1.0)
    
    # Determine direction
    if score > 0.05 and buy_strong >= min_indicators and confidence >= min_confidence:
        direction = 'BUY'
        strength = 'STRONG' if score > 0.3 else ('MODERATE' if score > 0.15 else 'WEAK')
    elif score < -0.05 and sell_strong >= min_indicators and confidence >= min_confidence:
        direction = 'SELL'
        strength = 'STRONG' if score < -0.3 else ('MODERATE' if score < -0.15 else 'WEAK')
    elif score > 0.02 and buy_strong >= max(min_indicators - 2, 2):
        direction = 'BUY'
        strength = 'WEAK'
        confidence = confidence * 0.7
    elif score < -0.02 and sell_strong >= max(min_indicators - 2, 2):
        direction = 'SELL'
        strength = 'WEAK'
        confidence = confidence * 0.7
    else:
        direction = 'HOLD'
        strength = 'NEUTRAL'
        confidence = 0.5
    
    return {
        'direction': direction,
        'strength': strength,
        'confidence': round(confidence, 3),
    }


def _calculate_entry_exit(direction, current_price, atr, risk_params, df):
    """Calculate entry, target, and stop-loss prices"""
    target_range = risk_params['target_profit']
    stop_loss_pct = risk_params['stop_loss_pct']
    
    if direction == 'BUY':
        # Entry at current price or slightly below
        entry = round(current_price * 0.999, 2)
        
        # Target based on risk level
        target_pct = (target_range[0] + target_range[1]) / 2 / 100
        target = round(current_price * (1 + target_pct), 2)
        
        # Stop loss
        stop_loss = round(current_price * (1 - stop_loss_pct / 100), 2)
        
        profit_pct = round(target_pct * 100, 2)
        loss_pct = round(stop_loss_pct, 2)
        
    elif direction == 'SELL':
        # Short entry
        entry = round(current_price * 1.001, 2)
        
        # Target below current price
        target_pct = (target_range[0] + target_range[1]) / 2 / 100
        target = round(current_price * (1 - target_pct), 2)
        
        # Stop loss above
        stop_loss = round(current_price * (1 + stop_loss_pct / 100), 2)
        
        profit_pct = round(target_pct * 100, 2)
        loss_pct = round(stop_loss_pct, 2)
        
    else:  # HOLD
        entry = current_price
        target = current_price
        stop_loss = current_price
        profit_pct = 0
        loss_pct = 0
    
    risk_reward = round(profit_pct / loss_pct, 2) if loss_pct > 0 else 0
    
    return {
        'entry': entry,
        'target': target,
        'stop_loss': stop_loss,
        'profit_pct': profit_pct,
        'loss_pct': loss_pct,
        'risk_reward': risk_reward,
    }


def _analyze_time_windows(df, symbol):
    """Analyze best time windows for entry/exit depending on market type"""
    is_indian = '.NS' in symbol or '.BO' in symbol
    is_crypto = '-USD' in symbol
    
    if is_indian:
        best_entry = '9:15 - 10:00'
        best_exit = '15:00 - 15:30'
        high_vol = '9:15 - 10:30'
        suggested_holding = 'Full Intraday (Close before 3:30)'
    elif is_crypto:
        best_entry = 'UTC 12:00 - 16:00 (High Liq)'
        best_exit = 'UTC 20:00 - 22:00'
        high_vol = '24/7 (Global overlap)'
        suggested_holding = '4-8 Hours'
    else:  # US Stocks
        best_entry = '9:30 - 10:30 (Market Open)'
        best_exit = '15:00 - 16:00 (Power Hour)'
        high_vol = '9:30 - 11:00'
        suggested_holding = 'Full Day Intraday'

    if df is None or df.empty:
        return {}
    
    try:
        # Check if actual dataframe has intraday data
        if hasattr(df.index, 'hour'):
            # Intraday dynamic calculation can go here, but static is safer for specific markets
            pass
            
    except Exception as e:
        logger.error(f"Time window analysis error: {e}")
    
    return {
        'best_entry': best_entry,
        'best_exit': best_exit,
        'high_volatility': high_vol,
        'suggested_holding': 'Full Intraday (Close before 3:30)' if is_indian else '2-4 hours',
    }


def _generate_recommendation(signal, entry_exit, risk_params, sentiment):
    """Generate human-readable trading recommendation"""
    direction = signal['direction']
    confidence = signal['confidence']
    strength = signal['strength']
    
    if direction == 'HOLD':
        return {
            'action': 'HOLD / NO TRADE',
            'summary': 'No clear trading opportunity. Stay on sidelines.',
            'details': [
                'Indicators are giving mixed signals',
                'Wait for better confluence before entering',
                f'Current sentiment: {sentiment["sentiment_label"]}',
            ],
            'risk_warning': 'Low confidence in direction - avoid forced trades',
        }
    
    action = f"{'BUY' if direction == 'BUY' else 'SHORT SELL'}"
    
    details = [
        f"Signal Strength: {strength}",
        f"Confidence: {confidence * 100:.0f}%",
        f"Entry Price: {entry_exit['entry']:.2f}",
        f"Target Price: {entry_exit['target']:.2f} ({entry_exit['profit_pct']:.1f}% profit)",
        f"Stop Loss: {entry_exit['stop_loss']:.2f} ({entry_exit['loss_pct']:.1f}% risk)",
        f"Risk/Reward Ratio: 1:{entry_exit['risk_reward']:.1f}",
        f"News Sentiment: {sentiment['sentiment_label']}",
    ]
    
    risk_warning = f"Risk Mode: {risk_params['name']} - {risk_params['description']}"
    
    return {
        'action': action,
        'summary': f"{action} signal with {confidence*100:.0f}% confidence. Target {entry_exit['profit_pct']:.1f}% profit.",
        'details': details,
        'risk_warning': risk_warning,
    }


def _no_signal(symbol, reason):
    """Return empty signal when analysis fails"""
    return {
        'symbol': symbol,
        'timestamp': datetime.now().isoformat(),
        'current_price': 0,
        'signal': 'NO_DATA',
        'signal_strength': 'NONE',
        'confidence': 0,
        'confidence_pct': '0%',
        'entry_price': 0,
        'target_price': 0,
        'stop_loss': 0,
        'expected_profit_pct': 0,
        'max_loss_pct': 0,
        'risk_reward_ratio': 0,
        'technical_signals': [],
        'buy_count': 0,
        'sell_count': 0,
        'neutral_count': 0,
        'total_indicators': 0,
        'sentiment': {'overall_sentiment': 0, 'sentiment_label': 'N/A'},
        'indicators': {},
        'recommendation': {
            'action': 'NO TRADE',
            'summary': reason,
            'details': [reason],
            'risk_warning': 'Insufficient data for analysis',
        },
        'risk_level': 'N/A',
        'risk_name': 'N/A',
        'risk_emoji': '⚪',
    }


def scan_market(symbols, risk_level='medium', news_api_key=''):
    """Scan multiple symbols and return top signals"""
    from market_data import get_stock_data, get_stock_info
    
    results = []
    
    for symbol in symbols:
        try:
            df = get_stock_data(symbol, period='5d', interval='5m')
            if df is not None and len(df) >= 30:
                signal = generate_signal(df, symbol, risk_level, news_api_key)
                if signal['signal'] != 'NO_DATA':
                    # Add Logo and Name from info
                    info = get_stock_info(symbol)
                    signal['logo_url'] = info.get('logo_url', '')
                    signal['name'] = info.get('name', symbol.split('.')[0])
                    results.append(signal)
        except Exception as e:
            logger.error(f"Error scanning {symbol}: {e}")
    
    # Sort by confidence
    results.sort(key=lambda x: x.get('confidence', 0), reverse=True)
    
    return results
