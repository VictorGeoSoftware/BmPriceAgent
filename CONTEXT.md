# Context

## Glossary

### BmPriceAgent
FastAPI microservice (`port 5002`) that extracts electricity price tables from Spanish energy provider PDFs using `pdftotext` (or Gemini vision fallback for scanned PDFs), the `price-proposal-extraction` skill prompt, and deterministic post-processing.

### Price Proposal PDF
Commercial rate sheet (`propuesta de precios`) issued by a Spanish electricity retailer (`comercializadora`, e.g., `REPSOL`, `ENDESA`, `IBERDROLA`, `ADX`, `ELEIA`, `TOTAL`, `GESTERNOVA`).

### Producto
A single commercial electricity offer extracted into the `producto` array of the `/extract-price-tables` JSON payload. Its `name` is copied verbatim from the document and serves as the natural upsert key in `BmBackend` (`<PROVIDER> - <producto.name>`).

### Provider Whitelist
Explicit business selection rule restricting which printed rows in a provider's PDF are emitted as `producto` entries. Used when a provider's summary sheet mixes residential, SME, indexed, solar, and channel-tier variants that should not clutter the broker comparator.

### Tarifa (Access Tariff)
Regulatory Spanish electricity access tariff code normalized without spaces (`2.0TD` for $\le 15\text{ kW}$, `3.0TD` for $> 15\text{ kW}$ low voltage, `6.1TD`–`6.4TD` for high voltage).

### Término de Potencia (`TP1`–`TP6`)
Contracted power prices per regulatory period. `2.0TD` uses `P1`–`P2` (`P3`–`P6` are `null`); `3.0TD` and `6.xTD` use `P1`–`P6`. Canonical unit returned by `BmPriceAgent` is `€/kW·día` (`EUR_KW_DIA`).

### Término de Energía (`TE1`–`TE6`)
Consumed energy prices per regulatory period. `2.0TD` uses `P1`–`P3` (`P4`–`P6` are `null`); `3.0TD` and `6.xTD` use `P1`–`P6`. Canonical unit returned by `BmPriceAgent` is `€/kWh` (`EUR_KWH`).

### Flat Energy Tariff (`Tarifa Plana` / `Sin Horarios`)
An electricity offer charging a single 24h energy price across all active regulatory periods of its access tariff. In Repsol `2.0TD` summary tables, this single price is printed only under the `TE1` column (`TE2`–`TE6` blank) but applies across `P1`–`P3`.

### Printed Unit vs. Canonical Unit
The LLM reports numbers exactly as printed in the PDF and declares `unidadPotencia` (`EUR_KW_DIA`, `EUR_KW_MES`, `EUR_KW_ANO`) and `unidadEnergia` (`EUR_KWH`, `CENT_KWH`). Deterministic code in `normalize.py` converts values to canonical units (`€/kW·día` and `€/kWh`) and strips the unit fields before returning.

### Grounding Check
Runtime and eval verification step (`ungrounded_values` / `eval/source_check.py`) asserting that every pre-conversion numeric price emitted by the LLM literally exists in the PDF's extracted text layer.

### Golden Corpus
The 30 deduplicated reference PDFs and their approved canonical JSON outputs under `.devin/skills/price-proposal-extraction/eval/golden/`, gated by `eval/run_eval.py`.

### Source SHA-256 Deduplication
`BmBackend` check (`isSourceAlreadyStored(sourceSha256)`) that skips re-extraction if a PDF with identical bytes already has rows in `price_table_results`.

## Rejected / Ambiguous Terms

### "All Periods" (`todos los periodos`) for `2.0TD`
Use `Tariff-Active Energy Periods (P1–P3 for 2.0TD)` instead. Reason: Repsol's summary table shares `TE1`–`TE6` column headers across `2.0TD`, `3.0TD`, and `6.1TD`, but `2.0TD` only has 3 regulatory energy periods (`P1`–`P3`). Filling `P4`–`P6` on `2.0TD` violates the `SKILL.md` contract.

### "Extracting the PDF" as Dumping Every Row
Use `Provider Whitelist Extraction` for curated providers (`ENDESA`, `IBERDROLA`, `REPSOL`). Reason: extracting all 30 rows of a Repsol summary sheet pollutes the broker comparator with unused channel tiers, indexed margins (`2,5` / `1,5` c€/kWh), and unoffered tariffs.
