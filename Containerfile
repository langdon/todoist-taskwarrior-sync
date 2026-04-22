FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    taskwarrior \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY todoist_taskwarrior/ ./todoist_taskwarrior/
COPY pyproject.toml ./

RUN pip install --no-cache-dir --no-deps .

ENTRYPOINT ["titwsync"]
CMD ["--help"]
