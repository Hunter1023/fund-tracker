#!/bin/bash

# 进入项目目录
cd "$(dirname "$0")"

# 启动开发环境
docker compose -f docker-compose.dev.yml up
