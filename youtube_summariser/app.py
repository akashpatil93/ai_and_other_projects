import streamlit as st
from summariser import summarise_video

st.set_page_config(
    page_title="YouTube Video Summariser",
    page_icon="▶️",
    layout="centered",
)

st.title("YouTube Video Summariser")
st.caption("Paste a YouTube link and get a clean summary — no watching required.")

with st.sidebar:
    st.header("Configuration")
    api_key = st.text_input(
        "Anthropic API Key",
        type="password",
        placeholder="sk-ant-...",
        help="Your Claude API key from console.anthropic.com",
    )
    st.markdown("---")
    st.markdown("**Supported URL formats**")
    st.code(
        "https://youtube.com/watch?v=...\n"
        "https://youtu.be/...\n"
        "https://youtube.com/shorts/..."
    )

url = st.text_input(
    "YouTube URL",
    placeholder="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
)

summarise_btn = st.button("Summarise", type="primary", use_container_width=True)

if summarise_btn:
    if not api_key:
        st.error("Please enter your Anthropic API key in the sidebar.")
    elif not url.strip():
        st.error("Please enter a YouTube URL.")
    else:
        with st.spinner("Fetching transcript and generating summary…"):
            try:
                result = summarise_video(url.strip(), api_key)
                st.success(
                    f"Done! Transcript was **{result['transcript_length']:,} words**."
                )
                st.markdown("---")
                st.markdown(result["summary"])
                st.markdown("---")
                with st.expander("Video details"):
                    st.write(f"Video ID: `{result['video_id']}`")
                    st.write(
                        f"Watch on YouTube: https://www.youtube.com/watch?v={result['video_id']}"
                    )
            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"An unexpected error occurred: {str(e)}")
