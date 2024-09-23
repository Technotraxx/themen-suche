import xml.etree.ElementTree as ET
import requests
import pandas as pd
import streamlit as st

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
            if '/politik/' in loc:
                daten = {'loc': loc}
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
    st.title("Politik-Artikel aus der XML-Datei")
    
    xml_url = 'https://www.stern.de/736974656d6170-news.xml'
    
    df = lade_daten(xml_url)
    
    if df.empty:
        st.warning("Keine Daten verfügbar.")
        return
    
    # Veröffentlichungsdatum in datetime umwandeln
    df['publication_date'] = pd.to_datetime(df['publication_date'])
    
    # Filteroptionen im Sidebar
    st.sidebar.header("Filteroptionen")
    
    # Nach Datum filtern
    start_date = df['publication_date'].min().date()
    end_date = df['publication_date'].max().date()
    selected_dates = st.sidebar.date_input("Veröffentlichungsdatum", [start_date, end_date])
    
    if len(selected_dates) == 2:
        start_date, end_date = selected_dates
        df = df[(df['publication_date'].dt.date >= start_date) & (df['publication_date'].dt.date <= end_date)]
    
    # Nach Keyword filtern
    keyword = st.sidebar.text_input("Nach Keyword filtern")
    if keyword:
        df = df[df['keywords'].str.contains(keyword, case=False, na=False)]
    
    # Datenanzeige
    st.subheader("Gefundene Artikel")
    st.write(f"Anzahl der Artikel: {len(df)}")
    st.dataframe(df[['publication_date', 'title', 'keywords', 'loc']])
    
    # Download-Optionen
    st.subheader("Daten exportieren")
    export_format = st.selectbox("Exportformat wählen", ["CSV", "Excel", "JSON"])
    
    if st.button("Daten exportieren"):
        if export_format == "CSV":
            csv = df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(label="CSV herunterladen", data=csv, file_name='politik_artikel.csv', mime='text/csv')
        elif export_format == "Excel":
            excel_buffer = pd.ExcelWriter('politik_artikel.xlsx', engine='xlsxwriter')
            df.to_excel(excel_buffer, index=False)
            excel_buffer.save()
            st.download_button(label="Excel herunterladen", data=open('politik_artikel.xlsx', 'rb'), file_name='politik_artikel.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        elif export_format == "JSON":
            json_data = df.to_json(orient='records', force_ascii=False)
            st.download_button(label="JSON herunterladen", data=json_data, file_name='politik_artikel.json', mime='application/json')
    
    # Visualisierung
    st.subheader("Artikel nach Datum")
    artikel_pro_tag = df['publication_date'].dt.date.value_counts().sort_index()
    st.bar_chart(artikel_pro_tag)
    
    # Einzelne Artikel anzeigen
    st.subheader("Artikel Details")
    selected_article = st.selectbox("Artikel auswählen", df['title'])
    article = df[df['title'] == selected_article].iloc[0]
    st.write("**Titel:**", article['title'])
    st.write("**Veröffentlichungsdatum:**", article['publication_date'])
    st.write("**Keywords:**", article['keywords'])
    st.write("**URL:**", article['loc'])
    if pd.notna(article.get('image_loc', None)):
        st.image(article['image_loc'], caption=article.get('image_caption', ''))
    
if __name__ == "__main__":
    main()
