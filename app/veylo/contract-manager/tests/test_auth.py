from unittest.mock import MagicMock
import pytest
from flask import session
from app import create_app
from config import get_settings


@pytest.fixture
def auth_client(monkeypatch):
    """Creates a test client with auth explicitly enabled."""
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("ENTRA_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("ENTRA_TENANT_ID", "test-tenant-id")

    # Clear cached settings
    get_settings.cache_clear()

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

    get_settings.cache_clear()


def test_health_check_always_accessible_without_auth(auth_client):
    """The Cloud Run health probe must remain unauthenticated."""
    response = auth_client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"


def test_unauthenticated_request_redirects_to_login(auth_client):
    """Accessing contracts catalog without a session should redirect to /auth/login."""
    response = auth_client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_auth_login_redirects_to_microsoft(auth_client, monkeypatch):
    """Calling /auth/login should construct a valid Microsoft Entra ID authorization URL."""
    mock_msal = MagicMock()
    mock_msal.get_authorization_request_url.side_effect = (
        lambda scopes, state, redirect_uri, prompt: (
            f"https://login.microsoftonline.com/test-tenant-id/oauth2/v2.0/authorize"
            f"?client_id=test-client-id&scope={' '.join(scopes)}&state={state}"
        )
    )
    monkeypatch.setattr("blueprints.auth.routes._build_msal_app", lambda cache=None: mock_msal)

    response = auth_client.get("/auth/login", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["Location"]
    assert "login.microsoftonline.com/test-tenant-id/oauth2/v2.0/authorize" in location
    assert "client_id=test-client-id" in location
    assert "scope=User.Read" in location


def test_auth_callback_state_mismatch(auth_client):
    """Mismatched CSRF state must reject the callback."""
    response = auth_client.get("/auth/callback?state=invalid-state&code=test-code", follow_redirects=False)
    assert response.status_code == 302
    # Redirects to home with flash message


def test_auth_callback_success(auth_client, monkeypatch):
    """Successful callback acquires token, sets session user, and redirects to home."""
    mock_msal = MagicMock()
    mock_msal.acquire_token_by_authorization_code.return_value = {
        "id_token_claims": {
            "name": "Mortimer User",
            "preferred_username": "mortimer@example.com",
            "oid": "test-user-oid",
            "tid": "test-tenant-id",
            "roles": ["Reader"],
        }
    }
    monkeypatch.setattr("blueprints.auth.routes._build_msal_app", lambda cache=None: mock_msal)

    with auth_client.session_transaction() as sess:
        sess["auth_state"] = "valid-state"

    response = auth_client.get("/auth/callback?state=valid-state&code=test-auth-code", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"] == "/"

    with auth_client.session_transaction() as sess:
        assert sess["user"]["email"] == "mortimer@example.com"
        assert sess["user"]["name"] == "Mortimer User"


def test_auth_callback_tenant_mismatch(auth_client, monkeypatch):
    """Callback with wrong tenant must be rejected."""
    mock_msal = MagicMock()
    mock_msal.acquire_token_by_authorization_code.return_value = {
        "id_token_claims": {
            "name": "Untrusted User",
            "preferred_username": "untrusted@rogue.com",
            "oid": "rogue-oid",
            "tid": "wrong-tenant-id",
        }
    }
    monkeypatch.setattr("blueprints.auth.routes._build_msal_app", lambda cache=None: mock_msal)

    with auth_client.session_transaction() as sess:
        sess["auth_state"] = "valid-state"

    response = auth_client.get("/auth/callback?state=valid-state&code=test-auth-code", follow_redirects=False)
    assert response.status_code == 302

    with auth_client.session_transaction() as sess:
        assert "user" not in sess


def test_auth_logout_clears_session(auth_client):
    """Logout clears session and redirects to Microsoft logout endpoint."""
    with auth_client.session_transaction() as sess:
        sess["user"] = {"name": "Test User", "email": "test@example.com"}

    response = auth_client.get("/auth/logout", follow_redirects=False)
    assert response.status_code == 302
    assert "login.microsoftonline.com/test-tenant-id/oauth2/v2.0/logout" in response.headers["Location"]

    with auth_client.session_transaction() as sess:
        assert "user" not in sess

