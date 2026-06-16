import os
import re
import sys
import time
from pathlib import Path
from config.genai_client import generate_content

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
PROMPTS_DIR = Path.home() / "Desktop" / "JarvisOptimizedPrompts"

def prompt_optimizer(parameters: dict, player=None, speak=None) -> str:
    """
    Optimizes vague, raw, or multilingual user requests into highly specialized prompts.
    Parameters:
        raw_request: The original request in any language (e.g., Hindi, raw English)
        target_tool: "image", "frontend", "code", or "general" (optional)
    """
    raw_request = parameters.get("raw_request", "")
    target_tool = parameters.get("target_tool", "general")
    
    if not raw_request:
        return "Please provide a request to optimize, sir."

    if player:
        player.write_log(f"Optimizing prompt for {target_tool}...")

    # Specialized Prompt Engineering System Prompt
    system_instruction = f"""You are a Master Prompt Engineer and AI Architect.
Your goal is to take raw, vague, or multilingual user inputs and transform them into "high-fidelity, exhaustive, and highly specialized" prompts that will produce world-class results from AI models.

RULES:
1. Translate to English: If the input is in Hindi or any other language, translate the intent to professional English.
2. Exhaustive Detail: For complex tasks (like frontend or code), generate a HUGE, highly detailed prompt. Leave no ambiguity. 
3. Structure: 
   - For 'image': Focus on resolution, style (cinematic, photorealistic), lighting, and camera angle.
   - For 'frontend': Provide an exhaustive breakdown of UI/UX principles, themes, color palettes, functional sections, routing, and specific libraries (GSAP, Three.js).
   - For 'code': Define architecture, edge cases, best practices, and error handling in meticulous detail.
4. Output: Return ONLY the optimized prompt text. No conversational filler.

RAW REQUEST: {raw_request}
TARGET TOOL: {target_tool}
"""

    try:
        optimized_prompt = generate_content(
            model="gemini-3.1-flash-lite",
            contents=f"Optimize this request for {target_tool}: {raw_request}",
            config={"system_instruction": system_instruction}
        )
        
        optimized_prompt = optimized_prompt.strip()
        
        # Save to Desktop
        PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^\w\-]", "_", raw_request[:20]).lower() or "optimized_prompt"
        file_path = PROMPTS_DIR / f"{safe_name}_{int(time.time())}.txt"
        
        file_path.write_text(optimized_prompt, encoding="utf-8")
        
        # Auto-open the text file
        try:
            os.startfile(file_path)
        except Exception:
            pass

        # Return a concise message WITHOUT the prompt snippet so the voice model doesn't read it aloud.
        msg = f"Prompt optimized, sir. I have engineered a highly detailed, professional version and saved it securely to your Desktop ({PROMPTS_DIR.name}). It is now open on your screen."
        return msg

    except Exception as e:
        error_msg = f"Prompt optimization failed: {e}"
        print(f"[PromptOptimizer] {error_msg}")
        return error_msg
