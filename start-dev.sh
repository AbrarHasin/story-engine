#!/bin/bash
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
pkill -f uvicorn 2>/dev/null; pkill -f vite 2>/dev/null; sleep 1
cd /home/abrar/code/story-engine/backend
nohup .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload > /tmp/backend.log 2>&1 &
echo backend:$!
cd /home/abrar/code/story-engine/frontend
nohup npm run dev -- --host > /tmp/frontend.log 2>&1 &
echo frontend:$!
