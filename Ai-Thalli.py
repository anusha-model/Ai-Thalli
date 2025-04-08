import streamlit as st
import re
import requests
from bs4 import BeautifulSoup
from youtube_transcript_api import YouTubeTranscriptApi
from duckduckgo_search import DDGS
import google.generativeai as genai

# ========== CONFIG ==========
GENAI_API_KEY = "AIzaSyDkCWbe60Y_f8jw-Tp_lHoHFsEnqb1QBoE"
genai.configure(api_key=GENAI_API_KEY)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
}

# ========== UTILS ==========
def clean_text(text):
    text = re.sub(r'\[\d+\]', '', text)
    text = re.sub(r'http[s]?://\S+', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.encode("ascii", "ignore").decode().strip()

def remove_unwanted_lines(structured_output):
    cleaned_output = []
    for line in structured_output:
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

# ========== YOUTUBE ==========
def extract_transcript(youtube_video_url):
    try:
        video_id = youtube_video_url.split("v=")[1].split("&")[0]
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join([entry['text'] for entry in transcript_list]).strip()
    except Exception as e:
        return f"❌ Transcript error: {e}"

def summarize_youtube(transcript):
    prompt = f"""
You are a YouTube video summarizer. You will be taking the transcript text
and summarizing the entire video and providing the important summary in points. Please provide the summary of the text given here:

Here is the transcript:
{transcript}
"""
    return send_to_gemini(prompt)

# ========== URL ==========
def fetch_full_html_content(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        for tag in soup(['script', 'style', 'noscript', 'iframe', 'object', 'embed', 'applet', 'header', 'footer', 'nav']):
            tag.decompose()

        body = soup.find('body')
        if not body:
            return "❌ Body content not found."

        structured_output = []
        for element in body.find_all(True):
            tag = element.name
            text = element.get_text(strip=True)
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

            if line:
                structured_output.append(clean_text(line))

        structured_output = remove_unwanted_lines(structured_output)
        final_output = "\n\n".join(structured_output)
        return send_to_gemini(f"Correct grammar, improve formatting, and preserve structure:\n\n{final_output}")

    except requests.exceptions.RequestException as e:
        return f"❌ Error fetching page: {e}"

# ========== GENERAL QUERY ==========
def get_top_sites_duckduckgo(query, count=5):
    with DDGS() as ddgs:
        results = ddgs.text(query, max_results=count)
        return [r['href'] for r in results if 'href' in r][:count]

def fetch_page_content(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        paragraphs = soup.find_all("p")
        return clean_text(" ".join(p.get_text() for p in paragraphs[:5]))
    except Exception as e:
        return f"⚠️ Could not fetch {url}: {e}"

def analyze_with_llm(query, site_contents):
    prompt = f"""You are a helpful AI assistant. Here is a question:\n\n{query}\n\n""" + \
        "\n\n".join([f"--- Website {i+1} ---\n{site_contents[i]}" for i in range(len(site_contents))]) + \
        "\n\nReturn only the best and most accurate answer."
    return send_to_gemini(prompt)

def fetch_top_5_and_analyze(query):
    websites = get_top_sites_duckduckgo(query, count=5)
    if not websites:
        return "🚫 No websites found via DuckDuckGo."
    site_contents = [fetch_page_content(url) for url in websites]
    return analyze_with_llm(query, site_contents)

# ========== STREAMLIT APP ==========
st.set_page_config(page_title="Web & YouTube Summarizer", layout="wide")
st.title("📚 Web & YouTube Summarizer using Gemini AI")

user_input = st.text_input("🔍 Enter a query, website URL, or YouTube video link:")

if st.button("Process") and user_input:
    with st.spinner("Processing..."):
        if "youtube.com/watch" in user_input or "youtu.be/" in user_input:
            transcript = extract_transcript(user_input)
            result = summarize_youtube(transcript)
        elif user_input.startswith("http://") or user_input.startswith("https://"):
            result = fetch_full_html_content(user_input)
        else:
            result = fetch_top_5_and_analyze(user_input)

    st.subheader("✅ Final Answer")
    st.markdown(result)
