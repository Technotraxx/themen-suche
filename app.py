import xml.etree.ElementTree as ET
import requests
import pandas as pd
import streamlit as st
from urllib.parse import urlparse, quote
import altair as alt
from io import BytesIO

# Importieren der Sitemaps und Kategorien aus den separaten Dateien
from sitemaps import SITEMAP_LIBRARY

def load_and_process_sitemap(xml_url):
    try:
        response = requests.get(xml_url)
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except Exception as e:
        st.error(f"Error loading or parsing sitemap {xml_url}: {e}")
        return pd.DataFrame()

    results = []
    for url in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}url'):
        loc = url.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
        if loc is not None and loc.text:
            category = extract_category(loc.text)
            results.append({'loc': loc.text, 'category': category})
            
            # Debugging output
            st.write(f"URL: {loc.text}")
            st.write(f"Extracted Category: {category}")
            st.write("---")

    return pd.DataFrame(results)

def extract_category(url):
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.strip('/').split('/')
    
    ignore_words = {'www', 'com', 'de', 'article', 'articles', 'story', 'stories', 'news', 'id', 'html'}
    
    categories = []
    for part in path_parts[:3]:  # Only consider the first 3 parts of the path
        part = part.lower().rstrip('.html')
        if len(part) > 2 and not part.isdigit() and part not in ignore_words:
            categories.append(part)
    
    if not categories:
        domain = parsed_url.netloc.split('.')[-2]
        if domain not in ignore_words:
            categories.append(domain)
    
    return ' > '.join(categories) if categories else 'Unbekannt'
    
def verarbeite_sitemap_url(url, namespaces):
    loc_element = url.find('ns:loc', namespaces)
    if loc_element is not None:
        loc = loc_element.text
        category = ' > '.join(extrahiere_rubriken(loc))
        daten = {'loc': loc, 'category': category}

        news_element = url.find('news:news', namespaces)
        if news_element is not None:
            daten.update(extrahiere_news_daten(news_element, namespaces))
        else:
            daten.update(extrahiere_fallback_daten(url, namespaces))

        image_element = url.find('image:image', namespaces)
        if image_element is not None:
            daten.update(extrahiere_bild_daten(image_element, namespaces))

        return daten
    return {}

def verarbeite_atom_entry(entry, namespaces):
    title = entry.find('atom:title', namespaces)
    link = entry.find('atom:link', namespaces)
    pub_date = (entry.find('atom:published', namespaces) or
                entry.find('atom:updated', namespaces) or
                entry.find('dc:date', namespaces))
    summary = entry.find('atom:summary', namespaces)

    loc = link.get('href') if link is not None else None
    category = ' > '.join(extrahiere_rubriken(loc if loc else ''))
    daten = {
        'title': title.text if title is not None else None,
        'loc': loc,
        'publication_date': pub_date.text if pub_date is not None else None,
        'keywords': None,
        'category': category
    }

    if summary is not None:
        daten['description'] = summary.text

    return daten

def verarbeite_rss_item(item, namespaces):
    title = item.find('title')
    link = item.find('link')
    pub_date = item.find('pubDate')
    description = item.find('description')

    loc = link.text if link is not None else None
    category = ' > '.join(extrahiere_rubriken(loc if loc else ''))
    daten = {
        'title': title.text if title is not None else None,
        'loc': loc,
        'publication_date': pub_date.text if pub_date is not None else None,
        'keywords': None,
        'category': category
    }

    if description is not None:
        daten['description'] = description.text

    return daten

def extrahiere_news_daten(news_element, namespaces):
    daten = {}
    pub_date = news_element.find('news:publication_date', namespaces)
    if pub_date is not None and pub_date.text:
        daten['publication_date'] = pub_date.text

    publication = news_element.find('news:publication', namespaces)
    if publication is not None:
        name = publication.find('news:name', namespaces)
        language = publication.find('news:language', namespaces)
        if name is not None:
            daten['name'] = name.text
        if language is not None:
            daten['language'] = language.text

    title = news_element.find('news:title', namespaces)
    keywords = news_element.find('news:keywords', namespaces)
    if title is not None:
        daten['title'] = title.text
    if keywords is not None:
        daten['keywords'] = keywords.text

    return daten

def extrahiere_fallback_daten(url, namespaces):
    daten = {'publication_date': None, 'title': None, 'keywords': None, 'name': None, 'language': None}
    lastmod_element = url.find('ns:lastmod', namespaces)
    if lastmod_element is not None and lastmod_element.text:
        daten['publication_date'] = lastmod_element.text
    return daten

def extrahiere_bild_daten(image_element, namespaces):
    daten = {}
    image_loc = image_element.find('image:loc', namespaces)
    caption = image_element.find('image:caption', namespaces)
    if image_loc is not None:
        daten['image_loc'] = image_loc.text
    if caption is not None:
        daten['image_caption'] = caption.text
    return daten

@st.cache_data
def lade_daten(xml_urls):
    dfs = []
    progress_bar = st.progress(0)
    total = len(xml_urls)
    for i, xml_url in enumerate(xml_urls):
        st.write(f"Lade Daten von {xml_url}...")
        df = lade_einzelne_sitemap(xml_url)
        if not df.empty:
            df['sitemap'] = xml_url
            dfs.append(df)
        else:
            st.warning(f"Keine Daten von {xml_url} geladen.")
        progress_bar.progress((i + 1) / total)
    if dfs:
        result_df = pd.concat(dfs, ignore_index=True)
        st.write("Kombinierte Spalten nach dem Laden aller Sitemaps:", result_df.columns.tolist())
        return result_df
    else:
        return pd.DataFrame()

def main():
    st.title("Artikel aus verschiedenen Rubriken")
    st.sidebar.header("Sitemap-Auswahl")
    sitemap_options = list(SITEMAP_LIBRARY.keys()) + ['Alle Sitemaps']
    sitemap_choice = st.sidebar.selectbox("Wählen Sie eine Sitemap", sitemap_options)

    if sitemap_choice == 'Alle Sitemaps':
        xml_urls = list(SITEMAP_LIBRARY.values())
    else:
        xml_urls = [SITEMAP_LIBRARY[sitemap_choice]]

    dfs = []
    for xml_url in xml_urls:
        df = load_and_process_sitemap(xml_url)
        if not df.empty:
            df['sitemap'] = xml_url
            dfs.append(df)

    if dfs:
        df = pd.concat(dfs, ignore_index=True)
    else:
        df = pd.DataFrame()

    if not df.empty:
        # Check if 'publication_date' column exists
        if 'publication_date' in df.columns:
            df['publication_date'] = pd.to_datetime(df['publication_date'], errors='coerce', utc=True)
            df = df.dropna(subset=['publication_date'])
            
            if not df.empty:
                df['publication_date'] = df['publication_date'].dt.tz_convert('Europe/Berlin').dt.tz_localize(None)
                df['hour'] = df['publication_date'].dt.hour
                bins = [0, 8, 12, 18, 24]
                labels = ['0-8 Uhr', '8-12 Uhr', '12-18 Uhr', '18-24 Uhr']
                df['time_slot'] = pd.cut(df['hour'], bins=bins, labels=labels, right=False, include_lowest=True)
                df['time_slot'] = pd.Categorical(df['time_slot'], categories=labels, ordered=True)
            else:
                st.warning("No valid publication dates found in the data.")
        else:
            st.warning("Publication date column not found in the data.")

        # Check if 'loc' column exists for source extraction
        if 'loc' in df.columns:
            df['source'] = df['loc'].apply(lambda x: urlparse(x).netloc)
        else:
            st.warning("URL column not found in the data.")

        # Display the data we have
        st.write("Vorhandene Spalten im DataFrame:", df.columns.tolist())
        st.write("Anzahl der geladenen Zeilen:", len(df))
        st.write(df.head())

        if 'source' in df.columns:
            sources = df['source'].unique()
            selected_sources = st.sidebar.multiselect("Quelle auswählen", sources, default=sources)
            df = df[df['source'].isin(selected_sources)]

        st.sidebar.header("Filteroptionen")

        # Flexible category filter
        if 'category' in df.columns:
            all_categories = set()
            for category in df['category'].dropna():
                all_categories.update(category.split(' > '))
            
            category_counts = {cat: df['category'].str.contains(cat, case=False).sum() for cat in all_categories}
            category_options = sorted(all_categories)
            
            selected_categories = st.sidebar.multiselect(
                "Kategorie auswählen",
                options=category_options,
                format_func=lambda x: f"{x} ({category_counts[x]})",
                default=[]
            )

            if selected_categories:
                df = df[df['category'].apply(lambda x: any(cat.lower() in x.lower() for cat in selected_categories))]

        if df.empty:
            st.info("Keine Artikel gefunden. Bitte passen Sie die Filterkriterien an.")
            return

        if 'publication_date' in df.columns and df['publication_date'].notnull().any():
            start_date = df['publication_date'].min().date()
            end_date = df['publication_date'].max().date()
            selected_dates = st.sidebar.date_input("Veröffentlichungsdatum", [start_date, end_date])

            if len(selected_dates) == 2:
                start_date, end_date = selected_dates
                df = df[(df['publication_date'].dt.date >= start_date) & (df['publication_date'].dt.date <= end_date)]

        keyword = st.sidebar.text_input("Nach Keyword filtern")
        if keyword and not df.empty:
            if 'keywords' in df.columns and 'title' in df.columns:
                df = df[df['keywords'].str.contains(keyword, case=False, na=False) | df['title'].str.contains(keyword, case=False, na=False)]
            elif 'title' in df.columns:
                df = df[df['title'].str.contains(keyword, case=False, na=False)]

        st.subheader("Gefundene Artikel")
        st.write(f"Anzahl der Artikel: {len(df)}")
        columns_to_display = [col for col in ['publication_date', 'title', 'category', 'source', 'keywords', 'loc'] if col in df.columns]
        st.dataframe(df[columns_to_display])

        # Export functionality
        st.subheader("Daten exportieren")
        export_format = st.selectbox("Exportformat wählen", ["CSV", "Excel", "JSON"])

        if st.button("Daten exportieren"):
            if not df.empty:
                if export_format == "CSV":
                    csv = df.to_csv(index=False, encoding='utf-8-sig')
                    st.download_button(label="CSV herunterladen", data=csv, file_name='artikel.csv', mime='text/csv')
                elif export_format == "Excel":
                    excel_buffer = BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                        df.to_excel(writer, index=False)
                    excel_data = excel_buffer.getvalue()
                    st.download_button(
                        label="Excel herunterladen",
                        data=excel_data,
                        file_name='artikel.xlsx',
                        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    )
                elif export_format == "JSON":
                    json_data = df.to_json(orient='records', force_ascii=False).encode('utf-8')
                    st.download_button(
                        label="JSON herunterladen",
                        data=json_data,
                        file_name='artikel.json',
                        mime='application/json'
                    )
            else:
                st.warning("Keine Daten zum Exportieren verfügbar.")

        # Visualization
        if not df.empty and 'time_slot' in df.columns:
            st.subheader("Artikelverteilung nach Zeitslots")
            artikel_pro_slot = df.groupby('time_slot').size().reset_index(name='Anzahl')
            chart = alt.Chart(artikel_pro_slot).mark_bar().encode(
                x=alt.X('time_slot:N', sort=labels, title='Zeitslot'),
                y=alt.Y('Anzahl:Q', title='Anzahl der Artikel')
            ).properties(
                width=600,
                height=400
            )
            st.altair_chart(chart)
        else:
            st.write("Keine Veröffentlichungsdaten verfügbar für die Visualisierung.")

        # Article details
        st.subheader("Artikel Details")
        if not df.empty and 'title' in df.columns:
            search_term = st.text_input("Artikeltitel suchen")
            filtered_df = df[df['title'].str.contains(search_term, case=False, na=False)]
            if not filtered_df.empty:
                selected_index = st.selectbox("Artikel auswählen", filtered_df.index, format_func=lambda x: filtered_df.at[x, 'title'])
                article = filtered_df.loc[selected_index]
                for col in df.columns:
                    if col != 'sitemap':
                        st.write(f"**{col.capitalize()}:** {article[col]}")

                if 'loc' in article:
                    with st.expander("Artikel mit Jina.ai Reader anzeigen"):
                        if st.button("Artikel abrufen"):
                            encoded_loc = quote(article['loc'], safe='')
                            reader_url = f"https://r.jina.ai/{encoded_loc}"
                            try:
                                reader_response = requests.get(reader_url)
                                reader_response.raise_for_status()
                                content = reader_response.text
                                st.markdown(f"**Response von Jina.ai Reader:**\n\n{content}")
                            except requests.exceptions.RequestException as e:
                                st.error(f"Fehler beim Abrufen des Artikels: {e}")
                        else:
                            st.write("Klicken Sie auf 'Artikel abrufen', um den Artikel über Jina.ai Reader abzurufen.")
            else:
                st.write("Keine Artikel entsprechen dem Suchbegriff.")
        else:
            st.write("Keine Artikel zum Anzeigen verfügbar.")
    else:
        st.warning("No data available.")

if __name__ == "__main__":
    main()
