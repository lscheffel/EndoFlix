import { updateDashboard, updateSessionsTable } from './dashboard.js';

class UltraWebSocket {
    constructor() {
        this.socket = null;
        this.connected = false;
    }

    connect() {
        this.socket = io('/ultra');

        this.socket.on('connect', () => {
            console.log('Connected to Ultra WebSocket');
            this.connected = true;
        });

        this.socket.on('disconnect', () => {
            console.log('Disconnected from Ultra WebSocket');
            this.connected = false;
        });

        this.socket.on('ultra_analytics_update', (data) => {
            console.log('Received real-time update:', data);
            updateDashboard(data);
        });

        this.socket.on('ultra_control', (data) => {
            console.log('Received control command:', data);
            // Handle control commands if needed
        });

        this.socket.on('ultra_session_update', (data) => {
            console.log('Received session update:', data);
            // Handle session updates, e.g., refresh sessions table
            if (typeof updateSessionsTable === 'function') {
                updateSessionsTable(data);
            }
        });

        this.socket.on('ultra_command_response', (data) => {
            console.log('Received command response:', data);
            if (data.success) {
                // Update UI based on command
                this._updateControlStatus(data.result);
            } else {
                alert('Erro no comando: ' + data.error);
            }
        });

        this.socket.on('ultra_batch_response', (data) => {
            console.log('Received batch response:', data);
            if (data.success) {
                alert('Comandos em lote processados com sucesso!');
            } else {
                alert('Erro nos comandos em lote: ' + data.error);
            }
        });
    }

    requestUpdate() {
        if (this.connected) {
            this.socket.emit('request_ultra_update');
        }
    }

    sendCommand(command, data = {}) {
        if (this.connected) {
            this.socket.emit('ultra_command', { command, ...data });
            console.log('Sent command:', { command, ...data });
        } else {
            console.error('WebSocket not connected');
        }
    }

    sendBatchCommands(commands) {
        if (this.connected) {
            this.socket.emit('ultra_batch_commands', { commands });
            console.log('Sent batch commands:', commands);
        } else {
            console.error('WebSocket not connected');
        }
    }

    _updateControlStatus(result) {
        const realtimeStatusEl = document.getElementById('realtimeStatus');
        const controlStatusEl = document.getElementById('controlStatus');
        const currentSpeedEl = document.getElementById('currentSpeed');
        const shuffleStatusEl = document.getElementById('shuffleStatus');

        if (result.action === 'play_all') {
            if (realtimeStatusEl) realtimeStatusEl.textContent = 'Todos os players reproduzindo';
            if (controlStatusEl) controlStatusEl.textContent = 'Reproduzindo';
        } else if (result.action === 'pause_all') {
            if (realtimeStatusEl) realtimeStatusEl.textContent = 'Todos os players pausados';
            if (controlStatusEl) controlStatusEl.textContent = 'Pausado';
        } else if (result.action === 'set_speed') {
            if (currentSpeedEl) currentSpeedEl.textContent = `Velocidade atual: ${result.speed[0]}x`;
            if (controlStatusEl) controlStatusEl.textContent = `Velocidade: ${result.speed[0]}x`;
        } else if (result.action === 'toggle_shuffle') {
            if (shuffleStatusEl) shuffleStatusEl.textContent = `Shuffle: ${result.shuffle ? 'Ativado' : 'Desativado'}`;
            if (controlStatusEl) controlStatusEl.textContent = `Shuffle ${result.shuffle ? 'Ativado' : 'Desativado'}`;
        }
    }
}

export default UltraWebSocket;