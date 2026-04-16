#!/bin/bash
# Run TermZilla application

cd "$(dirname "$0")"
exec .venv/bin/python -m termzilla.main "$@"
