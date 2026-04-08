/**
 * TradePulse AI — Unified Trading Platform
 * Dashboard + Expert Analysis + Market Scanner
 */

const state = {
    riskLevel: 'medium',
    market: 'indian',
    signals: {},
    isScanning: false,
    currentChart: null,
    currentRsiChart: null,
    currentMacdChart: null,
    currentSymbol: null,
    currentInterval: '5m',
    realtimeInterval: null,
    candleSeries: null,
    currentView: 'dashboard',
    watchlistData: [],
};

const API_BASE = '';

// ==================== INIT ====================
function checkAuth() {
    const isAuth = sessionStorage.getItem('tradePulseAuth');
    const overlay = document.getElementById('loginOverlay');
    if (isAuth === 'true') {
        if (overlay) overlay.style.display = 'none';
    } else {
        if (overlay) overlay.style.display = 'flex';
    }
}

function handleLogin() {
    const u = document.getElementById('loginUsername').value;
    const p = document.getElementById('loginPassword').value;
    const err = document.getElementById('loginError');
    if (u === 'admin' && p === 'Utkarsh@2002') {
        sessionStorage.setItem('tradePulseAuth', 'true');
        err.textContent = '';
        checkAuth();
    } else {
        err.textContent = 'Invalid credentials';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    checkAuth();
    updateTime();
    setInterval(updateTime, 1000);
    loadDashboard();
    setupSearch();
    initTradingViewTicker();
    loadMarketStatus();
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeChartModal(); });
});

// ==================== VIEW SWITCH ====================
function switchView(view) {
    state.currentView = view;
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.getElementById(`nav-${view}`).classList.add('active');
    document.querySelectorAll('.view-panel').forEach(p => p.classList.remove('active'));
    document.getElementById(`view-${view}`).classList.add('active');

    if (view === 'scanner') loadWatchlistStatus();
    if (view === 'expert') loadQuickPicks();
}

// ==================== TIME ====================
function updateTime() {
    const now = new Date();
    document.getElementById('currentTime').textContent = now.toLocaleString('en-IN', {
        hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true,
        day: 'numeric', month: 'short', year: 'numeric'
    });
}

// ==================== SEARCH ====================
function getRecentSearches() {
    try { return JSON.parse(localStorage.getItem('tradePulseRecent')) || []; }
    catch(e) { return []; }
}
function saveRecentSearch(symbol) {
    let recent = getRecentSearches();
    recent = recent.filter(s => s !== symbol);
    recent.unshift(symbol);
    if (recent.length > 5) recent.pop();
    localStorage.setItem('tradePulseRecent', JSON.stringify(recent));
}

function setupSearch() {
    const input = document.getElementById('searchInput');
    const results = document.getElementById('searchResults');
    let debounceTimer;

    const showRecent = () => {
        const recent = getRecentSearches();
        if (recent.length > 0) {
            results.innerHTML = `<div style="padding: 8px 12px; font-size:0.75rem; color:var(--text-muted); font-weight:bold; letter-spacing:1px; text-transform:uppercase;">Recent Searches</div>` +
                recent.map(sym => `
                <div class="search-result-item" onclick="handleSearchSelect('${sym}')">
                    <span class="symbol">${sym}</span>
                </div>
            `).join('');
            results.classList.add('active');
        } else {
            results.classList.remove('active');
        }
    };

    input.addEventListener('focus', () => {
        if (input.value.trim().length === 0) showRecent();
    });

    input.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        const q = input.value.trim();
        if (q.length === 0) { showRecent(); return; }
        if (q.length < 2) { results.classList.remove('active'); return; }
        debounceTimer = setTimeout(async () => {
            try {
                const res = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(q)}`);
                const data = await res.json();
                if (data.length > 0) {
                    results.innerHTML = data.slice(0, 8).map(item => `
                        <div class="search-result-item" onclick="handleSearchSelect('${item.symbol}')">
                            <span class="symbol">${item.symbol}</span>
                            <span class="name">${item.name || ''}</span>
                        </div>
                    `).join('');
                    results.classList.add('active');
                } else {
                    results.classList.remove('active');
                }
            } catch (e) { results.classList.remove('active'); }
        }, 300);
    });

    input.addEventListener('blur', () => setTimeout(() => results.classList.remove('active'), 200));
}

function handleSearchSelect(symbol) {
    saveRecentSearch(symbol);
    document.getElementById('searchInput').value = '';
    document.getElementById('searchResults').classList.remove('active');
    openChartModal(symbol);
}

// ==================== RISK / MARKET ====================
function setRiskLevel(level) {
    state.riskLevel = level;
    document.querySelectorAll('.risk-card').forEach(c => c.classList.remove('active'));
    document.getElementById(`risk-${level}`).classList.add('active');
    loadDashboard();
}

async function setMarket(market) {
    state.market = market;
    document.querySelectorAll('.market-tab').forEach(t => {
        t.classList.remove('active');
        if (t.id === `tab-${market}`) t.classList.add('active');
    });
    const titleMap = { 'indian': 'All Indian Stocks', 'us': 'All US Stocks', 'crypto': 'Cryptocurrencies' };
    document.getElementById('listingTitle').textContent = titleMap[market] || 'Stocks';
    loadDashboard();
}

// ==================== DASHBOARD ====================
async function loadDashboard() {
    const tableBody = document.getElementById('stockTableBody');
    tableBody.innerHTML = `<tr><td colspan="10" style="text-align:center;padding:40px;"><div class="loading-spinner"></div></td></tr>`;

    try {
        const res = await fetch(`${API_BASE}/api/symbols?market=${state.market}`);
        const data = await res.json();
        let stocks = data[state.market] || [];
        renderStockTable(stocks);
        
        // Auto-run scanner when the dashboard loads to populate analysis instantly
        if (!state.isScanning) {
            setTimeout(scanMarket, 500);
        }
    } catch (e) {
        console.error('Data Load Error:', e);
        tableBody.innerHTML = `<tr><td colspan="10" style="text-align:center;color:var(--red);">Failed to load market data.</td></tr>`;
    }
}

async function scanMarket() {
    const btn = document.getElementById('scanBtn');
    btn.innerHTML = `<span>⏳</span> Scanning...`;
    btn.disabled = true;

    try {
        const res = await fetch(`${API_BASE}/api/scan?market=${state.market}&risk=${state.riskLevel}`);
        const data = await res.json();
        renderStockTable(data.signals || []);
        updateOverallStats(data.signals || []);
    } catch (e) { console.error(e); }

    btn.innerHTML = `<span>🔄</span> Scan Market`;
    btn.disabled = false;
}

function updateOverallStats(signals) {
    let b = 0, s = 0, h = 0;
    signals.forEach(sig => {
        if (sig.signal === 'BUY') b++;
        else if (sig.signal === 'SELL') s++;
        else h++;
    });
    document.getElementById('statBuy').textContent = b;
    document.getElementById('statSell').textContent = s;
    document.getElementById('statHold').textContent = h;
    document.getElementById('statScanned').textContent = signals.length;
}

// ==================== LOGO MAPPING ====================
const LOGO_DOMAINS = {
    'RELIANCE.NS':'ril.com','TCS.NS':'tcs.com','HDFCBANK.NS':'hdfcbank.com','INFY.NS':'infosys.com',
    'ICICIBANK.NS':'icicibank.com','HINDUNILVR.NS':'hul.co.in','SBIN.NS':'sbi.co.in','BHARTIARTL.NS':'airtel.in',
    'ITC.NS':'itcportal.com','KOTAKBANK.NS':'kotak.com','LT.NS':'larsentoubro.com','AXISBANK.NS':'axisbank.com',
    'BAJFINANCE.NS':'bajajfinserv.in','ASIANPAINT.NS':'asianpaints.com','MARUTI.NS':'marutisuzuki.com',
    'TITAN.NS':'titancompany.in','SUNPHARMA.NS':'sunpharma.com','TATAMOTORS.NS':'tatamotors.com',
    'WIPRO.NS':'wipro.com','HCLTECH.NS':'hcltech.com','ADANIENT.NS':'adani.com',
    'AAPL':'apple.com','MSFT':'microsoft.com','GOOGL':'google.com','AMZN':'amazon.com','NVDA':'nvidia.com',
    'META':'meta.com','TSLA':'tesla.com','JPM':'jpmorganchase.com','V':'visa.com',
    'AMD':'amd.com','NFLX':'netflix.com','DIS':'disney.com','UBER':'uber.com',
};

function getLogoUrl(symbol) {
    if (symbol.includes('-USD')) {
        const coin = symbol.replace('-USD', '').toLowerCase();
        return `https://assets.coincap.io/assets/icons/${coin}@2x.png`;
    }
    const domain = LOGO_DOMAINS[symbol] || `${symbol.split('.')[0].toLowerCase()}.com`;
    return `https://t2.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://${domain}&size=128`;
}

function handleLogoError(img) {
    img.style.display = 'none';
    if (img.nextElementSibling) img.nextElementSibling.style.display = 'flex';
}

// ==================== STOCK TABLE ====================
function renderStockTable(stocks) {
    const tableBody = document.getElementById('stockTableBody');
    tableBody.innerHTML = '';
    const sym = getCurrencySymbol();

    stocks.forEach(s => {
        const row = document.createElement('tr');
        const price = s.price ? `${sym}${fmtNum(s.price)}` : '—';
        const changePct = s.change_pct !== undefined ? `${s.change_pct.toFixed(2)}%` : '—';
        const changeCls = s.change >= 0 ? 'green' : (s.change < 0 ? 'red' : '');
        const signalCls = (s.signal || 'HOLD').toLowerCase();
        const logo = getLogoUrl(s.symbol);

        row.innerHTML = `
            <td>
                <div class="symbol-info">
                    <div class="logo-wrapper">
                        <img src="${logo}" class="stock-logo" onerror="handleLogoError(this)">
                        <div class="symbol-avatar" style="display:none;">${s.symbol[0]}</div>
                    </div>
                    <div class="symbol-ticker">${s.symbol}</div>
                </div>
            </td>
            <td><div class="symbol-name">${s.name || '—'}</div></td>
            <td class="price-cell">
                <div class="price-val">${price}</div>
                <div class="price-change ${changeCls}">${changePct}</div>
            </td>
            <td><span class="signal-badge ${signalCls}">${s.signal || 'WAIT'}</span></td>
            <td><span class="conf-val">${s.confidence ? (s.confidence * 100).toFixed(0) + '%' : '—'}</span></td>
            <td><span class="price-level entry">${s.entry_price ? sym + fmtNum(s.entry_price) : '—'}</span></td>
            <td><span class="price-level target">${s.target_price ? sym + fmtNum(s.target_price) : '—'}</span></td>
            <td><span class="price-level stoploss">${s.stop_loss ? sym + fmtNum(s.stop_loss) : '—'}</span></td>
            <td><span class="profit-val ${s.expected_profit_pct > 0 ? 'green' : ''}">${s.expected_profit_pct ? s.expected_profit_pct + '%' : '—'}</span></td>
            <td>
                <div class="action-group" style="display:flex;gap:4px;">
                    <button class="chart-btn" onclick="openChartModal('${s.symbol}')">Chart</button>
                    <button class="predict-btn" onclick="openExpertForSymbol('${s.symbol}')">Expert</button>
                </div>
            </td>
        `;
        tableBody.appendChild(row);
    });
}

// ==================== EXPERT ANALYSIS ====================
async function loadQuickPicks() {
    const grid = document.getElementById('quickPicksGrid');
    try {
        const res = await fetch(`${API_BASE}/api/watchlist-status`);
        const data = await res.json();
        if (data.error) { grid.innerHTML = `<div class="loading-placeholder">${data.error}</div>`; return; }

        state.watchlistData = data.market_data || [];
        const picks = data.top_picks || [];

        if (picks.length === 0 && state.watchlistData.length > 0) {
            // Show top 6 from watchlist by score
            const top = [...state.watchlistData].sort((a,b) => Math.abs(b.score) - Math.abs(a.score)).slice(0, 6);
            grid.innerHTML = top.map(s => renderQuickPickCard(s)).join('');
        } else if (picks.length > 0) {
            grid.innerHTML = picks.map(s => renderQuickPickCard(s)).join('');
        } else {
            grid.innerHTML = `<div class="loading-placeholder">No strong opportunities found. Market might be choppy.</div>`;
        }
    } catch (e) {
        grid.innerHTML = `<div class="loading-placeholder">Failed to load watchlist. Make sure server is running.</div>`;
    }
}

function renderQuickPickCard(stock) {
    const typeClass = stock.signal.includes('BUY') ? 'buy' : (stock.signal.includes('SELL') ? 'sell' : 'neutral');
    const symbolClean = stock.symbol.replace('.NS', '');
    const sym = getCurrencySymbol();
    return `
        <div class="quick-pick-card ${typeClass}" onclick="openExpertForSymbol('${stock.symbol}')">
            <div class="qp-header">
                <span class="qp-symbol">${symbolClean}</span>
                <span class="qp-signal signal-badge ${typeClass}">${stock.signal}</span>
            </div>
            <div class="qp-price">${sym}${stock.price} <span class="${stock.change >= 0 ? 'green' : 'red'}">(${stock.change > 0 ? '+' : ''}${stock.change}%)</span></div>
            <div class="qp-reason">${stock.reason}</div>
            <div class="qp-score">Score: ${stock.score}</div>
        </div>
    `;
}

function openExpertForSymbol(symbol) {
    closeChartModal();
    switchView('expert');
    const clean = symbol.replace('.NS', '').replace('.BO', '').replace('-USD', '');
    document.getElementById('expertSymbolInput').value = clean;
    runExpertAnalysis();
}

async function runExpertAnalysis() {
    const symbolRaw = document.getElementById('expertSymbolInput').value.trim();
    if (!symbolRaw) return;

    const investment = parseFloat(document.getElementById('expertInvestmentInput').value) || 10000;
    const loading = document.getElementById('expertLoadingPanel');
    const results = document.getElementById('expertResultsPanel');
    const btn = document.getElementById('btnRunExpert');

    btn.disabled = true;
    btn.textContent = '⏳ Analyzing...';
    loading.style.display = 'flex';
    results.style.display = 'none';

    try {
        const res = await fetch(`${API_BASE}/api/expert-analysis/${encodeURIComponent(symbolRaw)}?investment=${investment}`);
        const data = await res.json();

        loading.style.display = 'none';

        if (data.error) {
            results.style.display = 'block';
            results.innerHTML = `<div class="expert-error">⚠️ ${data.error}</div>`;
        } else {
            results.style.display = 'block';
            results.innerHTML = renderExpertHTML(data);
            animateConfidenceRing(data.expert_verdict?.confidence || 0);
        }
    } catch (e) {
        loading.style.display = 'none';
        results.style.display = 'block';
        results.innerHTML = `<div class="expert-error">⚠️ Failed to connect to expert engine</div>`;
    }

    btn.disabled = false;
    btn.textContent = '🧠 Run Expert Analysis';
}

function renderExpertHTML(data) {
    const v = data.expert_verdict || {};
    const pl = data.profit_loss || {};
    const ind = data.indicators || {};
    const sym = getCurrencySymbol();

    const verdictColor = v.verdict?.includes('BUY') ? 'buy' : (v.verdict?.includes('SELL') ? 'sell' : 'hold');

    // Verdict Banner
    let html = `
        <div class="expert-verdict-banner ${verdictColor}-verdict">
            <div class="verdict-left">
                <div class="verdict-label">EXPERT VERDICT</div>
                <div class="verdict-text ${verdictColor}-color">${v.verdict || 'HOLD'}</div>
                <div class="verdict-meta">
                    <span>Price: ${sym}${data.current_price || 0}</span>
                    <span>Day: ${data.day_change > 0 ? '+' : ''}${data.day_change || 0}%</span>
                </div>
            </div>
            <div class="verdict-right">
                <div class="confidence-ring" id="confidenceRing">
                    <svg viewBox="0 0 80 80">
                        <circle class="ring-bg" cx="40" cy="40" r="34"/>
                        <circle class="ring-fill" id="confidenceArc" cx="40" cy="40" r="34"/>
                    </svg>
                    <div class="confidence-val" id="confidenceVal">${v.confidence || 0}%</div>
                </div>
                <div class="confidence-label">Confidence</div>
            </div>
        </div>
    `;

    // P/L Section
    if (pl && pl.direction !== 'NONE') {
        const dirIcon = pl.direction === 'LONG' ? '📈' : '📉';
        const dirColor = pl.direction === 'LONG' ? 'var(--green)' : 'var(--red)';

        html += `
            <div class="expert-section">
                <h4 class="expert-section-title">💰 Profit / Loss Projection</h4>
                <div class="pl-meta-grid">
                    <div class="pl-meta-card"><div class="pl-meta-label">Direction</div><div class="pl-meta-value" style="color:${dirColor}">${dirIcon} ${pl.direction}</div></div>
                    <div class="pl-meta-card"><div class="pl-meta-label">Entry</div><div class="pl-meta-value">${sym}${pl.entry}</div></div>
                    <div class="pl-meta-card"><div class="pl-meta-label">Shares</div><div class="pl-meta-value">${pl.shares}</div></div>
                    <div class="pl-meta-card"><div class="pl-meta-label">Investment</div><div class="pl-meta-value">${sym}${(pl.investment || 0).toLocaleString()}</div></div>
                    <div class="pl-meta-card"><div class="pl-meta-label">Stop Loss</div><div class="pl-meta-value" style="color:var(--red)">${sym}${pl.stop_loss}</div></div>
                </div>
        `;

        if (pl.scenarios && pl.scenarios.length > 0) {
            html += `<div class="pl-scenarios-grid">`;
            pl.scenarios.forEach(s => {
                const isProfit = s.profit >= 0;
                html += `
                    <div class="scenario-card" style="border-left: 3px solid ${s.color || (isProfit ? 'var(--green)' : 'var(--red)')}">
                        <div class="scenario-label" style="color:${s.color}">${s.label}</div>
                        <div class="scenario-target">Target: ${sym}${s.target}</div>
                        <div class="scenario-profit" style="color:${isProfit ? 'var(--green)' : 'var(--red)'}">
                            ${isProfit ? '+' : ''}${sym}${Math.abs(s.profit).toLocaleString()}
                        </div>
                        <div class="scenario-pct" style="color:${s.color}">${isProfit ? '+' : ''}${s.profit_pct}%</div>
                    </div>
                `;
            });
            html += `</div>`;
        }

        // Risk
        html += `
            <div class="pl-risk-row">
                <div class="risk-mini-card">
                    <span class="risk-mini-icon">🛡️</span>
                    <div>
                        <div class="risk-mini-label">Max Loss</div>
                        <div class="risk-mini-value" style="color:var(--red)">-${sym}${Math.abs(pl.max_loss || 0).toLocaleString()} (${pl.max_loss_pct || 0}%)</div>
                    </div>
                </div>
                <div class="risk-mini-card">
                    <span class="risk-mini-icon">⚖️</span>
                    <div>
                        <div class="risk-mini-label">Risk : Reward</div>
                        <div class="risk-mini-value" style="color:${pl.risk_reward >= 1.5 ? 'var(--green)' : 'var(--red)'}">1 : ${pl.risk_reward}</div>
                    </div>
                </div>
            </div>
        `;

        if (pl.recommendation) {
            html += `<div class="pl-recommendation">📋 ${pl.recommendation}</div>`;
        }
        html += `</div>`;
    } else {
        html += `<div class="expert-section"><div class="pl-recommendation">⏸️ No trade recommended. Wait for clearer signals.</div></div>`;
    }

    // Technical Indicators
    const indItems = [
        { name: 'RSI', value: ind.rsi, color: ind.rsi < 30 ? 'var(--green)' : (ind.rsi > 70 ? 'var(--red)' : 'var(--text-primary)') },
        { name: 'MACD Hist', value: ind.macd_histogram?.toFixed(4), color: ind.macd_histogram > 0 ? 'var(--green)' : 'var(--red)' },
        { name: 'MACD Cross', value: ind.macd_crossover === 'none' ? '—' : ind.macd_crossover?.toUpperCase(), color: ind.macd_crossover === 'bullish' ? 'var(--green)' : (ind.macd_crossover === 'bearish' ? 'var(--red)' : 'var(--text-secondary)') },
        { name: 'Bollinger', value: ind.bollinger_position?.replace(/_/g, ' ').toUpperCase(), color: 'var(--blue)' },
        { name: 'ATR', value: `${sym}${ind.atr}`, color: 'var(--yellow)' },
        { name: 'VWAP', value: `${sym}${ind.vwap}`, color: 'var(--blue)' },
        { name: 'vs VWAP', value: ind.price_vs_vwap?.toUpperCase(), color: ind.price_vs_vwap === 'above' ? 'var(--green)' : (ind.price_vs_vwap === 'below' ? 'var(--red)' : 'var(--text-secondary)') },
        { name: 'Vol Ratio', value: `${ind.volume_ratio}x`, color: ind.volume_ratio > 1.5 ? 'var(--yellow)' : 'var(--text-primary)' },
        { name: 'SMA 20', value: `${sym}${ind.sma_20}`, color: 'var(--text-primary)' },
        { name: 'Stoch %K', value: ind.stochastic_k, color: ind.stochastic_k < 20 ? 'var(--green)' : (ind.stochastic_k > 80 ? 'var(--red)' : 'var(--text-primary)') },
        { name: 'Support', value: `${sym}${ind.support}`, color: 'var(--green)' },
        { name: 'Resistance', value: `${sym}${ind.resistance}`, color: 'var(--red)' },
    ];

    html += `
        <div class="expert-section">
            <h4 class="expert-section-title">📊 Technical Indicators</h4>
            <div class="indicators-chip-grid">
                ${indItems.map(i => `
                    <div class="indicator-chip">
                        <div class="indicator-name">${i.name}</div>
                        <div class="indicator-value" style="color:${i.color}">${i.value ?? '—'}</div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;

    // Rules Fired
    if (v.rules_fired && v.rules_fired.length > 0) {
        html += `
            <div class="expert-section">
                <h4 class="expert-section-title">⚙️ Expert Rules Fired</h4>
                <div class="rules-list">
                    ${v.rules_fired.map(rule => {
                        const t = rule.type.toLowerCase();
                        return `
                            <div class="rule-item ${t}-rule">
                                <span class="rule-badge ${t}-badge">${rule.type}</span>
                                <div class="rule-body">
                                    <div class="rule-name">${rule.rule}</div>
                                    <div class="rule-detail">${rule.detail}</div>
                                </div>
                                <span class="rule-weight">+${rule.weight}</span>
                            </div>
                        `;
                    }).join('')}
                </div>
                <div class="score-bar-container">
                    <div class="score-bar-label">
                        <span style="color:var(--green)">BUY ${v.buy_score}</span>
                        <span style="color:var(--text-secondary)">Net: ${v.net_score}</span>
                        <span style="color:var(--red)">SELL ${v.sell_score}</span>
                    </div>
                    <div class="score-bar-track">
                        <div class="score-bar-buy" style="width:${v.buy_score + v.sell_score > 0 ? (v.buy_score / (v.buy_score + v.sell_score) * 100) : 50}%"></div>
                        <div class="score-bar-sell" style="width:${v.buy_score + v.sell_score > 0 ? (v.sell_score / (v.buy_score + v.sell_score) * 100) : 50}%"></div>
                    </div>
                </div>
            </div>
        `;
    }

    return html;
}

function animateConfidenceRing(confidence) {
    setTimeout(() => {
        const arc = document.getElementById('confidenceArc');
        if (!arc) return;
        const circumference = 2 * Math.PI * 34;
        const offset = circumference - (confidence / 100) * circumference;
        arc.style.strokeDasharray = circumference;
        arc.style.strokeDashoffset = offset;

        // Color
        const verdict = document.querySelector('.expert-verdict-banner');
        if (verdict?.classList.contains('buy-verdict')) arc.style.stroke = 'var(--green)';
        else if (verdict?.classList.contains('sell-verdict')) arc.style.stroke = 'var(--red)';
        else arc.style.stroke = 'var(--yellow)';
    }, 100);
}

// ==================== WATCHLIST / SCANNER ====================
async function loadWatchlistStatus() {
    const container = document.getElementById('watchlistOpportunities');
    const tbody = document.getElementById('watchlistTableBody');
    container.innerHTML = '<div class="loading-placeholder">Analyzing market data...</div>';
    tbody.innerHTML = '';

    try {
        const res = await fetch(`${API_BASE}/api/watchlist-status`);
        const data = await res.json();

        if (data.error) {
            container.innerHTML = `<div class="loading-placeholder">${data.error}</div>`;
            return;
        }

        // Opportunities
        const picks = data.top_picks || [];
        if (picks.length > 0) {
            container.innerHTML = picks.map(s => renderQuickPickCard(s)).join('');
        } else {
            container.innerHTML = `<div class="loading-placeholder">No strong opportunities found currently.</div>`;
        }

        // Table
        const allData = data.market_data || [];
        allData.forEach(stock => {
            const row = document.createElement('tr');
            row.style.cursor = 'pointer';
            row.onclick = () => openExpertForSymbol(stock.symbol);

            const changeClass = stock.change >= 0 ? 'green' : 'red';
            let signalColor = 'var(--text-secondary)';
            if (stock.signal.includes('BUY')) signalColor = 'var(--green)';
            if (stock.signal.includes('SELL')) signalColor = 'var(--red)';

            const getPredIcon = (pred) => {
                if (pred === 'UP') return '<span class="green">↑</span>';
                if (pred === 'DOWN') return '<span class="red">↓</span>';
                return '<span style="color:grey">—</span>';
            };
            const preds = stock.time_predictions || {};
            const sym = getCurrencySymbol();

            row.innerHTML = `
                <td style="font-weight:500">${stock.symbol.replace('.NS', '')}</td>
                <td style="font-family:'JetBrains Mono',monospace">${sym}${stock.price}</td>
                <td class="${changeClass}">${stock.change > 0 ? '+' : ''}${stock.change}%</td>
                <td>${getPredIcon(preds['1m'])}</td>
                <td>${getPredIcon(preds['2m'])}</td>
                <td>${getPredIcon(preds['1h'])}</td>
                <td>${getPredIcon(preds['2h'])}</td>
                <td style="color:${signalColor};font-weight:600">${stock.signal}</td>
                <td>
                    <div style="background:rgba(255,255,255,0.08);width:60px;height:6px;border-radius:3px;overflow:hidden;">
                        <div style="width:${Math.min(Math.abs(stock.score), 100)}%;background:${stock.score > 0 ? 'var(--green)' : 'var(--red)'};height:100%;"></div>
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });
    } catch (e) {
        container.innerHTML = `<div class="loading-placeholder">Failed to load. Server might be unavailable.</div>`;
    }
}

// ==================== CHART MODAL ====================
async function openChartModal(symbol) {
    state.currentSymbol = symbol;
    state.currentInterval = '5m';

    // Reset toolbar buttons
    document.querySelectorAll('.tf-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('.tf-btn:nth-child(2)').classList.add('active');

    document.getElementById('chartModal').style.display = 'flex';
    document.body.style.overflow = 'hidden';

    const avatar = document.getElementById('chartSymbolAvatar');
    const logo = getLogoUrl(symbol);
    avatar.innerHTML = `
        <img src="${logo}" class="stock-logo-lg" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
        <div class="symbol-avatar-lg" style="display:none;">${symbol[0]}</div>
    `;

    document.getElementById('chartSymbolName').textContent = symbol.split('.')[0];
    document.getElementById('chartSymbolTag').textContent = symbol;

    document.getElementById('chartSignalLoading').style.display = 'flex';
    document.getElementById('chartSignalContent').style.display = 'none';
    document.getElementById('aiAnalysisContent').innerHTML = '';

    startRealtimeTicker(symbol);
    
    // Render Native Lightweight Chart
    renderLightweightChart(symbol, '5m');

    await Promise.all([loadSignalPanel(symbol), loadAiAnalysis(symbol), loadNewsPanel(symbol)]);
}

function changeChartInterval(interval) {
    if (state.currentInterval === interval) return;
    state.currentInterval = interval;
    
    // Update active button state
    const buttons = document.querySelectorAll('.tf-btn');
    buttons.forEach(btn => {
        if (btn.textContent === interval) btn.classList.add('active');
        else btn.classList.remove('active');
    });

    // Re-fetch and re-render the chart with the new interval
    renderLightweightChart(state.currentSymbol, interval);
}

async function renderLightweightChart(symbol, interval = '5m') {
    const chartArea = document.querySelector('.chart-area');
    
    if(state.currentChart) { state.currentChart.remove(); state.currentChart = null; }
    if(state.rsiChart) { state.rsiChart.remove(); state.rsiChart = null; }
    if(state.macdChart) { state.macdChart.remove(); state.macdChart = null; }

    chartArea.innerHTML = `
        <div id="lwchart_container" style="width: 100%; flex: 5; position: relative;"></div>
        <div id="rsi_container" style="width: 100%; flex: 1.5; position: relative; border-top: 2px solid rgba(30, 34, 45, 1);">
            <div style="position: absolute; top: 4px; left: 8px; font-size: 11px; font-weight: bold; color: #a855f7; z-index: 10;">RSI (14)</div>
        </div>
        <div id="macd_container" style="width: 100%; flex: 1.5; position: relative; border-top: 2px solid rgba(30, 34, 45, 1);">
            <div style="position: absolute; top: 4px; left: 8px; font-size: 11px; font-weight: bold; color: #3b82f6; z-index: 10;">MACD (12, 26, 9)</div>
        </div>
    `;
    
    if (window.LightweightCharts) {
        const commonOpts = {
            layout: { background: { type: 'solid', color: '#0a0e17' }, textColor: '#94a3b8' },
            grid: { vertLines: { color: 'rgba(42, 46, 57, 0.3)' }, horzLines: { color: 'rgba(42, 46, 57, 0.3)' } },
            crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
            timeScale: { visible: false, borderColor: 'rgba(197, 203, 206, 0.4)' },
            rightPriceScale: { borderColor: 'rgba(197, 203, 206, 0.4)' }
        };

        state.currentChart = LightweightCharts.createChart(document.getElementById('lwchart_container'), { 
            ...commonOpts, 
            timeScale: { visible: true, borderColor: 'rgba(197, 203, 206, 0.4)' }
        });
        state.candleSeries = state.currentChart.addCandlestickSeries({
            upColor: '#10b981', downColor: '#ef4444', borderDownColor: '#ef4444',
            borderUpColor: '#10b981', wickDownColor: '#ef4444', wickUpColor: '#10b981'
        });

        state.rsiChart = LightweightCharts.createChart(document.getElementById('rsi_container'), commonOpts);
        state.rsiSeries = state.rsiChart.addLineSeries({ color: '#a855f7', lineWidth: 1.5 });
        state.rsiChart.priceScale().applyOptions({ autoScale: false, scaleMargins: { top: 0.1, bottom: 0.1 }, minValue: 0, maxValue: 100 });
        
        state.macdChart = LightweightCharts.createChart(document.getElementById('macd_container'), commonOpts);
        state.macdSeries = state.macdChart.addLineSeries({ color: '#3b82f6', lineWidth: 1.5 });
        state.macdSignalSeries = state.macdChart.addLineSeries({ color: '#f59e0b', lineWidth: 1.5 });
        state.macdHistSeries = state.macdChart.addHistogramSeries({
             color: '#10b981', priceFormat: { type: 'volume' }, priceScaleId: ''
        });

        const mScale = state.currentChart.timeScale();
        const rScale = state.rsiChart.timeScale();
        const dScale = state.macdChart.timeScale();
        mScale.subscribeVisibleLogicalRangeChange(r => { if(r) { rScale.setVisibleLogicalRange(r); dScale.setVisibleLogicalRange(r); }});
        
        try {
            const periodMap = { '1m': '1d', '5m': '5d', '15m': '5d', '30m': '1mo', '1h': '1mo', '1d': '1y' };
            const reqPeriod = periodMap[interval] || '5d';
            const res = await fetch(`${API_BASE}/api/stock-data/${encodeURIComponent(symbol)}?period=${reqPeriod}&interval=${interval}&markers=true`);
            const data = await res.json();
            if (data && data.data && data.data.length > 0) {
                state.lastChartData = data.data;
                state.candleSeries.setData(data.data);
                if (data.markers) state.candleSeries.setMarkers(data.markers);

                const rsiData = data.data.filter(d => d.rsi != null).map(d => ({time: d.time, value: d.rsi}));
                if (rsiData.length) state.rsiSeries.setData(rsiData);

                const mData = data.data.filter(d => d.macd != null).map(d => ({time: d.time, value: d.macd}));
                const sData = data.data.filter(d => d.macd_signal != null).map(d => ({time: d.time, value: d.macd_signal}));
                const hData = data.data.filter(d => d.macd_hist != null).map(d => ({time: d.time, value: d.macd_hist, color: d.macd_hist > 0 ? 'rgba(16, 185, 129, 0.4)' : 'rgba(239, 68, 68, 0.4)'}));
                
                if (mData.length) state.macdSeries.setData(mData);
                if (sData.length) state.macdSignalSeries.setData(sData);
                if (hData.length) state.macdHistSeries.setData(hData);

                state.currentChart.timeScale().fitContent();
            }
        } catch(e) {}
    }
}

// ==================== SIGNAL & AI ====================
async function loadSignalPanel(symbol) {
    const content = document.getElementById('chartSignalContent');
    try {
        const res = await fetch(`${API_BASE}/api/signal/${encodeURIComponent(symbol)}?risk=${state.riskLevel}`);
        const sig = await res.json();
        document.getElementById('chartSignalLoading').style.display = 'none';
        content.style.display = 'block';
        content.innerHTML = generateSignalHTML(sig);
    } catch (e) {
        content.innerHTML = `<div class="error-msg">Signal Analysis Unavailable</div>`;
    }
}

function generateSignalHTML(sig) {
    const st = (sig.signal || 'HOLD').toLowerCase();
    const conf = (sig.confidence || 0) * 100;
    return `
        <div class="signal-action-box-lg ${st}">
            <div class="sal-label">${sig.signal || 'HOLD'}</div>
            <div class="sal-sub">Confidence: ${conf.toFixed(1)}% • Strength: ${sig.signal_strength || 'Normal'}</div>
        </div>
        <div class="chart-signal-grid">
            <div class="chart-signal-card"><div class="cs-label">📉 Expected Profit</div><div class="cs-value green">${sig.expected_profit_pct || 0}%</div></div>
            <div class="chart-signal-card"><div class="cs-label">⏱️ Hold Period</div><div class="cs-value">${sig.holding_period || 'Intraday'}</div></div>
            <div class="chart-signal-card"><div class="cs-label">📰 Sentiment</div><div class="cs-value">${sig.sentiment_label || 'Neutral'}</div></div>
            <div class="chart-signal-card"><div class="cs-label">📊 Buy/Sell Ratio</div><div class="cs-value">${sig.buy_count || 0}/${sig.sell_count || 0}</div></div>
        </div>
    `;
}

async function loadAiAnalysis(symbol) {
    const cont = document.getElementById('aiAnalysisContent');
    const loading = document.getElementById('aiAnalysisLoading');
    loading.style.display = 'block';
    try {
        const res = await fetch(`${API_BASE}/api/ai-analysis/${encodeURIComponent(symbol)}?risk=${state.riskLevel}`);
        const data = await res.json();
        loading.style.display = 'none';
        if (data.ai_report) {
            cont.innerHTML = typeof marked !== 'undefined' ? marked.parse(data.ai_report) : data.ai_report;
        }
    } catch (e) { loading.style.display = 'none'; }
}

// ==================== REAL-TIME TICKER ====================
function startRealtimeTicker(symbol) {
    stopRealtimeTicker();
    fetchRealtimePrice(symbol);
    state.realtimeInterval = setInterval(() => fetchRealtimePrice(symbol), 3000);
}

function stopRealtimeTicker() { if (state.realtimeInterval) clearInterval(state.realtimeInterval); }

async function fetchRealtimePrice(symbol) {
    try {
        const res = await fetch(`${API_BASE}/api/realtime/${encodeURIComponent(symbol)}`);
        const d = await res.json();
        const sym = getCurrencySymbol();
        if (d.price) {
            document.getElementById('realtimePrice').textContent = `${sym}${fmtNum(d.price)}`;
            document.getElementById('realtimeHigh').textContent = `${sym}${fmtNum(d.high)}`;
            document.getElementById('realtimeLow').textContent = `${sym}${fmtNum(d.low)}`;
            document.getElementById('realtimeVol').textContent = fmtVol(d.volume);
            
            // Sync live ticker directly into the chart's last plotted candle
            if (state.candleSeries && state.lastChartData && state.lastChartData.length > 0) {
                let lastBar = state.lastChartData[state.lastChartData.length - 1];
                let livePrice = parseFloat(d.price);
                lastBar.close = livePrice;
                if (livePrice > lastBar.high) lastBar.high = livePrice;
                if (livePrice < lastBar.low) lastBar.low = livePrice;
                state.candleSeries.update(lastBar);
            }
        }
    } catch(e) {}
}

function closeChartModal(event) {
    if (event && event.target !== event.currentTarget) return;
    document.getElementById('chartModal').style.display = 'none';
    document.body.style.overflow = '';
    stopRealtimeTicker();
}

// ==================== NEWS & HOLIDAYS ====================
async function loadNewsPanel(symbol) {
    const cont = document.getElementById('newsContainer');
    const loading = document.getElementById('newsLoading');
    loading.style.display = 'block';
    cont.innerHTML = '';
    try {
        const res = await fetch(`${API_BASE}/api/news/${encodeURIComponent(symbol)}`);
        const data = await res.json();
        loading.style.display = 'none';
        
        if (data.articles && data.articles.length > 0) {
            cont.innerHTML = data.articles.map(a => {
                const imgStr = a.image ? `<img src="${a.image}" class="news-img" onerror="this.style.display='none'">` : `<div class="news-img" style="display:flex;align-items:center;justify-content:center;background:var(--bg-secondary);font-size:1.5rem;">📰</div>`;
                const date = a.published ? new Date(a.published).toLocaleDateString('en-IN', {month:'short', day:'numeric'}) : '';
                return `
                    <div class="news-article">
                        <a href="${a.url}" target="_blank">
                            ${imgStr}
                            <div class="news-content">
                                <div class="news-title">${a.title}</div>
                                <div class="news-meta">
                                    <span>${a.source}</span>
                                    <span>${date}</span>
                                </div>
                            </div>
                        </a>
                    </div>
                `;
            }).join('');
        } else {
            cont.innerHTML = `<div class="expert-error">No recent news available.</div>`;
        }
    } catch (e) { 
        loading.style.display = 'none';
        cont.innerHTML = `<div class="expert-error">Failed to load news.</div>`;
    }
}

async function loadMarketStatus() {
    try {
        const res = await fetch(`${API_BASE}/api/holidays`);
        const data = await res.json();
        
        // Holiday logic
        if (data.is_holiday_today) {
            document.getElementById('holidayBanner').style.display = 'block';
            document.getElementById('holidayName').textContent = data.holiday_name;
            document.getElementById('marketTimerBanner').style.display = 'none';
        } else {
            initMarketTimer();
        }
    } catch(e) { console.error('Holidays error', e); }
}

function initMarketTimer() {
    setInterval(async () => {
        try {
            const res = await fetch(`${API_BASE}/api/market-status`);
            const data = await res.json();
            const ind = data.indian;
            
            const dot = document.querySelector('#marketTimerBanner .timer-dot');
            if (dot) dot.className = ind.is_open ? 'timer-dot open' : 'timer-dot closed';
            const modDot = document.querySelector('#modalTimerBanner .timer-dot');
            if (modDot) modDot.className = ind.is_open ? 'timer-dot open' : 'timer-dot closed';
            
            const timeStr = formatSeconds(ind.timer_seconds || 0);

            const mLabel = document.getElementById('marketTimerLabel');
            if (mLabel) mLabel.textContent = ind.timer_label + ': ';
            const mVal = document.getElementById('marketTimerValue');
            if (mVal) mVal.textContent = timeStr;

            const modVal = document.getElementById('modalTimerValue');
            if (modVal) modVal.textContent = ind.timer_label + ' ' + timeStr;
            
        } catch(e) {}
    }, 1000);
}

function formatSeconds(s) {
    if (s <= 0) return '00:00:00';
    const hrs = Math.floor(s / 3600).toString().padStart(2, '0');
    const mins = Math.floor((s % 3600) / 60).toString().padStart(2, '0');
    const secs = (s % 60).toString().padStart(2, '0');
    return `${hrs}:${mins}:${secs}`;
}

// ==================== TV TICKER ====================
function initTradingViewTicker() {
    const container = document.getElementById('tvTickerTape');
    if (!container) return;
    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js';
    script.async = true;
    script.innerHTML = JSON.stringify({
        "symbols": [
            { "proName": "BSE:SENSEX", "title": "Sensex" },
            { "proName": "NSE:NIFTY", "title": "Nifty 50" },
            { "proName": "NSE:BANKNIFTY", "title": "Bank Nifty" },
            { "proName": "NASDAQ:AAPL", "title": "Apple" },
            { "proName": "BINANCE:BTCUSDT", "title": "Bitcoin" }
        ],
        "showSymbolLogo": true,
        "isTransparent": true,
        "displayMode": "adaptive",
        "colorTheme": "dark",
        "locale": "in"
    });
    container.appendChild(script);
}

// ==================== UTILS ====================
function getCurrencySymbol() {
    if (state.market === 'us' || state.market === 'crypto') return '$';
    return '₹';
}
function fmtNum(n) { return (n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
function fmtVol(n) {
    if (!n) return '0';
    if (n >= 1e7) return (n / 1e7).toFixed(1) + 'Cr';
    if (n >= 1e5) return (n / 1e5).toFixed(1) + 'L';
    return n.toLocaleString('en-IN');
}
