import base64
import pandas as pd
import streamlit as st
from streamlit.runtime.caching import cache_data
from helpers import (determine_feed_type, extract_urls_from_rss, extract_urls_from_sitemap,
                     parse_datetime, parse_iso_datetime, extract_categories, normalize_categories, get_all_articles,
                     REGIONAL_LOCATIONS)
from analytics import perform_topic_clustering, create_topic_map, create_topic_timeline

@st.cache_data(ttl=3600)
def cached_get_all_articles():
    return get_all_articles()

def main():
    st.set_page_config(page_title='📰 Enhanced News Feed Aggregator', layout='wide')
    st.title('📰 Enhanced News Feed Aggregator')

    # Retrieve all articles and log messages
    df, log_messages = cached_get_all_articles()

    # Sidebar: Processing Log
    with st.sidebar.expander("🗒 Processing Log", expanded=False):
        st.markdown('<div style="font-size: small;">', unsafe_allow_html=True)
        for message in log_messages:
            st.write(message)
        st.markdown('</div>', unsafe_allow_html=True)

    # Sidebar: Filters
    st.sidebar.title("🔍 Filters")
    filter_logic = st.sidebar.radio(
        'Category Filter Logic:', options=['AND', 'OR'], index=0, key='filter_logic_radio'
    )
    combined_search = st.sidebar.text_input('Search by Title or Keywords:', value='', key='combined_search_input')
    st.sidebar.markdown("")  # Space

    filtered_df = df.copy()
    if combined_search:
        search_query = combined_search.lower()
        filtered_df = filtered_df[
            filtered_df['Keywords'].str.lower().str.contains(search_query, na=False) |
            filtered_df['Title'].str.lower().str.contains(search_query, na=False)
        ]

    # Determine available categories and locations
    available_categories = (
        filtered_df['Normalized_Categories']
        .explode()
        .dropna()
        .value_counts()
        .loc[lambda x: ~x.index.isin(REGIONAL_LOCATIONS)]
    )
    available_locations = (
        filtered_df['Normalized_Categories']
        .explode()
        .dropna()
        .value_counts()
        .loc[lambda x: x.index.isin(REGIONAL_LOCATIONS)]
    )

    category_options = [f"{cat} ({count})" for cat, count in available_categories.items()]
    location_options = [f"{loc} ({count})" for loc, count in available_locations.items()]
    selected_categories = st.sidebar.multiselect('Select Categories:', options=category_options, key='category_multiselect')
    selected_locations = st.sidebar.multiselect('Select Regional Locations:', options=location_options, key='location_multiselect')

    # Apply category and location filters
    filtered_df_final = filtered_df.copy()
    selected_categories_clean = [cat.split(' (')[0] for cat in selected_categories]
    selected_locations_clean = [loc.split(' (')[0] for loc in selected_locations]
    if selected_categories_clean or selected_locations_clean:
        if filter_logic == 'OR':
            condition = (
                filtered_df_final['Normalized_Categories'].apply(lambda cats: any(cat in cats for cat in selected_categories_clean))
                if selected_categories_clean else pd.Series([False] * len(filtered_df_final))
            )
            if selected_locations_clean:
                condition |= filtered_df_final['Normalized_Categories'].apply(lambda locs: any(loc in locs for loc in selected_locations_clean))
            filtered_df_final = filtered_df_final[condition]
        elif filter_logic == 'AND':
            if selected_categories_clean:
                filtered_df_final = filtered_df_final[filtered_df_final['Normalized_Categories'].apply(lambda cats: all(cat in cats for cat in selected_categories_clean))]
            if selected_locations_clean:
                filtered_df_final = filtered_df_final[filtered_df_final['Normalized_Categories'].apply(lambda locs: all(loc in locs for loc in selected_locations_clean))]

    filtered_df_final = filtered_df_final.sort_values(by='Publication_Date', ascending=False)
    st.subheader(f"🔍 Number of articles found: {len(filtered_df_final)}")
    st.dataframe(filtered_df_final)

    # Download filtered articles as CSV
    if not filtered_df_final.empty:
        csv = filtered_df_final.to_csv(index=False)
        b64 = base64.b64encode(csv.encode()).decode()
        href = f'<a href="data:file/csv;base64,{b64}" download="filtered_articles.csv">💾 Download CSV</a>'
        st.markdown(href, unsafe_allow_html=True)

    # Topic Clustering and Visualization
    clustered_df = perform_topic_clustering(filtered_df_final)
    st.subheader("📊 Topic Map")
    topic_map = create_topic_map(clustered_df)
    st.markdown("**Interactive Topic Map**")
    topic_map.show("topic_map.html")
    st.markdown(f'<iframe src="topic_map.html" width="100%" height="750px" frameborder="0"></iframe>', unsafe_allow_html=True)

    st.subheader("📊 Topic Timeline")
    timeline = create_topic_timeline(clustered_df)
    st.plotly_chart(timeline)

if __name__ == "__main__":
    main()
