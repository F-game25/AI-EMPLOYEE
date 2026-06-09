"""Register ReAct-specific atomic tools into ToolRegistry.

Imported by tools/__init__.py autoregister. Adds:
- shell_exec  (risk 2)
- code_exec   (risk 2)
- read_file   (risk 0, replaces stub)
- write_file  (risk 1, replaces stub)
- list_dir    (risk 0)
- web_fetch   (risk 2, replaces browser_fetch stub)
"""
from __future__ import annotations

from .registry import get_tool_registry
from .implementations.shell_exec import shell_exec
from .implementations.code_exec import code_exec
from .implementations.file_ops import read_file, write_file, list_dir
from .implementations.web_fetch import web_fetch


def _register_react_tools() -> None:
    reg = get_tool_registry()

    reg.register(
        "shell_exec", shell_exec, risk_level=2,
        description="Run a shell command in a sandboxed environment",
        input_schema={"command": "str", "cwd": "str", "timeout": "int"},
    )
    reg.register(
        "code_exec", code_exec, risk_level=2,
        description="Execute Python, JavaScript, or Bash code in a sandboxed subprocess",
        input_schema={"language": "str", "code": "str", "timeout": "int"},
    )
    # Override stubs with real implementations
    reg.register(
        "read_file", read_file, risk_level=0,
        description="Read a file from the filesystem (up to 50 KB)",
        input_schema={"path": "str"},
    )
    reg.register(
        "write_file", write_file, risk_level=1,
        description="Write content to a file, creating parent directories as needed",
        input_schema={"path": "str", "content": "str"},
    )
    reg.register(
        "list_dir", list_dir, risk_level=0,
        description="List files and directories at a path",
        input_schema={"path": "str"},
    )
    reg.register(
        "web_fetch", web_fetch, risk_level=2,
        description="Fetch a URL via HTTP GET or POST, returns status and body",
        input_schema={"url": "str", "method": "str", "headers": "dict", "body": "dict", "timeout": "int"},
    )
    # Also override browser_fetch stub
    reg.register(
        "browser_fetch", web_fetch, risk_level=2,
        description="Fetch a URL via HTTP (alias for web_fetch)",
        input_schema={"url": "str"},
    )


_register_react_tools()
