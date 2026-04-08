
const API_BASE = 'http://localhost:8000/api';
let currentMarketData = [];
let activeSymbol = null;

// ─── Data Fetching ───────────────────────────────────────────────────────────

async function fetchMarketData() {
    try {
        const response = await fetch(`${API_BASE}/market-status`);
        const data = await response.json();

        if (data.error) {
            console.error(data.error);
            return;
        }

        currentMarketData = data.market_data;
        updatePredictions(data.top_picks);
        updateTable(data.market_data);
        updateClock();

        if (activeSymbol) {
            const stock = currentMarketData.find(s => s.symbol === activeSymbol);
            if (stock) populateModal(stock);
        }

    } catch (error) {
        console.error('Error fetching data:', error);
    }
}

// ─── Prediction Cards ────────────────────────────────────────────────────────

function updatePredictions(picks) {
    const container = document.getElementById('predictions');
    container.innerHTML = '';

    if (picks.length === 0) {
        container.innerHTML = '<div class="loading">No strong opportunities found currently. Market might be choppy.</div>';
        return;
    }

    picks.forEach(stock => {
        const card = document.createElement('div');
        const typeClass = stock.signal.includes('BUY') ? 'buy' : (stock.signal.includes('SELL') ? 'sell' : 'neutral');

        card.className = `prediction-card ${typeClass}`;
        card.onclick = () => openModalForStock(stock.symbol);
        card.style.cursor = 'pointer';

        card.innerHTML = `
            <div class="card-header">
                <span class="stock-name">${stock.symbol.replace('.NS', '')}</span>
                <span class="signal-badge">${stock.signal}</span>
            </div>
            <div class="stock-price">₹${stock.price} <span class="${stock.change >= 0 ? 'trend-up' : 'trend-down'}" style="font-size: 0.9em">(${stock.change}%)</span></div>
            <div class="reason">Strategy: ${stock.reason}</div>
            <div style="margin-top: 10px; font-size: 0.8rem; opacity: 0.6;">Confidence Score: ${stock.score}</div>
        `;
        container.appendChild(card);
    });
}

// ─── Watchlist Table ─────────────────────────────────────────────────────────

function updateTable(data) {
    const tbody = document.getElementById('market-table');
    tbody.innerHTML = '';

    data.forEach(stock => {
        const row = document.createElement('tr');
        const changeClass = stock.change >= 0 ? 'trend-up' : 'trend-down';
        row.onclick = () => openModalForStock(stock.symbol);

        let signalColor = 'var(--text-secondary)';
        if (stock.signal.includes('BUY')) signalColor = 'var(--accent-green)';
        if (stock.signal.includes('SELL')) signalColor = 'var(--accent-red)';

        const getPredIcon = (pred) => {
            if (pred === 'UP') return '<span class="trend-up">↑</span>';
            if (pred === 'DOWN') return '<span class="trend-down">↓</span>';
            return '<span style="color: grey">—</span>';
        };

        const preds = stock.time_predictions || {};

        row.innerHTML = `
            <td style="font-weight: 500">${stock.symbol.replace('.NS', '')}</td>
            <td style="font-family: var(--font-mono, monospace)">₹${stock.price}</td>
            <td class="${changeClass}">${stock.change > 0 ? '+' : ''}${stock.change}%</td>
            <td>${getPredIcon(preds['30s'])}</td>
            <td>${getPredIcon(preds['1m'])}</td>
            <td>${getPredIcon(preds['2m'])}</td>
            <td>${getPredIcon(preds['1h'])}</td>
            <td>${getPredIcon(preds['2h'])}</td>
            <td style="color: ${signalColor}; font-weight: 600">${stock.signal}</td>
            <td>
                <div style="background: rgba(255,255,255,0.08); width: 60px; height: 6px; border-radius: 3px; overflow: hidden;">
                    <div style="width: ${Math.min(Math.abs(stock.score), 100)}%; background: ${stock.score > 0 ? 'var(--accent-green)' : 'var(--accent-red)'}; height: 100%;"></div>
                </div>
            </td>
        `;
        tbody.appendChild(row);
    });
}

// ─── Modal ───────────────────────────────────────────────────────────────────

function openModalForStock(symbol) {
    activeSymbol = symbol;
    const stock = currentMarketData.find(s => s.symbol === symbol);
    if (!stock) return;

    // Reset expert panel
    document.getElementById('expert-results').style.display = 'none';
    document.getElementById('expert-loading').style.display = 'none';

    populateModal(stock);
    document.getElementById('stock-modal').style.display = 'block';

    // Auto-run expert analysis
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

        if (!trade) {
            el.innerHTML = '<div>No Data</div>';
            return;
        }

        let type = 'wait';
        if (trade.action === 'BUY') type = 'buy';
        if (trade.action === 'SELL') type = 'sell';

        el.className = `trade-card ${type}`;

        el.innerHTML = `
            <div class="trade-header">
                ${label}
                <span class="${pred === 'UP' ? 'trend-up' : (pred === 'DOWN' ? 'trend-down' : '')}">${trade.action}</span>
            </div>
            <div class="trade-values">
                Entry: <span>₹${trade.entry}</span><br>
                Target: <span>₹${trade.target}</span><br>
                Stop: <span>₹${trade.stop_loss}</span>
            </div>
        `;
    };

    ['1m', '2m', '3m', '4m', '5m'].forEach((tf, i) => fillCard(`pred-${tf}`, `${i + 1} Min`, tf));
    ['1h', '2h', '3h', '4h', '5h'].forEach((tf, i) => fillCard(`pred-${tf}`, `${i + 1} Hour`, tf));

    document.getElementById('history-log').innerHTML = '<div style="padding:20px; text-align:center; color:var(--text-secondary);">Loading history...</div>';
    fetchHistoryAndRenderLog(stock.symbol);
}

// ─── Expert Analysis ─────────────────────────────────────────────────────────

async function runExpertAnalysis() {
    if (!activeSymbol) return;

    const investment = parseFloat(document.getElementById('investment-input').value) || 10000;
    const btn = document.getElementById('btn-run-expert');
    const loading = document.getElementById('expert-loading');
    const results = document.getElementById('expert-results');

    btn.disabled = true;
    btn.textContent = 'Analyzing...';
    loading.style.display = 'flex';
    results.style.display = 'none';

    try {
        const response = await fetch(`${API_BASE}/expert-analysis/${activeSymbol}?investment=${investment}`);
        const data = await response.json();

        if (data.error) {
            loading.innerHTML = `<span style="color: var(--accent-red);">⚠️ ${data.error}</span>`;
            return;
        }

        renderExpertResults(data);
    } catch (e) {
        loading.innerHTML = `<span style="color: var(--accent-red);">⚠️ Failed to fetch expert analysis</span>`;
        console.error('Expert analysis error:', e);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Run Analysis';
    }
}

function renderExpertResults(data) {
    const loading = document.getElementById('expert-loading');
    const results = document.getElementById('expert-results');

    loading.style.display = 'none';
    results.style.display = 'block';

    // ── Verdict Banner ──
    const verdict = data.expert_verdict;
    const banner = document.getElementById('expert-verdict-banner');
    banner.className = 'verdict-banner';

    let verdictColor = 'hold-color';
    let bannerClass = 'hold-verdict';
    if (verdict.verdict.includes('BUY')) { verdictColor = 'buy-color'; bannerClass = 'buy-verdict'; }
    else if (verdict.verdict.includes('SELL')) { verdictColor = 'sell-color'; bannerClass = 'sell-verdict'; }
    banner.classList.add(bannerClass);

    document.getElementById('verdict-text').className = `verdict-text ${verdictColor}`;
    document.getElementById('verdict-text').textContent = verdict.verdict;

    // Confidence ring animation
    const confidence = verdict.confidence;
    document.getElementById('confidence-val').textContent = `${confidence}%`;
    const circumference = 2 * Math.PI * 34; // r=34
    const offset = circumference - (confidence / 100) * circumference;
    const arc = document.getElementById('confidence-arc');
    arc.style.strokeDasharray = circumference;

    // Pick ring color based on verdict
    if (verdict.verdict.includes('BUY')) arc.style.stroke = 'var(--accent-green)';
    else if (verdict.verdict.includes('SELL')) arc.style.stroke = 'var(--accent-red)';
    else arc.style.stroke = 'var(--accent-yellow)';

    // Animate
    setTimeout(() => { arc.style.strokeDashoffset = offset; }, 100);

    // ── Profit / Loss ──
    const pl = data.profit_loss;
    if (pl) {
        renderProfitLoss(pl, data.current_price);
    }

    // ── Technical Indicators ──
    renderIndicators(data.indicators);

    // ── Rules Fired ──
    renderRules(verdict);
}

function renderProfitLoss(pl, currentPrice) {
    const metaContainer = document.getElementById('pl-meta');
    const scenariosContainer = document.getElementById('pl-scenarios');
    const riskContainer = document.getElementById('pl-risk');
    const recContainer = document.getElementById('pl-recommendation');

    // Meta info cards
    const directionColor = pl.direction === 'LONG' ? 'var(--accent-green)' :
        (pl.direction === 'SHORT' ? 'var(--accent-red)' : 'var(--text-secondary)');
    const directionIcon = pl.direction === 'LONG' ? '📈' : (pl.direction === 'SHORT' ? '📉' : '⏸️');

    metaContainer.innerHTML = `
        <div class="pl-meta-card">
            <div class="pl-meta-label">Direction</div>
            <div class="pl-meta-value" style="color: ${directionColor}">${directionIcon} ${pl.direction}</div>
        </div>
        <div class="pl-meta-card">
            <div class="pl-meta-label">Entry Price</div>
            <div class="pl-meta-value">₹${pl.entry}</div>
        </div>
        <div class="pl-meta-card">
            <div class="pl-meta-label">Shares</div>
            <div class="pl-meta-value">${pl.shares}</div>
        </div>
        <div class="pl-meta-card">
            <div class="pl-meta-label">Investment</div>
            <div class="pl-meta-value">₹${pl.investment.toLocaleString()}</div>
        </div>
        <div class="pl-meta-card">
            <div class="pl-meta-label">Stop Loss</div>
            <div class="pl-meta-value" style="color: var(--accent-red)">₹${pl.stop_loss}</div>
        </div>
    `;

    // Scenario cards
    if (pl.scenarios && pl.scenarios.length > 0) {
        scenariosContainer.innerHTML = pl.scenarios.map(s => {
            const isProfit = s.profit >= 0;
            const profitSign = isProfit ? '+' : '';
            const borderColor = s.color || (isProfit ? 'var(--accent-green)' : 'var(--accent-red)');
            const bgColor = s.color ?
                `${s.color}10` :
                (isProfit ? 'rgba(0, 230, 118, 0.05)' : 'rgba(255, 23, 68, 0.05)');

            return `
                <div class="scenario-card" style="background: ${bgColor}; border-color: ${borderColor}30;">
                    <div class="scenario-label" style="color: ${borderColor}">${s.label}</div>
                    <div class="scenario-target">Target: <span>₹${s.target}</span></div>
                    <div class="scenario-profit" style="color: ${isProfit ? 'var(--accent-green)' : 'var(--accent-red)'}">
                        ${profitSign}₹${Math.abs(s.profit).toLocaleString()}
                    </div>
                    <div class="scenario-pct" style="color: ${borderColor}">
                        ${profitSign}${s.profit_pct}%
                    </div>
                </div>
            `;
        }).join('');
    } else {
        scenariosContainer.innerHTML = '<div style="color: var(--text-secondary); padding: 16px;">No trade scenarios — HOLD recommended</div>';
    }

    // Risk cards
    if (pl.direction !== 'NONE') {
        riskContainer.innerHTML = `
            <div class="risk-card loss-card">
                <div class="risk-icon">🛡️</div>
                <div class="risk-detail">
                    <div class="risk-label">Max Loss</div>
                    <div class="risk-value" style="color: var(--accent-red)">-₹${Math.abs(pl.max_loss).toLocaleString()}</div>
                    <div class="risk-sub">${pl.max_loss_pct}% of investment</div>
                </div>
            </div>
            <div class="risk-card rr-card">
                <div class="risk-icon">⚖️</div>
                <div class="risk-detail">
                    <div class="risk-label">Risk : Reward</div>
                    <div class="risk-value" style="color: ${pl.risk_reward >= 1.5 ? 'var(--accent-green)' : (pl.risk_reward >= 1 ? 'var(--accent-orange)' : 'var(--accent-red)')}">
                        1 : ${pl.risk_reward}
                    </div>
                    <div class="risk-sub">${pl.risk_reward >= 2 ? 'Excellent' : pl.risk_reward >= 1.5 ? 'Good' : pl.risk_reward >= 1 ? 'Fair' : 'Poor'}</div>
                </div>
            </div>
        `;
    } else {
        riskContainer.innerHTML = '';
    }

    // Recommendation
    recContainer.innerHTML = `<strong>📋 Recommendation:</strong> ${pl.recommendation}`;
}

function renderIndicators(indicators) {
    const grid = document.getElementById('indicators-grid');
    if (!indicators) { grid.innerHTML = ''; return; }

    const items = [
        { name: 'RSI', value: indicators.rsi, color: indicators.rsi < 30 ? 'var(--accent-green)' : (indicators.rsi > 70 ? 'var(--accent-red)' : 'var(--text-primary)') },
        { name: 'MACD Hist', value: indicators.macd_histogram?.toFixed(4), color: indicators.macd_histogram > 0 ? 'var(--accent-green)' : 'var(--accent-red)' },
        { name: 'MACD Cross', value: indicators.macd_crossover === 'none' ? '—' : indicators.macd_crossover.toUpperCase(), color: indicators.macd_crossover === 'bullish' ? 'var(--accent-green)' : (indicators.macd_crossover === 'bearish' ? 'var(--accent-red)' : 'var(--text-secondary)') },
        { name: 'Bollinger', value: indicators.bollinger_position?.replace('_', ' ').toUpperCase(), color: 'var(--accent-blue)' },
        { name: 'BB Upper', value: `₹${indicators.bollinger_upper}`, color: 'var(--text-primary)' },
        { name: 'BB Lower', value: `₹${indicators.bollinger_lower}`, color: 'var(--text-primary)' },
        { name: 'ATR', value: `₹${indicators.atr}`, color: 'var(--accent-orange)' },
        { name: 'VWAP', value: `₹${indicators.vwap}`, color: 'var(--accent-blue)' },
        { name: 'vs VWAP', value: indicators.price_vs_vwap?.toUpperCase(), color: indicators.price_vs_vwap === 'above' ? 'var(--accent-green)' : (indicators.price_vs_vwap === 'below' ? 'var(--accent-red)' : 'var(--text-secondary)') },
        { name: 'Vol Ratio', value: `${indicators.volume_ratio}x`, color: indicators.volume_ratio > 1.5 ? 'var(--accent-orange)' : 'var(--text-primary)' },
        { name: 'SMA 20', value: `₹${indicators.sma_20}`, color: 'var(--text-primary)' },
        { name: 'Stoch %K', value: indicators.stochastic_k, color: indicators.stochastic_k < 20 ? 'var(--accent-green)' : (indicators.stochastic_k > 80 ? 'var(--accent-red)' : 'var(--text-primary)') },
        { name: 'Stoch %D', value: indicators.stochastic_d, color: 'var(--text-primary)' },
        { name: 'Support', value: `₹${indicators.support}`, color: 'var(--accent-green)' },
        { name: 'Resistance', value: `₹${indicators.resistance}`, color: 'var(--accent-red)' },
    ];

    grid.innerHTML = items.map((item, i) => `
        <div class="indicator-chip" style="animation-delay: ${i * 0.03}s">
            <div class="indicator-name">${item.name}</div>
            <div class="indicator-value" style="color: ${item.color}">${item.value}</div>
        </div>
    `).join('');
}

function renderRules(verdict) {
    const list = document.getElementById('rules-list');
    const barContainer = document.getElementById('score-bar-container');

    if (!verdict.rules_fired || verdict.rules_fired.length === 0) {
        list.innerHTML = '<div style="color: var(--text-secondary); padding: 12px;">No rules fired</div>';
        barContainer.innerHTML = '';
        return;
    }

    list.innerHTML = verdict.rules_fired.map((rule, i) => {
        const type = rule.type.toLowerCase();
        return `
            <div class="rule-item ${type}-rule" style="animation-delay: ${i * 0.05}s">
                <span class="rule-badge ${type}-badge">${rule.type}</span>
                <div class="rule-body">
                    <div class="rule-name">${rule.rule}</div>
                    <div class="rule-detail">${rule.detail}</div>
                </div>
                <span class="rule-weight">+${rule.weight}</span>
            </div>
        `;
    }).join('');

    // Score bar
    const total = verdict.buy_score + verdict.sell_score;
    const buyPct = total > 0 ? (verdict.buy_score / total * 100) : 50;
    const sellPct = total > 0 ? (verdict.sell_score / total * 100) : 50;

    barContainer.innerHTML = `
        <div class="score-bar-label">
            <span style="color: var(--accent-green)">BUY ${verdict.buy_score}</span>
            <span style="color: var(--text-secondary)">Net: ${verdict.net_score}</span>
            <span style="color: var(--accent-red)">SELL ${verdict.sell_score}</span>
        </div>
        <div class="score-bar-track">
            <div class="score-bar-buy" style="width: ${buyPct}%"></div>
            <div class="score-bar-sell" style="width: ${sellPct}%"></div>
        </div>
    `;
}

// ─── History / Trajectory (existing) ─────────────────────────────────────────

async function fetchHistoryAndRenderLog(symbol) {
    try {
        const response = await fetch(`${API_BASE}/stock-history/${symbol}`);
        const data = await response.json();

        if (data.error) { console.error("History error:", data.error); return; }

        if (data.forecast_5m) {
            document.getElementById('ai-forecast-container').style.display = 'flex';
            document.getElementById('forecast-value').innerText = `₹${data.forecast_5m}`;
        } else {
            document.getElementById('ai-forecast-container').style.display = 'none';
        }

        renderHistoryLog(data.labels, data.data);
    } catch (e) {
        console.error("Failed to load history", e);
    }
}

function renderHistoryLog(labels, prices) {
    const logContainer = document.getElementById('history-log');
    logContainer.innerHTML = '';

    const reversedLabels = [...labels].reverse();
    const reversedPrices = [...prices].reverse();

    reversedLabels.forEach((time, index) => {
        const price = reversedPrices[index];
        const item = document.createElement('div');
        item.className = 'history-item';

        let trendClass = '';
        if (index < reversedPrices.length - 1) {
            const prevPrice = reversedPrices[index + 1];
            if (price > prevPrice) trendClass = 'trend-up';
            else if (price < prevPrice) trendClass = 'trend-down';
        }

        item.innerHTML = `
            <span style="color: var(--text-secondary);">${time}</span>
            <span class="${trendClass}" style="font-weight: 500; font-family: var(--font-mono, monospace);">₹${price}</span>
        `;
        logContainer.appendChild(item);
    });
}

// ─── Prediction / Trajectory ─────────────────────────────────────────────────

function setupCheckboxes() {
    document.getElementById('btn-predict').onclick = async () => {
        if (!activeSymbol) return;

        const checkboxes = document.querySelectorAll('.hist-check:checked');
        const contexts = Array.from(checkboxes).map(cb => cb.value);

        if (contexts.length === 0) {
            alert("Please select at least one history period.");
            return;
        }

        const btn = document.getElementById('btn-predict');
        const originalText = btn.innerText;
        btn.innerText = "Predicting...";
        btn.disabled = true;

        await fetchTrajectory(activeSymbol, contexts);

        btn.innerText = originalText;
        btn.disabled = false;
    };
}

async function fetchTrajectory(symbol, contexts) {
    try {
        const ctxStr = contexts.join(',');
        const response = await fetch(`${API_BASE}/predict-trajectory/${symbol}?contexts=${ctxStr}`);
        const data = await response.json();
        renderTrajectory(data);
    } catch (e) {
        console.error("Trajectory failed", e);
    }
}

function renderTrajectory(data) {
    const container = document.getElementById('trajectory-container');
    const log = document.getElementById('trajectory-log');
    log.innerHTML = '';
    container.style.display = 'block';

    const priceText = document.getElementById('modal-price').innerText.replace('₹', '');
    const currentPrice = parseFloat(priceText) || 0;

    Object.keys(data).forEach(ctx => {
        const points = data[ctx];
        if (points.length === 0) return;

        points.forEach(pt => {
            const item = document.createElement('div');
            item.className = 'trajectory-item';

            let colorStyle = 'color: var(--text-primary)';
            if (pt.price > currentPrice) colorStyle = 'color: var(--accent-green)';
            else if (pt.price < currentPrice) colorStyle = 'color: var(--accent-red)';

            item.innerHTML = `
                <span>+${pt.minutes_ahead}m (${pt.time})</span>
                <span style="font-weight:600; font-family: var(--font-mono); ${colorStyle}">₹${pt.price}</span>
                <span style="font-size:0.78rem; opacity:0.6">${ctx} Base</span>
            `;
            log.appendChild(item);
        });

        const sep = document.createElement('div');
        sep.style.borderBottom = '1px dashed rgba(255,255,255,0.08)';
        log.appendChild(sep);
    });
}

// ─── Modal Close ─────────────────────────────────────────────────────────────

document.getElementById('close-modal-btn').onclick = () => {
    document.getElementById('stock-modal').style.display = 'none';
    activeSymbol = null;
    document.getElementById('trajectory-container').style.display = 'none';
};

window.onclick = (event) => {
    const modal = document.getElementById('stock-modal');
    if (event.target === modal) {
        modal.style.display = 'none';
        activeSymbol = null;
        document.getElementById('trajectory-container').style.display = 'none';
    }
};

// ─── Expert Button ───────────────────────────────────────────────────────────

document.getElementById('btn-run-expert').onclick = () => runExpertAnalysis();

// ─── Clock ───────────────────────────────────────────────────────────────────

function updateClock() {
    const now = new Date();
    document.getElementById('clock').innerText = now.toLocaleTimeString();
}

// ─── Init ────────────────────────────────────────────────────────────────────

setupCheckboxes();
fetchMarketData();
setInterval(fetchMarketData, 15000);
