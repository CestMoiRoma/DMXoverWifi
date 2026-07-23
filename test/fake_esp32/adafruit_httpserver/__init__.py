"""Fake `adafruit_httpserver`.

Enough of the real API for `src/web_server.py` to register its routes unchanged,
plus a `dispatch()` helper so a test can call the API without a socket:

    response = server.dispatch("POST", "/api/devices", {"name": "PAR"})
    assert response.data["name"] == "PAR"

Route patterns support the `<name>` placeholders the firmware uses. Captured
values are passed to the handler positionally, in the order they appear in the
path, which is how the real library does it.
"""

GET = "GET"
POST = "POST"
PUT = "PUT"
DELETE = "DELETE"
HEAD = "HEAD"
PATCH = "PATCH"


class Request:
    def __init__(self, method, path, body=None, headers=None):
        self.method = method
        self.path = path
        self.body = body
        self.headers = headers or {}
        self.query_params = {}

    def json(self):
        if self.body is None:
            raise ValueError("request has no body")
        return self.body


class Response:
    def __init__(self, request, status=None):
        self.request = request
        code, reason = status if status else (200, "OK")
        self.status_code = code
        self.reason = reason


class JSONResponse(Response):
    def __init__(self, request, data, status=None):
        super().__init__(request, status)
        self.data = data


class FileResponse(Response):
    def __init__(self, request, filename, root_path=None, content_type=None, status=None):
        super().__init__(request, status)
        self.filename = filename
        self.root_path = root_path
        self.content_type = content_type


class Route:
    def __init__(self, pattern, method, handler):
        self.pattern = pattern
        self.method = method
        self.handler = handler
        self.parts = [p for p in pattern.strip("/").split("/") if p != ""]

    def match(self, path):
        """Return the list of captured values, or None if the path is a miss."""
        parts = [p for p in path.strip("/").split("/") if p != ""]
        if len(parts) != len(self.parts):
            return None
        captured = []
        for pattern_part, actual in zip(self.parts, parts):
            if pattern_part.startswith("<") and pattern_part.endswith(">"):
                captured.append(actual)
            elif pattern_part != actual:
                return None
        return captured


class ServerStoppedError(RuntimeError):
    pass


class Server:
    def __init__(self, socket_source, root_path="/", debug=False):
        self.socket_source = socket_source
        self.root_path = root_path
        self.debug = debug
        self.routes = []
        self.started = False
        self.host = None
        self.port = None
        self.poll_count = 0

    def route(self, path, method=GET, **kwargs):
        def decorator(handler):
            self.routes.append(Route(path, method, handler))
            return handler

        return decorator

    def start(self, host="0.0.0.0", port=80):
        self.started = True
        self.host = host
        self.port = port

    def stop(self):
        self.started = False

    def poll(self):
        self.poll_count += 1

    # -- test helper --

    def dispatch(self, method, path, body=None):
        """Route a request the way the real server would, and return the
        Response object the handler built."""
        for route in self.routes:
            if route.method != method:
                continue
            captured = route.match(path)
            if captured is None:
                continue
            request = Request(method, path, body)
            return route.handler(request, *captured)
        raise LookupError("no route for %s %s" % (method, path))

    def has_route(self, method, path):
        return any(r.method == method and r.match(path) is not None for r in self.routes)
