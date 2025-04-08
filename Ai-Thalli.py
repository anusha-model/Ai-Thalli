import streamlit as st
from dotenv import load_dotenv
import os
import re
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai

# Load environment variables
load_dotenv()
GENAI_API_KEY = os.getenv("AIzaSyDkCWbe60Y_f8jw-Tp_lHoHFsEnqb1QBoE")
genai.configure(api_key=GENAI_API_KEY)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
}

YOUTUBE_PROMPT = """
You are a YouTube video summarizer. You will be taking the transcript text
and summarizing the entire video, providing the important summary in points
within 250 words. Please provide the summary of the text given here:
"""

# Utility Functions
def is_url(input_text):
    return input_text.startswith("http://") or input_text.startswith("https://")

def clean_text(text):
    text = re.sub(r'\[\d+\]', '', text)  # citations
    text = re.sub(r'http[s]?://\S+', '', text)  # URLs
    text = re.sub(r'\s+', ' ', text)
    return text.encode("ascii", "ignore").decode().strip()

def remove_unwanted_lines(lines):
    cleaned_output = []
    for line in lines:
        if re.match(r'^[A-Z][a-z]+\s[A-Z][a-z]+$', line.strip()):
            continue
        if re.search(r'\*\*[^()\n]+\*\*', line) and not re.search(r'\*\*\(.*\)\*\*', line):
            continue
        if re.match(r'^\*\s+(\w+\s*){1,3}$', line.strip()):
            continue
        if '[Content Placeholder' in line:
            continue
        cleaned_output.append(line)
    return cleaned_output

def send_to_gemini(prompt_text):
    model = genai.GenerativeModel("gemini-1.5-pro-latest")
    response = model.generate_content(prompt_text)
    return response.text.strip()

# YouTube Functions
def extract_transcript_details(youtube_video_url):
    try:
        if "v=" in youtube_video_url:
            video_id = youtube_video_url.split("v=")[1].split("&")[0]
        else:
            video_id = youtube_video_url.split("/")[-1]

        transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
        transcript = " ".join([item["text"] for item in transcript_data])
        return transcript, video_id
    except Exception as e:
        st.error(f"Failed to extract transcript: {e}")
        return None, None

def generate_gemini_content(transcript_text):
    return send_to_gemini(YOUTUBE_PROMPT + transcript_text)

# Web Analysis Functions
def get_top_sites_duckduckgo(query, count=5):
    with DDGS() as ddgs:
        results = ddgs.text(query, max_results=count)
        return [r['href'] for r in results if 'href' in r][:count]

def fetch_page_content(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        paragraphs = soup.find_all("p")
        text = " ".join(p.get_text() for p in paragraphs[:5])
        return clean_text(text)
    except Exception as e:
        return f"⚠️ Could not fetch content from {url}: {e}"

def analyze_with_llm(query, site_contents):
    prompt = f"""You are a helpful AI assistant. Here is a question:\n\n{query}\n\n
Below are the extracted responses from the top 5 websites. Compare them, correct inaccuracies, and summarize the most reliable and accurate answer.

""" + "\n\n".join([f"--- Website {i+1} ---\n{site_contents[i]}" for i in range(len(site_contents))]) + "\n\nReturn only the best and most accurate answer."
    return send_to_gemini(prompt)

def fetch_top_5_and_analyze(query):
    websites = get_top_sites_duckduckgo(query, count=5)
    if not websites:
        return "🚫 No websites found via DuckDuckGo."
    site_contents = [fetch_page_content(url) for url in websites]
    return analyze_with_llm(query, site_contents)

def fetch_full_html_content(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        for tag in soup(['script', 'style', 'noscript', 'iframe', 'object', 'embed', 'applet', 'header', 'footer', 'nav']):
            tag.decompose()

        for noisy in soup.find_all("div", {"id": ["tpointtech-images", "link", "navbarCollapse", "nav", "menu", "sidebar"]}):
            noisy.decompose()

        body = soup.find('body')
        if not body:
            return "❌ Body content not found."

        structured_output = []
        for element in body.find_all(True):
            tag = element.name
            text = element.get_text(strip=True)
            data_title = element.get("title", "")

            if not text or len(text.split()) < 3:
                continue
            if any(bad in text.lower() for bad in ["cookie", "privacy", "login", "subscribe", "terms", "accept"]):
                continue

            line = ""
            if tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                level = int(tag[1])
                line = f"{'#' * level} {text}"
            elif tag == "p":
                line = f"{text}"
            elif tag == "li":
                line = f"- {text}"
            elif tag == "blockquote":
                line = f"> {text}"
            elif tag in ["pre", "code"]:
                line = f"```\n{text}\n```"
            elif tag == "a":
                display_text = text or data_title or element.get("name", "")
                if display_text:
                    line = display_text.replace("\xa0", " ").strip()
            elif tag == "img":
                alt = element.get("alt", "Image")
                line = f"[Image: {alt}]"
            elif tag == "table":
                line = "\n--- Table ---"
            elif tag == "tr":
                row = "| " + " | ".join(cell.get_text(strip=True) for cell in element.find_all(["th", "td"])) + " |"
                line = row
            elif tag in ["strong", "b"]:
                line = f"**{text}**"
            elif tag in ["em", "i"]:
                line = f"*{text}*"
            elif tag == "u":
                line = f"<u>{text}</u>"
            elif tag in ["s", "del", "strike"]:
                line = f"~~{text}~~"
            elif tag in ["abbr", "acronym"]:
                title = element.get("title", "")
                line = f"*{text}* ({title})" if title else f"*{text}*"
            elif tag == "mark":
                line = f"`{text}`"
            elif tag in ["dt", "dd", "figcaption", "caption", "summary"]:
                line = f"**{text}**"
            elif tag in ["kbd", "samp", "tt", "var", "q"]:
                line = f"`{text}`"

            if line:
                structured_output.append(clean_text(line))

        structured_output = remove_unwanted_lines(structured_output)
        final_output = "\n\n".join(structured_output)
        return send_to_gemini(f"Correct grammar, improve formatting, preserve structure:\n\n{final_output}")
    except Exception as e:
        return f"❌ Error fetching page content: {str(e)}"

# Streamlit UI
st.title("🧠 AI Summarizer: YouTube + Web Insights")

input_text = st.text_input("Enter a YouTube link or Search Query/URL:")

if input_text:
    if "youtube.com" in input_text or "youtu.be" in input_text:
        transcript, video_id = extract_transcript_details(input_text)
        if video_id:
            st.image(f"http://img.youtube.com/vi/{video_id}/0.jpg", use_container_width=True)
        if st.button("Summarize YouTube Video") and transcript:
            with st.spinner("Generating YouTube summary..."):
                summary = generate_gemini_content(transcript)
            st.markdown("## 📝 Video Summary:")
            st.write(summary)

    elif is_url(input_text):
        if st.button("Summarize Web Page"):
            with st.spinner("Processing web content..."):
                result = fetch_full_html_content(input_text)
            st.markdown("## 🌐 Web Page Summary:")
            st.write(result)
    else:
        if st.button("Get Best Answer from Web"):
            with st.spinner("Analyzing top 5 websites..."):
                result = fetch_top_5_and_analyze(input_text)
            st.markdown("## 🔍 Answer from Top 5 Sites:")
            st.write(result)
