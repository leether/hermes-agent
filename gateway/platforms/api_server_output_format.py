"""Bounded, opt-in structured output on transient model requests."""
import json
import re


def request_output_format(options):
    value = options.get("response_format") if isinstance(options, dict) else None
    if value is None:
        return None
    if value == {"type": "json_object"}:
        return value
    if not isinstance(value, dict) or set(value) != {"type", "json_schema"} or value["type"] != "json_schema":
        raise ValueError("Unsupported transient response format")
    spec = value["json_schema"]
    if (not isinstance(spec, dict) or set(spec) != {"name", "strict", "schema"}
            or not isinstance(spec["name"], str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", spec["name"])
            or spec["strict"] is not True or not isinstance(spec["schema"], dict)):
        raise ValueError("Invalid transient JSON schema")
    encoded = json.dumps(value)
    if len(encoded) > 16384 or re.search(r'"\$(?:ref|dynamicRef)"\s*:', encoded):
        raise ValueError("Transient JSON schema must be bounded and self-contained")
    return json.loads(encoded)
