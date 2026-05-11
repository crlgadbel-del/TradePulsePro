
const API_BASE = window.TRADEAI_API_BASE || 
    (window.location.pathname.startsWith('/stock-search') ? '/stock-search/api' : '/api');
let currentMarketData = [];
let activeSymbol = null;
let activeTickerFull = null;   

let _livePriceTimer   = null;  
let _autoAnalyseTimer = null;  
let _countdownTimer   = null;  
let _countdownSec     = 60;    

const POPULAR_STOCKS = [
  'RELIANCE','TCS','HDFCBANK','INFY','ICICIBANK','HINDUNILVR','SBIN','BHARTIARTL',
  'KOTAKBANK','LT','AXISBANK','ASIANPAINT','MARUTI','TITAN','SUNPHARMA','WIPRO',
  'BAJFINANCE','ITC','ONGC','NTPC','POWERGRID','ULTRACEMCO','JSWSTEEL','TATASTEEL',
  'TATAMOTORS','ADANIENT','ADANIPORTS','COALINDIA','TECHM','HCLTECH','DRREDDY',
  'DIVISLAB','CIPLA','EICHERMOT','HEROMOTOCO','BAJAJFINSV','BPCL','NESTLEIND',
  'SBILIFE','HDFCLIFE','ZOMATO','PAYTM','NAUKRI','IRCTC','DMART','POLICYBZR',
  'TATACONSUM','PIDILITIND','BERGEPAINT','TORNTPHARM','MUTHOOTFIN','PFC','RECLTD',
  'CANBK','UNIONBANK','BANKBARODA','INDUSINDBK','FEDERALBNK','YESBANK','RBLBANK',
  'IDEA','GAIL','IOC','HINDPETRO','PETRONET','TATAPOWER','ADANIGREEN','ADANIPOWER',
  'SIEMENS','ABB','BEL','HAL','BHEL','SAIL','NMDC','HINDALCO','VEDL',
  'ZYDUSLIFE','LUPIN','AUROPHARMA','BIOCON','IPCALAB','ALKEM','GLENMARK',
  'PERSISTENT','LTIM','MPHASIS','COFORGE','KPITTECH','TATAELXSI'
];

async function fetchMarketData() {
    try {
        const response = await fetch(`${API_BASE}/market-status`);
        const data = await response.json();
        if (data.error) { console.error(data.error); return; }
        currentMarketData = data.market_data;
        updatePredictions(data.top_picks);
        updateTable(data.market_data);
        updateClock();
        if (activeSymbol) {
            const stock = currentMarketData.find(s => 
                s.symbol === activeSymbol || 
                s.symbol.replace('.NS', '').replace('.BO', '') === activeSymbol
            );
            if (stock) populateModal(stock);
        }
    } catch (error) { console.error('Error fetching data:', error); }
}

function updatePredictions(picks) {
    const container = document.getElementById('predictions');
    container.innerHTML = '';
    picks.forEach(stock => {
        const card = document.createElement('div');
        const typeClass = stock.signal.includes('BUY') ? 'buy' : (stock.signal.includes('SELL') ? 'sell' : 'neutral');
        card.className = `prediction-card ${typeClass}`;
        card.onclick = () => openModalForStock(stock.symbol);
        card.innerHTML = `
            <div class="card-header"><span class="stock-name">${stock.symbol.replace('.NS', '')}</span><span class="signal-badge">${stock.signal}</span></div>
            <div class="stock-price">₹${stock.price} <span class="${stock.change >= 0 ? 'trend-up' : 'trend-down'}">(${stock.change}%)</span></div>
            <div class="reason">Strategy: ${stock.reason}</div>
            <div class="confidence-score">Confidence: ${stock.score}</div>
        `;
        container.appendChild(card);
    });
}

function updateTable(data) {
    const tbody = document.getElementById('market-table');
    tbody.innerHTML = '';
    data.forEach(stock => {
        const row = document.createElement('tr');
        const changeClass = stock.change >= 0 ? 'trend-up' : 'trend-down';
        row.onclick = () => openModalForStock(stock.symbol);
        const getPredIcon = (pred) => {
            if (pred === 'UP') return '↑';
            if (pred === 'DOWN') return '↓';
            return '—';
        };
        const preds = stock.time_predictions || {};
        row.innerHTML = `
            <td>${stock.symbol.replace('.NS', '')}</td>
            <td>₹${stock.price}</td>
            <td class="${changeClass}">${stock.change}%</td>
            <td>${getPredIcon(preds['1m'])}</td>
            <td>${getPredIcon(preds['5m'])}</td>
            <td>${getPredIcon(preds['1h'])}</td>
            <td style="font-weight:600">${stock.signal}</td>
            <td><div class="score-bar"><div class="score-fill" style="width:${Math.abs(stock.score)}%; background:${stock.score > 0 ? 'var(--accent-green)':'var(--accent-red)'}"></div></div></td>
        `;
        tbody.appendChild(row);
    });
}

function openModalForStock(symbol) {
    activeSymbol = symbol;
    activeTickerFull = symbol.includes('.') ? symbol : symbol + '.NS';
    const stock = currentMarketData.find(s => s.symbol === symbol);
    document.getElementById('expert-results').style.display = 'none';
    document.getElementById('expert-loading').style.display = 'none';
    if(stock) populateModal(stock);
    document.getElementById('stock-modal').style.display = 'flex';
    startLiveModalRefresh();
    runExpertAnalysis();
}

function populateModal(stock) {
    document.getElementById('modal-title').innerText = stock.symbol.replace('.NS', '');
    document.getElementById('modal-price').innerText = `₹${stock.price}`;
    document.getElementById('modal-price').style.color = stock.change >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';

    const trades = stock.trades || {};
    const predictions = stock.time_predictions || {};

    const fillCard = (elementId, label, timeframeKey) => {
        const el = document.getElementById(elementId);
        if (!el) return;
        const trade = trades[timeframeKey];
        const pred = predictions[timeframeKey];
        if (!trade) { el.innerHTML = '<div>No Data</div>'; return; }
        const type = trade.action.toLowerCase();
        el.className = `trade-card ${type}`;
        el.innerHTML = `
            <div class="trade-header">${label} <span class="${pred === 'UP' ? 'trend-up' : 'trend-down'}">${trade.action}</span></div>
            <div class="trade-values">Entry: ₹${trade.entry}<br>Target: ₹${trade.target}<br>Stop: ₹${trade.stop_loss}</div>
        `;
    };

    ['1m', '2m', '3m', '4m', '5m'].forEach((tf, i) => fillCard(`pred-${tf}`, `${i + 1} Min`, tf));
    ['1h', '2h', '3h', '4h', '5h'].forEach((tf, i) => fillCard(`pred-${tf}`, `${i + 1} Hour`, tf));

    fetchHistoryAndRenderLog(stock.symbol);
}

function startLiveModalRefresh() {
    stopLiveModalRefresh();
    _livePriceTimer = setInterval(pollLivePrice, 10000);
    _countdownSec = 60;
    _countdownTimer = setInterval(() => {
        _countdownSec--;
        updateCountdownDisplay();
        if (_countdownSec <= 0) { _countdownSec = 60; runExpertAnalysis(); }
    }, 1000);
}

function stopLiveModalRefresh() {
    clearInterval(_livePriceTimer);
    clearInterval(_countdownTimer);
}

async function pollLivePrice() {
    if (!activeTickerFull) return;
    try {
        const res = await fetch(`${API_BASE}/search-stock/${encodeURIComponent(activeTickerFull)}`);
        const info = await res.json();
        if (info.valid) {
            const priceEl = document.getElementById('modal-price');
            if (priceEl) {
                priceEl.innerText = `₹${info.price}`;
                const dot = document.getElementById('live-dot');
                if (dot) { dot.style.opacity = '0'; setTimeout(() => dot.style.opacity = '1', 200); }
            }
        }
    } catch (e) {}
}

function updateCountdownDisplay() {
    const el = document.getElementById('analyse-countdown');
    if (el) el.textContent = `Auto-refresh in ${_countdownSec}s`;
}

async function runExpertAnalysis(overrideTicker = null) {
    const sym = overrideTicker || activeTickerFull || activeSymbol;
    if (!sym) return;
    const investment = parseFloat(document.getElementById('investment-input').value) || 10000;
    const loading = document.getElementById('expert-loading');
    const results = document.getElementById('expert-results');
    
    loading.style.display = 'flex';
    results.style.display = 'none';

    try {
        const response = await fetch(`${API_BASE}/expert-analysis/${encodeURIComponent(sym)}?investment=${investment}`);
        const data = await response.json();
        if (data.error) { loading.innerHTML = `<span style="color:var(--accent-red)">⚠️ ${data.error}</span>`; return; }
        renderExpertResults(data);
    } catch (e) { loading.innerHTML = `<span>⚠️ Analysis failed</span>`; }
}

function renderExpertResults(data) {
    document.getElementById('expert-loading').style.display = 'none';
    document.getElementById('expert-results').style.display = 'block';

    const hybrid = data.hybrid_verdict || { verdict: 'HOLD', confidence: 50 };
    document.getElementById('verdict-text').textContent = hybrid.verdict;
    document.getElementById('confidence-val').textContent = `${hybrid.confidence}%`;
    
    renderIntradayTiming(data.intraday_timing);
    renderAICouncil(data.meta_ensemble);
    renderMLAnalysis(data.ml_analysis, data.regression, hybrid);
    if (data.profit_loss) renderProfitLoss(data.profit_loss, data.current_price);
    renderIndicators(data.indicators);
    renderRules(data.expert_verdict);

    if (data.trades && data.time_predictions) {
        data.price = data.current_price;
        populateModal(data);
    }
}

function renderProfitLoss(pl, currentPrice) {
    const meta = document.getElementById('pl-meta');
    meta.innerHTML = `
        <div class="pl-meta-card">Label: Direction, Value: ${pl.direction}</div>
        <div class="pl-meta-card">Label: Entry, Value: ₹${pl.entry}</div>
        <div class="pl-meta-card">Label: Stop Loss, Value: ₹${pl.stop_loss}</div>
    `;
    const scenarios = document.getElementById('pl-scenarios');
    scenarios.innerHTML = (pl.scenarios || []).map(s => `
        <div class="scenario-card">
            <div>${s.label}</div>
            <div>Target: ₹${s.target}</div>
            <div style="color:${s.profit >= 0 ? 'var(--accent-green)':'var(--accent-red)'}">₹${s.profit} (${s.profit_pct}%)</div>
        </div>
    `).join('');
}

function renderIndicators(inds) {
    const grid = document.getElementById('indicators-grid');
    if (!inds) return;
    grid.innerHTML = Object.entries(inds).map(([k, v]) => `
        <div class="indicator-chip">
            <div class="indicator-name">${k.toUpperCase()}</div>
            <div class="indicator-value">${v}</div>
        </div>
    `).join('');
}

function renderMLAnalysis(ml, reg, hybrid) {
    if (!ml) return;
    document.getElementById('ml-ensemble-signal').textContent = ml.ml_signal;
    document.getElementById('ml-predicted-return').textContent = `Return: ${ml.predicted_return_pct}%`;
    const featEl = document.getElementById('ml-feature-list');
    featEl.innerHTML = Object.entries(ml.feature_importance || {}).map(([n, v]) => `<div>${n}: ${v.toFixed(1)}%</div>`).join('');
}

function renderRules(v) {
    const list = document.getElementById('rules-list');
    list.innerHTML = (v.rules_fired || []).map(r => `
        <div class="rule-item">
            <span class="rule-badge">${r.type}</span>
            <div class="rule-name">${r.rule}</div>
            <div class="rule-weight">+${r.weight}</div>
        </div>
    `).join('');
}

function renderIntradayTiming(t) {
    if (!t) return;
    document.getElementById('timing-session-name').textContent = t.current_session?.name || 'Session';
    document.getElementById('t-entry-price').textContent = `₹${t.entry?.price || '—'}`;
    document.getElementById('t-exit-target').textContent = `🎯 ₹${t.exit?.price_target || '—'}`;
    document.getElementById('timing-note').textContent = t.strategy_note || '';
}

function renderAICouncil(meta) {
    if (!meta) return;
    document.getElementById('council-final-badge').textContent = meta.final_verdict;
    const grid = document.getElementById('council-grid');
    grid.innerHTML = (meta.model_breakdown || []).map(m => `
        <div class="cg-card">
            <div class="cg-name">${m.name}</div>
            <div class="cg-sig">${m.signal}</div>
        </div>
    `).join('');
}

async function fetchHistoryAndRenderLog(symbol) {
    const res = await fetch(`${API_BASE}/stock-history/${symbol}`);
    const data = await res.json();
    const log = document.getElementById('history-log');
    log.innerHTML = (data.data || []).map((p, i) => `<div>${data.labels[i]}: ₹${p}</div>`).join('');
}

function initSearch() {
    const input = document.getElementById('stock-search-input');
    input.onkeydown = e => { if (e.key === 'Enter') doSearch(); };
    document.getElementById('btn-stock-search').onclick = doSearch;
}

async function doSearch() {
    const input = document.getElementById('stock-search-input');
    const status = document.getElementById('search-status');
    const raw = input.value.trim();
    status.textContent = `Validating ${raw}...`;
    const res = await fetch(`${API_BASE}/search-stock/${encodeURIComponent(raw)}`);
    const info = await res.json();
    if (info.valid) {
        status.textContent = `Found: ${info.name}`;
        openModalForStock(info.ticker);
    } else {
        status.textContent = `Not found: ${info.error}`;
    }
}

function updateClock() { document.getElementById('clock').innerText = new Date().toLocaleTimeString(); }

window.onload = () => {
    initSearch();
    fetchMarketData();
    setInterval(fetchMarketData, 30000);
};

document.getElementById('close-modal-btn').onclick = () => {
    document.getElementById('stock-modal').style.display = 'none';
    stopLiveModalRefresh();
};
