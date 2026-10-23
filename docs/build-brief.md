# Build Brief

## Problem
Currently, `price-proposal-extraction` and `BmPriceAgent` extract all 30 electricity rows from `REPSOL_Precios_Resumen 260726.pdf` (including unused channel tiers, solar variants, 6.1TD rows, and indexed fee rows) and populate only `p1` (`p2`–`p6 = null`) for Repsol `2.0TD` flat-energy tariffs (`Tarifa Sin Horarios...`, `Batería Virtual...`) because Repsol prints the single price only under column `TE1`.

This causes two production defects in the comparator (`BmBackend` / `BmApp` / `PowerAppWeb`):
1. **Comparator noise and invalid products:** Brokers see 25+ irrelevant or indexed Repsol tariffs instead of the 5 commercial offers curated by the business.
2. **Under-calculated `2.0TD` annual energy cost:** `ProposalCalculationUtils.kt` multiplies `annualConsumptionPi * pricePi` for `P1`–`P6`. When `p2` and `p3` are `null` on a `2.0TD` flat tariff, `P2` and `P3` customer consumption is priced at `0.00 €`.

## Current Workaround / Existing System
- **Skill source of truth:** `/Users/victor/Documents/Personal/Projects/BM/.devin/skills/price-proposal-extraction/SKILL.md`, synced into `/Users/victor/Documents/Personal/Projects/BM/BmPriceAgent/skill/SKILL.md` via `eval/sync_skill.sh`.
- **Service:** `BmPriceAgent` (`FastAPI`, `app/extractor.py`, `app/normalize.py`) extracts structured JSON via Gemini and normalizes units (`CENT_KWH` $\div 100 \rightarrow$ `EUR_KWH`; `EUR_KW_DIA` $\times 1.0$).
- **Eval & Golden Gate:** `.devin/skills/price-proposal-extraction/eval/golden/REPSOL_Precios_Resumen_260726.json` currently locks all 30 electricity rows with `p2: null, p3: null` on `2.0TD` flat tariffs.

## Target Users
- **Brokers (end users of `BmApp` / `PowerAppWeb`):** Compare a customer's current electricity bill against curated commercial proposals, including Repsol's competitive `2.0TD` flat offers and `3.0TD` `SUPERCLIENTE L8` offer.
- **Back-Office Admins (`BmWeb`):** Upload monthly/campaign PDF price sheets from providers and manage stored proposals.

## Goals
1. **Enforce the Repsol Product Whitelist:** Extract only the 5 business-approved electricity products from Repsol summary proposals:
   - `Tarifa Sin Horarios 2.0TD_PB RES <10KW AV` (`2.0TD`)
   - `Tarifa Sin Horarios Hogar 2.0TD_PB RES <10KW AV + SVA` (`2.0TD`)
   - `Tarifa Sin Horarios 2.0TD_PB RES <10KW MV` (`2.0TD`)
   - `Batería Virtual 2.0TD_PB RES <15KW GdO MV` (`2.0TD`)
   - `Tarifa Empresa 3.0 3.0TD_PB SUPERCLIENTE L8` (`3.0TD`)
2. **Repeat `2.0TD` Flat Energy Prices Across `P1`–`P3`:** When a Repsol `2.0TD` flat-energy product prints a single price in `TE1` (`TE2`–`TE6` empty), populate `p1`, `p2`, and `p3` with that price (`p4`–`p6 = null`) so `BmBackend` prices all `2.0TD` consumption periods accurately.
3. **Preserve Final-Price & Unit Rules:** Keep `descuentoEnergiaPct = null` (Repsol printed prices are final), `unidadEnergia = CENT_KWH` ($\div 100$ in `normalize.py`), and `unidadPotencia = EUR_KW_DIA`.
4. **Update Golden Corpus & Keep Regression Gate Green:** Update `REPSOL_Precios_Resumen_260726.json` (and review sheet) and pass `eval/run_eval.py` and `eval/source_check.py` across all 30 corpus PDFs.

## Non-Goals
- **Gas tariff extraction (`GAS` / `RL.1`–`RL.5`):** Mentioned at the end of the briefing video (`01:06–01:17`) as a future topic; excluded from this feature because `BmBackend` only models electricity `P1`–`P6`.
- **Changes to `BmBackend` calculation formulas or HTTP contracts:** `BmPriceAgent` remains a drop-in `/extract-price-tables` service.
- **UI/Visual changes:** Visual design (`DESIGN.md`) is **not applicable** — this change is strictly in extraction prompt rules, skill sync, and golden evaluation artifacts.

## MVP Slice
1. Add a `### REPSOL` subsection under `## Provider selection rules` in `.devin/skills/price-proposal-extraction/SKILL.md` specifying the 5 whitelisted products, `descuentoEnergiaPct = null`, and the `2.0TD` flat-energy `TE1` $\rightarrow$ `P1`–`P3` rule (and align the `REPSOL` bullet under `## Known provider notes` and `## Banded prices and flat prices`).
2. Sync the updated skill into `BmPriceAgent/skill/` via `eval/sync_skill.sh`.
3. Re-run extraction on `REPSOL_Precios_Resumen 260726.pdf`, verify grounding with `eval/source_check.py`, regenerate `eval/review/REPSOL_Precios_Resumen_260726.md`, promote the 5-product output to `eval/golden/REPSOL_Precios_Resumen_260726.json`, and run `eval/run_eval.py`.

## Validation Plan
All verification runs locally on the host using `.devin/skills/price-proposal-extraction/.venv` — **no Docker containers and no full-corpus LLM re-runs**:
1. **Single-file Gemini extraction (~6–8s, 1 API call):**
   `.venv/bin/python eval/run_extraction.py --only REPSOL_Precios_Resumen_260726`
   Verify `eval/candidates/REPSOL_Precios_Resumen_260726.json` contains only the 5 whitelisted products in canonical units (`€/kWh` and `€/kW·día`) with `p1 = p2 = p3` (`p4`–`p6 = null`) on the 4 `2.0TD` products.
2. **Offline grounding & sanity check (~0.2s, 0 API calls):**
   `.venv/bin/python eval/source_check.py --only REPSOL_Precios_Resumen_260726`
   Confirm 0 ungrounded values and 0 sanity violations.
3. **Offline golden regression check (~0.2s, 0 API calls):**
   Promote the verified candidate to `eval/golden/REPSOL_Precios_Resumen_260726.json`, regenerate `eval/review/REPSOL_Precios_Resumen_260726.md`, and run `.venv/bin/python eval/run_eval.py --golden eval/golden --candidates eval/candidates` to confirm 0 diffs.
4. **Skill sync check (<0.1s):**
   `diff -q BmPriceAgent/skill/SKILL.md .devin/skills/price-proposal-extraction/SKILL.md`

## Success Criteria
- `REPSOL_Precios_Resumen 260726.pdf` extracts to exactly the 5 whitelisted products, with `0.1399`, `0.1299`, `0.1199`, `0.1299` repeated across `p1`–`p3` (`p4`–`p6 = null`) for the 4 `2.0TD` products, and `0.1399` across `p1`–`p6` for `Tarifa Empresa 3.0 3.0TD_PB SUPERCLIENTE L8`.
- `BmPriceAgent/skill/SKILL.md` is byte-identical to `.devin/skills/price-proposal-extraction/SKILL.md`.
- `eval/run_eval.py` and `eval/source_check.py` exit with `0` errors.

## Notes
- **Access & Permissions:** No user/role changes. Upload access remains restricted to `admin_users` in `BmWeb` (`POST /api/v1/upload-price-proposal`), and read access for comparisons remains restricted to `granted_users` (`GET /api/v1/price-table-results`); revoking a user or admin grant immediately blocks API access on the next request.
- **Observability & Operations:** `BmPriceAgent` logs extracted product counts, unit conversions (`CENT_KWH -> EUR_KWH`), grounding retries (`UNGROUNDED`), and sanity warnings (`SANITY`) to stdout/Loki. Operational owner is the BM platform maintainer (Victor).
- **Re-upload Operational Note:** Because `BmBackend` deduplicates uploads by `source_sha256` and upserts per product name without deleting removed products, an admin re-uploading an already-stored `REPSOL_Precios_Resumen 260726.pdf` in QA/Prod must delete existing Repsol rows in `BmWeb` first so the 25 excluded products are purged and extraction runs afresh.
