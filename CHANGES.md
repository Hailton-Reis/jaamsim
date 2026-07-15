# Changes from upstream JaamSim

Base: official JaamSim tag `v2026-03`, commit `5b4d13ef4e6e354dfb66a97f9573f659f06764b1`.

## Academic assistant extension

### New files

- `src/main/java/com/jaamsim/ui/AIAssistantBox.java`: native simulation assistant shell;
- `src/main/java/com/jaamsim/ui/StatFitAssistantBox.java`: native StatFit-like assistant shell;
- `extensions/academic-assistant/`: Python helpers, synthetic examples, tests, and local output directory;
- `docs/academic-assistant/`: architecture, research scope, and screenshots;
- `scripts/build.ps1` and `scripts/build.sh`: reproducible build checks.

### Modified upstream files

- `src/main/java/com/jaamsim/ui/GUIFrame.java`: adds Tools menu entries, toolbar actions, assistant-window lifecycle, and completion notification hooks;
- `src/main/java/com/jaamsim/events/EventManager.java`: exposes an implementation descriptor used by the academic evidence layer;
- `src/main/java25/com/jaamsim/events/EventManager.java`: aligns the Java 25 implementation descriptor;
- `build.xml`: sets source encoding explicitly for reproducible UTF-8 compilation;
- `make/JS64.exe4j`: enables the JVM native-access option needed by the current packaged runtime.

## Public cleanup

- replaced private thesis-directory discovery with `JAAMSIM_ASSISTANT_ROOT` / `jaamsim.assistant.root`;
- moved generated output to `extensions/academic-assistant/output/`;
- removed private secret-bank path discovery;
- added Apache-2.0 headers to new source files;
- included only synthetic examples and tests;
- excluded academic documents, third-party PDFs, credentials, logs, build output, and local evidence.

