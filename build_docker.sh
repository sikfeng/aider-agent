#!/usr/bin/env bash

docker buildx build --target raider-backend -t sikfeng/raider-backend -f docker/Dockerfile .