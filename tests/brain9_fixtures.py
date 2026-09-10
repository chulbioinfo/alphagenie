"""Small metadata-only fixtures; production always uses the full sealed registry."""
import pandas as pd
from worker import brain9


def small_catalog():
    full = brain9.registry()
    return {key: value for group, _ in brain9.FULL_GROUP_ORDER
            for key, value in [next((k, v) for k, v in full.items() if v["display_group"] == group)]}


def score_row(index, value, null_id=None):
    metadata = list(small_catalog().values())[index]
    row = {field: metadata[field] for field in brain9.CLASS_FIELDS}
    row.update(variant_group_id="TEST_del3", output_type="RNA_SEQ", variant_scorer="GeneMaskLFCScorer",
               gene_name="TEST", raw_score=value)
    if null_id is not None:
        row["null_id"] = null_id
    return row


def frames(count=3):
    real = pd.DataFrame([score_row(g, 2) for g in range(11)])
    null = pd.DataFrame([score_row(g, float(i), str(i)) for i in range(count) for g in range(11)])
    return real, null
