#!/bin/bash

cd "$(dirname "$0")"

bash scripts/init-env.sh

docker compose -f docker-compose.dev.yml down
docker compose -f docker-compose.dev.yml up -d
