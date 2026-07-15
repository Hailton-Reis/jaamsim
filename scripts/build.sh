#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

command -v java >/dev/null || { echo "Java was not found. Install JDK 25." >&2; exit 1; }
command -v ant >/dev/null || { echo "Apache Ant was not found. Install Ant 1.10+." >&2; exit 1; }

ant -f "$repo_root/build.xml" clean jar

jar_path="$repo_root/build/jars/JaamSim2026-03.jar"
test -f "$jar_path"
jar tf "$jar_path" | grep -qx 'com/jaamsim/ui/AIAssistantBox.class'
jar tf "$jar_path" | grep -qx 'com/jaamsim/ui/StatFitAssistantBox.class'

printf 'BUILD_OK %s\n' "$jar_path"

