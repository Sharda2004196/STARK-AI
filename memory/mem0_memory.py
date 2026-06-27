# memory/mem0_memory.py
# Mem0AI integration for JARVIS — semantic long-term memory
# Uses Gemini API (existing key) for embeddings + ChromaDB (local file-based) for storage
# No LLM extraction needed — we use infer=False on all calls
#
# V2 improvements:
#   - JSON backup file for ALL facts (immune to ChromaDB corruption)
#   - Unicode-safe text sanitization (prevents Rust serialization bugs)
#   - Startup health check + auto-recovery from backup
#   - ALL facts included in prompt when ≤ 50 (no more lost via top-10 ceiling)
#   - Conversation turns stored in backup only (reduces ChromaDB corruption surface)

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path


# ── Unicode Sanitizer ─────────────────────────────────────────────────────────
# ChromaDB's Rust-based storage can corrupt on certain complex Unicode sequences.
# This sanitizer strips/replaces characters known to trigger serialization bugs
# while preserving readability.

_SUSPECT_RE = re.compile(
    r"[\u0000-\u0008\u000b\u000c\u000e-\u001f"  # control chars (except tab/newline)
    r"\ufffe\uffff"                               # non-characters
    r"\ufdd0-\ufdef"                              # non-characters
    r"\u2028\u2029"                               # line/paragraph separators
    r"\u200b-\u200f\u202a-\u202f\u2060-\u2064"    # zero-width / invisible / bidi
    r"\ufe00-\ufe0f"                               # variation selectors
    r"\u0300-\u036f]"                              # combining diacriticals (safe but can cause issues)
)


def _sanitize_text(text: str) -> str:
    """Remove or replace characters known to cause Rust/ChromaDB serialization issues."""
    if not text:
        return text
    # Step 1: strip suspect characters
    text = _SUSPECT_RE.sub("", text)
    # Step 2: normalize Unicode (NFC composes where possible — reduces variability)
    import unicodedata
    text = unicodedata.normalize("NFC", text)
    # Step 3: collapse repeated whitespace
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text


# ── JSON Backup Layer ─────────────────────────────────────────────────────────
# Two separate files for durability:
#   facts_backup.json         — user facts only (small, permanently important)
#   conversations_backup.json — conversation turns (can grow, pruned at 200)

_BACKUP_DIR = Path(__file__).resolve().parent
_FACTS_PATH = _BACKUP_DIR / "facts_backup.json"
_CONVO_PATH = _BACKUP_DIR / "conversations_backup.json"

# Module-level lock for ALL backup file writes (prevents TOCTOU race)
_backup_lock = threading.Lock()


def _atomic_write_json(path: Path, data):
    """Write JSON to a file atomically: write .tmp then os.replace.
    
    This prevents corruption if the process crashes mid-write.
    os.replace is atomic on Windows (same filesystem).
    """
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)  # atomic on Windows


def _read_json(path: Path) -> list[dict]:
    """Read a JSON list from file. Returns [] on missing/corrupt."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return []
    except (json.JSONDecodeError, OSError) as e:
        print(f"[Mem0] ⚠️ Read error ({path.name}): {e}")
        return []


def _append_fact_backup(fact: dict):
    """Append one user-fact dict to facts_backup.json (thread-safe via module lock)."""
    with _backup_lock:
        try:
            existing = _read_json(_FACTS_PATH)
            existing.append(fact)
            _atomic_write_json(_FACTS_PATH, existing)
        except OSError as e:
            print(f"[Mem0] ⚠️ Fact backup write error: {e}")


def _append_conversation_backup(turn: dict):
    """Append a conversation turn to conversations_backup.json, then prune to max 200."""
    with _backup_lock:
        try:
            existing = _read_json(_CONVO_PATH)
            existing.append(turn)
            # Prune oldest turns when over 200
            if len(existing) > 200:
                existing = existing[-200:]
            _atomic_write_json(_CONVO_PATH, existing)
        except OSError as e:
            print(f"[Mem0] ⚠️ Conversation backup write error: {e}")


# ── Memory Class ──────────────────────────────────────────────────────────────

class Mem0Memory:
    """Wrapper around the mem0ai Memory class for JARVIS.
    
    Architecture (V2 — resilient):
      ┌──────────────────────────────────────────────────┐
      │  ChromaDB  ←── semantic search, may lose data     │
      │                                                   │
      │  facts_backup.json  ←── always complete            │
      │  (auto-recovered into ChromaDB on startup)         │
      └──────────────────────────────────────────────────┘
    
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
        """Initialize mem0 with Gemini embedder + local ChromaDB, then health-check."""
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

            # ── Health check + auto-recovery ───────────────────────────
            self._health_check_and_recover()

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
                data = json.loads(config_path.read_text(encoding="utf-8"))
                return data.get("gemini_api_key")
            return None
        except Exception:
            return None

    # ── Health check & recovery (V3: hash-based) ───────────────────────────────
    #
    # Root cause of the recurring-recovery bug (V2):
    #   mem0's get_all() has a default top_k=20, which internally fetches only
    #   the oldest 80 records (fetch_limit = max(20*4, 60) = 80). ChromaDB has
    #   ~75 old conversation entries (from before V2) that occupy those 80 slots,
    #   so only 5 original facts were visible. Recovery added 11 more facts, but
    #   they were the "newest" records — beyond the 80-record window. Next startup,
    #   the same 5 facts were found, recovery ran again, and duplicates accumulated
    #   endlessly.
    #
    # V3 fix: compute an MD5 hash of the backup file and store it. Recovery runs
    #   ONLY when the backup actually changes (new fact added/deleted). This is
    #   immune to the top_k counting bug, immune to ChromaDB corruption, and
    #   produces zero duplicate accumulation.

    def _health_check_and_recover(self):
        """Hash-based recovery check. Only re-imports when backup file actually changes."""
        if not self._enabled or not self._memory:
            return

        backup_facts = _read_json(_FACTS_PATH)
        if not backup_facts:
            print("[Mem0] ℹ️  No backup facts to verify.")
            return

        # Compute hash of current backup content
        backup_hash = hashlib.md5(
            json.dumps(backup_facts, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

        # Check if we already recovered for this exact backup state
        marker_path = _BACKUP_DIR / ".recovery_hash"

        if marker_path.exists():
            prev_hash = marker_path.read_text().strip()
            if prev_hash == backup_hash:
                print(f"[Mem0] ✅ Health check passed ({len(backup_facts)} facts, backup unchanged)")
                return

        # Backup has changed (or first run) — run recovery
        print(f"[Mem0] 🔄 Backup changed — syncing {len(backup_facts)} facts to ChromaDB...")
        self._recover_from_backup(backup_facts)

        # Save hash marker so we don't recover again for the same backup state
        # Note: if ChromaDB is manually reset (e.g. deleting mem0_data/), delete
        # the .recovery_hash file to force a fresh re-import on next startup.
        try:
            marker_path.write_text(backup_hash)
        except OSError as e:
            print(f"[Mem0] ⚠️ Could not save recovery marker: {e}")

    def _recover_from_backup(self, facts: list[dict]):
        """Clear ChromaDB for this user, then re-import all facts from backup.

        Deletes ALL existing records in ChromaDB for user 'stark' first (to prevent
        the duplicate accumulation that plagued V2), then fresh-imports every fact
        from the backup file.
        """
        if not self._enabled or not self._memory:
            return

        # ── Step 1: Delete all existing ChromaDB records for this user ───
        try:
            existing = self._memory.get_all(filters={"user_id": "stark"}, top_k=10000)
            if existing:
                raw = existing.get("results", existing if isinstance(existing, list) else [])
                ids_to_delete = [r["id"] for r in raw if isinstance(r, dict) and r.get("id")]
                if ids_to_delete:
                    for mid in ids_to_delete:
                        try:
                            self._memory.delete(mid)
                        except Exception:
                            pass  # swallow per-item errors
                    print(f"[Mem0] 🗑️ Cleared {len(ids_to_delete)} existing records from ChromaDB")
        except Exception as e:
            print(f"[Mem0] ⚠️ Could not clear ChromaDB (continuing with re-import): {e}")

        # ── Step 2: Fresh-import all facts from backup ───────────────────
        imported = 0
        for fact in facts:
            try:
                cat = fact.get("category", "notes")
                key = fact.get("key", "")
                val = fact.get("value", "")
                if not key or not val:
                    continue
                if cat == "conversation":
                    continue  # skip conversation turns (stored in separate file)

                fact_text = f"[{cat}] {key.replace('_', ' ').title()}: {val}"
                safe_text = _sanitize_text(fact_text)

                self._memory.add(
                    safe_text,
                    user_id="stark",
                    agent_id="jarvis",
                    infer=False,
                )
                imported += 1
            except Exception as e:
                print(f"[Mem0] ⚠️ Recovery import error ({fact.get('key', '?')}): {e}")

        print(f"[Mem0] ✅ Recovery complete — imported {imported}/{len(facts)} facts")

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ── Store fact (primary: ChromaDB + JSON backup) ─────────────────────────

    def store_fact(self, category: str, key: str, value: str):
        """Store an explicit fact extracted from conversation.
        
        Writes to BOTH ChromaDB (for semantic search) and JSON backup (durable).
        """
        if not key.strip() or not value.strip():
            return

        # Sanitize text before storing anywhere
        safe_category = _sanitize_text(category)
        safe_key = _sanitize_text(key)
        safe_value = _sanitize_text(value)

        # Always write to JSON backup first (most reliable)
        fact_record = {
            "category": safe_category,
            "key": safe_key,
            "value": safe_value,
            "stored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        _append_fact_backup(fact_record)

        # Then try ChromaDB
        if not self._enabled or not self._memory:
            print(f"[Mem0] 💾 Saved fact to backup only (ChromaDB offline): {safe_category}/{safe_key} = {safe_value}")
            return

        with self._lock:
            try:
                fact_text = f"[{safe_category}] {safe_key.replace('_', ' ').title()}: {safe_value}"
                self._memory.add(
                    fact_text,
                    user_id="stark",
                    agent_id="jarvis",
                    infer=False,
                )
                print(f"[Mem0] 💾 Saved fact: {safe_category}/{safe_key} = {safe_value}")
            except Exception as e:
                print(f"[Mem0] ⚠️ store_fact error (backup saved): {e}")

    # ── Store conversation (backup only, no ChromaDB — reduces corruption risk) ─

    def store_conversation(self, user_text: str, assistant_text: str):
        """Store a conversation turn.
        
        V2 change: stored in conversations_backup.json ONLY (not ChromaDB).
        Conversation turns are high-volume and often contain complex Unicode,
        which was the root cause of ChromaDB corruption. The backup file handles
        them safely, and recent turns are included in the system prompt.
        """
        if not user_text.strip():
            return

        safe_user = _sanitize_text(user_text.strip())
        safe_assistant = _sanitize_text(assistant_text.strip()) if assistant_text.strip() else ""

        # Truncate very long conversations
        if len(safe_user) > 2000:
            safe_user = safe_user[:2000] + " […]"
        if len(safe_assistant) > 2000:
            safe_assistant = safe_assistant[:2000] + " […]"

        turn_record = {
            "category": "conversation",
            "value": f"User: {safe_user}" + (f"\nJarvis: {safe_assistant}" if safe_assistant else ""),
            "stored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        _append_conversation_backup(turn_record)

    # ── Retrieval ─────────────────────────────────────────────────────────────

    def get_relevant_memories(self, query: str = "") -> list[str]:
        """Get ALL stored facts + semantically relevant ChromaDB memories.
        
        Returns:
            - ALL user facts from facts_backup.json (up to 50)
            - Recent conversation turns from conversations_backup.json (last 3)
            - Plus any additional context from ChromaDB semantic search
        Combined and deduplicated.
        """
        combined: list[str] = []

        # ── 1. Always start with ALL facts from facts_backup.json ────────
        facts_data = _read_json(_FACTS_PATH)
        seen = set()
        for fact in facts_data:
            cat = fact.get("category", "")
            key = fact.get("key", "")
            val = fact.get("value", "")
            if cat == "conversation":
                continue  # conversations are in a separate file now
            if key and val:
                text = f"{key.replace('_', ' ').title()}: {val}"
                dedup_key = text.lower().strip()
                if dedup_key not in seen:
                    seen.add(dedup_key)
                    combined.append(text)

        # ── 2. Also add recent conversation turns (last 3 from separate file) ─
        convo_data = _read_json(_CONVO_PATH)
        conv_count = 0
        for turn in reversed(convo_data):
            val = turn.get("value", "")
            if val:
                combined.append(val)
                conv_count += 1
                if conv_count >= 3:
                    break

        # ── 3. Supplement with ChromaDB semantic search if available ────
        if self._enabled and self._memory:
            search_query = query.strip() or "information about the user"
            with self._lock:
                try:
                    response = self._memory.search(
                        query=search_query,
                        filters={"user_id": "stark"},
                    )
                    if response:
                        raw_results = response.get(
                            "results",
                            response if isinstance(response, list) else [],
                        )
                        for r in raw_results:
                            text = ""
                            if isinstance(r, str):
                                text = r
                            elif isinstance(r, dict):
                                text = r.get("memory") or r.get("text", "")
                            if text:
                                dedup_key = text.lower().strip()
                                if dedup_key not in seen:
                                    seen.add(dedup_key)
                                    combined.append(text)
                except Exception as e:
                    print(f"[Mem0] ⚠️ search error (falling back to backup only): {e}")

        return combined[:50]  # generous cap — most users have < 50 facts

    def get_all_memories(self) -> list[str]:
        """Get ALL stored user facts (non-conversation) from facts_backup.json.
        
        ChromaDB is NOT used as primary source because of known corruption issues.
        The JSON backup is always the complete source of truth.
        """
        texts: list[str] = []

        facts_data = _read_json(_FACTS_PATH)
        seen = set()
        for fact in facts_data:
            cat = fact.get("category", "")
            key = fact.get("key", "")
            val = fact.get("value", "")
            if cat == "conversation":
                continue
            if key and val:
                text = f"[{cat}] {key.replace('_', ' ').title()}: {val}"
                dedup_key = text.lower().strip()
                if dedup_key not in seen:
                    seen.add(dedup_key)
                    texts.append(text)

        return texts

    # ── Formatting ────────────────────────────────────────────────────────────

    def format_memories_for_prompt(self, memories: list[str]) -> str:
        """Format retrieved memories into a prompt-friendly string."""
        if not memories:
            return ""

        lines = ["[RELEVANT MEMORIES FROM PAST CONVERSATIONS]"]
        for mem in memories:
            lines.append(f"  • {mem}")
        lines.append("")
        return "\n".join(lines)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def close(self):
        """Cleanup resources. Call on JARVIS shutdown."""
        with self._lock:
            self._memory = None
            self._enabled = False
        print("[Mem0] 🔒 Closed")
