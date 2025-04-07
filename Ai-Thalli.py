import re
import requests
import streamlit as st
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import google.generativeai as genai

GENAI_API_KEY = "AIzaSyDkCWbe60Y_f8jw-Tp_lHoHFsEnqb1QBoE"  # Replace with your Gemini API key

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

def send_to_gemini(prompt_text, max_tokens=12000):
    genai.configure(api_key=GENAI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-pro-latest")

    try:
        if len(prompt_text) > max_tokens:
            prompt_text = prompt_text[:max_tokens]
            prompt_text += "\n\n[Truncated due to length limits]"

        response = model.generate_content(prompt_text)
        return response.text.strip()

    except genai.types.generation_types.StopCandidateException:
        return "⚠️ Gemini API stopped generation unexpectedly."
    except Exception as e:
        return f"❌ Gemini API Error: {str(e)}"

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
            data_title = element.get("data-title", "")

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

        if len(final_output) > 12000:
            final_output = final_output[:12000] + "\n\n[Truncated due to size limit]"

        return send_to_gemini(f"Correct grammar, improve formatting, preserve structure:\n\n{final_output}")

    except requests.exceptions.RequestException as e:
        return f"❌ Error fetching the page: {str(e)}"

def get_top_sites_duckduckgo(query, count=3):
    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=count)
            return [r['href'] for r in results if 'href' in r][:count]
    except Exception as e:
        return []

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

# --- Streamlit UI ---
# --- Streamlit UI ---
st.set_page_config(page_title="Ai-Thalli Web Analyzer Developed by Shiva", layout="wide")
st.title("🤖 Ai-Thalli Web Analyzer Developed by Shiva")

user_input = st.text_input("Enter your query or a URL:", "")
submit = st.button("Submit")

if submit and user_input:
    with st.spinner("🔍 Analyzing..."):
        if is_url(user_input):
            result = fetch_full_html_content(user_input)
        else:
            result = fetch_top_3_and_analyze(user_input)
        st.markdown("---")
        st.markdown(result)
