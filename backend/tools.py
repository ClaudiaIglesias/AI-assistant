import json
import logging
import ast
import operator
import math
import re
import requests
import os
import stat
from pathlib import Path

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from security import (
    MAX_TOOL_EXECUTIONS, MAX_RESULT_SIZE, MAX_ARGUMENT_SIZE, MAX_DIRECTORY_ENTRIES,
    validate_tool_arguments, format_untrusted_content, is_safe_search_result_url,
    validate_directory_path, is_blocked_directory_name, is_blocked_file_name, is_restricted_filesystem_entry, is_hidden_or_system_entry,
)


logger = logging.getLogger(__name__)

# ---------- LIMITS -------------

# -- Web Search
SEARXNG_URL = "http://127.0.0.1:8080/search"

MAX_SEARCH_QUERY_LENGTH = 300
MAX_SEARCH_RESULTS = 5
MAX_SEARCH_RESPONSE_BYTES = 1_000_000
MAX_SEARCH_RESULT_TITLE_LENGTH = 300
MAX_SEARCH_RESULT_CONTENT_LENGTH = 1_200

# -- Read files
MAX_READ_FILE_SIZE = 1_000_000  # 1 MB
MAX_READ_FILE_CHARS = 32_000
MAX_READ_FILE_PATH_LENGTH = 1_000

ALLOWED_READ_FILE_EXTENSIONS = {".py", ".md"}


# ---------- TOOLS -------------
# -- Time
def get_current_time(timezone: str = "Europe/Madrid"):
    """Returns the current date and time in the requested timezone."""

    timezone = timezone.strip() if timezone else "Europe/Madrid"

    try:
        tz = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return {"error": f"Unknown or invalid timezone: {timezone}", "default_timezone": "Europe/Madrid"}

    now = datetime.now(tz)

    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "day": now.strftime("%A"),
        "timezone": tz.key
    }

# -- Calculator
def calculate(expression: str):
    """
    Evaluates mathematical expressions using a restricted AST.

    Supports basic arithmetic, percentages, powers,
    roots, logarithms, trigonometric functions, and constants.
    """

    if not isinstance(expression, str):
        raise ValueError("Expression must be a string.")

    if len(expression) > 200:
        raise ValueError("Expression is too long.")


    # Convert percentages: 15% -> (15/100)
    expression = re.sub(
        r"(?<![\w.])(\d+(?:\.\d+)?)\s*%",
        r"(\1/100)",
        expression
    )

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        raise ValueError("Invalid mathematical expression.")

    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    functions = {
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "asin": math.asin,
        "acos": math.acos,
        "atan": math.atan,
        "log": math.log10,
        "log10": math.log10,
        "log2": math.log2,
        "ln": math.log,
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
    }

    constants = {
        "pi": math.pi,
        "e": math.e,
    }

    def evaluate(node):
        if isinstance(node, ast.Expression):
            return evaluate(node.body)

        elif isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance( node.value, (int, float)):
                raise ValueError("Only numeric constants are allowed.")

            return node.value

        elif isinstance(node, ast.BinOp):
            operation = operators.get(type(node.op))

            if operation is None:
                raise ValueError("Operator not allowed.")

            left = evaluate(node.left)
            right = evaluate(node.right)

            if isinstance(node.op, ast.Pow):
                if abs(right) > 100:
                    raise ValueError("Exponent is too large.")

                if abs(left) > 1_000_000:
                    raise ValueError("Power base is too large.")
            return operation(left, right)

        elif isinstance(node, ast.UnaryOp):
            operation = operators.get(type(node.op))

            if operation is None:
                raise ValueError("Unary operator not allowed.")

            return operation(evaluate(node.operand))

        elif isinstance(node, ast.Name):
            if node.id in constants:
                return constants[node.id]

            raise ValueError(f"Name not allowed: {node.id}")

        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Function call not allowed.")

            function = functions.get(node.func.id)

            if function is None:
                raise ValueError(f"Function not allowed: {node.func.id}")

            if node.keywords:
                raise ValueError("Keyword arguments are not allowed.")

            arguments = [evaluate(arg) for arg in node.args]

            return function(*arguments)

        else:
            raise ValueError("Expression component not allowed.")

    # Limit expression complexity.
    if sum(1 for _ in ast.walk(tree)) > 50:
        raise ValueError("Expression is too complex.")

    result = evaluate(tree)

    if not isinstance(result, (int, float)) or not math.isfinite(result):
        raise ValueError("Result is not a valid finite number.")

    return { "expression": expression, "result": result }

# -- Weather
def get_weather(city: str = "", forecast_days: int = 3):
    """
    Retrieves current weather and forecast for a location.

    city: City name and, if possible, country.
    forecast_days: Number of forecast days, between 1 and 7.
    """

    if not isinstance(city, str) or not city.strip():
        return { "status": "needs_clarification", "question": "Which city or location should I check?"}

    if len(city) > 120:
        raise ValueError("City name is too long.")

    if not isinstance(forecast_days, int) or isinstance(forecast_days, bool):
        raise ValueError("forecast_days must be an integer.")

    if not 1 <= forecast_days <= 7:
        raise ValueError("Forecast must be between 1 and 7 days.")

    # WMO codes meaning
    weather_descriptions = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        56: "Light freezing drizzle",
        57: "Dense freezing drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        66: "Light freezing rain",
        67: "Heavy freezing rain",
        71: "Slight snowfall",
        73: "Moderate snowfall",
        75: "Heavy snowfall",
        77: "Snow grains",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Slight snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }

     # Search for multiple possible locations
    
    # Search the city coordinates
    geocoding_response = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={
            "name": city.strip(),
            "count": 10,
            "language": "en",
            "format": "json",
        },
        timeout=10,
    )

    geocoding_response.raise_for_status()
    geocoding_data = geocoding_response.json()

    results = geocoding_data.get("results", [])

    if not results:
        return {"status": "error", "error": f"No location found for: {city}"}

    # Check whether the user provided a country or region
    query = city.casefold()

    matching_context = []

    for result in results:
        country = result.get("country", "")
        region = result.get("admin1", "")

        if ( country and country.casefold() in query) or (region and region.casefold() in query):
            matching_context.append(result)

    # If the user specified a country or region, prefer the matching location.
    if matching_context:
        place = matching_context[0]

    else:
        # Find exact city-name matches
        exact_matches = [
            result for result in results
            if result.get("name", "").casefold() == query
        ]

        if not exact_matches:
            exact_matches = results

        # Detect different possible locations
        distinct_locations = {
            (
                result.get("name"),
                result.get("admin1"),
                result.get("country"),
            )
            for result in exact_matches
        }

        if len(distinct_locations) > 1:
            candidates = []

            for result in exact_matches[:5]:
                candidates.append({
                    "name": result.get("name"),
                    "region": result.get("admin1"),
                    "country": result.get("country"),
                })

            return {
                "status": "needs_clarification",
                "question": "Which location do you mean?",
                "candidates": candidates,
            }

        place = exact_matches[0]

    latitude = place["latitude"]
    longitude = place["longitude"]


    # Retrieve the weather forecast.
    weather_response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,"
                "relative_humidity_2m,"
                "apparent_temperature,"
                "precipitation,"
                "weather_code,"
                "wind_speed_10m"
            ),
            "daily": (
                "weather_code,"
                "temperature_2m_max,"
                "temperature_2m_min,"
                "precipitation_probability_max,"
                "sunrise,"
                "sunset"
            ),
            "forecast_days": forecast_days,
            "timezone": "auto",
        },
        timeout=10,
    )

    weather_response.raise_for_status()
    data = weather_response.json()

    # Prepare current weather.
    current = data["current"]

    current_weather = {
        "time": current["time"],
        "temperature": current["temperature_2m"],
        "feels_like": current["apparent_temperature"],
        "humidity": current["relative_humidity_2m"],
        "precipitation": current["precipitation"],
        "wind_speed": current["wind_speed_10m"],
        "description": weather_descriptions.get(
            current["weather_code"],
            "Estado meteorológico desconocido",
        ),
    }

    # Prepare daily forecast.
    daily_data = data["daily"]
    daily_forecast = []

    for i in range(len(daily_data["time"])):
        weather_code = daily_data["weather_code"][i]

        daily_forecast.append({
            "date": daily_data["time"][i],
            "description": weather_descriptions.get(
                weather_code,
                "Estado meteorológico desconocido",
            ),
            "temperature_max": daily_data["temperature_2m_max"][i],
            "temperature_min": daily_data["temperature_2m_min"][i],
            "precipitation_probability": (
                daily_data["precipitation_probability_max"][i]
            ),
            "sunrise": daily_data["sunrise"][i],
            "sunset": daily_data["sunset"][i],
        })

    return {
        "status": "success",
        "location": {
            "name": place.get("name"),
            "region": place.get("admin1"),
            "country": place.get("country"),
            "timezone": data.get("timezone"),
        },
        "current": current_weather,
        "forecast": daily_forecast,
        "source": "Open-Meteo",
    }

# -- Web Search
def search_web(query: str, max_results: int = 5):
    """
    Searches the web through the local SearXNG instance.

    Search results are treated as untrusted external content.
    The function never visits result URLs.
    """

    if not isinstance(query, str):
        raise ValueError("Search query must be a string.")

    query = re.sub(r"\s+", " ", query).strip()

    if not query:
        raise ValueError("Search query cannot be empty.")

    if len(query) > MAX_SEARCH_QUERY_LENGTH:
        raise ValueError("Search query is too long.")

    if not isinstance(max_results, int) or isinstance(max_results, bool):
        raise ValueError("max_results must be an integer.")

    if not 1 <= max_results <= MAX_SEARCH_RESULTS:
        raise ValueError(f"max_results must be between 1 and {MAX_SEARCH_RESULTS}.")

    logger.info("Performing web search through local SearXNG.")

    try:
        # Use a dedicated session without environment proxy settings.
        with requests.Session() as session:
            session.trust_env = False

            with session.get(
                SEARXNG_URL,
                params={
                    "q": query,
                    "format": "json",
                    "categories": "general",
                },
                headers={
                    "Accept": "application/json",
                    "User-Agent": "LocalAssistant/1.0",
                },
                timeout=(5, 15),
                allow_redirects=False,
                stream=True,
            ) as response:

                if response.status_code != 200:
                    logger.warning( "SearXNG returned HTTP status %s.", response.status_code )
                    return {"status": "error", "message": "The search service returned an unexpected response." }

                content_type = response.headers.get(
                    "Content-Type", ""
                ).lower()

                if "application/json" not in content_type:
                    logger.warning("SearXNG returned an unexpected content type." )
                    return { "status": "error", "message": "The search service did not return JSON." }

                content_length = response.headers.get("Content-Length")

                if content_length:
                    try:
                        if int(content_length) > MAX_SEARCH_RESPONSE_BYTES:
                            return { "status": "error", "message": "The search response was too large." }
                    except ValueError:
                        return { "status": "error", "message": "The search response had an invalid size." }

                # Read the response with a strict size limit.
                response_body = bytearray()

                for chunk in response.iter_content(chunk_size=65_536):
                    if not chunk:
                        continue

                    response_body.extend(chunk)

                    if len(response_body) > MAX_SEARCH_RESPONSE_BYTES:
                        logger.warning( "SearXNG response exceeded the size limit." )
                        return { "status": "error", "message": "The search response was too large." }

                data = json.loads(response_body)

        if not isinstance(data, dict):
            raise ValueError("Invalid search response structure.")

        raw_results = data.get("results", [])

        if not isinstance(raw_results, list):
            raise ValueError("Invalid search results structure.")

        safe_results = []

        for result in raw_results:
            if not isinstance(result, dict):
                continue

            title = result.get("title")
            url = result.get("url")
            content = result.get("content")

            if not isinstance(title, str):
                continue

            if not isinstance(content, str):
                content = ""

            if not is_safe_search_result_url(url):
                continue

            safe_results.append({
                "title": title[:MAX_SEARCH_RESULT_TITLE_LENGTH],
                "url": url,
                "snippet": content[:MAX_SEARCH_RESULT_CONTENT_LENGTH],
            })

            if len(safe_results) >= max_results:
                break

        if not safe_results:
            return {
                "status": "success",
                "query": query,
                "result_count": 0,
                "message": "No usable search results were found.",
                "source": "SearXNG",
            }

        # Mark every search result as untrusted external content.
        untrusted_results = format_untrusted_content(
            source="SearXNG web search",
            content=safe_results,
        )

        return {
            "status": "success",
            "query": query,
            "result_count": len(safe_results),
            "results": untrusted_results,
            "source": "SearXNG",
        }

    except requests.RequestException:
        logger.exception("Could not connect to the local SearXNG service.")
        return {"status": "error", "message": "The local search service could not be reached."}

    except (ValueError, json.JSONDecodeError):
        logger.exception("Invalid response received from SearXNG.")
        return {"status": "error", "message": "The search service returned invalid data."}

# -- File system
def ls(path: str = ".") -> dict:
    """
    Lists files and directories in a specified directory.

    This function only lists directory entries.
    It does not read, modify, delete, or execute files.
    """

    if not isinstance(path, str):
        return {"status": "error", "message": "Path must be a string."}

    path = path.strip()

    if not path:
        return {"status": "error", "message": "A directory path must be specified."}

    
    try:
        directory = validate_directory_path(path)

        directories = []
        files = []
        skipped = 0
        truncated = False

        with os.scandir(directory) as entries:
            for entry in entries:

                if len(directories) + len(files) >= MAX_DIRECTORY_ENTRIES:
                    truncated = True
                    break

                name = entry.name
                lower_name = name.lower()

                # Skip restricted directory names.
                if is_blocked_directory_name(name):
                    skipped += 1
                    continue

                try:
                    entry_stat = entry.stat(follow_symlinks=False)

                    # Reject links, reparse points, hidden entries,
                    # and system entries.
                    if is_restricted_filesystem_entry(entry_stat):
                        skipped += 1
                        continue

                    if is_hidden_or_system_entry(entry_stat):
                        skipped += 1
                        continue

                except OSError:
                    skipped += 1
                    continue

                # Handle directories.
                if entry.is_dir(follow_symlinks=False):
                    if lower_name.startswith("."):
                        skipped += 1
                        continue

                    directories.append(name)
                    continue

                # Handle regular files.
                if entry.is_file(follow_symlinks=False):
                    if is_blocked_file_name(name):
                        skipped += 1
                        continue

                    files.append(name)
                    continue

                skipped += 1

        directories.sort(key=str.lower)
        files.sort(key=str.lower)

        logger.info(
            "Filesystem listing completed | Directories: %d | Files: %d | Skipped: %d",
            len(directories),
            len(files),
            skipped
        )

        return {
            "status": "success",
            "directory": str(directory),
            "directories": directories,
            "files": files,
            "directory_count": len(directories),
            "file_count": len(files),
            "skipped_entries": skipped,
            "max_entries": MAX_DIRECTORY_ENTRIES,
            "truncated": truncated
        }

    except FileNotFoundError:
        return {"status": "error", "message": "The specified directory does not exist."}

    except NotADirectoryError:
        return {"status": "error", "message": "The specified path is not a directory."}

    except PermissionError:
        return {"status": "error", "message": "Access to the specified directory is restricted."}

    except OSError:
        logger.exception("Could not list the specified directory.")

        return {"status": "error", "message": "Could not access the specified directory."}

# -- Read files
def read_file(path: str) -> dict:
    """
    Reads the contents of an allowed file without modifying it.

    Only Python and Markdown files are supported.
    Restricted directories, hidden files, symbolic links,
    and Windows reparse points are rejected.
    """

    if not isinstance(path, str):
        return {"status": "error", "message": "Path must be a string."}

    path = path.strip()

    if not path:
        return {"status": "error", "message": "A file path must be specified."}

    if len(path) > MAX_READ_FILE_PATH_LENGTH:
        return {"status": "error", "message": "File path is too long."}

    file_path = Path(path).expanduser()

    if not file_path.is_absolute():
        file_path = Path.cwd() / file_path

    file_path = Path(os.path.abspath(file_path))

    # Check the file extension.
    if file_path.suffix.lower() not in ALLOWED_READ_FILE_EXTENSIONS:
        return {"status": "error", "message": "Only .py and .md files can be read."}

    # Reject restricted filenames.
    if is_blocked_file_name(file_path.name):
        return {"status": "error", "message": "Access to this file is restricted."}

    file_descriptor = None

    try:
        # Validate the parent directory using the same rules as ls().
        validate_directory_path(str(file_path.parent))

        # Inspect the file without following symbolic links.
        file_stat = os.lstat(file_path)

        if is_restricted_filesystem_entry(file_stat):
            return {"status": "error", "message": "Symbolic links and reparse points are not allowed."}

        if is_hidden_or_system_entry(file_stat):
            return {"status": "error", "message": "Hidden and system files cannot be read."}

        if not stat.S_ISREG(file_stat.st_mode):
            return {"status": "error", "message": "The specified path is not a regular file."}

        if file_stat.st_size > MAX_READ_FILE_SIZE:
            return {"status": "error", "message": "File exceeds the maximum allowed size of 1 MB."}

        # Open the file in read-only mode.
        flags = os.O_RDONLY

        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY

        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW

        file_descriptor = os.open(file_path, flags)

        opened_stat = os.fstat(file_descriptor)

        # Verify that the opened file is still a regular file.
        if not stat.S_ISREG(opened_stat.st_mode):
            return {"status": "error", "message": "The opened path is not a regular file."}

        if is_restricted_filesystem_entry(opened_stat):
            return {"status": "error", "message": "The opened file is restricted."}

        if is_hidden_or_system_entry(opened_stat):
            return {"status": "error", "message": "Hidden and system files cannot be read."}

        # Detect changes between the initial inspection and opening.
        if ( file_stat.st_ino and opened_stat.st_ino and (file_stat.st_dev != opened_stat.st_dev or file_stat.st_ino != opened_stat.st_ino)):
            return {"status": "error", "message": "The file changed during validation."}

        if opened_stat.st_size > MAX_READ_FILE_SIZE:
            return {"status": "error", "message": "File exceeds the maximum allowed size of 1 MB."}

        # Read at most 1 MB plus one byte to detect unexpected growth.
        with os.fdopen(file_descriptor, "rb") as file:
            file_descriptor = None
            raw_content = file.read(MAX_READ_FILE_SIZE + 1)

        if len(raw_content) > MAX_READ_FILE_SIZE:
            return {"status": "error", "message": "File exceeds the maximum allowed size of 1 MB."}

        # Decode UTF-8 text.
        try:
            content = raw_content.decode("utf-8-sig")
        except UnicodeDecodeError:
            return {"status": "error", "message": "The file is not valid UTF-8 text."}

        total_chars = len(content)
        truncated = total_chars > MAX_READ_FILE_CHARS

        if truncated:
            content = content[:MAX_READ_FILE_CHARS]

        logger.info(
            "File read completed | Extension: %s | Characters: %d | Truncated: %s",
            file_path.suffix.lower(),
            len(content),
            truncated
        )

        return {
            "status": "success",
            "file": str(file_path),
            "content": content,
            "characters_returned": len(content),
            "total_characters": total_chars,
            "truncated": truncated,
            "max_characters": MAX_READ_FILE_CHARS
        }

    except FileNotFoundError:
        return {"status": "error", "message": "The specified file does not exist."}

    except PermissionError:
        return {"status": "error", "message": "Access to the specified file is restricted."}

    except IsADirectoryError:
        return {"status": "error", "message": "The specified path is a directory, not a file."}

    except (ValueError, OSError):
        logger.exception("Could not read the specified file.")
        return {"status": "error", "message": "Could not access or read the specified file."}

    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)


# ------------ Central registry of available tools -------------
TOOL_REGISTRY = {
    "get_current_time": get_current_time,
    "calculate": calculate,
    "get_weather": get_weather,
    "search_web": search_web,
    "ls": ls,
    "read_file": read_file,
}

def get_available_tools():
    """Returns the tools available to Ollama."""
    return list(TOOL_REGISTRY.values())


# --------- Tool execution ----------
def execute_tool(tool_call, execution_context):
    """Executes a tool requested by the model."""

    try:
        # Check the tool call structure
        function_data = getattr(tool_call, "function", None)

        if function_data is None:
            raise ValueError("Invalid tool call structure.")

        tool_name = tool_call.function.name
        arguments = tool_call.function.arguments or {}

        if not isinstance(tool_name, str):
            raise ValueError("Invalid tool name.")

        # Only registered tools can be executed
        tool_function = TOOL_REGISTRY.get(tool_name)

        if tool_function is None:
            logger.warning("Unknown tool requested: %s", tool_name)
            return json.dumps({"error": "La herramienta solicitada no está disponible."}, ensure_ascii=False)


        # Some model responses may provide arguments as a JSON string
        if isinstance(arguments, str):
            if len(arguments.encode("utf-8")) > MAX_ARGUMENT_SIZE:
                raise ValueError("Tool arguments are too large.")

            arguments = json.loads(arguments)

        if arguments is None:
            arguments = {}

    
        # Validate arguments before execution
        validate_tool_arguments(tool_function, arguments)

        # Validate execution context
        if not isinstance(execution_context, dict):
            raise ValueError("Invalid execution context.")

        if not isinstance(execution_context.get("count"), int):
            raise ValueError("Invalid execution counter.")

        if not isinstance(execution_context.get("seen"), set):
            raise ValueError("Invalid execution history.")


        # Identify this exact tool call
        call_signature = json.dumps(
            {"tool": tool_name, "arguments": arguments},
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False
        )

        # Prevent repeated executions
        if call_signature in execution_context["seen"]:
            raise ValueError("Repeated tool execution blocked.")

        # Limit total executions per user request
        if execution_context["count"] >= MAX_TOOL_EXECUTIONS:
            raise ValueError("Maximum number of tool executions exceeded.")

        execution_context["seen"].add(call_signature)
        execution_context["count"] += 1

        logger.info("Executing tool: %s  --- Arguments: %s", tool_name, tool_call.function.arguments)

        result = tool_function(**arguments)

        # Serialize the result safely
        serialized_result = json.dumps(
            result,
            ensure_ascii=False,
            allow_nan=False
        )

        # Prevent excessively large results from reaching the model
        if len(serialized_result.encode("utf-8")) > MAX_RESULT_SIZE:
            logger.warning(
                "Tool result exceeded size limit: %s",
                tool_name
            )

            return json.dumps({"error": "The tool result was too large to process."}, ensure_ascii=False)

        return serialized_result

    except Exception:
        logger.exception("Error executing tool: %s", tool_name)
        return json.dumps({"error": (f"No se ha podido ejecutar la herramienta {tool_name}.")}, ensure_ascii=False)


