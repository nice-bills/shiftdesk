# ShiftDesk OpenEnv server. The arena runs linux/amd64 only.
FROM python:3.12-slim

WORKDIR /app/env
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONPATH=/app/env

# CLI tools the policy's bash tool offers (python3 comes with the base image).
RUN apt-get update \
 && apt-get install -y --no-install-recommends jq sqlite3 bc openssl file util-linux \
      $(apt-cache show setpriv >/dev/null 2>&1 && echo setpriv) \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY vendor ./vendor
RUN pip install --no-cache-dir --no-deps ./vendor/openenv-0.6.1.dev0-py3-none-any.whl

COPY shiftdesk ./shiftdesk
COPY openenv.yaml ./

# Instance seed salt and server code are root-only; policy code runs as nobody.
RUN python -c "import secrets; print(secrets.token_hex(32))" > /app/salt \
 && chmod 600 /app/salt && chmod -R go-rwx /app/env

EXPOSE 8000
CMD ["uvicorn", "shiftdesk.server.app:app", "--host", "0.0.0.0", "--port", "8000"]
