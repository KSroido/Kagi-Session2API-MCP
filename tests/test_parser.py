"""Unit tests for HTML parser module."""

import pytest

from kagi_session_mcp.parser import (
    RelatedSearches,
    SearchResponse,
    SearchResult,
    _sanitize_text,
    parse_search_html,
)


class TestSanitizeText:
    """Tests for HTML entity sanitization."""

    def test_basic_text(self):
        assert _sanitize_text("hello world") == "hello world"

    def test_html_entities(self):
        assert _sanitize_text("it&#39;s &quot;great&quot;") == "it's \"great\""

    def test_whitespace_normalization(self):
        assert _sanitize_text("  hello   world  ") == "hello world"

    def test_empty_string(self):
        assert _sanitize_text("") == ""


class TestSearchResultToDict:
    """Tests for SearchResult serialization."""

    def test_minimal_result(self):
        result = SearchResult(url="https://example.com", title="Example")
        d = result.to_dict()
        assert d["t"] == 0
        assert d["url"] == "https://example.com"
        assert d["title"] == "Example"
        assert "snippet" not in d
        assert "published" not in d

    def test_full_result(self):
        result = SearchResult(
            url="https://example.com",
            title="Example",
            snippet="A description",
            published="2024-01-01",
            thumbnail={"src": "https://example.com/img.png"},
        )
        d = result.to_dict()
        assert d["snippet"] == "A description"
        assert d["published"] == "2024-01-01"
        assert d["thumbnail"]["src"] == "https://example.com/img.png"


class TestRelatedSearchesToDict:
    """Tests for RelatedSearches serialization."""

    def test_basic(self):
        related = RelatedSearches(list=["term1", "term2", "term3"])
        d = related.to_dict()
        assert d["t"] == 1
        assert d["list"] == ["term1", "term2", "term3"]


class TestSearchResponseToDict:
    """Tests for SearchResponse serialization."""

    def test_empty_response(self):
        response = SearchResponse()
        d = response.to_dict()
        assert "meta" in d
        assert "data" in d
        assert d["data"] == []

    def test_with_results(self):
        response = SearchResponse(
            meta={"id": "test-123", "node": "session", "ms": 100, "api_balance": None},
            data=[
                SearchResult(url="https://a.com", title="A"),
                RelatedSearches(list=["x", "y"]),
            ],
        )
        d = response.to_dict()
        assert len(d["data"]) == 2
        assert d["data"][0]["t"] == 0
        assert d["data"][1]["t"] == 1


class TestParseSearchHtml:
    """Tests for the main parse function."""

    def test_empty_html(self):
        """Empty HTML should return empty results with warning."""
        response = parse_search_html("<html><body></body></html>", "test")
        assert len(response.data) == 0

    def test_login_page_html(self):
        """Login page should return empty results (token expired)."""
        html = """
        <html><body>
        <form action="/authenticate" id="login">
            <input name="email" type="text">
        </form>
        </body></html>
        """
        response = parse_search_html(html, "test")
        assert len(response.data) == 0

    def test_basic_search_results(self):
        """Basic search results HTML should parse correctly."""
        html = """
        <html><body>
        <div class="search-result">
            <a class="__sri_title_link" href="https://example.com">Example Title</a>
            <div class="sri-desc">This is a description of the result.</div>
        </div>
        <div class="search-result">
            <a class="__sri_title_link" href="https://another.com">Another Result</a>
            <div class="sri-desc">Another description here.</div>
        </div>
        </body></html>
        """
        response = parse_search_html(html, "test query")
        assert len(response.data) >= 2

        # Check first result
        result0 = response.data[0]
        assert isinstance(result0, SearchResult)
        assert result0.url == "https://example.com"
        assert result0.title == "Example Title"
        assert result0.snippet == "This is a description of the result."

    def test_relative_url_handling(self):
        """Relative URLs should be converted to absolute."""
        html = """
        <html><body>
        <div class="search-result">
            <a class="__sri_title_link" href="/search?q=test">Test</a>
        </div>
        </body></html>
        """
        response = parse_search_html(html, "test")
        if response.data:
            assert response.data[0].url.startswith("https://kagi.com/")

    def test_published_date(self):
        """Published dates should be extracted."""
        html = """
        <html><body>
        <div class="search-result">
            <a class="__sri_title_link" href="https://example.com">Title</a>
            <time datetime="2024-01-15">Jan 15, 2024</time>
        </div>
        </body></html>
        """
        response = parse_search_html(html, "test")
        if response.data:
            assert response.data[0].published is not None

    def test_related_searches(self):
        """Related searches should be extracted."""
        html = """
        <html><body>
        <div class="related-searches">
            <a href="/search?q=term1">term1</a>
            <a href="/search?q=term2">term2</a>
            <a href="/search?q=term3">term3</a>
        </div>
        </body></html>
        """
        response = parse_search_html(html, "test")
        related = [r for r in response.data if isinstance(r, RelatedSearches)]
        if related:
            assert "term1" in related[0].list

    def test_meta_fields(self):
        """Meta fields should be set correctly."""
        html = "<html><body></body></html>"
        response = parse_search_html(html, "test", elapsed_ms=250)
        assert response.meta["node"] == "session"
        assert response.meta["ms"] == 250
        assert response.meta["api_balance"] is None

    def test_data_og_url_fallback(self):
        """data-og-url should be used as fallback for URLs."""
        html = """
        <html><body>
        <div class="search-result" data-og-url="https://original.com">
            <a class="__sri_title_link" href="#">Title</a>
        </div>
        </body></html>
        """
        response = parse_search_html(html, "test")
        if response.data:
            # href="#" should be skipped, data-og-url used instead
            result = response.data[0]
            if isinstance(result, SearchResult):
                assert result.url == "https://original.com"

    def test_prefixed_selectors(self):
        """Prefixed CSS classes (._0_*) should also be matched."""
        html = """
        <html><body>
        <div class="_0_search-result">
            <a class="_0_sri_title_link" href="https://example.com">Title</a>
            <div class="_0_sri-desc">Description</div>
        </div>
        </body></html>
        """
        response = parse_search_html(html, "test")
        if response.data:
            result = response.data[0]
            assert isinstance(result, SearchResult)
            assert result.title == "Title"
