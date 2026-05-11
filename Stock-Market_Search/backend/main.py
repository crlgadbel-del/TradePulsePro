
from pathlib import Path
from fastapi import Body, FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import yfinance as yf
from analyzer import get_market_data, analyze_market, get_stock_history_for_chart, get_prediction_trajectory
from ai_layer import set_api_key, get_keys_status

STATIC_DIR = str(Path(__file__).parent.parent / "static")

app = FastAPI(title="Antigravity TradeAI — Hybrid Expert System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WATCHLIST = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "SBIN.NS",
    "ADANIENT.NS", "TATAMOTORS.NS", "BAJFINANCE.NS", "AXISBANK.NS",
    "ICICIBANK.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS",
    "WIPRO.NS", "ASIANPAINT.NS", "BHARTIARTL.NS", "ITC.NS"
]


def _load_expert_analysis():
    try:
        from expert_engine import run_expert_analysis
        return run_expert_analysis, None
    except ModuleNotFoundError as exc:
        return None, f"Missing Python dependency: {exc.name}. Run pip install -r requirements.txt"
    except Exception as exc:
        return None, f"Expert engine failed to load: {exc}"


@app.get("/api/market-status")
async def get_market_status():
    data = get_market_data(WATCHLIST)
    if data is None:
        return {"error": "Failed to fetch data"}
    analysis = analyze_market(data, WATCHLIST)
    opportunities = [x for x in analysis if x['signal'] in ['STRONG BUY', 'BUY', 'SELL']]
    return {"market_data": analysis, "top_picks": opportunities[:5]}


@app.get("/api/stock-history/{symbol}")
async def get_stock_history(symbol: str):
    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        ticker = f"{symbol}.NS"
    else:
        ticker = symbol
    history = get_stock_history_for_chart(WATCHLIST, ticker)
    if history is None:
        return {"error": "Failed to fetch history"}
    return history


@app.get("/api/predict-trajectory/{symbol}")
async def predict_trajectory(symbol: str, contexts: str):
    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        ticker = f"{symbol}.NS"
    else:
        ticker = symbol
    ctx_list = contexts.split(',')
    trajectory = get_prediction_trajectory(ticker, ctx_list)
    return trajectory


@app.get("/api/expert-analysis/{symbol}")
async def expert_analysis(symbol: str, investment: float = 10000):
    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        ticker = f"{symbol}.NS"
    else:
        ticker = symbol
    run_expert_analysis, load_error = _load_expert_analysis()
    if load_error:
        return {"error": load_error}
    result = run_expert_analysis(ticker, investment)
    return result


@app.get("/api/search-stock/{symbol}")
async def search_stock(symbol: str):
    """
    Validate any NSE/BSE ticker and return basic quote info.
    Tries NSE (.NS) first, falls back to BSE (.BO).
    """
    sym = symbol.upper().strip().replace(" ", "")
    base = sym.replace(".NS", "").replace(".BO", "")
    attempted = []

    def probe(ticker: str):
        attempted.append(ticker)
        try:
            t = yf.Ticker(ticker)
            fast_info = {}
            exchange = "BSE" if ticker.endswith(".BO") else "NSE"
            currency = "INR"
            price = None
            try:
                fast_info = t.fast_info
                price = (fast_info.get("lastPrice")
                         or fast_info.get("regularMarketPrice")
                         or fast_info.get("previousClose")
                         or fast_info.get("regularMarketPreviousClose"))
                exchange = fast_info.get("exchange") or exchange
                currency = fast_info.get("currency") or currency
            except Exception:
                pass

            if not price:
                history = t.history(period="5d")
                if history is not None and not history.empty and "Close" in history:
                    close = history["Close"].dropna()
                    if not close.empty:
                        price = close.iloc[-1]

            if price and float(price) > 0:
                return {
                    "valid":    True,
                    "ticker":   ticker,
                    "name":     ticker,
                    "price":    round(float(price), 2),
                    "sector":   "",
                    "industry": "",
                    "exchange": exchange,
                    "currency": currency,
                }
        except Exception as exc:
            print(f"Search lookup failed for {ticker}: {exc}")
        return None

    result = probe(f"{base}.NS") or probe(f"{base}.BO") or probe(base)
    if result:
        return result
    tried = ", ".join(attempted)
    return {"valid": False, "error": f"'{symbol}' not found on NSE or BSE. Tried: {tried}."}


@app.get("/api/config/status")
async def config_status():
    """Returns which AI API keys are currently configured."""
    return get_keys_status()


@app.post("/api/config/keys")
async def save_config(payload: dict = Body(...)):
    """Save Claude and/or Groq API keys. Send {anthropic_key, groq_key}."""
    if payload.get("anthropic_key"):
        set_api_key("anthropic", payload["anthropic_key"])
    if payload.get("groq_key"):
        set_api_key("groq", payload["groq_key"])
    return {"status": "saved", **get_keys_status()}


# Mount static files last
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    import threading
    import webbrowser
    import socket

    def find_free_port(start=8000, end=8010):
        for port in range(start, end):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("0.0.0.0", port))
                    return port
                except OSError:
                    continue
        return start  # fallback

    PORT = find_free_port()
    URL  = f"http://localhost:{PORT}"

    def _open_browser():
        import time
        time.sleep(2.0)
        webbrowser.open(URL)

    threading.Thread(target=_open_browser, daemon=True).start()

    print("\n" + "═" * 54)
    print("  🚀  Antigravity TradeAI — Hybrid Expert System")
    print("═" * 54)
    print(f"  ➤  Open in browser  :  {URL}")
    print(f"  ➤  API docs         :  {URL}/docs")
    print("  ➤  Press Ctrl+C to stop the server")
    print("═" * 54 + "\n")

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
