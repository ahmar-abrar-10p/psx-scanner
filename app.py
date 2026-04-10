import streamlit as st

st.set_page_config(
    page_title="PSX AI Scanner",
    page_icon="📈",
    layout="wide",
)

scanner_page = st.Page("pages/0_KMI_Scanner.py", title="KMI Scanner", icon="📈", default=True)
analyzer_page = st.Page("pages/1_Stock_Analyzer.py", title="Stock Analyzer", icon="🔬")

nav = st.navigation([scanner_page, analyzer_page])
nav.run()
