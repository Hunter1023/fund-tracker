#!/bin/bash

# 进入项目目录
cd "$(dirname "$0")"

# 启动生产环境
docker compose -f docker-compose.yml down
docker compose -f docker-compose.yml up
