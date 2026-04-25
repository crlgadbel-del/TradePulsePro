"""
Technical Analysis Engine - Computes 20+ technical indicators
"""
import pandas as pd
import numpy as np
import ta
import math
import warnings
from config import INDICATOR_PARAMS as IP
import logging

warnings.filterwarnings('ignore', category=FutureWarning)
logger = logging.getLogger(__name__)


def _project_pivot_line(values, pivot_mask):
    """Project a line from the last two confirmed pivots at every candle."""
    arr = values.to_numpy(dtype=float)
    pivots = np.flatnonzero(pivot_mask.fillna(False).to_numpy())
    projected = np.full(len(values), np.nan)
    cursor = 0
    last_pivots = []

    for i in range(len(values)):
        while cursor < len(pivots) and pivots[cursor] < i:
            last_pivots.append(pivots[cursor])
            cursor += 1
        if len(last_pivots) >= 2:
            p1, p2 = last_pivots[-2], last_pivots[-1]
            if p2 != p1:
                slope = (arr[p2] - arr[p1]) / (p2 - p1)
                projected[i] = arr[p2] + slope * (i - p2)

    return pd.Series(projected, index=values.index)


def detect_advanced_patterns(df):
    """Detect complex candlestick and chart patterns"""
    df = df.copy()
    
    # Core price logic
    open_p = df['Open']
    close_p = df['Close']
    high_p = df['High']
    low_p = df['Low']
    
    body = abs(close_p - open_p)
    candle_range = high_p - low_p
    upper_shadow = high_p - df[['Open', 'Close']].max(axis=1)
    lower_shadow = df[['Open', 'Close']].min(axis=1) - low_p
    
    # 1. Hammer Pattern
    # Small body, long lower shadow (>= 2x body), very small upper shadow
    df['Pattern_Hammer'] = (
        (lower_shadow >= (2 * body)) & 
        (upper_shadow <= (0.1 * candle_range)) & 
        (candle_range > 0) & 
        (body > 0)
    )
    
    # 2. Three Black Crows Pattern
    # Three consecutive long red candles with lower closes
    is_red = close_p < open_p
    df['Pattern_3BlackCrows'] = (
        is_red & is_red.shift(1) & is_red.shift(2) & 
        (close_p < close_p.shift(1)) & 
        (close_p.shift(1) < close_p.shift(2)) &
        (open_p < open_p.shift(1)) & (open_p > close_p.shift(1)) & # Opens within previous body
        (open_p.shift(1) < open_p.shift(2)) & (open_p.shift(1) > close_p.shift(2))
    )
    
    # 3. Support & Resistance (using rolling windows to find local min/max)
    window = 14
    df['Support_Level'] = df['Low'].rolling(window=window, center=True).min()
    df['Resistance_Level'] = df['High'].rolling(window=window, center=True).max()
    
    # Forward fill to make it a distinct step-line instead of NaN holes
    df['Support_Level'] = df['Support_Level'].ffill()
    df['Resistance_Level'] = df['Resistance_Level'].ffill()
    
    # 4. Head and Shoulders (Simplified top detecting)
    # We look for 3 peaks where middle is highest. Using 20-period rolling max to find peaks.
    # To do this correctly in a pandas vectorized way is complex, so we'll do a basic rolling window check
    peak = high_p.rolling(5, center=True).max() == high_p
    peaks = df[peak]['High']
    df['Pattern_H_and_S'] = False
    
    # 5. Triangle Breakout
    # Checking for converging highs and lows (Volatility contraction) followed by a strong breakout
    atr = df['High'] - df['Low']
    atr_sma = atr.rolling(14).mean()
    volatility_contraction = (atr < atr_sma) & (atr.shift(1) < atr_sma.shift(1)) & (atr.shift(2) < atr_sma.shift(2))
    breakout_up = (close_p > df['Resistance_Level'].shift(1)) & (close_p > open_p) & (df['Volume'] > df['Volume'].rolling(20).mean())
    breakout_down = (close_p < df['Support_Level'].shift(1)) & (close_p < open_p) & (df['Volume'] > df['Volume'].rolling(20).mean())
    
    df['Pattern_Triangle_Breakout_Up'] = volatility_contraction.shift(1) & breakout_up
    df['Pattern_Triangle_Breakout_Down'] = volatility_contraction.shift(1) & breakout_down

    # 6. PDF-informed trend-line logic: at least two pivots create a line,
    # the third test validates it, and a volume breakout suggests trend change.
    pivot_window = 5
    pivot_high = high_p.eq(high_p.rolling(pivot_window * 2 + 1, center=True).max())
    pivot_low = low_p.eq(low_p.rolling(pivot_window * 2 + 1, center=True).min())
    df['Trend_Support'] = _project_pivot_line(low_p, pivot_low)
    df['Trend_Resistance'] = _project_pivot_line(high_p, pivot_high)

    avg_range = candle_range.rolling(14).mean().replace(0, np.nan)
    trend_tolerance = avg_range.fillna(candle_range.expanding().mean()) * 0.35
    vol_sma = df['Volume'].rolling(20).mean()
    volume_confirm = df['Volume'] > (vol_sma * 1.15)

    support_test = (
        df['Trend_Support'].notna() &
        ((low_p - df['Trend_Support']).abs() <= trend_tolerance) &
        (close_p > open_p)
    )
    resistance_test = (
        df['Trend_Resistance'].notna() &
        ((high_p - df['Trend_Resistance']).abs() <= trend_tolerance) &
        (close_p < open_p)
    )

    df['Pattern_Trendline_Support_Test'] = support_test
    df['Pattern_Trendline_Resistance_Test'] = resistance_test
    df['Pattern_Trendline_Breakout_Up'] = (
        df['Trend_Resistance'].notna() &
        (close_p > df['Trend_Resistance'] + trend_tolerance) &
        (close_p.shift(1) <= df['Trend_Resistance'].shift(1) + trend_tolerance.shift(1)) &
        volume_confirm
    )
    df['Pattern_Trendline_Breakout_Down'] = (
        df['Trend_Support'].notna() &
        (close_p < df['Trend_Support'] - trend_tolerance) &
        (close_p.shift(1) >= df['Trend_Support'].shift(1) - trend_tolerance.shift(1)) &
        volume_confirm
    )

    # 7. Fibonacci retracement zones from the latest rolling swing.
    fib_window = min(60, max(20, len(df) // 2))
    swing_high = high_p.rolling(fib_window).max()
    swing_low = low_p.rolling(fib_window).min()
    swing_range = (swing_high - swing_low).replace(0, np.nan)
    high_pos = high_p.rolling(fib_window).apply(np.argmax, raw=True)
    low_pos = low_p.rolling(fib_window).apply(np.argmin, raw=True)
    swing_up = high_pos > low_pos

    df['Fib_382'] = np.where(swing_up, swing_high - swing_range * 0.382, swing_low + swing_range * 0.382)
    df['Fib_500'] = np.where(swing_up, swing_high - swing_range * 0.500, swing_low + swing_range * 0.500)
    df['Fib_618'] = np.where(swing_up, swing_high - swing_range * 0.618, swing_low + swing_range * 0.618)
    fib_tol = avg_range.fillna(candle_range.expanding().mean()) * 0.45
    near_fib = (
        (close_p - df['Fib_382']).abs().le(fib_tol) |
        (close_p - df['Fib_500']).abs().le(fib_tol) |
        (close_p - df['Fib_618']).abs().le(fib_tol)
    )
    df['Pattern_Fib_Bounce_Buy'] = near_fib & swing_up & (close_p > open_p) & (close_p > close_p.shift(1))
    df['Pattern_Fib_Rejection_Sell'] = near_fib & (~swing_up) & (close_p < open_p) & (close_p < close_p.shift(1))
    df['Pattern_Fib_Extension_Up'] = swing_up & (close_p > swing_high.shift(1)) & volume_confirm
    df['Pattern_Fib_Extension_Down'] = (~swing_up) & (close_p < swing_low.shift(1)) & volume_confirm

    # 8. Classical reversal patterns from repeated peaks/troughs.
    prior_high = high_p.rolling(20).max().shift(15)
    recent_high = high_p.rolling(20).max()
    prior_low = low_p.rolling(20).min().shift(15)
    recent_low = low_p.rolling(20).min()
    df['Pattern_Double_Top'] = (
        prior_high.notna() &
        ((recent_high - prior_high).abs() / prior_high <= 0.012) &
        (close_p < low_p.rolling(10).min().shift(1)) &
        volume_confirm
    )
    df['Pattern_Double_Bottom'] = (
        prior_low.notna() &
        ((recent_low - prior_low).abs() / prior_low <= 0.012) &
        (close_p > high_p.rolling(10).max().shift(1)) &
        volume_confirm
    )
    
    return df


def compute_all_indicators(df):
    """Compute all technical indicators on the dataframe"""
    if df is None or df.empty or len(df) < 30:
        return None
    
    df = df.copy()
    
    try:
        # ============================================
        # TREND INDICATORS
        # ============================================
        
        # Simple Moving Averages
        df['SMA_9'] = ta.trend.sma_indicator(df['Close'], window=IP['sma_short'])
        df['SMA_21'] = ta.trend.sma_indicator(df['Close'], window=IP['sma_medium'])
        df['SMA_50'] = ta.trend.sma_indicator(df['Close'], window=min(IP['sma_long'], len(df)-1))
        
        # Exponential Moving Averages
        df['EMA_9'] = ta.trend.ema_indicator(df['Close'], window=IP['ema_short'])
        df['EMA_21'] = ta.trend.ema_indicator(df['Close'], window=IP['ema_medium'])
        df['EMA_50'] = ta.trend.ema_indicator(df['Close'], window=min(IP['ema_long'], len(df)-1))
        
        # MACD
        macd = ta.trend.MACD(df['Close'], 
                             window_slow=IP['macd_slow'], 
                             window_fast=IP['macd_fast'], 
                             window_sign=IP['macd_signal'])
        df['MACD'] = macd.macd()
        df['MACD_Signal'] = macd.macd_signal()
        df['MACD_Histogram'] = macd.macd_diff()
        
        # ADX (Average Directional Index)
        adx = ta.trend.ADXIndicator(df['High'], df['Low'], df['Close'], 
                                     window=IP['adx_period'])
        df['ADX'] = adx.adx()
        df['ADX_Pos'] = adx.adx_pos()
        df['ADX_Neg'] = adx.adx_neg()
        
        # Ichimoku Cloud
        ichimoku = ta.trend.IchimokuIndicator(
            df['High'], df['Low'],
            window1=IP['ichimoku_tenkan'],
            window2=IP['ichimoku_kijun'],
            window3=IP['ichimoku_senkou']
        )
        df['Ichimoku_Tenkan'] = ichimoku.ichimoku_conversion_line()
        df['Ichimoku_Kijun'] = ichimoku.ichimoku_base_line()
        df['Ichimoku_A'] = ichimoku.ichimoku_a()
        df['Ichimoku_B'] = ichimoku.ichimoku_b()
        
        # Parabolic SAR
        psar = ta.trend.PSARIndicator(df['High'], df['Low'], df['Close'])
        df['PSAR'] = psar.psar()
        df['PSAR_Up'] = psar.psar_up()
        df['PSAR_Down'] = psar.psar_down()
        
        # ============================================
        # MOMENTUM INDICATORS
        # ============================================
        
        # RSI (Relative Strength Index)
        df['RSI'] = ta.momentum.rsi(df['Close'], window=IP['rsi_period'])
        
        # Stochastic Oscillator
        stoch = ta.momentum.StochasticOscillator(
            df['High'], df['Low'], df['Close'],
            window=IP['stoch_k'], smooth_window=IP['stoch_d']
        )
        df['Stoch_K'] = stoch.stoch()
        df['Stoch_D'] = stoch.stoch_signal()
        
        # CCI (Commodity Channel Index)
        df['CCI'] = ta.trend.cci(df['High'], df['Low'], df['Close'], 
                                  window=IP['cci_period'])
        
        # Williams %R
        df['Williams_R'] = ta.momentum.williams_r(
            df['High'], df['Low'], df['Close'], 
            lbp=IP['williams_period']
        )
        
        # ROC (Rate of Change)
        df['ROC'] = ta.momentum.roc(df['Close'], window=12)
        
        # Awesome Oscillator
        df['AO'] = ta.momentum.awesome_oscillator(df['High'], df['Low'])
        
        # ============================================
        # VOLATILITY INDICATORS
        # ============================================
        
        # Bollinger Bands
        bb = ta.volatility.BollingerBands(df['Close'], 
                                           window=IP['bb_period'], 
                                           window_dev=IP['bb_std'])
        df['BB_Upper'] = bb.bollinger_hband()
        df['BB_Middle'] = bb.bollinger_mavg()
        df['BB_Lower'] = bb.bollinger_lband()
        df['BB_Width'] = bb.bollinger_wband()
        df['BB_Pct'] = bb.bollinger_pband()
        
        # ATR (Average True Range)
        df['ATR'] = ta.volatility.average_true_range(
            df['High'], df['Low'], df['Close'], 
            window=IP['atr_period']
        )
        
        # Keltner Channels
        kc = ta.volatility.KeltnerChannel(df['High'], df['Low'], df['Close'])
        df['KC_Upper'] = kc.keltner_channel_hband()
        df['KC_Middle'] = kc.keltner_channel_mband()
        df['KC_Lower'] = kc.keltner_channel_lband()
        
        # ============================================
        # VOLUME INDICATORS
        # ============================================
        
        # On-Balance Volume
        df['OBV'] = ta.volume.on_balance_volume(df['Close'], df['Volume'])
        df['OBV_SMA'] = df['OBV'].rolling(window=IP['obv_sma_period']).mean()
        
        # Money Flow Index
        df['MFI'] = ta.volume.money_flow_index(
            df['High'], df['Low'], df['Close'], df['Volume'],
            window=IP['mfi_period']
        )
        
        # Accumulation/Distribution
        df['AD'] = ta.volume.acc_dist_index(df['High'], df['Low'], df['Close'], df['Volume'])
        
        # Chaikin Money Flow
        df['CMF'] = ta.volume.chaikin_money_flow(
            df['High'], df['Low'], df['Close'], df['Volume']
        )
        
        # VWAP (Volume Weighted Average Price)
        df['VWAP'] = (df['Volume'] * (df['High'] + df['Low'] + df['Close']) / 3).cumsum() / df['Volume'].cumsum()
        
        # Volume SMA
        df['Volume_SMA'] = df['Volume'].rolling(window=20).mean()
        df['Volume_Ratio'] = df['Volume'] / df['Volume_SMA']
        
        # ============================================
        # SUPPORT & RESISTANCE
        # ============================================
        
        # Pivot Points
        df['Pivot'] = (df['High'].shift(1) + df['Low'].shift(1) + df['Close'].shift(1)) / 3
        df['R1'] = 2 * df['Pivot'] - df['Low'].shift(1)
        df['S1'] = 2 * df['Pivot'] - df['High'].shift(1)
        df['R2'] = df['Pivot'] + (df['High'].shift(1) - df['Low'].shift(1))
        df['S2'] = df['Pivot'] - (df['High'].shift(1) - df['Low'].shift(1))
        
        # ---------------- ADVANCED PATTERNS ----------------
        df = detect_advanced_patterns(df)
        
        return df
        
    except Exception as e:
        logger.error(f"Error computing indicators: {e}")
        return df


def analyze_indicators(df):
    """Analyze all indicators and return signals"""
    if df is None or df.empty:
        return {'signals': [], 'score': 0, 'total': 0}
    
    signals = []
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    
    # ---- RSI Signal ----
    rsi_val = last.get('RSI', 50)
    if not pd.isna(rsi_val):
        if rsi_val > 65:
            signals.append({'name': 'RSI', 'signal': 'BUY', 'strength': 'strong',
                           'value': f'{rsi_val:.1f}', 'reason': 'Strong bullish momentum (>65)'})
        elif rsi_val > 55:
            signals.append({'name': 'RSI', 'signal': 'BUY', 'strength': 'moderate',
                           'value': f'{rsi_val:.1f}', 'reason': 'Bullish momentum (>55)'})
        elif rsi_val < 35:
            signals.append({'name': 'RSI', 'signal': 'SELL', 'strength': 'strong',
                           'value': f'{rsi_val:.1f}', 'reason': 'Strong bearish momentum (<35)'})
        elif rsi_val < 45:
            signals.append({'name': 'RSI', 'signal': 'SELL', 'strength': 'moderate',
                           'value': f'{rsi_val:.1f}', 'reason': 'Bearish momentum (<45)'})
        else:
            signals.append({'name': 'RSI', 'signal': 'NEUTRAL', 'strength': 'weak',
                           'value': f'{rsi_val:.1f}', 'reason': 'Neutral zone'})
    
    # ---- MACD Signal ----
    macd_val = last.get('MACD', 0)
    macd_sig = last.get('MACD_Signal', 0)
    macd_hist = last.get('MACD_Histogram', 0)
    prev_hist = prev.get('MACD_Histogram', 0)
    if not pd.isna(macd_val) and not pd.isna(macd_sig):
        if macd_val > macd_sig and prev.get('MACD', 0) <= prev.get('MACD_Signal', 0):
            signals.append({'name': 'MACD', 'signal': 'BUY', 'strength': 'strong',
                           'value': f'{macd_val:.4f}', 'reason': 'Bullish crossover'})
        elif macd_val < macd_sig and prev.get('MACD', 0) >= prev.get('MACD_Signal', 0):
            signals.append({'name': 'MACD', 'signal': 'SELL', 'strength': 'strong',
                           'value': f'{macd_val:.4f}', 'reason': 'Bearish crossover'})
        elif macd_val > macd_sig:
            signals.append({'name': 'MACD', 'signal': 'BUY', 'strength': 'moderate',
                           'value': f'{macd_val:.4f}', 'reason': 'MACD above signal line'})
        elif macd_val < macd_sig:
            signals.append({'name': 'MACD', 'signal': 'SELL', 'strength': 'moderate',
                           'value': f'{macd_val:.4f}', 'reason': 'MACD below signal line'})
        else:
            signals.append({'name': 'MACD', 'signal': 'NEUTRAL', 'strength': 'weak',
                           'value': f'{macd_val:.4f}', 'reason': 'No clear signal'})
    
    # ---- Bollinger Bands Signal ----
    close = last.get('Close', 0)
    bb_upper = last.get('BB_Upper', 0)
    bb_lower = last.get('BB_Lower', 0)
    bb_mid = last.get('BB_Middle', 0)
    if not pd.isna(bb_upper) and not pd.isna(bb_lower) and close > 0:
        bb_pct = (close - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5
        if close >= bb_upper:
            signals.append({'name': 'Bollinger Bands', 'signal': 'BUY', 'strength': 'strong',
                           'value': f'{bb_pct:.2f}', 'reason': 'Breakout above upper band'})
        elif close >= bb_upper * 0.99:
            signals.append({'name': 'Bollinger Bands', 'signal': 'BUY', 'strength': 'moderate',
                           'value': f'{bb_pct:.2f}', 'reason': 'Testing upper band (bullish)'})
        elif close <= bb_lower:
            signals.append({'name': 'Bollinger Bands', 'signal': 'SELL', 'strength': 'strong',
                           'value': f'{bb_pct:.2f}', 'reason': 'Breakdown below lower band'})
        elif close <= bb_lower * 1.01:
            signals.append({'name': 'Bollinger Bands', 'signal': 'SELL', 'strength': 'moderate',
                           'value': f'{bb_pct:.2f}', 'reason': 'Testing lower band (bearish)'})
        else:
            signals.append({'name': 'Bollinger Bands', 'signal': 'NEUTRAL', 'strength': 'weak',
                           'value': f'{bb_pct:.2f}', 'reason': 'Price within bands'})
    
    # ---- Moving Average Signal ----
    ema9 = last.get('EMA_9', 0)
    ema21 = last.get('EMA_21', 0)
    sma50 = last.get('SMA_50', 0)
    if not pd.isna(ema9) and not pd.isna(ema21):
        if ema9 > ema21 and close > ema9:
            signals.append({'name': 'Moving Averages', 'signal': 'BUY', 'strength': 'strong',
                           'value': f'EMA9={ema9:.2f}', 'reason': 'Price above rising EMAs'})
        elif ema9 > ema21:
            signals.append({'name': 'Moving Averages', 'signal': 'BUY', 'strength': 'moderate',
                           'value': f'EMA9={ema9:.2f}', 'reason': 'EMA9 above EMA21 (bullish)'})
        elif ema9 < ema21 and close < ema9:
            signals.append({'name': 'Moving Averages', 'signal': 'SELL', 'strength': 'strong',
                           'value': f'EMA9={ema9:.2f}', 'reason': 'Price below falling EMAs'})
        elif ema9 < ema21:
            signals.append({'name': 'Moving Averages', 'signal': 'SELL', 'strength': 'moderate',
                           'value': f'EMA9={ema9:.2f}', 'reason': 'EMA9 below EMA21 (bearish)'})
        else:
            signals.append({'name': 'Moving Averages', 'signal': 'NEUTRAL', 'strength': 'weak',
                           'value': f'EMA9={ema9:.2f}', 'reason': 'EMAs converging'})
    
    # ---- Stochastic Signal ----
    stoch_k = last.get('Stoch_K', 50)
    stoch_d = last.get('Stoch_D', 50)
    if not pd.isna(stoch_k) and not pd.isna(stoch_d):
        if stoch_k > 80 and stoch_k > stoch_d:
            signals.append({'name': 'Stochastic', 'signal': 'BUY', 'strength': 'strong',
                           'value': f'K={stoch_k:.1f}, D={stoch_d:.1f}', 
                           'reason': 'Bullish continuation in uptrend'})
        elif stoch_k > 60:
            signals.append({'name': 'Stochastic', 'signal': 'BUY', 'strength': 'moderate',
                           'value': f'K={stoch_k:.1f}, D={stoch_d:.1f}',
                           'reason': 'Positive momentum'})
        elif stoch_k < 20 and stoch_k < stoch_d:
            signals.append({'name': 'Stochastic', 'signal': 'SELL', 'strength': 'strong',
                           'value': f'K={stoch_k:.1f}, D={stoch_d:.1f}',
                           'reason': 'Bearish continuation in downtrend'})
        elif stoch_k < 40:
            signals.append({'name': 'Stochastic', 'signal': 'SELL', 'strength': 'moderate',
                           'value': f'K={stoch_k:.1f}, D={stoch_d:.1f}',
                           'reason': 'Negative momentum'})
        else:
            signals.append({'name': 'Stochastic', 'signal': 'NEUTRAL', 'strength': 'weak',
                           'value': f'K={stoch_k:.1f}, D={stoch_d:.1f}',
                           'reason': 'Neutral zone'})
    
    # ---- ADX Signal ----
    adx_val = last.get('ADX', 0)
    adx_pos = last.get('ADX_Pos', 0)
    adx_neg = last.get('ADX_Neg', 0)
    if not pd.isna(adx_val):
        if adx_val > 25 and adx_pos > adx_neg:
            signals.append({'name': 'ADX', 'signal': 'BUY', 'strength': 'strong' if adx_val > 40 else 'moderate',
                           'value': f'{adx_val:.1f}', 'reason': f'Strong uptrend (ADX={adx_val:.0f})'})
        elif adx_val > 25 and adx_neg > adx_pos:
            signals.append({'name': 'ADX', 'signal': 'SELL', 'strength': 'strong' if adx_val > 40 else 'moderate',
                           'value': f'{adx_val:.1f}', 'reason': f'Strong downtrend (ADX={adx_val:.0f})'})
        else:
            signals.append({'name': 'ADX', 'signal': 'NEUTRAL', 'strength': 'weak',
                           'value': f'{adx_val:.1f}', 'reason': 'No strong trend'})
    
    # ---- CCI Signal ----
    cci_val = last.get('CCI', 0)
    if not pd.isna(cci_val):
        if cci_val < -100:
            signals.append({'name': 'CCI', 'signal': 'BUY', 'strength': 'strong',
                           'value': f'{cci_val:.1f}', 'reason': 'Oversold (CCI < -100)'})
        elif cci_val < -50:
            signals.append({'name': 'CCI', 'signal': 'BUY', 'strength': 'moderate',
                           'value': f'{cci_val:.1f}', 'reason': 'Approaching oversold'})
        elif cci_val > 100:
            signals.append({'name': 'CCI', 'signal': 'SELL', 'strength': 'strong',
                           'value': f'{cci_val:.1f}', 'reason': 'Overbought (CCI > 100)'})
        elif cci_val > 50:
            signals.append({'name': 'CCI', 'signal': 'SELL', 'strength': 'moderate',
                           'value': f'{cci_val:.1f}', 'reason': 'Approaching overbought'})
        else:
            signals.append({'name': 'CCI', 'signal': 'NEUTRAL', 'strength': 'weak',
                           'value': f'{cci_val:.1f}', 'reason': 'Neutral zone'})
    
    # ---- Williams %R Signal ----
    williams = last.get('Williams_R', -50)
    if not pd.isna(williams):
        if williams < -80:
            signals.append({'name': 'Williams %R', 'signal': 'BUY', 'strength': 'strong',
                           'value': f'{williams:.1f}', 'reason': 'Oversold (< -80)'})
        elif williams > -20:
            signals.append({'name': 'Williams %R', 'signal': 'SELL', 'strength': 'strong',
                           'value': f'{williams:.1f}', 'reason': 'Overbought (> -20)'})
        else:
            signals.append({'name': 'Williams %R', 'signal': 'NEUTRAL', 'strength': 'weak',
                           'value': f'{williams:.1f}', 'reason': 'Neutral zone'})
    
    # ---- MFI Signal ----
    mfi_val = last.get('MFI', 50)
    if not pd.isna(mfi_val):
        if mfi_val < 20:
            signals.append({'name': 'MFI', 'signal': 'BUY', 'strength': 'strong',
                           'value': f'{mfi_val:.1f}', 'reason': 'Oversold money flow'})
        elif mfi_val < 30:
            signals.append({'name': 'MFI', 'signal': 'BUY', 'strength': 'moderate',
                           'value': f'{mfi_val:.1f}', 'reason': 'Low money flow'})
        elif mfi_val > 80:
            signals.append({'name': 'MFI', 'signal': 'SELL', 'strength': 'strong',
                           'value': f'{mfi_val:.1f}', 'reason': 'Overbought money flow'})
        elif mfi_val > 70:
            signals.append({'name': 'MFI', 'signal': 'SELL', 'strength': 'moderate',
                           'value': f'{mfi_val:.1f}', 'reason': 'High money flow'})
        else:
            signals.append({'name': 'MFI', 'signal': 'NEUTRAL', 'strength': 'weak',
                           'value': f'{mfi_val:.1f}', 'reason': 'Normal money flow'})
    
    # ---- OBV Signal ----
    obv = last.get('OBV', 0)
    obv_sma = last.get('OBV_SMA', 0)
    if not pd.isna(obv) and not pd.isna(obv_sma) and obv_sma != 0:
        if obv > obv_sma * 1.05:
            signals.append({'name': 'OBV', 'signal': 'BUY', 'strength': 'moderate',
                           'value': f'{obv:.0f}', 'reason': 'Volume supporting price rise'})
        elif obv < obv_sma * 0.95:
            signals.append({'name': 'OBV', 'signal': 'SELL', 'strength': 'moderate',
                           'value': f'{obv:.0f}', 'reason': 'Volume supporting price decline'})
        else:
            signals.append({'name': 'OBV', 'signal': 'NEUTRAL', 'strength': 'weak',
                           'value': f'{obv:.0f}', 'reason': 'Volume neutral'})
    
    # ---- VWAP Signal ----
    vwap = last.get('VWAP', 0)
    if not pd.isna(vwap) and vwap > 0:
        if close > vwap * 1.005:
            signals.append({'name': 'VWAP', 'signal': 'BUY', 'strength': 'moderate',
                           'value': f'{vwap:.2f}', 'reason': 'Price above VWAP (bullish)'})
        elif close < vwap * 0.995:
            signals.append({'name': 'VWAP', 'signal': 'SELL', 'strength': 'moderate',
                           'value': f'{vwap:.2f}', 'reason': 'Price below VWAP (bearish)'})
        else:
            signals.append({'name': 'VWAP', 'signal': 'NEUTRAL', 'strength': 'weak',
                           'value': f'{vwap:.2f}', 'reason': 'Price near VWAP'})
    
    # ---- Ichimoku Cloud Signal ----
    ich_tenkan = last.get('Ichimoku_Tenkan', 0)
    ich_kijun = last.get('Ichimoku_Kijun', 0)
    ich_a = last.get('Ichimoku_A', 0)
    ich_b = last.get('Ichimoku_B', 0)
    if not pd.isna(ich_tenkan) and not pd.isna(ich_kijun):
        cloud_top = max(ich_a, ich_b) if not (pd.isna(ich_a) or pd.isna(ich_b)) else 0
        cloud_bottom = min(ich_a, ich_b) if not (pd.isna(ich_a) or pd.isna(ich_b)) else 0
        
        if close > cloud_top and ich_tenkan > ich_kijun:
            signals.append({'name': 'Ichimoku', 'signal': 'BUY', 'strength': 'strong',
                           'value': f'Above cloud', 'reason': 'Price above cloud, bullish TK cross'})
        elif close > cloud_top:
            signals.append({'name': 'Ichimoku', 'signal': 'BUY', 'strength': 'moderate',
                           'value': f'Above cloud', 'reason': 'Price above Ichimoku cloud'})
        elif close < cloud_bottom and ich_tenkan < ich_kijun:
            signals.append({'name': 'Ichimoku', 'signal': 'SELL', 'strength': 'strong',
                           'value': f'Below cloud', 'reason': 'Price below cloud, bearish TK cross'})
        elif close < cloud_bottom:
            signals.append({'name': 'Ichimoku', 'signal': 'SELL', 'strength': 'moderate',
                           'value': f'Below cloud', 'reason': 'Price below Ichimoku cloud'})
        else:
            signals.append({'name': 'Ichimoku', 'signal': 'NEUTRAL', 'strength': 'weak',
                           'value': f'In cloud', 'reason': 'Price inside Ichimoku cloud'})
    
    # ---- Parabolic SAR Signal ----
    psar = last.get('PSAR', 0)
    if not pd.isna(psar) and psar > 0:
        if close > psar:
            signals.append({'name': 'Parabolic SAR', 'signal': 'BUY', 'strength': 'moderate',
                           'value': f'{psar:.2f}', 'reason': 'Price above SAR (uptrend)'})
        else:
            signals.append({'name': 'Parabolic SAR', 'signal': 'SELL', 'strength': 'moderate',
                           'value': f'{psar:.2f}', 'reason': 'Price below SAR (downtrend)'})
    
    # ---- CMF Signal ----
    cmf = last.get('CMF', 0)
    if not pd.isna(cmf):
        if cmf > 0.1:
            signals.append({'name': 'CMF', 'signal': 'BUY', 'strength': 'moderate',
                           'value': f'{cmf:.3f}', 'reason': 'Strong buying pressure'})
        elif cmf > 0:
            signals.append({'name': 'CMF', 'signal': 'BUY', 'strength': 'weak',
                           'value': f'{cmf:.3f}', 'reason': 'Mild buying pressure'})
        elif cmf < -0.1:
            signals.append({'name': 'CMF', 'signal': 'SELL', 'strength': 'moderate',
                           'value': f'{cmf:.3f}', 'reason': 'Strong selling pressure'})
        elif cmf < 0:
            signals.append({'name': 'CMF', 'signal': 'SELL', 'strength': 'weak',
                           'value': f'{cmf:.3f}', 'reason': 'Mild selling pressure'})
        else:
            signals.append({'name': 'CMF', 'signal': 'NEUTRAL', 'strength': 'weak',
                           'value': f'{cmf:.3f}', 'reason': 'No money flow direction'})
    
    # ---- Volume Signal ----
    vol_ratio = last.get('Volume_Ratio', 1)
    if not pd.isna(vol_ratio):
        if vol_ratio > 1.5:
            vol_signal = 'BUY' if close > last.get('Open', close) else 'SELL'
            signals.append({'name': 'Volume', 'signal': vol_signal, 'strength': 'strong',
                           'value': f'{vol_ratio:.2f}x', 
                           'reason': f'Very high volume ({vol_ratio:.1f}x average)'})
        elif vol_ratio > 1.2:
            vol_signal = 'BUY' if close > last.get('Open', close) else 'SELL'
            signals.append({'name': 'Volume', 'signal': vol_signal, 'strength': 'moderate',
                           'value': f'{vol_ratio:.2f}x',
                           'reason': f'Above average volume ({vol_ratio:.1f}x)'})
        else:
            signals.append({'name': 'Volume', 'signal': 'NEUTRAL', 'strength': 'weak',
                           'value': f'{vol_ratio:.2f}x',
                           'reason': 'Normal/low volume'})
    
    # ---- Support/Resistance Signal ----
    pivot = last.get('Pivot', 0)
    r1 = last.get('R1', 0)
    s1 = last.get('S1', 0)
    if not pd.isna(pivot) and pivot > 0:
        if close < s1:
            signals.append({'name': 'Pivot Points', 'signal': 'BUY', 'strength': 'moderate',
                           'value': f'S1={s1:.2f}', 'reason': 'Price below S1 support'})
        elif close > r1:
            signals.append({'name': 'Pivot Points', 'signal': 'SELL', 'strength': 'moderate',
                           'value': f'R1={r1:.2f}', 'reason': 'Price above R1 resistance'})
        elif close > pivot:
            signals.append({'name': 'Pivot Points', 'signal': 'BUY', 'strength': 'weak',
                           'value': f'P={pivot:.2f}', 'reason': 'Price above pivot point'})
        else:
            signals.append({'name': 'Pivot Points', 'signal': 'SELL', 'strength': 'weak',
                           'value': f'P={pivot:.2f}', 'reason': 'Price below pivot point'})
                           
    # ---- Pattern Signals ----
    if last.get('Pattern_Hammer', False):
        signals.append({'name': 'Hammer Pattern', 'signal': 'BUY', 'strength': 'strong',
                       'value': 'Detected', 'reason': 'Bullish reversal candlestick spotted'})
                       
    if last.get('Pattern_3BlackCrows', False):
        signals.append({'name': '3 Black Crows', 'signal': 'SELL', 'strength': 'strong',
                       'value': 'Detected', 'reason': 'Strong bearish continuation pattern'})

    if last.get('Pattern_Triangle_Breakout_Up', False):
        signals.append({'name': 'Triangle Breakout', 'signal': 'BUY', 'strength': 'strong',
                       'value': 'Upward Break', 'reason': 'Volatility contraction followed by upside volume break'})

    if last.get('Pattern_Triangle_Breakout_Down', False):
        signals.append({'name': 'Triangle Breakout', 'signal': 'SELL', 'strength': 'strong',
                       'value': 'Downward Break', 'reason': 'Volatility contraction followed by downside volume break'})

    if last.get('Pattern_Trendline_Support_Test', False):
        signals.append({'name': 'Trendline Test', 'signal': 'BUY', 'strength': 'moderate',
                       'value': 'Support respected', 'reason': 'Validated trend line held as support'})

    if last.get('Pattern_Trendline_Resistance_Test', False):
        signals.append({'name': 'Trendline Test', 'signal': 'SELL', 'strength': 'moderate',
                       'value': 'Resistance respected', 'reason': 'Validated trend line held as resistance'})

    if last.get('Pattern_Trendline_Breakout_Up', False):
        signals.append({'name': 'Trendline Breakout', 'signal': 'BUY', 'strength': 'strong',
                       'value': 'Upside break', 'reason': 'Price broke validated resistance with volume'})

    if last.get('Pattern_Trendline_Breakout_Down', False):
        signals.append({'name': 'Trendline Breakout', 'signal': 'SELL', 'strength': 'strong',
                       'value': 'Downside break', 'reason': 'Price broke validated support with volume'})

    if last.get('Pattern_Fib_Bounce_Buy', False):
        signals.append({'name': 'Fibonacci', 'signal': 'BUY', 'strength': 'moderate',
                       'value': 'Retracement bounce', 'reason': 'Price bounced from a Fibonacci retracement zone'})

    if last.get('Pattern_Fib_Rejection_Sell', False):
        signals.append({'name': 'Fibonacci', 'signal': 'SELL', 'strength': 'moderate',
                       'value': 'Retracement rejection', 'reason': 'Price rejected a Fibonacci retracement zone'})

    if last.get('Pattern_Fib_Extension_Up', False):
        signals.append({'name': 'Fibonacci Extension', 'signal': 'BUY', 'strength': 'strong',
                       'value': 'Upside extension', 'reason': 'Price extended beyond prior swing high with volume'})

    if last.get('Pattern_Fib_Extension_Down', False):
        signals.append({'name': 'Fibonacci Extension', 'signal': 'SELL', 'strength': 'strong',
                       'value': 'Downside extension', 'reason': 'Price extended below prior swing low with volume'})

    if last.get('Pattern_Double_Bottom', False):
        signals.append({'name': 'Double Bottom', 'signal': 'BUY', 'strength': 'strong',
                       'value': 'Breakout', 'reason': 'Repeated troughs followed by upside confirmation'})

    if last.get('Pattern_Double_Top', False):
        signals.append({'name': 'Double Top', 'signal': 'SELL', 'strength': 'strong',
                       'value': 'Breakdown', 'reason': 'Repeated peaks followed by downside confirmation'})
    
    # Calculate overall score
    buy_score = 0
    sell_score = 0
    total_signals = len(signals)
    
    strength_weights = {'strong': 3, 'moderate': 2, 'weak': 1}
    
    for sig in signals:
        weight = strength_weights.get(sig['strength'], 1)
        if sig['signal'] == 'BUY':
            buy_score += weight
        elif sig['signal'] == 'SELL':
            sell_score += weight
    
    max_possible = total_signals * 3
    
    return {
        'signals': signals,
        'buy_score': buy_score,
        'sell_score': sell_score,
        'total_signals': total_signals,
        'max_score': max_possible,
        'buy_pct': (buy_score / max_possible * 100) if max_possible > 0 else 0,
        'sell_pct': (sell_score / max_possible * 100) if max_possible > 0 else 0,
        'overall': 'BUY' if buy_score > sell_score * 1.2 else ('SELL' if sell_score > buy_score * 1.2 else 'HOLD')
    }


def get_indicator_summary(df):
    """Get a summary of key indicator values"""
    if df is None or df.empty:
        return {}
    
    last = df.iloc[-1]
    
    return {
        'price': float(last.get('Close', 0)),
        'rsi': float(last.get('RSI', 0)) if not pd.isna(last.get('RSI', np.nan)) else None,
        'macd': float(last.get('MACD', 0)) if not pd.isna(last.get('MACD', np.nan)) else None,
        'macd_signal': float(last.get('MACD_Signal', 0)) if not pd.isna(last.get('MACD_Signal', np.nan)) else None,
        'bb_upper': float(last.get('BB_Upper', 0)) if not pd.isna(last.get('BB_Upper', np.nan)) else None,
        'bb_lower': float(last.get('BB_Lower', 0)) if not pd.isna(last.get('BB_Lower', np.nan)) else None,
        'ema_9': float(last.get('EMA_9', 0)) if not pd.isna(last.get('EMA_9', np.nan)) else None,
        'ema_21': float(last.get('EMA_21', 0)) if not pd.isna(last.get('EMA_21', np.nan)) else None,
        'sma_50': float(last.get('SMA_50', 0)) if not pd.isna(last.get('SMA_50', np.nan)) else None,
        'adx': float(last.get('ADX', 0)) if not pd.isna(last.get('ADX', np.nan)) else None,
        'atr': float(last.get('ATR', 0)) if not pd.isna(last.get('ATR', np.nan)) else None,
        'vwap': float(last.get('VWAP', 0)) if not pd.isna(last.get('VWAP', np.nan)) else None,
        'stoch_k': float(last.get('Stoch_K', 0)) if not pd.isna(last.get('Stoch_K', np.nan)) else None,
        'mfi': float(last.get('MFI', 0)) if not pd.isna(last.get('MFI', np.nan)) else None,
        'cci': float(last.get('CCI', 0)) if not pd.isna(last.get('CCI', np.nan)) else None,
        'volume_ratio': float(last.get('Volume_Ratio', 1)) if not pd.isna(last.get('Volume_Ratio', np.nan)) else None,
        'trend_support': float(last.get('Trend_Support', 0)) if not pd.isna(last.get('Trend_Support', np.nan)) else None,
        'trend_resistance': float(last.get('Trend_Resistance', 0)) if not pd.isna(last.get('Trend_Resistance', np.nan)) else None,
        'fib_382': float(last.get('Fib_382', 0)) if not pd.isna(last.get('Fib_382', np.nan)) else None,
        'fib_500': float(last.get('Fib_500', 0)) if not pd.isna(last.get('Fib_500', np.nan)) else None,
        'fib_618': float(last.get('Fib_618', 0)) if not pd.isna(last.get('Fib_618', np.nan)) else None,
    }
