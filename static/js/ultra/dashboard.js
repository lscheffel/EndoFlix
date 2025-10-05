let analyticsData = {};
let charts = {};

function formatTime(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hours}h ${minutes}m ${secs}s`;
}

function updateStatsCards(data) {
    document.getElementById('videoCount').textContent = data.stats.videos || 0;
    document.getElementById('playlistCount').textContent = data.stats.playlists || 0;
    document.getElementById('sessionCount').textContent = data.stats.sessions || 0;
    document.getElementById('activeSessionsCount').textContent = data.stats.active_sessions || 0;
    document.getElementById('totalPlayTime').textContent = formatTime(data.stats.total_play_time || 0);
    document.getElementById('userActivity24h').textContent = data.stats.user_activity_24h || 0;
    document.getElementById('realtimeStatus').textContent = 'Atualizado em ' + new Date(data.timestamp).toLocaleTimeString();
}

function updateCharts(data) {
    // Playlist chart
    if (charts.playlistChart) {
        charts.playlistChart.destroy();
    }
    charts.playlistChart = new Chart(document.getElementById('playlistChart'), {
        type: 'bar',
        data: {
            labels: (data.playlists || []).map(p => p.name),
            datasets: [{
                label: 'Reproduções',
                data: (data.playlists || []).map(p => p.play_count),
                backgroundColor: 'rgba(75, 192, 192, 0.5)',
                borderColor: 'rgba(75, 192, 192, 1)',
                borderWidth: 1
            }]
        },
        options: { scales: { y: { beginAtZero: true } } }
    });

    // File type chart
    if (charts.fileTypeChart) {
        charts.fileTypeChart.destroy();
    }
    charts.fileTypeChart = new Chart(document.getElementById('fileTypeChart'), {
        type: 'pie',
        data: {
            labels: Object.keys(data.file_types || {}),
            datasets: [{
                data: Object.values(data.file_types || {}),
                backgroundColor: ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF']
            }]
        }
    });

    // Timeline chart with play time
    if (charts.timelineChart) {
        charts.timelineChart.destroy();
    }
    charts.timelineChart = new Chart(document.getElementById('timelineChart'), {
        type: 'line',
        data: {
            labels: (data.sessions || []).map(s => new Date(s.timestamp).toLocaleDateString()),
            datasets: [{
                label: 'Sessões Criadas',
                data: (data.sessions || []).map((_, i) => i + 1),
                borderColor: 'rgba(255, 99, 132, 1)',
                fill: false
            }, {
                label: 'Tempo de Reprodução (s)',
                data: (data.sessions || []).map(() => Math.random() * 1000), // Mock data
                borderColor: 'rgba(54, 162, 235, 1)',
                fill: false
            }]
        },
        options: { scales: { y: { beginAtZero: true } } }
    });
}

function updateTables(data) {
    const topVideosTable = document.getElementById('topVideosTable');
    topVideosTable.innerHTML = (data.top_videos || []).map(v => `
        <tr>
            <td><a href="/player?video=${encodeURIComponent(v.path)}" class="text-light">${v.path.split(/[\\/]/).pop()}</a></td>
            <td>${v.play_count}</td>
            <td>${formatTime(v.total_play_time || 0)}</td>
            <td>${v.engagement_score || 0}</td>
            <td>${v.favorited ? '<i class="bi bi-star-fill text-warning"></i>' : '<i class="bi bi-star"></i>'}</td>
            <td>
                <button class="btn btn-sm btn-warning" onclick="toggleFavorite('${encodeURIComponent(v.path)}')">${v.favorited ? 'Desfavoritar' : 'Favoritar'}</button>
            </td>
        </tr>
    `).join('');

    // Update pagination
    updatePagination(data.top_videos_total || 0);

    const sessionsTable = document.getElementById('sessionsTable');
    sessionsTable.innerHTML = (data.sessions || []).map(s => `
        <tr>
            <td>${s.name}</td>
            <td>${(s.videos || []).map(v => v ? v.split(/[\\/]/).pop() : '-').join(', ')}</td>
            <td>${s.state || 'active'}</td>
            <td>${formatTime(s.duration || 0)}</td>
            <td>${s.created_at ? new Date(s.created_at).toLocaleString() : '-'}</td>
            <td>${s.updated_at ? new Date(s.updated_at).toLocaleString() : '-'}</td>
            <td>
                <button class="btn btn-sm btn-danger" onclick="removeSession('${s.name}')">Excluir</button>
            </td>
        </tr>
    `).join('');
}

function updatePagination(total) {
    const paginationControls = document.getElementById('paginationControls');
    const limit = parseInt(document.getElementById('limitSelect').value);
    const totalPages = Math.ceil(total / limit);
    const currentPage = parseInt(localStorage.getItem('currentPage') || 1);

    let html = '';
    if (totalPages > 1) {
        // Previous
        html += `<li class="page-item ${currentPage === 1 ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="changePage(${currentPage - 1})">Anterior</a>
        </li>`;

        // Pages
        for (let i = Math.max(1, currentPage - 2); i <= Math.min(totalPages, currentPage + 2); i++) {
            html += `<li class="page-item ${i === currentPage ? 'active' : ''}">
                <a class="page-link" href="#" onclick="changePage(${i})">${i}</a>
            </li>`;
        }

        // Next
        html += `<li class="page-item ${currentPage === totalPages ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="changePage(${currentPage + 1})">Próximo</a>
        </li>`;
    }
    paginationControls.innerHTML = html;
    document.getElementById('paginationNav').style.display = totalPages > 1 ? 'block' : 'none';
}

export function updateDashboard(data) {
    analyticsData = data;
    document.getElementById('errorMessage').style.display = 'none';
    document.getElementById('dashboardContent').style.display = 'block';

    updateStatsCards(data);
    updateCharts(data);
    updateTables(data);
}

export async function loadSessions() {
    try {
        const response = await fetch('/sessions');
        const sessions = await response.json();
        const sessionsTable = document.getElementById('sessionsTable');
        sessionsTable.innerHTML = sessions.map(s => `
            <tr>
                <td>${s.name}</td>
                <td>${(s.videos || []).map(v => v ? v.split(/[\\/]/).pop() : '-').join(', ')}</td>
                <td>${s.state || 'active'}</td>
                <td>${formatTime(s.duration || 0)}</td>
                <td>${s.created_at ? new Date(s.created_at).toLocaleString() : '-'}</td>
                <td>${s.updated_at ? new Date(s.updated_at).toLocaleString() : '-'}</td>
                <td>
                    <button class="btn btn-sm btn-danger" onclick="removeSession('${s.name}')">Excluir</button>
                </td>
            </tr>
        `).join('');
    } catch (error) {
        console.error('Error loading sessions:', error);
    }
}

export function updateSessionsTable(data) {
    if (data.action === 'created' || data.action === 'updated') {
        loadSessions(); // Reload sessions on update
    }
}
export function showError() {
    document.getElementById('errorMessage').style.display = 'block';
    document.getElementById('dashboardContent').style.display = 'none';
}