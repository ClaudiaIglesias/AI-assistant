
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import logging
import inspect
from typing import get_type_hints
import ast
import operator
import math
import re

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

# -- Calculator
def evaluate_expression(node):
    """Safely evaluates a mathematical expression using allowed operations."""

    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError("Only numeric values are allowed.")

        return node.value

    if isinstance(node, ast.BinOp):
        operation = operators.get(type(node.op))

        if operation is None:
            raise ValueError("This mathematical operation is not allowed.")

        left = evaluate_expression(node.left)
        right = evaluate_expression(node.right)

        # Prevent excessively large exponent calculations
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("Exponent is too large.")

        return operation(left, right)

    if isinstance(node, ast.UnaryOp):
        operation = operators.get(type(node.op))

        if operation is None:
            raise ValueError("This mathematical operation is not allowed.")

        return operation(evaluate_expression(node.operand))

    raise ValueError("Invalid mathematical expression.")


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


# ------------ Central registry of available tools -------------
TOOL_REGISTRY = {
    "get_current_time": get_current_time,
    "calculate": calculate,
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