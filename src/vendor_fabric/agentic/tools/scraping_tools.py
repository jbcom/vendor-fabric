"""Web scraping tools for agentic workflows."""

from __future__ import annotations

import logging

from ipaddress import IPv6Address, ip_address
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse

import requests

from bs4 import BeautifulSoup


if TYPE_CHECKING:

    class ScrapeWebsiteTool:
        """Minimal scrape-tool fallback used when CrewAI tools are not installed."""

else:
    try:
        from crewai_tools import ScrapeWebsiteTool
    except ImportError:

        class ScrapeWebsiteTool:
            """Minimal scrape-tool fallback used when CrewAI tools are not installed."""


log = logging.getLogger(__name__)
REQUEST_TIMEOUT_SECONDS = 30
BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal"}


def _is_blocked_host(hostname: str | None) -> bool:
    """Return whether a crawl hostname targets local, private, or metadata resources."""
    if not hostname:
        return True

    normalized = hostname.strip().lower().rstrip(".")
    if normalized in BLOCKED_HOSTNAMES:
        return True
    if normalized.startswith("metadata.") or normalized.endswith((".local", ".internal")):
        return True

    try:
        parsed_ip = ip_address(normalized)
    except ValueError:
        return False

    if isinstance(parsed_ip, IPv6Address) and parsed_ip.ipv4_mapped is not None:
        parsed_ip = parsed_ip.ipv4_mapped

    return any(
        (
            parsed_ip.is_loopback,
            parsed_ip.is_link_local,
            parsed_ip.is_private,
            parsed_ip.is_reserved,
            parsed_ip.is_unspecified,
            parsed_ip.is_multicast,
        )
    )


def _validate_crawl_url(url: str) -> str | None:
    """Return an error message when a crawl URL is unsupported or unsafe."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return "Error: Only HTTP and HTTPS protocols are allowed."
    if _is_blocked_host(parsed.hostname):
        return "Error: Access to local, private, or metadata addresses is blocked."
    return None


class CrawlWebsiteTool(ScrapeWebsiteTool):
    """A tool for crawling a website and scraping its content.

    This tool extends ScrapeWebsiteTool to support crawling multiple pages
    starting from a given URL.
    """

    name: str = "CrawlWebsiteTool"
    description: str = "Crawl a website from a given URL and scrape its content."

    def _run(self, url: str) -> str:
        """Crawls a website and returns the scraped content.

        Args:
            url: The URL to start crawling from.

        Returns:
            The scraped content of the website.
        """
        if error := _validate_crawl_url(url):
            return error

        scraped_content = ""
        visited_urls = set()
        urls_to_visit = [url]
        base_netloc = urlparse(url).netloc

        while urls_to_visit:
            current_url = urls_to_visit.pop(0)
            if current_url in visited_urls:
                continue

            try:
                response = requests.get(current_url, timeout=REQUEST_TIMEOUT_SECONDS)
                response.raise_for_status()
                visited_urls.add(current_url)

                soup = BeautifulSoup(response.content, "html.parser")
                scraped_content += self._scrape_content(soup)

                for link in soup.find_all("a", href=True):
                    href = link.get("href")
                    if not isinstance(href, str):
                        continue

                    next_url = urljoin(current_url, href)
                    if (
                        urlparse(next_url).netloc == base_netloc
                        and next_url not in visited_urls
                        and _validate_crawl_url(next_url) is None
                    ):
                        urls_to_visit.append(next_url)

            except requests.RequestException:
                log.exception("Error crawling %s", current_url)

        return scraped_content

    def _scrape_content(self, soup: BeautifulSoup) -> str:
        """Scrapes the readable content from a BeautifulSoup object."""
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()
        return " ".join(t.strip() for t in soup.stripped_strings)
