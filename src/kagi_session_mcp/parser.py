"""HTML parser for Kagi search results.

Parses Kagi's server-rendered HTML from /html/search and converts it
to API-compatible data structures matching the official Kagi API format.

Uses BeautifulSoup + lxml for robust HTML parsing with multiple CSS
selector fallback strategies for resilience against HTML structure changes.
"""

import html
import logging
from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup, Tag

from .exceptions import ParseError

logger = logging.getLogger("kagi-session2api-mcp")

_PARSER_VERSION = "0.1.0"


# --- Data Classes (API-compatible) ---


@dataclass
class SearchResult:
    """API-compatible search result (t=0)."""

    t: int = 0
    url: str = ""
    title: str = ""
    snippet: str | None = None
    published: str | None = None
    thumbnail: dict | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to API-compatible dict, omitting None values."""
        d: dict[str, Any] = {"t": self.t, "url": self.url, "title": self.title}
        if self.snippet is not None:
            d["snippet"] = self.snippet
        if self.published is not None:
            d["published"] = self.published
        if self.thumbnail is not None:
            d["thumbnail"] = self.thumbnail
        return d


@dataclass
class RelatedSearches:
    """API-compatible related searches (t=1)."""

    t: int = 1
    items: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"t": self.t, "list": self.items}


@dataclass
class SearchResponse:
    """API-compatible search response."""

    meta: dict = field(
        default_factory=lambda: {
            "id": "",
            "node": "session",
            "ms": 0,
            "api_balance": None,
        }
    )
    data: list[SearchResult | RelatedSearches] = field(default_factory=list)
    error: list[dict] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to API-compatible dict."""
        result: dict[str, Any] = {
            "meta": self.meta,
            "data": [item.to_dict() for item in self.data],
        }
        if self.error:
            result["error"] = self.error
        return result


# --- Text Sanitization ---


def _sanitize_text(text: str) -> str:
    """Clean HTML entities and whitespace from extracted text.

    BeautifulSoup's .get_text() handles most entities, but this provides
    a safety net for edge cases and normalizes whitespace.
    """
    if not text:
        return ""
    # Handle any remaining HTML entities that BeautifulSoup might miss
    text = html.unescape(text)
    # Normalize whitespace
    text = " ".join(text.split())
    return text.strip()


# --- Main Parser ---


def parse_search_html(
    html_content: str, query: str, elapsed_ms: int = 0
) -> SearchResponse:
    """Parse Kagi search HTML into API-compatible SearchResponse.

    Args:
        html_content: Raw HTML from /html/search endpoint
        query: The search query that produced this HTML
        elapsed_ms: Time taken for the request in milliseconds

    Returns:
        SearchResponse with parsed results

    Raises:
        ParseError: If HTML parsing fails catastrophically
    """
    try:
        soup = BeautifulSoup(html_content, "lxml")
    except Exception as e:
        raise ParseError(f"Failed to parse HTML: {e}")

    results: list[SearchResult | RelatedSearches] = []

    # --- Primary search results ---
    # Try multiple selector strategies for resilience
    search_items = _select_elements(
        soup,
        [
            ".search-result",          # Primary result class
            "._0_search-result",       # Prefixed variant
            ".sri",                    # Short result identifier
            "._0_sri",                 # Prefixed short variant
            "[data-og-url]",           # Data attribute based
        ],
    )

    for item in search_items:
        result = _parse_search_result(item)
        if result:
            results.append(result)

    # --- Grouped results (sri-group) ---
    for group in soup.select(".sri-group, ._0_sri-group"):
        # Parse the main result from the group
        result = _parse_search_result(group)
        if result:
            results.append(result)
        # Also parse sub-results within the group
        for sub in group.select(".sri-sub-result, ._0_sri-sub-result, .sub-result"):
            sub_result = _parse_search_result(sub)
            if sub_result:
                results.append(sub_result)

    # --- News results ---
    for item in soup.select(".newsResultItem, ._0_newsResultItem, .news-result"):
        result = _parse_news_result(item)
        if result:
            results.append(result)

    # --- Video results ---
    for item in soup.select(".videoResultItem, ._0_videoResultItem, .video-result"):
        result = _parse_video_result(item)
        if result:
            results.append(result)

    # --- Wikipedia / instant answer results ---
    for item in soup.select(
        ".wikipediaResult, ._0_wikipediaResult, .instant-answer, .infobox"
    ):
        result = _parse_wikipedia_result(item)
        if result:
            results.append(result)

    # --- Related searches ---
    related = _extract_related_searches(soup)
    if related and related.items:
        results.append(related)

    # --- Warning if no results found ---
    if not results:
        logger.warning(
            f"Parser v{_PARSER_VERSION}: No results extracted for query '{query}'. "
            f"Kagi's HTML structure may have changed. "
            f"HTML length: {len(html_content)} chars"
        )

    return SearchResponse(
        meta={
            "id": f"session-{abs(hash(query)) & 0xFFFFFFFF:08x}",
            "node": "session",
            "ms": elapsed_ms,
            "api_balance": None,
        },
        data=results,
    )


# --- Selector Helpers ---


def _select_elements(soup: BeautifulSoup, selectors: list[str]) -> list[Tag]:
    """Try multiple CSS selectors and return results from the first one that matches.

    This provides resilience against HTML structure changes.
    """
    for selector in selectors:
        elements = soup.select(selector)
        if elements:
            return elements
    return []


# --- Individual Parsers ---


def _parse_search_result(item: Tag) -> SearchResult | None:
    """Parse a search result element into a SearchResult dataclass."""
    # --- Title and URL ---
    # Try multiple selectors for the title link
    title_el = (
        item.select_one(".__sri_title_link")
        or item.select_one("._0_sri_title_link")
        or item.select_one("a._0_URL")
        or item.select_one("a.__URL")
        or item.select_one(".sri-title a")
        or item.select_one("h3 a")
        or item.select_one("a[href]")  # Last resort: any link
    )

    if not title_el:
        return None

    # Extract URL
    url = title_el.get("href", "")
    if not url or url.startswith("#"):
        # Try data-og-url as fallback
        url = item.get("data-og-url", "") or item.get("data-url", "")

    if not url:
        return None

    # Handle relative URLs
    if url.startswith("/"):
        url = f"https://kagi.com{url}"

    # Extract title
    title = _sanitize_text(title_el.get_text())

    if not title:
        return None

    # --- Snippet / description ---
    snippet_el = (
        item.select_one(".sri-desc")
        or item.select_one("._0_sri-desc")
        or item.select_one(".sri-snippet")
        or item.select_one("._0_sri-snippet")
        or item.select_one(".snippet")
        or item.select_one("p")  # Fallback: first paragraph
    )
    snippet = _sanitize_text(snippet_el.get_text()) if snippet_el else None

    # --- Published date ---
    published = _extract_published_date(item)

    # --- Thumbnail ---
    thumbnail = _extract_thumbnail(item)

    return SearchResult(
        url=url,
        title=title,
        snippet=snippet,
        published=published,
        thumbnail=thumbnail,
    )


def _parse_news_result(item: Tag) -> SearchResult | None:
    """Parse a news result element."""
    title_el = (
        item.select_one("a.news-title")
        or item.select_one(".news-title a")
        or item.select_one("h3 a")
        or item.select_one("a[href]")
    )

    if not title_el:
        return None

    url = title_el.get("href", "")
    title = _sanitize_text(title_el.get_text())

    if not url or not title:
        return None

    if url.startswith("/"):
        url = f"https://kagi.com{url}"

    snippet_el = (
        item.select_one(".news-snippet")
        or item.select_one(".snippet")
        or item.select_one("p")
    )
    snippet = _sanitize_text(snippet_el.get_text()) if snippet_el else None

    published = _extract_published_date(item)
    thumbnail = _extract_thumbnail(item)

    return SearchResult(
        url=url,
        title=title,
        snippet=snippet,
        published=published,
        thumbnail=thumbnail,
    )


def _parse_video_result(item: Tag) -> SearchResult | None:
    """Parse a video result element."""
    title_el = (
        item.select_one("a.video-title")
        or item.select_one(".video-title a")
        or item.select_one("h3 a")
        or item.select_one("a[href]")
    )

    if not title_el:
        return None

    url = title_el.get("href", "")
    title = _sanitize_text(title_el.get_text())

    if not url or not title:
        return None

    if url.startswith("/"):
        url = f"https://kagi.com{url}"

    snippet_el = (
        item.select_one(".video-snippet")
        or item.select_one(".snippet")
        or item.select_one("p")
    )
    snippet = _sanitize_text(snippet_el.get_text()) if snippet_el else None

    thumbnail = _extract_thumbnail(item)

    return SearchResult(
        url=url,
        title=title,
        snippet=snippet,
        published=None,
        thumbnail=thumbnail,
    )


def _parse_wikipedia_result(item: Tag) -> SearchResult | None:
    """Parse a Wikipedia / instant answer result element."""
    # Wikipedia results often have a different structure
    title_el = (
        item.select_one(".wiki-title a")
        or item.select_one(".instant-answer-title a")
        or item.select_one("h2 a")
        or item.select_one("h3 a")
        or item.select_one("a[href]")
    )

    if not title_el:
        return None

    url = title_el.get("href", "")
    title = _sanitize_text(title_el.get_text())

    if not url or not title:
        return None

    if url.startswith("/"):
        url = f"https://kagi.com{url}"

    snippet_el = (
        item.select_one(".wiki-extract")
        or item.select_one(".wiki-desc")
        or item.select_one(".instant-answer-snippet")
        or item.select_one("p")
    )
    snippet = _sanitize_text(snippet_el.get_text()) if snippet_el else None

    thumbnail = _extract_thumbnail(item)

    return SearchResult(
        url=url,
        title=title,
        snippet=snippet,
        published=None,
        thumbnail=thumbnail,
    )


def _extract_published_date(item: Tag) -> str | None:
    """Extract published date from a result element."""
    # Try multiple selectors for date
    date_el = (
        item.select_one(".sri-date")
        or item.select_one("._0_sri-date")
        or item.select_one(".news-date")
        or item.select_one(".date")
        or item.select_one("time")
    )
    if date_el:
        date_text = _sanitize_text(date_el.get_text())
        if date_text:
            return date_text

    # Try datetime attribute on time element
    time_el = item.select_one("time[datetime]")
    if time_el:
        dt = time_el.get("datetime", "")
        if dt:
            return str(dt)

    return None


def _extract_thumbnail(item: Tag) -> dict | None:
    """Extract thumbnail information from a result element."""
    img_el = (
        item.select_one(".sri-thumbnail img")
        or item.select_one("._0_sri-thumbnail img")
        or item.select_one(".thumbnail img")
        or item.select_one("img[src]")
    )
    if not img_el:
        return None

    src = img_el.get("src", "")
    if not src or src.startswith("data:"):
        return None

    # Handle relative URLs
    if src.startswith("/"):
        src = f"https://kagi.com{src}"

    return {"src": src}


def _extract_related_searches(soup: BeautifulSoup) -> RelatedSearches | None:
    """Extract related search suggestions."""
    terms: list[str] = []

    # Strategy 1: Explicit related searches container
    related_el = soup.select_one(
        ".related-searches, ._0_related-searches, .related-searches-box"
    )
    if related_el:
        for a in related_el.select("a"):
            text = _sanitize_text(a.get_text())
            if text:
                terms.append(text)
        if terms:
            return RelatedSearches(items=terms)

    # Strategy 2: Look for "Related searches" / "People also search for" section
    for heading in soup.select("h2, h3, .section-title"):
        heading_text = heading.get_text(strip=True).lower()
        if any(
            keyword in heading_text
            for keyword in ["related", "also search", "related search"]
        ):
            # Find links in the sibling container
            parent = heading.find_parent()
            if parent:
                for a in parent.select("a"):
                    text = _sanitize_text(a.get_text())
                    if text and text not in terms:
                        terms.append(text)
            if terms:
                return RelatedSearches(items=terms)

    # Strategy 3: Look for common related search patterns in list items
    for el in soup.select(".related-terms a, .related-links a"):
        text = _sanitize_text(el.get_text())
        if text:
            terms.append(text)

    return RelatedSearches(items=terms) if terms else None
