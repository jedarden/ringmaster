FROM docker.io/library/golang:1.22-alpine AS builder
WORKDIR /app
COPY main.go .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o zai-proxy main.go

FROM docker.io/library/alpine:3.19
RUN apk add --no-cache ca-certificates
COPY --from=builder /app/zai-proxy /zai-proxy
EXPOSE 8080
ENTRYPOINT ["/zai-proxy"]
