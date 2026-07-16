#!/usr/bin/env bash
set -euo pipefail

# Release script for fastauthmcp
# Usage:
#   ./scripts/release.sh patch    # 0.1.0 → 0.1.1
#   ./scripts/release.sh minor    # 0.1.0 → 0.2.0
#   ./scripts/release.sh major    # 0.1.0 → 1.0.0
#   ./scripts/release.sh 0.3.0    # explicit version

BUMP="${1:-patch}"

# Ensure we're on main
BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "main" ]; then
  echo "Error: releases must be cut from 'main'. You're on '$BRANCH'."
  echo "Merge your release branch first, then run this script."
  exit 1
fi

# Ensure working tree is clean
if [ -n "$(git status --porcelain)" ]; then
  echo "Error: working tree is dirty. Commit or stash changes first."
  exit 1
fi

# Ensure we're up to date with remote
git fetch origin main
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
if [ "$LOCAL" != "$REMOTE" ]; then
  echo "Error: local main is not in sync with origin/main. Pull first."
  exit 1
fi

# Get current version from pyproject.toml
CURRENT=$(grep '^version' pyproject.toml | head -1 | sed 's/version = "\(.*\)"/\1/')
echo "Current version: $CURRENT"

# Calculate new version
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT"

case "$BUMP" in
  patch)
    NEW_VERSION="$MAJOR.$MINOR.$((PATCH + 1))"
    ;;
  minor)
    NEW_VERSION="$MAJOR.$((MINOR + 1)).0"
    ;;
  major)
    NEW_VERSION="$((MAJOR + 1)).0.0"
    ;;
  *)
    # Assume explicit version
    if [[ ! "$BUMP" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      echo "Error: invalid version '$BUMP'. Use patch/minor/major or X.Y.Z format."
      exit 1
    fi
    NEW_VERSION="$BUMP"
    ;;
esac

echo "New version: $NEW_VERSION"
echo ""

# Confirm
read -p "Release v$NEW_VERSION? [y/N] " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Aborted."
  exit 0
fi

# Bump version in pyproject.toml
if [[ "$OSTYPE" == "darwin"* ]]; then
  sed -i '' "s/^version = \"$CURRENT\"/version = \"$NEW_VERSION\"/" pyproject.toml
else
  sed -i "s/^version = \"$CURRENT\"/version = \"$NEW_VERSION\"/" pyproject.toml
fi
echo "Updated pyproject.toml: $CURRENT → $NEW_VERSION"

# Commit the version bump
git add pyproject.toml
git commit -m "release: v$NEW_VERSION"

# Tag
git tag -a "v$NEW_VERSION" -m "Release v$NEW_VERSION"

# Push commit + tag
git push origin main
git push origin "v$NEW_VERSION"

echo ""
echo "Done! Release v$NEW_VERSION pushed."
echo "  → CI will run tests on the commit"
echo "  → publish.yml will build and upload to PyPI"
echo "  → Check: https://github.com/enzomar/fastauthmcp/actions"
