
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import timedelta

def get_prediction_trajectory(target_ticker, contexts):
    """
    Generates price trajectories for multiple context windows.
    contexts: list of strings e.g. ["1h", "2h", "1d", "2d", "1wk"]
    Returns: { "1h": [ {time: '...', price: ...}, ... ], ... }
    """
    try:
        # Fetch max necessary data (approx 5 days for '1wk' coverage on 1m interval)
        # yfinance 1m interval is limited to last 7 days usually.
        data = yf.download(target_ticker, period="5d", interval="1m", progress=False)
        
        if data.empty:
            return {}

        df = data
        if isinstance(df['Close'], pd.DataFrame):
             close = df['Close'][target_ticker] 
        else:
             close = df['Close']
        close = close.dropna()
        
        if close.empty:
            return {}

        results = {}
        
        # Define checkpoints (minutes from now)
        checkpoints = [1, 2, 3, 4, 5, 10, 15, 30, 60, 120, 180, 240, 300]
        
        current_time = close.index[-1]
        
        for ctx in contexts:
            # Determine window size (number of candles approx)
            # Assuming 1m interval, 1 row = 1 minute (roughly, ignoring gaps for simplicity or using time deltas)
            
            sliced_data = None
            
            if ctx.endswith('h'):
                hours = int(ctx[:-1])
                # Slice last N hours (approx N * 60 points)
                # Ideally filter by time, but tail is safe/fast for "last N"
                count = hours * 60
                if len(close) >= 2:
                    sliced_data = close.tail(count)
            
            elif ctx.endswith('d'):
                days = int(ctx[:-1])
                # Filter by start date
                # For "Same Day" (1d), we want from midnight today? Or last 24h?
                # User said "same day".
                if days == 0: # Treat '0d' or similar as "Today"
                     # Midnight of current_time
                     start_date = current_time.normalize()
                else:
                    start_date = current_time - timedelta(days=days)
                
                sliced_data = close[close.index >= start_date]

            elif ctx == '1wk':
                # full 5d data
                sliced_data = close

            if sliced_data is None or len(sliced_data) < 2:
                results[ctx] = [] # Not enough data
                continue
                
            # Perform Regression
            y = sliced_data.values
            x = np.arange(len(y))
            
            try:
                slope, intercept = np.polyfit(x, y, 1)
                
                # Predict
                trajectory = []
                last_idx = len(y) - 1
                
                for minutes in checkpoints:
                    future_idx = last_idx + minutes
                    price = (slope * future_idx) + intercept
                    
                    # Calculate future time label
                    future_time = current_time + timedelta(minutes=minutes)
                    
                    # Convert to IST for display
                    try:
                         if future_time.tzinfo is not None:
                              future_time_ist = future_time.tz_convert('Asia/Kolkata')
                         else:
                              # Assume UTC if naive
                              future_time_ist = future_time.tz_localize('UTC').tz_convert('Asia/Kolkata')
                         time_str = future_time_ist.strftime('%H:%M')
                    except:
                         time_str = future_time.strftime('%H:%M')

                    trajectory.append({
                        "minutes_ahead": minutes,
                        "time": time_str,
                        "price": round(price, 2)
                    })
                
                results[ctx] = trajectory
                
            except Exception as e:
                # print(f"Regression failed for {ctx}: {e}")
                results[ctx] = []
                
        return results

    except Exception as e:
        print(f"Trajectory error {target_ticker}: {e}")
        return {}
from datetime import datetime, timedelta

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def get_market_data(tickers):
    # Fetch data for 1 day with 1 minute interval for precise intraday predictions
    try:
        data = yf.download(tickers, period="2d", interval="1m", progress=False, group_by='ticker')
        return data
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None

def predict_trend(close_prices, window_size):
    """
    Simple trend prediction based on the slope of the last 'window_size' candles.
    """
    if len(close_prices) < window_size:
        return "NEUTRAL"
    
    # Take the recent window
    recent = close_prices.tail(window_size)
    
    # Calculate simple linear regression slope (normalized)
    x = np.arange(len(recent))
    y = recent.values
    
    # Handle NaN
    if np.isnan(y).any():
        return "NEUTRAL"

    # Slope
    try:
        slope, _ = np.polyfit(x, y, 1)
        
        # Define a threshold for "flat"
        threshold = recent.mean() * 0.0001 # 0.01% change per minute
        
        if slope > threshold:
            return "UP"
        elif slope < -threshold:
            return "DOWN"
        else:
            return "NEUTRAL"
    except:
        return "NEUTRAL"


def calculate_trade_levels(current_price, volatility, direction):
    """
    Calculate simple Entry, Target, and Stop Loss based on volatility and direction.
    """
    if direction == "UP":
        entry = current_price
        target = current_price + (volatility * 1.5)
        stop_loss = current_price - volatility
        return {"action": "BUY", "entry": round(entry, 2), "target": round(target, 2), "stop_loss": round(stop_loss, 2)}
    elif direction == "DOWN":
        entry = current_price
        target = current_price - (volatility * 1.5)
        stop_loss = current_price + volatility
        return {"action": "SELL", "entry": round(entry, 2), "target": round(target, 2), "stop_loss": round(stop_loss, 2)}
    else:
        return {"action": "WAIT", "entry": 0.0, "target": 0.0, "stop_loss": 0.0}

def analyze_market(data, tickers):
    results = []
    
    for ticker in tickers:
        try:
            # Handle multi-index data from yfinance
            if len(tickers) > 1:
                df = data[ticker].copy()
            else:
                df = data.copy()
            
            if df.empty:
                continue

            # Calculate Indicators
            close = df['Close']
            
            # --- Technical Indicators ---
            rsi = calculate_rsi(close).iloc[-1]
            sma_20 = close.rolling(window=20).mean().iloc[-1]
            
            current_vol = df['Volume'].iloc[-1]
            avg_vol = df['Volume'].rolling(window=20).mean().iloc[-1]
            vol_spike = current_vol > (avg_vol * 1.5) if avg_vol > 0 else False
            
            current_price = close.iloc[-1]
            
            # Change from 1 hour ago (approx 60 candles)
            prev_price = close.iloc[-60] if len(close) > 60 else close.iloc[0]
            change_p = ((current_price - prev_price) / prev_price) * 100
            
            # --- Prediction Logic for Requested Horizons ---
            # 1m to 5m, 1h to 5h
            # We use slope of 'N' candles as a proxy for trend of 'N' minutes/hours (assuming 1m intervals)
            # 1 hour = 60 minutes
            
            timeframes = {
                "1m": 1, "2m": 2, "3m": 3, "4m": 4, "5m": 5,
                "1h": 60, "2h": 120, "3h": 180, "4h": 240, "5h": 300
            }
            
            predictions = {}
            trades = {}
            
            # Base volatility on recent 10 minutes
            recent_closes = close.tail(10)
            base_volatility = recent_closes.std() if len(recent_closes) > 1 else (current_price * 0.001)
            if base_volatility == 0 or np.isnan(base_volatility):
                base_volatility = current_price * 0.0005

            for label, minutes in timeframes.items():
                # Predict trend based on this window
                # For longer horizons (hours), we look at longer historical windows to detect the trend
                trend = predict_trend(close, minutes) 
                predictions[label] = trend
                
                # Calculate specific trade levels for this timeframe
                # We scale volatility for longer timeframes
                # sqrt(time) rule approximation for volatility scaling
                scaled_volatility = base_volatility * np.sqrt(minutes)
                trades[label] = calculate_trade_levels(current_price, scaled_volatility, trend)

            # --- Scoring Logic ---
            score = 0
            signal = "NEUTRAL"
            reason = []

            # Buy Conditions
            if rsi < 30:
                score += 30
                reason.append("Oversold")
            elif 50 < rsi < 70:
                score += 10
                reason.append("Bullish Mom.")
            
            if current_price > sma_20:
                score += 20
            
            if vol_spike:
                score += 10
                reason.append("Vol Spike")

            # Sell Conditions
            if rsi > 70:
                score = -30
                reason = ["Overbought"]
                signal = "SELL"
            elif current_price < sma_20:
                score -= 10
            
            if score >= 40:
                signal = "STRONG BUY"
            elif score >= 20:
                signal = "BUY"
            elif score <= -20:
                signal = "SELL"
            
            # Helper to handle NaN/Inf
            def safe_float(val, default=0.0):
                if pd.isna(val) or np.isinf(val):
                    return default
                return float(val)

            results.append({
                "symbol": ticker,
                "price": round(safe_float(current_price), 2),
                "change": round(safe_float(change_p), 2),
                "rsi": round(safe_float(rsi), 1),
                "signal": signal,
                "score": int(safe_float(score)),
                "reason": ", ".join(reason) if reason else "No strong trend",
                "time_predictions": predictions,
                "trades": trades # Contains the buy/sell values for each timeframe
            })
            
        except Exception as e:
            # print(f"Error analyzing {ticker}: {e}")
            continue
            
    # Sort by "Opportunity" (absolute score magnitude)
    results.sort(key=lambda x: x['score'], reverse=True)
    return results

def predict_future_price(close_prices, minutes_ahead=5):
    """
    Predicts the price 'minutes_ahead' from now using linear regression on recent data.
    """
    try:
        # Use last 30 minutes for trend analysis
        window = 30
        if len(close_prices) < 2:
            return None
        
        # Slice recent data
        recent = close_prices.tail(window)
        y = recent.values
        x = np.arange(len(y))
        
        # Calculate Slope and Intercept (y = mx + c)
        if len(y) > 1:
            slope, intercept = np.polyfit(x, y, 1)
            
            # Predict
            # Current last index is len(y)-1
            # Future index is (len(y)-1) + minutes_ahead
            future_x = (len(y) - 1) + minutes_ahead
            
            predicted_price = (slope * future_x) + intercept
            return round(predicted_price, 2)
        return None
    except Exception:
        return None

def get_stock_history_for_chart(tickers, target_ticker):
    """
    Fetches fresh or processes existing data to return time-series for chart.
    Returns: { "labels": [...timestamps], "data": [...prices], "forecast_5m": float }
    """
    try:
        # Re-fetch specific ticker data for cleaner history (or use cached if optimal)
        # Fetching 1d with 1m interval for decent intraday resolution
        data = yf.download(target_ticker, period="1d", interval="1m", progress=False)
        
        if data.empty:
            return None
            
        # If multi-level columns (price, ticker), flatten or access directly
        # For single ticker download, it might be simpler
        df = data
        
        # Check if 'Close' is a Series or DataFrame
        if isinstance(df['Close'], pd.DataFrame):
             # Depending on yfinance version, might have Ticker level column
             close = df['Close'][target_ticker] 
        else:
             close = df['Close']

        # Filter out NaN
        close = close.dropna()
        
        # Calculate Forecast
        forecast = predict_future_price(close, 5)

        # Prepare for Chart.js
        # Labels: HH:MM string
        # Data: Price float
        
        # Convert to local time (IST) for display
        try:
            # Check if tz-aware
            if close.index.tz is not None:
                local_index = close.index.tz_convert('Asia/Kolkata')
            else:
                # Assume UTC if naive (yfinance standard)
                local_index = close.index.tz_localize('UTC').tz_convert('Asia/Kolkata')
            
            labels = local_index.strftime('%H:%M').tolist()
        except Exception:
            # Fallback if conversion fails
            labels = close.index.strftime('%H:%M').tolist()
            
        prices = [round(float(x), 2) for x in close.values]
        
        return {
            "labels": labels,
            "data": prices,
            "forecast_5m": forecast
        }

    except Exception as e:
        print(f"Error getting history for {target_ticker}: {e}")
        return None


