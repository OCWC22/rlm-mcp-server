FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml rlm_mcp.py README.md LICENSE /app/
RUN pip install --no-cache-dir .
ENV RLM_STATE_DIR=/data
VOLUME ["/data"]
ENTRYPOINT ["rlm-mcp"]
