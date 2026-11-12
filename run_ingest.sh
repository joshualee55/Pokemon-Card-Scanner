#!/bin/bash
# keep retrying until the API serves the whole catalogue (exit 0 = reached the last page)
cd "$(dirname "$0")"
until python -m app.ingest; do echo "restarting in 20s"; sleep 20; done
