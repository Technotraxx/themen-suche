import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

import feedparser
import pandas as pd
import requests
import streamlit as st

# ----------------------------- Configuration ----------------------------- #

FEEDS: Dict[str, str] = {
    'Stern.de News Sitemap': 'https://www.stern.de/736974656d6170-news.xml',
    'Welt.de News Sitemap': 'https://www.welt.de/sitemaps/newssitemap/newssitemap.xml',
    'Spiegel.de News Sitemap': 'https://www.spiegel.de/sitemaps/news-de.xml',
    'Focus.de Politik News Sitemap': 'https://www.focus.de/sitemap_news_politik.xml',
    'Bild.de News Sitemap': 'https://www.bild.de/sitemap-news.xml',
    'Tagesschau.de RSS Feed': 'https://www.tagesschau.de/index~rss2.xml',
    'T-Online.de RSS Feed': 'https://www.t-online.de/schlagzeilen/feed.rss'
}

STATES_OF_GERMANY: List[str] = [
    'baden-wuerttemberg', 'bayern', 'berlin', 'brandenburg', 'bremen', 'hamburg', 'hessen',
    'mecklenburg-vorpommern', 'niedersachsen', 'nordrhein-westfalen', 'rheinland-pfalz',
    'saarland', 'sachsen', 'sachsen-anhalt', 'schleswig-holstein', 'thueringen'
]

BIGGEST_CITIES_GERMANY: List[str] = [
    'berlin', 'hamburg', 'muenchen', 'koeln', 'frankfurt', 'stuttgart', 'dortmund',
    'essen', 'duesseldorf', 'bremen'
]

COMPOUND_REGIONS: List[str] = [
    'baden-wuerttemberg', 'mecklenburg-vorpommern', 'nordrhein-westfalen',
    'rheinland-pfalz', 'sachsen-anhalt', 'schleswig-holstein'
]

# Combine lists of locations with priority to compound regions
# Sort REGIONAL_LOCATIONS by descending length to prioritize longer names first
REGIONAL_LOCATIONS: List[str] = sorted(
    COMPOUND_REGIONS +
    [region for region in STATES_OF_GERMANY if region not in COMPOUND_REGIONS] +
    BIGGEST_CITIES_GERMANY,
    key=lambda x: len(x),
    reverse=True
)

NORMALIZATION_RULES: Dict[str, List[str]] = {
    'wirtschaft': ['economy', 'wirtschaft'],
    'politik': ['politics', 'politik'],
    'ausland': ['international', 'ausland'],
    'sport': ['sports', 'sport'],
    'regional': ['region', 'regionales', 'regional'],
    'nordrhein-westfalen': ['nordrhein-westfalen', 'nrw', 'ruhrgebiet']
}

NON_CATEGORY_PATTERNS: List[str] = [
    r'^article\d+$',
    r'^plus\d+$',
    r'^amp\d+$',
    r'^content\d+$',
    r'^rss\d+$',
    r'^id_\d+$'
]

COMPILED_NON_CATEGORY_PATTERNS: List[Any] = [re.compile(pattern) for pattern in NON_CATEGORY_PATTERNS]

# ----------------------------- Helper Functions ----------------------------- #

@st.cache_data(ttl=3600)
def determine_feed_type(feed_url: str) -> str:
    try:
        feed = feedparser.parse(feed_url)
        if feed.bozo:
            return 'sitemap'
        elif hasattr(feed, 'entries') and len(feed.entries) > 0 and hasattr(feed.entries[0], 'link'):
            return 'rss'
        else:
            return 'sitemap'
    except Exception:
        return 'sitemap'


@st.cache_data(ttl=3600)
def extract_urls_from_rss(feed_url: str) -> List[Dict[str, Any]]:
    articles = []
    try:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            keywords = [tag.term for tag in entry.tags if 'term' in tag] if 'tags' in entry else []
            publication_date_str = entry.get('published', entry.get('updated', ''))
            pub_date = parse_datetime(publication_date_str)
            news_title = entry.get('title', '')
            articles.append({
                'link': entry.get('link', ''),
                'title': news_title,
                'description': entry.get('description', ''),
                'keywords': keywords,
                'publication_date': pub_date
            })
    except Exception as e:
        print(f"Error parsing RSS feed {feed_url}: {e}")
    return articles


@st.cache_data(ttl=3600)
def extract_urls_from_sitemap(feed_url: str) -> List[Dict[str, Any]]:
    entries = []
    try:
        response = requests.get(feed_url)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        namespace = {
            's': 'http://www.sitemaps.org/schemas/sitemap/0.9',
            'news': 'http://www.google.com/schemas/sitemap-news/0.9'
        }
        for url in root.findall('s:url', namespaces=namespace):
            loc = url.find('s:loc', namespaces=namespace)
            loc_text = loc.text if loc is not None else ''
            keywords_elem = url.find('news:news/news:keywords', namespaces=namespace)
            keywords = [kw.strip().lower() for kw in keywords_elem.text.split(',')] if keywords_elem is not None and keywords_elem.text else []
            publication_date_str = url.find('news:news/news:publication_date', namespaces=namespace)
            publication_date = parse_iso_datetime(publication_date_str.text) if publication_date_str is not None and publication_date_str.text else None
            news_title_elem = url.find('news:news/news:title', namespaces=namespace)
            news_title = news_title_elem.text if news_title_elem is not None and news_title_elem.text else ''
            entries.append({
                'loc': loc_text,
                'keywords': keywords,
                'publication_date': publication_date,
                'news_title': news_title
            })
    except Exception as e:
        print(f"Error parsing Sitemap {feed_url}: {e}")
    return entries


def parse_datetime(date_str: str) -> Any:
    try:
        return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %Z").astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


def parse_iso_datetime(date_str: str) -> Any:
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


def extract_categories(url: str) -> List[str]:
    try:
        parsed_url = urlparse(url)
        path = parsed_url.path
        parts = [part for part in path.split('/') if part]
        potential_categories = parts[:-1]  # Exclude the last part which is typically the article
        categories = [cat for cat in potential_categories if not any(pattern.match(cat) for pattern in COMPILED_NON_CATEGORY_PATTERNS)]
        return categories
    except Exception as e:
        print(f"Error parsing URL {url}: {e}")
        return []

def normalize_categories(categories: List[str], url: str) -> List[str]:
    normalized: set = set()
    specific_regions: set = set()

    # Step 1: Normalize general categories and preserve "regional"
    for cat in categories:
        cat_lower = cat.lower()
        matched = False
        for key, synonyms in NORMALIZATION_RULES.items():
            if cat_lower in [syn.lower() for syn in synonyms]:
                normalized.add(key)
                matched = True
                break
        if not matched:
            normalized.add(cat_lower)

    # Step 2: Extract specific regional locations from URL and categories
    url_path = urlparse(url).path.lower()

    for region in REGIONAL_LOCATIONS:
        # Use word boundaries and ensure 'region' is a complete segment
        if re.search(rf'\b{re.escape(region)}\b', url_path) or any(re.search(rf'\b{re.escape(region)}\b', cat.lower()) for cat in categories):
            specific_regions.add(region)

    # Step 3: Add specific regional locations to normalized categories without removing "regional"
    normalized.update(specific_regions)

    return list(normalized)


@st.cache_data(ttl=3600)
def get_all_articles() -> Tuple[pd.DataFrame, List[str]]:
    all_articles: List[Dict[str, Any]] = []
    log_messages: List[str] = []

    for feed_name, feed_url in FEEDS.items():
        feed_type = determine_feed_type(feed_url)
        log_message = f"Processing '{feed_name}' as {feed_type.upper()}..."
        log_messages.append(log_message)

        if feed_type == 'rss':
            articles = extract_urls_from_rss(feed_url)
            for article in articles:
                categories = extract_categories(article['link'])
                normalized_categories = normalize_categories(categories, article['link'])
                combined_keywords = ', '.join(article['keywords']) + ', ' + article['description']
                all_articles.append({
                    'Feed': feed_name,
                    'URL': article['link'],
                    'Title': article['title'],
                    'Keywords': combined_keywords,
                    'Publication_Date': article['publication_date'],
                    'Categories': categories,
                    'Normalized_Categories': normalized_categories
                })
        else:
            sitemap_entries = extract_urls_from_sitemap(feed_url)
            for entry in sitemap_entries:
                categories = extract_categories(entry['loc'])
                normalized_categories = normalize_categories(categories, entry['loc'])
                combined_keywords = ', '.join(entry['keywords'])
                all_articles.append({
                    'Feed': feed_name,
                    'URL': entry['loc'],
                    'Title': entry['news_title'],
                    'Keywords': combined_keywords,
                    'Publication_Date': entry['publication_date'],
                    'Categories': categories,
                    'Normalized_Categories': normalized_categories
                })

    df = pd.DataFrame(all_articles)
    df = df[['Title', 'Feed', 'Keywords', 'Categories', 'Normalized_Categories', 'URL', 'Publication_Date']]
    return df, log_messages
