from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from foa_extract.models import FundingOpportunity

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

MAX_RETRIES = 3
BACKOFF_FACTOR = 1.5

# Selenium page-load timeout (seconds)
SELENIUM_WAIT = 15


def fetch_with_retry(url: str, headers: dict | None = None, timeout: int = 30) -> requests.Response:
    headers = headers or DEFAULT_HEADERS.copy()
    last_exception = None

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_exception = exc
            wait_time = BACKOFF_FACTOR ** attempt
            logger.warning(
                "Request attempt %d/%d failed for %s: %s. Retrying in %.1fs...",
                attempt + 1, MAX_RETRIES, url, exc, wait_time,
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait_time)

    raise ConnectionError(
        f"Failed to fetch {url} after {MAX_RETRIES} attempts: {last_exception}"
    )


def render_with_selenium(url: str, wait_seconds: int = SELENIUM_WAIT) -> str:
    """Use headless Chrome via Selenium to render a JS-heavy page.

    Returns the fully rendered HTML string.
    Raises ``RuntimeError`` if Selenium / Chrome is unavailable.
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError as exc:
        raise RuntimeError(
            "Selenium or webdriver-manager is not installed. "
            "Install with: pip install selenium webdriver-manager"
        ) from exc

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    # Suppress noisy logging
    options.add_argument("--log-level=3")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])

    logger.info("Launching headless Chrome for %s", url)
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )
    try:
        driver.get(url)
        # Wait for the page's main content table to appear
        try:
            WebDriverWait(driver, wait_seconds).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table tr td"))
            )
        except Exception:
            # Fallback: just wait a flat amount if the selector never appears
            logger.warning("Timed out waiting for table; using flat wait")
            time.sleep(wait_seconds)

        html = driver.page_source
        logger.info("Selenium rendered %d characters of HTML", len(html))
        return html
    finally:
        driver.quit()


class BaseIngestor(ABC):
    @abstractmethod
    def extract(self, url: str) -> FundingOpportunity:
        ...

    @staticmethod
    def clean_text(text: str | None) -> str:
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text)
        return text.strip()


class GrantsGovIngestor(BaseIngestor):

    def extract(self, url: str) -> FundingOpportunity:
        opp_id = self._extract_opportunity_id(url)

        # Primary path: render with Selenium (JS SPA)
        try:
            html = render_with_selenium(url)
            return self._parse_html(html, url, opp_id)
        except RuntimeError as sel_err:
            logger.warning("Selenium unavailable (%s), falling back to static HTML", sel_err)
        except Exception as sel_err:
            logger.warning("Selenium rendering failed (%s), falling back to static HTML", sel_err)

        # Fallback: plain requests (works if page is server-rendered)
        return self._extract_via_static_html(url, opp_id)

    def _extract_opportunity_id(self, url: str) -> str:
        match = re.search(r"/(\d+)(?:\?|$|#)", url)
        if match:
            return match.group(1)

        match = re.search(r"oppId=(\d+)", url)
        if match:
            return match.group(1)

        parts = url.rstrip("/").split("/")
        for part in reversed(parts):
            if part.isdigit():
                return part

        raise ValueError(f"Cannot extract opportunity ID from URL: {url}")

    def _extract_via_static_html(self, url: str, opp_id: str) -> FundingOpportunity:
        """Fallback: fetch raw HTML with requests (no JS rendering)."""
        response = fetch_with_retry(url)
        return self._parse_html(response.text, url, opp_id)

    def _parse_html(self, html: str, url: str, opp_id: str) -> FundingOpportunity:
        """Parse opportunity data from HTML (rendered or static)."""
        soup = BeautifulSoup(html, "lxml")

        title = (
            self._find_field(soup, [
                "Funding Opportunity Title",
                "Opportunity Title",
                "Title",
            ])
            or self._get_page_title(soup)
        )
        agency = self._find_field(soup, [
            "Agency Name",
            "Agency",
            "Department",
        ])
        opp_number = (
            self._find_field(soup, [
                "Funding Opportunity Number",
                "Opportunity Number",
            ])
            or opp_id
        )
        open_date = self._find_field(soup, [
            "Posted Date",
            "Open Date",
            "Post Date",
        ])
        close_date = self._find_field(soup, [
            "Current Closing Date for Applications",
            "Close Date",
            "Closing Date",
            "Original Closing Date for Applications",
            "Application Deadline",
        ])
        eligibility = self._find_field(soup, [
            "Eligible Applicants",
            "Eligibility",
        ])
        description = self._find_field(soup, [
            "Description",
            "Synopsis",
            "Opportunity Description",
        ])
        award_ceiling = self._find_field(soup, [
            "Award Ceiling",
            "Estimated Total Program Funding",
        ])
        award_floor = self._find_field(soup, ["Award Floor"])
        expected_awards = self._find_field(soup, ["Expected Number of Awards"])

        # Fallback: look for a synopsis/description div
        if not description:
            synopsis_div = soup.find("div", {"id": re.compile(r"synopsis|description", re.I)})
            if synopsis_div:
                description = self.clean_text(synopsis_div.get_text())

        return FundingOpportunity(
            foa_id=opp_number,
            title=title or "Unknown",
            agency=agency or "",
            open_date=open_date,
            close_date=close_date,
            eligibility=eligibility or "",
            description=self.clean_text(description),
            source_url=url,
            award_ceiling=award_ceiling,
            award_floor=award_floor,
            expected_awards=expected_awards,
        )

    def _find_field(self, soup: BeautifulSoup, labels: list[str]) -> str | None:
        """Find a field value by matching label text.

        Handles two common patterns:
        1. Label in a ``th/dt/label/strong/b/span`` followed by a value in
           ``td/dd/span/div/p``.
        2. Grants.gov table pattern: label in a ``td`` (label text may end
           with ``:``) with the value in the next ``td`` sibling.
        """
        for label in labels:
            # --- Pattern 1: th/dt/label/strong/b/span -> sibling value ---
            th = soup.find(
                ["th", "dt", "label", "strong", "b", "span"],
                string=re.compile(re.escape(label), re.I),
            )
            if th:
                sibling = th.find_next(["td", "dd", "span", "div", "p"])
                if sibling:
                    text = self.clean_text(sibling.get_text())
                    if text and text.lower() != label.lower():
                        return text

            # --- Pattern 2: td label -> next td value (Grants.gov SPA) ---
            label_re = re.compile(re.escape(label) + r"\s*:?\s*$", re.I)
            for td in soup.find_all("td", string=label_re):
                next_td = td.find_next_sibling("td")
                if next_td:
                    text = self.clean_text(next_td.get_text())
                    if text:
                        return text

            # --- Pattern 3: meta tag ---
            meta = soup.find("meta", {"name": re.compile(re.escape(label), re.I)})
            if meta and meta.get("content"):
                return self.clean_text(meta["content"])

        return None

    @staticmethod
    def _get_page_title(soup: BeautifulSoup) -> str:
        # Skip generic page titles like "Grants.gov" or "Search Results Detail"
        title_tag = soup.find("title")
        if title_tag:
            text = title_tag.get_text().strip()
            # Only use if it looks like an actual opportunity title
            skip = ["grants.gov", "search results", "view grant", "lock"]
            if text and not any(s in text.lower() for s in skip):
                return text

        h1 = soup.find("h1")
        if h1:
            text = h1.get_text().strip()
            if text and "view grant" not in text.lower():
                return text
        return "Unknown"


class NSFIngestor(BaseIngestor):

    def extract(self, url: str) -> FundingOpportunity:
        # Try Selenium first for JS-rendered pages
        html = None
        try:
            html = render_with_selenium(url)
        except Exception as exc:
            logger.warning("Selenium failed for NSF (%s), using static HTML", exc)

        if html is None:
            response = fetch_with_retry(url)
            html = response.text

        soup = BeautifulSoup(html, "lxml")

        award_id = self._extract_award_id(url)
        title = self._find_nsf_field(soup, ["Title", "Award Title"]) or self._get_page_title(soup)
        agency = "National Science Foundation"
        abstract = self._find_nsf_field(soup, ["Abstract", "Synopsis", "Program Synopsis"])
        start_date = self._find_nsf_field(soup, ["Start Date", "Effective Date", "Award Effective Date"])
        end_date = self._find_nsf_field(soup, ["End Date", "Expiration Date", "Award Expiration Date"])
        eligibility = self._find_nsf_field(soup, ["Eligible", "Eligibility", "Who May Submit"])
        award_amount = self._find_nsf_field(soup, ["Award Amount", "Awarded Amount", "Estimated Total"])

        if not abstract:
            for div in soup.find_all("div"):
                div_id = div.get("id", "")
                div_class = " ".join(div.get("class", []))
                if any(keyword in (div_id + div_class).lower() for keyword in ["abstract", "synopsis", "description"]):
                    abstract = self.clean_text(div.get_text())
                    break

        return FundingOpportunity(
            foa_id=award_id or "NSF-UNKNOWN",
            title=title or "Unknown",
            agency=agency,
            open_date=start_date,
            close_date=end_date,
            eligibility=eligibility or "",
            description=self.clean_text(abstract),
            source_url=url,
            award_ceiling=award_amount,
        )

    def _extract_award_id(self, url: str) -> str:
        match = re.search(r"AWD_ID=(\d+)", url, re.I)
        if match:
            return f"NSF-{match.group(1)}"

        match = re.search(r"/(\d{7,})(?:\?|$|#)", url)
        if match:
            return f"NSF-{match.group(1)}"

        return ""

    def _find_nsf_field(self, soup: BeautifulSoup, labels: list[str]) -> str | None:
        for label in labels:
            element = soup.find(
                ["th", "dt", "label", "strong", "b", "span", "div"],
                string=re.compile(re.escape(label), re.I),
            )
            if element:
                sibling = element.find_next(["td", "dd", "span", "div", "p"])
                if sibling:
                    text = self.clean_text(sibling.get_text())
                    if text and text.lower() != label.lower():
                        return text

            # td-td pattern
            label_re = re.compile(re.escape(label) + r"\s*:?\s*$", re.I)
            for td in soup.find_all("td", string=label_re):
                next_td = td.find_next_sibling("td")
                if next_td:
                    text = self.clean_text(next_td.get_text())
                    if text:
                        return text
        return None

    @staticmethod
    def _get_page_title(soup: BeautifulSoup) -> str:
        h1 = soup.find("h1")
        if h1:
            return h1.get_text().strip()
        title = soup.find("title")
        if title:
            return title.get_text().strip()
        return "Unknown"


class IngestorFactory:
    _registry: dict[str, type[BaseIngestor]] = {}

    @classmethod
    def register(cls, domain_pattern: str, ingestor_cls: type[BaseIngestor]) -> None:
        cls._registry[domain_pattern] = ingestor_cls

    @classmethod
    def get_ingestor(cls, url: str) -> BaseIngestor:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""

        for pattern, ingestor_cls in cls._registry.items():
            if pattern in hostname:
                return ingestor_cls()

        raise ValueError(
            f"No ingestor registered for domain: {hostname}. "
            f"Supported domains: {', '.join(cls._registry.keys())}"
        )


IngestorFactory.register("grants.gov", GrantsGovIngestor)
IngestorFactory.register("nsf.gov", NSFIngestor)


def ingest(url: str) -> FundingOpportunity:
    ingestor = IngestorFactory.get_ingestor(url)
    logger.info("Using %s for URL: %s", type(ingestor).__name__, url)
    return ingestor.extract(url)
