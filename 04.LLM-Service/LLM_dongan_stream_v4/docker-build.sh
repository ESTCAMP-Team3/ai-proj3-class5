#!/bin/bash

docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t harbor.dongango.com/aiclass5/zolgima-svr:0.6 \
  -f Dockerfile . \
  --push
