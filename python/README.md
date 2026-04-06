# oncell

REST API client for [oncell.ai](https://oncell.ai) — per-customer isolated compute for AI agents.

See the [main README](../README.md) for full documentation.

```python
from oncell import OnCell

oncell = OnCell(api_key="oncell_sk_...")
cell = await oncell.cells.create(customer_id="user-1", tier="standard")
print(cell.preview_url)
```
