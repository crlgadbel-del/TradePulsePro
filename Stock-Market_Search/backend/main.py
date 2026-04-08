
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from analyzer import get_market_data, analyze_market, get_stock_history_for_chart, get_prediction_trajectory
from expert_engine import run_expert_analysis
import asyncio

STATIC_DIR = str(Path(__file__).parent.parent / "static")

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# List of active stocks (Nifty 50 / F&O stocks for high liquidity)
# Suffix .NS for NSE
WATCHLIST = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "SBIN.NS",
    "ADANIENT.NS", "TATAMOTORS.NS", "BAJFINANCE.NS", "AXISBANK.NS",
    "ICICIBANK.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS",
    "WIPRO.NS", "ASIANPAINT.NS", "BHARTIARTL.NS", "ITC.NS"
]

@app.get("/api/market-status")
async def get_market_status():
    data = get_market_data(WATCHLIST)
    if data is None:
        return {"error": "Failed to fetch data"}
    
    analysis = analyze_market(data, WATCHLIST)
    
    # Sort: Top Gainers/Losers/High Potentials
    # Pick top 3 "Strong Buy" or highest score
    opportunities = [x for x in analysis if x['signal'] in ['STRONG BUY', 'BUY', 'SELL']]
    
    return {
        "market_data": analysis,
        "top_picks": opportunities[:5] # Return top 5 interesting stocks
    }

@app.get("/api/stock-history/{symbol}")
async def get_stock_history(symbol: str):
    # Ensure symbol has .NS if missing and not index (assuming NSE)
    # The frontend passes just title for some, so keep safe
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
    """
    contexts: comma separated string e.g., "1h,2h,1d"
    """
    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        ticker = f"{symbol}.NS"
    else:
        ticker = symbol
        
    ctx_list = contexts.split(',')
    trajectory = get_prediction_trajectory(ticker, ctx_list)
    return trajectory

@app.get("/api/expert-analysis/{symbol}")
async def expert_analysis(symbol: str, investment: float = 10000):
    """
    Run full expert-based analysis with profit/loss projections.
    investment: Amount in INR to simulate (default 10000)
    """
    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        ticker = f"{symbol}.NS"
    else:
        ticker = symbol

    result = run_expert_analysis(ticker, investment)
    return result

# Mount static files for the frontend
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
