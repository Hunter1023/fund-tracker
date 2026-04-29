#!/bin/bash

cd "$(dirname "$0")"

bash scripts/init-env.sh

docker compose -f docker-compose.yml down
docker compose -f docker-compose.yml up -d
