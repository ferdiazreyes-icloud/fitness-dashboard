# Constitution: Health Dashboard

## Immutable Principles

1. **Personal dashboard, not a product.** This is a tool for one person (Fernando). Decisions optimize for personal utility, not scalability or multi-tenancy.

2. **The repository must always be private.** The CSVs contain personal health data (heart rate, body composition, sleep, GPS routes). Never make this repo public.

3. **Read-only visualization.** The dashboard only displays data — it never modifies source data. The source of truth is always the Apple Health export and the Strong App export.

4. **MVP over perfection.** The value is in seeing the data, not in architecture. Ship working pages quickly; polish later.

5. **No medical interpretation.** Health metrics are shown as-is. The dashboard does not diagnose, prescribe, or interpret clinical significance.

6. **Weekly manual update is acceptable.** Full automation is a nice-to-have, not a requirement. The export → ETL → push flow runs once a week.
