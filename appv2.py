import streamlit as st
import feedparser
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
import pandas as pd
import re
from collections import defaultdict
import base64

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

def main():
    st.title('News Feed Aggregator')

    # Extract all article URLs and metadata from all feeds
    all_articles = []
    for feed_name, feed_url in feeds.items():
        feed_type = determine_feed_type(feed_url)
        st.write(f"Processing '{feed_name}' as {feed_type.upper()}...")
        
        if feed_type == 'rss':
            articles = extract_urls_from_rss(feed_url)
            for article in articles:
                all_articles.append({
                    'Feed': feed_name,
                    'URL': article['link'],
                    'Title': article['title'],
                    'Description': article['description'],
                    'Keywords': ', '.join(article['keywords']),
                    'Publication_Date': article['publication_date']
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
                    'Publication_Date': entry['publication_date']
                })
    
    # Create a DataFrame from all_articles
    df = pd.DataFrame(all_articles)

    # Filters
    category_filter = st.selectbox('Select Category:', options=['All'] + df['Feed'].unique().tolist(), index=0)
    keyword_filter = st.text_input('Enter Keyword:')

    # Filter DataFrame based on user input
    filtered_df = df.copy()
    if category_filter != 'All':
        filtered_df = filtered_df[filtered_df['Feed'] == category_filter]
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
