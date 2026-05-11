from __future__ import annotations
"""
Hybrid ML Engine for Stock Market Analysis
============================================
Combines:
  1. Random Forest Classifier       — trend classification (BUY/HOLD/SELL)
  2. Gradient Boosting Classifier   — probability scoring with boosting
  3. Ridge Regression               — price-return magnitude forecast
  4. Ensemble Voting                — weighted probabilistic combination

Models are trained on-the-fly using recent 60-day intraday (5-min) data,
cached per ticker for 30 minutes, then retrained to stay fresh.
"""

import time
import warnings
import numpy as np
import pandas as pd
import yfinance as yf

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import Ridge
from sklearn.preprocessing import RobustScaler

warnings.filterwarnings('ignore')


# ─── Model Cache ──────────────────────────────────────────────────────────────

class _ModelCache:
    """In-memory per-ticker model cache with TTL."""
    def __init__(self, ttl_minutes: int = 30):
        self._store: dict = {}
        self._ttl: float = ttl_minutes * 60

    def get(self, ticker: str):
        entry = self._store.get(ticker)
        if entry and (time.time() - entry["ts"] < self._ttl):
            return entry["engine"]
        return None

    def set(self, ticker: str, engine):
        self._store[ticker] = {"engine": engine, "ts": time.time()}

    def remove(self, ticker: str):
        self._store.pop(ticker, None)


_cache = _ModelCache(ttl_minutes=30)


# ─── Feature Engineering ──────────────────────────────────────────────────────

def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0).rolling(period, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period, min_periods=1).mean()
    return 100 - (100 / (1 + gain / (loss + 1e-9)))


def extract_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract ~50 technical features from an OHLCV DataFrame.
    All features are normalised to be scale-invariant where possible.
    """
    # Safely squeeze to Series (handles MultiIndex columns from yfinance)
    def _col(name):
        col = df[name]
        return col.squeeze() if isinstance(col, pd.DataFrame) else col

    close  = _col('Close')
    high   = _col('High')
    low    = _col('Low')
    volume = _col('Volume') if 'Volume' in df.columns else pd.Series(1, index=df.index)
    open_p = _col('Open')   if 'Open'   in df.columns else close.shift(1)

    feat = pd.DataFrame(index=df.index)

    # ── Price Momentum ──
    for p in [1, 3, 5, 10, 20, 30, 60]:
        feat[f'ret_{p}'] = close.pct_change(p)

    # ── RSI (multiple periods) ──
    for p in [7, 14, 21]:
        feat[f'rsi_{p}'] = _rsi(close, p) / 100.0          # normalise 0-1

    # ── MACD ──
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    sig   = macd.ewm(span=9, adjust=False).mean()
    feat['macd_hist']  = (macd - sig) / (close + 1e-9)
    feat['macd_slope'] = macd.diff(3) / (close + 1e-9)

    # ── Bollinger Bands ──
    for p in [10, 20]:
        sma = close.rolling(p, min_periods=max(3, p // 2)).mean()
        std = close.rolling(p, min_periods=max(3, p // 2)).std()
        feat[f'bb_pct_{p}']    = (close - sma) / (std * 2 + 1e-9)   # -1 to +1
        feat[f'bb_squeeze_{p}'] = std / (sma + 1e-9)

    # ── ATR (normalised by close) ──
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    for p in [7, 14]:
        feat[f'atr_pct_{p}'] = tr.rolling(p, min_periods=3).mean() / (close + 1e-9)

    # ── Volume ──
    avg_vol = volume.rolling(20, min_periods=5).mean()
    feat['vol_ratio']    = volume / (avg_vol + 1e-9)
    feat['vol_momentum'] = volume.pct_change(5)

    # ── Price vs SMAs ──
    for p in [5, 10, 20, 50]:
        sma = close.rolling(p, min_periods=max(3, p // 2)).mean()
        feat[f'sma_dev_{p}'] = (close - sma) / (sma + 1e-9)

    # ── Stochastic Oscillator ──
    for k in [9, 14]:
        ll = low.rolling(k,  min_periods=3).min()
        hh = high.rolling(k, min_periods=3).max()
        stoch_k = (close - ll) / (hh - ll + 1e-9)
        feat[f'stoch_k_{k}'] = stoch_k
        feat[f'stoch_d_{k}'] = stoch_k.rolling(3).mean()

    # ── VWAP deviation ──
    tp   = (high + low + close) / 3
    if (volume > 0).any():
        vwap = (tp * volume).cumsum() / (volume.cumsum() + 1e-9)
    else:
        vwap = tp.rolling(20).mean()
    feat['vwap_dev'] = (close - vwap) / (vwap + 1e-9)

    # ── SMA Cross-over signals ──
    for fast, slow in [(5, 20), (10, 30), (20, 50)]:
        sf = close.rolling(fast, min_periods=fast // 2).mean()
        ss = close.rolling(slow, min_periods=slow // 2).mean()
        feat[f'sma_x_{fast}_{slow}'] = (sf - ss) / (ss + 1e-9)

    # ── Candlestick Features ──
    body     = (close - open_p) / (high - low + 1e-9)
    feat['candle_body']  = body.clip(-1, 1)
    feat['upper_wick']   = (high - close.clip(lower=open_p)) / (high - low + 1e-9)
    feat['lower_wick']   = (close.clip(upper=open_p) - low ) / (high - low + 1e-9)

    # ── Volatility Regime ──
    feat['volatility']    = close.pct_change().rolling(20).std()
    feat['vol_of_vol']    = feat['volatility'].rolling(10).std()

    # ── Momentum features ──
    feat['price_accel']   = close.pct_change(5).diff(5)   # acceleration
    feat['high_low_ratio'] = (high - low) / (close + 1e-9)

    # Clean: replace inf/-inf with nan, will be filled with 0 before model
    feat.replace([np.inf, -np.inf], np.nan, inplace=True)
    return feat


# ─── Label Generation ─────────────────────────────────────────────────────────

def _make_labels(close: pd.Series, horizon: int, threshold: float) -> pd.Series:
    """
    3-class labels:
      +1 = BUY  (future return > +threshold)
       0 = HOLD
      -1 = SELL (future return < -threshold)
    """
    fut_ret = close.shift(-horizon) / close - 1
    fut_ret.replace([np.inf, -np.inf], np.nan, inplace=True)
    lbl = pd.Series(0, index=close.index, dtype=int)
    lbl[fut_ret >  threshold] =  1
    lbl[fut_ret < -threshold] = -1
    return lbl


# ─── Hybrid ML Engine ─────────────────────────────────────────────────────────

class HybridMLEngine:
    """
    Hybrid engine: RandomForest + GradientBoosting + Ridge, ensemble-voted.
    """

    HORIZON   = 12     # candles ahead (12 × 5min = 60 min)
    THRESHOLD = 0.003  # 0.3% return threshold for BUY/SELL label

    def __init__(self):
        self.rf:    RandomForestClassifier       = None
        self.gb:    GradientBoostingClassifier   = None
        self.lr:    Ridge                        = None
        self.scaler: RobustScaler               = RobustScaler()
        self.feat_cols: list                     = []
        self.feature_importance: dict            = {}
        self.train_accuracy: dict                = {}
        self.train_samples: int                  = 0
        self.is_trained: bool                    = False

    # ── Training ──────────────────────────────────────────────────────────────

    def train(self, df: pd.DataFrame) -> bool:
        try:
            if len(df) < 200:
                print("⚠️  Not enough rows to train (<200).")
                return False

            close = df['Close'].squeeze() if isinstance(df['Close'], pd.DataFrame) else df['Close']

            feats  = extract_features(df)
            labels = _make_labels(close, self.HORIZON, self.THRESHOLD)
            reg_tgt = (close.shift(-self.HORIZON) / close - 1).replace([np.inf, -np.inf, np.nan], 0.0)

            # Validity mask: all feature cols non-nan AND labels valid
            valid = (
                feats.notna().all(axis=1)
                & labels.notna()
                & reg_tgt.notna()
            )
            valid.iloc[-self.HORIZON:] = False   # no future for last rows

            X   = feats[valid].fillna(0)
            y   = labels[valid]
            y_r = reg_tgt[valid]

            if len(X) < 80:
                print("⚠️  Too few clean samples after filtering.")
                return False

            self.feat_cols = X.columns.tolist()
            Xs = self.scaler.fit_transform(X.values)
            yv = y.values
            yr = y_r.values

            # Random Forest
            self.rf = RandomForestClassifier(
                n_estimators=200, max_depth=10,
                min_samples_split=6, min_samples_leaf=3,
                max_features='sqrt', random_state=42,
                n_jobs=-1, class_weight='balanced'
            )
            self.rf.fit(Xs, yv)

            # Gradient Boosting
            self.gb = GradientBoostingClassifier(
                n_estimators=200, max_depth=5,
                learning_rate=0.07, subsample=0.8,
                min_samples_split=6, random_state=42
            )
            self.gb.fit(Xs, yv)

            # Ridge Regression (return magnitude)
            self.lr = Ridge(alpha=0.5)
            self.lr.fit(Xs, yr)

            # Feature importance (from RF)
            imp = self.rf.feature_importances_
            top_idx = np.argsort(imp)[::-1][:12]
            self.feature_importance = {
                self.feat_cols[i]: round(float(imp[i]) * 100, 2)
                for i in top_idx
            }

            # Training accuracy
            self.train_accuracy = {
                "random_forest":      round(self.rf.score(Xs, yv) * 100, 1),
                "gradient_boosting":  round(self.gb.score(Xs, yv) * 100, 1),
            }
            self.train_samples = len(X)
            self.is_trained    = True

            print(
                f"✅ Hybrid model trained | samples={len(X)} | "
                f"RF={self.train_accuracy['random_forest']}% | "
                f"GB={self.train_accuracy['gradient_boosting']}%"
            )
            return True

        except Exception as exc:
            import traceback
            print(f"❌ Training error: {exc}")
            traceback.print_exc()
            return False

    # ── Prediction ────────────────────────────────────────────────────────────

    def predict(self, df: pd.DataFrame) -> dict | None:
        if not self.is_trained:
            return None
        try:
            feats  = extract_features(df)
            latest = feats.iloc[-1:][self.feat_cols].fillna(0)
            Xs     = self.scaler.transform(latest.values)

            # RF probabilities
            rf_p = dict(zip(self.rf.classes_.tolist(), self.rf.predict_proba(Xs)[0].tolist()))
            # GB probabilities
            gb_p = dict(zip(self.gb.classes_.tolist(), self.gb.predict_proba(Xs)[0].tolist()))
            # Ridge regression
            lr_ret = float(self.lr.predict(Xs)[0])

            # Weighted ensemble (RF 50%, GB 50%)
            ens_buy  = rf_p.get(1, 0) * 0.50 + gb_p.get(1, 0) * 0.50
            ens_sell = rf_p.get(-1, 0) * 0.50 + gb_p.get(-1, 0) * 0.50
            ens_hold = rf_p.get(0, 0) * 0.50 + gb_p.get(0, 0) * 0.50

            # Determine ensemble signal
            best = max(ens_buy, ens_sell, ens_hold)
            if ens_buy == best and ens_buy > 0.35:
                ml_signal = "STRONG BUY" if ens_buy > 0.55 else "BUY"
            elif ens_sell == best and ens_sell > 0.35:
                ml_signal = "STRONG SELL" if ens_sell > 0.55 else "SELL"
            else:
                ml_signal = "HOLD"

            # Let regression nudge boundary HOLDs
            if ml_signal == "HOLD":
                if lr_ret >  0.005:
                    ml_signal = "WEAK BUY"
                elif lr_ret < -0.005:
                    ml_signal = "WEAK SELL"

            return {
                "ml_signal":            ml_signal,
                "confidence":           round(best * 100, 1),
                "buy_probability":      round(ens_buy  * 100, 1),
                "sell_probability":     round(ens_sell * 100, 1),
                "hold_probability":     round(ens_hold * 100, 1),
                "predicted_return_pct": round(lr_ret * 100, 3),
                "model_signals": {
                    "random_forest":     _cls_to_str(int(self.rf.predict(Xs)[0])),
                    "gradient_boosting": _cls_to_str(int(self.gb.predict(Xs)[0])),
                    "ridge_regression":  "BUY" if lr_ret > 0.002 else ("SELL" if lr_ret < -0.002 else "HOLD"),
                },
                "model_probabilities": {
                    "random_forest": {
                        "buy":  round(rf_p.get(1,  0) * 100, 1),
                        "sell": round(rf_p.get(-1, 0) * 100, 1),
                        "hold": round(rf_p.get(0,  0) * 100, 1),
                    },
                    "gradient_boosting": {
                        "buy":  round(gb_p.get(1,  0) * 100, 1),
                        "sell": round(gb_p.get(-1, 0) * 100, 1),
                        "hold": round(gb_p.get(0,  0) * 100, 1),
                    },
                },
                "feature_importance":  self.feature_importance,
                "training_accuracy":   self.train_accuracy,
                "training_samples":    self.train_samples,
            }

        except Exception as exc:
            import traceback
            print(f"❌ Prediction error: {exc}")
            traceback.print_exc()
            return None


def _cls_to_str(cls: int) -> str:
    return {1: "BUY", -1: "SELL"}.get(cls, "HOLD")


# ─── Public API ───────────────────────────────────────────────────────────────

def get_ml_prediction(ticker: str, df: pd.DataFrame | None = None) -> dict | None:
    """
    Returns ML prediction dict for ticker.
    Pulls from cache if fresh; otherwise fetches training data and retrains.
    """
    engine = _cache.get(ticker)
    if engine is None:
        engine = HybridMLEngine()
        if df is None:
            try:
                df_train = yf.download(
                    ticker, period="60d", interval="5m",
                    progress=False, auto_adjust=True
                )
                if isinstance(df_train.columns, pd.MultiIndex):
                    df_train.columns = df_train.columns.droplevel(1)
            except Exception as e:
                print(f"⚠️  Failed to fetch training data for {ticker}: {e}")
                return None
        else:
            df_train = df

        success = engine.train(df_train)
        if not success:
            return None
        _cache.set(ticker, engine)

    return engine.predict(df if df is not None else _fetch_recent(ticker))


def _fetch_recent(ticker: str) -> pd.DataFrame | None:
    """Fetch last 5 days of 5-min data for prediction (not training)."""
    try:
        data = yf.download(ticker, period="5d", interval="5m",
                           progress=False, auto_adjust=True)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.droplevel(1)
        return data if not data.empty else None
    except Exception as e:
        print(f"⚠️  Failed to fetch recent data for {ticker}: {e}")
        return None
