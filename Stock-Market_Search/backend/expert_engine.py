"""
Expert-Based Trading Analysis Engine
=====================================
Uses multiple technical indicators + rule-based expert system to produce
profit/loss suggestions with risk-reward ratios and confidence scores.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


# ─── Technical Indicator Functions ────────────────────────────────────────────

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calc_macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_bollinger(series, period=20, std_dev=2):
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return upper, sma, lower


def calc_atr(high, low, close, period=14):
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def calc_vwap(high, low, close, volume):
    typical_price = (high + low + close) / 3
    cumulative_tp_vol = (typical_price * volume).cumsum()
    cumulative_vol = volume.cumsum()
    return cumulative_tp_vol / cumulative_vol


def find_support_resistance(close, window=20):
    """Find support and resistance levels from recent price action."""
    recent = close.tail(window * 3)
    if len(recent) < window:
        return None, None

    # Rolling min/max
    rolling_min = recent.rolling(window=window).min()
    rolling_max = recent.rolling(window=window).max()

    support = rolling_min.dropna().iloc[-1]
    resistance = rolling_max.dropna().iloc[-1]

    return float(support), float(resistance)


def calc_stochastic(high, low, close, k_period=14, d_period=3):
    lowest_low = low.rolling(window=k_period).min()
    highest_high = high.rolling(window=k_period).max()
    k = 100 * ((close - lowest_low) / (highest_high - lowest_low))
    d = k.rolling(window=d_period).mean()
    return k, d


# ─── Expert Rules Engine ─────────────────────────────────────────────────────

def evaluate_expert_rules(indicators):
    """
    Rule-based expert system that aggregates technical indicators
    into a final verdict with confidence and reasoning.
    """
    rules_fired = []
    buy_score = 0
    sell_score = 0
    total_weight = 0

    rsi = indicators.get('rsi', 50)
    macd_hist = indicators.get('macd_histogram', 0)
    macd_cross = indicators.get('macd_crossover', 'none')
    bb_position = indicators.get('bb_position', 'middle')
    price_vs_vwap = indicators.get('price_vs_vwap', 'at')
    vol_trend = indicators.get('volume_trend', 'normal')
    trend_slope = indicators.get('trend_slope', 0)
    stoch_k = indicators.get('stoch_k', 50)
    stoch_d = indicators.get('stoch_d', 50)
    price_vs_sma20 = indicators.get('price_vs_sma20', 'at')
    support = indicators.get('support', 0)
    resistance = indicators.get('resistance', 0)
    current_price = indicators.get('current_price', 0)
    atr = indicators.get('atr', 0)

    # ── Rule 1: RSI (weight: 20) ──
    weight = 20
    total_weight += weight
    if rsi < 25:
        buy_score += weight
        rules_fired.append({"rule": "RSI Extreme Oversold", "type": "BUY", "weight": weight,
                            "detail": f"RSI={rsi:.1f} < 25 → Strong reversal likely"})
    elif rsi < 35:
        buy_score += weight * 0.7
        rules_fired.append({"rule": "RSI Oversold", "type": "BUY", "weight": int(weight * 0.7),
                            "detail": f"RSI={rsi:.1f} in oversold zone"})
    elif rsi > 75:
        sell_score += weight
        rules_fired.append({"rule": "RSI Extreme Overbought", "type": "SELL", "weight": weight,
                            "detail": f"RSI={rsi:.1f} > 75 → Price exhaustion likely"})
    elif rsi > 65:
        sell_score += weight * 0.7
        rules_fired.append({"rule": "RSI Overbought", "type": "SELL", "weight": int(weight * 0.7),
                            "detail": f"RSI={rsi:.1f} in overbought zone"})
    elif 45 <= rsi <= 55:
        rules_fired.append({"rule": "RSI Neutral", "type": "HOLD", "weight": 0,
                            "detail": f"RSI={rsi:.1f} neutral — no directional bias"})

    # ── Rule 2: MACD (weight: 25) ──
    weight = 25
    total_weight += weight
    if macd_cross == 'bullish':
        buy_score += weight
        rules_fired.append({"rule": "MACD Bullish Crossover", "type": "BUY", "weight": weight,
                            "detail": "MACD line crossed above signal → momentum shifting up"})
    elif macd_cross == 'bearish':
        sell_score += weight
        rules_fired.append({"rule": "MACD Bearish Crossover", "type": "SELL", "weight": weight,
                            "detail": "MACD line crossed below signal → momentum shifting down"})
    elif macd_hist > 0:
        buy_score += weight * 0.4
        rules_fired.append({"rule": "MACD Positive Histogram", "type": "BUY", "weight": int(weight * 0.4),
                            "detail": "MACD histogram positive → bullish momentum"})
    elif macd_hist < 0:
        sell_score += weight * 0.4
        rules_fired.append({"rule": "MACD Negative Histogram", "type": "SELL", "weight": int(weight * 0.4),
                            "detail": "MACD histogram negative → bearish momentum"})

    # ── Rule 3: Bollinger Bands (weight: 15) ──
    weight = 15
    total_weight += weight
    if bb_position == 'below_lower':
        buy_score += weight
        rules_fired.append({"rule": "Price Below Lower Bollinger", "type": "BUY", "weight": weight,
                            "detail": "Price below lower band → potential bounce/mean reversion"})
    elif bb_position == 'above_upper':
        sell_score += weight
        rules_fired.append({"rule": "Price Above Upper Bollinger", "type": "SELL", "weight": weight,
                            "detail": "Price above upper band → overextended, pullback likely"})
    elif bb_position == 'near_lower':
        buy_score += weight * 0.5
        rules_fired.append({"rule": "Price Near Lower Bollinger", "type": "BUY", "weight": int(weight * 0.5),
                            "detail": "Price approaching lower band"})
    elif bb_position == 'near_upper':
        sell_score += weight * 0.5
        rules_fired.append({"rule": "Price Near Upper Bollinger", "type": "SELL", "weight": int(weight * 0.5),
                            "detail": "Price approaching upper band"})

    # ── Rule 4: VWAP (weight: 10) ──
    weight = 10
    total_weight += weight
    if price_vs_vwap == 'above':
        buy_score += weight * 0.6
        rules_fired.append({"rule": "Price Above VWAP", "type": "BUY", "weight": int(weight * 0.6),
                            "detail": "Trading above VWAP → institutional buying pressure"})
    elif price_vs_vwap == 'below':
        sell_score += weight * 0.6
        rules_fired.append({"rule": "Price Below VWAP", "type": "SELL", "weight": int(weight * 0.6),
                            "detail": "Trading below VWAP → institutional selling pressure"})

    # ── Rule 5: Volume (weight: 10) ──
    weight = 10
    total_weight += weight
    if vol_trend == 'spike_up':
        buy_score += weight * 0.5
        rules_fired.append({"rule": "Volume Spike (Bullish)", "type": "BUY", "weight": int(weight * 0.5),
                            "detail": "Volume surge with upward price → strong buying interest"})
    elif vol_trend == 'spike_down':
        sell_score += weight * 0.5
        rules_fired.append({"rule": "Volume Spike (Bearish)", "type": "SELL", "weight": int(weight * 0.5),
                            "detail": "Volume surge with downward price → panic/distribution"})
    elif vol_trend == 'declining':
        rules_fired.append({"rule": "Declining Volume", "type": "HOLD", "weight": 0,
                            "detail": "Decreasing volume → trend losing steam"})

    # ── Rule 6: Trend Slope (weight: 10) ──
    weight = 10
    total_weight += weight
    if trend_slope > 0.0002:
        buy_score += weight
        rules_fired.append({"rule": "Strong Uptrend", "type": "BUY", "weight": weight,
                            "detail": f"Price slope strongly positive ({trend_slope:.6f})"})
    elif trend_slope > 0:
        buy_score += weight * 0.4
        rules_fired.append({"rule": "Mild Uptrend", "type": "BUY", "weight": int(weight * 0.4),
                            "detail": f"Price slope mildly positive"})
    elif trend_slope < -0.0002:
        sell_score += weight
        rules_fired.append({"rule": "Strong Downtrend", "type": "SELL", "weight": weight,
                            "detail": f"Price slope strongly negative ({trend_slope:.6f})"})
    elif trend_slope < 0:
        sell_score += weight * 0.4
        rules_fired.append({"rule": "Mild Downtrend", "type": "SELL", "weight": int(weight * 0.4),
                            "detail": f"Price slope mildly negative"})

    # ── Rule 7: Stochastic (weight: 10) ──
    weight = 10
    total_weight += weight
    if stoch_k < 20 and stoch_d < 20:
        buy_score += weight
        rules_fired.append({"rule": "Stochastic Oversold", "type": "BUY", "weight": weight,
                            "detail": f"Stochastic %K={stoch_k:.1f}, %D={stoch_d:.1f} → oversold"})
    elif stoch_k > 80 and stoch_d > 80:
        sell_score += weight
        rules_fired.append({"rule": "Stochastic Overbought", "type": "SELL", "weight": weight,
                            "detail": f"Stochastic %K={stoch_k:.1f}, %D={stoch_d:.1f} → overbought"})

    # ── Compute Final Verdict ──
    net_score = buy_score - sell_score
    max_possible = total_weight
    confidence = min(abs(net_score) / max_possible * 100, 100)

    if net_score > 15:
        verdict = "STRONG BUY"
    elif net_score > 5:
        verdict = "BUY"
    elif net_score < -15:
        verdict = "STRONG SELL"
    elif net_score < -5:
        verdict = "SELL"
    else:
        verdict = "HOLD"

    return {
        "verdict": verdict,
        "confidence": round(confidence, 1),
        "buy_score": round(buy_score, 1),
        "sell_score": round(sell_score, 1),
        "net_score": round(net_score, 1),
        "rules_fired": rules_fired
    }


# ─── Profit / Loss Calculator ────────────────────────────────────────────────

def calculate_profit_loss(current_price, verdict, atr, support, resistance,
                          investment_amount=10000):
    """
    Calculates projected profit/loss scenarios based on expert verdict,
    ATR-based targets, and support/resistance levels.
    """
    if current_price <= 0 or atr <= 0:
        return None

    shares = int(investment_amount / current_price)
    if shares <= 0:
        shares = 1

    actual_investment = shares * current_price

    # Calculate dynamic levels using ATR
    if verdict in ["STRONG BUY", "BUY"]:
        # Long position
        entry = current_price
        # Conservative target: 1.5 ATR, Aggressive: 3 ATR
        target_conservative = current_price + (atr * 1.5)
        target_moderate = current_price + (atr * 2.5)
        target_aggressive = current_price + (atr * 3.5)
        stop_loss = max(current_price - (atr * 1.0), support * 0.998 if support else current_price * 0.97)

        # Cap target at resistance if close
        if resistance and target_conservative > resistance:
            target_conservative = min(target_conservative, resistance * 1.002)

        profit_conservative = (target_conservative - entry) * shares
        profit_moderate = (target_moderate - entry) * shares
        profit_aggressive = (target_aggressive - entry) * shares
        max_loss = (entry - stop_loss) * shares
        direction = "LONG"

    elif verdict in ["STRONG SELL", "SELL"]:
        # Short position
        entry = current_price
        target_conservative = current_price - (atr * 1.5)
        target_moderate = current_price - (atr * 2.5)
        target_aggressive = current_price - (atr * 3.5)
        stop_loss = min(current_price + (atr * 1.0), resistance * 1.002 if resistance else current_price * 1.03)

        if support and target_conservative < support:
            target_conservative = max(target_conservative, support * 0.998)

        profit_conservative = (entry - target_conservative) * shares
        profit_moderate = (entry - target_moderate) * shares
        profit_aggressive = (entry - target_aggressive) * shares
        max_loss = (stop_loss - entry) * shares
        direction = "SHORT"

    else:
        # HOLD — no trade recommended
        return {
            "direction": "NONE",
            "entry": round(current_price, 2),
            "shares": shares,
            "investment": round(actual_investment, 2),
            "stop_loss": 0,
            "scenarios": [],
            "max_loss": 0,
            "max_loss_pct": 0,
            "risk_reward": 0,
            "recommendation": "No trade recommended. Wait for clearer signals."
        }

    # Risk-Reward Ratio
    risk = abs(entry - stop_loss) if abs(entry - stop_loss) > 0 else 0.01
    reward_conservative = abs(target_conservative - entry) if abs(target_conservative - entry) > 0 else 0.01
    risk_reward = round(reward_conservative / risk, 2)

    scenarios = [
        {
            "label": "Conservative",
            "target": round(target_conservative, 2),
            "profit": round(profit_conservative, 2),
            "profit_pct": round((profit_conservative / actual_investment) * 100, 2),
            "color": "#00e676"
        },
        {
            "label": "Moderate",
            "target": round(target_moderate, 2),
            "profit": round(profit_moderate, 2),
            "profit_pct": round((profit_moderate / actual_investment) * 100, 2),
            "color": "#2979ff"
        },
        {
            "label": "Aggressive",
            "target": round(target_aggressive, 2),
            "profit": round(profit_aggressive, 2),
            "profit_pct": round((profit_aggressive / actual_investment) * 100, 2),
            "color": "#ff9100"
        }
    ]

    max_loss_pct = round((max_loss / actual_investment) * 100, 2)

    # Generate recommendation text
    if risk_reward >= 2:
        rec_quality = "Excellent"
    elif risk_reward >= 1.5:
        rec_quality = "Good"
    elif risk_reward >= 1:
        rec_quality = "Fair"
    else:
        rec_quality = "Poor"

    recommendation = (
        f"{rec_quality} trade setup. "
        f"Risk-Reward ratio is {risk_reward}:1. "
        f"{'Enter long' if direction == 'LONG' else 'Enter short'} at ₹{round(entry, 2)} "
        f"with stop-loss at ₹{round(stop_loss, 2)}. "
        f"Conservative target ₹{round(target_conservative, 2)} "
        f"({round((profit_conservative / actual_investment) * 100, 1)}% return). "
        f"Maximum risk: ₹{round(max_loss, 2)} ({abs(max_loss_pct)}%)."
    )

    return {
        "direction": direction,
        "entry": round(entry, 2),
        "shares": shares,
        "investment": round(actual_investment, 2),
        "stop_loss": round(stop_loss, 2),
        "scenarios": scenarios,
        "max_loss": round(max_loss, 2),
        "max_loss_pct": abs(max_loss_pct),
        "risk_reward": risk_reward,
        "recommendation": recommendation
    }


# ─── Main Expert Analysis Function ───────────────────────────────────────────

def safe_float(val, default=0.0):
    if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
        return default
    return float(val)


def run_expert_analysis(ticker, investment_amount=10000):
    """
    Runs the full expert analysis pipeline for a single stock ticker.
    Returns comprehensive analysis with profit/loss projections.
    """
    try:
        # Fetch intraday data (2 days for enough history)
        data = yf.download(ticker, period="5d", interval="5m", progress=False)

        if data.empty:
            return {"error": f"No data available for {ticker}"}

        # Handle multi-level columns
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.droplevel(1)

        close = data['Close'].dropna()
        high = data['High'].dropna()
        low = data['Low'].dropna()
        volume = data['Volume'].dropna()

        if len(close) < 30:
            return {"error": "Insufficient data for analysis"}

        current_price = safe_float(close.iloc[-1])
        prev_close = safe_float(close.iloc[-2]) if len(close) > 1 else current_price
        day_change = round(((current_price - prev_close) / prev_close) * 100, 2)

        # ── Calculate All Indicators ──
        rsi_series = calc_rsi(close)
        rsi_val = safe_float(rsi_series.iloc[-1], 50)

        macd_line, signal_line, histogram = calc_macd(close)
        macd_hist_val = safe_float(histogram.iloc[-1], 0)

        # MACD crossover detection
        macd_cross = 'none'
        if len(macd_line) >= 2 and len(signal_line) >= 2:
            prev_macd = safe_float(macd_line.iloc[-2])
            prev_signal = safe_float(signal_line.iloc[-2])
            curr_macd = safe_float(macd_line.iloc[-1])
            curr_signal = safe_float(signal_line.iloc[-1])
            if prev_macd <= prev_signal and curr_macd > curr_signal:
                macd_cross = 'bullish'
            elif prev_macd >= prev_signal and curr_macd < curr_signal:
                macd_cross = 'bearish'

        # Bollinger Bands
        bb_upper, bb_mid, bb_lower = calc_bollinger(close)
        bb_upper_val = safe_float(bb_upper.iloc[-1], current_price * 1.02)
        bb_lower_val = safe_float(bb_lower.iloc[-1], current_price * 0.98)
        bb_mid_val = safe_float(bb_mid.iloc[-1], current_price)

        bb_range = bb_upper_val - bb_lower_val if bb_upper_val > bb_lower_val else 1
        if current_price < bb_lower_val:
            bb_position = 'below_lower'
        elif current_price > bb_upper_val:
            bb_position = 'above_upper'
        elif current_price < bb_lower_val + bb_range * 0.15:
            bb_position = 'near_lower'
        elif current_price > bb_upper_val - bb_range * 0.15:
            bb_position = 'near_upper'
        else:
            bb_position = 'middle'

        # ATR
        atr_series = calc_atr(high, low, close)
        atr_val = safe_float(atr_series.iloc[-1], current_price * 0.01)

        # VWAP
        try:
            vwap_series = calc_vwap(high, low, close, volume)
            vwap_val = safe_float(vwap_series.iloc[-1], current_price)
            price_vs_vwap = 'above' if current_price > vwap_val * 1.001 else (
                'below' if current_price < vwap_val * 0.999 else 'at')
        except:
            vwap_val = current_price
            price_vs_vwap = 'at'

        # Volume trend
        avg_vol = safe_float(volume.rolling(window=20).mean().iloc[-1], 1)
        curr_vol = safe_float(volume.iloc[-1], 0)
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1

        if vol_ratio > 1.8 and current_price > prev_close:
            vol_trend = 'spike_up'
        elif vol_ratio > 1.8 and current_price < prev_close:
            vol_trend = 'spike_down'
        elif vol_ratio < 0.5:
            vol_trend = 'declining'
        else:
            vol_trend = 'normal'

        # Trend slope (normalized)
        recent_close = close.tail(30)
        x = np.arange(len(recent_close))
        y = recent_close.values
        try:
            slope, _ = np.polyfit(x, y, 1)
            trend_slope = slope / current_price
        except:
            trend_slope = 0

        # SMA 20
        sma_20 = safe_float(close.rolling(window=20).mean().iloc[-1], current_price)
        price_vs_sma20 = 'above' if current_price > sma_20 * 1.001 else (
            'below' if current_price < sma_20 * 0.999 else 'at')

        # Stochastic
        stoch_k, stoch_d = calc_stochastic(high, low, close)
        stoch_k_val = safe_float(stoch_k.iloc[-1], 50)
        stoch_d_val = safe_float(stoch_d.iloc[-1], 50)

        # Support / Resistance
        support, resistance = find_support_resistance(close)
        support = safe_float(support, current_price * 0.97)
        resistance = safe_float(resistance, current_price * 1.03)

        # Day High/Low
        today_data = data.tail(78)  # ~6.5 hours of 5-min candles
        day_high = safe_float(today_data['High'].max(), current_price)
        day_low = safe_float(today_data['Low'].min(), current_price)

        # ── Build Indicator Dictionary ──
        indicators = {
            'rsi': rsi_val,
            'macd_histogram': macd_hist_val,
            'macd_crossover': macd_cross,
            'bb_position': bb_position,
            'price_vs_vwap': price_vs_vwap,
            'volume_trend': vol_trend,
            'trend_slope': trend_slope,
            'stoch_k': stoch_k_val,
            'stoch_d': stoch_d_val,
            'price_vs_sma20': price_vs_sma20,
            'support': support,
            'resistance': resistance,
            'current_price': current_price,
            'atr': atr_val,
        }

        # ── Run Expert Rules ──
        expert_result = evaluate_expert_rules(indicators)

        # ── Calculate Profit/Loss ──
        pl_result = calculate_profit_loss(
            current_price, expert_result['verdict'],
            atr_val, support, resistance, investment_amount
        )

        # ── Build Response ──
        return {
            "symbol": ticker,
            "current_price": round(current_price, 2),
            "day_change": day_change,
            "day_high": round(day_high, 2),
            "day_low": round(day_low, 2),
            "indicators": {
                "rsi": round(rsi_val, 1),
                "macd_histogram": round(macd_hist_val, 4),
                "macd_crossover": macd_cross,
                "bollinger_position": bb_position,
                "bollinger_upper": round(bb_upper_val, 2),
                "bollinger_mid": round(bb_mid_val, 2),
                "bollinger_lower": round(bb_lower_val, 2),
                "atr": round(atr_val, 2),
                "vwap": round(vwap_val, 2),
                "price_vs_vwap": price_vs_vwap,
                "volume_ratio": round(vol_ratio, 2),
                "volume_trend": vol_trend,
                "sma_20": round(sma_20, 2),
                "stochastic_k": round(stoch_k_val, 1),
                "stochastic_d": round(stoch_d_val, 1),
                "support": round(support, 2),
                "resistance": round(resistance, 2),
                "trend_slope": round(trend_slope, 6),
            },
            "expert_verdict": expert_result,
            "profit_loss": pl_result,
        }

    except Exception as e:
        return {"error": f"Analysis failed for {ticker}: {str(e)}"}
