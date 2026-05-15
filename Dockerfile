FROM golang:1.25-alpine AS builder
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /kobodl .

FROM gcr.io/distroless/static-debian12
COPY --from=builder /kobodl /kobodl
ENTRYPOINT ["/kobodl"]
