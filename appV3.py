import base64
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import feedparser
import pandas as pd
import requests
import streamlit as st
from urllib.parse import urlparse

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
    'regional': ['region', 'regionales', 'regional']
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
    """
    Determine whether the given feed URL is an RSS feed or a Sitemap.

    Args:
        feed_url (str): The URL of the feed.

    Returns:
        str: 'rss' if it's an RSS feed, 'sitemap' otherwise.
    """
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
    """
    Extract articles from an RSS feed.

    Args:
        feed_url (str): The RSS feed URL.

    Returns:
        List[Dict[str, Any]]: A list of articles with relevant information.
    """
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
        st.error(f"Error parsing RSS feed {feed_url}: {e}")
    return articles


@st.cache_data(ttl=3600)
def extract_urls_from_sitemap(feed_url: str) -> List[Dict[str, Any]]:
    """
    Extract URLs from a Sitemap.

    Args:
        feed_url (str): The Sitemap URL.

    Returns:
        List[Dict[str, Any]]: A list of sitemap entries with relevant information.
    """
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
        st.error(f"Error parsing Sitemap {feed_url}: {e}")
    return entries


def parse_datetime(date_str: str) -> Any:
    """
    Parse a datetime string into a datetime object.

    Args:
        date_str (str): The datetime string.

    Returns:
        datetime or None: The parsed datetime object or None if parsing fails.
    """
    try:
        return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %Z").astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


def parse_iso_datetime(date_str: str) -> Any:
    """
    Parse an ISO formatted datetime string into a datetime object.

    Args:
        date_str (str): The ISO datetime string.

    Returns:
        datetime or None: The parsed datetime object or None if parsing fails.
    """
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


def extract_categories(url: str) -> List[str]:
    """
    Extract potential category segments from a URL path.

    Args:
        url (str): The URL to extract categories from.

    Returns:
        List[str]: A list of category segments.
    """
    try:
        parsed_url = urlparse(url)
        path = parsed_url.path
        parts = [part for part in path.split('/') if part]
        potential_categories = parts[:-1]  # Exclude the last part which is typically the article
        categories = [cat for cat in potential_categories if not any(pattern.match(cat) for pattern in COMPILED_NON_CATEGORY_PATTERNS)]
        return categories
    except Exception as e:
        st.error(f"Error parsing URL {url}: {e}")
        return []


def normalize_categories(categories: List[str], url: str) -> List[str]:
    """
    Normalize category names and extract specific regional locations.

    Args:
        categories (List[str]): The list of extracted categories.
        url (str): The URL associated with the categories.

    Returns:
        List[str]: A list of normalized categories.
    """
    normalized: set = set()
    specific_regions: set = set()

    # Step 1: Normalize general categories
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
        # This prevents partial matches like 'sachsen' in 'sachsen-anhalt'
        pattern = rf'(?<![\w-]){re.escape(region)}(?![\w-])'
        if re.search(pattern, url_path) or any(re.search(pattern, cat.lower()) for cat in categories):
            specific_regions.add(region)

    # Step 3: Add specific regional locations to normalized categories
    if specific_regions:
        normalized.update(specific_regions)
        # Remove "regional" if specific regions are identified to avoid redundancy
        normalized.discard("regional")

    return list(normalized)


@st.cache_data(ttl=3600)
def get_all_articles() -> Tuple[pd.DataFrame, List[str]]:
    """
    Aggregate articles from all configured feeds.

    Returns:
        Tuple[pd.DataFrame, List[str]]: A DataFrame containing all articles and a list of log messages.
    """
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
                all_articles.append({
                    'Feed': feed_name,
                    'URL': article['link'],
                    'Title': article['title'],
                    'Description': article['description'],
                    'Keywords': ', '.join(article['keywords']),
                    'Publication_Date': article['publication_date'],
                    'Categories': categories,  # Stored as list
                    'Normalized_Categories': normalized_categories  # Stored as list
                })
        else:
            sitemap_entries = extract_urls_from_sitemap(feed_url)
            for entry in sitemap_entries:
                categories = extract_categories(entry['loc'])
                normalized_categories = normalize_categories(categories, entry['loc'])
                all_articles.append({
                    'Feed': feed_name,
                    'URL': entry['loc'],
                    'Title': entry['news_title'],
                    'Description': '',
                    'Keywords': ', '.join(entry['keywords']),
                    'Publication_Date': entry['publication_date'],
                    'Categories': categories,  # Stored as list
                    'Normalized_Categories': normalized_categories  # Stored as list
                })

    df = pd.DataFrame(all_articles)
    return df, log_messages

# ----------------------------- Main Application ----------------------------- #

def main():
    st.set_page_config(page_title='📰 News Feed Aggregator', layout='wide')
    st.title('📰 News Feed Aggregator')

    # Retrieve all articles and log messages
    df, log_messages = get_all_articles()

    # Sidebar: Processing Log
    with st.sidebar.expander("📝 Processing Log", expanded=False):
        st.markdown('<div style="font-size: small;">', unsafe_allow_html=True)
        for message in log_messages:
            st.write(message)
        st.markdown('</div>', unsafe_allow_html=True)

    # Sidebar: Filters
    st.sidebar.title("🔍 Filters")

    # 1. Category Filter Logic
    filter_logic = st.sidebar.radio(
        'Category Filter Logic:',
        options=['AND', 'OR'],
        index=0,  # Default to 'AND'
        key='filter_logic_radio'
    )

    st.sidebar.markdown("")  # Space

    # 2. Search by Title or Keywords
    combined_search = st.sidebar.text_input(
        'Search by Title or Keywords:',
        value='',
        key='combined_search_input'
    )

    st.sidebar.markdown("")  # Space

    # Apply combined search filter first
    filtered_df = df.copy()

    if combined_search:
        search_query = combined_search.lower()
        filtered_df = filtered_df[
            filtered_df['Keywords'].str.lower().str.contains(search_query, na=False) |
            filtered_df['Description'].str.lower().str.contains(search_query, na=False) |
            filtered_df['Title'].str.lower().str.contains(search_query, na=False)
        ]

    # Determine available categories and locations based on current filters
    available_categories = (
        filtered_df['Normalized_Categories']
        .explode()
        .value_counts()
        .loc[lambda x: ~x.index.isin(REGIONAL_LOCATIONS)]
    )

    available_locations = (
        filtered_df['Normalized_Categories']
        .explode()
        .value_counts()
        .loc[lambda x: x.index.isin(REGIONAL_LOCATIONS)]
    )

    # Prepare filter options with counts
    category_options = [f"{cat} ({count})" for cat, count in available_categories.items()]
    location_options = [f"{loc} ({count})" for loc, count in available_locations.items()]

    # Retrieve previous selections to prevent them from vanishing
    selected_categories = st.sidebar.multiselect(
        'Select Categories:',
        options=category_options,
        default=st.session_state.get('selected_categories', []),
        key='category_multiselect'
    )

    selected_locations = st.sidebar.multiselect(
        'Select Regional Locations:',
        options=location_options,
        default=st.session_state.get('selected_locations', []),
        key='location_multiselect'
    )

    # Update session state with current selections
    st.session_state['selected_categories'] = selected_categories
    st.session_state['selected_locations'] = selected_locations

    # Extract actual category and location names from selected items
    selected_categories_clean = [cat.split(' (')[0] for cat in selected_categories]
    selected_locations_clean = [loc.split(' (')[0] for loc in selected_locations]

    # Ensure selected items are always in the options
    # Add selected items back to the options if they were filtered out
    for cat in selected_categories_clean:
        if cat not in available_categories.index:
            category_options.append(f"{cat} (0)")
    for loc in selected_locations_clean:
        if loc not in available_locations.index:
            location_options.append(f"{loc} (0)")

    # Recreate the multiselects with updated options including selected items
    # This prevents selected items from vanishing
    selected_categories = st.sidebar.multiselect(
        'Select Categories:',
        options=category_options,
        default=selected_categories,
        key='category_multiselect_updated'
    )

    selected_locations = st.sidebar.multiselect(
        'Select Regional Locations:',
        options=location_options,
        default=selected_locations,
        key='location_multiselect_updated'
    )

    # Extract actual category and location names from updated selections
    selected_categories_clean = [cat.split(' (')[0] for cat in selected_categories]
    selected_locations_clean = [loc.split(' (')[0] for loc in selected_locations]

    # Apply category and location filters
    filtered_df_final = filtered_df.copy()

    if selected_categories_clean or selected_locations_clean:
        if filter_logic == 'OR':
            condition = pd.Series([False] * len(filtered_df_final))
            if selected_categories_clean:
                condition = condition | filtered_df_final['Normalized_Categories'].apply(
                    lambda cats: any(cat in cats for cat in selected_categories_clean)
                )
            if selected_locations_clean:
                condition = condition | filtered_df_final['Normalized_Categories'].apply(
                    lambda locs: any(loc in locs for loc in selected_locations_clean)
                )
            filtered_df_final = filtered_df_final[condition]
        elif filter_logic == 'AND':
            if selected_categories_clean:
                for cat in selected_categories_clean:
                    filtered_df_final = filtered_df_final[
                        filtered_df_final['Normalized_Categories'].apply(lambda cats: cat in cats)
                    ]
            if selected_locations_clean:
                for loc in selected_locations_clean:
                    filtered_df_final = filtered_df_final[
                        filtered_df_final['Normalized_Categories'].apply(lambda locs: loc in locs)
                    ]

    # Sort the DataFrame by the newest publication date
    filtered_df_final = filtered_df_final.sort_values(by='Publication_Date', ascending=False)

    # Display the number of articles found
    st.subheader(f"🔍 Number of articles found: {len(filtered_df_final)}")

    # Display the DataFrame
    st.dataframe(filtered_df_final)

    # Download filtered articles as CSV
    if not filtered_df_final.empty:
        csv = filtered_df_final.to_csv(index=False)
        b64 = base64.b64encode(csv.encode()).decode()
        href = f'<a href="data:file/csv;base64,{b64}" download="filtered_articles.csv">📥 Download CSV</a>'
        st.markdown(href, unsafe_allow_html=True)

    # Visual Insights
    st.subheader("📊 Visual Insights")

    # Bar chart for Top 25 General Categories
    top_25_categories = (
        filtered_df_final['Normalized_Categories']
        .explode()
        .value_counts()
        .loc[lambda x: ~x.index.isin(REGIONAL_LOCATIONS)]
        .head(25)
    )
    if not top_25_categories.empty:
        st.markdown("**Top 25 Categories by Number of Articles**")
        category_df = top_25_categories.rename_axis('Category').reset_index(name='Count')
        category_chart = pd.DataFrame(category_df.set_index('Category')['Count'])
        st.bar_chart(category_chart)
    else:
        st.write("No category data available for visualization.")

    # Bar chart for Articles Published Each Hour
    if not filtered_df_final.empty and filtered_df_final['Publication_Date'].notna().any():
        filtered_df_final['Hour'] = filtered_df_final['Publication_Date'].dt.hour
        articles_per_hour = filtered_df_final['Hour'].value_counts().sort_index()
        st.markdown("**Number of Articles Published Each Hour**")
        st.bar_chart(articles_per_hour)
    else:
        st.write("No publication date data available for visualization.")

    # Distribution of Feeds
    feed_counts = filtered_df_final['Feed'].value_counts()
    if not feed_counts.empty:
        st.markdown("**Distribution of Feeds**")
        st.write(feed_counts)
    else:
        st.write("No feed distribution data available.")

if __name__ == "__main__":
    main()
