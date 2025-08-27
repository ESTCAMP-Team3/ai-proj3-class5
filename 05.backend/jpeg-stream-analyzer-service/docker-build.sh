#!/bin/bash

docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t harbor.dongango.com/aiclass5/zolgima-mpipe:0.7 \
  -f Dockerfile . \
  --push
