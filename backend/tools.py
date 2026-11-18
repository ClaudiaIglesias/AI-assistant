
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import logging
import inspect
from typing import get_type_hints

logger = logging.getLogger(__name__)


# ---------- TOOLS -------------
def get_current_time():
    """Returns the current date and time in Madrid."""

    now = datetime.now(ZoneInfo("Europe/Madrid"))

    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "day": now.strftime("%A"),
        "timezone": "Europe/Madrid"
    }


# ------------ Central registry of available tools -------------
TOOL_REGISTRY = {
    "get_current_time": get_current_time,
}


def get_available_tools():
    """Returns the tools available to Ollama."""
    return list(TOOL_REGISTRY.values())

def execute_tool(tool_call, execution_context):
    """Executes a tool requested by the model."""

    tool_name = tool_call.function.name
    arguments = tool_call.function.arguments or {}

    tool_function = TOOL_REGISTRY.get(tool_name)

    if tool_function is None:
        logger.warning("Unknown tool requested: %s", tool_name)
        return json.dumps({"error": "La herramienta solicitada no está disponible."}, ensure_ascii=False)

    try:
        # Validate arguments
        validate_tool_arguments(tool_function, arguments)

        # Identify this exact tool call
        call_signature = json.dumps(
            {"tool": tool_name, "arguments": arguments},
            sort_keys=True,
            ensure_ascii=False
        )

        # Prevent repeated executions
        if call_signature in execution_context["seen"]:
            raise ValueError("Repeated tool execution blocked.")

        # Limit total executions per user request
        if execution_context["count"] >= 5:
            raise ValueError("Maximum number of tool executions exceeded.")

        execution_context["seen"].add(call_signature)
        execution_context["count"] += 1


        result = tool_function(**arguments)
        return json.dumps(result, ensure_ascii=False)

    except Exception:
        logger.exception("Error executing tool: %s", tool_name)
        return json.dumps({"error": (f"No se ha podido ejecutar la herramienta {tool_name}.")}, ensure_ascii=False)


# --------- Helpers ----------

def validate_tool_arguments(tool_function, arguments):
    """Validates the arguments received by a tool."""

    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a dictionary.")

    signature = inspect.signature(tool_function)

    # Check required and unexpected arguments
    signature.bind(**arguments)

    # Check argument types when annotations are available
    type_hints = get_type_hints(tool_function)

    for name, value in arguments.items():
        expected_type = type_hints.get(name)

        if expected_type is None:
            continue

        if expected_type is int and isinstance(value, bool):
            raise ValueError(f"Invalid type for argument: {name}")

        if isinstance(expected_type, type) and not isinstance(value, expected_type):
            raise ValueError(f"Invalid type for argument: {name}")