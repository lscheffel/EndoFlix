import UltraWebSocket from './websocket.js';
import { updateDashboard, showError, loadSessions } from './dashboard.js';
import { initControls } from './controls.js';

let analyticsData = {};
window.analyticsData = analyticsData;

async function fetchAnalytics(params = {}) {
    try {
        const url = new URL('/analytics', window.location.origin);
        Object.keys(params).forEach(key => {
            if (params[key]) url.searchParams.set(key, params[key]);
        });
        const response = await fetch(url);
        if (!response.ok) throw new Error('Erro ao carregar análises');
        analyticsData = await response.json();
        window.analyticsData = analyticsData;
        updateDashboard(analyticsData);
    } catch (error) {
        console.error('Erro ao buscar análises:', error);
        showError();
    }
}

function initThemeToggle() {
    document.getElementById('themeToggle').addEventListener('change', (e) => {
        document.body.classList.toggle('bg-light', e.target.checked);
        document.body.classList.toggle('bg-dark', !e.target.checked);
        document.body.classList.toggle('text-dark', e.target.checked);
        document.body.classList.toggle('text-light', !e.target.checked);
        document.querySelectorAll('.card').forEach(card => {
            card.classList.toggle('bg-light', e.target.checked);
            card.classList.toggle('bg-dark', !e.target.checked);
            card.classList.toggle('text-dark', e.target.checked);
            card.classList.toggle('text-light', !e.target.checked);
        });
        document.querySelectorAll('.table').forEach(table => {
            table.classList.toggle('table-light', e.target.checked);
            table.classList.toggle('table-dark', !e.target.checked);
        });
    });
}

function init() {
    const ws = new UltraWebSocket();
    ws.connect();
    initControls(ws);
    initThemeToggle();
    initTableControls();

    // Initial load
    loadTableData();
    loadSessions();

    // Set up periodic refresh as fallback
    setInterval(() => {
        if (!ws.connected) {
            loadTableData();
        }
    }, 30000); // 30 seconds fallback
}

function initTableControls() {
    const searchInput = document.getElementById('searchInput');
    const sortBy = document.getElementById('sortBy');
    const sortOrder = document.getElementById('sortOrder');
    const limitSelect = document.getElementById('limitSelect');
    const refreshBtn = document.getElementById('refreshBtn');

    // Debounce search
    let searchTimeout;
    searchInput.addEventListener('input', () => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            localStorage.setItem('currentPage', '1'); // Reset to page 1 on search
            loadTableData();
        }, 300);
    });

    [sortBy, sortOrder, limitSelect].forEach(el => {
        el.addEventListener('change', () => {
            localStorage.setItem('currentPage', '1'); // Reset to page 1
            loadTableData();
        });
    });

    refreshBtn.addEventListener('click', loadTableData);
}

function loadTableData() {
    const params = {
        page: localStorage.getItem('currentPage') || 1,
        limit: document.getElementById('limitSelect').value,
        search: document.getElementById('searchInput').value,
        sort_by: document.getElementById('sortBy').value,
        sort_order: document.getElementById('sortOrder').value
    };
    fetchAnalytics(params);
}

function changePage(page) {
    localStorage.setItem('currentPage', page);
    loadTableData();
}

// Make changePage global
window.changePage = changePage;

// Start the app when DOM is ready
document.addEventListener('DOMContentLoaded', init);