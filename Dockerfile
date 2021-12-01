FROM python:3.9-alpine AS builder
WORKDIR /home/kobodl

RUN apk add --no-cache gcc libc-dev libffi-dev
RUN pip install poetry

COPY . .

RUN poetry env use system
RUN poetry config virtualenvs.create false
RUN poetry install
RUN poetry build

# Distributable Stage
FROM python:3.9-alpine
WORKDIR /home/kobodl

RUN apk add --no-cache tini

COPY --from=builder /home/kobodl /home/kobodl
COPY --from=builder /usr/local/ /usr/local/

RUN mkdir /home/config && chmod 555 /home/config

ENTRYPOINT ["/sbin/tini", "--", "kobodl"]
