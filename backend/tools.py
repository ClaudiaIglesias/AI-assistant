import json
from datetime import datetime
from zoneinfo import ZoneInfo
import logging
import ast
import operator
import math
import re
import requests

from security import validate_tool_arguments, format_untrusted_content, _is_safe_search_result_url


logger = logging.getLogger(__name__)


# --------- TOOL SECURITY LIMITS ----------

MAX_TOOL_EXECUTIONS = 5
# Maximum serialized size of tool results
MAX_RESULT_SIZE = 16_000



# ---------- TOOLS -------------
# -- Time
def get_current_time():
    """Returns the current date and time in Madrid."""

    now = datetime.now(ZoneInfo("Europe/Madrid"))

    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "day": now.strftime("%A"),
        "timezone": "Europe/Madrid"
    }

# -- Calculator
def calculate(expression: str):
    """
    Calculadora matemática segura.
    Admite operaciones básicas, porcentajes, raíces,
    logaritmos, trigonometría y constantes matemáticas.
    """

    if not isinstance(expression, str):
        raise ValueError("La expresión debe ser texto.")

    if len(expression) > 200:
        raise ValueError("La expresión es demasiado larga.")

    # Convertir porcentajes: 15% -> (15/100)
    expression = re.sub(
        r"(?<![\w.])(\d+(?:\.\d+)?)\s*%",
        r"(\1/100)",
        expression
    )

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        raise ValueError("La expresión matemática no es válida.")

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
            if isinstance(node.value, bool) or not isinstance(
                node.value, (int, float)
            ):
                raise ValueError("Solo se permiten números.")

            return node.value

        elif isinstance(node, ast.BinOp):
            operation = operators.get(type(node.op))

            if operation is None:
                raise ValueError("Operador no permitido.")

            left = evaluate(node.left)
            right = evaluate(node.right)

            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("Exponente demasiado grande.")

            return operation(left, right)

        elif isinstance(node, ast.UnaryOp):
            operation = operators.get(type(node.op))

            if operation is None:
                raise ValueError("Operador no permitido.")

            return operation(evaluate(node.operand))

        elif isinstance(node, ast.Name):
            if node.id in constants:
                return constants[node.id]

            raise ValueError(f"Nombre no permitido: {node.id}")

        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Llamada a función no permitida.")

            function = functions.get(node.func.id)

            if function is None:
                raise ValueError(
                    f"Función no permitida: {node.func.id}"
                )

            if node.keywords:
                raise ValueError("No se permiten argumentos con nombre.")

            arguments = [evaluate(arg) for arg in node.args]

            return function(*arguments)

        else:
            raise ValueError("Expresión no permitida.")

    # Limitar la complejidad de la expresión
    if sum(1 for _ in ast.walk(tree)) > 50:
        raise ValueError("Expresión demasiado compleja.")

    result = evaluate(tree)

    if not isinstance(result, (int, float)) or not math.isfinite(result):
        raise ValueError("El resultado no es un número válido.")

    return {
        "expression": expression,
        "result": result
    }

# -- Weather
def get_weather(city: str = "", forecast_days: int = 3):
    """
    Consulta el tiempo actual y la previsión meteorológica de una ciudad.
    city: Nombre de la ciudad y, si es posible, país.
    forecast_days: Número de días de previsión, entre 1 y 7.
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


    # Consultar la previsión meteorológica
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

    # Preparar el tiempo actual
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

    # Preparar la previsión diaria
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
SEARXNG_URL = "http://127.0.0.1:8080/search"

MAX_SEARCH_QUERY_LENGTH = 300
MAX_SEARCH_RESULTS = 5
MAX_SEARCH_RESPONSE_BYTES = 1_000_000
MAX_SEARCH_RESULT_TITLE_LENGTH = 300
MAX_SEARCH_RESULT_CONTENT_LENGTH = 1_200


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
        raise ValueError(
            f"max_results must be between 1 and {MAX_SEARCH_RESULTS}."
        )

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
                    logger.warning(
                        "SearXNG returned HTTP status %s.",
                        response.status_code
                    )
                    return {
                        "status": "error",
                        "message": "The search service returned an unexpected response."
                    }

                content_type = response.headers.get(
                    "Content-Type", ""
                ).lower()

                if "application/json" not in content_type:
                    logger.warning(
                        "SearXNG returned an unexpected content type."
                    )
                    return {
                        "status": "error",
                        "message": "The search service did not return JSON."
                    }

                content_length = response.headers.get("Content-Length")

                if content_length:
                    try:
                        if int(content_length) > MAX_SEARCH_RESPONSE_BYTES:
                            return {
                                "status": "error",
                                "message": "The search response was too large."
                            }
                    except ValueError:
                        return {
                            "status": "error",
                            "message": "The search response had an invalid size."
                        }

                # Read the response with a strict size limit.
                response_body = bytearray()

                for chunk in response.iter_content(chunk_size=65_536):
                    if not chunk:
                        continue

                    response_body.extend(chunk)

                    if len(response_body) > MAX_SEARCH_RESPONSE_BYTES:
                        logger.warning(
                            "SearXNG response exceeded the size limit."
                        )
                        return {
                            "status": "error",
                            "message": "The search response was too large."
                        }

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

            if not _is_safe_search_result_url(url):
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


# ------------ Central registry of available tools -------------
TOOL_REGISTRY = {
    "get_current_time": get_current_time,
    "calculate": calculate,
    "get_weather": get_weather,
    "search_web": search_web,
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

        logger.info("Executing tool: %s", tool_name)

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


