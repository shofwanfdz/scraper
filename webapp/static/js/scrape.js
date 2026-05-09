/**
 * Scraping Tools - WebSocket Client
 * Handles real-time communication with backend
 */

let ws = null;
let jobId = null;

// DOM Elements
const formSection = document.getElementById('form-section');
const progressSection = document.getElementById('progress-section');
const resultSection = document.getElementById('result-section');
const progressLog = document.getElementById('progress-log');
const actionArea = document.getElementById('action-area');
const actionMessage = document.getElementById('action-message');
const btnStart = document.getElementById('btn-start');

// Form submit
document.getElementById('scrape-form').addEventListener('submit', function(e) {
    e.preventDefault();
    startScraping();
});

function startScraping() {
    const keyword = document.getElementById('keyword').value.trim();
    if (!keyword) { alert('Masukkan keyword!'); return; }

    const pages = parseInt(document.getElementById('pages').value) || 1;
    const mode = document.getElementById('mode').value;
    const minPrice = document.getElementById('min_price').value;
    const maxPrice = document.getElementById('max_price').value;
    const minRating = document.getElementById('min_rating').value;
    const sort = document.getElementById('sort').value;

    let filters = {};
    if (sort && sort !== '0') filters.sort = parseInt(sort);
    if (minPrice) filters.min_price = parseInt(minPrice);
    if (maxPrice) filters.max_price = parseInt(maxPrice);
    if (minRating) filters.min_rating = parseInt(minRating);

    // Blibli-specific filters
    const locationEl = document.getElementById('location');
    if (locationEl && locationEl.value) filters.location = locationEl.value;

    // Show progress, hide form
    formSection.style.display = 'none';
    progressSection.style.display = 'block';
    resultSection.style.display = 'none';
    progressLog.innerHTML = '';
    actionArea.style.display = 'none';

    // Connect WebSocket
    connectWebSocket(keyword, pages, mode, filters);
}

function connectWebSocket(keyword, pages, mode, filters) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}/ws/scrape`);

    ws.onopen = function() {
        addLog('Terhubung ke server...', 'status');
        // Send start command
        ws.send(JSON.stringify({
            action: 'start_scrape',
            marketplace: MARKETPLACE,
            keyword: keyword,
            pages: pages,
            mode: mode,
            filters: filters,
        }));
    };

    ws.onmessage = function(event) {
        const msg = JSON.parse(event.data);
        handleMessage(msg);
    };

    ws.onclose = function() {
        addLog('Koneksi terputus.', 'error');
    };

    ws.onerror = function() {
        addLog('Error koneksi WebSocket.', 'error');
    };
}

function handleMessage(msg) {
    switch (msg.type) {
        case 'status':
            addLog(msg.message, 'status');
            break;

        case 'progress':
            addLog(msg.message, 'progress');
            break;

        case 'need_action':
            addLog('⚠️ ' + msg.message, 'warning');
            showActionButton(msg.message);
            break;

        case 'complete':
            addLog('✅ ' + msg.message, 'progress');
            showResult(msg);
            break;

        case 'error':
            addLog('❌ ' + msg.message, 'error');
            break;
    }
}

function addLog(message, type) {
    const div = document.createElement('div');
    div.className = 'log-item log-' + type;
    const time = new Date().toLocaleTimeString('id-ID');
    div.textContent = `[${time}] ${message}`;
    progressLog.appendChild(div);
    progressLog.scrollTop = progressLog.scrollHeight;
}

function showActionButton(message) {
    actionArea.style.display = 'block';
    actionMessage.textContent = message;
}

function confirmAction() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'confirm' }));
        actionArea.style.display = 'none';
        addLog('Konfirmasi dikirim ✓', 'status');
    }
}

function showResult(msg) {
    progressSection.querySelector('.spinner').style.display = 'none';
    resultSection.style.display = 'block';
    document.getElementById('result-message').textContent =
        `${msg.total} produk berhasil di-scrape!`;

    if (msg.file) {
        const downloadLink = document.getElementById('download-link');
        downloadLink.href = `/api/download/${MARKETPLACE}/${msg.file}`;
        downloadLink.style.display = 'inline-block';

        // Set dashboard link with pre-selected file
        const dashboardLink = document.getElementById('dashboard-link');
        dashboardLink.href = `/dashboard?file=${MARKETPLACE}/${msg.file}`;
    }
}

function resetForm() {
    formSection.style.display = 'block';
    progressSection.style.display = 'none';
    resultSection.style.display = 'none';
    if (ws) ws.close();
}
