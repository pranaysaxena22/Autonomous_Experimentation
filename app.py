import streamlit as st

st.set_page_config(page_title="Cell POC", layout="wide")

st.title("Cell POC")
st.write("Your Streamlit app is running. Edit app.py to start building.")

name = st.text_input("What's your name?")
if name:
    st.success(f"Hello, {name}!")
