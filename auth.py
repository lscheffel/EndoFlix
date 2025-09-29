from flask_login import LoginManager, UserMixin
import bcrypt

login_manager = LoginManager()

class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    # For single user system, return the default user
    return User(1, 'admin')

# Simple password hash for demo - in production, store in DB
DEFAULT_PASSWORD_HASH = bcrypt.hashpw(b'admin123', bcrypt.gensalt())