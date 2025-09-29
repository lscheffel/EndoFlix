from flask import Blueprint, request, Response, jsonify
from pathlib import Path
import json
import logging
from flask_login import login_required
from ..utils import get_media_files

scan_bp = Blueprint('scan', __name__)

@scan_bp.route('/scan', methods=['POST', 'GET'])
@login_required
def scan():
    if request.method == 'POST':
        folder = request.json.get('folder')
        folder_path = Path(folder)
        if not folder_path.exists() or not folder_path.is_dir():
            return jsonify({'error': 'Pasta inválida ou não encontrada'}), 400
        return Response(get_media_files(folder), mimetype='text/event-stream')
    elif request.method == 'GET':
        folder = request.args.get('folder')
        if not folder:
            return jsonify({'error': 'Parâmetro folder é obrigatório'}), 400
        return Response(get_media_files(folder), mimetype='text/event-stream')