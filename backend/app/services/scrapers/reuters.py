"""
Reuters Middle East Scraper.
Specialized scraper for Reuters Middle East news section.
"""
import re
import logging
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


class ReutersScraper:
    """
    Scraper for Reuters Arabic Middle East news.
    Handles Reuters.com Arabic structure with proper encoding.
    """

    BASE_URL = "https://www.reuters.com"
    MIDDLE_EAST_URL = "https://www.reuters.com/ar/middle-east/"

    # Arabic/Reuters specific headers
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ar-SA,ar;q=0.9',
        'Accept-Encoding': 'utf-8',
    }
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
    
    def fetch_page(self, url: str) -> Optional[str]:
        """
        Fetch HTML content from URL.
        
        Args:
            url: URL to fetch
            
        Returns:
            HTML content or None if failed
        """
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            response.encoding = 'utf-8'
            return response.text
        except requests.RequestException as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None
    
    def extract_article_urls(self, html: str) -> List[str]:
        """
        Extract article URLs from a listing page.
        
        Args:
            html: HTML content
            
        Returns:
            List of article URLs
        """
        soup = BeautifulSoup(html, 'html.parser')
        urls = []
        
        # Reuters uses various article link patterns
        # Look for article links in the listing
        for link in soup.find_all('a', href=True):
            href = link['href']
            
            # Check if it's an article URL
            if self._is_article_url(href):
                full_url = urljoin(self.BASE_URL, href)
                if full_url not in urls:
                    urls.append(full_url)
        
        logger.info(f"Found {len(urls)} article URLs")
        return urls
    
    def _is_article_url(self, url: str) -> bool:
        """Check if URL points to an Arabic article."""
        # Arabic article URLs have /ar/ prefix and specific structure
        patterns = [
            r'/ar/middle-east/[^/]+/\d{4}-\d{2}-\d{2}/',
            r'/ar/middle-east/[^/]+/$',
            r'/ar/.*article/',
        ]

        for pattern in patterns:
            if re.search(pattern, url):
                return True
        return False
    
    def scrape_article(self, url: str) -> Optional[Dict[str, str]]:
        """
        Scrape a single Arabic article.

        Args:
            url: Article URL

        Returns:
            Dictionary with title, content, author, date or None if failed/not Arabic
        """
        html = self.fetch_page(url)
        if not html:
            return None

        soup = BeautifulSoup(html, 'html.parser')

        # Extract title
        title = self._extract_title(soup)
        if not title:
            logger.warning(f"No title found for {url}")
            return None

        # Check if title contains Arabic text
        if not self._is_arabic_text(title):
            logger.info(f"Skipping non-Arabic article: {url}")
            return None

        # Extract content
        content = self._extract_content(soup)
        if not content:
            logger.warning(f"No content found for {url}")
            return None

        # Extract author
        author = self._extract_author(soup)

        # Extract date
        date = self._extract_date(soup)

        # Extract description/summary
        description = self._extract_description(soup)

        return {
            "url": url,
            "title": title,
            "content": content,
            "author": author or "Unknown",
            "date": date or "",
            "description": description or title,
            "source": "Reuters Arabic",
            "language": "ar"
        }

    def _is_arabic_text(self, text: str) -> bool:
        """
        Check if text contains Arabic characters.

        Args:
            text: Text to check

        Returns:
            True if text contains Arabic, False otherwise
        """
        # Arabic Unicode range: \u0600-\u06FF
        arabic_pattern = re.compile(r'[\u0600-\u06FF]')
        arabic_chars = len(arabic_pattern.findall(text))

        # Consider it Arabic if at least 30% of characters are Arabic
        if len(text) > 0:
            arabic_ratio = arabic_chars / len(text)
            return arabic_ratio >= 0.3

        return False
    
    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract article title."""
        # Reuters uses h1 for article title
        title_tag = soup.find('h1')
        if title_tag:
            return title_tag.get_text(strip=True)
        
        # Fallback to meta title
        meta_title = soup.find('meta', {'name': 'title'})
        if meta_title and meta_title.get('content'):
            return meta_title['content']
        
        return None
    
    def _extract_content(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract article content."""
        content_parts = []
        
        # Reuters article body typically in div with specific classes
        # Try multiple selectors
        content_selectors = [
            'div[data-testid="Body"]',
            'div.article-body',
            'div.body',
            'article',
        ]
        
        content_div = None
        for selector in content_selectors:
            if '[' in selector:
                # Attribute selector
                attr_name = selector.split('[')[1].split(']')[0].split('=')[1].strip('"\'')
                content_div = soup.find('div', {'data-testid': attr_name})
            else:
                content_div = soup.find(selector)
            
            if content_div:
                break
        
        if content_div:
            # Extract paragraphs
            paragraphs = content_div.find_all('p')
            for p in paragraphs:
                text = p.get_text(strip=True)
                if text and len(text) > 20:  # Filter out short/empty paragraphs
                    content_parts.append(text)
        
        # Fallback: get all paragraphs from main content area
        if not content_parts:
            main = soup.find('main') or soup.find('article')
            if main:
                paragraphs = main.find_all('p')
                for p in paragraphs:
                    text = p.get_text(strip=True)
                    if text and len(text) > 20:
                        content_parts.append(text)
        
        if content_parts:
            return '\n\n'.join(content_parts)
        
        return None
    
    def _extract_author(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract article author."""
        # Look for author meta tag
        meta_author = soup.find('meta', {'name': 'author'})
        if meta_author and meta_author.get('content'):
            return meta_author['content']
        
        # Look for byline
        byline = soup.find('div', class_=re.compile(r'byline|author', re.I))
        if byline:
            return byline.get_text(strip=True)
        
        return None
    
    def _extract_date(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract article publication date."""
        # Look for date meta tag
        meta_date = soup.find('meta', {'name': 'date'})
        if meta_date and meta_date.get('content'):
            return meta_date['content']
        
        # Look for article:published_time
        meta_pub = soup.find('meta', {'property': 'article:published_time'})
        if meta_pub and meta_pub.get('content'):
            return meta_pub['content']
        
        # Look for time tag
        time_tag = soup.find('time')
        if time_tag:
            return time_tag.get('datetime') or time_tag.get_text(strip=True)
        
        return None
    
    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract article description/summary."""
        # Look for meta description
        meta_desc = soup.find('meta', {'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            return meta_desc['content']
        
        # Look for og:description
        og_desc = soup.find('meta', {'property': 'og:description'})
        if og_desc and og_desc.get('content'):
            return og_desc['content']
        
        return None
    
    def scrape_middle_east_section(self, max_articles: int = 10) -> List[Dict[str, str]]:
        """
        Scrape latest Arabic articles from Reuters Middle East section.

        Args:
            max_articles: Maximum number of articles to scrape

        Returns:
            List of article dictionaries (Arabic only)
        """
        articles = []

        # Fetch the Arabic Middle East section page
        logger.info(f"Fetching Arabic Middle East section: {self.MIDDLE_EAST_URL}")
        html = self.fetch_page(self.MIDDLE_EAST_URL)
        if not html:
            logger.error("Failed to fetch Arabic Middle East section")
            return articles

        # Extract article URLs
        urls = self.extract_article_urls(html)
        logger.info(f"Found {len(urls)} potential article URLs")

        # Scrape each article
        skipped = 0
        for url in urls[:max_articles]:
            logger.info(f"Scraping: {url}")
            article = self.scrape_article(url)
            if article:
                articles.append(article)
                logger.info(f"  -> Successfully scraped Arabic article")
            else:
                skipped += 1
                logger.info(f"  -> Skipped (non-Arabic or failed)")

        logger.info(f"Successfully scraped {len(articles)} Arabic articles (skipped {skipped})")
        return articles


class ArabicNewsScraper:
    """
    General Arabic news scraper supporting multiple sources.
    """

    SOURCES = {
        "reuters_arabic": {
            "url": "https://www.reuters.com/ar/middle-east/",
            "scraper": ReutersScraper
        },
        # Future sources can be added here
        # "alarabiya": {"url": "https://www.alarabiya.net/", "scraper": ...},
        # "aljazeera": {"url": "https://www.aljazeera.net/", "scraper": ...},
    }
    
    def __init__(self, source: str = "reuters_arabic"):
        if source not in self.SOURCES:
            raise ValueError(f"Unknown source: {source}")
        
        self.source = source
        self.scraper = self.SOURCES[source]["scraper"]()
    
    def scrape(self, max_articles: int = 10) -> List[Dict[str, str]]:
        """Scrape articles from the configured source."""
        if isinstance(self.scraper, ReutersScraper):
            return self.scraper.scrape_middle_east_section(max_articles)
        return []
    
    def scrape_url(self, url: str) -> Optional[Dict[str, str]]:
        """Scrape a specific URL."""
        if isinstance(self.scraper, ReutersScraper):
            return self.scraper.scrape_article(url)
        return None
