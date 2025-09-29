from flask import Blueprint, render_template
from flask_login import login_required

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
@login_required
def index():
    return render_template('base.html')

@main_bp.route('/about')
@login_required
def about():
    return render_template('about.html')

@main_bp.route('/ultra')
@login_required
def ultra():
    return render_template('ultra.html')

@main_bp.route('/keymaps')
@login_required
def keymaps():
    return render_template('keymaps.html')