#!/usr/bin/env bash
# Fail unless every commit in a range is karpuzmining, with no co-author trailer.
set -euo pipefail

name="karpuzmining"
email="256796049+karpuzmining@users.noreply.github.com"
range="${1:-}"

if [ -z "${range}" ]; then
  echo "usage: scripts/check-authors.sh <git-rev-range>" >&2
  exit 2
fi

if ! commits=$(git rev-list "${range}"); then
  echo "could not read ${range}" >&2
  exit 1
fi

if [ -z "${commits}" ]; then
  echo "no commits in ${range}"
  exit 0
fi

fail=0
while IFS= read -r commit; do
  author_name=$(git log -1 --format='%an' "${commit}")
  author_email=$(git log -1 --format='%ae' "${commit}")
  committer_name=$(git log -1 --format='%cn' "${commit}")
  committer_email=$(git log -1 --format='%ce' "${commit}")
  body=$(git log -1 --format='%B' "${commit}")
  if [ "${author_name}" != "${name}" ] || [ "${author_email}" != "${email}" ] \
    || [ "${committer_name}" != "${name}" ] || [ "${committer_email}" != "${email}" ]; then
    echo "bad identity ${commit}: author ${author_name} <${author_email}> committer ${committer_name} <${committer_email}>" >&2
    fail=1
  fi
  if printf '%s\n' "${body}" | grep -qi '^[[:space:]]*co-authored-by:'; then
    echo "co-authored-by trailer in ${commit}" >&2
    fail=1
  fi
done <<< "${commits}"

if [ "${fail}" -ne 0 ]; then
  exit 1
fi
echo "identity ok for ${range}"
