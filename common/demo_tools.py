"""Small, safe, offline tools shared by the Level 2 examples (no network, no side effects)."""
import ast
import operator

WEATHER = {"paris": (18, "cloudy"), "tokyo": (24, "sunny"), "london": (14, "rainy")}


class ToolError(Exception):
    """Raised by a tool for a recoverable failure; the message is shown to the model."""


def get_weather(location: str, unit: str = "celsius") -> str:
    key = location.strip().lower()
    if key not in WEATHER:
        # Tell the model how to recover, not just that it failed (see 02_tools/tool_design.md).
        raise ToolError(f"No data for '{location}'. Known cities: {', '.join(sorted(WEATHER))}.")
    temp_c, sky = WEATHER[key]
    temp = temp_c if unit == "celsius" else round(temp_c * 9 / 5 + 32)
    return f"{temp} degrees {unit}, {sky}"


_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg,
}


def calculate(expression: str) -> str:
    """Evaluate +,-,*,/,** on numbers. Walks the AST; never uses eval()."""
    def walk(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](walk(node.operand))
        raise ToolError("Only numbers and + - * / ** are allowed.")

    try:
        return str(walk(ast.parse(expression, mode="eval").body))
    except ZeroDivisionError:
        raise ToolError("Division by zero.") from None
    except SyntaxError:
        raise ToolError(f"Could not parse '{expression}' as an arithmetic expression.") from None


# strict=True + additionalProperties=false guarantees tool_use.input matches the schema.
TOOLS = [
    {
        "name": "get_weather",
        "description": (
            "Get the current weather for one city. Use for questions about temperature or "
            "conditions right now; not for forecasts."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name, e.g. 'Paris'."},
                "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
            },
            "required": ["location", "unit"],
            "additionalProperties": False,
        },
    },
    {
        "name": "calculate",
        "description": "Evaluate an arithmetic expression using + - * / ** and numbers. Returns the result.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"expression": {"type": "string", "description": "e.g. '(3 + 4) * 2'."}},
            "required": ["expression"],
            "additionalProperties": False,
        },
    },
]

HANDLERS = {"get_weather": get_weather, "calculate": calculate}


def run_tool(name: str, tool_input: dict) -> tuple[str, bool]:
    """Run one tool. Returns (content, is_error); never raises, so a failure becomes a tool_result."""
    handler = HANDLERS.get(name)
    if handler is None:
        return f"Unknown tool '{name}'. Available: {', '.join(HANDLERS)}.", True
    try:
        return handler(**tool_input), False
    except ToolError as e:
        return str(e), True
    except TypeError as e:  # bad/missing arguments; reported to the model instead of crashing the loop
        return f"Invalid arguments for {name}: {e}", True
