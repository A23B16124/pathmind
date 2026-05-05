#!/bin/bash
# Auto-deploy: pull main changes and rebuild if master branch advanced.
set -e

REPO="/home/ubuntu/pathmind"
BRANCH="master"
LOG="/var/log/pathmind-deploy.log"
LOCK="/tmp/pathmind_deploy.lock"

# Single instance — skip if already running
[ -f "$LOCK" ] && exit 0
trap "rm -f $LOCK" EXIT
touch "$LOCK"

cd "$REPO"

git fetch origin "$BRANCH" --quiet

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")

if [ "$LOCAL" = "$REMOTE" ]; then
  exit 0
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Deploy triggered: $LOCAL -> $REMOTE" >> "$LOG"

git pull origin "$BRANCH" --ff-only --quiet

cd frontend
npm ci --silent >> "$LOG" 2>&1
npm run build >> "$LOG" 2>&1

cd "$REPO"
if [ -f backend/requirements.txt ]; then
  pip install -q -r backend/requirements.txt >> "$LOG" 2>&1 || true
fi

pm2 restart pathmind-frontend pathmind-backend --silent

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Deploy done." >> "$LOG"
