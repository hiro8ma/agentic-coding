FROM golang:1.24-alpine AS build
WORKDIR /src
COPY go.mod ./
COPY main.go ./
RUN CGO_ENABLED=0 go build -o /out/labdemo .

FROM alpine:3.20
COPY --from=build /out/labdemo /usr/local/bin/labdemo
ENTRYPOINT ["/usr/local/bin/labdemo"]
