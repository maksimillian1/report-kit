#!/usr/bin/env bash
set -eo pipefail

REPO="maksimillian1/report-kit"
BRANCH="master"
MODE="full"
TARGET_DIR=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --minimal)
      MODE="minimal"
      shift
      ;;
    *)
      if [[ -z "$TARGET_DIR" ]]; then
        TARGET_DIR="$1"
      else
        echo "Error: Too many arguments."
        echo "Usage: bash bootstrap.sh [--minimal] <target-directory>"
        exit 1
      fi
      shift
      ;;
  esac
done

if [[ -z "$TARGET_DIR" ]]; then
  echo "Error: Target directory not specified."
  echo "Usage: bash bootstrap.sh [--minimal] <target-directory>"
  exit 1
fi

echo "-> Bootstrapping report-kit into '$TARGET_DIR' (Mode: $MODE)..."

# Create target and download via GitHub API
mkdir -p "$TARGET_DIR"
TAR_URL="https://github.com/${REPO}/archive/refs/heads/${BRANCH}.tar.gz"

echo "-> Fetching $TAR_URL..."
curl -sL "$TAR_URL" | tar -xz -C "$TARGET_DIR" --strip-components=1

# Post-processing based on mode
cd "$TARGET_DIR"

if [[ "$MODE" == "minimal" ]]; then
  echo "-> Applying minimal layout..."

  # Remove multi-execution overhead
  rm -rf benchmarks
  rm -rf executions/00-baseline

  # Promote template to standard execution
  mv executions/_template execution
  rm -rf executions

  # Remove specific instructions from README if needed, or leave as is
else
  echo "-> Applying full multi-execution layout..."
fi

# Cleanup repository-only files
rm -rf .git
rm -f bootstrap.sh .gitignore README.md methodology.md

echo "-> Done. Report skeleton ready in '$TARGET_DIR'."
