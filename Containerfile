FROM registry.fedoraproject.org/fedora-minimal:latest

RUN microdnf install -y \
    python3 \
    python3-pip \
    taskwarrior \
    && microdnf clean all

WORKDIR /app

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

COPY todoist_taskwarrior/ ./todoist_taskwarrior/
COPY pyproject.toml ./

RUN pip3 install --no-cache-dir --no-deps .

ENTRYPOINT ["titwsync"]
CMD ["--help"]
