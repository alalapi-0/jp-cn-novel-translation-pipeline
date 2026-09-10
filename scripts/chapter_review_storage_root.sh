#!/bin/zsh
set -eu

fail() {
  print -u2 -- "chapter-review storage: $*"
  exit 78
}

readonly guard=/Users/alalapi/.config/storage-governance/guard.sh
readonly map_key=mappings.light_novel.chapter_review_root
readonly expected_root=/Volumes/AI_WORK_SSD/ProjectData/light_novel/chapter_review

[[ -x "$guard" ]] || fail "storage guard is missing or not executable"
resolved_root="$("$guard" --get-path "$map_key")" || fail "external storage identity or map validation failed"
[[ "$resolved_root" == "$expected_root" ]] || fail "mapped root drifted from the project contract"
[[ -d "$resolved_root" && -r "$resolved_root" && -w "$resolved_root" ]] || fail "mapped root is unavailable or not writable"

case "${1:---check}" in
  --check)
    [[ "$#" -eq 1 ]] || fail "--check takes no additional arguments"
    print -- "chapter-review storage: OK $resolved_root"
    ;;
  --root)
    [[ "$#" -eq 1 ]] || fail "--root takes no additional arguments"
    print -r -- "$resolved_root"
    ;;
  --path)
    [[ "$#" -eq 2 ]] || fail "--path requires one relative path"
    relative_path="$2"
    [[ -n "$relative_path" && "$relative_path" != /* ]] || fail "path must be relative"
    case "/$relative_path/" in
      */../*|*/./*|*//*) fail "path traversal or empty components are forbidden" ;;
    esac
    print -r -- "$resolved_root/$relative_path"
    ;;
  *)
    fail "unknown argument: $1"
    ;;
esac
