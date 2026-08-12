from sqlalchemy import create_engine
import streamlit as st

DATABASES = {
    "137": create_engine(
        st.secrets["DB_137"]
    ),
    "137est": create_engine(
        st.secrets["DB_137EST"]
    ),
    "4101": create_engine(
        st.secrets["DB_4101"]
    ),
}