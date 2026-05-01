# Kagi Session2API MCP Server

A Kagi Search MCP (Model Context Protocol) server that uses session token authentication instead of the official paid API.

**[English](README.md)** | [中文文档](README_ZH.md)

> **⚠️ EndUser Warning**: This project uses Kagi session tokens to access search and summarizer features without the official paid API. This may violate [Kagi's Terms of Service](https://kagi.com/terms). Potential consequences include account suspension or permanent ban. **Use at your own risk.** The authors assume no liability for any account actions taken by Kagi.
>
> **⚠️ Security Warning**: Your Kagi session token provides full account access. Treat it like a password. Never share it or commit it to version control.

## Features

- **Session-based access**: Uses Kagi session tokens instead of the official API ($25/1000 queries)
- **Multi-token pool**: Configure multiple tokens for higher throughput with round-robin rotation
- **Per-token rate limiting**: 5 req/s per token with token bucket algorithm
- **API-compatible output**: Returns results in the same format as the official `kagimcp`
- **Two tools**: `kagi_search_fetch` (web search) and `kagi_summarizer` (URL summarization)
- **Firefox UA spoofing**: Mimics a real Firefox browser for session-based access
- **Auto-disable expired tokens**: Expired tokens are automatically detected and skipped
- **Search operators**: Supports Kagi operators (`site:`, `lang:`, `filetype:`, etc.)

## Installation

```bash
pip install kagi-session2api-mcp
```

Or with `uvx`:
```bash
uvx kagi-session2api-mcp
```

## Configuration

### Option 1: Environment Variable (Single Token)

```json
{
  "mcpServers": {
    "kagi-session": {
      "command": "uvx",
      "args": ["kagi-session2api-mcp"],
      "env": {
        "KAGI_SESSION_TOKEN": "YOUR_SESSION_TOKEN_HERE"
      }
    }
  }
}
```

### Option 2: Environment Variable (Multiple Tokens)

```json
{
  "mcpServers": {
    "kagi-session": {
      "command": "uvx",
      "args": ["kagi-session2api-mcp"],
      "env": {
        "KAGI_SESSION_TOKENS": "TOKEN_1,TOKEN_2,TOKEN_3"
      }
    }
  }
}
```

### Option 3: Config File (Recommended for Multi-Token)

Create `~/.config/kagi-session2api-mcp/config.toml`:

```toml
[kagi]
session_tokens = [
    "YOUR_TOKEN_1_HERE",
    "YOUR_TOKEN_2_HERE",
]

summarizer_engine = "cecil"

[client]
timeout = 30
max_retries = 2
```

Then configure:
```json
{
  "mcpServers": {
    "kagi-session": {
      "command": "uvx",
      "args": ["kagi-session2api-mcp"],
      "env": {
        "KAGI_SESSION_CONFIG": "/path/to/config.toml"
      }
    }
  }
}
```

## Getting Your Session Token

1. Log in to [kagi.com](https://kagi.com)
2. Go to **Settings → Account → Session Link**
3. Copy the token from the session URL: `https://kagi.com/search?token={THIS_PART}&q=test`
4. Use this token in your configuration

## Usage

### MCP Tools

#### `kagi_search_fetch`

Search the web using Kagi:

```
Search for "Python async tutorial"
```

Supports Kagi search operators:
- `site:github.com` - Restrict to domain
- `-site:reddit.com` - Exclude domain
- `filetype:pdf` - File type filter
- `intitle:python` - Title filter
- `lang:zh` - Language filter
- `before:2024-01-01` / `after:2024-01-01` - Date filters
- `"exact phrase"` - Exact match

#### `kagi_summarizer`

Summarize any URL:

```
Summarize https://example.com/article
```

Options:
- `summary_type`: "summary" (prose) or "takeaway" (bullet points)
- `engine`: "cecil" (default), "agnes", "daphne", "muriel"
- `target_language`: Language code (e.g., "EN")

> ⚠️ The summarizer is experimental — it uses Kagi's internal endpoint which may change.

### Transport Modes

**Stdio** (default, for Claude Desktop):
```bash
kagi-session2api-mcp
```

**HTTP** (for remote access):
```bash
kagi-session2api-mcp --http --host 0.0.0.0 --port 8000
```

## Architecture

```
MCP Client → FastMCP Server → TokenPool (round-robin) → httpx.AsyncClient → kagi.com
                                ↓
                          TokenBucket (5 req/s per token)
                                ↓
                          Auto-disable expired tokens
```

## Token Pool Behavior

| Config | Rate Limit | Effective Rate |
|--------|-----------|----------------|
| 1 token | 5 req/s | 5 req/s |
| 2 tokens | 5 req/s each | 10 req/s |
| N tokens | 5 req/s each | 5×N req/s |

When a token expires (detected via 401/403 or redirect to login), it is automatically disabled. Remaining tokens continue serving requests.

## Differences from Official `kagimcp`

| Aspect | Official `kagimcp` | `kagi-session2api-mcp` |
|--------|-------------------|-------------------|
| Authentication | API key ($25/1000) | Session token (free) |
| Search endpoint | `/api/v0/search` | `/html/search` (HTML scraping) |
| Summarizer | `/api/v0/summarize` | `/mother/summary_labs` (internal) |
| Rate limiting | Server-side | Client-side (token bucket) |
| `api_balance` | Returns balance | Always `null` |
| Cost | Paid | Free (uses existing session) |

## Risks

- Kagi may change their HTML structure, breaking the parser
- Session-based access may violate Kagi's Terms of Service
- Account suspension or permanent ban is possible
- The summarizer endpoint is internal and may change without notice
- **Use at your own risk.** The authors assume no liability for any consequences, including but not limited to account actions taken by Kagi.

## License

MIT
