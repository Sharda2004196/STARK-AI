# memory/mem0_memory.py
# Mem0AI integration for JARVIS — semantic long-term memory
# Uses Gemini API (existing key) for embeddings + ChromaDB (local file-based) for storage
# No LLM extraction needed — we use infer=False on all calls

import os
import threading
from pathlib import Path
from typing import Callable


class Mem0Memory:
    """Wrapper around the mem0ai Memory class for JARVIS.
    
    Uses:
    - Embeddings: Gemini API (model: text-embedding-004) — uses existing GOOGLE_API_KEY
    - Vector store: ChromaDB — local file-based, no server needed
    - LLM: Disabled entirely via infer=False
    """

    def __init__(self):
        self._memory = None
        self._enabled = False
        self._lock = threading.Lock()
        self._init_memory()

    def _init_memory(self):
        """Initialize mem0 with Gemini embedder + local ChromaDB."""
        try:
            from mem0 import Memory

            data_dir = str(Path(__file__).resolve().parent / "mem0_data")

            # Read Gemini key from config (same place JARVIS gets it)
            api_key = self._get_gemini_key()
            if not api_key:
                print("[Mem0] ⚠️ Could not read Gemini API key from config/api_keys.json")
                self._enabled = False
                return

            os.environ["GOOGLE_API_KEY"] = api_key

            config = {
                "vector_store": {
                    "provider": "chroma",
                    "config": {
                        "collection_name": "jarvis_memory",
                        "path": data_dir,
                    },
                },
                "embedder": {
                    "provider": "gemini",
                    "config": {
                        "model": "gemini-embedding-2",
                    },
                },
            }
            # Set dummy OpenAI key to prevent default LLM init from failing
            if "OPENAI_API_KEY" not in os.environ:
                os.environ["OPENAI_API_KEY"] = "sk-dummy-placeholder"

            self._memory = Memory.from_config(config)
            self._enabled = True
            print("[Mem0] ✅ Initialized (Gemini embeddings + ChromaDB)")
        except ModuleNotFoundError as e:
            print(f"[Mem0] ⚠️ Missing chromadb package.")
            print(f"[Mem0]   Run: pip install chromadb")
        except Exception as e:
            print(f"[Mem0] ❌ Init failed: {e}")
            print("[Mem0]   JARVIS will continue without semantic memory.")
            self._memory = None
            self._enabled = False

    def _get_gemini_key(self) -> str | None:
        """Load Gemini API key from config/api_keys.json."""
        try:
            config_path = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
            if config_path.exists():
                import json
                data = json.loads(config_path.read_text(encoding="utf-8"))
                return data.get("gemini_api_key")
            return None
        except Exception:
            return None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def store_fact(self, category: str, key: str, value: str):
        """Store an explicit fact extracted from conversation."""
        if not self._enabled or not self._memory:
            return

        if not key.strip() or not value.strip():
            return

        with self._lock:
            try:
                fact = f"{key.replace('_', ' ').title()}: {value}"
                self._memory.add(
                    f"[{category}] {fact}",
                    user_id="stark",
                    agent_id="jarvis",
                    infer=False,  # Skip LLM extraction, store raw
                )
                print(f"[Mem0] 💾 Saved fact: {category}/{key} = {value}")
            except Exception as e:
                print(f"[Mem0] ⚠️ store_fact error: {e}")

    def store_conversation(self, user_text: str, assistant_text: str):
        """Store a conversation turn in mem0 for semantic retrieval."""
        if not self._enabled or not self._memory:
            return

        if not user_text.strip():
            return

        with self._lock:
            try:
                # Store as plain text with infer=False — no LLM extraction needed
                text = user_text.strip()
                if assistant_text.strip():
                    text = f"User: {text}\nJarvis: {assistant_text.strip()}"
                self._memory.add(
                    text,
                    user_id="stark",
                    agent_id="jarvis",
                    infer=False,  # Skip LLM, just embed and store
                )
            except Exception as e:
                print(f"[Mem0] ⚠️ store_conversation error: {e}")

    def get_relevant_memories(self, query: str = "") -> list[str]:
        """Search for semantically relevant memories."""
        if not self._enabled or not self._memory:
            return []

        search_query = query.strip() or "information about the user"
        with self._lock:
            try:
                response = self._memory.search(
                    query=search_query,
                    filters={"user_id": "stark"},
                )
                if not response:
                    return []

                # mem0.search() returns a dict: {"results": [...], "query": "..."}
                # The results list contains dicts with "id", "memory", "score", etc.
                raw_results = response.get("results", response if isinstance(response, list) else [])

                texts = []
                for r in raw_results:
                    if isinstance(r, str):
                        texts.append(r)
                    elif isinstance(r, dict):
                        text = r.get("memory") or r.get("text", "")
                        if text:
                            texts.append(text)
                return texts[:10]  # Limit to 10 most relevant
            except Exception as e:
                print(f"[Mem0] ⚠️ search error: {e}")
                return []

    def get_all_memories(self) -> list[str]:
        """Get all stored memories for the user."""
        if not self._enabled or not self._memory:
            return []

        with self._lock:
            try:
                response = self._memory.get_all(filters={"user_id": "stark"})
                if not response:
                    return []

                # get_all may return a dict with "results" key or a list directly
                raw_results = response.get("results", response if isinstance(response, list) else [])

                texts = []
                for r in raw_results:
                    if isinstance(r, str):
                        texts.append(r)
                    elif isinstance(r, dict):
                        text = r.get("memory") or r.get("text", "")
                        if text:
                            texts.append(text)
                return texts
            except Exception as e:
                print(f"[Mem0] ⚠️ get_all error: {e}")
                return []

    def format_memories_for_prompt(self, memories: list[str]) -> str:
        """Format retrieved memories into a prompt-friendly string."""
        if not memories:
            return ""

        lines = ["[RELEVANT MEMORIES FROM PAST CONVERSATIONS]"]
        for mem in memories:
            lines.append(f"  • {mem}")
        lines.append("")
        return "\n".join(lines)

    def close(self):
        """Cleanup resources. Call on JARVIS shutdown."""
        with self._lock:
            self._memory = None
            self._enabled = False
        print("[Mem0] 🔒 Closed")
