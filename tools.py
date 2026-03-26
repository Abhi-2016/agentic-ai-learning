"""
tools.py — The three tools available to the Research Synthesizer agent.

Each tool has:
  - A DESCRIPTION string: this is what the LLM reads to decide when to call it.
    (Remember Quiz 2: the description IS the product decision.)
  - A function: the actual code that runs when the agent calls the tool.

In a real production agent, these would call real APIs (Tavily, Browserless, a vector DB).
For learning, they use the Anthropic API's built-in web search via tool_use,
and a local JSON file as the scratchpad.
"""

import json
import os
from pathlib import Path

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
    STUB: In production, this calls a real search API (e.g. Tavily, SerpAPI).
    For now, returns a placeholder so you can see the tool call flow.
    Replace the body of this function with a real API call when ready.
    """
    # TODO: Replace with real search API
    # Example with Tavily:
    #   from tavily import TavilyClient
    #   client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    #   results = client.search(query)
    #   return json.dumps(results["results"])
    return (
        f"[STUB] search_web called with query: '{query}'\n"
        "Replace this stub with a real search API (e.g. Tavily) to get live results.\n"
        "Expected return format: list of {url, title, snippet} objects."
    )


def execute_read_page_contents(url: str) -> str:
    """
    STUB: In production, this calls a headless browser or scraping API.
    Replace with a real implementation when ready.
    """
    # TODO: Replace with real page reader
    # Example with requests + BeautifulSoup:
    #   import requests
    #   from bs4 import BeautifulSoup
    #   response = requests.get(url, timeout=10)
    #   soup = BeautifulSoup(response.text, "html.parser")
    #   return soup.get_text(separator="\n", strip=True)
    return (
        f"[STUB] read_page_contents called with url: '{url}'\n"
        "Replace this stub with a real scraper to get live page content.\n"
        "Expected return format: full text content of the page."
    )


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
