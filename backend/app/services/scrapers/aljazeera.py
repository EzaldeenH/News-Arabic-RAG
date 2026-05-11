"""
Al Jazeera Arabic Scraper.
Specialized scraper for Al Jazeera Arabic news (aljazeera.net).
Scrapes all main categories and their subcategories, enters each article
to extract full body text, title, author, date, and metadata.
"""
import re
import logging
import time
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse, unquote
import requests
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Full site-map: main categories → subcategories
# Each entry is (arabic_label, url_path, auto_category, auto_region)
# ──────────────────────────────────────────────────────────────────────
ALJAZEERA_SECTIONS = {
    "أخبار": {
        "label": "News",
        "subcategories": [
            ("عربي", "/where/mideast/arab/"),
            ("دولي", "/where/intl/"),
            ("سياسة", "/politics"),
            ("مراسلو الجزيرة", "/politics/reporters"),
            ("صحافة", "/politics/presstour"),
            ("تحقق", "/fact-check"),
            ("وسم", "/tag/viral/"),
            ("موسوعة", "/encyclopedia"),
            ("حريات", "/tag/humanrights/"),
            ("بالصور", "/gallery"),
        ],
    },
    "اقتصاد": {
        "label": "Economy",
        "subcategories": [
            ("اقتصاد", "/ebusiness/"),
            ("عربي", "/ebusiness/arab-economy"),
            ("دولي", "/ebusiness/world-economy"),
            ("أسواق", "/ebusiness/markets"),
            ("شخصي", "/ebusiness/personal-finance"),
            ("ريادة", "/ebusiness/reyada"),
        ],
    },
    "رأي": {
        "label": "Opinion",
        "subcategories": [
            ("مقالات", "/opinion/"),
            ("مدونات", "/blogs/"),
        ],
    },
    "ميدان": {
        "label": "Dimensions",
        "subcategories": [
            ("إعلام", "/media/"),
            ("دراسات", "/tag/studies/"),
            ("تراث", "/turath/"),
            ("سلاح", "/dimensions/military"),
            ("صراع", "/dimensions/conflict"),
            ("فكر ونفس", "/dimensions/existence"),
            ("وجوه", "/dimensions/profiles"),
            ("ملفات", "/dimensions/specialfiles"),
        ],
    },
    "متخصصة": {
        "label": "Specialized",
        "subcategories": [
            ("رياضة", "/sport/"),
            ("علوم وبيئة", "/science/"),
            ("صحة", "/health/"),
            ("تقنية", "/tech/"),
            ("أسلوب حياة", "/lifestyle/"),
            ("أسرة", "/family/"),
            ("سفر", "/travel"),
            ("ثقافة", "/culture/"),
            ("فن", "/arts/"),
            ("منوعات", "/misc/"),
        ],
    },
    "محليات": {
        "label": "Local",
        "subcategories": [
            ("فلسطين", "/where/mideast/arab/palestine/"),
            ("اليمن", "/where/mideast/arab/yemen/"),
            ("سوريا", "/where/mideast/arab/syria/"),
            ("السودان", "/where/mideast/arab/sudan/"),
            ("مصر", "/where/mideast/arab/egypt/"),
            ("العراق", "/where/mideast/arab/iraq/"),
            ("لبنان", "/where/mideast/arab/lebanon/"),
            ("المغرب", "/where/mideast/arab/morocco/"),
            ("ليبيا", "/where/mideast/arab/libya/"),
        ],
    },
}


class AlJazeeraScraper:
    """
    Scraper for Al Jazeera Arabic news (aljazeera.net).
    Navigates all main categories and their subcategories,
    enters each article page to extract full content.
    """

    BASE_URL = "https://www.aljazeera.net"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "ar-SA,ar;q=0.9,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
    }

    # Paths that should never be treated as articles
    _SKIP_PREFIXES = (
        "/video/",
        "/video/live",
        "/videos/",
        "/aljazeerarss/",
        "/newsletters",
        "/sitemap",
    )

    def __init__(self, timeout: int = 30, request_delay: float = 1.0):
        """
        Args:
            timeout: HTTP request timeout in seconds
            request_delay: Seconds to wait between requests (politeness)
        """
        self.timeout = timeout
        self.request_delay = request_delay
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    # ─── HTTP helpers ────────────────────────────────────────────────

    def fetch_page(self, url: str) -> Optional[str]:
        """
        Fetch HTML content from a URL.

        Args:
            url: URL to fetch

        Returns:
            HTML content or None if failed
        """
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            response.encoding = "utf-8"
            return response.text
        except requests.RequestException as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None

    # ─── URL classification ──────────────────────────────────────────

    def _is_article_url(self, href: str) -> bool:
        """
        Check whether *href* points to an individual Al Jazeera article.
        Al Jazeera article URLs typically follow the pattern:
          /section/YYYY/M/DD/slug   or
          /section/subsection/YYYY/M/DD/slug

        We also accept encyclopedia and liveblog URLs.
        """
        # Must be on aljazeera.net (relative or absolute)
        if href.startswith("http") and "aljazeera.net" not in href:
            return False

        # Skip known non-article paths
        for prefix in self._SKIP_PREFIXES:
            if href.startswith(prefix) or (
                "aljazeera.net" in href and prefix in href
            ):
                return False

        # Match /section(.../subsection)?/YYYY/M/DD/slug
        pattern = r"/([\w-]+/){1,3}\d{4}/\d{1,2}/\d{1,2}/[\w%\u0600-\u06FF-]+"
        if re.search(pattern, href):
            return True

        return False

    def _detect_metadata_from_url(
        self, url: str
    ) -> Tuple[str, str]:
        """
        Auto-detect main_category and subcategory from the article URL path.

        Returns:
            (main_category, subcategory) tuple
        """
        path = urlparse(url).path

        best_main = "أخبار"
        best_sub = "عربي"

        # Match against ALJAZEERA_SECTIONS paths
        # Iterate over sections to find the longest matching path
        best_match_len = 0
        for main_cat, info in ALJAZEERA_SECTIONS.items():
            for sub_cat, sub_path in info["subcategories"]:
                if sub_path in path and len(sub_path) > best_match_len:
                    best_main = main_cat
                    best_sub = sub_cat
                    best_match_len = len(sub_path)

        return best_main, best_sub

    # ─── Listing-page parsing ────────────────────────────────────────

    def extract_article_urls(self, html: str) -> List[str]:
        """
        Extract unique article URLs from a listing / section page.
        Only returns articles visible before the "show more" button.

        Args:
            html: HTML content of the listing page

        Returns:
            De-duplicated list of absolute article URLs
        """
        soup = BeautifulSoup(html, "html.parser")
        seen = set()
        urls: List[str] = []

        for link in soup.find_all("a", href=True):
            href = link["href"]
            if self._is_article_url(href):
                full_url = urljoin(self.BASE_URL, href)
                if full_url not in seen:
                    seen.add(full_url)
                    urls.append(full_url)

        logger.info(f"Found {len(urls)} article URLs on listing page")
        return urls

    # ─── Individual article extraction ───────────────────────────────

    def scrape_article(self, url: str) -> Optional[Dict[str, str]]:
        """
        Scrape a single Al Jazeera article page.
        Enters the article and extracts full body text, not just the title.

        Args:
            url: Article URL

        Returns:
            Dict with title, content, author, date, description, etc.
            None if the page could not be parsed.
        """
        html = self.fetch_page(url)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")

        # ── Title ────────────────────────────────────────────────────
        title = self._extract_title(soup)
        if not title:
            logger.warning(f"No title found for {url}")
            return None

        # Require Arabic text
        if not self._is_arabic_text(title):
            logger.info(f"Skipping non-Arabic article: {url}")
            return None

        # ── Body content ─────────────────────────────────────────────
        content = self._extract_content(soup)
        if not content:
            logger.warning(f"No content found for {url}")
            return None

        # ── Metadata ─────────────────────────────────────────────────
        author = self._extract_author(soup)
        date = self._extract_date(soup)
        description = self._extract_description(soup)
        main_category, subcategory = self._detect_metadata_from_url(url)

        return {
            "url": url,
            "title": title,
            "content": content,
            "author": author or "الجزيرة نت",
            "date": date or "",
            "description": description or title,
            "source": "Al Jazeera Arabic",
            "language": "ar",
            "main_category": main_category,
            "subcategory": subcategory,
        }

    # ─── Extraction helpers ──────────────────────────────────────────

    @staticmethod
    def _is_arabic_text(text: str) -> bool:
        """Return True if ≥30 % of characters are Arabic."""
        arabic_chars = len(re.findall(r"[\u0600-\u06FF]", text))
        return (arabic_chars / max(len(text), 1)) >= 0.3

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> Optional[str]:
        """Extract article title from <h1> or og:title."""
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)

        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            return og["content"]

        return None

    @staticmethod
    def _extract_content(soup: BeautifulSoup) -> Optional[str]:
        """
        Extract the full article body text.
        Al Jazeera articles use a main content area identified by
        id="main-content-area" or the <article> tag, with the body
        text in <p> tags.
        """
        content_parts: List[str] = []

        # Strategy 1: main content area by id
        main_area = soup.find(id="main-content-area")

        # Strategy 2: <article> tag
        if not main_area:
            main_area = soup.find("article")

        # Strategy 3: <main> tag
        if not main_area:
            main_area = soup.find("main")

        if main_area:
            for p in main_area.find_all("p"):
                text = p.get_text(strip=True)
                if text and len(text) > 20:
                    content_parts.append(text)

        # Strategy 4 (fallback): all <p> tags in body, filtering noise
        if not content_parts:
            body = soup.find("body")
            if body:
                for p in body.find_all("p"):
                    text = p.get_text(strip=True)
                    # Skip very short or navigation-like text
                    if text and len(text) > 40:
                        content_parts.append(text)

        if content_parts:
            return "\n\n".join(content_parts)

        return None

    @staticmethod
    def _extract_author(soup: BeautifulSoup) -> Optional[str]:
        """Extract author from meta tags or byline elements."""
        meta = soup.find("meta", attrs={"name": "author"})
        if meta and meta.get("content"):
            return meta["content"]

        # og:article:author
        og = soup.find("meta", property="article:author")
        if og and og.get("content"):
            return og["content"]

        # Byline div (common pattern)
        byline = soup.find("div", class_=re.compile(r"byline|author", re.I))
        if byline:
            return byline.get_text(strip=True)

        return None

    @staticmethod
    def _extract_date(soup: BeautifulSoup) -> Optional[str]:
        """Extract publication date."""
        meta = soup.find("meta", property="article:published_time")
        if meta and meta.get("content"):
            return meta["content"]

        meta2 = soup.find("meta", attrs={"name": "date"})
        if meta2 and meta2.get("content"):
            return meta2["content"]

        time_tag = soup.find("time")
        if time_tag:
            return time_tag.get("datetime") or time_tag.get_text(strip=True)

        return None

    @staticmethod
    def _extract_description(soup: BeautifulSoup) -> Optional[str]:
        """Extract article description / summary."""
        og = soup.find("meta", property="og:description")
        if og and og.get("content"):
            return og["content"]

        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            return meta["content"]

        return None

    # ─── Section-level scraping ──────────────────────────────────────

    def scrape_section(
        self,
        section_path: str,
        default_main_category: str = "أخبار",
        default_subcategory: str = "عربي",
        max_articles: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """
        Scrape all visible articles from a single section/subcategory page.

        Args:
            section_path: URL path like "/where/mideast/arab/"
            default_main_category: Fallback main category if not detectable from URL
            default_subcategory: Fallback subcategory if not detectable from URL
            max_articles: Optional cap on articles per section

        Returns:
            List of article dicts with full body content
        """
        section_url = urljoin(self.BASE_URL, section_path)
        logger.info(f"Scraping section: {section_url}")

        html = self.fetch_page(section_url)
        if not html:
            logger.error(f"Failed to fetch section: {section_url}")
            return []

        article_urls = self.extract_article_urls(html)

        if max_articles:
            article_urls = article_urls[:max_articles]

        articles: List[Dict[str, str]] = []
        skipped = 0

        for url in article_urls:
            logger.info(f"  Scraping article: {url}")

            # Politeness delay
            time.sleep(self.request_delay)

            article = self.scrape_article(url)
            if article:
                # Apply defaults if auto-detection didn't override
                if not article.get("main_category"):
                    article["main_category"] = default_main_category
                if not article.get("subcategory"):
                    article["subcategory"] = default_subcategory
                articles.append(article)
                logger.info(
                    f"    -> OK ({len(article.get('content', ''))} chars)"
                )
            else:
                skipped += 1
                logger.info(f"    -> Skipped (failed or non-Arabic)")

        logger.info(
            f"Section complete: {len(articles)} articles, {skipped} skipped"
        )
        return articles

    def scrape_all_sections(
        self,
        max_articles_per_section: Optional[int] = None,
        categories: Optional[List[str]] = None,
    ) -> List[Dict[str, str]]:
        """
        Scrape every subcategory across all main categories.

        Args:
            max_articles_per_section: Optional cap per subcategory page
            categories: If provided, only scrape these main categories
                        (Arabic keys, e.g. ["أخبار", "اقتصاد"])

        Returns:
            Aggregated list of all scraped articles
        """
        all_articles: List[Dict[str, str]] = []
        seen_urls: set = set()

        sections_to_scrape = ALJAZEERA_SECTIONS
        if categories:
            sections_to_scrape = {
                k: v
                for k, v in ALJAZEERA_SECTIONS.items()
                if k in categories
            }

        for main_cat_ar, info in sections_to_scrape.items():
            main_cat_en = info["label"]
            logger.info(
                f"\n{'='*60}\n"
                f"Main category: {main_cat_ar} ({main_cat_en})\n"
                f"{'='*60}"
            )

            for (
                sub_label,
                sub_path,
            ) in info["subcategories"]:
                logger.info(
                    f"\n--- Subcategory: {sub_label} -> {sub_path} ---"
                )
                articles = self.scrape_section(
                    section_path=sub_path,
                    default_main_category=main_cat_ar,
                    default_subcategory=sub_label,
                    max_articles=max_articles_per_section,
                )

                # De-duplicate across sections
                for art in articles:
                    if art["url"] not in seen_urls:
                        seen_urls.add(art["url"])
                        all_articles.append(art)

        logger.info(
            f"\n{'='*60}\n"
            f"TOTAL: {len(all_articles)} unique articles scraped\n"
            f"{'='*60}"
        )
        return all_articles


class ArabicNewsScraper:
    """
    General Arabic news scraper supporting multiple sources.
    Currently supports Al Jazeera Arabic.
    """

    SOURCES = {
        "aljazeera": {
            "url": "https://www.aljazeera.net/",
            "scraper": AlJazeeraScraper,
        },
        # Future sources can be added here
        # "alarabiya": {"url": "https://www.alarabiya.net/", "scraper": ...},
    }

    def __init__(self, source: str = "aljazeera"):
        if source not in self.SOURCES:
            raise ValueError(
                f"Unknown source: {source}. "
                f"Available: {list(self.SOURCES.keys())}"
            )

        self.source = source
        self.scraper = self.SOURCES[source]["scraper"]()

    def scrape(
        self,
        max_articles: int = 10,
        categories: Optional[List[str]] = None,
    ) -> List[Dict[str, str]]:
        """
        Scrape articles from the configured source.

        Args:
            max_articles: Max articles *per subcategory page*
            categories: Optional list of main categories to scrape
                       (Arabic keys: أخبار, اقتصاد, رأي, ميدان, متخصصة, محليات)

        Returns:
            List of article dictionaries
        """
        if isinstance(self.scraper, AlJazeeraScraper):
            return self.scraper.scrape_all_sections(
                max_articles_per_section=max_articles,
                categories=categories,
            )
        return []

    def scrape_url(self, url: str) -> Optional[Dict[str, str]]:
        """Scrape a single article by URL."""
        if isinstance(self.scraper, AlJazeeraScraper):
            return self.scraper.scrape_article(url)
        return None
