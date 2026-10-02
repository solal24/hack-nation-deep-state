"""Demo UI. Run: streamlit run src/app.py"""
import streamlit as st

from llm import ask

st.set_page_config(page_title="Deep State", page_icon="🧠")
st.title("Deep State")
st.caption("Hack-Nation 7th Global AI Hackathon")

prompt = st.text_area("Input")
if st.button("Run") and prompt:
    with st.spinner("Thinking..."):
        st.markdown(ask(prompt))
