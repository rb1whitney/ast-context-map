#!/usr/bin/env bash
# Fetch corpus repositories at the commits recorded in corpus-shas.tsv.
# Usage: corpus/clone_corpus.sh gson yapf brotli ...   (clones into research/graph-of-graphs/<repo>)
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dest="$(dirname "$here")"
[ "$#" -gt 0 ] || { echo "usage: $0 <repo> [<repo> ...]" >&2; exit 2; }
for repo in "$@"; do
  line="$(awk -F'\t' -v r="$repo" '$1 == r {print $2 "\t" $4}' "$here/corpus-shas.tsv")"
  [ -n "$line" ] || { echo "unknown repo: $repo" >&2; exit 1; }
  sha="${line%%$'\t'*}"
  remote="${line#*$'\t'}"
  if [ -d "$dest/$repo/.git" ]; then
    echo "$repo: already present, skipping"
    continue
  fi
  git init -q "$dest/$repo"
  git -C "$dest/$repo" remote add origin "$remote"
  git -C "$dest/$repo" fetch -q --depth 1 origin "$sha"
  git -C "$dest/$repo" checkout -q FETCH_HEAD
  echo "$repo: $sha"
done
