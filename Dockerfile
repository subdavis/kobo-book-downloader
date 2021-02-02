FROM python:3.9-alpine AS builder

# Copy only setup.py to utilize build cache
WORKDIR /home
COPY setup.py README.md ./
RUN apk add --no-cache gcc tini libc-dev \
  && pip3 install .

FROM python:3.9-alpine
RUN apk add --no-cache tini
WORKDIR /home
COPY --from=builder /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
COPY . .
RUN pip3 install --no-deps .

ENTRYPOINT ["/sbin/tini", "--", "kobodl"]
