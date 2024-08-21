#!/usr/bin/env bash

docker buildx build --target aider-agent -t sikfeng/aider-agent -f docker/Dockerfile .