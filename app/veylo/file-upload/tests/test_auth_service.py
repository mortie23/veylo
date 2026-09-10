import os
import pytest
from services.auth_service import validate_jwt_token


def test_missing_auth_header():
    claims, err = validate_jwt_token(None)
    assert claims is None
    assert "Missing Authorization header" in err


def test_malformed_auth_header():
    claims, err = validate_jwt_token("Basic 123456")
    assert claims is None
    assert "Expected 'Bearer <token>'" in err

    claims, err = validate_jwt_token("BearerOnly")
    assert claims is None
    assert "Expected 'Bearer <token>'" in err


def test_dev_mock_token_bypass(monkeypatch):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "true")
    claims, err = validate_jwt_token("Bearer dev-mock-token")
    assert err is None
    assert claims is not None
    assert claims["contact_id"] == "00000000-0000-0000-0000-000000000001"
    assert "File.Upload" in claims["roles"]


def test_invalid_jwt_token():
    claims, err = validate_jwt_token("Bearer not-a-valid-jwt-token")
    assert claims is None
    assert err is not None
