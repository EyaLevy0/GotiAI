"""
Godot documentation retrieval tool for the Scene Agent.

This module fetches relevant context from the official Godot documentation.
It is responsible only for documentation retrieval, not for code generation.

Main public function:
    retrieve_godot_docs_context(query)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

GODOT_DOCS_BASE_URL = "https://docs.godotengine.org/en/stable"
REQUEST_TIMEOUT_SECONDS = 20
DEFAULT_MAX_CHARS_PER_PAGE = 4000
DEFAULT_MAX_TOTAL_CHARS = 8000


@dataclass
class GodotDocsPage:
    """
    Represents one retrieved Godot documentation page.
    """

    title: str
    url: str
    text: str


def _normalize_class_name(topic: str) -> str:
    """
    Convert a Godot class name into the format used by Godot class docs URLs.

    Example:
        CharacterBody2D -> characterbody2d
        Node2D -> node2d
    """

    return topic.strip().lower()


def _build_class_docs_url(class_name: str) -> str:
    """
    Build a Godot class reference URL.

    Example:
        CharacterBody2D
        -> https://docs.godotengine.org/en/stable/classes/class_characterbody2d.html
    """

    normalized = _normalize_class_name(class_name)
    return f"{GODOT_DOCS_BASE_URL}/classes/class_{normalized}.html"


def _build_search_url(query: str) -> str:
    """
    Build a Godot documentation search URL.
    """

    encoded_query = quote_plus(query.strip())
    return (
        f"{GODOT_DOCS_BASE_URL}/search.html"
        f"?q={encoded_query}&check_keywords=yes&area=default"
    )


def _fetch_html(url: str) -> str:
    """
    Fetch raw HTML from a URL.
    """

    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": "GotiAI-Scene-Agent/0.1"},
    )

    response.raise_for_status()
    return response.text


def _extract_main_text(html: str) -> str:
    """
    Extract readable documentation text from a Godot docs HTML page.
    """

    soup = BeautifulSoup(html, "html.parser")

    main_content = soup.find("div", {"role": "main"})

    if main_content is None:
        main_content = soup.find("main")

    if main_content is None:
        main_content = soup.body

    if main_content is None:
        return ""

    for unwanted in main_content(["script", "style", "nav", "footer", "header"]):
        unwanted.decompose()

    text = main_content.get_text(separator="\n")

    clean_lines = []

    for line in text.splitlines():
        clean_line = line.strip()

        if clean_line:
            clean_lines.append(clean_line)

    return "\n".join(clean_lines)


def _extract_page_title(html: str, fallback_url: str) -> str:
    """
    Extract a readable title from a documentation page.
    """

    soup = BeautifulSoup(html, "html.parser")

    heading = soup.find(["h1", "h2"])

    if heading:
        return heading.get_text(strip=True)

    if soup.title:
        return soup.title.get_text(strip=True)

    return fallback_url


def _limit_text(text: str, max_chars: int) -> str:
    """
    Limit text size so the LLM prompt does not become too large.
    """

    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "\n\n[Documentation context truncated]"


def _fetch_docs_page(url: str, max_chars: int) -> Optional[GodotDocsPage]:
    """
    Fetch one documentation page and return extracted text.
    """

    try:
        html = _fetch_html(url)
    except requests.RequestException:
        return None

    title = _extract_page_title(html, fallback_url=url)
    text = _extract_main_text(html)

    if not text:
        return None

    return GodotDocsPage(
        title=title,
        url=url,
        text=_limit_text(text, max_chars=max_chars),
    )


def _looks_like_class_name(query: str) -> bool:
    """
    Heuristic for detecting Godot class names.

    Examples:
        CharacterBody2D -> True
        Node2D -> True
        player movement -> False
    """

    clean_query = query.strip()

    if not clean_query:
        return False

    if " " in clean_query:
        return False

    return any(char.isupper() for char in clean_query)


def _extract_search_result_links(search_html: str, max_results: int) -> List[str]:
    """
    Extract documentation result links from a Godot search page.

    This works with the server-rendered fallback content when available.
    """

    soup = BeautifulSoup(search_html, "html.parser")
    links: List[str] = []

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]

        if not href.endswith(".html") and ".html#" not in href:
            continue

        absolute_url = urljoin(GODOT_DOCS_BASE_URL + "/", href)

        if "docs.godotengine.org/en/stable/" not in absolute_url:
            continue

        if absolute_url not in links:
            links.append(absolute_url)

        if len(links) >= max_results:
            break

    return links


def _search_godot_docs(query: str, max_results: int) -> List[str]:
    """
    Search Godot docs and return candidate documentation URLs.
    """

    search_url = _build_search_url(query)

    try:
        search_html = _fetch_html(search_url)
    except requests.RequestException:
        return []

    return _extract_search_result_links(search_html, max_results=max_results)


def retrieve_godot_docs_pages(
    query: str,
    max_pages: int = 3,
    max_chars_per_page: int = DEFAULT_MAX_CHARS_PER_PAGE,
) -> List[GodotDocsPage]:
    """
    Retrieve relevant Godot documentation pages for a query.

    Strategy:
        1. If the query looks like a class name, try the exact class page first.
        2. Search the Godot documentation.
        3. Fetch the best result pages.
    """

    clean_query = query.strip()

    if not clean_query:
        return []

    pages: List[GodotDocsPage] = []
    visited_urls = set()

    if _looks_like_class_name(clean_query):
        class_url = _build_class_docs_url(clean_query)
        page = _fetch_docs_page(class_url, max_chars=max_chars_per_page)

        if page:
            pages.append(page)
            visited_urls.add(class_url)

    search_result_urls = _search_godot_docs(clean_query, max_results=max_pages * 2)

    for url in search_result_urls:
        if len(pages) >= max_pages:
            break

        if url in visited_urls:
            continue

        page = _fetch_docs_page(url, max_chars=max_chars_per_page)

        if page:
            pages.append(page)
            visited_urls.add(url)

    return pages


def format_docs_pages_as_context(
    pages: List[GodotDocsPage],
    max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
) -> str:
    """
    Convert retrieved pages into one context string for the LLM.
    """

    if not pages:
        return "No relevant Godot documentation context was found."

    sections = []

    for index, page in enumerate(pages, start=1):
        section = f"""
[Godot Docs Page {index}]
Title: {page.title}
URL: {page.url}

{page.text}
"""
        sections.append(section.strip())

    context = "\n\n---\n\n".join(sections)

    return _limit_text(context, max_chars=max_total_chars)


def retrieve_godot_docs_context(
    query: str,
    max_pages: int = 3,
    max_chars_per_page: int = DEFAULT_MAX_CHARS_PER_PAGE,
    max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
) -> str:
    """
    Retrieve relevant Godot documentation context for a user query.

    This is the main function other tools should call.
    """

    pages = retrieve_godot_docs_pages(
        query=query,
        max_pages=max_pages,
        max_chars_per_page=max_chars_per_page,
    )

    return format_docs_pages_as_context(
        pages=pages,
        max_total_chars=max_total_chars,
    )


def lookup_godot_topic(topic: str, max_chars: int = DEFAULT_MAX_TOTAL_CHARS) -> str:
    """
    Backward-compatible wrapper.

    Older code can still call lookup_godot_topic(topic).
    Internally, this now performs real Godot documentation retrieval.
    """

    return retrieve_godot_docs_context(
        query=topic,
        max_total_chars=max_chars,
    )
