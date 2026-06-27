#!/bin/bash
# Cron launcher for Rocky News Digest
# Sources .env from nature_digest (same email/API/proxy credentials)

ENV_FILE="/Users/lenia/claude/nature_digest/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "$(date): .env not found at $ENV_FILE" >> /Users/lenia/claude/news_digest/news_digest.log
    exit 1
fi

set -a
source "$ENV_FILE"
set +a

cd /Users/lenia/claude/news_digest
/opt/anaconda3/bin/python3 -u news_digest.py >> news_digest.log 2>&1
