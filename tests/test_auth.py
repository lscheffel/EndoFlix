import pytest
from flask import url_for
import bcrypt
from auth import DEFAULT_PASSWORD_HASH

class TestAuth:
    def test_login_page_loads(self, client):
        """Test that login page loads"""
        response = client.get('/login')
        assert response.status_code == 200
        assert b'EndoFlix - Login' in response.data

    def test_login_with_valid_credentials(self, client):
        """Test login with valid credentials"""
        response = client.post('/login', data={
            'username': 'admin',
            'password': 'admin123'
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'EndoFlix' in response.data

    def test_login_with_invalid_username(self, client):
        """Test login with invalid username"""
        response = client.post('/login', data={
            'username': 'wronguser',
            'password': 'admin123'
        })
        assert response.status_code == 200
        assert b'Credenciais inv' in response.data

    def test_login_with_invalid_password(self, client):
        """Test login with invalid password"""
        response = client.post('/login', data={
            'username': 'admin',
            'password': 'wrongpassword'
        })
        assert response.status_code == 200
        assert b'Credenciais inv' in response.data

    def test_login_with_empty_fields(self, client):
        """Test login with empty username and password"""
        response = client.post('/login', data={
            'username': '',
            'password': ''
        })
        assert response.status_code == 200
        assert b'Credenciais inv' in response.data

    def test_logout_without_login(self, client):
        """Test that logout redirects when not logged in"""
        response = client.get('/logout')
        assert response.status_code == 302
        assert '/login' in response.headers['Location']

    def test_logout_with_login(self, authenticated_client):
        """Test logout when logged in"""
        response = authenticated_client.get('/logout')
        assert response.status_code == 302
        assert '/login' in response.headers['Location']
        # Verify session is cleared
        response2 = authenticated_client.get('/')
        assert response2.status_code == 302
        assert '/login' in response2.headers['Location']

    def test_protected_route_requires_login(self, client):
        """Test that protected routes require login"""
        response = client.get('/playlists')
        assert response.status_code == 302
        assert '/login' in response.headers['Location']

    def test_rate_limiting_login(self, client):
        """Test rate limiting on login endpoint"""
        # Attempt multiple logins quickly
        for _ in range(6):
            response = client.post('/login', data={
                'username': 'admin',
                'password': 'wrong'
            })
        # Should be rate limited after 5 attempts
        assert response.status_code == 429  # Too Many Requests

    def test_default_password_hash(self):
        """Test that default password hash is correct"""
        assert bcrypt.checkpw(b'admin123', DEFAULT_PASSWORD_HASH)

    def test_user_creation(self):
        """Test User class creation"""
        from auth import User
        user = User(1, 'admin')
        assert user.id == 1
        assert user.username == 'admin'
        assert user.is_authenticated == True
        assert user.is_active == True
        assert user.is_anonymous == False
        assert user.get_id() == '1'