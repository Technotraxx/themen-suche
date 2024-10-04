# Import libraries
import feedparser
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
import pandas as pd
import ipywidgets as widgets
from IPython.display import display, clear_output, HTML
import re  # For regex operations
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
    """
    Extract article URLs and metadata from an RSS feed.
    Returns a list of dictionaries with keys: 'link', 'title', 'description', 'keywords', 'publication_date', 'news_title'.
    """
    try:
        feed = feedparser.parse(feed_url)
        articles = []
        for entry in feed.entries:
            if 'link' in entry:
                # Extract keywords if available
                if 'tags' in entry:
                    keywords = [tag.term for tag in entry.tags if 'term' in tag]
                else:
                    keywords = []
                # Extract publication_date if available
                publication_date = ''
                if 'published' in entry:
                    publication_date = entry.published
                elif 'updated' in entry:
                    publication_date = entry.updated
                # Extract news:title if available
                news_title = ''
                if 'title_detail' in entry and 'base' in entry.title_detail:
                    news_title = entry.title
                article = {
                    'link': entry.link,
                    'title': entry.title if 'title' in entry else '',
                    'description': entry.description if 'description' in entry else '',
                    'keywords': keywords,
                    'publication_date': publication_date,
                    'news_title': news_title
                }
                articles.append(article)
        return articles
    except Exception as e:
        print(f"Error parsing RSS feed {feed_url}: {e}")
        return []

def extract_urls_from_sitemap(feed_url):
    """
    Extract article URLs and keywords from an XML sitemap.
    Returns a list of dictionaries with keys: 'loc', 'keywords', 'publication_date', 'news_title'.
    """
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
            if loc is not None:
                loc_text = loc.text
                # Attempt to find news:keywords
                keywords_elem = url.find('news:news/news:keywords', namespaces=namespace)
                if keywords_elem is not None and keywords_elem.text:
                    keywords = [kw.strip().lower() for kw in keywords_elem.text.split(',')]
                else:
                    keywords = []
                # Attempt to find news:publication_date
                pub_date_elem = url.find('news:news/news:publication_date', namespaces=namespace)
                if pub_date_elem is not None and pub_date_elem.text:
                    publication_date = pub_date_elem.text
                else:
                    publication_date = ''
                # Attempt to find news:title
                news_title_elem = url.find('news:news/news:title', namespaces=namespace)
                if news_title_elem is not None and news_title_elem.text:
                    news_title = news_title_elem.text
                else:
                    news_title = ''
                urls.append({
                    'loc': loc_text,
                    'keywords': keywords,
                    'publication_date': publication_date,
                    'news_title': news_title
                })
        return urls
    except Exception as e:
        print(f"Error parsing Sitemap {feed_url}: {e}")
        return []

def determine_feed_type(feed_url):
    """
    Attempt to parse the feed as RSS. If it fails, assume it's a sitemap.
    """
    try:
        feed = feedparser.parse(feed_url)
        if feed.bozo:
            # If bozo is True, there's a parsing issue; assume sitemap
            return 'sitemap'
        else:
            # Check if entries have links
            if hasattr(feed, 'entries') and len(feed.entries) > 0 and hasattr(feed.entries[0], 'link'):
                return 'rss'
            else:
                return 'sitemap'
    except:
        return 'sitemap'

def extract_categories(url):
    """
    Extract categories from the URL by parsing the path and removing the last segment.
    Automatically filters out non-category segments based on predefined patterns.
    """
    try:
        parsed_url = urlparse(url)
        path = parsed_url.path  # e.g., /politik/ausland/article-name-12345.html
        
        # Split the path into parts, ignoring empty strings
        parts = [part for part in path.split('/') if part]
        
        # Remove the last part which is typically the article slug
        potential_categories = parts[:-1]
        
        # Define patterns that indicate non-category segments
        # For example, segments starting with 'article', 'plus', 'id_', etc., followed by digits
        non_category_patterns = [
            r'^article\d+$',
            r'^plus\d+$',
            r'^amp\d+$',
            r'^content\d+$',
            r'^rss\d+$',
            r'^id_\d+$'  # Added to exclude 'id_100502722' etc.
        ]
        
        # Compile regex patterns for efficiency
        compiled_patterns = [re.compile(pattern) for pattern in non_category_patterns]
        
        # Filter out non-category segments
        categories = [cat for cat in potential_categories if not any(pattern.match(cat) for pattern in compiled_patterns)]
        
        return categories
    except Exception as e:
        print(f"Error parsing URL {url}: {e}")
        return []

def normalize_categories(categories):
    """
    Normalize categories by combining similar categories.
    For example, 'region', 'regionales', 'regional' -> 'regional'.
    """
    # Define normalization rules as a dictionary
    normalization_rules = {
        'regional': ['region', 'regionales', 'regional'],
        'wirtschaft': ['economy', 'wirtschaft'],
        'politik': ['politics', 'politik'],
        'ausland': ['international', 'ausland'],
        'sport': ['sports', 'sport'],
        # Add more normalization rules as needed
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
            normalized.append(cat.lower())  # Keep original if no rule matches
    return normalized

# Function to extract keywords from the feed data (already present)
def extract_feed_keywords(keywords_str):
    """
    Split the comma-separated keywords string into a list.
    """
    if keywords_str:
        return [kw.strip().lower() for kw in keywords_str.split(',')]
    else:
        return []

# Extract all article URLs and metadata from all feeds
all_articles = []

for feed_name, feed_url in feeds.items():
    feed_type = determine_feed_type(feed_url)
    print(f"Processing '{feed_name}' as {feed_type.upper()}...")
    
    if feed_type == 'rss':
        articles = extract_urls_from_rss(feed_url)
        print(f"Found {len(articles)} articles in '{feed_name}'.\n")
        for article in articles:
            all_articles.append({
                'Feed': feed_name,
                'URL': article['link'],
                'Title': article['title'],
                'Description': article['description'],
                'Keywords': ', '.join(article['keywords']),  # Join keywords into a comma-separated string
                'Publication_Date': article['publication_date'],
                'News_Title': article['news_title']
            })
    else:
        sitemap_entries = extract_urls_from_sitemap(feed_url)
        print(f"Found {len(sitemap_entries)} articles in '{feed_name}'.\n")
        for entry in sitemap_entries:
            all_articles.append({
                'Feed': feed_name,
                'URL': entry['loc'],
                'Title': entry['news_title'] if entry['news_title'] else '',
                'Description': '',
                'Keywords': ', '.join(entry['keywords']),  # Join keywords into a comma-separated string
                'Publication_Date': entry['publication_date'],
                'News_Title': entry['news_title']
            })

# Create a DataFrame from all_articles
df = pd.DataFrame(all_articles)

# Extract categories using the enhanced extract_categories function
df['Categories'] = df['URL'].apply(extract_categories)

# Normalize categories
df['Normalized_Categories'] = df['Categories'].apply(normalize_categories)

# Extract keywords into a list
df['Keywords_List'] = df['Keywords'].apply(extract_feed_keywords)

# Display the first few entries
print("Aggregated DataFrame:")
display(df.head())

# Count the number of articles per normalized category
category_counts = defaultdict(int)
for cats in df['Normalized_Categories']:
    for cat in cats:
        category_counts[cat] += 1

# Convert to a list of tuples and sort by count descending
sorted_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)

# Create a sorted list of categories based on count
sorted_category_list = [cat for cat, count in sorted_categories]

# Update unique_categories with sorted categories
unique_categories = sorted_category_list

# Create Dropdown Widgets with sorted categories
category_dropdown = widgets.Dropdown(
    options=['All'] + unique_categories,
    value='All',
    description='Category:',
    disabled=False,
)

# Create Feed Dropdown Widget
feed_dropdown = widgets.Dropdown(
    options=['All'] + list(feeds.keys()),
    value='All',
    description='Feed:',
    disabled=False,
)

# Create Keyword Search Widget
keyword_search = widgets.Text(
    value='',
    placeholder='Enter keyword',
    description='Keyword:',
    disabled=False
)

# Output widget to display DataFrame and count
output = widgets.Output()

# Initialize filtered_df
filtered_df = df.copy()

# Define the filtering function
def update_filter(change):
    global filtered_df
    with output:
        clear_output()
        selected_category = category_dropdown.value
        selected_feed = feed_dropdown.value
        search_keyword = keyword_search.value.lower().strip()
        
        filtered_df = df.copy()
        
        if selected_category != 'All':
            filtered_df = filtered_df[filtered_df['Normalized_Categories'].apply(lambda x: selected_category in x)]
        
        if selected_feed != 'All':
            filtered_df = filtered_df[filtered_df['Feed'] == selected_feed]
        
        if search_keyword:
            # Filter articles where the keyword is in the Keywords_List
            filtered_df = filtered_df[filtered_df['Keywords_List'].apply(lambda x: search_keyword in x)]
        
        count = len(filtered_df)
        print(f"Number of articles found: {count}")
        display(filtered_df)

# Attach the function to dropdowns and search box
category_dropdown.observe(update_filter, names='value')
feed_dropdown.observe(update_filter, names='value')
keyword_search.observe(update_filter, names='value')

# Display widgets and output
display(widgets.HBox([category_dropdown, feed_dropdown]))
display(keyword_search)
display(output)

# Initial display
with output:
    print(f"Number of articles found: {len(filtered_df)}")
    display(filtered_df)

# Optional Enhancement: Exporting the DataFrame to CSV
def export_to_csv(dataframe):
    """
    Export the provided DataFrame to a CSV file and create a download link.
    """
    csv = dataframe.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:text/csv;base64,{b64}" download="filtered_articles.csv">Download filtered_articles.csv</a>'
    return HTML(href)

# Button to export DataFrame to CSV
export_button = widgets.Button(
    description='Export Filtered CSV',
    disabled=False,
    button_style='info',
    tooltip='Click to export filtered DataFrame to CSV',
    icon='download'
)

# Output widget for export feedback
export_output = widgets.Output()

def on_export_click(b):
    with export_output:
        clear_output()
        display(export_to_csv(filtered_df))
        print("Exported 'filtered_articles.csv' successfully.")

export_button.on_click(on_export_click)

display(export_button, export_output)

# Optional Enhancement: Dynamic Feed Addition
# Widgets for adding a new feed
new_feed_name_widget = widgets.Text(
    value='',
    placeholder='Enter Feed Name',
    description='Feed Name:',
    disabled=False
)

new_feed_url_widget = widgets.Text(
    value='',
    placeholder='Enter Feed URL',
    description='Feed URL:',
    disabled=False
)

add_feed_button = widgets.Button(
    description='Add Feed',
    disabled=False,
    button_style='success',
    tooltip='Click to add feed',
    icon='plus'
)

# Output widget for feedback
add_feed_output = widgets.Output()

def add_feed(b):
    with add_feed_output:
        clear_output()
        new_name = new_feed_name_widget.value.strip()
        new_url = new_feed_url_widget.value.strip()
        if new_name and new_url:
            if new_name in feeds:
                print(f"Feed '{new_name}' already exists. Please choose a different name.")
            else:
                feeds[new_name] = new_url
                print(f"Added new feed: {new_name} -> {new_url}")
                # Determine feed type and extract URLs
                feed_type = determine_feed_type(new_url)
                if feed_type == 'rss':
                    articles = extract_urls_from_rss(new_url)
                    print(f"Found {len(articles)} articles in '{new_name}'.\n")
                    for article in articles:
                        df.loc[len(df)] = {
                            'Feed': new_name,
                            'URL': article['link'],
                            'Title': article['title'],
                            'Description': article['description'],
                            'Keywords': ', '.join(article['keywords']),
                            'Publication_Date': article['publication_date'],
                            'News_Title': article['news_title'],
                            'Categories': extract_categories(article['link']),
                            'Normalized_Categories': normalize_categories(extract_categories(article['link'])),
                            'Keywords_List': extract_feed_keywords(', '.join(article['keywords']))
                        }
                else:
                    sitemap_entries = extract_urls_from_sitemap(new_url)
                    print(f"Found {len(sitemap_entries)} articles in '{new_name}'.\n")
                    for entry in sitemap_entries:
                        df.loc[len(df)] = {
                            'Feed': new_name,
                            'URL': entry['loc'],
                            'Title': entry['news_title'] if entry['news_title'] else '',
                            'Description': '',
                            'Keywords': ', '.join(entry['keywords']),
                            'Publication_Date': entry['publication_date'],
                            'News_Title': entry['news_title'],
                            'Categories': extract_categories(entry['loc']),
                            'Normalized_Categories': normalize_categories(extract_categories(entry['loc'])),
                            'Keywords_List': extract_feed_keywords(', '.join(entry['keywords']))
                        }
                # Update category counts and sorted list
                global category_counts, sorted_categories, sorted_category_list, unique_categories
                category_counts = defaultdict(int)
                for cats in df['Normalized_Categories']:
                    for cat in cats:
                        category_counts[cat] += 1
                sorted_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
                sorted_category_list = [cat for cat, count in sorted_categories]
                unique_categories = sorted_category_list
                category_dropdown.options = ['All'] + unique_categories
                print(f"Unique categories updated. Total categories: {len(sorted_category_list)}.")
        else:
            print("Please provide both Feed Name and Feed URL.")

add_feed_button.on_click(add_feed)

display(new_feed_name_widget, new_feed_url_widget, add_feed_button, add_feed_output)
