from starlette.requests import Request


async def make_request(body: bytes, headers: dict) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
    }

    async def receive():
        return {"type": "http.request", "body": body}

    return Request(scope, receive)
