"""
AI Advisory Layer
=================
Adds Claude Opus + Groq/Emergent AI as reasoning advisors.
MetaEnsemble fuses ALL model signals into one final verdict.

Model weights:
  Rule Engine        → 1.0
  Random Forest      → 1.0
  Gradient Boosting  → 1.0
  Ridge Regression   → 0.7
  Linear Regression  → 0.7
  Claude Opus        → 1.5  (if API key set)
  Emergent AI (Groq) → 1.2  (if API key set)
"""
from __future__ import annotations

import os
import json
import threading
import requests
from pathlib import Path
from dataclasses import dataclass, field

# ─── API Key Store ────────────────────────────────────────────────────────────

_CONFIG_FILE = Path(__file__).parent / "api_keys.json"
_API_KEYS: dict = {"anthropic": "", "groq": ""}


def _load_keys():
    _API_KEYS["anthropic"] = os.environ.get("ANTHROPIC_API_KEY", "")
    _API_KEYS["groq"]      = os.environ.get("GROQ_API_KEY", "")
    if _CONFIG_FILE.exists():
        try:
            saved = json.loads(_CONFIG_FILE.read_text())
            for k, v in saved.items():
                if v: _API_KEYS[k] = v
        except Exception:
            pass


def set_api_key(provider: str, key: str):
    _API_KEYS[provider] = key
    try:
        existing = {}
        if _CONFIG_FILE.exists():
            existing = json.loads(_CONFIG_FILE.read_text())
        existing[provider] = key
        _CONFIG_FILE.write_text(json.dumps(existing, indent=2))
    except Exception:
        pass


def get_key(provider: str) -> str:
    return _API_KEYS.get(provider, "")


def get_keys_status() -> dict:
    return {
        "anthropic_set": bool(_API_KEYS.get("anthropic")),
        "groq_set":      bool(_API_KEYS.get("groq")),
    }


_load_keys()


# ─── ModelSignal Dataclass ────────────────────────────────────────────────────

@dataclass
class ModelSignal:
    name:       str
    buy_prob:   float      # 0.0 – 1.0
    hold_prob:  float
    sell_prob:  float
    signal:     str        # STRONG BUY / BUY / HOLD / SELL / STRONG SELL
    confidence: float      # 0 – 100
    reasoning:  str  = ""
    weight:     float = 1.0
    available:  bool  = True

    @classmethod
    def unavailable(cls, name: str, reason: str = "API key not set") -> "ModelSignal":
        return cls(name=name, buy_prob=0.33, hold_prob=0.34, sell_prob=0.33,
                   signal="UNAVAILABLE", confidence=0.0,
                   reasoning=reason, weight=0.0, available=False)


# ─── Claude Opus Advisor ──────────────────────────────────────────────────────

class ClaudeAdvisor:
    MODEL   = "claude-3-5-sonnet-20240620"
    API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or get_key("anthropic")

    def analyze(self, ctx: dict) -> ModelSignal:
        if not self.api_key:
            return ModelSignal.unavailable("Claude Opus 4", "Add ANTHROPIC_API_KEY in ⚙️ Settings")
        try:
            resp = requests.post(
                self.API_URL,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.MODEL,
                    "max_tokens": 350,
                    "messages": [{"role": "user", "content": self._prompt(ctx)}],
                },
                timeout=14,
            )
            resp.raise_for_status()
            return self._parse(resp.json()["content"][0]["text"], "Claude Opus 4", weight=1.5)
        except Exception as e:
            return ModelSignal.unavailable("Claude Opus 4", f"Error: {str(e)[:80]}")

    def _prompt(self, c: dict) -> str:
        return (
            f"You are an expert NSE intraday trader. Analyze {c.get('symbol')} strictly.\n"
            f"Price=₹{c.get('price')}, Change={c.get('day_change')}%, RSI={c.get('rsi')}, "
            f"MACD={c.get('macd_hist')}, BB={c.get('bb_pos')}, VWAP={c.get('vwap_pos')}, "
            f"Volume={c.get('vol_trend')}, ADX={c.get('adx')}, StochK={c.get('stoch_k')}, "
            f"Slope={c.get('trend_slope')}, Support=₹{c.get('support')}, "
            f"Resistance=₹{c.get('resistance')}.\n"
            f"ML signals → RF:{c.get('rf_signal')} GB:{c.get('gb_signal')} "
            f"Rules:{c.get('rule_verdict')} LR:{c.get('reg_signal')}.\n"
            "Reply ONLY valid JSON: "
            '{"buy_probability":0.0,"hold_probability":0.0,"sell_probability":0.0,'
            '"signal":"BUY|HOLD|SELL|STRONG BUY|STRONG SELL","confidence":0,"reasoning":"brief"}'
        )

    def _parse(self, text: str, name: str, weight: float) -> ModelSignal:
        try:
            data = json.loads(text[text.find("{"):text.rfind("}")+1])
            b, h, s = (float(data.get(k, 0.33)) for k in
                       ("buy_probability", "hold_probability", "sell_probability"))
            tot = b + h + s or 1
            return ModelSignal(
                name=name, buy_prob=round(b/tot, 3), hold_prob=round(h/tot, 3),
                sell_prob=round(s/tot, 3), signal=str(data.get("signal", "HOLD")),
                confidence=float(data.get("confidence", 50)),
                reasoning=str(data.get("reasoning", ""))[:220],
                weight=weight, available=True,
            )
        except Exception as e:
            return ModelSignal.unavailable(name, f"Parse error: {e}")


# ─── Groq / Emergent AI Advisor ───────────────────────────────────────────────

class GroqAdvisor:
    MODEL   = "llama-3.3-70b-versatile"
    API_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or get_key("groq")

    def analyze(self, ctx: dict) -> ModelSignal:
        if not self.api_key:
            return ModelSignal.unavailable("Emergent AI (Groq)", "Add GROQ_API_KEY in ⚙️ Settings")
        try:
            resp = requests.post(
                self.API_URL,
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                json={
                    "model": self.MODEL,
                    "messages": [
                        {"role": "system",
                         "content": "Expert NSE intraday analyst. Reply ONLY valid JSON."},
                        {"role": "user", "content": self._prompt(ctx)},
                    ],
                    "max_tokens": 280,
                    "temperature": 0.1,
                },
                timeout=10,
            )
            resp.raise_for_status()
            return self._parse(
                resp.json()["choices"][0]["message"]["content"],
                "Emergent AI (Groq)", weight=1.2
            )
        except Exception as e:
            return ModelSignal.unavailable("Emergent AI (Groq)", f"Error: {str(e)[:80]}")

    def _prompt(self, c: dict) -> str:
        return (
            f"Analyze {c.get('symbol')} for NSE intraday. "
            f"RSI={c.get('rsi')} MACD={c.get('macd_hist')} ADX={c.get('adx')} "
            f"BB={c.get('bb_pos')} VWAP={c.get('vwap_pos')} StochK={c.get('stoch_k')} "
            f"Slope={c.get('trend_slope')} Support={c.get('support')} Res={c.get('resistance')}. "
            f"Models: RF={c.get('rf_signal')} GB={c.get('gb_signal')} "
            f"Rules={c.get('rule_verdict')} LR={c.get('reg_signal')}. "
            'JSON only: {"buy_probability":0.0,"hold_probability":0.0,"sell_probability":0.0,'
            '"signal":"BUY|HOLD|SELL|STRONG BUY|STRONG SELL","confidence":0,"reasoning":"brief"}'
        )

    def _parse(self, text: str, name: str, weight: float) -> ModelSignal:
        return ClaudeAdvisor("x")._parse(text, name, weight)  # shared parser


# ─── Parallel AI Caller ───────────────────────────────────────────────────────

def get_ai_signals(ctx: dict) -> tuple[ModelSignal, ModelSignal]:
    """Calls Claude + Groq in parallel to minimise latency."""
    results: list = [None, None]

    def _c(): results[0] = ClaudeAdvisor().analyze(ctx)
    def _g(): results[1] = GroqAdvisor().analyze(ctx)

    t1 = threading.Thread(target=_c, daemon=True)
    t2 = threading.Thread(target=_g, daemon=True)
    t1.start(); t2.start()
    t1.join(timeout=15); t2.join(timeout=11)

    return (
        results[0] or ModelSignal.unavailable("Claude Opus 4",    "Request timed out"),
        results[1] or ModelSignal.unavailable("Emergent AI (Groq)", "Request timed out"),
    )


# ─── Meta-Ensemble Voting System ─────────────────────────────────────────────

class MetaEnsemble:
    """
    Weighted probability fusion over all active model signals.
    Converts individual [buy%, hold%, sell%] distributions
    into a single authoritative verdict + consensus score.
    """

    def fuse(self, signals: list[ModelSignal]) -> dict:
        active = [s for s in signals if s.available and s.weight > 0]
        if not active:
            return self._empty()

        w_total = sum(s.weight for s in active)
        fb = sum(s.buy_prob  * s.weight for s in active) / w_total
        fh = sum(s.hold_prob * s.weight for s in active) / w_total
        fs = sum(s.sell_prob * s.weight for s in active) / w_total

        # Normalise
        tot = fb + fh + fs or 1
        fb /= tot; fh /= tot; fs /= tot

        verdict, conf = self._verdict(fb, fh, fs)

        # Vote tally
        tally = {"BUY": 0, "HOLD": 0, "SELL": 0, "UNAVAILABLE": 0}
        for s in signals:
            if not s.available:
                tally["UNAVAILABLE"] += 1; continue
            v = s.signal.upper().replace("STRONG ", "").replace("WEAK ", "")
            tally[v if v in tally else "HOLD"] += 1

        dominant = max(tally["BUY"], tally["HOLD"], tally["SELL"])
        consensus = round(dominant / max(len(signals), 1) * 100, 1)

        return {
            "final_verdict":    verdict,
            "final_confidence": round(conf, 1),
            "fused_buy_pct":    round(fb * 100, 1),
            "fused_hold_pct":   round(fh * 100, 1),
            "fused_sell_pct":   round(fs * 100, 1),
            "consensus_pct":    consensus,
            "vote_tally":       tally,
            "active_models":    len(active),
            "total_models":     len(signals),
            "model_breakdown":  [
                {
                    "name":       s.name,
                    "signal":     s.signal,
                    "buy_pct":    round(s.buy_prob  * 100, 1),
                    "hold_pct":   round(s.hold_prob * 100, 1),
                    "sell_pct":   round(s.sell_prob * 100, 1),
                    "confidence": round(s.confidence, 1),
                    "reasoning":  s.reasoning,
                    "weight":     round(s.weight, 1),
                    "available":  s.available,
                }
                for s in signals
            ],
        }

    def _verdict(self, b: float, h: float, s: float) -> tuple[str, float]:
        if   b >= 0.60: return "STRONG BUY",  min(b * 100, 97)
        if   b >= 0.42: return "BUY",          b * 100
        if   s >= 0.60: return "STRONG SELL", min(s * 100, 97)
        if   s >= 0.42: return "SELL",         s * 100
        return "HOLD", h * 100

    def _empty(self) -> dict:
        return {
            "final_verdict": "HOLD", "final_confidence": 0,
            "fused_buy_pct": 33.3, "fused_hold_pct": 33.3, "fused_sell_pct": 33.4,
            "consensus_pct": 0, "vote_tally": {"BUY": 0, "HOLD": 0, "SELL": 0, "UNAVAILABLE": 0},
            "active_models": 0, "total_models": 0, "model_breakdown": [],
        }


# ─── Helper: build signals from existing engine outputs ───────────────────────

def build_signals(rule_result: dict, ml_result: dict | None,
                  reg_result: dict) -> list[ModelSignal]:
    """Converts rule/ML/regression outputs into comparable ModelSignal objects."""
    sigs: list[ModelSignal] = []

    # 1. Rule Engine
    bs = rule_result.get("buy_score", 0)
    ss = rule_result.get("sell_score", 0)
    tot = bs + ss + 1e-9
    hs = max(0.0, 1.0 - (bs + ss) / (tot * 2))
    rb, rs = bs / (tot + hs * tot), ss / (tot + hs * tot)
    rh = max(0.0, 1.0 - rb - rs)
    sigs.append(ModelSignal(
        name="Rule Engine", buy_prob=round(rb,3), hold_prob=round(rh,3), sell_prob=round(rs,3),
        signal=rule_result.get("verdict", "HOLD"),
        confidence=rule_result.get("confidence", 0),
        reasoning="Weighted technical indicator rules",
        weight=1.0, available=True,
    ))

    if ml_result:
        probs = ml_result.get("model_probabilities", {})
        msigs = ml_result.get("model_signals", {})

        # 2. Random Forest
        if "random_forest" in probs:
            p = probs["random_forest"]
            sigs.append(ModelSignal(
                name="Random Forest",
                buy_prob=p["buy"]/100, hold_prob=p["hold"]/100, sell_prob=p["sell"]/100,
                signal=msigs.get("random_forest", "HOLD"),
                confidence=max(p["buy"], p["hold"], p["sell"]),
                reasoning=f"RF train acc: {ml_result.get('training_accuracy',{}).get('random_forest','?')}%",
                weight=1.0, available=True,
            ))

        # 3. Gradient Boosting
        if "gradient_boosting" in probs:
            p = probs["gradient_boosting"]
            sigs.append(ModelSignal(
                name="Gradient Boosting",
                buy_prob=p["buy"]/100, hold_prob=p["hold"]/100, sell_prob=p["sell"]/100,
                signal=msigs.get("gradient_boosting", "HOLD"),
                confidence=max(p["buy"], p["hold"], p["sell"]),
                reasoning=f"GB train acc: {ml_result.get('training_accuracy',{}).get('gradient_boosting','?')}%",
                weight=1.0, available=True,
            ))

        # 4. Ridge Regression
        lr_ret = ml_result.get("predicted_return_pct", 0) / 100
        lr_buy = min(1.0, max(0.0, 0.5 + lr_ret * 30))
        lr_sell = min(1.0, max(0.0, 0.5 - lr_ret * 30))
        lr_hold = max(0.0, 1.0 - lr_buy - lr_sell)
        sigs.append(ModelSignal(
            name="Ridge Regression",
            buy_prob=round(lr_buy,3), hold_prob=round(lr_hold,3), sell_prob=round(lr_sell,3),
            signal=msigs.get("ridge_regression", "HOLD"),
            confidence=min(100, abs(lr_ret) * 5000),
            reasoning=f"Predicted return: {ml_result.get('predicted_return_pct',0)}%",
            weight=0.7, available=True,
        ))

    # 5. Linear Regression Trend
    sig_map = {"UP":   ("BUY",  0.6, 0.25, 0.15),
               "DOWN": ("SELL", 0.15, 0.25, 0.6),
               "NEUTRAL": ("HOLD", 0.25, 0.5, 0.25)}
    lv, lb, lh, ls = sig_map.get(reg_result.get("signal", "NEUTRAL"), ("HOLD",0.25,0.5,0.25))
    sigs.append(ModelSignal(
        name="Linear Regression",
        buy_prob=lb, hold_prob=lh, sell_prob=ls, signal=lv,
        confidence=min(100, abs(reg_result.get("slope_pct", 0)) * 10000),
        reasoning=f"Slope={reg_result.get('slope_pct',0)}, R²={reg_result.get('r2',0)}",
        weight=0.7, available=True,
    ))

    return sigs
