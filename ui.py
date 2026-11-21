"""Streamlit test UI. Not used by the custom HTTP route."""
import streamlit as st
from engine import recommend

st.set_page_config(page_title="Eagles Wing ML Lab", page_icon="🕊️")
st.title("🕊️ Eagles Wing Recommendation Lab")
st.caption("Title-based semantic matches. The model has not read the videos or transcripts.")
text = st.text_area("What's on your heart?", placeholder="Put your thoughts here, and we'll find some videos that match.")
count = st.slider("Number of suggestions", 1, 10, 5)
if st.button("Find videos", disabled=not bool(text.strip())):
    try:
        with st.spinner("Matching your reflection to video titles..."):
            response = recommend(text, count)
        for item in response["recommendations"]:
            st.write(f'**{item["title"]}** — similarity {item["score"]:.2f}')
            st.link_button("Open on YouTube", f'https://www.youtube.com/watch?v={item["video_id"]}')
    except (OSError, ValueError) as exc:
        st.error(f"Model/index unavailable: {exc}")
    except Exception:
        st.error("Recommendation failed. Review server logs for model-loading errors.")
