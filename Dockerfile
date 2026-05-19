FROM golang:1.26.3-alpine3.22 AS builder

WORKDIR /app

# 1. Copy package files first for caching
COPY go.mod go.sum ./

# 2. Install dependencies
RUN go mod download

# 3. Copy remaining source code
COPY . .
RUN CGO_ENABLED=0 go build -o glance .

FROM alpine:3.22

WORKDIR /app
COPY --from=builder /app/glance .

EXPOSE 8080/tcp
ENTRYPOINT ["/app/glance", "--config", "/app/config/glance.yml"]
