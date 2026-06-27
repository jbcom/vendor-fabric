"""Tests for the scraping tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


pytest.importorskip("crewai", reason="crewai not installed")

from vendor_fabric.agentic.tools.scraping_tools import CrawlWebsiteTool


@patch("vendor_fabric.agentic.tools.scraping_tools.requests.get")
def test_crawl_website_tool(mock_get: MagicMock):
    """Tests that the CrawlWebsiteTool scrapes content and discovers links."""
    mock_response_page1 = MagicMock()
    mock_response_page1.content = b'<html><body><a href="/page2">Page 2</a><p>Content 1</p></body></html>'
    mock_response_page1.raise_for_status.return_value = None

    mock_response_page2 = MagicMock()
    mock_response_page2.content = b"<html><body><p>Content 2</p></body></html>"
    mock_response_page2.raise_for_status.return_value = None

    mock_get.side_effect = [mock_response_page1, mock_response_page2]

    tool = CrawlWebsiteTool()
    result = tool._run("http://example.com")

    assert "Content 1" in result
    assert "Page 2" in result
    assert "Content 2" in result
    assert mock_get.call_count == 2


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://localhost",
        "http://127.0.0.1",
        "http://10.0.0.1",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://metadata.google.internal/computeMetadata/v1/",
    ],
)
@patch("vendor_fabric.agentic.tools.scraping_tools.requests.get")
def test_crawl_website_tool_blocks_unsafe_urls(mock_get: MagicMock, url: str):
    """Crawler should reject protocols and hosts that could enable SSRF."""
    tool = CrawlWebsiteTool()

    result = tool._run(url)

    assert result.startswith("Error:")
    mock_get.assert_not_called()
