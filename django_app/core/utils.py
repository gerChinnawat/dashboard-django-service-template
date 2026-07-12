def classify_temperature(avg_temp, max_temp):
    """Pure classification, no I/O -- trivially unit-testable in isolation
    (see docs/LAYER_GUIDELINES.md, "Util")."""
    if max_temp >= 32:
        return "critical"
    if avg_temp >= 28:
        return "warning"
    return "ok"
