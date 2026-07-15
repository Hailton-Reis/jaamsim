# Research scope and limitations

## Evaluated core

The controlled study evaluates RCL01-RCL10 against six synthetic snapshots: reference and inconsistent variants of C1, C2, and C3.

| Case | Reference | Inconsistent result |
|---|---|---|
| C1 | 0 alerts | 4 alert instances; 4 unique rules |
| C2 | 0 alerts | 8 alert instances; 5 unique rules |
| C3 | 0 alerts | 3 alert instances; 3 unique rules |

RCL11-RCL26 are implemented as technical extensions but were not evaluated with the same quantitative matrix.

## What the evidence supports

- the deterministic engine reproduces the expected controlled findings;
- the synthetic `.cfg` cases run in JaamSim batch mode;
- supported `.cfg` files can be converted directly into snapshots;
- evidence can be generated repeatedly in machine-readable and human-readable forms.

## What the evidence does not support

- general validity for arbitrary industrial models;
- complete parsing of the JaamSim configuration language;
- absence of false positives or false negatives;
- behavioral validation against a real system;
- autonomous correction of a simulation model;
- claims that an LLM validates a model.

## Known heuristic risks

- RCL09 uses a narrow name-based inspection/processing heuristic;
- RCL24 uses lexical time, unit, and distribution signals;
- some expanded rules require an explicit parameter contract before they can trigger;
- undocumented information cannot be inferred reliably from structure alone.

## Recommended next evaluation

1. create a dedicated matrix for RCL11-RCL26;
2. test progressively larger public JaamSim models;
3. measure per-rule precision, recall, and reviewer agreement;
4. compare tool-assisted and unaided human reviews;
5. publish a formal snapshot schema and parser compatibility table.

