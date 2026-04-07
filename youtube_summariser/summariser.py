import re
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


def extract_video_id(url: str) -> str:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r"(?:v=)([A-Za-z0-9_-]{11})",
        r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:embed/)([A-Za-z0-9_-]{11})",
        r"(?:shorts/)([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError("Could not extract video ID from URL. Please check the link.")


def fetch_transcript(video_id: str) -> str:
    """Fetch transcript text from a YouTube video."""
    try:
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id)
        return " ".join(entry.text for entry in transcript)
    except TranscriptsDisabled:
        raise ValueError("Transcripts are disabled for this video.")
    except NoTranscriptFound:
        raise ValueError("No transcript found for this video. It may not have captions.")
    except Exception as e:
        raise ValueError(f"Failed to fetch transcript: {str(e)}")


def build_summary_chain(api_key: str):
    """Build a LangChain summarisation chain using Claude."""
    llm = ChatAnthropic(
        model="claude-sonnet-4-6",
        anthropic_api_key=api_key,
        max_tokens=1024,
    )

    prompt = ChatPromptTemplate.from_template(
        """You are an expert content summariser. Given the transcript of a YouTube video, produce a clean, well-structured summary.

Structure your response as:
## TL;DR
One to two sentences capturing the core message.

## Key Points
Bullet list of the 5–7 most important takeaways.

## Detailed Summary
A few concise paragraphs expanding on the key points.

## Who Should Watch This
One sentence on the ideal audience.

Transcript:
{transcript}

Produce only the summary — no preamble, no commentary."""
    )

    chain = prompt | llm | StrOutputParser()
    return chain


def summarise_video(url: str, api_key: str) -> dict:
    """
    Full pipeline: URL → transcript → summary.
    Returns a dict with 'summary' and 'transcript_length'.
    """
    video_id = extract_video_id(url)
    transcript = fetch_transcript(video_id)

    chain = build_summary_chain(api_key)
    summary = chain.invoke({"transcript": transcript})

    return {
        "summary": summary,
        "transcript_length": len(transcript.split()),
        "video_id": video_id,
    }
