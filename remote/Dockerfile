FROM python:3.13-slim AS runtime
ARG APP_VERSION=1.1.1
LABEL org.opencontainers.image.title="Firmware Monitor" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.description="Мониторинг версий прошивок сетевого оборудования"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN groupadd --system app && useradd --system --gid app --home /app app
RUN apt-get update && apt-get install --no-install-recommends -y iputils-ping && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN mkdir -p /data && chown -R app:app /app /data
USER app
EXPOSE 8080
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8080","--proxy-headers","--no-server-header"]
