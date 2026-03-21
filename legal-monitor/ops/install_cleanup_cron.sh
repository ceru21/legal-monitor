#!/usr/bin/env bash
set -euo pipefail

CRON_LINE='17 3 * * * cd /root/.openclaw/workspace/legal-monitor && . .venv/bin/activate && python scripts/cleanup_runs.py >> /root/.openclaw/workspace/legal-monitor/logs/cleanup.log 2>&1'

( crontab -l 2>/dev/null | grep -Fv 'scripts/cleanup_runs.py' ; echo "$CRON_LINE" ) | crontab -
echo "Installed cleanup cron: $CRON_LINE"
