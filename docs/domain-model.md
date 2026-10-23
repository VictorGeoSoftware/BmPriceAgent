# Domain Model

## Core Concepts

### 1. Repsol Price Proposal (`REPSOL_Precios_Resumen`)
A single-page tabular summary PDF containing:
- **2.0TD section (`POTENCIA HASTA 10kW` and `POTENCIA CONTRATADA DE +10kW`):** Residential (`RES <10KW`, `RES <15KW`) and SME (`PYME 10-15KW`) rows.
- **3.0TD section (`POTENCIA CONTRATADA DE +10kW`):** Business tariffs (`Tarifa Empresa 3.0`, `Tarifa Discriminación Horaria 3.0TD`, `Tarifa Comercio 3.0`, `Tarifa Solar Empresa 3.0TD`, `Tarifa Indexada 3.0TD`).
- **6.1TD section:** High-voltage tariffs (`6.1 TD` / `6.1TD`).
- **GAS section:** `RL.1`–`RL.5` gas rows.
- **Columns:** `NOMBRE DEL PRODUCTO`, tariff code (`2.0TD`, `3.0TD`, `6.1 TD`, `GAS`), channel tier (`A`, `S`, `C`, `SC`, `P`), energy terms `TE1`–`TE6` (printed in `c€/kWh`), and power terms `TP1`–`TP6` (printed in `€/kW·día`).

### 2. Whitelisted Repsol `Producto` Set
Only 5 rows from the Repsol summary table are valid domain products for the BM comparator:

| # | Verbatim `producto.name` | Tariff | Printed `TE` (`c€/kWh`) | Canonical `preciosEnergia` (`€/kWh`) | Canonical `preciosPotencia` (`€/kW·día`) | `descuentoEnergiaPct` |
|---|---|---|---|---|---|---|
| 1 | `Tarifa Sin Horarios 2.0TD_PB RES <10KW AV` | `2.0TD` | `TE1 = 13,99` | `P1–P3 = 0.1399`, `P4–P6 = null` | `P1–P2 = 0.0901`, `P3–P6 = null` | `null` |
| 2 | `Tarifa Sin Horarios Hogar 2.0TD_PB RES <10KW AV + SVA` | `2.0TD` | `TE1 = 12,99` | `P1–P3 = 0.1299`, `P4–P6 = null` | `P1–P2 = 0.0901`, `P3–P6 = null` | `null` |
| 3 | `Tarifa Sin Horarios 2.0TD_PB RES <10KW MV` | `2.0TD` | `TE1 = 11,99` | `P1–P3 = 0.1199`, `P4–P6 = null` | `P1–P2 = 0.0901`, `P3–P6 = null` | `null` |
| 4 | `Batería Virtual 2.0TD_PB RES <15KW GdO MV` | `2.0TD` | `TE1 = 12,99` | `P1–P3 = 0.1299`, `P4–P6 = null` | `P1–P2 = 0.0901`, `P3–P6 = null` | `null` |
| 5 | `Tarifa Empresa 3.0 3.0TD_PB SUPERCLIENTE L8` | `3.0TD` | `TE1–TE6 = 13,99` | `P1–P6 = 0.1399` | `P1 = 0.0573, P2 = 0.0353, P3 = 0.0162, P4 = 0.0134, P5 = 0.0107, P6 = 0.0079` | `null` |

## Relationships
- One uploaded Repsol PDF (`filename: "REPSOL"`) produces 5 `producto` items in `BmPriceAgent`'s response.
- Each `producto` contains one `preciosPotencia.tarifa` entry and one `preciosEnergia.tarifa` entry whose `name` is the normalized access tariff (`2.0TD` or `3.0TD`).
- `BmBackend` transforms each `producto` into a `PriceTableResult` keyed by `(fileName = "REPSOL - <producto.name>", companyName = "REPSOL")` and stores child rows in `termino_de_potencia` and `termino_de_energia`.
- `ProposalCalculationUtils.kt` joins stored `PriceTableResult` rows with a customer's `CleanedConsumptionData` by `tarifaType` (`2.0TD` or `3.0TD`) and multiplies period-by-period power (`kW × price × 365`) and energy (`kWh × price`).

## States and Lifecycles
1. **Raw PDF Input:** Uploaded via `BmWeb` or processed via `eval/run_extraction.py`; `pdftotext -layout` extracts text layer.
2. **LLM Structured Extraction:** Gemini reads the text with `SKILL.md` instructions and emits raw printed numbers (`13.99`, `12.99`, `11.99` in `p1`–`p3` for `2.0TD` and `p1`–`p6` for `3.0TD`), `unidadEnergia: "CENT_KWH"`, `unidadPotencia: "EUR_KW_DIA"`, `descuentoEnergiaPct: null`.
3. **Grounding Verification:** `ungrounded_values()` checks that every raw number (`13.99`, `12.99`, `11.99`, `0.0901`, `0.0573`, etc.) literally exists in the extracted text layer. Repeating `TE1` into `p2` and `p3` passes grounding because `ungrounded_values()` checks membership against the set of printed numbers in the document.
4. **Deterministic Normalization:** `apply_discounts()` strips `descuentoEnergiaPct: null`; `normalize_units()` multiplies `CENT_KWH` energy values by `0.01` ($\rightarrow$ `0.1399`, `0.1299`, `0.1199`) and strips `unidadPotencia` / `unidadEnergia`.
5. **Persistence & Notification (`BmBackend`):** Upserted into PostgreSQL (`price_table_results`) and broadcast via `DebouncingPriceUpdatesNotifier` to connected `BmApp` / `PowerAppWeb` clients.

## Important Scenarios
- **Scenario 1 — `2.0TD` customer comparison with Repsol `Sin Horarios`:** A `2.0TD` customer has consumption in `P1`, `P2`, and `P3`. Because `p1`, `p2`, and `p3` are all populated with the flat `€/kWh` price (`0.1399`, `0.1299`, or `0.1199`), `ProposalCalculationUtils.kt` prices 100% of the customer's annual kWh.
- **Scenario 2 — `3.0TD` customer comparison with Repsol `Empresa 3.0`:** Only `Tarifa Empresa 3.0 3.0TD_PB SUPERCLIENTE L8` (`0.1399 €/kWh` across `P1`–`P6`) appears in the comparator alongside other providers' `3.0TD` offers; the higher-priced `AGENCIA L0`, `ESTANDAR L2`, and `CLIENTE L4` tiers are omitted.
- **Scenario 3 — Excluded rows:** `Tarifa Tranquilísima 5 Años`, `Tarifa Luz M+`, `Tarifa Sin Horarios Hogar ... BV + SVA` (`10,99`), `Tarifa Ahorro Renovable`, `Tarifa 10 horas con Descuento`, `Tarifa 2ª Residencia`, `Tarifa Solar`, `Tarifa Sin Horarios PYME`, `Tarifa Indexada`, `6.1TD` rows, and all `GAS` rows are ignored.

## Edge Cases
- **Single `TE1` column for flat `2.0TD` rows:** Even though `TE2` and `TE3` cells are blank in the PDF for `Tarifa Sin Horarios` and `Batería Virtual`, they represent a 24h flat rate and must fill `p1`–`p3` (never `p4`–`p6`).
- **Floating-point representation during `/100` conversion:** In Python, `12.99 * 0.01` produces `0.12990000000000002`. Both `eval/run_eval.py` (`1e-6` tolerance) and `eval/source_check.py` handle IEEE-754 float representation consistently with existing golden files.
- **Channel codes (`A`, `S`, `C`, `SC`, `P`):** Printed between the tariff column and `TE1`; must never be appended to `producto.name` or misread as prices.
