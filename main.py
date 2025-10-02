from flask import Flask, render_template, request, jsonify, Response, redirect, url_for, flash
import os
from pathlib import Path
from db import Database
from config import Config
import logging
from collections import Counter
from datetime import datetime
import hashlib
import subprocess
import json
from concurrent.futures import ProcessPoolExecutor, as_completed, ThreadPoolExecutor
import redis
import time
import signal
import sys
import base64
import threading
from queue import Queue
from flask_login import login_user, login_required, logout_user, current_user

# Import auth module
from auth import login_manager

# Import blueprints
from blueprints.main import main_bp
from blueprints.auth import auth_bp
from blueprints.scan import scan_bp
from blueprints.playlists import playlists_bp
from blueprints.sessions import sessions_bp
from blueprints.favorites import favorites_bp
from blueprints.analytics import analytics_bp
from blueprints.video import video_bp

app = Flask(__name__)
app.secret_key = 'endoFlix_secret_key_2024'  # Change this in production
TRANSCODE_DIR = Path("transcode")
FFPROBE_PATH = Config.FFPROBE_PATH
REDIS_SERVER_PATH = Config.REDIS_SERVER_PATH
REDIS_CLIENT = None
REDIS_PROCESS = None
DB_POOL = Database()  # Updated to use new Database class

# Flask-Login setup
login_manager.login_view = 'auth.login'
login_manager.init_app(app)

logging.basicConfig(level=logging.INFO)

# Register blueprints
app.register_blueprint(main_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(scan_bp)
app.register_blueprint(playlists_bp)
app.register_blueprint(sessions_bp)
app.register_blueprint(favorites_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(video_bp)

def start_redis():
    global REDIS_PROCESS
    try:
        temp_client = redis.Redis(host='localhost', port=6379, db=0)
        temp_client.ping()
        logging.info("Redis já está rodando em localhost:6379")
        return
    except redis.ConnectionError:
        pass

    if not os.path.exists(REDIS_SERVER_PATH):
        logging.error(f"Arquivo redis-server.exe não encontrado em {REDIS_SERVER_PATH}")
        return

    try:
        REDIS_PROCESS = subprocess.Popen(
            [REDIS_SERVER_PATH],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        time.sleep(2)
        if REDIS_PROCESS.poll() is not None:
            logging.error("Falha ao iniciar o Redis: processo terminou inesperadamente")
            return
        logging.info("Servidor Redis iniciado com sucesso")
    except Exception as e:
        logging.error(f"Erro ao iniciar o Redis: {e}")

def init_redis(max_retries=3, retry_delay=2):
    global REDIS_CLIENT
    for attempt in range(max_retries):
        try:
            REDIS_CLIENT = redis.Redis(host='localhost', port=6379, db=0)
            REDIS_CLIENT.ping()
            logging.info("Conexão com Redis estabelecida")
            return True
        except redis.ConnectionError as e:
            logging.warning(f"Tentativa {attempt + 1}/{max_retries} de conexão ao Redis falhou: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
    logging.warning("Não foi possível conectar ao Redis. Usando fallback sem cache.")
    REDIS_CLIENT = None
    return False

def shutdown_redis():
    global REDIS_PROCESS
    if REDIS_PROCESS:
        try:
            REDIS_PROCESS.terminate()
            REDIS_PROCESS.wait(timeout=5)
            logging.info("Servidor Redis encerrado")
        except Exception as e:
            logging.error(f"Erro ao encerrar o Redis: {e}")

def signal_handler(sig, frame):
    logging.info("Encerrando o EndoFlix...")
    shutdown_redis()
    DB_POOL.closeall()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)





if __name__ == '__main__':
    start_redis()
    init_redis()
    try:
        app.run(port=5000)
    finally:
        shutdown_redis()
        DB_POOL.closeall()