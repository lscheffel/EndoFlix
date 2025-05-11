document.addEventListener('keydown', (e) => {
    const videoContainers = document.querySelectorAll('.video-container');
    if (e.key === 's' || e.key === 'S') {
        document.getElementById('wishMeLuck').click();
    } else if (e.key === '1') {
        document.getElementById('shuffle1').click();
    } else if (e.key === '2') {
        document.getElementById('shuffle2').click();
    } else if (e.key === '3') {
        document.getElementById('shuffle3').click();
    } else if (e.key === '4') {
        document.getElementById('shuffle4').click();
    } else if (e.key === 'q' || e.key === 'Q') {
        const player = document.getElementById('player1');
        if (player.requestFullscreen) {
            player.requestFullscreen();
        } else if (player.webkitRequestFullscreen) {
            player.webkitRequestFullscreen();
        } else if (player.msRequestFullscreen) {
            player.msRequestFullscreen();
        }
        showToast('Player 1 em tela cheia!', false);
    } else if (e.key === 'w' || e.key === 'W') {
        const player = document.getElementById('player2');
        if (player.requestFullscreen) {
            player.requestFullscreen();
        } else if (player.webkitRequestFullscreen) {
            player.webkitRequestFullscreen();
        } else if (player.msRequestFullscreen) {
            player.msRequestFullscreen();
        }
        showToast('Player 2 em tela cheia!', false);
    } else if (e.key === 'e' || e.key === 'E') {
        const player = document.getElementById('player3');
        if (player.requestFullscreen) {
            player.requestFullscreen();
        } else if (player.webkitRequestFullscreen) {
            player.webkitRequestFullscreen();
        } else if (player.msRequestFullscreen) {
            player.msRequestFullscreen();
        }
        showToast('Player 3 em tela cheia!', false);
    } else if (e.key === 'r' || e.key === 'R') {
        const player = document.getElementById('player4');
        if (player.requestFullscreen) {
            player.requestFullscreen();
        } else if (player.webkitRequestFullscreen) {
            player.webkitRequestFullscreen();
        } else if (player.msRequestFullscreen) {
            player.msRequestFullscreen();
        }
        showToast('Player 4 em tela cheia!', false);
    } else if (e.key === 'm' || e.key === 'M') {
        let allMuted = true;
        videoContainers.forEach(container => {
            const player = container.querySelector('.video-player');
            if (!player.muted) allMuted = false;
        });
        videoContainers.forEach(container => {
            const player = container.querySelector('.video-player');
            player.muted = !allMuted;
        });
        showToast(allMuted ? 'Som ativado!' : 'Som desativado!', false);
    } else if (e.key === ' ') {
        videoContainers.forEach(container => {
            const player = container.querySelector('.video-player');
            player.pause();
        });
        showToast('Todos os players pausados!', false);
    } else if (e.key === "'") {
        document.getElementById('panicBtn').click();
    } else if (e.key === 'c' || e.key === 'C') {
        document.getElementById('clearDeck').click();
    } else if (e.key === '5') {
        const source = document.getElementById('source1');
        if (source.src) {
            const file = decodeURIComponent(source.src.split('/video/')[1]);
            toggleFavorite(file);
        } else {
            showToast('Nenhum vídeo no player 1!', true);
        }
    } else if (e.key === '6') {
        const source = document.getElementById('source2');
        if (source.src) {
            const file = decodeURIComponent(source.src.split('/video/')[1]);
            toggleFavorite(file);
        } else {
            showToast('Nenhum vídeo no player 2!', true);
        }
    } else if (e.key === '7') {
        const source = document.getElementById('source3');
        if (source.src) {
            const file = decodeURIComponent(source.src.split('/video/')[1]);
            toggleFavorite(file);
        } else {
            showToast('Nenhum vídeo no player 3!', true);
        }
    } else if (e.key === '8') {
        const source = document.getElementById('source4');
        if (source.src) {
            const file = decodeURIComponent(source.src.split('/video/')[1]);
            toggleFavorite(file);
        } else {
            showToast('Nenhum vídeo no player 4!', true);
        }
    }
});