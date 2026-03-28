"""
tools.py — The three tools available to the Research Synthesizer agent.

Each tool has:
  - A DESCRIPTION string: this is what the LLM reads to decide when to call it.
    (Remember Quiz 2: the description IS the product decision.)
  - A function: the actual code that runs when the agent calls the tool.

Tool implementations:
  - search_web        → Tavily Search API (set TAVILY_API_KEY env var)
  - read_page_contents → requests + BeautifulSoup (no key needed)
  - save_note         → local scratchpad.json (persistent memory)
"""

import json
import os
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # loads .env from project root into os.environ

# Max characters to return from a page — full pages can be 100k+ chars and
# will overflow the context window. 8000 chars (~2000 tokens) is enough to
# extract meaningful findings without blowing up the agent's memory.
MAX_PAGE_CHARS = 8_000

# ── Scratchpad location ──────────────────────────────────────────────────────
# This is the PERSISTENT memory (Quiz 4: survives restarts, external to script).
SCRATCHPAD_PATH = Path(__file__).parent / "scratchpad.json"


def _load_scratchpad() -> list[dict]:
    """Read all saved notes from the persistent scratchpad file."""
    if not SCRATCHPAD_PATH.exists():
        return []
    with open(SCRATCHPAD_PATH, "r") as f:
        return json.load(f)


def _save_to_scratchpad(note: dict) -> None:
    """Append a new note to the scratchpad file."""
    notes = _load_scratchpad()
    notes.append(note)
    with open(SCRATCHPAD_PATH, "w") as f:
        json.dump(notes, f, indent=2)


# ── Tool definitions ─────────────────────────────────────────────────────────
# These are the structured tool schemas the LLM receives.
# The "description" field is what shapes agent behavior — not the code.

TOOLS = [
    {
        "name": "search_web",
        "description": (
            "Use this tool to search the internet for peer-reviewed articles or research papers "
            "on a given topic. The input can be a word, sentence, or alphanumeric string. "
            "Returns a list of URLs with short snippets about each result. "
            "Use this when you need to DISCOVER sources — not to read them. "
            "Do NOT use this to read the full content of a page; use read_page_contents for that. "
            "Prefer specific, targeted queries over broad ones to avoid irrelevant results."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query string."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "read_page_contents",
        "description": (
            "Use this tool to retrieve the full text content of a specific URL. "
            "Use this AFTER search_web has returned a promising URL, when you want to verify "
            "relevance or extract findings to save. "
            "Returns the full page content, which may include text, links, numbers, and images. "
            "Do NOT use this to perform web searches — use search_web for that."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The full URL of the page to read."
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "save_note",
        "description": (
            "Use this tool to store a confirmed, relevant finding to your persistent scratchpad memory. "
            "Use ONLY after reading a page with read_page_contents and confirming the content is "
            "relevant to the research topic. "
            "Each note must include: the finding (1-3 sentences), the source URL, "
            "and the author/organization and year if available. "
            "Do NOT use this to search the web (use search_web) or read a URL (use read_page_contents). "
            "Returns true if the note was saved successfully, false otherwise."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "finding": {
                    "type": "string",
                    "description": "The specific claim or insight to save (1-3 sentences)."
                },
                "source_url": {
                    "type": "string",
                    "description": "The URL this finding came from."
                },
                "author_or_org": {
                    "type": "string",
                    "description": "The author or organization. Use 'Unknown' if not found."
                },
                "year": {
                    "type": "string",
                    "description": "Publication year if available. Use 'Unknown' if not found."
                }
            },
            "required": ["finding", "source_url", "author_or_org", "year"]
        }
    }
]


# ── Tool execution functions ─────────────────────────────────────────────────
# These run when the agent decides to call a tool.
# The agent sees the DESCRIPTION above; Python executes the function below.

def execute_search_web(query: str) -> str:
    """
    Searches the web using the Tavily API and returns a list of results.

    Tavily is purpose-built for LLM agents — it returns clean, structured
    results rather than raw HTML, which makes it much easier for the agent
    to reason about what to read next.

    Requires: TAVILY_API_KEY environment variable.
    Get a free key at: https://app.tavily.com (free tier: 1000 searches/month)
    """
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return (
            "[error] TAVILY_API_KEY environment variable not set. "
            "Get a free key at https://app.tavily.com and run: "
            "export TAVILY_API_KEY=your_key_here"
        )

    try:
        # Tavily's /search endpoint — optimised for LLM agent use
        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "advanced",   # deeper crawl for research queries
                "max_results": 5,             # enough to evaluate, not overwhelming
                "include_answer": False,      # we want sources, not a pre-baked answer
            },
            timeout=15
        )
        response.raise_for_status()
        data = response.json()

        # Format results as a clean, readable list for the agent
        results = data.get("results", [])
        if not results:
            return f"No results found for query: '{query}'. Try a more specific search term."

        formatted = []
        for i, r in enumerate(results, 1):
            formatted.append(
                f"{i}. {r.get('title', 'No title')}\n"
                f"   URL: {r.get('url', '')}\n"
                f"   Snippet: {r.get('content', '')[:300]}..."
            )

        return f"Search results for '{query}':\n\n" + "\n\n".join(formatted)

    except requests.exceptions.Timeout:
        return "[error] Search timed out. Try again or use a more specific query."
    except requests.exceptions.RequestException as e:
        return f"[error] Search failed: {str(e)}"


def execute_read_page_contents(url: str) -> str:
    """
    Fetches a URL and returns its cleaned text content.

    Uses requests to fetch the page and BeautifulSoup to strip HTML tags,
    nav elements, footers, and scripts — leaving just the readable content.

    Why truncate? Full pages can be 50,000–200,000 characters. Feeding that
    raw into the context window would consume most of the agent's token budget
    on a single page. We take the first MAX_PAGE_CHARS characters, which is
    enough to evaluate relevance and extract key findings.

    Note: Some pages (paywalled journals, JS-rendered SPAs) will return
    limited content. This is expected — the agent should move on if a page
    returns less than ~500 characters of meaningful text.
    """
    headers = {
        # Polite browser-like user agent — reduces 403 rejections from servers
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove elements that add noise but no content
        for tag in soup(["script", "style", "nav", "footer", "header",
                         "aside", "advertisement", "cookie-banner"]):
            tag.decompose()

        # Extract clean text
        text = soup.get_text(separator="\n", strip=True)

        # Collapse excessive blank lines
        lines = [line for line in text.splitlines() if line.strip()]
        clean_text = "\n".join(lines)

        # Truncate to context-window-safe size
        if len(clean_text) > MAX_PAGE_CHARS:
            clean_text = clean_text[:MAX_PAGE_CHARS] + (
                f"\n\n[Content truncated at {MAX_PAGE_CHARS} characters. "
                "This is the most relevant portion of the page.]"
            )

        if len(clean_text) < 200:
            return (
                f"[warning] Page at {url} returned very little content ({len(clean_text)} chars). "
                "It may be paywalled, JS-rendered, or require authentication. "
                "Consider trying a different source.\n\n" + clean_text
            )

        return f"Content from {url}:\n\n{clean_text}"

    except requests.exceptions.Timeout:
        return f"[error] Timed out reading {url}. The page took too long to respond."
    except requests.exceptions.HTTPError as e:
        return f"[error] HTTP {e.response.status_code} reading {url}. Try a different source."
    except requests.exceptions.RequestException as e:
        return f"[error] Could not read {url}: {str(e)}"


def execute_save_note(finding: str, source_url: str, author_or_org: str, year: str) -> bool:
    """
    Saves a research finding to the persistent scratchpad (scratchpad.json).
    This is REAL — it actually writes to disk.
    This is the persistent memory from Quiz 4.
    """
    try:
        note = {
            "finding": finding,
            "source_url": source_url,
            "author_or_org": author_or_org,
            "year": year
        }
        _save_to_scratchpad(note)
        return True
    except Exception as e:
        print(f"[save_note error] {e}")
        return False


def get_saved_notes() -> list[dict]:
    """
    Returns all notes saved to the scratchpad so far.
    Used by agent.py to check the stopping condition:
    'Do I have 3 saved notes yet?'
    """
    return _load_scratchpad()


def clear_scratchpad() -> None:
    """
    Wipes the scratchpad clean. Call this at the start of a new research session
    if you don't want notes from a previous run to carry over.
    """
    if SCRATCHPAD_PATH.exists():
        SCRATCHPAD_PATH.write_text("[]")


# ── Tool dispatcher ───────────────────────────────────────────────────────────
# The agent.py loop calls this function after the LLM returns a tool_use block.
# It maps tool name → the right execution function.

def dispatch_tool(tool_name: str, tool_input: dict) -> str:
    """
    Routes a tool call from the agent to the correct function.
    Returns the tool result as a string to be fed back into the context window.
    """
    if tool_name == "search_web":
        return execute_search_web(**tool_input)

    elif tool_name == "read_page_contents":
        return execute_read_page_contents(**tool_input)

    elif tool_name == "save_note":
        success = execute_save_note(**tool_input)
        return "true" if success else "false"

    else:
        return f"[error] Unknown tool: {tool_name}"
