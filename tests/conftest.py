"""
Pytest configuration and global fixtures.
Enforces offline deterministic test execution and prevents external network hangs.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def mock_gemini_client_globally(monkeypatch):
    """
    Prevents tests from attempting live outbound HTTP calls to Google Gemini API
    when GEMINI_API_KEY is present in the local .env file.
    Tests specifically testing API behavior can override self._client with their own mocks.
    """
    try:
        from google import genai

        mock_models = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "Kondisi arus kas dan rasio likuiditas terpantau stabil dalam batas aman."
        mock_models.generate_content.return_value = mock_resp
        monkeypatch.setattr(genai.Client, "models", mock_models)
    except Exception:
        pass
