import base64
import pandas as pd
import streamlit as st
from streamlit.runtime.caching import cache_data
from helpers import (determine_feed_type, extract_urls_from_rss, extract_urls_from_sitemap,
                     parse_datetime, parse_iso_datetime, extract_categories, normalize_categories, get_all_articles,
                     REGIONAL_LOCATIONS)

# ----------------------------- Main Application ----------------------------- #

@st.cache_data(ttl=3600)
def cached_get_all_articles():
    return get_all_articles()

def main():
    st.set_page_config(page_title='📰 News Feed Aggregator', layout='wide')
    st.title('📰 News Feed Aggregator')

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
            filtered_df['Title'].str.lower().str.contains(search_query, na=False)
        ]

    # Determine available categories and locations based on current filters
    available_categories = (
        filtered_df['Normalized_Categories']
        .explode()
        .dropna()
        .value_counts()
    )

    available_locations = available_categories.loc[lambda x: x.index.isin(REGIONAL_LOCATIONS)]
    available_categories = available_categories.loc[lambda x: ~x.index.isin(REGIONAL_LOCATIONS)]

    # Prepare filter options with counts
    category_options = [f"{cat} ({count})" for cat, count in available_categories.items()]
    location_options = [f"{loc} ({count})" for loc, count in available_locations.items()]

    # Retrieve previous selections and filter them to ensure they are still valid
    previous_selected_categories = st.session_state.get('selected_categories', [])
    selected_categories = [cat for cat in previous_selected_categories if cat in category_options]

    previous_selected_locations = st.session_state.get('selected_locations', [])
    selected_locations = [loc for loc in previous_selected_locations if loc in location_options]

    # Sidebar: Multiselects for categories and locations
    selected_categories = st.sidebar.multiselect(
        'Select Categories:',
        options=category_options,
        default=selected_categories,
        key='category_multiselect'
    )

    selected_locations = st.sidebar.multiselect(
        'Select Regional Locations:',
        options=location_options,
        default=selected_locations,
        key='location_multiselect'
    )

    # Update session state with current selections
    st.session_state['selected_categories'] = selected_categories
    st.session_state['selected_locations'] = selected_locations

    # Extract actual category and location names from selected items
    selected_categories_clean = [cat.split(' (')[0] for cat in selected_categories]
    selected_locations_clean = [loc.split(' (')[0] for loc in selected_locations]

    # Apply category and location filters
    filtered_df_final = filtered_df.copy()

    if selected_categories_clean or selected_locations_clean:
        if filter_logic == 'OR':
            condition = (
                filtered_df_final['Normalized_Categories'].apply(
                    lambda cats: any(cat in cats for cat in selected_categories_clean)
                ) if selected_categories_clean else pd.Series([False] * len(filtered_df_final))
            )
            if selected_locations_clean:
                condition |= filtered_df_final['Normalized_Categories'].apply(
                    lambda locs: any(loc in locs for loc in selected_locations_clean)
                )
            filtered_df_final = filtered_df_final[condition]
        elif filter_logic == 'AND':
            if selected_categories_clean:
                filtered_df_final = filtered_df_final[
                    filtered_df_final['Normalized_Categories'].apply(lambda cats: all(cat in cats for cat in selected_categories_clean))
                ]
            if selected_locations_clean:
                filtered_df_final = filtered_df_final[
                    filtered_df_final['Normalized_Categories'].apply(lambda locs: all(loc in locs for loc in selected_locations_clean))
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
        href = f'<a href="data:file/csv;base64,{b64}" download="filtered_articles.csv">💾 Download CSV</a>'
        st.markdown(href, unsafe_allow_html=True)

    # Visual Insights
    st.subheader("📊 Visual Insights")

    # Bar chart for Top 25 General Categories
    top_25_categories = (
        filtered_df_final['Normalized_Categories']
        .explode()
        .dropna()
        .value_counts()
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
