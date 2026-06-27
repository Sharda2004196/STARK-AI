# actions/notebooklm.py
# NotebookLM integration for JARVIS via notebooklm-py (unofficial API)
# Provides programmatic access to Google NotebookLM for research,
# content generation, and grounded AI-powered knowledge management.

import asyncio
import os
import time
from pathlib import Path
from typing import Optional

_NOTEBOOKLM_OK = False
try:
    from notebooklm import NotebookLMClient, RPCError, MindMapKind
    from notebooklm import (
        NotebookNotFoundError,
        SourceNotFoundError,
        ArtifactNotFoundError,
        WaitTimeoutError,
    )
    from notebooklm.types import (
        VideoFormat,
        QuizDifficulty,
        QuizQuantity,
        ReportFormat,
        InfographicOrientation,
        InfographicDetail,
    )
    _NOTEBOOKLM_OK = True
except ImportError:
    pass

# ── Helpers ────────────────────────────────────────────────────────────────────


def _get_storage_path() -> Optional[str]:
    """Check for existing NotebookLM auth. Returns path or None."""
    home = Path.home() / ".notebooklm"
    candidates = [
        home / "profiles" / "default" / "storage_state.json",
        home / "storage_state.json",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def _fmt_notebooks(notebooks: list) -> str:
    lines = [f"Found {len(notebooks)} notebook(s):"]
    for nb in notebooks:
        title = getattr(nb, "title", getattr(nb, "name", "Untitled"))
        nid = getattr(nb, "id", "?")
        lines.append(f"  📓 {title}  ({nid})")
    return "\n".join(lines)


def _fmt_sources(sources: list) -> str:
    lines = [f"Sources ({len(sources)}):"]
    for src in sources:
        display = getattr(src, "display_name", getattr(src, "title", getattr(src, "url", "?")))
        sid = getattr(src, "id", "?")
        lines.append(f"  📄 {display}  ({sid})")
    return "\n".join(lines)


def _fmt_artifacts(artifacts: list) -> str:
    lines = [f"Artifacts ({len(artifacts)}):"]
    for art in artifacts:
        kind = getattr(art, "kind", getattr(art, "type", "?"))
        aid = getattr(art, "id", "?")
        lines.append(f"  🎨 {kind}  ({aid})")
    return "\n".join(lines)


async def _run_client_action(action: str, params: dict) -> str:
    """Execute a NotebookLM action inside an async client context."""
    storage_path = _get_storage_path()
    if not storage_path:
        return (
            "NotebookLM is not authenticated, sir. "
            "Please run 'notebooklm login' in your terminal first to sign in with your Google account."
        )

    async with NotebookLMClient.from_storage(storage_path) as client:

        # ── Notebook operations ────────────────────────────────────────────

        if action == "list_notebooks":
            nbs = await client.notebooks.list()
            if not nbs:
                return "No notebooks found. Create one with 'create_notebook'."
            return _fmt_notebooks(nbs)

        elif action == "create_notebook":
            title = params.get("title", "JARVIS Notebook")
            nb = await client.notebooks.create(title)
            return f"Notebook created: {getattr(nb, 'title', title)}  ({nb.id})"

        elif action == "delete_notebook":
            nb_id = params.get("notebook_id", "")
            if not nb_id:
                return "Please provide a notebook_id."
            await client.notebooks.delete(nb_id)
            return f"Notebook deleted: {nb_id}"

        elif action == "get_notebook":
            nb_id = params.get("notebook_id", "")
            if not nb_id:
                return "Please provide a notebook_id."
            try:
                nb = await client.notebooks.get(nb_id)
                title = getattr(nb, "title", getattr(nb, "name", "?"))
                return f"Notebook: {title}  ({nb.id})"
            except NotebookNotFoundError:
                return f"Notebook not found: {nb_id}"

        # ── Source operations ───────────────────────────────────────────────

        elif action == "add_source_url":
            nb_id = params.get("notebook_id", "")
            url = params.get("url", "")
            if not nb_id or not url:
                return "Please provide a notebook_id and url."
            src = await client.sources.add_url(nb_id, url, wait=True)
            display = getattr(src, "display_name", getattr(src, "title", url))
            return f"Source added: {display}"

        elif action == "add_source_file":
            nb_id = params.get("notebook_id", "")
            path = params.get("file_path", "")
            if not nb_id or not path:
                return "Please provide a notebook_id and file_path."
            if not os.path.exists(path):
                return f"File not found: {path}"
            src = await client.sources.add_file(nb_id, path, wait=True)
            display = getattr(src, "display_name", getattr(src, "title", Path(path).name))
            return f"Source added: {display}"

        elif action == "add_source_text":
            nb_id = params.get("notebook_id", "")
            title = params.get("title", "Pasted text")
            content = params.get("content", "")
            if not nb_id or not content:
                return "Please provide a notebook_id and content."
            src = await client.sources.add_text(nb_id, title, content)
            return f"Text source added: {title}"

        elif action == "add_web_research":
            nb_id = params.get("notebook_id", "")
            query = params.get("query", "")
            mode = params.get("mode", "fast")  # fast or deep
            if not nb_id or not query:
                return "Please provide a notebook_id and query."
            # Use research.start() (not add_research — that method doesn't exist)
            task = await client.research.start(nb_id, query, source="web", mode=mode)
            result = await client.research.wait_for_completion(nb_id, task.task_id, timeout=1800)
            if result.status == "completed":
                return f"Research complete for: {query}. Found {len(result.sources)} source(s)."
            elif result.status == "failed":
                return f"Research failed for: {query}. Try a different query or check if your sources are accessible."
            else:
                return f"Research finished with status: {result.status}. Try again with a different query."

        elif action == "list_sources":
            nb_id = params.get("notebook_id", "")
            if not nb_id:
                return "Please provide a notebook_id."
            sources = await client.sources.list(nb_id)
            return _fmt_sources(sources)

        # ── Chat ────────────────────────────────────────────────────────────

        elif action == "ask":
            nb_id = params.get("notebook_id", "")
            query = params.get("query", "")
            if not nb_id or not query:
                return "Please provide a notebook_id and query."
            result = await client.chat.ask(nb_id, query)
            answer = getattr(result, "answer", str(result))
            if len(answer) > 800:
                answer = answer[:800] + "... (truncated)"
            return answer

        # ── Content Generation ──────────────────────────────────────────────

        elif action == "generate_audio":
            nb_id = params.get("notebook_id", "")
            instructions = params.get("instructions", "")
            if not nb_id:
                return "Please provide a notebook_id."
            status = await client.artifacts.generate_audio(nb_id, instructions=instructions)
            await client.artifacts.wait_for_completion(nb_id, status.task_id, timeout=1200)
            return f"Audio overview generated successfully (task: {status.task_id})"

        elif action == "generate_video":
            nb_id = params.get("notebook_id", "")
            instructions = params.get("instructions", "")
            style = params.get("style", "explainer")  # explainer, brief, cinematic
            if not nb_id:
                return "Please provide a notebook_id."
            # Map string style to VideoFormat enum
            fmt_map = {"explainer": VideoFormat.EXPLAINER, "brief": VideoFormat.BRIEF, "cinematic": VideoFormat.CINEMATIC}
            vf = fmt_map.get(style.lower(), VideoFormat.EXPLAINER)
            status = await client.artifacts.generate_video(nb_id, instructions=instructions, video_format=vf)
            await client.artifacts.wait_for_completion(nb_id, status.task_id, timeout=1800)
            return f"Video overview generated successfully (task: {status.task_id})"

        elif action == "generate_cinematic_video":
            nb_id = params.get("notebook_id", "")
            instructions = params.get("instructions", "")
            if not nb_id:
                return "Please provide a notebook_id."
            status = await client.artifacts.generate_cinematic_video(nb_id, instructions=instructions)
            await client.artifacts.wait_for_completion(nb_id, status.task_id, timeout=3600)
            return f"Cinematic video generated successfully (task: {status.task_id})"

        elif action == "generate_quiz":
            nb_id = params.get("notebook_id", "")
            difficulty = params.get("difficulty", "medium").lower()  # easy, medium, hard
            quantity = params.get("quantity", 5)
            if not nb_id:
                return "Please provide a notebook_id."
            # Map to QuizDifficulty enum
            diff_map = {"easy": QuizDifficulty.EASY, "medium": QuizDifficulty.MEDIUM, "hard": QuizDifficulty.HARD}
            qd = diff_map.get(difficulty, QuizDifficulty.MEDIUM)
            # Map quantity to QuizQuantity enum
            qq = QuizQuantity.STANDARD if int(quantity) > 8 else QuizQuantity.FEWER
            status = await client.artifacts.generate_quiz(nb_id, difficulty=qd, quantity=qq)
            await client.artifacts.wait_for_completion(nb_id, status.task_id)
            return f"Quiz generated with {quantity} questions (difficulty: {difficulty})"

        elif action == "generate_flashcards":
            nb_id = params.get("notebook_id", "")
            quantity = params.get("quantity", 10)
            if not nb_id:
                return "Please provide a notebook_id."
            qq = QuizQuantity.STANDARD if int(quantity) > 8 else QuizQuantity.FEWER
            status = await client.artifacts.generate_flashcards(nb_id, quantity=qq)
            await client.artifacts.wait_for_completion(nb_id, status.task_id)
            return f"{quantity} flashcards generated"

        elif action == "generate_slide_deck":
            nb_id = params.get("notebook_id", "")
            instructions = params.get("instructions", "")
            if not nb_id:
                return "Please provide a notebook_id."
            status = await client.artifacts.generate_slide_deck(nb_id, instructions=instructions)
            await client.artifacts.wait_for_completion(nb_id, status.task_id)
            return f"Slide deck generated (task: {status.task_id})"

        elif action == "generate_report":
            nb_id = params.get("notebook_id", "")
            format_type = params.get("format", "briefing-doc")  # briefing-doc, study-guide, blog-post, custom
            instructions = params.get("instructions", "")
            if not nb_id:
                return "Please provide a notebook_id."
            # Map string to ReportFormat enum (supports both hyphen and underscore variants)
            fmt_key = format_type.lower().replace("-", "_")
            fmt_map = {
                "briefing_doc": ReportFormat.BRIEFING_DOC,
                "study_guide": ReportFormat.STUDY_GUIDE,
                "blog_post": ReportFormat.BLOG_POST,
                "custom": ReportFormat.CUSTOM,
            }
            rf = fmt_map.get(fmt_key, ReportFormat.BRIEFING_DOC)
            status = await client.artifacts.generate_report(nb_id, report_format=rf, extra_instructions=instructions)
            await client.artifacts.wait_for_completion(nb_id, status.task_id)
            return f"Report generated (format: {format_type})"

        elif action == "generate_infographic":
            nb_id = params.get("notebook_id", "")
            orientation = params.get("orientation", "landscape").lower()  # landscape, portrait, square
            detail = params.get("detail", "medium").lower()  # low/concise, medium/standard, high/detailed
            if not nb_id:
                return "Please provide a notebook_id."
            # Map to InfographicOrientation enum
            ori_map = {"landscape": InfographicOrientation.LANDSCAPE, "portrait": InfographicOrientation.PORTRAIT, "square": InfographicOrientation.SQUARE}
            io = ori_map.get(orientation, InfographicOrientation.LANDSCAPE)
            # Map detail to InfographicDetail enum
            det_map = {"low": InfographicDetail.CONCISE, "concise": InfographicDetail.CONCISE, "medium": InfographicDetail.STANDARD, "standard": InfographicDetail.STANDARD, "high": InfographicDetail.DETAILED, "detailed": InfographicDetail.DETAILED}
            detail_enum = det_map.get(detail, InfographicDetail.STANDARD)
            status = await client.artifacts.generate_infographic(nb_id, orientation=io, detail_level=detail_enum)
            await client.artifacts.wait_for_completion(nb_id, status.task_id)
            return f"Infographic generated (orientation: {orientation})"

        elif action == "generate_data_table":
            nb_id = params.get("notebook_id", "")
            instructions = params.get("instructions", "")
            if not nb_id:
                return "Please provide a notebook_id."
            status = await client.artifacts.generate_data_table(nb_id, instructions=instructions)
            await client.artifacts.wait_for_completion(nb_id, status.task_id)
            return f"Data table generated"

        elif action == "generate_mind_map":
            nb_id = params.get("notebook_id", "")
            kind = params.get("kind", "interactive")  # interactive or note-backed
            if not nb_id:
                return "Please provide a notebook_id."
            mk = MindMapKind.INTERACTIVE if kind == "interactive" else MindMapKind.NOTE_BACKED
            await client.mind_maps.generate(nb_id, kind=mk)
            return f"Mind map generated (kind: {kind})"

        # ── Download ────────────────────────────────────────────────────────

        elif action == "download":
            nb_id = params.get("notebook_id", "")
            artifact_type = params.get("artifact_type", "audio")  # audio, video, quiz, flashcards, slide-deck, infographic, mind-map, report, data-table
            output_path = params.get("output_path", "")
            fmt = params.get("format", "json")  # for quiz/flashcards: json, markdown, html
            if not nb_id:
                return "Please provide a notebook_id."
            if not output_path:
                out_dir = Path.cwd() / "notebooklm_downloads"
                out_dir.mkdir(exist_ok=True)
                output_path = str(out_dir / f"{artifact_type}_{int(time.time())}")

            download_map = {
                "audio": lambda: client.artifacts.download_audio(nb_id, output_path),
                "video": lambda: client.artifacts.download_video(nb_id, output_path),
                "quiz": lambda: client.artifacts.download_quiz(nb_id, output_path, output_format=fmt),
                "flashcards": lambda: client.artifacts.download_flashcards(nb_id, output_path, output_format=fmt),
                "slide-deck": lambda: client.artifacts.download_slide_deck(nb_id, output_path),
                "infographic": lambda: client.artifacts.download_infographic(nb_id, output_path),
                "report": lambda: client.artifacts.download_report(nb_id, output_path),
                "mind-map": lambda: client.artifacts.download_mind_map(nb_id, output_path),
                "data-table": lambda: client.artifacts.download_data_table(nb_id, output_path),
            }

            fn = download_map.get(artifact_type)
            if not fn:
                return f"Unknown artifact type: {artifact_type}. Supported: {', '.join(download_map.keys())}"
            result_path = await fn()
            return f"Downloaded {artifact_type} to: {result_path}"

        elif action == "list_artifacts":
            nb_id = params.get("notebook_id", "")
            if not nb_id:
                return "Please provide a notebook_id."
            artifacts = await client.artifacts.list(nb_id)
            return _fmt_artifacts(artifacts)

        elif action == "status":
            nbs = await client.notebooks.list()
            return (
                f"NotebookLM is authenticated. {len(nbs)} notebook(s) available."
            )

        else:
            return f"Unknown action: '{action}'. See tool description for available actions."


# ── Sync entry point (called by Jarvis tool router) ────────────────────────────


def notebooklm_controller(parameters: dict = None, player=None, speak=None) -> str:
    """
    JARVIS tool entry point for NotebookLM operations.

    Parameters:
        action (str): The operation to perform.

    Notebook operations:
        - list_notebooks
        - create_notebook (title)
        - delete_notebook (notebook_id)
        - get_notebook (notebook_id)

    Source operations:
        - add_source_url (notebook_id, url)
        - add_source_file (notebook_id, file_path)
        - add_source_text (notebook_id, title, content)
        - add_web_research (notebook_id, query, mode=fast|deep)
        - list_sources (notebook_id)

    Chat:
        - ask (notebook_id, query)

    Content generation:
        - generate_audio (notebook_id, instructions)
        - generate_video (notebook_id, instructions, style)
        - generate_cinematic_video (notebook_id, instructions)
        - generate_quiz (notebook_id, difficulty, quantity)
        - generate_flashcards (notebook_id, quantity)
        - generate_slide_deck (notebook_id, instructions)
        - generate_report (notebook_id, format, instructions)
        - generate_infographic (notebook_id, orientation, detail)
        - generate_data_table (notebook_id, instructions)
        - generate_mind_map (notebook_id, kind)

    Download:
        - download (notebook_id, artifact_type, output_path, format)

    Utilities:
        - list_artifacts (notebook_id)
        - status
    """
    if not _NOTEBOOKLM_OK:
        return (
            "NotebookLM library is not installed, sir. "
            "Please run: pip install notebooklm-py"
        )

    params = parameters or {}
    action = params.get("action", "").strip().lower()

    if not action:
        return "Please specify an action. See tool description for available actions."

    if player:
        player.write_log(f"[NotebookLM] Action: {action}")

    try:
        result = asyncio.run(_run_client_action(action, params))
        return result
    except NotebookNotFoundError:
        return f"Notebook not found. Please check the notebook_id and try again."
    except SourceNotFoundError:
        return "Source not found in the notebook."
    except ArtifactNotFoundError:
        return "Artifact not found. It may have been deleted or not yet generated."
    except WaitTimeoutError:
        return (
            "The operation timed out. Generation tasks can take a while — "
            "try a shorter or simpler request."
        )
    except RPCError as e:
        return f"NotebookLM API error: {e}"
    except Exception as e:
        err = str(e)
        if player:
            player.write_log(f"[NotebookLM] ❌ {err}")
        return f"NotebookLM action failed: {err}"
