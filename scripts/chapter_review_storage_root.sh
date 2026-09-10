#!/bin/zsh
set -eu

fail() {
  print -u2 -- "chapter-review storage: $*"
  exit 78
}

readonly guard=/Users/alalapi/.config/storage-governance/guard.sh
readonly map_key=mappings.light_novel.chapter_review_root
readonly expected_root=/Volumes/AI_WORK_SSD/ProjectData/light_novel/chapter_review
readonly expected_volume=/Volumes/AI_WORK_SSD

device_id() {
  local value
  if value=$(/usr/bin/stat -f '%d' "$1" 2>/dev/null); then
    print -r -- "$value"
  elif value=$(/usr/bin/stat -c '%d' "$1" 2>/dev/null); then
    print -r -- "$value"
  else
    fail "cannot determine filesystem identity: $1"
  fi
}

[[ -x "$guard" ]] || fail "storage guard is missing or not executable"
resolved_root="$("$guard" --get-path "$map_key")" || fail "external storage identity or map validation failed"
[[ "$resolved_root" == "$expected_root" ]] || fail "mapped root drifted from the project contract"
[[ -d "$resolved_root" && ! -L "$resolved_root" && -r "$resolved_root" && -w "$resolved_root" ]] ||
  fail "mapped root is unavailable, redirected, or not writable"
physical_root="$(cd -P -- "$resolved_root" && pwd -P)" ||
  fail "mapped root cannot be resolved physically"
[[ "$physical_root" == "$expected_root" ]] || fail "mapped root escaped its physical contract"
[[ -d "$expected_volume" ]] || fail "expected external volume is unavailable"
root_device="$(device_id "$resolved_root")"
volume_device="$(device_id "$expected_volume")"
[[ "$root_device" == "$volume_device" ]] || fail "mapped root crossed the external filesystem"

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
    components=("${(@s:/:)relative_path}")
    current="$resolved_root"
    integer component_index=0
    for component in "${components[@]}"; do
      (( component_index += 1 ))
      current="$current/$component"
      if [[ -e "$current" || -L "$current" ]]; then
        [[ ! -L "$current" ]] || fail "path contains a symlink: $relative_path"
        [[ "$(device_id "$current")" == "$root_device" ]] ||
          fail "path crossed the external filesystem: $relative_path"
        if (( component_index < ${#components[@]} )); then
          [[ -d "$current" ]] || fail "path ancestor is not a directory: $relative_path"
        fi
      fi
    done
    print -r -- "$current"
    ;;
  *)
    fail "unknown argument: $1"
    ;;
esac
