import xml.etree.ElementTree as ET
import requests
import pandas as pd
import streamlit as st
from urllib.parse import urlparse, quote_plus
import re
import altair as alt

# Importieren der Sitemaps und Kategorien aus den separaten Dateien
from sitemaps import SITEMAP_LIBRARY
from kategorien import BEKANNTE_KATEGORIEN

# Funktion zum Herunterladen und Parsen der XML-Datei
@st.cache_data
def lade_daten(xml_url):
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
    }
    
    ergebnisse = []
    
    for url in root.findall('ns:url', namespaces):
        loc_element = url.find('ns:loc', namespaces)
        if loc_element is not None:
            loc = loc_element.text
            # Rubrik aus der URL extrahieren
            parsed_url = urlparse(loc)
            path_parts = parsed_url.path.strip('/').split('/')
            rubrik = 'Unbekannt'

            # Kategorien erkennen
            for part in path_parts:
                if part.lower() in BEKANNTE_KATEGORIEN:
                    rubrik = part.lower()
                    break  # Erste gefundene Kategorie verwenden

            # Falls keine bekannte Kategorie gefunden wurde, erstes Pfadsegment verwenden
            if rubrik == 'Unbekannt' and len(path_parts) >= 1:
                rubrik = path_parts[0].lower()

            daten = {'loc': loc, 'rubrik': rubrik}
            news_element = url.find('news:news', namespaces)
            if news_element is not None:
                publication = news_element.find('news:publication', namespaces)
                if publication is not None:
                    name = publication.find('news:name', namespaces)
                    language = publication.find('news:language', namespaces)
                    if name is not None:
                        daten['name'] = name.text
                    if language is not None:
                        daten['language'] = language.text
                pub_date = news_element.find('news:publication_date', namespaces)
                title = news_element.find('news:title', namespaces)
                keywords = news_element.find('news:keywords', namespaces)
                if pub_date is not None:
                    daten['publication_date'] = pub_date.text
                if title is not None:
                    daten['title'] = title.text
                if keywords is not None:
                    daten['keywords'] = keywords.text
            image_element = url.find('image:image', namespaces)
            if image_element is not None:
                image_loc = image_element.find('image:loc', namespaces)
                caption = image_element.find('image:caption', namespaces)
                if image_loc is not None:
                    daten['image_loc'] = image_loc.text
                if caption is not None:
                    daten['image_caption'] = caption.text
            ergebnisse.append(daten)
    
    df = pd.DataFrame(ergebnisse)
    return df

# Hauptprogramm
def main():
    st.title("Artikel aus verschiedenen Rubriken")
    
    # Auswahl der Sitemap
    st.sidebar.header("Sitemap-Auswahl")
    sitemap_choice = st.sidebar.selectbox("Wählen Sie eine Sitemap", list(SITEMAP_LIBRARY.keys()))
    xml_url = SITEMAP_LIBRARY[sitemap_choice]
    
    df = lade_daten(xml_url)
    
    if df.empty:
        st.warning("Keine Daten verfügbar.")
        return
    
    # Veröffentlichungsdatum in datetime umwandeln
    df['publication_date'] = pd.to_datetime(df['publication_date'], errors='coerce')
    
    # Neue Spalte 'time_slot' hinzufügen
    if not df.empty and df['publication_date'].notnull().any():
        df['hour'] = df['publication_date'].dt.hour
        bins = [0, 8, 12, 18, 24]
        labels = ['0-8 Uhr', '8-12 Uhr', '12-18 Uhr', '18-24 Uhr']
        df['time_slot'] = pd.cut(df['hour'], bins=bins, labels=labels, right=False, include_lowest=True)
        # Setze 'time_slot' als kategorische Variable mit der gewünschten Reihenfolge
        df['time_slot'] = pd.Categorical(df['time_slot'], categories=labels, ordered=True)
    
    # Verfügbare Rubriken ermitteln
    rubriken = df['rubrik'].dropna().unique()
    rubriken.sort()
    
    # Filteroptionen im Sidebar
    st.sidebar.header("Filteroptionen")
    
    # Rubrikenauswahl - Standardmäßig keine Rubriken ausgewählt
    selected_rubriken = st.sidebar.multiselect("Rubrik auswählen", rubriken, default=[])
    if selected_rubriken:
        df = df[df['rubrik'].isin(selected_rubriken)]
    else:
        # Wenn keine Rubriken ausgewählt sind, leeren DataFrame setzen
        df = df.iloc[0:0]
        st.info("Bitte wählen Sie mindestens eine Rubrik aus, um die Artikel anzuzeigen.")
    
    # Nach Datum filtern
    if not df.empty and df['publication_date'].notnull().any():
        start_date = df['publication_date'].min().date()
        end_date = df['publication_date'].max().date()
        selected_dates = st.sidebar.date_input("Veröffentlichungsdatum", [start_date, end_date])
        
        if len(selected_dates) == 2:
            start_date, end_date = selected_dates
            df = df[(df['publication_date'].dt.date >= start_date) & (df['publication_date'].dt.date <= end_date)]
    
    # Nach Keyword filtern
    keyword = st.sidebar.text_input("Nach Keyword filtern")
    if keyword and not df.empty:
        df = df[df['keywords'].str.contains(keyword, case=False, na=False)]
    
    # Datenanzeige
    st.subheader(f"Gefundene Artikel in {sitemap_choice}")
    st.write(f"Anzahl der Artikel: {len(df)}")
    st.dataframe(df[['publication_date', 'title', 'rubrik', 'keywords', 'loc']])
    
    # Download-Optionen
    st.subheader("Daten exportieren")
    export_format = st.selectbox("Exportformat wählen", ["CSV", "Excel", "JSON"])
    
    if st.button("Daten exportieren"):
        if not df.empty:
            if export_format == "CSV":
                csv = df.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(label="CSV herunterladen", data=csv, file_name='artikel.csv', mime='text/csv')
            elif export_format == "Excel":
                excel_buffer = pd.ExcelWriter('artikel.xlsx', engine='xlsxwriter')
                df.to_excel(excel_buffer, index=False)
                excel_buffer.save()
                st.download_button(label="Excel herunterladen", data=open('artikel.xlsx', 'rb'), file_name='artikel.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            elif export_format == "JSON":
                json_data = df.to_json(orient='records', force_ascii=False)
                st.download_button(label="JSON herunterladen", data=json_data, file_name='artikel.json', mime='application/json')
        else:
            st.warning("Keine Daten zum Exportieren verfügbar.")
    
    # Visualisierung
    st.subheader("Artikelverteilung nach Zeitslots")
    if not df.empty and 'time_slot' in df.columns:
        # Gruppieren der Daten
        artikel_pro_slot = df.groupby('time_slot').size().reset_index(name='Anzahl')
        
        # Erstellung des Balkendiagramms mit Altair
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
    
    # Einzelne Artikel anzeigen
    st.subheader("Artikel Details")
    if not df.empty:
        selected_article = st.selectbox("Artikel auswählen", df['title'])
        article = df[df['title'] == selected_article].iloc[0]
        st.write("**Titel:**", article['title'])
        st.write("**Rubrik:**", article['rubrik'])
        st.write("**Veröffentlichungsdatum:**", article['publication_date'])
        st.write("**Keywords:**", article['keywords'])
        st.write("**URL:**", article['loc'])
        if pd.notna(article.get('image_loc', None)):
            st.image(article['image_loc'], caption=article.get('image_caption', ''))
    else:
        st.write("Keine Artikel zum Anzeigen verfügbar.")

if __name__ == "__main__":
    main()


