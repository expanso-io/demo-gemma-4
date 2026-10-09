#!/usr/bin/env bash
# Source this helper, then demo_ports_load /absolute/demo/path [--allow-bound].
# No shell evaluation: allocator output contains validated names and decimals.
demo_ports_load() {
    local demo_dir="$1" name value output allocator
    shift
    allocator="${demo_dir}/scripts/demo-ports.py"
    [[ -f "$allocator" ]] || allocator="${demo_dir}/../_demo-kit/demo-ports.py"
    output=$(uv run --no-project "$allocator" resolve --demo-dir "$demo_dir" --format shell "$@") || return
    while IFS='=' read -r name value; do
        [[ -z "$name" ]] && continue
        [[ "$name" =~ ^[A-Z][A-Z0-9_]*$ && "$value" =~ ^[0-9]+$ ]] || return 1
        export "$name=$value"
    done <<< "$output"
}
