# Parking lot

Unresolved items, not yet hashed out.

- **Duplicate endpoint keys in the Cin7 spec.** The parser emits 295 endpoints, but the loader keeps 288: 7 `METHOD path` keys appear more than once upstream (`production/productionBOM` GET/POST/PUT/DELETE, `DELETE purchase/payment`, `GET crm/task` ×3), and the dict keeps the last one. Decide whether to merge them, warn about them, or leave them. (Found during PR #8.)
