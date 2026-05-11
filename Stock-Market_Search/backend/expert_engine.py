from __future__ import annotations
"""
Hybrid Expert System — Trading Analysis Engine
===============================================
Architecture:
  ┌─────────────────────────────────────────────────────┐
  │   Layer 1: Classical Technical Indicators           │
  │   RSI, MACD, Bollinger, VWAP, ATR, Stochastic...   │
  └─────────────────┬───────────────────────────────────┘
                    │
  ┌─────────────────▼────────────────────────────────────┐
  │   Layer 2a: Rule-Based Expert Engine  (40% weight)  │
  │   Weighted rules → buy_score, sell_score             │
  └─────────────────┬────────────────────────────────────┘
                    │
  ┌─────────────────▼────────────────────────────────────┐
  │   Layer 2b: Hybrid ML Engine          (40% weight)  │
  │   RandomForest + GradientBoosting + Ridge Regression │
  └─────────────────┬────────────────────────────────────┘
                    │
  ┌─────────────────▼────────────────────────────────────┐
  │   Layer 2c: Linear Regression Trend   (20% weight)  │
  │   Slope-based trajectory and trend direction         │
  └─────────────────┬────────────────────────────────────┘
                    │
  ┌─────────────────▼────────────────────────────────────┐
  │   Layer 3: Ensemble Fusion → Final Verdict + P/L     │
  └─────────────────────────────────────────────────────┘
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

try:
    from ml_engine import get_ml_prediction
except ModuleNotFoundError:
    get_ml_prediction = None
from ai_layer import get_ai_signals, build_signals, MetaEnsemble, get_keys_status
from analyzer import predict_trend, calculate_trade_levels


# ─── Layer 1: Technical Indicator Functions ───────────────────────────────────

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))


def calc_macd(series, fast=12, slow=26, signal=9):
    ema_fast   = series.ewm(span=fast,   adjust=False).mean()
    ema_slow   = series.ewm(span=slow,   adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram  = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_bollinger(series, period=20, std_dev=2):
    sma   = series.rolling(window=period).mean()
    std   = series.rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return upper, sma, lower


def calc_atr(high, low, close, period=14):
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low  - close.shift()).abs()
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def calc_vwap(high, low, close, volume):
    typical_price = (high + low + close) / 3
    return (typical_price * volume).cumsum() / (volume.cumsum() + 1e-9)


def find_support_resistance(close, window=20):
    recent       = close.tail(window * 3)
    if len(recent) < window:
        return None, None
    support    = recent.rolling(window=window).min().dropna().iloc[-1]
    resistance = recent.rolling(window=window).max().dropna().iloc[-1]
    return float(support), float(resistance)


def calc_stochastic(high, low, close, k_period=14, d_period=3):
    lowest_low    = low.rolling(window=k_period).min()
    highest_high  = high.rolling(window=k_period).max()
    k = 100 * ((close - lowest_low) / (highest_high - lowest_low + 1e-9))
    d = k.rolling(window=d_period).mean()
    return k, d


def calc_adx(high, low, close, period=14):
    """Average Directional Index — measures trend strength."""
    try:
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs()
        ], axis=1).max(axis=1)

        plus_dm  = high.diff()
        minus_dm = -low.diff()
        plus_dm  = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

        tr14    = tr.ewm(span=period, adjust=False).mean()
        pdm14   = plus_dm.ewm(span=period, adjust=False).mean()
        mdm14   = minus_dm.ewm(span=period, adjust=False).mean()

        pdi = 100 * pdm14 / (tr14 + 1e-9)
        mdi = 100 * mdm14 / (tr14 + 1e-9)
        dx  = 100 * (pdi - mdi).abs() / (pdi + mdi + 1e-9)
        adx = dx.ewm(span=period, adjust=False).mean()

        return float(adx.iloc[-1]), float(pdi.iloc[-1]), float(mdi.iloc[-1])
    except Exception:
        return 25.0, 0.0, 0.0


# ─── Layer 2a: Rule-Based Expert Engine ──────────────────────────────────────

def evaluate_expert_rules(ind: dict) -> dict:
    """
    Fires weighted rules from technical indicators.
    Returns buy_score, sell_score, net_score, confidence, verdict, rules_fired.
    """
    rules_fired  = []
    buy_score    = 0.0
    sell_score   = 0.0
    total_weight = 0.0

    rsi            = ind.get('rsi', 50)
    macd_hist      = ind.get('macd_histogram', 0)
    macd_cross     = ind.get('macd_crossover', 'none')
    bb_position    = ind.get('bb_position', 'middle')
    price_vs_vwap  = ind.get('price_vs_vwap', 'at')
    vol_trend      = ind.get('volume_trend', 'normal')
    trend_slope    = ind.get('trend_slope', 0)
    stoch_k        = ind.get('stoch_k', 50)
    stoch_d        = ind.get('stoch_d', 50)
    current_price  = ind.get('current_price', 0)
    adx            = ind.get('adx', 25)
    pdi            = ind.get('pdi', 0)
    mdi            = ind.get('mdi', 0)

    # ── Rule 1: RSI (weight 20) ──
    w = 20; total_weight += w
    if rsi < 25:
        buy_score += w
        rules_fired.append({"rule": "RSI Extreme Oversold",    "type": "BUY",  "weight": w,
                            "detail": f"RSI={rsi:.1f} < 25 → strong reversal likely"})
    elif rsi < 35:
        buy_score += w * 0.7
        rules_fired.append({"rule": "RSI Oversold",            "type": "BUY",  "weight": int(w*0.7),
                            "detail": f"RSI={rsi:.1f} in oversold zone"})
    elif rsi > 75:
        sell_score += w
        rules_fired.append({"rule": "RSI Extreme Overbought",  "type": "SELL", "weight": w,
                            "detail": f"RSI={rsi:.1f} > 75 → price exhaustion"})
    elif rsi > 65:
        sell_score += w * 0.7
        rules_fired.append({"rule": "RSI Overbought",          "type": "SELL", "weight": int(w*0.7),
                            "detail": f"RSI={rsi:.1f} in overbought zone"})
    else:
        rules_fired.append({"rule": "RSI Neutral",             "type": "HOLD", "weight": 0,
                            "detail": f"RSI={rsi:.1f} — no directional bias"})

    # ── Rule 2: MACD (weight 22) ──
    w = 22; total_weight += w
    if macd_cross == 'bullish':
        buy_score += w
        rules_fired.append({"rule": "MACD Bullish Crossover",  "type": "BUY",  "weight": w,
                            "detail": "MACD crossed above signal → momentum shifting up"})
    elif macd_cross == 'bearish':
        sell_score += w
        rules_fired.append({"rule": "MACD Bearish Crossover",  "type": "SELL", "weight": w,
                            "detail": "MACD crossed below signal → momentum shifting down"})
    elif macd_hist > 0:
        buy_score += w * 0.4
        rules_fired.append({"rule": "MACD Positive Histogram", "type": "BUY",  "weight": int(w*0.4),
                            "detail": "Histogram positive → bullish momentum"})
    elif macd_hist < 0:
        sell_score += w * 0.4
        rules_fired.append({"rule": "MACD Negative Histogram", "type": "SELL", "weight": int(w*0.4),
                            "detail": "Histogram negative → bearish momentum"})

    # ── Rule 3: Bollinger Bands (weight 14) ──
    w = 14; total_weight += w
    if bb_position == 'below_lower':
        buy_score += w
        rules_fired.append({"rule": "Price Below Lower BB",    "type": "BUY",  "weight": w,
                            "detail": "Below lower band → mean reversion bounce likely"})
    elif bb_position == 'above_upper':
        sell_score += w
        rules_fired.append({"rule": "Price Above Upper BB",    "type": "SELL", "weight": w,
                            "detail": "Above upper band → overextended, pullback likely"})
    elif bb_position == 'near_lower':
        buy_score += w * 0.5
        rules_fired.append({"rule": "Price Near Lower BB",     "type": "BUY",  "weight": int(w*0.5),
                            "detail": "Approaching lower band"})
    elif bb_position == 'near_upper':
        sell_score += w * 0.5
        rules_fired.append({"rule": "Price Near Upper BB",     "type": "SELL", "weight": int(w*0.5),
                            "detail": "Approaching upper band"})

    # ── Rule 4: VWAP (weight 10) ──
    w = 10; total_weight += w
    if price_vs_vwap == 'above':
        buy_score += w * 0.6
        rules_fired.append({"rule": "Price Above VWAP",        "type": "BUY",  "weight": int(w*0.6),
                            "detail": "Institutional buying pressure above VWAP"})
    elif price_vs_vwap == 'below':
        sell_score += w * 0.6
        rules_fired.append({"rule": "Price Below VWAP",        "type": "SELL", "weight": int(w*0.6),
                            "detail": "Institutional selling pressure below VWAP"})

    # ── Rule 5: Volume (weight 10) ──
    w = 10; total_weight += w
    if vol_trend == 'spike_up':
        buy_score += w * 0.6
        rules_fired.append({"rule": "Volume Spike (Bullish)",  "type": "BUY",  "weight": int(w*0.6),
                            "detail": "Volume surge on up move → strong demand"})
    elif vol_trend == 'spike_down':
        sell_score += w * 0.6
        rules_fired.append({"rule": "Volume Spike (Bearish)",  "type": "SELL", "weight": int(w*0.6),
                            "detail": "Volume surge on down move → panic/distribution"})
    elif vol_trend == 'declining':
        rules_fired.append({"rule": "Declining Volume",        "type": "HOLD", "weight": 0,
                            "detail": "Decreasing volume → trend losing steam"})

    # ── Rule 6: Trend Slope (weight 10) ──
    w = 10; total_weight += w
    if trend_slope > 0.0002:
        buy_score += w
        rules_fired.append({"rule": "Strong Uptrend",          "type": "BUY",  "weight": w,
                            "detail": f"Slope strongly positive ({trend_slope:.6f})"})
    elif trend_slope > 0:
        buy_score += w * 0.4
        rules_fired.append({"rule": "Mild Uptrend",            "type": "BUY",  "weight": int(w*0.4),
                            "detail": "Slope mildly positive"})
    elif trend_slope < -0.0002:
        sell_score += w
        rules_fired.append({"rule": "Strong Downtrend",        "type": "SELL", "weight": w,
                            "detail": f"Slope strongly negative ({trend_slope:.6f})"})
    elif trend_slope < 0:
        sell_score += w * 0.4
        rules_fired.append({"rule": "Mild Downtrend",          "type": "SELL", "weight": int(w*0.4),
                            "detail": "Slope mildly negative"})

    # ── Rule 7: Stochastic (weight 8) ──
    w = 8; total_weight += w
    if stoch_k < 20 and stoch_d < 20:
        buy_score += w
        rules_fired.append({"rule": "Stochastic Oversold",     "type": "BUY",  "weight": w,
                            "detail": f"%K={stoch_k:.1f}, %D={stoch_d:.1f} → oversold"})
    elif stoch_k > 80 and stoch_d > 80:
        sell_score += w
        rules_fired.append({"rule": "Stochastic Overbought",   "type": "SELL", "weight": w,
                            "detail": f"%K={stoch_k:.1f}, %D={stoch_d:.1f} → overbought"})

    # ── Rule 8: ADX / Directional Movement (weight 6) ──
    w = 6; total_weight += w
    if adx > 25:
        if pdi > mdi:
            buy_score += w
            rules_fired.append({"rule": "ADX Strong Uptrend",  "type": "BUY",  "weight": w,
                                "detail": f"ADX={adx:.1f} strong, +DI>{'-DI'} → trend confirmed"})
        else:
            sell_score += w
            rules_fired.append({"rule": "ADX Strong Downtrend","type": "SELL", "weight": w,
                                "detail": f"ADX={adx:.1f} strong, -DI>+DI → downtrend confirmed"})
    else:
        rules_fired.append({"rule": "ADX Weak Trend",          "type": "HOLD", "weight": 0,
                            "detail": f"ADX={adx:.1f} < 25 → ranging/choppy market"})

    # ── Compute Rule-Based Verdict ──
    net   = buy_score - sell_score
    conf  = min(abs(net) / (total_weight + 1e-9) * 100, 100)

    if   net >  20: verdict = "STRONG BUY"
    elif net >   8: verdict = "BUY"
    elif net < -20: verdict = "STRONG SELL"
    elif net <  -8: verdict = "SELL"
    else:           verdict = "HOLD"

    return {
        "verdict":     verdict,
        "confidence":  round(conf, 1),
        "buy_score":   round(buy_score, 1),
        "sell_score":  round(sell_score, 1),
        "net_score":   round(net, 1),
        "rules_fired": rules_fired,
    }


# ─── Layer 2c: Linear Regression Trend ───────────────────────────────────────

def regression_signal(close: pd.Series, window: int = 30) -> dict:
    """Fit a linear regrssion on recent closes → slope-based signal."""
    try:
        recent = close.tail(window).dropna()
        if len(recent) < 5:
            return {"signal": "NEUTRAL", "slope_pct": 0.0, "r2": 0.0}
        x = np.arange(len(recent))
        y = recent.values
        slope, intercept = np.polyfit(x, y, 1)
        predicted        = slope * x + intercept
        ss_res = ((y - predicted) ** 2).sum()
        ss_tot = ((y - y.mean()) ** 2).sum()
        r2     = 1 - ss_res / (ss_tot + 1e-9)
        slope_pct = slope / (recent.mean() + 1e-9) * 100
        sig = "UP" if slope_pct > 0.005 else ("DOWN" if slope_pct < -0.005 else "NEUTRAL")
        return {"signal": sig, "slope_pct": round(slope_pct, 5), "r2": round(r2, 3)}
    except Exception:
        return {"signal": "NEUTRAL", "slope_pct": 0.0, "r2": 0.0}


# ─── Layer 3: Ensemble Fusion ─────────────────────────────────────────────────

def _signal_to_score(sig: str) -> float:
    """Convert any signal string to a scalar in [-1, +1]."""
    s = sig.upper()
    if "STRONG BUY"  in s: return  1.0
    if "BUY"         in s: return  0.65
    if "WEAK BUY"    in s: return  0.35
    if "STRONG SELL" in s: return -1.0
    if "SELL"        in s: return -0.65
    if "WEAK SELL"   in s: return -0.35
    if "UP"          in s: return  0.5
    if "DOWN"        in s: return -0.5
    return 0.0


def ensemble_verdict(rule_result: dict, ml_result: dict | None, reg_result: dict) -> dict:
    """
    Weighted combination:
      Rule Engine  → 40%
      ML Ensemble  → 40%
      Regression   → 20%
    Returns final hybrid verdict + component breakdown.
    """
    rule_score = _signal_to_score(rule_result["verdict"])
    reg_score  = _signal_to_score(reg_result["signal"])

    if ml_result:
        # ML confidence as probability weight
        ml_net_prob = (ml_result["buy_probability"] - ml_result["sell_probability"]) / 100.0
        hybrid_score = rule_score * 0.40 + ml_net_prob * 0.40 + reg_score * 0.20
        ml_available = True
    else:
        hybrid_score = rule_score * 0.65 + reg_score * 0.35
        ml_available = False

    # Final verdict
    if   hybrid_score >  0.55: verdict = "STRONG BUY"
    elif hybrid_score >  0.20: verdict = "BUY"
    elif hybrid_score < -0.55: verdict = "STRONG SELL"
    elif hybrid_score < -0.20: verdict = "SELL"
    else:                      verdict = "HOLD"

    # Confidence: blend rule confidence with ML confidence
    if ml_result and ml_available:
        confidence = round(
            rule_result["confidence"] * 0.45
            + ml_result["confidence"] * 0.45
            + abs(reg_result["slope_pct"]) * 0.10 * 100,
            1
        )
    else:
        confidence = round(rule_result["confidence"] * 0.75 + abs(reg_result.get("slope_pct", 0)) * 25, 1)

    confidence = min(confidence, 100.0)

    return {
        "verdict":       verdict,
        "confidence":    confidence,
        "hybrid_score":  round(hybrid_score, 4),
        "weights_used": {
            "rule_engine":        "40%" if ml_available else "65%",
            "ml_engine":          "40%" if ml_available else "N/A",
            "regression":         "20%" if ml_available else "35%",
        },
        "component_scores": {
            "rule_engine":   round(rule_score, 3),
            "ml_ensemble":   round(ml_net_prob if ml_available else 0.0, 3),
            "regression":    round(reg_score, 3),
        },
        "ml_available": ml_available,
        # pass through sub-results
        "rule_verdict":  rule_result,
        "ml_result":     ml_result,
        "reg_result":    reg_result,
    }


# ─── Profit / Loss Calculator ─────────────────────────────────────────────────

def calculate_profit_loss(current_price, verdict, atr, support, resistance, investment=10000):
    if current_price <= 0 or atr <= 0:
        return None

    shares           = max(1, int(investment / current_price))
    actual_inv       = shares * current_price

    if verdict in ("STRONG BUY", "BUY"):
        entry              = current_price
        tgt_conservative   = current_price + atr * 1.5
        tgt_moderate       = current_price + atr * 2.5
        tgt_aggressive     = current_price + atr * 3.5
        stop_loss          = max(current_price - atr * 1.0, support * 0.998 if support else current_price * 0.97)
        if resistance and tgt_conservative > resistance:
            tgt_conservative = min(tgt_conservative, resistance * 1.002)
        profits = [(tgt_conservative - entry) * shares,
                   (tgt_moderate     - entry) * shares,
                   (tgt_aggressive   - entry) * shares]
        max_loss  = (entry - stop_loss) * shares
        direction = "LONG"
        targets   = [tgt_conservative, tgt_moderate, tgt_aggressive]

    elif verdict in ("STRONG SELL", "SELL"):
        entry              = current_price
        tgt_conservative   = current_price - atr * 1.5
        tgt_moderate       = current_price - atr * 2.5
        tgt_aggressive     = current_price - atr * 3.5
        stop_loss          = min(current_price + atr * 1.0, resistance * 1.002 if resistance else current_price * 1.03)
        if support and tgt_conservative < support:
            tgt_conservative = max(tgt_conservative, support * 0.998)
        profits = [(entry - tgt_conservative) * shares,
                   (entry - tgt_moderate)     * shares,
                   (entry - tgt_aggressive)   * shares]
        max_loss  = (stop_loss - entry) * shares
        direction = "SHORT"
        targets   = [tgt_conservative, tgt_moderate, tgt_aggressive]

    else:
        return {
            "direction": "NONE", "entry": round(current_price, 2),
            "shares": shares, "investment": round(actual_inv, 2),
            "stop_loss": 0, "scenarios": [], "max_loss": 0,
            "max_loss_pct": 0, "risk_reward": 0,
            "recommendation": "No trade — wait for clearer signals.",
        }

    risk   = abs(entry - stop_loss)
    reward = abs(targets[0] - entry)
    rr     = round(reward / (risk + 1e-9), 2)

    labels = ["Conservative", "Moderate", "Aggressive"]
    colors = ["#00e676", "#2979ff", "#ff9100"]
    scenarios = [
        {
            "label":      labels[i],
            "target":     round(targets[i], 2),
            "profit":     round(profits[i], 2),
            "profit_pct": round(profits[i] / actual_inv * 100, 2),
            "color":      colors[i],
        }
        for i in range(3)
    ]

    max_loss_pct = round(max_loss / actual_inv * 100, 2)
    q = "Excellent" if rr >= 2 else ("Good" if rr >= 1.5 else ("Fair" if rr >= 1 else "Poor"))
    rec = (
        f"{q} trade setup. R:R = {rr}:1. "
        f"{'Long' if direction == 'LONG' else 'Short'} at ₹{round(entry, 2)} "
        f"| SL ₹{round(stop_loss, 2)} | Target ₹{round(targets[0], 2)} "
        f"({round(profits[0]/actual_inv*100,1)}% return). Max risk ₹{round(max_loss,2)} ({abs(max_loss_pct)}%)."
    )

    return {
        "direction":   direction, "entry":       round(entry, 2),
        "shares":      shares,    "investment":  round(actual_inv, 2),
        "stop_loss":   round(stop_loss, 2),
        "scenarios":   scenarios, "max_loss":    round(max_loss, 2),
        "max_loss_pct": abs(max_loss_pct),
        "risk_reward": rr,        "recommendation": rec,
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def safe_float(val, default=0.0):
    if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
        return default
    try:
        return float(val)
    except Exception:
        return default


# ─── Main Entry Point ─────────────────────────────────────────────────────────

def run_expert_analysis(ticker: str, investment_amount: float = 10000,
                        preferred_interval: str = "5m") -> dict:
    """
    Full hybrid expert analysis for a single ticker.
    Returns technical indicators, rule verdict, ML prediction, ensemble verdict, P/L.
    """
    try:
        interval_cfg = {
            "1m": ("5d", "1m"),
            "3m": ("5d", "1m"),
            "5m": ("5d", "5m"),
            "15m": ("5d", "15m"),
            "30m": ("1mo", "30m"),
            "1h": ("1mo", "60m"),
            "1d": ("1y", "1d"),
            "10d": ("3mo", "1d"),
        }
        requested_interval = preferred_interval if preferred_interval in interval_cfg else "5m"
        period, yf_interval = interval_cfg[requested_interval]

        # ── Fetch data at the requested analysis interval ──
        data = yf.download(ticker, period=period, interval=yf_interval,
                           progress=False, auto_adjust=True)
        if data.empty:
            data = yf.Ticker(ticker).history(period=period, interval=yf_interval, auto_adjust=True)
        if data.empty:
            return {"error": f"No data for {ticker}"}

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.droplevel(1)

        if requested_interval == "3m":
            data = data.resample("3min").agg({
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "Volume": "sum",
            }).dropna()
            if data.empty:
                return {"error": f"No 3m data for {ticker}"}

        close  = data['Close'].dropna()
        high   = data['High'].dropna()
        low    = data['Low'].dropna()
        volume = data['Volume'].dropna()

        if len(close) < 30:
            return {"error": "Insufficient data for analysis"}

        # ── Anchor current_price to the freshest available tick ──
        # yf fast_info gives the last traded price with minimal delay
        try:
            tk = yf.Ticker(ticker)
            live_price = (
                getattr(tk.fast_info, 'last_price', None)
                or getattr(tk.fast_info, 'regular_market_price', None)
            )
            if live_price and float(live_price) > 0:
                # Patch the last close candle with the live price so all
                # indicators computed below use the most current price
                close.iloc[-1] = float(live_price)
        except Exception:
            pass  # fall back to last OHLCV candle silently

        current_price = safe_float(close.iloc[-1])
        prev_close    = safe_float(close.iloc[-2]) if len(close) > 1 else current_price
        day_change    = round((current_price - prev_close) / (prev_close + 1e-9) * 100, 2)

        # ── Technical Indicators ──
        rsi_s   = calc_rsi(close);          rsi_val   = safe_float(rsi_s.iloc[-1], 50)
        macd_l, sig_l, hist = calc_macd(close)
        macd_hist_val = safe_float(hist.iloc[-1], 0)

        macd_cross = 'none'
        if len(macd_l) >= 2:
            if safe_float(macd_l.iloc[-2]) <= safe_float(sig_l.iloc[-2]) and \
               safe_float(macd_l.iloc[-1]) >  safe_float(sig_l.iloc[-1]):
                macd_cross = 'bullish'
            elif safe_float(macd_l.iloc[-2]) >= safe_float(sig_l.iloc[-2]) and \
                 safe_float(macd_l.iloc[-1]) <  safe_float(sig_l.iloc[-1]):
                macd_cross = 'bearish'

        bb_up, bb_mid, bb_lo = calc_bollinger(close)
        bb_up_v  = safe_float(bb_up.iloc[-1],  current_price * 1.02)
        bb_lo_v  = safe_float(bb_lo.iloc[-1],  current_price * 0.98)
        bb_mid_v = safe_float(bb_mid.iloc[-1], current_price)
        bb_range = bb_up_v - bb_lo_v if bb_up_v > bb_lo_v else 1
        if   current_price < bb_lo_v:                       bb_pos = 'below_lower'
        elif current_price > bb_up_v:                       bb_pos = 'above_upper'
        elif current_price < bb_lo_v + bb_range * 0.15:     bb_pos = 'near_lower'
        elif current_price > bb_up_v - bb_range * 0.15:     bb_pos = 'near_upper'
        else:                                               bb_pos = 'middle'

        atr_s   = calc_atr(high, low, close); atr_val = safe_float(atr_s.iloc[-1], current_price * 0.01)
        vwap_v  = safe_float(calc_vwap(high, low, close, volume).iloc[-1], current_price)
        pvwap   = 'above' if current_price > vwap_v * 1.001 else ('below' if current_price < vwap_v * 0.999 else 'at')

        avg_vol   = safe_float(volume.rolling(20).mean().iloc[-1], 1)
        curr_vol  = safe_float(volume.iloc[-1], 0)
        vol_ratio = curr_vol / (avg_vol + 1e-9)
        if   vol_ratio > 1.8 and current_price > prev_close: vol_trend = 'spike_up'
        elif vol_ratio > 1.8 and current_price < prev_close: vol_trend = 'spike_down'
        elif vol_ratio < 0.5:                                 vol_trend = 'declining'
        else:                                                 vol_trend = 'normal'

        # SMA 20 & trend slope
        sma_20     = safe_float(close.rolling(20).mean().iloc[-1], current_price)
        pvssma20   = 'above' if current_price > sma_20 * 1.001 else ('below' if current_price < sma_20 * 0.999 else 'at')
        recent30   = close.tail(30)
        try:
            slope, _  = np.polyfit(np.arange(len(recent30)), recent30.values, 1)
            trend_slope = slope / (current_price + 1e-9)
        except Exception:
            trend_slope = 0.0

        # Stochastic
        stk, std_ = calc_stochastic(high, low, close)
        stk_v = safe_float(stk.iloc[-1], 50); std_v = safe_float(std_.iloc[-1], 50)

        # ADX
        adx_v, pdi_v, mdi_v = calc_adx(high, low, close)

        # Support / Resistance
        support, resistance = find_support_resistance(close)
        support    = safe_float(support,    current_price * 0.97)
        resistance = safe_float(resistance, current_price * 1.03)

        # Day high / low (last ~78 candles = 6.5 hours of 5-min)
        today = data.tail(78)
        day_high = safe_float(today['High'].max(), current_price)
        day_low  = safe_float(today['Low'].min(),  current_price)

        # ── Layer 2a: Rule Engine ──
        indicators_dict = {
            'rsi': rsi_val, 'macd_histogram': macd_hist_val,
            'macd_crossover': macd_cross, 'bb_position': bb_pos,
            'price_vs_vwap': pvwap, 'volume_trend': vol_trend,
            'trend_slope': trend_slope, 'stoch_k': stk_v, 'stoch_d': std_v,
            'current_price': current_price, 'adx': adx_v, 'pdi': pdi_v, 'mdi': mdi_v,
        }
        rule_result = evaluate_expert_rules(indicators_dict)

        # ── Layer 2b: ML Engine ──
        ml_result = None
        if get_ml_prediction:
            try:
                ml_result = get_ml_prediction(ticker, data)
            except Exception as me:
                print(f"⚠️  ML skipped for {ticker}: {me}")

        # ── Layer 2c: Linear Regression Trend ──
        reg_result = regression_signal(close, window=30)

        # ── Layer 3: Ensemble Fusion ──
        hybrid = ensemble_verdict(rule_result, ml_result, reg_result)

        # ── Profit / Loss ──
        pl = calculate_profit_loss(
            current_price, hybrid["verdict"],
            atr_val, support, resistance, investment_amount
        )

        # ── Intraday Timing ──
        timing = get_intraday_timing(
            close, current_price, hybrid["verdict"], atr_val, support, resistance
        )

        # ── Meta-Ensemble (all 7 models incl. Claude + Groq) ──
        ai_ctx = {
            "symbol": ticker, "price": current_price,
            "day_change": day_change, "rsi": round(rsi_val,1),
            "macd_hist": round(macd_hist_val,4), "bb_pos": bb_pos,
            "vwap_pos": pvwap, "vol_trend": vol_trend, "adx": round(adx_v,1),
            "stoch_k": round(stk_v,1), "trend_slope": round(trend_slope,6),
            "support": round(support,2), "resistance": round(resistance,2),
            "rf_signal":    (ml_result or {}).get("model_signals",{}).get("random_forest","—"),
            "gb_signal":    (ml_result or {}).get("model_signals",{}).get("gradient_boosting","—"),
            "rule_verdict": rule_result.get("verdict","—"),
            "reg_signal":   reg_result.get("signal","—"),
        }
        base_signals = build_signals(rule_result, ml_result, reg_result)
        claude_sig, groq_sig = get_ai_signals(ai_ctx)
        all_signals = base_signals + [claude_sig, groq_sig]
        meta = MetaEnsemble().fuse(all_signals)

        # ── Multi-Timeframe Quick Analysis (for UI cards) ──
        timeframes = {
            "1m": 1, "2m": 2, "3m": 3, "4m": 4, "5m": 5,
            "1h": 60, "2h": 120, "3h": 180, "4h": 240, "5h": 300
        }
        time_predictions = {}
        trades = {}
        
        # Base volatility for scaling projections
        recent_closes = close.tail(10)
        base_vol = recent_closes.std() if len(recent_closes) > 1 else (current_price * 0.001)
        if base_vol == 0 or np.isnan(base_vol):
            base_vol = current_price * 0.0005

        for label, mins in timeframes.items():
            t_trend = predict_trend(close, mins)
            time_predictions[label] = t_trend
            
            scaled_vol = base_vol * np.sqrt(mins)
            trades[label] = calculate_trade_levels(current_price, scaled_vol, t_trend)

        # ── Assemble Response ──
        return {
            "symbol":        ticker,
            "requested_interval": requested_interval,
            "primary_interval": requested_interval,
            "last_updated": datetime.now().isoformat(timespec="seconds"),
            "current_price": round(current_price, 2),
            "day_change":    day_change,
            "day_high":      round(day_high, 2),
            "day_low":       round(day_low, 2),
            "indicators": {
                "rsi":                  round(rsi_val, 1),
                "macd_histogram":       round(macd_hist_val, 4),
                "macd_crossover":       macd_cross,
                "bollinger_position":   bb_pos,
                "bollinger_upper":      round(bb_up_v, 2),
                "bollinger_mid":        round(bb_mid_v, 2),
                "bollinger_lower":      round(bb_lo_v, 2),
                "atr":                  round(atr_val, 2),
                "vwap":                 round(vwap_v, 2),
                "price_vs_vwap":        pvwap,
                "volume_ratio":         round(vol_ratio, 2),
                "volume_trend":         vol_trend,
                "sma_20":               round(sma_20, 2),
                "stochastic_k":         round(stk_v, 1),
                "stochastic_d":         round(std_v, 1),
                "support":              round(support, 2),
                "resistance":           round(resistance, 2),
                "trend_slope":          round(trend_slope, 6),
                "adx":                  round(adx_v, 1),
                "pdi":                  round(pdi_v, 1),
                "mdi":                  round(mdi_v, 1),
            },
            "expert_verdict":  rule_result,
            "ml_analysis":     ml_result,
            "regression":      reg_result,
            "hybrid_verdict":  hybrid,
            "profit_loss":     pl,
            "intraday_timing": timing,
            "meta_ensemble":   meta,
            "time_predictions": time_predictions,
            "trades":           trades,
        }

    except Exception as exc:
        import traceback
        traceback.print_exc()
        return {"error": f"Analysis failed for {ticker}: {str(exc)}"}




# ─── Intraday Timing Intelligence ────────────────────────────────────────────

def get_intraday_timing(close: pd.Series, current_price: float,
                        verdict: str, atr: float,
                        support: float, resistance: float) -> dict:
    """
    Returns specific intraday buy/sell timing guidance for NSE market hours.
    Analyses current session, recommends entry window, exit deadline,
    stop-loss level, and projected price milestones for each hour.
    Uses only stdlib datetime (no pytz required).
    """
    from datetime import datetime, timezone, timedelta

    IST = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(IST)

    MARKET_OPEN  = 9  * 60 + 15   # 9:15 AM
    MARKET_CLOSE = 15 * 60 + 30   # 3:30 PM
    curr_mins = now.hour * 60 + now.minute
    is_open   = MARKET_OPEN <= curr_mins <= MARKET_CLOSE
    remaining = max(0, MARKET_CLOSE - curr_mins)

    # ── Session identification ──
    SESSIONS = [
        ("Opening Bell",       9*60+15,  10*60,    "High volatility. Best timing for momentum entries.",  "#ff9100"),
        ("Mid-Morning",        10*60,    11*60+30, "Trend confirming. Lower risk entry window.",          "#00e676"),
        ("Pre-Lunch",          11*60+30, 12*60+30, "Choppy and sideways. Reduce new exposure.",           "#ffd600"),
        ("Lunch Hour",         12*60+30, 13*60+30, "Low volume drift. Avoid opening fresh positions.",    "#8b949e"),
        ("Afternoon Session",  13*60+30, 14*60+30, "Second momentum wave. Good for trend continuation.", "#00e676"),
        ("Power Hour",         14*60+30, 15*60+30, "High volume. Best for exits, avoid new entries.",    "#ff9100"),
    ]
    session = {"name": "Pre-Market" if curr_mins < MARKET_OPEN else "After Hours",
               "tip":  "Wait for 9:15 AM market open." if curr_mins < MARKET_OPEN else "Market closed. Plan trades for tomorrow.",
               "color": "#8b949e"}
    for sname, ss, se, stip, scol in SESSIONS:
        if ss <= curr_mins < se:
            session = {"name": sname, "tip": stip, "color": scol}
            break

    # ── Defaults ──
    action   = "WAIT"
    urgency  = "LOW"
    entry_time = now.strftime("%I:%M %p")
    entry_window = "—"
    exit_time    = "—"
    strategy_note = "No strong signal. Wait for confirmation or next session."
    stop   = round(current_price - atr, 2)
    tgt    = current_price
    tgt_c  = current_price

    t = curr_mins  # shorthand

    if verdict in ("STRONG BUY", "BUY", "WEAK BUY"):
        action = "BUY"
        stop  = round(max(current_price - atr * 1.0, support * 0.998), 2)
        tgt   = round(current_price + atr * 2.5, 2)
        tgt_c = round(current_price + atr * 1.2, 2)

        if not is_open:
            entry_time = "09:15 AM"; exit_time = "01:00 PM"; urgency = "LOW"
            strategy_note = "Set a buy limit order at current price for tomorrow's open. Book 50 % at 1:00 PM, rest by 2:30 PM."
        elif t < 9*60+45:
            entry_window = "NOW → 09:45 AM"; exit_time = "11:30 AM"; urgency = "HIGH"
            strategy_note = "⚡ Opening momentum play — enter immediately. Book 50 % profits at 11:30 AM, remaining by 1:00 PM. Put hard stop at SL."
        elif t < 10*60+30:
            entry_window = "NOW → 10:30 AM"; exit_time = "01:00 PM"; urgency = "MEDIUM"
            strategy_note = "Mid-morning pullback entry. Buy on any minor dip. Target 1:00 PM exit. Reduce size if no breakout by 10:30."
        elif t < 11*60+30:
            entry_window = "NOW → 11:30 AM"; exit_time = "02:00 PM"; urgency = "MEDIUM"
            strategy_note = "Later entry — cut position size by 30 %. Target 2:00 PM exit. Tighten stop-loss."
        elif t < 13*60+30:
            action = "WAIT"; urgency = "LOW"
            strategy_note = "Lunch lull — choppy sideways action. Avoid new entries. Resume watch at 1:30 PM for afternoon session."
        elif t < 14*60+30:
            entry_window = "NOW → 02:30 PM"; exit_time = "03:20 PM"; urgency = "HIGH"
            strategy_note = "⚡ Afternoon momentum window — tight stop, must exit before 3:20 PM. Use trailing SL."
        else:
            action = "WAIT"; urgency = "LOW"
            strategy_note = "Power hour — avoid new long entries. Only manage existing positions with trailing stop."

    elif verdict in ("STRONG SELL", "SELL", "WEAK SELL"):
        action = "SELL"
        stop  = round(min(current_price + atr * 1.0, resistance * 1.002), 2)
        tgt   = round(current_price - atr * 2.5, 2)
        tgt_c = round(current_price - atr * 1.2, 2)

        if not is_open:
            entry_time = "09:20 AM"; exit_time = "01:00 PM"; urgency = "LOW"
            strategy_note = "Plan short for tomorrow. Sell on first opening rally. Cover all shorts by 1:00 PM."
        elif t < 10*60:
            entry_window = "NOW — sell into rally"; exit_time = "01:00 PM"; urgency = "HIGH"
            strategy_note = "⚡ Fade the morning rally. Sell into any brief bounce. Cover shorts by 1:00 PM."
        elif t < 13*60+30:
            entry_window = "NOW → next bounce"; exit_time = "03:00 PM"; urgency = "MEDIUM"
            strategy_note = "Sell on counter-rally. Use trailing stop. Cover all shorts before 3:00 PM."
        else:
            entry_window = "NOW"; exit_time = "03:15 PM"; urgency = "HIGH"
            strategy_note = "⚠️ Late-day selling — urgent. Cover ALL shorts before 3:15 PM. Settlement risk increases at close."

    # ── Price Milestones ──
    dir_mult       = 1 if action == "BUY" else (-1 if action == "SELL" else 0)
    price_velocity = (atr * 1.5) / (6.5 * 60)   # price move per minute over full session

    # Use recent slope from close for more accuracy
    if len(close) >= 10:
        recent = close.tail(30).dropna()
        if len(recent) >= 2:
            x = np.arange(len(recent))
            try:
                slope, _ = np.polyfit(x, recent.values, 1)
                slope_velocity = abs(slope)
                price_velocity = max(price_velocity, slope_velocity)
            except Exception:
                pass

    KEY_TIMES = [
        ("09:15", 9*60+15), ("09:45", 9*60+45), ("10:30", 10*60+30),
        ("11:30", 11*60+30), ("12:30", 12*60+30), ("13:30", 13*60+30),
        ("14:30", 14*60+30), ("15:20", 15*60+20),
    ]
    milestones = []
    for t_str, t_mins in KEY_TIMES:
        diff  = t_mins - curr_mins
        price = round(current_price + dir_mult * price_velocity * diff, 2)
        milestones.append({
            "time":            t_str,
            "projected_price": price,
            "is_past":         t_mins < curr_mins,
        })

    return {
        "current_time":        now.strftime("%I:%M %p"),
        "current_session":     session,
        "time_remaining_mins": remaining,
        "market_status":       "OPEN" if is_open else "CLOSED",
        "action":              action,
        "urgency":             urgency,
        "entry": {
            "time":   entry_time,
            "price":  round(current_price, 2),
            "window": entry_window,
        },
        "exit": {
            "time":                exit_time,
            "price_target":        round(tgt, 2),
            "price_conservative":  round(tgt_c, 2),
        },
        "stop_loss_price": stop,
        "strategy_note":   strategy_note,
        "milestones":      milestones,
    }
