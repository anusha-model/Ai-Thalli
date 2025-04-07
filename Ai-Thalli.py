

# ✅ Write the Streamlit app to a file
import re
import requests
import streamlit as st
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import google.generativeai as genai

GENAI_API_KEY = "AIzaSyDkCWbe60Y_f8jw-Tp_lHoHFsEnqb1QBoE"  # Replace with env var in production

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
}

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
    genai.configure(api_key=GENAI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-pro-latest")
    response = model.generate_content(prompt_text)
    return response.text.strip()

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

            if line:
                structured_output.append(clean_text(line))

        structured_output = remove_unwanted_lines(structured_output)
        final_output = "\n\n".join(structured_output)
        return send_to_gemini(f"Correct grammar, improve formatting, preserve structure:\n\n{final_output}")

    except requests.exceptions.RequestException as e:
        return f"❌ Error fetching the page: {str(e)}"

def get_top_sites_duckduckgo(query, count=3):
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
Below are the extracted responses from the top 3 websites. Compare them, correct inaccuracies, and summarize the most reliable and accurate answer.

--- Website 1 ---
{site_contents[0]}

--- Website 2 ---
{site_contents[1]}

--- Website 3 ---
{site_contents[2]}

Return only the best and most accurate answer."""
    return send_to_gemini(prompt)

def fetch_top_3_and_analyze(query):
    websites = get_top_sites_duckduckgo(query, count=3)
    if not websites:
        return "🚫 No websites found via DuckDuckGo."

    site_contents = [fetch_page_content(url) for url in websites]
    best_answer = analyze_with_llm(query, site_contents)
    return f"✅ Final Answer:\n\n{best_answer}"

def is_url(input_text):
    return input_text.startswith("http://") or input_text.startswith("https://")

# ------------------ Streamlit UI ------------------
st.set_page_config(page_title="Web Intelligence by Gemini", layout="wide")
st.title("🔍 AI-Powered Web Intelligence Tool")
st.write("Enter a search query or a full URL to get structured, cleaned, and summarized information using Google Gemini.")

user_input = st.text_input("Enter a query or URL", placeholder="e.g. What is quantum computing? OR https://example.com/article")

if st.button("Get Answer") and user_input.strip():
    with st.spinner("Processing..."):
        if is_url(user_input):
            result = fetch_full_html_content(user_input)
        else:
            result = fetch_top_3_and_analyze(user_input)
        st.markdown("### ✅ Result:")
        st.markdown(result)
