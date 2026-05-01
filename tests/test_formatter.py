"""Unit tests for formatter module."""

import pytest

from kagi_session_mcp.formatter import (
    format_search_results,
    format_summarizer_result,
    _format_search_result,
    _format_related_searches,
)
from kagi_session_mcp.parser import RelatedSearches, SearchResponse, SearchResult


class TestFormatSearchResult:
    """Tests for individual result formatting."""

    def test_basic_result(self):
        result = SearchResult(url="https://example.com", title="Example")
        text = _format_search_result(result, 1)
        assert "1. Example" in text
        assert "https://example.com" in text

    def test_result_with_snippet(self):
        result = SearchResult(
            url="https://example.com",
            title="Example",
            snippet="A description",
        )
        text = _format_search_result(result, 1)
        assert "A description" in text

    def test_result_with_published_date(self):
        result = SearchResult(
            url="https://example.com",
            title="Example",
            published="2024-01-15",
        )
        text = _format_search_result(result, 1)
        assert "Published: 2024-01-15" in text

    def test_numbering(self):
        result = SearchResult(url="https://example.com", title="Example")
        text = _format_search_result(result, 5)
        assert "5. Example" in text


class TestFormatRelatedSearches:
    """Tests for related searches formatting."""

    def test_basic(self):
        related = RelatedSearches(items=["term1", "term2", "term3"])
        text = _format_related_searches(related)
        assert "Related searches" in text
        assert "term1" in text
        assert "term2" in text

    def test_empty(self):
        related = RelatedSearches(items=[])
        text = _format_related_searches(related)
        assert text == ""


class TestFormatSearchResults:
    """Tests for full results formatting."""

    def test_single_query(self):
        response = SearchResponse(
            data=[
                SearchResult(url="https://a.com", title="Result A"),
                SearchResult(url="https://b.com", title="Result B"),
            ]
        )
        text = format_search_results(["test query"], [response])
        assert "1. Result A" in text
        assert "2. Result B" in text
        assert "Search results for: test query" in text

    def test_multiple_queries(self):
        response1 = SearchResponse(
            data=[SearchResult(url="https://a.com", title="Result A")]
        )
        response2 = SearchResponse(
            data=[SearchResult(url="https://b.com", title="Result B")]
        )
        text = format_search_results(["query1", "query2"], [response1, response2])
        assert "Query: query1" in text
        assert "Query: query2" in text
        assert "1. Result A" in text
        assert "2. Result B" in text

    def test_empty_results(self):
        text = format_search_results([], [])
        assert "No search results" in text

    def test_empty_data(self):
        response = SearchResponse(data=[])
        text = format_search_results(["test"], [response])
        assert "No results found" in text


class TestFormatSummarizerResult:
    """Tests for summarizer result formatting."""

    def test_data_output_path(self):
        data = {"data": {"output": "This is a summary."}}
        text = format_summarizer_result(data)
        assert "This is a summary." in text

    def test_top_level_output(self):
        data = {"output": "Summary text here."}
        text = format_summarizer_result(data)
        assert "Summary text here." in text

    def test_top_level_summary(self):
        data = {"summary": "Another summary."}
        text = format_summarizer_result(data)
        assert "Another summary." in text

    def test_unknown_structure(self):
        data = {"unknown_key": "value"}
        text = format_summarizer_result(data)
        assert "Summary data" in text
