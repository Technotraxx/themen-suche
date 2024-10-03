import xml.etree.ElementTree as ET
import requests
import pandas as pd
import streamlit as st
from urllib.parse import urlparse, quote
import altair as alt
from io import BytesIO

# Importieren der Sitemaps und Kategorien aus den separaten Dateien
from sitemaps import SITEMAP_LIBRARY
from kategorien import BEKANNTE_KATEGORIEN

# Funktion zum Laden einer einzelnen Sitemap
def lade_einzelne_sitemap(xml_url):
    try:
        response = requests.get(xml_url)
        response.raise_for_status()
        xml_content = response.content
    except requests.exceptions.RequestException as e:
        st.error(f"Fehler beim Herunterladen der XML-Datei: {e}")
        return pd.DataFrame()

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        st.error(f"Fehler beim Parsen der XML-Datei: {e}")
        return pd.DataFrame()

    namespaces = {
        'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9',
        'news': 'http://www.google.com/schemas/sitemap-news/0.9',
        'image': 'http://www.google.com/schemas/sitemap-image/1.1',
        'video': 'http://www.google.com/schemas/sitemap-video/1.1',
        'atom': 'http://www.w3.org/2005/Atom',
        'rss': 'http://purl.org/rss/1.0/',
        'dc': 'http://purl.org/dc/elements/1.1/',
    }

    ergebnisse = []

    if root.tag.endswith('urlset'):  # Sitemap
        for url in root.findall('ns:url', namespaces):
            ergebnisse.append(verarbeite_sitemap_url(url, namespaces))
    elif root.tag.endswith('feed'):  # Atom-Feed
        for entry in root.findall('atom:entry', namespaces):
            ergebnisse.append(verarbeite_atom_entry(entry, namespaces))
    elif root.tag == 'rss':  # RSS-Feed
        channel = root.find('channel')
        if channel is not None:
            for item in channel.findall('item'):
                ergebnisse.append(verarbeite_rss_item(item, namespaces))

    # Entfernen von leeren Ergebnissen
    ergebnisse = [item for item in ergebnisse if item]
    df = pd.DataFrame(ergebnisse)
    return df

def verarbeite_sitemap_url(url, namespaces):
    loc_element = url.find('ns:loc', namespaces)
    if loc_element is not None:
        loc = loc_element.text
        rubrik = extrahiere_rubrik(loc)
        daten = {'loc': loc, 'rubrik': rubrik}
        
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
    daten = {
        'title': title.text if title is not None else None,
        'loc': loc,
        'publication_date': pub_date.text if pub_date is not None else None,
        'keywords': None,
        'rubrik': extrahiere_rubrik(loc if loc is not None else '')
    }
    
    if summary is not None:
        daten['description'] = summary.text
    
    return daten

def verarbeite_rss_item(item, namespaces):
    title = item.find('title')
    link = item.find('link')
    pub_date = item.find('pubDate')
    description = item.find('description')
    
    daten = {
        'title': title.text if title is not None else None,
        'loc': link.text if link is not None else None,
        'publication_date': pub_date.text if pub_date is not None else None,
        'keywords': None,
        'rubrik': extrahiere_rubrik(link.text if link is not None else '')
    }
    
    if description is not None:
        daten['description'] = description.text
    
    return daten

def extrahiere_rubrik(loc):
    parsed_url = urlparse(loc)
    path_parts = parsed_url.path.strip('/').split('/')
    rubrik = 'Unbekannt'
    
    for part in path_parts:
        if part.lower() in BEKANNTE_KATEGORIEN:
            rubrik = part.lower()
            break
    
    if rubrik == 'Unbekannt' and len(path_parts) >= 1:
        rubrik = path_parts[0].lower()
    
    return rubrik

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
        return pd.concat(dfs, ignore_index=True)
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

    df = lade_daten(xml_urls)

    if df.empty:
        st.warning("Keine Daten verfügbar.")
        return

    df['publication_date'] = pd.to_datetime(df['publication_date'], errors='coerce', utc=True)

    if 'publication_date' not in df.columns:
        st.error("Spalte 'publication_date' ist nicht vorhanden.")
        st.stop()

    df = df.dropna(subset=['publication_date'])

    if pd.api.types.is_datetime64_any_dtype(df['publication_date']):
        pass
    else:
        st.error("Fehler bei der Umwandlung von 'publication_date' in datetime.")
        st.stop()

    df['publication_date'] = df['publication_date'].dt.tz_convert('Europe/Berlin').dt.tz_localize(None)
    df['hour'] = df['publication_date'].dt.hour
    bins = [0, 8, 12, 18, 24]
    labels = ['0-8 Uhr', '8-12 Uhr', '12-18 Uhr', '18-24 Uhr']
    df['time_slot'] = pd.cut(df['hour'], bins=bins, labels=labels, right=False, include_lowest=True)
    df['time_slot'] = pd.Categorical(df['time_slot'], categories=labels, ordered=True)
    df['source'] = df['loc'].apply(lambda x: urlparse(x).netloc)

    rubriken_counts = df['rubrik'].value_counts()
    rubriken = rubriken_counts.index.tolist()
    sources = df['source'].unique()
    selected_sources = st.sidebar.multiselect("Quelle auswählen", sources, default=sources)
    df = df[df['source'].isin(selected_sources)]

    st.sidebar.header("Filteroptionen")
    selected_rubriken = st.sidebar.multiselect(
        "Rubrik auswählen (sortiert nach Anzahl der Artikel)",
        options=rubriken,
        format_func=lambda x: f"{x} ({rubriken_counts[x]})",
        default=[]
    )

    if selected_rubriken:
        df = df[df['rubrik'].isin(selected_rubriken)]
    else:
        df = df.iloc[0:0]
        st.info("Bitte wählen Sie mindestens eine Rubrik aus, um die Artikel anzuzeigen.")

    if not df.empty and df['publication_date'].notnull().any():
        start_date = df['publication_date'].min().date()
        end_date = df['publication_date'].max().date()
        selected_dates = st.sidebar.date_input("Veröffentlichungsdatum", [start_date, end_date])

        if len(selected_dates) == 2:
            start_date, end_date = selected_dates
            df = df[(df['publication_date'].dt.date >= start_date) & (df['publication_date'].dt.date <= end_date)]

    keyword = st.sidebar.text_input("Nach Keyword filtern")
    if keyword and not df.empty:
        df = df[df['keywords'].str.contains(keyword, case=False, na=False)]

    st.subheader("Gefundene Artikel")
    st.write(f"Anzahl der Artikel: {len(df)}")
    st.dataframe(df[['publication_date', 'title', 'rubrik', 'source', 'keywords', 'loc']])

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

    st.subheader("Artikelverteilung nach Zeitslots")
    if not df.empty and 'time_slot' in df.columns:
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

    st.subheader("Artikel Details")
    if not df.empty:
        search_term = st.text_input("Artikeltitel suchen")
        filtered_df = df[df['title'].str.contains(search_term, case=False, na=False)]
        if not filtered_df.empty:
            selected_index = st.selectbox("Artikel auswählen", filtered_df.index, format_func=lambda x: filtered_df.at[x, 'title'])
            article = filtered_df.loc[selected_index]
            st.write("**Titel:**", article['title'])
            st.write("**Rubrik:**", article['rubrik'])
            st.write("**Quelle:**", article['source'])
            st.write("**Veröffentlichungsdatum:**", article['publication_date'])
            st.write("**Keywords:**", article['keywords'])
            st.write("**URL:**", article['loc'])
            if pd.notna(article.get('image_loc', None)):
                st.image(article['image_loc'], caption=article.get('image_caption', ''))

            with st.expander("Artikel mit Jina.ai Reader anzeigen"):
                if st.button("Artikel abrufen"):
                    reader_url = "https://r.jina.ai/read"
                    params = {'url': article['loc']}
                    try:
                        reader_response = requests.get(reader_url, params=params)
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

if __name__ == "__main__":
    main()
