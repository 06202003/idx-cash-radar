"""
Unit tests for RAG Conversational Engine and free-form financial Q&A.
Strictly verifies Section 1, Section 6, and Section 7 of AGENTS.md.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.bot.main import handle_ask
from src.db.repository import FinancialRepository
from src.engine.news_radar import NewsRadar
from src.engine.rag_chat import RAGFinancialChatbot


def test_extract_tickers_from_query():
    rag = RAGFinancialChatbot()
    assert rag.extract_tickers_from_query("Bagaimana kondisi kas WIKA dan TOTL saat ini?") == [
        "WIKA", "TOTL"
    ]
    assert rag.extract_tickers_from_query("Apakah BBCA masuk semesta?") == []
    assert rag.extract_tickers_from_query("Jelaskan rasio keuangan WSKT?") == ["WSKT"]


def test_retrieve_context_for_query():
    repo = FinancialRepository()
    radar = NewsRadar()
    rag = RAGFinancialChatbot(repository=repo, news_radar=radar)

    ctx = rag.retrieve_context_for_query("Kenapa WIKA mengalami tekanan kas di 2023?")
    assert "WIKA" in ctx["mentioned_tickers"]
    assert "DATA RESMI BEI" in ctx["retrieved_facts"]
    assert "Histori 4 Tahun WIKA" in ctx["retrieved_facts"]


def test_retrieve_context_for_methodology_query():
    rag = RAGFinancialChatbot()
    ctx = rag.retrieve_context_for_query("Apa maksud dari Sloan Accrual dan PSAK 72?")
    assert "METODOLOGI PSAK 72" in ctx["relevant_knowledge"]
    assert "METODOLOGI SLOAN ACCRUAL" in ctx["relevant_knowledge"]


def test_generate_deterministic_fallback_with_ticker():
    rag = RAGFinancialChatbot()
    context = rag.retrieve_context_for_query("Bagaimana rasio kas TOTL?")
    answer = rag.generate_deterministic_fallback_answer("Bagaimana rasio kas TOTL?", context)

    assert "data keuangan resmi bei" in answer.lower()
    assert "TOTL" in answer
    assert "Catatan Analis" in answer


def test_generate_deterministic_fallback_methodology():
    rag = RAGFinancialChatbot()
    context = rag.retrieve_context_for_query("Apa arti Sloan Accrual?")
    answer = rag.generate_deterministic_fallback_answer("Apa arti Sloan Accrual?", context)

    assert "Sloan Accrual Ratio mengukur" in answer


def test_rag_chatbot_language_compliance_rejects_blacklisted_word():
    rag = RAGFinancialChatbot()
    rag._client = MagicMock()
    mock_response = MagicMock()
    # Hallucinates a blacklisted word "manipulasi"
    mock_response.text = "Perusahaan ini terindikasi melakukan manipulasi laporan keuangan."
    rag._client.models.generate_content.return_value = mock_response

    result = rag.answer_query("Apakah ada masalah di WIKA?")
    # Must reject the blacklisted response and fall back
    assert "manipulasi" not in result.lower()
    assert "Catatan Analis" in result or "DATA RESMI BEI" in result


def test_rag_chatbot_mock_gemini_success():
    rag = RAGFinancialChatbot()
    rag._client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = (
        "Secara fundamental, solvabilitas kas TOTL berada dalam kondisi sangat sehat "
        "karena beroperasi tanpa beban utang jangka pendek berbunga. Arus kas operasional "
        "mampu menopang seluruh kebutuhan modal kerja proyek secara mandiri."
    )
    rag._client.models.generate_content.return_value = mock_response

    result = rag.answer_query("Jelaskan kas TOTL")
    assert "kondisi sangat sehat" in result
    assert "beban utang jangka pendek" in result


def test_handle_ask_command():
    message = MagicMock()
    message.text = "/ask Bagaimana prospek kas WIKA?"
    message.answer = AsyncMock()
    message.bot = None

    asyncio.run(handle_ask(message))

    message.answer.assert_called_once()
    args, kwargs = message.answer.call_args
    assert len(args[0]) > 0
    assert kwargs.get("reply_markup") is not None
