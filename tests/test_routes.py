import pytest
from flask import url_for

class TestRoutes:
    def test_index_redirects_to_login_when_not_logged_in(self, client):
        """Test that index redirects to login when not authenticated"""
        response = client.get('/')
        assert response.status_code == 302  # Redirect
        assert '/login' in response.headers['Location']

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
        # Should redirect to index after login
        assert b'EndoFlix' in response.data

    def test_login_with_invalid_credentials(self, client):
        """Test login with invalid credentials"""
        response = client.post('/login', data={
            'username': 'admin',
            'password': 'wrongpassword'
        })
        assert response.status_code == 200
        assert b'Credenciais inv' in response.data  # Flash message

    def test_protected_route_requires_login(self, client):
        """Test that protected routes require login"""
        response = client.get('/about')
        assert response.status_code == 302
        assert '/login' in response.headers['Location']

    def test_stats_requires_login(self, client):
        """Test that stats endpoint requires login"""
        response = client.get('/stats')
        assert response.status_code == 302
        assert '/login' in response.headers['Location']

    def test_analytics_requires_login(self, client):
        """Test that analytics endpoint requires login"""
        response = client.get('/analytics')
        assert response.status_code == 302
        assert '/login' in response.headers['Location']

    def test_logout_requires_login(self, client):
        """Test that logout requires login"""
        response = client.get('/logout')
        assert response.status_code == 302
        assert '/login' in response.headers['Location']