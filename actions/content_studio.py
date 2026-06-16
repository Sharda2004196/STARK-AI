import os
import json
import asyncio
import time
import requests
import platform
import subprocess
import sys
import re
from pathlib import Path
from urllib.parse import quote
from actions.web_search import web_search as web_search_tool
from config import genai_client

try:
    from rembg import remove
    from PIL import Image
    _REMBG_AVAILABLE = True
except ImportError:
    _REMBG_AVAILABLE = False

def _get_api_key() -> str:
    """Load API key from the config file."""
    base_path = Path(__file__).resolve().parent.parent
    full_path = base_path / "config" / "api_keys.json"
    try:
        with open(full_path, 'r') as f:
            keys = json.load(f)
        for k, v in keys.items():
            if k.lower() in ["gemini_api_key", "google_api_key"]:
                return v
    except Exception as e:
        print(f"[!] Content Studio: Could not load API key: {e}")
    return None

def _get_save_dir() -> Path:
    save_dir = Path.home() / "Desktop" / "JarvisMedia"
    save_dir.mkdir(parents=True, exist_ok=True)
    return save_dir

# --- Shared Tools for Agents ---

def web_research(query: str) -> str:
    """Searches the web for current trends, facts, or viral data."""
    print(f"[Studio-Tool] 🔍 Researching: {query}...")
    return web_search_tool(parameters={"query": query})

def clean_text(text: str) -> str:
    """Strips out any AI-generated design instructions or meta-talk."""
    # Aggressive list of common instructional phrases to remove
    trash = [
        r"HIGH-CONTRAST.*?\.", r"VISUAL UTILIZING.*?\.", r"PORTRAIT WITH.*?\.",
        r"GLITCH EFFECT.*?\.", r"WORKSPACE WITH.*?\.", r"HIGHLIGHTS AND.*?\.",
        r"BADGE IN.*?\.", r"CONCEPT", r"LAYOUT", r"FEATURING", r"OVERLAPPING",
        r"USE A .*? EXPRESSION", r"A GLOWING .*? OVERLAY", r"AND A BRIGHT .*? BAR"
    ]
    cleaned = text.upper()
    for pattern in trash:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    
    # Final cleanup of common artifacts
    cleaned = cleaned.replace("THUMBNAIL", "").replace("CAROUSEL", "").strip(": ")
    
    # If the cleaning made it empty or it's still too long, take the meaningful words
    words = cleaned.split()
    if not words or len(words) > 8:
        # Fallback: Just take the core of the message
        cleaned = " ".join(words[:5]) if words else "AI UPDATE 2026"
        
    return cleaned.upper()

# --- "Pure Design" Media Renderers (Playwright) ---

def remove_background(input_path: Path) -> Path:
    """Removes background from an image and returns path to a transparent PNG."""
    if not _REMBG_AVAILABLE:
        return input_path
    
    print(f"[Studio-Tool] ✂️  Removing background from subject...")
    try:
        output_path = input_path.parent / f"subject_{int(time.time())}.png"
        with open(input_path, 'rb') as i:
            input_data = i.read()
            output_data = remove(input_data)
            with open(output_path, 'wb') as o:
                o.write(output_data)
        return output_path
    except Exception as e:
        print(f"[!] BG Removal failed: {e}")
        return input_path

def render_thumbnail(title: str, subtitle: str, output_path: Path, user_image_path: Path = None):
    """
    Renders a high-end 'Tech Pro' YouTube thumbnail (1280x720).
    Includes auto-BG removal, floating icons, and code textures.
    """
    # Clean text to prevent instruction leakage
    title_clean = clean_text(title)
    sub_clean = clean_text(subtitle)
    
    print(f"[Studio-Tool] 🎬 Designing Pro-Split Thumbnail: {title_clean[:20]}...")
    
    # Image logic: We put the subject on the right with a glow
    img_element = ""
    if user_image_path and user_image_path.exists():
        final_img_path = remove_background(user_image_path)
        subject_url = final_img_path.absolute().as_uri()
        img_element = f'<img src="{subject_url}" class="subject-img" />'
    else:
        img_element = '<div class="subject-placeholder"></div>'

    # Split title for the hook effect
    words = title_clean.split()
    main_word = words[0] if words else "AI"
    rest_of_title = " ".join(words[1:]) if len(words) > 1 else ""

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,900;1,900&family=Fira+Code:wght@700&display=swap');
            body, html {{
                margin: 0; padding: 0;
                width: 1280px; height: 720px;
                font-family: 'Inter', sans-serif;
                overflow: hidden;
                background: #02040a;
            }}
            .main-container {{
                position: relative;
                width: 100%; height: 100%;
                display: flex;
                background: radial-gradient(circle at 85% 50%, #004e92 0%, #02040a 85%);
            }}
            /* Code-Rain texture */
            .grid {{
                position: absolute;
                top: 0; left: 0; width: 100%; height: 100%;
                background-image: linear-gradient(rgba(0,229,255,0.06) 1px, transparent 1px),
                                  linear-gradient(90deg, rgba(0,229,255,0.06) 1px, transparent 1px);
                background-size: 50px 50px;
                z-index: 1;
            }}
            .text-area {{
                position: relative;
                z-index: 30;
                width: 65%;
                height: 100%;
                display: flex;
                flex-direction: column;
                justify-content: center;
                padding-left: 80px;
                box-sizing: border-box;
            }}
            .image-area {{
                position: relative;
                z-index: 20;
                width: 35%;
                height: 100%;
                display: flex;
                align-items: flex-end;
                justify-content: flex-end;
            }}
            .subject-img {{
                height: 110%; 
                object-fit: contain;
                filter: drop-shadow(0 0 50px rgba(0,229,255,0.5)) brightness(1.1);
                z-index: 25;
                margin-right: -40px;
                margin-bottom: -10px;
            }}
            .highlight-num {{
                font-size: 200px;
                font-weight: 900;
                color: #FFD700;
                line-height: 0.8;
                margin-bottom: 10px;
                font-style: italic;
                text-shadow: 8px 8px 0px #000;
                letter-spacing: -10px;
            }}
            .sub-header {{
                font-size: 42px;
                font-weight: 900;
                color: #FFFFFF;
                text-transform: uppercase;
                letter-spacing: 2px;
                margin-bottom: 15px;
                background: rgba(0,0,0,0.6);
                display: inline-block;
                padding: 5px 20px;
                border-left: 10px solid #FFD700;
            }}
            .main-title {{
                font-size: 92px;
                font-weight: 900;
                line-height: 0.9;
                text-transform: uppercase;
                font-style: italic;
                background: linear-gradient(180deg, #FFFFFF 20%, #00E5FF 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                filter: drop-shadow(0 10px 20px rgba(0,0,0,1));
            }}
            /* Modern Tech Icon */
            .floating-icon {{
                position: absolute;
                top: 60px; right: 400px;
                width: 140px; height: 140px;
                background: rgba(0,229,255,0.1);
                border: 2px solid #00E5FF;
                border-radius: 30px;
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 5;
                transform: rotate(-15deg);
                box-shadow: 0 0 40px rgba(0,229,255,0.2);
            }}
        </style>
    </head>
    <body>
        <div class="grid"></div>
        <div class="main-container">
            <div class="floating-icon">
                <svg width="80" height="80" viewBox="0 0 24 24" fill="none" stroke="#00E5FF" stroke-width="2">
                    <polyline points="16 18 22 12 16 6"></polyline>
                    <polyline points="8 6 2 12 8 18"></polyline>
                </svg>
            </div>
            <div class="text-area">
                <div class="highlight-num">{main_word}</div>
                <div class="sub-header">{sub_clean}</div>
                <div class="main-title">{rest_of_title}</div>
            </div>
            <div class="image-area">
                {img_element}
            </div>
        </div>
    </body>
    </html>
    """
    
    temp_dir = Path.home() / "AppData" / "Local" / "Temp"
    temp_html = temp_dir / f"thumb_{int(time.time())}.html"
    temp_html.write_text(html_content, encoding="utf-8")
    
    script = f"""
from playwright.sync_api import sync_playwright
import sys
def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={{"width": 1280, "height": 720}})
        page.goto(r"{temp_html.absolute().as_uri()}")
        page.wait_for_timeout(1500)
        page.screenshot(path=r"{output_path.absolute()}", quality=100)
        browser.close()
if __name__ == "__main__":
    run()
"""
    temp_py = temp_html.with_suffix(".py")
    temp_py.write_text(script, encoding="utf-8")
    try:
        subprocess.run([sys.executable, str(temp_py)], check=True, capture_output=True)
    finally:
        if temp_html.exists(): temp_html.unlink()
        if temp_py.exists(): temp_py.unlink()

def render_carousel_slide(title: str, text: str, slide_index: int, total_slides: int, output_path: Path):
    """
    Renders a professional carousel slide using HTML/CSS blueprints via Playwright.
    """
    print(f"[Studio-Tool] 🎨 Designing slide {slide_index + 1}/{total_slides}: {title[:20]}...")
    
    gradients = [
        "linear-gradient(135deg, #1e3c72 0%, #2a5298 100%)",
        "linear-gradient(135deg, #232526 0%, #414345 100%)",
        "linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%)"
    ]
    bg_style = gradients[slide_index % len(gradients)]
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="hi">
    <head>
        <meta charset="UTF-8">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&family=Noto+Sans+Devanagari:wght@400;700;900&display=swap');
            body, html {{
                margin: 0; padding: 0;
                width: 1080px; height: 1350px;
                font-family: 'Inter', 'Noto Sans Devanagari', sans-serif;
                overflow: hidden;
                background: {bg_style};
            }}
            .container {{
                position: relative;
                width: 100%; height: 100%;
                display: flex;
                flex-direction: column;
                justify-content: center;
                padding: 80px;
                box-sizing: border-box;
                color: white;
            }}
            .glass {{
                background: rgba(255, 255, 255, 0.05);
                backdrop-filter: blur(20px);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 40px;
                padding: 80px;
                height: 80%;
                display: flex;
                flex-direction: column;
                justify-content: center;
                box-shadow: 0 25px 50px rgba(0,0,0,0.3);
            }}
            .slide-num {{
                font-size: 180px;
                font-weight: 900;
                opacity: 0.1;
                position: absolute;
                top: 40px; right: 80px;
            }}
            .title {{
                font-size: 80px;
                font-weight: 900;
                line-height: 1.1;
                margin-bottom: 40px;
                color: #00E5FF;
                text-transform: uppercase;
                letter-spacing: -2px;
            }}
            .text {{
                font-size: 46px;
                line-height: 1.5;
                color: #FFFFFF;
                opacity: 0.95;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="slide-num">0{slide_index + 1}</div>
            <div class="glass">
                <div class="title">{title}</div>
                <div class="text">{text}</div>
            </div>
        </div>
    </body>
    </html>
    """
    
    temp_dir = Path.home() / "AppData" / "Local" / "Temp"
    temp_html = temp_dir / f"slide_{int(time.time())}_{slide_index}.html"
    temp_html.write_text(html_content, encoding="utf-8")
    
    script = f"""
from playwright.sync_api import sync_playwright
import sys
def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={{"width": 1080, "height": 1350}})
        page.goto(r"{temp_html.absolute().as_uri()}")
        page.wait_for_timeout(1000)
        page.screenshot(path=r"{output_path.absolute()}", quality=100)
        browser.close()
if __name__ == "__main__":
    run()
"""
    temp_py = temp_html.with_suffix(".py")
    temp_py.write_text(script, encoding="utf-8")
    try:
        subprocess.run([sys.executable, str(temp_py)], check=True, capture_output=True)
    finally:
        if temp_html.exists(): temp_html.unlink()
        if temp_py.exists(): temp_py.unlink()

def create_professional_carousel(slides: list[dict], base_save_dir: Path) -> str:
    """
    Helper to render multiple carousel slides into a subfolder.
    """
    total = len(slides)
    results = []
    for i, slide in enumerate(slides):
        title = slide.get("title", f"Step {i+1}")
        body = slide.get("body", "")
        output_file = base_save_dir / f"slide_{i+1}.jpg"
        try:
            render_carousel_slide(title, body, i, total, output_file)
            results.append(output_file.name)
        except Exception as e:
            print(f"[Studio] ❌ Slide {i+1} failed: {e}")
    return ", ".join(results)

# --- Orchestrator Logic (Integrated Designer) ---

async def run_studio(user_goal: str, user_image_path: Path = None) -> str:
    print(f"[Studio] 🎬 Supervisor analyzing goal: '{user_goal[:50]}...'")
    
    # 1. Real-World Research
    research_summary = web_research(f"latest trends and data for: {user_goal}")
    
    # 2. Design Strategy Generation
    supervisor_prompt = f"""
    User Goal: {user_goal}
    Latest Research: {research_summary}
    Has User Photo: {"YES" if user_image_path else "NO"}
    
    MISSION: 
    1. Create a professional, CATCHY YouTube thumbnail headline and subtitle.
    2. Create a JSON plan ONLY for the specific assets requested. 
    
    CRITICAL RULES:
    - NO meta-text or design instructions in the JSON.
    - Title should be MAX 4-5 words (Short and high impact).
    - Subtitle should be MAX 2-3 words.
    - If the user asks for "AI Coding", the title should be like "CODING IS DEAD?" or "AI TOOK MY JOB".
    - DO NOT use descriptions like "Use a shocked human expression". 
    
    REQUIRED JSON FORMAT:
    {{
        "report": "Markdown content strategy",
        "tasks": [
            {{ "type": "thumbnail", "title": "CATCHY HEADLINE", "subtitle": "FAST SUBTITLE" }}, 
            {{ "type": "carousel", "slides": [...] }}
        ]
    }}
    """
    
    raw_response = genai_client.generate_content(
        model="gemini-3.1-flash-lite",
        contents=supervisor_prompt,
        system_instruction="Return ONLY pure content JSON. NO design instructions or meta-talk allowed."
    )
    
    try:
        clean_json = raw_response.strip().replace("```json", "").replace("```", "")
        data = json.loads(clean_json)
        report_text = data.get("report", "")
        tasks = data.get("tasks", [])
    except Exception:
        return f"Sir, I failed to structure the design plan. Output: {raw_response[:300]}..."

    production_logs = []
    save_dir = _get_save_dir() / f"Project_{int(time.time())}"
    save_dir.mkdir(parents=True, exist_ok=True)

    for task in tasks:
        t_type = task.get("type")
        if t_type == "thumbnail":
            out = save_dir / "youtube_thumbnail.jpg"
            render_thumbnail(
                task.get("title", "TITLE"), 
                task.get("subtitle", "TECH"), 
                out,
                user_image_path=user_image_path
            )
            production_logs.append(f"- Thumbnail created: {out.name}")
        elif t_type == "carousel":
            slides = task.get("slides", [])
            file_list = create_professional_carousel(slides, save_dir)
            production_logs.append(f"- Carousel created: {len(slides)} slides ({file_list})")

    # Save final strategy
    filename = f"Project_Report_{int(time.time())}.md"
    file_path = save_dir / filename
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"{report_text}\n\n---\n## 📦 PRODUCTION LOGS\n" + "\n".join(production_logs))
        
    return f"Sir, the Content Studio has finished. I have DESIGNED your professional assets using HTML blueprints. Saved to Desktop/JarvisMedia/{save_dir.name}."

def content_studio(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Jarvis Tool: Content Creation Studio (Pure Playwright Designer).
    """
    params = parameters or {}
    goal = params.get("goal", "").strip()
    image_path_raw = params.get("image_path", "").strip()
    
    user_image = None
    if image_path_raw:
        user_image = Path(image_path_raw).resolve()

    if not goal:
        return "Please provide a goal for the content studio."

    if player:
        player.write_log("[Studio] 🧬 Initializing Designer Engine...")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(run_studio(goal, user_image_path=user_image))
        print(f"[Studio] ✅ {result}")
        return result
    except Exception as e:
        error_msg = f"❌ Content Studio failed: {str(e)}"
        print(f"[Studio] {error_msg}")
        return error_msg
