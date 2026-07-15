# Architecture

## Components

### Native Java layer

`GUIFrame` exposes the simulation and StatFit-like assistants. The two windows orchestrate helper processes and present status to the operator. They do not contain the RCL implementation.

### Python deterministic core

- `jaamsim_cfg_to_snapshot.py` parses a supported subset of `.cfg` into JSON;
- `snapshot_analyzer.py` evaluates RCL rules and emits JSON/Markdown evidence;
- `modulo_ia_offline.py` adds structured suggestions, decision status, and audit output;
- `statfit_auxiliar.py` performs local numerical screening;
- `statfit_data_assist.py` prepares pasted or tabular input.

### Optional language-model layer

`tcc_llm_assist.py`, `simulation_chat_assist.py`, and `simulation_briefing_assist.py` can call configured providers. They are not used by the deterministic rule engine and should remain optional.

## Batch evidence is parallel

```text
                                 +--------------------+
                                 | JaamSim batch run  |
                                 | .cfg -> .dat       |
                                 +----------+---------+
                                            |
.cfg ----------------------+                 |
                           |                 v
                           |          numerical evidence
                           |
                           v
                +---------------------+
                | cfg snapshot parser |
                +----------+----------+
                           |
                           v
                      JSON snapshot
                           |
                           v
                       RCL engine
                           |
                           v
                   structural evidence
```

The two evidence sets can be reported together. Neither one is derived from the other.

## Trust boundaries

1. JaamSim remains the simulation engine.
2. RCL findings are deterministic and traceable to source data.
3. Suggestions do not modify a model without operator acceptance.
4. Online assistance is optional and advisory.
5. Output directories are local and ignored by Git.

## Extension discovery

The Java UI resolves the extension root in this order:

1. JVM property `jaamsim.assistant.root`;
2. environment variable `JAAMSIM_ASSISTANT_ROOT`;
3. current directory or an ancestor containing `extensions/academic-assistant`.

The root is accepted only when the required Python helper is present.

