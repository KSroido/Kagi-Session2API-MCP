"""HTML parser for Kagi search results.

Parses Kagi's server-rendered HTML from /html/search and converts it
to API-compatible data structures matching the official Kagi API format.

Uses selectolax (Lexbor engine) for fast HTML parsing with multiple CSS
selector fallback strategies for resilience against HTML structure changes.
"""

import html
import logging
from dataclasses import dataclass, field
from typing import Any

from selectolax.lexbor import LexborHTMLParser

from .exceptions import ParseError

logger = logging.getLogger("kagi-session2api-mcp")

_PARSER_VERSION = "0.2.0"


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

    selectolax's .text() handles most entities, but this provides
    a safety net for edge cases and normalizes whitespace.
    """
    if not text:
        return ""
    # Handle any remaining HTML entities that the parser might miss
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
        tree = LexborHTMLParser(html_content)
    except Exception as e:
        raise ParseError(f"Failed to parse HTML: {e}")

    results: list[SearchResult | RelatedSearches] = []

    # --- Primary search results ---
    # Try multiple selector strategies for resilience
    search_items = _select_elements(
        tree,
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
    for group in tree.css(".sri-group, ._0_sri-group"):
        # Parse the main result from the group
        result = _parse_search_result(group)
        if result:
            results.append(result)
        # Also parse sub-results within the group
        for sub in group.css(".sri-sub-result, ._0_sri-sub-result, .sub-result"):
            sub_result = _parse_search_result(sub)
            if sub_result:
                results.append(sub_result)

    # --- News results ---
    for item in tree.css(".newsResultItem, ._0_newsResultItem, .news-result"):
        result = _parse_news_result(item)
        if result:
            results.append(result)

    # --- Video results ---
    for item in tree.css(".videoResultItem, ._0_videoResultItem, .video-result"):
        result = _parse_video_result(item)
        if result:
            results.append(result)

    # --- Wikipedia / instant answer results ---
    for item in tree.css(
        ".wikipediaResult, ._0_wikipediaResult, .instant-answer, .infobox"
    ):
        result = _parse_wikipedia_result(item)
        if result:
            results.append(result)

    # --- Related searches ---
    related = _extract_related_searches(tree)
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


def _select_elements(tree: LexborHTMLParser, selectors: list[str]) -> list:
    """Try multiple CSS selectors and return results from the first one that matches.

    This provides resilience against HTML structure changes.

    Args:
        tree: LexborHTMLParser instance (parsed document)
        selectors: List of CSS selectors to try in order

    Returns:
        List of matching nodes from the first selector that matches,
        or an empty list if none match.
    """
    for selector in selectors:
        elements = tree.css(selector)
        if elements:
            return elements
    return []


def _css_first(item, selectors: list[str]):
    """Try multiple CSS selectors and return the first match.

    Args:
        item: A selectolax node to search within
        selectors: List of CSS selectors to try in order

    Returns:
        First matching node, or None if no selector matches.
    """
    for selector in selectors:
        node = item.css_first(selector)
        if node is not None:
            return node
    return None


def _get_attr(node, attr: str, default: str = "") -> str:
    """Safely get an attribute from a selectolax node.

    Args:
        node: A selectolax node
        attr: Attribute name to retrieve
        default: Default value if attribute is missing

    Returns:
        Attribute value or default
    """
    if node is None:
        return default
    return node.attributes.get(attr, default)


# --- Individual Parsers ---


def _parse_search_result(item) -> SearchResult | None:
    """Parse a search result element into a SearchResult dataclass.

    Uses multiple CSS selector fallbacks for title, URL, and snippet
    extraction. Includes a depth-first text scan as last resort for
    snippet extraction when no known snippet element matches.
    """
    # --- Title and URL ---
    # Try multiple selectors for the title link
    title_el = _css_first(
        item,
        [
            ".__sri_title_link",
            "._0_sri_title_link",
            "a._0_URL",
            "a.__URL",
            ".sri-title a",
            "h3 a",
            "a[href]",  # Last resort: any link
        ],
    )

    if not title_el:
        return None

    # Extract URL
    url = _get_attr(title_el, "href", "")
    if not url or url.startswith("#"):
        # Try data-og-url as fallback
        url = _get_attr(item, "data-og-url", "") or _get_attr(item, "data-url", "")

    if not url:
        return None

    # Handle relative URLs
    if url.startswith("/"):
        url = f"https://kagi.com{url}"

    # Extract title
    title = _sanitize_text(title_el.text())

    if not title:
        return None

    # --- Snippet / description ---
    # Extended selector list with additional Kagi patterns for better extraction
    snippet_el = _css_first(
        item,
        [
            ".sri-desc",
            "._0_sri-desc",
            ".sri-snippet",
            "._0_sri-snippet",
            ".snippet",
            ".sri-body",
            "._0_sri-body",
            ".sri-rich",
            "._0_sri-rich",
            "[class*='snippet']",
            "[class*='desc']",
            "[class*='body']",
            "p",  # Fallback: first paragraph
        ],
    )

    if snippet_el is not None:
        snippet = _sanitize_text(snippet_el.text())
    else:
        # Depth-first text scan: extract the longest <p> or <div> text block
        # from the result item, excluding the title element
        snippet = _extract_longest_text_block(item, exclude_el=title_el)

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


def _parse_news_result(item) -> SearchResult | None:
    """Parse a news result element."""
    title_el = _css_first(
        item,
        [
            "a.news-title",
            ".news-title a",
            "h3 a",
            "a[href]",
        ],
    )

    if not title_el:
        return None

    url = _get_attr(title_el, "href", "")
    title = _sanitize_text(title_el.text())

    if not url or not title:
        return None

    if url.startswith("/"):
        url = f"https://kagi.com{url}"

    snippet_el = _css_first(
        item,
        [
            ".news-snippet",
            ".snippet",
            ".sri-body",
            "._0_sri-body",
            "[class*='snippet']",
            "[class*='desc']",
            "p",
        ],
    )

    if snippet_el is not None:
        snippet = _sanitize_text(snippet_el.text())
    else:
        snippet = _extract_longest_text_block(item, exclude_el=title_el)

    published = _extract_published_date(item)
    thumbnail = _extract_thumbnail(item)

    return SearchResult(
        url=url,
        title=title,
        snippet=snippet,
        published=published,
        thumbnail=thumbnail,
    )


def _parse_video_result(item) -> SearchResult | None:
    """Parse a video result element."""
    title_el = _css_first(
        item,
        [
            "a.video-title",
            ".video-title a",
            "h3 a",
            "a[href]",
        ],
    )

    if not title_el:
        return None

    url = _get_attr(title_el, "href", "")
    title = _sanitize_text(title_el.text())

    if not url or not title:
        return None

    if url.startswith("/"):
        url = f"https://kagi.com{url}"

    snippet_el = _css_first(
        item,
        [
            ".video-snippet",
            ".snippet",
            ".sri-body",
            "._0_sri-body",
            "[class*='snippet']",
            "[class*='desc']",
            "p",
        ],
    )

    if snippet_el is not None:
        snippet = _sanitize_text(snippet_el.text())
    else:
        snippet = _extract_longest_text_block(item, exclude_el=title_el)

    thumbnail = _extract_thumbnail(item)

    return SearchResult(
        url=url,
        title=title,
        snippet=snippet,
        published=None,
        thumbnail=thumbnail,
    )


def _parse_wikipedia_result(item) -> SearchResult | None:
    """Parse a Wikipedia / instant answer result element."""
    # Wikipedia results often have a different structure
    title_el = _css_first(
        item,
        [
            ".wiki-title a",
            ".instant-answer-title a",
            "h2 a",
            "h3 a",
            "a[href]",
        ],
    )

    if not title_el:
        return None

    url = _get_attr(title_el, "href", "")
    title = _sanitize_text(title_el.text())

    if not url or not title:
        return None

    if url.startswith("/"):
        url = f"https://kagi.com{url}"

    snippet_el = _css_first(
        item,
        [
            ".wiki-extract",
            ".wiki-desc",
            ".instant-answer-snippet",
            ".sri-body",
            "._0_sri-body",
            "[class*='snippet']",
            "[class*='desc']",
            "p",
        ],
    )

    if snippet_el is not None:
        snippet = _sanitize_text(snippet_el.text())
    else:
        snippet = _extract_longest_text_block(item, exclude_el=title_el)

    thumbnail = _extract_thumbnail(item)

    return SearchResult(
        url=url,
        title=title,
        snippet=snippet,
        published=None,
        thumbnail=thumbnail,
    )


def _extract_longest_text_block(item, exclude_el=None) -> str | None:
    """Depth-first scan for the longest <p> or <div> text block.

    Used as a last-resort fallback when no known snippet element matches.
    Skips the excluded element (typically the title link) to avoid
    duplicating the title as the snippet.

    Args:
        item: The selectolax result node to scan
        exclude_el: A node to exclude from text extraction (e.g., title element)

    Returns:
        Sanitized text of the longest text block found, or None
    """
    longest_text = ""
    exclude_html = ""
    if exclude_el is not None:
        try:
            exclude_html = exclude_el.html
        except Exception:
            pass  # If we can't get the HTML, don't exclude anything

    for tag_name in ("p", "div"):
        for node in item.css(tag_name):
            # Skip the excluded element (title) by comparing HTML content
            if exclude_html:
                try:
                    if node.html == exclude_html:
                        continue
                except Exception:
                    pass

            text = _sanitize_text(node.text())
            if len(text) > len(longest_text):
                longest_text = text

    return longest_text if longest_text else None


def _extract_published_date(item) -> str | None:
    """Extract published date from a result element."""
    # Try multiple selectors for date
    date_el = _css_first(
        item,
        [
            ".sri-date",
            "._0_sri-date",
            ".news-date",
            ".date",
            "time",
        ],
    )
    if date_el:
        date_text = _sanitize_text(date_el.text())
        if date_text:
            return date_text

    # Try datetime attribute on time element
    time_el = item.css_first("time[datetime]")
    if time_el:
        dt = _get_attr(time_el, "datetime", "")
        if dt:
            return str(dt)

    return None


def _extract_thumbnail(item) -> dict | None:
    """Extract thumbnail information from a result element."""
    img_el = _css_first(
        item,
        [
            ".sri-thumbnail img",
            "._0_sri-thumbnail img",
            ".thumbnail img",
            "img[src]",
        ],
    )
    if not img_el:
        return None

    src = _get_attr(img_el, "src", "")
    if not src or src.startswith("data:"):
        return None

    # Handle relative URLs
    if src.startswith("/"):
        src = f"https://kagi.com{src}"

    return {"src": src}


def _extract_related_searches(tree: LexborHTMLParser) -> RelatedSearches | None:
    """Extract related search suggestions."""
    terms: list[str] = []

    # Strategy 1: Explicit related searches container
    related_el = _css_first(
        tree,
        [
            ".related-searches",
            "._0_related-searches",
            ".related-searches-box",
        ],
    )
    if related_el:
        for a in related_el.css("a"):
            text = _sanitize_text(a.text())
            if text:
                terms.append(text)
        if terms:
            return RelatedSearches(items=terms)

    # Strategy 2: Look for "Related searches" / "People also search for" section
    for heading in tree.css("h2, h3, .section-title"):
        heading_text = heading.text(strip=True).lower()
        if any(
            keyword in heading_text
            for keyword in ["related", "also search", "related search"]
        ):
            # Find links in the parent container
            try:
                parent = heading.parent
            except Exception:
                parent = None
            if parent:
                for a in parent.css("a"):
                    text = _sanitize_text(a.text())
                    if text and text not in terms:
                        terms.append(text)
            if terms:
                return RelatedSearches(items=terms)

    # Strategy 3: Look for common related search patterns in list items
    for el in tree.css(".related-terms a, .related-links a"):
        text = _sanitize_text(el.text())
        if text:
            terms.append(text)

    return RelatedSearches(items=terms) if terms else None
