# Risks and Open Questions

## Blocking Next Phase
- None. All product selection, period-filling, unit, and scope decisions from the Repsol briefing video have been confirmed.

## Implementation-Time Questions
- **Exact prompt wording in `SKILL.md` for Repsol `2.0TD` flat energy:** Ensure the instruction clearly tells the model that the 4 whitelisted Repsol `2.0TD` products (`Tarifa Sin Horarios...` and `Batería Virtual...`) are flat 24h tariffs whose printed `TE1` value must be repeated across `p1`, `p2`, and `p3` (`p4`–`p6 = null`), overriding the general "empty cell = `null`" default for those rows. Verify at `temperature=0` via `eval/run_extraction.py`.

## Later / Not MVP
- **Gas tariff extraction (`GAS` / `RL.1`–`RL.5`):** Raised at `01:06–01:17` in the video (`"habría que empezar también a hablar de tema de gas"`). Requires separate discovery because `BmBackend`, `BmApp`, and `PowerAppWeb` currently model only electricity (`2.0TD` / `3.0TD` / `6.xTD`, periods `P1`–`P6`, `€/kW·día` and `€/kWh`).
- **Excel price proposal support (`.xlsx` / `.xlsm`):** Needed for Iberdrola `Resumen` and other Excel-only providers; tracked separately from this change.
- **Pending Endesa golden sign-off:** Mentioned in `ai-assistance-for-price-proposals.md` Task 5; independent of the Repsol rule update, though `eval/run_eval.py` will run across the full corpus.

## Assumptions
- Repsol keeps the exact commercial product names printed in `REPSOL_Precios_Resumen 260726.pdf` across subsequent campaign updates (`Tarifa Sin Horarios 2.0TD_PB RES <10KW AV`, `Tarifa Sin Horarios Hogar 2.0TD_PB RES <10KW AV + SVA`, `Tarifa Sin Horarios 2.0TD_PB RES <10KW MV`, `Batería Virtual 2.0TD_PB RES <15KW GdO MV`, `Tarifa Empresa 3.0 3.0TD_PB SUPERCLIENTE L8`).
- Repsol printed energy prices in `Resumen` PDFs already reflect final commercial rates (`descuentoEnergiaPct = null`) in `c€/kWh` (`CENT_KWH`), and power prices are printed in `€/kW·día` (`EUR_KW_DIA`).

## Risks
- **Skill drift between `.devin/skills/price-proposal-extraction/` and `BmPriceAgent/skill/`:** Editing only the workspace skill leaves the Docker service running stale instructions. Mitigation: always run `.devin/skills/price-proposal-extraction/eval/sync_skill.sh` and verify both `SKILL.md` copies match.
- **Historical Repsol naming changes (`BODEGA 2026`):** Earlier April 2026 archive PDFs (`REPSOL_Precios_Resumen 270426.pdf`) used internal codes (`2.0TD PRECIO FIJO CDR...`, `3.0TD PRECIO FIJO PRESENCIALES SBC REPOS3 12M L8`) instead of the current commercial names. If Repsol renames products in a future campaign, the whitelist in `SKILL.md` will need updating.
- **Stale rows in QA/Prod databases on re-upload:** `BmBackend` skips extraction when `source_sha256` already exists and upserts by product name without deleting removed products. Mitigation: delete existing `REPSOL` rows in `BmWeb` before re-uploading `REPSOL_Precios_Resumen 260726.pdf` in QA/Prod.

## Research Tasks
- None required before implementation.
