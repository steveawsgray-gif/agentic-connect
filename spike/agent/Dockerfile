# Gate 0 spike — AgentCore Runtime container.
# AgentCore Runtime expects an A2A server to be a stateless, streamable
# HTTP server on port 9000 at the root path (0.0.0.0:9000/).
# (AgentCore dev guide, "Deploy A2A servers in AgentCore Runtime".)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Non-root user: the Runtime runs the container as an unprivileged user
# in its microVM; nothing in this image needs root at runtime.
RUN useradd --create-home --uid 10001 spike

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

USER 10001

EXPOSE 9000

# /ping is served by main.py (the raw A2AStarletteApplication does not
# provide it; serve_a2a does — see the comment in main.py).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9000/ping', timeout=4)"

CMD ["python", "main.py"]
