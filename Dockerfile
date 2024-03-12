FROM python:3.9-alpine AS builder
WORKDIR /opt/kobodl/src

ENV PATH="/opt/kobodl/local/venv/bin:$PATH"
ENV VIRTUAL_ENV="/opt/kobodl/local/venv"

RUN apk add --no-cache gcc libc-dev libffi-dev ffmpeg
ADD https://install.python-poetry.org /install-poetry.py
RUN POETRY_VERSION=1.1.7 POETRY_HOME=/opt/kobodl/local python /install-poetry.py

COPY . .

RUN poetry env use system
RUN poetry config virtualenvs.create false
RUN poetry debug
RUN poetry install --no-dev

# Distributable Stage
FROM python:3.9-alpine
WORKDIR /opt/kobodl/src

ENV PATH="/opt/kobodl/local/venv/bin:$PATH"

RUN apk add --no-cache tini

COPY --from=builder /opt/kobodl /opt/kobodl

ENTRYPOINT ["/sbin/tini", "--", "kobodl"]
