# Academic assistant extension

This directory is the portable root used by the native JaamSim windows.

Set `JAAMSIM_ASSISTANT_ROOT` to this directory when JaamSim is launched outside the repository root.

## Direct commands

```powershell
python python\snapshot_analyzer.py
python python\modulo_ia_offline.py examples\jaamsim\c1_fila_simples_inconsistente.cfg
python python\statfit_auxiliar.py examples\statfit\exemplo_dados_tempos.csv --column tempo_atendimento
```

Generated artifacts are written to `output/` and are ignored by Git.

