"""Result formatting for MCP tool output.

Formats SearchResponse data into the same text format as the official
kagimcp server, ensuring compatibility with existing MCP clients.
"""

from .parser import RelatedSearches, SearchResponse, SearchResult


def format_search_results(
    queries: list[str], responses: list[SearchResponse]
) -> str:
    """Format search results as numbered text, matching official kagimcp output format.

    Results from all queries are numbered continuously so that users can
    refer to a specific result by its number.

    Args:
        queries: List of search queries
        responses: List of SearchResponse objects (one per query)

    Returns:
        Formatted text string with numbered results
    """
    if not queries or not responses:
        return "No search results found."

    parts: list[str] = []
    result_number = 0

    for query_idx, (query, response) in enumerate(zip(queries, responses)):
        # Add query header
        if len(queries) > 1:
            parts.append(f"## Query: {query}\n")
        else:
            parts.append(f"## Search results for: {query}\n")

        if not response.data:
            parts.append("No results found for this query.\n")
            continue

        for item in response.data:
            if isinstance(item, SearchResult):
                result_number += 1
                parts.append(_format_search_result(item, result_number))
            elif isinstance(item, RelatedSearches):
                parts.append(_format_related_searches(item))

        # Add separator between queries
        if query_idx < len(queries) - 1:
            parts.append("---\n")

    return "\n".join(parts)


def _format_search_result(result: SearchResult, number: int) -> str:
    """Format a single SearchResult as numbered text.

    Format matches official kagimcp:
    ```
    1. Title
       URL
       Published: 2024-01-01
       Snippet text here...
    ```
    """
    lines: list[str] = []

    # Title with number
    lines.append(f"{number}. {result.title}")

    # URL (indented)
    lines.append(f"   {result.url}")

    # Published date (if available)
    if result.published:
        lines.append(f"   Published: {result.published}")

    # Snippet (if available)
    if result.snippet:
        lines.append(f"   {result.snippet}")

    lines.append("")  # Blank line between results

    return "\n".join(lines)


def _format_related_searches(related: RelatedSearches) -> str:
    """Format related searches section."""
    if not related.items:
        return ""

    lines = ["**Related searches:**"]
    lines.append(", ".join(related.items))
    lines.append("")

    return "\n".join(lines)


def format_summarizer_result(summary_data: dict) -> str:
    """Format summarizer result as text.

    Args:
        summary_data: Parsed JSON response from /mother/summary_labs

    Returns:
        Formatted summary text
    """
    # The summarizer endpoint returns different structures depending on the engine
    # Try common paths for the summary text
    output = None

    # Path 1: data.output (most common)
    if "data" in summary_data and isinstance(summary_data["data"], dict):
        output = summary_data["data"].get("output")

    # Path 2: output at top level
    if not output and "output" in summary_data:
        output = summary_data["output"]

    # Path 3: summary at top level
    if not output and "summary" in summary_data:
        output = summary_data["summary"]

    if output:
        return str(output)

    # If we can't find the summary, return the raw data as formatted text
    return f"Summary data: {summary_data}"
