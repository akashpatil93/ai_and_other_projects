# YouTube Summariser

A Streamlit app that fetches a YouTube video's transcript and generates a clean summary using Claude (Anthropic). No watching required.

---

## Features

- Paste any YouTube URL (standard, short, or Shorts)
- Fetches transcript automatically via `youtube-transcript-api`
- Summarises with Claude using LangChain
- Shows word count of the original transcript
- Displays video ID and watch link in an expandable details panel

---

## Supported URL Formats

```
https://youtube.com/watch?v=...
https://youtu.be/...
https://youtube.com/shorts/...
```

---

## Prerequisites

- Python 3.9+
- An Anthropic API key — get one at https://console.anthropic.com

---

## Setup

1. Clone the repo and navigate to this folder:
   ```bash
   cd youtube_summariser
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the app:
   ```bash
   streamlit run app.py
   ```

5. Open **http://localhost:8501** in your browser.

---

## Usage

1. In the sidebar, paste your **Anthropic API key** (`sk-ant-...`)
2. Paste a YouTube URL in the main input
3. Click **Summarise**
4. Read the generated summary — no API key is stored between sessions

---

## Files

```
youtube_summariser/
├── app.py             # Streamlit UI
├── summariser.py      # Transcript fetching and Claude summarisation logic
└── requirements.txt   # Python dependencies
```
