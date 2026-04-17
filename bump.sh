#!/bin/bash
set -e

NEW_VERSION="$1"
[[ -z "$NEW_VERSION" ]] && { echo "Usage: bash bump.sh <version>  (e.g. 1.0.2)"; exit 1; }

sed -i "s/^version = \".*\"/version = \"$NEW_VERSION\"/" pyproject.toml

git add pyproject.toml
git commit -m "Bump version to $NEW_VERSION"
git tag "$NEW_VERSION"

echo "Version bumped to $NEW_VERSION. Run: git push && git push --tags"
