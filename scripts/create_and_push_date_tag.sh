#!/bin/bash
#
# 日付+連番タグを作成して push するユーティリティ
#
# 形式: vYYYYMMDD.N
# 例: v20260301.1, v20260301.2
#
# 使用方法:
#   ./scripts/create_and_push_date_tag.sh
#   ./scripts/create_and_push_date_tag.sh "タグメッセージ"
#   ./scripts/create_and_push_date_tag.sh --publish-release
#   ./scripts/create_and_push_date_tag.sh --publish-release "タグメッセージ"
#
# オプション:
#   --publish-release  タグ push 後に GitHub Release を作成/公開する
#

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./scripts/create_and_push_date_tag.sh [--publish-release] [message]

Options:
  --publish-release  タグ push 後に GitHub Release を作成/公開する
  -h, --help         このヘルプを表示する
EOF
}

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

TAG_PREFIX="v"
TODAY="$(date +%Y%m%d)"
PUBLISH_RELEASE=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    --publish-release)
      PUBLISH_RELEASE=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      break
      ;;
  esac
done

MESSAGE="${1:-release ${TODAY}}"

echo "Fetching tags..."
git fetch --tags --quiet

last_number="$(git tag --list "${TAG_PREFIX}${TODAY}.*" | sed -E "s/^${TAG_PREFIX}${TODAY}\.([0-9]+)$/\1/" | sort -n | tail -1)"

if [ -z "${last_number}" ]; then
  next_number=1
else
  next_number=$((last_number + 1))
fi

tag_name="${TAG_PREFIX}${TODAY}.${next_number}"

if git rev-parse "${tag_name}" >/dev/null 2>&1; then
  echo "Tag already exists: ${tag_name}" >&2
  exit 1
fi

echo "Creating tag: ${tag_name}"
git tag -a "${tag_name}" -m "${MESSAGE}"

echo "Pushing tag: ${tag_name}"
git push origin "${tag_name}"

if $PUBLISH_RELEASE; then
  if ! command -v gh >/dev/null 2>&1; then
    echo "gh command not found. Install GitHub CLI to publish release." >&2
    exit 1
  fi

  if ! gh auth status >/dev/null 2>&1; then
    echo "gh is not authenticated. Run 'gh auth login' first." >&2
    exit 1
  fi

  echo "Creating GitHub Release for tag: ${tag_name}"
  gh release create "${tag_name}" \
    --title "${tag_name}" \
    --generate-notes
  echo "Release published: ${tag_name}"
fi

echo "DONE: ${tag_name}"
