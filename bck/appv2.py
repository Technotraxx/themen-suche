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
from datetime import datetime, timezone

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
            try:
                pub_date = datetime.strptime(publication_date, "%a, %d %b %Y %H:%M:%S %Z").astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                pub_date = None
            news_title = entry.title if 'title' in entry else ''
            articles.append({
                'link': entry.link,
                'title': news_title,
                'description': entry.description if 'description' in entry else '',
                'keywords': keywords,
                'publication_date': pub_date
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
            try:
                pub_date = datetime.fromisoformat(publication_date.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                pub_date = None
            news_title_elem = url.find('news:news/news:title', namespaces=namespace)
            news_title = news_title_elem.text if news_title_elem is not None and news_title_elem.text else ''
            urls.append({
                'loc': loc_text,
                'keywords': keywords,
                'publication_date': pub_date,
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

import re
from urllib.parse import urlparse

# Define German states and the 10 biggest cities globally
states_of_germany = [
    'baden-wuerttemberg', 'bayern', 'berlin', 'brandenburg', 'bremen', 'hamburg', 'hessen',
    'mecklenburg-vorpommern', 'niedersachsen', 'nordrhein-westfalen', 'rheinland-pfalz',
    'saarland', 'sachsen', 'sachsen-anhalt', 'schleswig-holstein', 'thueringen'
]

biggest_cities_germany = [
    'berlin', 'hamburg', 'muenchen', 'koeln', 'frankfurt', 'stuttgart', 'dortmund',
    'essen', 'duesseldorf', 'bremen'
]

# Prioritize compound regions for exact matching
compound_regions = [
    'baden-wuerttemberg', 'mecklenburg-vorpommern', 'nordrhein-westfalen', 
    'rheinland-pfalz', 'sachsen-anhalt', 'schleswig-holstein'
]

# Combine lists of locations
regional_locations = compound_regions + [region for region in states_of_germany if region not in compound_regions] + biggest_cities_germany

def normalize_categories(categories, url):
    normalization_rules = {
        'wirtschaft': ['economy', 'wirtschaft'],
        'politik': ['politics', 'politik'],
        'ausland': ['international', 'ausland'],
        'sport': ['sports', 'sport'],
        'regional': ['region', 'regionales', 'regional']
    }

    # Initialize sets for normalized categories
    normalized = set()
    specific_regions = set()
    
    # Step 1: Normalize general categories
    for cat in categories:
        cat_lower = cat.lower()
        for key, synonyms in normalization_rules.items():
            if cat_lower in [syn.lower() for syn in synonyms]:
                normalized.add(key)
                break
        else:
            normalized.add(cat_lower)

    # Step 2: Extract specific regional locations from URL and keywords (use exact match, prioritize compound regions)
    url_path = urlparse(url).path.lower()

    # Match compound regions first to prevent partial matches
    for region in compound_regions:
        if re.search(rf'\b{re.escape(region)}\b', url_path) or any(re.search(rf'\b{re.escape(region)}\b', cat.lower()) for cat in categories):
            specific_regions.add(region)

    # Match other regional locations only if they haven't been matched as part of a compound region
    for region in states_of_germany + biggest_cities_germany:
        if region not in specific_regions:  # Only add if not already matched
            if re.search(rf'\b{re.escape(region)}\b', url_path) or any(re.search(rf'\b{re.escape(region)}\b', cat.lower()) for cat in categories):
                specific_regions.add(region)

    # Step 3: Add specific regional locations to normalized categories if found
    if specific_regions:
        normalized.update(specific_regions)
        # Remove "regional" if specific regions are identified to avoid redundancy
        normalized.discard("regional")

    return list(normalized)

def main():
    st.title('News Feed Aggregator')

    # Get all articles and create a DataFrame
    df, log_messages = get_all_articles()

    # Display the processing log in the sidebar using an expander with small font
    with st.sidebar.expander("Processing Log", expanded=False):
        st.markdown('<div style="font-size: small;">', unsafe_allow_html=True)
        for message in log_messages:
            st.write(message)
        st.markdown('</div>', unsafe_allow_html=True)

    # Normalize categories in the DataFrame
    df['Normalized_Categories'] = df.apply(lambda row: normalize_categories(row['Categories'], row['URL']), axis=1)

    # Extract counts for general categories and specific regions separately
    category_counts = df['Normalized_Categories'].explode().value_counts()
    location_counts = category_counts[category_counts.index.isin(regional_locations)]
    general_category_counts = category_counts[~category_counts.index.isin(regional_locations)]

    # Prepare category options with counts for sidebar dropdowns
    category_options = [f"{cat} ({count})" for cat, count in general_category_counts.items()]
    location_options = [f"{loc} ({count})" for loc, count in location_counts.items()]

    # Sidebar: Filters
    st.sidebar.title("Filters")
    combined_search = st.sidebar.text_input('Search by Title or Keywords:')
    category_filter = st.sidebar.multiselect('Select Categories:', options=category_options, default=[])
    location_filter = st.sidebar.multiselect('Select Regional Locations (States and Cities):', options=location_options, default=[])
    category_logic = st.sidebar.radio('Category Filter Logic:', options=['OR', 'AND'], index=0)

    # Apply filters
    filtered_df = df.copy()

    # Extract actual category names from selected items (since they include counts)
    category_filter = [cat.split(' (')[0] for cat in category_filter]
    location_filter = [loc.split(' (')[0] for loc in location_filter]

    if category_filter or location_filter:
        if category_logic == 'OR':
            filtered_df = filtered_df[
                filtered_df['Normalized_Categories'].apply(lambda x: any(cat in x for cat in category_filter)) |
                filtered_df['Normalized_Categories'].apply(lambda x: any(loc in x for loc in location_filter))
            ]
        elif category_logic == 'AND':
            filtered_df = filtered_df[
                filtered_df['Normalized_Categories'].apply(lambda x: all(cat in x for cat in category_filter)) &
                filtered_df['Normalized_Categories'].apply(lambda x: all(loc in x for loc in location_filter))
            ]

    # Exact match for location filters to prevent partial matches
    if location_filter:
        filtered_df = filtered_df[
            filtered_df['Normalized_Categories'].apply(lambda x: all(loc in x for loc in location_filter))
        ]

    if combined_search:
        combined_search = combined_search.lower()
        filtered_df = filtered_df[
            filtered_df['Keywords'].str.lower().str.contains(combined_search, na=False) | 
            filtered_df['Description'].str.lower().str.contains(combined_search, na=False) |
            filtered_df['Title'].str.lower().str.contains(combined_search, na=False)
        ]

    # Sort the DataFrame by the newest publication date
    filtered_df = filtered_df.sort_values(by='Publication_Date', ascending=False)

    # Display results
    st.write(f"Number of articles found: {len(filtered_df)}")
    st.dataframe(filtered_df)

    # Download filtered CSV
    if not filtered_df.empty:
        csv = filtered_df.to_csv(index=False)
        b64 = base64.b64encode(csv.encode()).decode()
        href = f'<a href="data:text/csv;base64,{b64}" download="filtered_articles.csv">Download CSV</a>'
        st.markdown(href, unsafe_allow_html=True)

    # Add charts to visualize the data
    st.subheader("Visual Insights")
    # Bar chart for the Top 25 Categories by number of articles (sorted highest to lowest)
    top_25_categories = general_category_counts[:25]
    st.bar_chart(pd.DataFrame({'Categories': top_25_categories.index, 'Count': top_25_categories.values}).set_index('Categories'))

    # Bar chart showing the number of articles published during each hour of the day
    if not filtered_df.empty:
        filtered_df['Hour'] = filtered_df['Publication_Date'].dt.hour
        articles_per_hour = filtered_df['Hour'].value_counts().sort_index()
        st.bar_chart(articles_per_hour)

    # Display table representing the Distribution of Feeds
    feed_counts = filtered_df['Feed'].value_counts()
    st.write("Distribution of Feeds")
    st.write(feed_counts)

if __name__ == "__main__":
    main()


