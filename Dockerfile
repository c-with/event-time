FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN groupadd --gid 10001 eventtime && useradd --uid 10001 --gid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin eventtime
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py models.py ./
COPY static ./static
COPY scripts ./scripts
RUN mkdir -p /data/files /data/thumbnails /data/tmp && chown -R eventtime:eventtime /app /data
USER eventtime:eventtime
EXPOSE 8097
CMD ["python", "app.py", "serve"]
