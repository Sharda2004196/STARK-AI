import os
import re
import sys
from pathlib import Path
from config.genai_client import generate_content

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
EXTENSIONS_DIR = Path.home() / "Desktop" / "JarvisExtensions"

def extension_builder(parameters: dict, player=None, speak=None) -> str:
    """
    Architects and generates source code for a Chrome/Edge extension.
    """
    extension_name = parameters.get("extension_name", "JarvisExtension")
    features = parameters.get("features", "")
    
    if not features:
        return "Please provide a description of the extension features, sir."

    safe_name = re.sub(r"[^\w\-]", "", extension_name).lower()
    project_dir = EXTENSIONS_DIR / safe_name
    
    if player:
        player.write_log(f"Architecting Browser Extension: {extension_name}...")

    os.makedirs(project_dir, exist_ok=True)
    
    system_instruction = """You are an Expert Browser Extension Developer.
Generate the complete source code for a STANDALONE Chrome/Edge browser extension powered by Google Gemini.

ARCHITECTURAL RULES (Mandatory):
1. NO BACKGROUND SERVER: The extension must talk DIRECTLY to Google Gemini API (generativelanguage.googleapis.com).
2. SETTINGS UI: 'popup.html' MUST include a hidden or toggleable settings section where the user can paste their Gemini API key.
3. PERSISTENCE: Use 'chrome.storage.local' to save/load the API key.
4. DIRECT API CALL: 'background.js' must fetch the key from storage and use 'fetch()' to call the Gemini 1.5 Flash endpoint.

FILE STRUCTURE:
You MUST wrap the content of EACH file in XML tags like this:
<file name="manifest.json">
{ "permissions": ["storage"], "host_permissions": ["https://generativelanguage.googleapis.com/*"], ... }
</file>
<file name="popup.html">
<!-- Must include inputs for task and settings for API key -->
</file>
<file name="popup.js">
<!-- Handle UI, storage of key, and messaging background.js -->
</file>
<file name="background.js">
<!-- Async listener that performs the fetch() to Gemini -->
</file>

Rules:
- ALWAYS use Manifest V3.
- Use 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=' as the API URL.
- Do NOT include markdown fences inside the XML tags.
- Provide production-ready, clean code."""

    code_prompt = f"Write the code for a browser extension named '{extension_name}'. Features: {features}."

    try:
        if player:
            player.write_log("Generating extension code via OpenCode Zen...")
            
        response = generate_content(
            model="deepseek-v4-flash-free",
            contents=code_prompt,
            config={"system_instruction": system_instruction},
            provider="opencode"
        )
        
        # Extract files using regex
        file_matches = re.findall(r'<file name="(.*?)">\s*(.*?)\s*</file>', response, re.DOTALL | re.IGNORECASE)
        
        if not file_matches:
            if player: player.write_log("Failed to parse XML tags from AI response.")
            return "Failed to parse extension code. The AI did not return the expected file format."
        
        for filename, content in file_matches:
            # Clean up potential markdown fences inside the tags just in case
            content = re.sub(r"^```[a-zA-Z]*\n?", "", content)
            content = re.sub(r"\n?```$", "", content)
            
            # Ensure subdirectories exist if filename contains slashes
            file_path = project_dir / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content.strip(), encoding="utf-8")

        msg = f"SUCCESS: Browser extension '{extension_name}' has been created.\nSaved to: {project_dir}\n\nTo install:\n1. Open Chrome/Edge extensions page\n2. Enable 'Developer Mode'\n3. Click 'Load unpacked'\n4. Select the {safe_name} folder."
        
        if player:
            player.write_log(f"Extension generated: {project_dir}")

        return msg

    except Exception as e:
        error_msg = f"Extension generation failed: {e}"
        print(f"[ExtensionBuilder] {error_msg}")
        if player: player.write_log(f"Error: {error_msg}")
        return error_msg
