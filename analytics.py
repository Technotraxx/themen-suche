import pandas as pd
import networkx as nx
from pyvis.network import Network
import plotly.graph_objects as go
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import LatentDirichletAllocation
import streamlit as st

@st.cache_data(ttl=3600)
def perform_topic_clustering(df: pd.DataFrame, n_topics: int = 5) -> pd.DataFrame:
    """
    Perform topic clustering on articles using LDA.
    
    Args:
        df (pd.DataFrame): DataFrame containing article data.
        n_topics (int): Number of topics to cluster.

    Returns:
        pd.DataFrame: DataFrame with topic labels.
    """
    vectorizer = TfidfVectorizer(stop_words='english', max_features=5000)
    tfidf_matrix = vectorizer.fit_transform(df['Title'] + " " + df['Keywords'])
    lda = LatentDirichletAllocation(n_components=n_topics, random_state=42)
    df['Topic'] = lda.fit_transform(tfidf_matrix).argmax(axis=1)
    return df

def create_topic_map(df: pd.DataFrame) -> Network:
    """
    Create a topic map visualization using PyVis.

    Args:
        df (pd.DataFrame): DataFrame containing clustered topics.

    Returns:
        Network: PyVis network graph.
    """
    G = nx.Graph()
    for _, row in df.iterrows():
        G.add_node(row['Title'], title=row['Title'], topic=row['Topic'])
        for word in row['Keywords'].split(','):
            G.add_edge(row['Title'], word.strip())
    
    net = Network(height="750px", width="100%", notebook=False)
    net.from_nx(G)
    return net

def create_topic_timeline(df: pd.DataFrame) -> go.Figure:
    """
    Create a timeline visualization for topics over time.

    Args:
        df (pd.DataFrame): DataFrame containing article publication dates and topics.

    Returns:
        go.Figure: Plotly figure for the topic timeline.
    """
    df['Date'] = pd.to_datetime(df['Publication_Date']).dt.date
    topic_counts = df.groupby(['Date', 'Topic']).size().unstack(fill_value=0)

    fig = go.Figure()
    for topic in topic_counts.columns:
        fig.add_trace(go.Scatter(x=topic_counts.index, y=topic_counts[topic], mode='lines', name=f"Topic {topic}"))
    
    fig.update_layout(title='Topic Timeline', xaxis_title='Date', yaxis_title='Number of Articles')
    return fig
