import os
import base64
import logging
from datetime import datetime
from queue import Queue, Full
from concurrent.futures import ThreadPoolExecutor
import threading
from config import Config
from typing import List, Dict, Any, Optional

class SnapshotProcessor:
    def __init__(self):
        self.queue = Queue(maxsize=Config.QUEUE_MAX_SIZE)
        self.executor = ThreadPoolExecutor(max_workers=Config.SNAPSHOT_WORKERS)
        self._start_workers()

    def _start_workers(self):
        for _ in range(Config.SNAPSHOT_WORKERS):
            self.executor.submit(self._worker_loop)

    def _worker_loop(self):
        while True:
            try:
                data = self.queue.get()
                if data is None:
                    break

                self._process_snapshot(data)
                self.queue.task_done()
            except Exception as e:
                logging.error(f"Erro no worker de snapshot: {e}")
                self.queue.task_done()

    def _process_snapshot(self, data: Dict[str, Any]) -> None:
        try:
            video_path = data['video_path']
            image_data = data['image_data']
            is_burst = data['is_burst']
            burst_index = data['burst_index']

            # Remove o prefixo da URL do vídeo
            video_path = video_path.replace('/video/', '')
            video_path = os.path.normpath(video_path)

            # Cria a pasta snapshots se não existir
            snapshots_dir = self._ensure_snapshots_dir(video_path)
            
            # Gera o nome do arquivo
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            if is_burst:
                filename = f'burst_{timestamp}_{burst_index}.webp'
            else:
                filename = f'snapshot_{timestamp}.webp'
            
            # Salva a imagem
            file_path = os.path.join(snapshots_dir, filename)
            image_data = base64.b64decode(image_data.split(',')[1])
            with open(file_path, 'wb') as f:
                f.write(image_data)
        except Exception as e:
            logging.error(f"Erro ao processar snapshot: {e}")

    def _ensure_snapshots_dir(self, video_path: str) -> str:
        video_dir = os.path.dirname(video_path)
        snapshots_dir = os.path.join(video_dir, 'snapshots')
        if not os.path.exists(snapshots_dir):
            os.makedirs(snapshots_dir)
        return snapshots_dir

    def add_snapshot(self, video_path: str, image_data: str, is_burst: bool = False, burst_index: int = 0) -> bool:
        try:
            self.queue.put({
                'video_path': video_path,
                'image_data': image_data,
                'is_burst': is_burst,
                'burst_index': burst_index
            }, timeout=Config.CONNECTION_TIMEOUT)
            return True
        except Full:
            logging.error("Fila de snapshots cheia")
            return False
        except Exception as e:
            logging.error(f"Erro ao adicionar snapshot: {e}")
            return False

    def add_burst(self, video_path: str, frames: List[str]) -> bool:
        success = True
        for i, frame_data in enumerate(frames, 1):
            if not self.add_snapshot(video_path, frame_data, is_burst=True, burst_index=i):
                success = False
        return success

    def cleanup(self):
        for _ in range(Config.SNAPSHOT_WORKERS):
            try:
                self.queue.put(None, timeout=Config.CONNECTION_TIMEOUT)
            except Full:
                pass
        self.executor.shutdown(wait=True) 