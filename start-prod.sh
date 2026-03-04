#!/bin/bash

# 进入项目目录
cd "$(dirname "$0")"

# 启动生产环境
docker compose up -d
