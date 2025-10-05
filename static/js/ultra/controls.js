import UltraWebSocket from './websocket.js';

let ws = null;

export function initControls(websocketInstance) {
    ws = websocketInstance;
}

export async function playVideo(path) {
    try {
        const response = await fetch('/sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: `Ultra_${new Date().toISOString().replace(/[:.]/g, '-')}`,
                videos: [path, null, null, null]
            })
        });
        if (response.ok) {
            showAlert('Vídeo carregado na sessão! Volte à página inicial para reproduzir.');
            window.location.href = '/';
        } else {
            showAlert('Erro ao carregar vídeo');
        }
    } catch (e) {
        showAlert('Erro ao carregar vídeo: ' + e.message);
    }
}

export async function toggleFavorite(path) {
    path = decodeURIComponent(path);
    try {
        const isFavorited = analyticsData.top_videos.some(v => v.path === path && v.favorited);
        const response = await fetch('/favorites', {
            method: isFavorited ? 'DELETE' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_path: path })
        });
        if (response.ok) {
            showAlert('Favorito atualizado!');
            ws.requestUpdate();
        } else {
            showAlert('Erro ao atualizar favorito');
        }
    } catch (e) {
        showAlert('Erro ao atualizar favorito: ' + e.message);
    }
}

export async function removeSession(name) {
    if (!confirm(`Deseja excluir a sessão "${name}"?`)) return;
    try {
        const response = await fetch('/remove_session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        if (response.ok) {
            showAlert('Sessão excluída!');
            ws.requestUpdate();
        } else {
            showAlert('Erro ao excluir sessão');
        }
    } catch (e) {
        showAlert('Erro ao excluir sessão: ' + e.message);
    }
}

export async function controlPlayers(action) {
    try {
        if (action === 'play') {
            ws.sendCommand('play_all');
            showAlert('Comando "Reproduzir Todos" enviado!');
        } else if (action === 'pause') {
            ws.sendCommand('pause_all');
            showAlert('Comando "Pausar Todos" enviado!');
        }
    } catch (e) {
        showAlert('Erro ao controlar players: ' + e.message);
    }
}

export function controlSpeed() {
    const speed = parseFloat(document.getElementById('speedControl').value);
    ws.sendCommand('set_speed', { speed: speed });
    showAlert(`Velocidade ajustada para ${speed}x!`);
}

export function toggleAutoShuffle(enable) {
    const interval = parseInt(document.getElementById('shuffleInterval').value) || 3;
    ws.sendCommand('toggle_shuffle', { enable: enable, interval: interval });
    showAlert(`Auto-shuffle ${enable ? 'ativado' : 'desativado'} com intervalo de ${interval}s!`);
}

export async function playAllTopVideos() {
    const videos = analyticsData.top_videos || [];
    if (videos.length === 0) {
        showAlert('Nenhum vídeo encontrado para criar playlist');
        return;
    }
    const name = 'Mais Assistidos';
    const files = videos.map(v => v.path);
    try {
        const response = await fetch('/playlists', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, files })
        });
        const result = await response.json();
        if (result.success) {
            showAlert(`Playlist "${name}" criada com ${files.length} vídeos`);
            window.location.href = '/';
        } else {
            showAlert(`Erro ao criar playlist: ${result.error}`);
        }
    } catch (e) {
        showAlert(`Erro ao criar playlist: ${e.message}`);
    }
}

export async function batchToggleFavorites() {
    const videos = analyticsData.top_videos || [];
    if (videos.length === 0) {
        showAlert('Nenhum vídeo encontrado');
        return;
    }
    // Toggle all: if any is favorited, remove all, else add all
    const anyFavorited = videos.some(v => v.favorited);
    const filePaths = videos.map(v => v.path);
    try {
        const response = await fetch('/favorites', {
            method: anyFavorited ? 'DELETE' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_paths: filePaths })
        });
        const result = await response.json();
        if (result.success) {
            showAlert(anyFavorited ? 'Removidos dos favoritos' : 'Adicionados aos favoritos');
            ws.requestUpdate();
        } else {
            showAlert(`Erro: ${result.error}`);
        }
    } catch (e) {
        showAlert(`Erro: ${e.message}`);
    }
}

export async function manageViewCounts() {
    const action = prompt('Escolha ação: reset (zerar contagens), increment (incrementar), decrement (decrementar)');
    if (!action || !['reset', 'increment', 'decrement'].includes(action)) {
        showAlert('Ação inválida');
        return;
    }
    const videos = analyticsData.top_videos || [];
    if (videos.length === 0) {
        showAlert('Nenhum vídeo encontrado');
        return;
    }
    const filePaths = videos.map(v => v.path);
    try {
        const response = await fetch('/manage_view_counts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action, file_paths: filePaths })
        });
        const result = await response.json();
        if (result.success) {
            showAlert(`Contagens de visualização ${action}adas`);
            ws.requestUpdate();
        } else {
            showAlert(`Erro: ${result.error}`);
        }
    } catch (e) {
        showAlert(`Erro: ${e.message}`);
    }
}

export function exportTopVideos() {
    const csv = [
        'Vídeos Mais Reproduzidos',
        'Vídeo,Reproduções,Tempo Total,Engajamento,Favoritado',
        ...(analyticsData.top_videos || []).map(v => `"${v.path}",${v.play_count},${v.total_play_time || 0},${v.engagement_score || 0},${v.favorited ? 'Sim' : 'Não'}`)
    ].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'EndoFlix_Top_Videos.csv';
    a.click();
    URL.revokeObjectURL(url);
}

function showAlert(message) {
    const notificationEl = document.createElement('div');
    notificationEl.textContent = message;
    notificationEl.style.position = 'fixed';
    notificationEl.style.top = '10px';
    notificationEl.style.right = '10px';
    notificationEl.style.background = 'rgba(0,0,0,0.8)';
    notificationEl.style.color = 'white';
    notificationEl.style.padding = '10px';
    notificationEl.style.borderRadius = '5px';
    notificationEl.style.zIndex = '1000';
    document.body.appendChild(notificationEl);
    setTimeout(() => notificationEl.remove(), 3000);
}

// Make functions global for onclick
window.playVideo = playVideo;
window.toggleFavorite = toggleFavorite;
window.removeSession = removeSession;
window.playAllTopVideos = playAllTopVideos;
window.batchToggleFavorites = batchToggleFavorites;
window.manageViewCounts = manageViewCounts;
window.exportTopVideos = exportTopVideos;