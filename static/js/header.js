// Header functionality: stats display and theme toggle

let isLightTheme = false;

async function fetchStats() {
    try {
        const response = await fetch('/stats');
        const stats = await response.json();
        const statsElement = document.getElementById('stats');
        if (statsElement) {
            statsElement.textContent = `(${stats.videos} vídeos, ${stats.playlists} playlists, ${stats.sessions} sessões)`;
        }
    } catch (e) {
        console.error('Erro ao obter estatísticas:', e);
    }
}

function initThemeToggle() {
    const themeToggle = document.getElementById('themeToggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            isLightTheme = !isLightTheme;
            document.body.classList.toggle('bg-light', isLightTheme);
            document.body.classList.toggle('bg-dark', !isLightTheme);
            document.body.classList.toggle('text-dark', isLightTheme);
            document.body.classList.toggle('text-light', !isLightTheme);
            themeToggle.classList.toggle('bi-lightbulb', !isLightTheme);
            themeToggle.classList.toggle('bi-lightbulb-fill', isLightTheme);
        });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    initThemeToggle();
    fetchStats();
});