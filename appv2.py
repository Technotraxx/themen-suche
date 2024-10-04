import streamlit as st
import feedparser
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
import pandas as pd
import re
from collections import defaultdict
import base64
import streamlit as st
import cachetools.func

# Define the feeds
feeds = {
    'Stern.de News Sitemap': 'https://www.stern.de/736974656d6170-news.xml',
    'Welt.de News Sitemap': 'https://www.welt.de/sitemaps/newssitemap/newssitemap.xml',
    'Spiegel.de News Sitemap': 'https://www.spiegel.de/sitemaps/news-de.xml',
    'Focus.de Politik News Sitemap': 'https://www.focus.de/sitemap_news_politik.xml',
    'Bild.de News Sitemap': 'https://www.bild.de/sitemap-news.xml',
    'Tagesschau.de RSS Feed': 'https://www.tagesschau.de/index~rss2.xml',
    'T-Online.de RSS Feed': 'https://www.t-online.de/schlagzeilen/feed.rss'
}

@cachetools.func.ttl_cache(maxsize=100, ttl=3600)
def extract_urls_from_rss(feed_url):
    try:
        feed = feedparser.parse(feed_url)
        articles = []
        for entry in feed.entries:
            keywords = [tag.term for tag in entry.tags if 'term' in tag] if 'tags' in entry else []
            publication_date = entry.published if 'published' in entry else entry.updated if 'updated' in entry else ''
            news_title = entry.title if 'title' in entry else ''
            articles.append({
                'link': entry.link,
                'title': news_title,
                'description': entry.description if 'description' in entry else '',
                'keywords': keywords,
                'publication_date': publication_date
            })
        return articles
    except Exception as e:
        st.error(f"Error parsing RSS feed {feed_url}: {e}")
        return []

@cachetools.func.ttl_cache(maxsize=100, ttl=3600)
def extract_urls_from_sitemap(feed_url):
    try:
        response = requests.get(feed_url)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        namespace = {
            's': 'http://www.sitemaps.org/schemas/sitemap/0.9',
            'news': 'http://www.google.com/schemas/sitemap-news/0.9'
        }
        urls = []
        for url in root.findall('s:url', namespaces=namespace):
            loc = url.find('s:loc', namespaces=namespace)
            loc_text = loc.text if loc is not None else ''
            keywords_elem = url.find('news:news/news:keywords', namespaces=namespace)
            keywords = [kw.strip().lower() for kw in keywords_elem.text.split(',')] if keywords_elem is not None and keywords_elem.text else []
            pub_date_elem = url.find('news:news/news:publication_date', namespaces=namespace)
            publication_date = pub_date_elem.text if pub_date_elem is not None and pub_date_elem.text else ''
            news_title_elem = url.find('news:news/news:title', namespaces=namespace)
            news_title = news_title_elem.text if news_title_elem is not None and news_title_elem.text else ''
            urls.append({
                'loc': loc_text,
                'keywords': keywords,
                'publication_date': publication_date,
                'news_title': news_title
            })
        return urls
    except Exception as e:
        st.error(f"Error parsing Sitemap {feed_url}: {e}")
        return []

@cachetools.func.ttl_cache(maxsize=100, ttl=3600)
def determine_feed_type(feed_url):
    try:
        feed = feedparser.parse(feed_url)
        if feed.bozo:
            return 'sitemap'
        else:
            if hasattr(feed, 'entries') and len(feed.entries) > 0 and hasattr(feed.entries[0], 'link'):
                return 'rss'
            else:
                return 'sitemap'
    except:
        return 'sitemap'

def extract_categories(url):
    try:
        parsed_url = urlparse(url)
        path = parsed_url.path
        parts = [part for part in path.split('/') if part]
        potential_categories = parts[:-1]
        non_category_patterns = [
            r'^article\d+$',
            r'^plus\d+$',
            r'^amp\d+$',
            r'^content\d+$',
            r'^rss\d+$',
            r'^id_\d+$'
        ]
        compiled_patterns = [re.compile(pattern) for pattern in non_category_patterns]
        categories = [cat for cat in potential_categories if not any(pattern.match(cat) for pattern in compiled_patterns)]
        return categories
    except Exception as e:
        st.error(f"Error parsing URL {url}: {e}")
        return []

def normalize_categories(categories):
    normalization_rules = {
        'regional': ['region', 'regionales', 'regional'],
        'wirtschaft': ['economy', 'wirtschaft'],
        'politik': ['politics', 'politik'],
        'ausland': ['international', 'ausland'],
        'sport': ['sports', 'sport']
    }
    normalized = []
    for cat in categories:
        found = False
        for key, synonyms in normalization_rules.items():
            if cat.lower() in [syn.lower() for syn in synonyms]:
                normalized.append(key)
                found = True
                break
        if not found:
            normalized.append(cat.lower())
    return normalized

@st.cache_data(ttl=3600)
def get_all_articles():
    all_articles = []
    log_messages = []
    for feed_name, feed_url in feeds.items():
        feed_type = determine_feed_type(feed_url)
        log_message = f"Processing '{feed_name}' as {feed_type.upper()}..."
        log_messages.append(log_message)
        
        if feed_type == 'rss':
            articles = extract_urls_from_rss(feed_url)
            for article in articles:
                all_articles.append({
                    'Feed': feed_name,
                    'URL': article['link'],
                    'Title': article['title'],
                    'Description': article['description'],
                    'Keywords': ', '.join(article['keywords']),
                    'Publication_Date': article['publication_date'],
                    'Categories': normalize_categories(extract_categories(article['link']))
                })
        else:
            sitemap_entries = extract_urls_from_sitemap(feed_url)
            for entry in sitemap_entries:
                all_articles.append({
                    'Feed': feed_name,
                    'URL': entry['loc'],
                    'Title': entry['news_title'],
                    'Description': '',
                    'Keywords': ', '.join(entry['keywords']),
                    'Publication_Date': entry['publication_date'],
                    'Categories': normalize_categories(extract_categories(entry['loc']))
                })
    return pd.DataFrame(all_articles), log_messages

def main():
    st.title('News Feed Aggregator')

    # Get all articles and create a DataFrame
    df, log_messages = get_all_articles()

    # Display log messages in the sidebar
    st.sidebar.title("Processing Log")
    for message in log_messages:
        st.sidebar.write(message)

    # Extract unique categories and sort them by the number of items
    category_counts = defaultdict(int)
    for cats in df['Categories']:
        for cat in cats:
            category_counts[cat] += 1
    sorted_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
    unique_categories = [cat for cat, _ in sorted_categories]

    # Filters
    category_filter = st.selectbox('Select Category:', options=['All'] + unique_categories, index=0)
    keyword_filter = st.text_input('Enter Keyword:')

    # Filter DataFrame based on user input
    filtered_df = df.copy()
    if category_filter != 'All':
        filtered_df = filtered_df[filtered_df['Categories'].apply(lambda x: category_filter in x)]
    if keyword_filter:
        filtered_df = filtered_df[filtered_df['Keywords'].str.contains(keyword_filter, case=False, na=False)]

    # Display results
    st.write(f"Number of articles found: {len(filtered_df)}")
    st.dataframe(filtered_df)

    # Download filtered CSV
    if not filtered_df.empty:
        csv = filtered_df.to_csv(index=False)
        b64 = base64.b64encode(csv.encode()).decode()
        href = f'<a href="data:text/csv;base64,{b64}" download="filtered_articles.csv">Download CSV</a>'
        st.markdown(href, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
