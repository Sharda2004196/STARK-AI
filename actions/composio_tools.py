import json
import os
import time
from composio_client import Composio

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

class JarvisToolManager:
    def __init__(self, key_file='config/api_keys.json'):
        self.composio = None
        self.client = None
        self.user_id = "pg-test-d26d0360-6d72-4b9d-81cf-3b8ba86d3d2c"
        self._tool_schemas = []

        try:
            with open(key_file, 'r') as f:
                keys = json.load(f)

            comp_key = None
            for k, v in keys.items():
                if k.lower() in ("composio_api_key", "composio"):
                    comp_key = v
                    break

            opencode_key = None
            for k, v in keys.items():
                if k.lower() == "opencode_api_key":
                    opencode_key = v
                    break

            if not comp_key:
                print("[!] COMPOSIO_API_KEY not found in api_keys.json")
                return

            os.environ["COMPOSIO_API_KEY"] = comp_key
            self.composio = Composio()

            if OpenAI is None:
                print("[!] 'openai' library is required to use OpenCode Zen. Run: pip install openai")
                return

            if opencode_key and opencode_key != "YOUR_OPENCODE_API_KEY":
                self.client = OpenAI(
                    base_url="https://opencode.ai/zen/v1",
                    api_key=opencode_key
                )
            else:
                print("[!] opencode_api_key not found or invalid in api_keys.json")

        except Exception as e:
            print(f"[!] SYSTEM ERROR in JarvisToolManager: {e}")

    def _get_tool_schemas(self):
        """Fetch tool schemas from Composio and convert to OpenAI function schemas."""
        if self._tool_schemas:
            return self._tool_schemas

        try:
            key_toolkits = ["gmail", "googledocs", "googlecalendar", "googlesheets", "googledrive", "youtube", "github", "linkedin", "googlemeet"]
            for toolkit in key_toolkits:
                tools = self.composio.tools.list(toolkit_slug=toolkit, limit=50)
                for item in tools.items:
                    name = (item.slug or "").strip()
                    if not name or name.startswith("_") or len(name) > 64:
                        continue

                    props = {}
                    req = []
                    ip = item.input_parameters or {}
                    for param_name, param_def in ip.get("properties", {}).items():
                        p = {"type": param_def.get("type", "string")}
                        if "description" in param_def:
                            p["description"] = param_def["description"]
                        props[param_name] = p
                        if param_name in ip.get("required", []):
                            req.append(param_name)

                    # OpenAI format
                    fd = {
                        "type": "function",
                        "function": {
                            "name": name,
                            "description": item.human_description or item.description or "",
                            "parameters": {
                                "type": "object",
                                "properties": props,
                                "required": req
                            }
                        }
                    }
                    self._tool_schemas.append(fd)
        except Exception as e:
            print(f"[!] Failed to fetch tool schemas: {e}")

        return self._tool_schemas

    def execute_task(self, prompt):
        if not self.composio or not self.client:
            return "Composio or OpenCode client not initialized. Check api_keys.json."

        try:
            tools = self._get_tool_schemas()
            if not tools:
                return "No Composio tools available. Please connect an app in your Composio dashboard."

            messages = [{"role": "user", "content": prompt}]

            for attempt in range(3):
                try:
                    response = self.client.chat.completions.create(
                        model="deepseek-v4-flash-free",
                        messages=messages,
                        tools=tools,
                        temperature=0.0
                    )
                    break
                except Exception as e:
                    err = str(e)
                    if "429" in err or "503" in err:
                        if attempt < 2:
                            print(f"[!] OpenCode API overloaded ({err}), retrying in {2 ** attempt}s...")
                            time.sleep(2 ** attempt)
                            continue
                    raise

            message = response.choices[0].message
            messages.append(message)

            while message.tool_calls:
                for tool_call in message.tool_calls:
                    fc = tool_call.function
                    name = fc.name
                    args = json.loads(fc.arguments) if fc.arguments else {}

                    print(f"[Composio] Executing tool '{name}'...")
                    
                    try:
                        result = self.composio.tools.execute(
                            tool_slug=name,
                            arguments=args,
                            entity_id=self.user_id
                        )
                        result_data = result.data if hasattr(result, "data") else str(result)
                    except Exception as e:
                        result_data = {"error": str(e)}

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": name,
                        "content": json.dumps(result_data)
                    })

                for attempt in range(3):
                    try:
                        response = self.client.chat.completions.create(
                            model="deepseek-v4-flash-free",
                            messages=messages,
                            tools=tools,
                            temperature=0.0
                        )
                        break
                    except Exception as e:
                        err = str(e)
                        if "429" in err or "503" in err:
                            if attempt < 2:
                                print(f"[!] OpenCode API overloaded, retrying in {2 ** attempt}s...")
                                time.sleep(2 ** attempt)
                                continue
                        raise
                        
                message = response.choices[0].message
                messages.append(message)

            return message.content if message.content else "Task completed."

        except Exception as e:
            return f"Task failed: {str(e)}"
