# Constraint map (draft)

`bopet_v3.json` is generated from `scenarios/bopet.py` and contains 24 variables.
Each row keeps: bounds, performance window, constraint type, calibration status,
evidence IDs and dependency variables.

This is a **draft/offline registry**, not a plant interlock:
- 16 of 24 variables are `UNCALIBRATED`;
- UNKNOWN is not PASS;
- literature applicability (material/equipment) still needs human verification;
- no row is automatically promoted to a hard safety limit.

Load with:

```python
from services.evidence_mapping import load_mapping, to_variables
data = load_mapping("data/constraints/bopet_v3.json")
variables = to_variables(data)
```
