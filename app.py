import xml.etree.ElementTree as ET
import requests
import pandas as pd
import streamlit as st
from urllib.parse import urlparse
import re
import altair as alt

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
                pub_date = news_element.find('news:publication_date', namespaces)
                if pub_date is not None and pub_date.text:
                    daten['publication_date'] = pub_date.text
                else:
                    daten['publication_date'] = None
                # Restliche Felder aus news:news extrahieren
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
            else:
                # Fallback: Verwenden von 'ns:lastmod' falls vorhanden
                lastmod_element = url.find('ns:lastmod', namespaces)
                if lastmod_element is not None and lastmod_element.text:
                    daten['publication_date'] = lastmod_element.text
                else:
                    daten['publication_date'] = None
                # Restliche Felder können nicht aus 'news:news' extrahiert werden
                daten['title'] = None
                daten['keywords'] = None
                daten['name'] = None
                daten['language'] = None

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

# Funktion zum Laden mehrerer Sitemaps
@st.cache_data
def lade_daten(xml_urls):
    dfs = []
    for xml_url in xml_urls:
        df = lade_einzelne_sitemap(xml_url)
        if not df.empty:
            df['sitemap'] = xml_url  # Quelle hinzufügen
            dfs.append(df)
    if dfs:
        return pd.concat(dfs, ignore_index=True)
    else:
        return pd.DataFrame()

# Hauptprogramm
def main():
    st.title("Artikel aus verschiedenen Rubriken")

    # Auswahl der Sitemaps
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

    # Convert 'publication_date' to datetime
    df['publication_date'] = pd.to_datetime(df['publication_date'], errors='coerce', utc=True)

    # Überprüfen der Daten nach dem Laden
    st.write("Anzahl der Artikel vor Datumskonvertierung:", len(df))
    st.write("Erste Zeilen von df:")
    st.write(df.head())

    # Überprüfen, ob 'publication_date' vorhanden ist
    if 'publication_date' in df.columns:
        st.write("Spalte 'publication_date' ist vorhanden.")
        st.write("Inhalt von 'publication_date' nach Konvertierung:")
        st.write(df['publication_date'].head(20))
    else:
        st.error("Spalte 'publication_date' ist nicht vorhanden.")
        st.stop()

    # Anzahl der gültigen und ungültigen Datumswerte
    st.write("Anzahl der gültigen 'publication_date' nach Konvertierung:", df['publication_date'].notnull().sum())
    st.write("Anzahl der ungültigen 'publication_date' nach Konvertierung:", df['publication_date'].isnull().sum())

    # Entfernen von Zeilen ohne gültiges Veröffentlichungsdatum
    df = df.dropna(subset=['publication_date'])

    # Überprüfen, ob 'publication_date' jetzt datetime ist
    st.write("Datentyp von 'publication_date' nach Konvertierung:", df['publication_date'].dtype)
    if pd.api.types.is_datetime64_any_dtype(df['publication_date']):
        st.success("Veröffentlichungsdatum erfolgreich in datetime umgewandelt.")
    else:
        st.error("Fehler bei der Umwandlung von 'publication_date' in datetime.")
        st.stop()

    # Convert UTC to local time and remove timezone information
    df['publication_date'] = df['publication_date'].dt.tz_convert('Europe/Berlin').dt.tz_localize(None)

    # Neue Spalte 'time_slot' hinzufügen
    df['hour'] = df['publication_date'].dt.hour
    bins = [0, 8, 12, 18, 24]
    labels = ['0-8 Uhr', '8-12 Uhr', '12-18 Uhr', '18-24 Uhr']
    df['time_slot'] = pd.cut(df['hour'], bins=bins, labels=labels, right=False, include_lowest=True)
    # Setze 'time_slot' als kategorische Variable mit der gewünschten Reihenfolge
    df['time_slot'] = pd.Categorical(df['time_slot'], categories=labels, ordered=True)

    # Quelle hinzufügen
    df['source'] = df['loc'].apply(lambda x: urlparse(x).netloc)

    # Verfügbare Rubriken ermitteln und nach Anzahl der Artikel sortieren
    rubriken_counts = df['rubrik'].value_counts()
    rubriken = rubriken_counts.index.tolist()

    # Verfügbare Quellen ermitteln
    sources = df['source'].unique()
    selected_sources = st.sidebar.multiselect("Quelle auswählen", sources, default=sources)
    df = df[df['source'].isin(selected_sources)]

    # Filteroptionen im Sidebar
    st.sidebar.header("Filteroptionen")

    # Rubrikenauswahl - Standardmäßig keine Rubriken ausgewählt
    selected_rubriken = st.sidebar.multiselect(
        "Rubrik auswählen (sortiert nach Anzahl der Artikel)",
        options=rubriken,
        format_func=lambda x: f"{x} ({rubriken_counts[x]})",
        default=[]
    )

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
    st.subheader("Gefundene Artikel")
    st.write(f"Anzahl der Artikel: {len(df)}")
    st.dataframe(df[['publication_date', 'title', 'rubrik', 'source', 'keywords', 'loc']])

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
        st.write("**Quelle:**", article['source'])
        st.write("**Veröffentlichungsdatum:**", article['publication_date'])
        st.write("**Keywords:**", article['keywords'])
        st.write("**URL:**", article['loc'])
        if pd.notna(article.get('image_loc', None)):
            st.image(article['image_loc'], caption=article.get('image_caption', ''))

        # Jina.ai Reader Integration
        with st.expander("Artikel mit Jina.ai Reader anzeigen"):
            if st.button("Artikel abrufen"):
                # Verwenden der Artikel-URL direkt ohne Encoding
                reader_url = f"https://r.jina.ai/{article['loc']}"
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
        st.write("Keine Artikel zum Anzeigen verfügbar.")

if __name__ == "__main__":
    main()
