import os

MAX_CONTENT_LEN = int(os.environ.get("AGENTTRACE_MAX_CONTENT", 500))


def truncate_payload(data):
    """Recursively truncate long 'content' strings in inputs/outputs to prevent DB bloat."""
    if int(os.environ.get("AGENTTRACE_FULL_PAYLOAD", 0)) == 1:
        return data

    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if k == "content" and isinstance(v, str) and len(v) > MAX_CONTENT_LEN:
                sanitized[k] = (
                    v[:MAX_CONTENT_LEN]
                    + f"\n\n... [Truncated by AgentTrace. Max length {MAX_CONTENT_LEN}]"
                )
            else:
                sanitized[k] = truncate_payload(v)
        return sanitized
    elif isinstance(data, list):
        return [truncate_payload(item) for item in data]
    return data
