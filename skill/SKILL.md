---
name: price-proposal-extraction
description: Extract electricity price tables (precios de potencia y energía, periodos P1-P6) from Spanish electricity providers' price proposal PDFs into the BM producto JSON schema. Use when parsing tarifas/precios from propuestas de precios de comercializadoras eléctricas españolas (ADX, ELEIA, TotalEnergies, Gesternova, Endesa, Iberdrola, Repsol, or any new provider).
---

# Price Proposal Extraction

Extract electricity prices from a Spanish provider's price-proposal PDF (or its
extracted text) and emit **exactly** the JSON contract below. This skill replaces
per-provider parser functions: the same rules apply to every provider, known or new.

## Output contract (must match exactly)

```json
{
  "filename": "<PROVIDER>",
  "producto": [
    {
      "name": "<product name as printed, verbatim>",
      "unidadPotencia": "EUR_KW_DIA",
      "unidadEnergia": "EUR_KWH",
      "descuentoEnergiaPct": null,
      "preciosPotencia": { "tarifa": [ { "name": "2.0TD", "p1": 0.0, "p2": null, "p3": null, "p4": null, "p5": null, "p6": null } ] },
      "preciosEnergia":  { "tarifa": [ { "name": "2.0TD", "p1": 0.0, "p2": 0.0, "p3": null, "p4": null, "p5": null, "p6": null } ] }
    }
  ]
}
```

- `filename`: the provider/company name in uppercase short form (ADX, ELEIA, TOTAL,
  GESTERNOVA, ENDESA, IBERDROLA, REPSOL, …). If unknown, best-effort brand name.
- One `producto` entry per commercial product/campaign. A document may contain
  several (e.g. "BRIEL CHEFF 1", "CLASSIC T0", "CLASICA TE1").
- **Product names are identity keys.** Providers never rename a product — a new
  price campaign reuses the exact same name, and the backend upserts by it.
  Copy the printed name VERBATIM, character-for-character: keep accents
  ("CLÁSICA" stays "CLÁSICA"), spacing, and every word. Never abbreviate,
  reformat, or add/drop qualifiers (BASE, UNICA, …). If the same product appears
  twice in the document under slightly different renderings, pick the most
  complete printed form and use it consistently.
- Within each producto, one `tarifa` entry per tariff type found. The entry
  `name` is **always the tariff code** — 2.0TD, 3.0TD, 6.1TD… — never the
  product name, a price-table title, or a band label. Normalize UPPERCASE
  without spaces: `2.0 TD` / `6.1 TD` → `2.0TD` / `6.1TD`. If a product table
  has no tariff label, use the document's tariff of access (stated in the
  proposal, e.g. "Tarifa de acceso: 2.0TD"). Known types: 2.0TD, 3.0TD, 6.1TD,
  6.2TD, 6.3TD, 6.4TD.
- `p1`…`p6` are numbers or JSON `null`. **Never invent a value**: if the document
  does not show a price for a period, use `null` (`―`, empty cell, missing row).
  Never use 0 for "absent".
- Both `preciosPotencia.tarifa` and `preciosEnergia.tarifa` must be present per
  producto, even when one has all-null values (e.g. bundled "peajes incluidos"
  offers may not itemize power).

## Domain knowledge

- **Término de potencia**: price per kW of contracted power. 2.0TD uses P1–P2;
  3.0TD and 6.xTD use P1–P6.
- **Término de energía**: price per kWh consumed. 2.0TD usually P1–P3 (sometimes
  up to P6); 3.0TD/6.xTD use P1–P6.
- Tables may be split across pages, rotated, transposed (products as rows, periods
  as column blocks), or repeated with rowspan/merged cells — a product name may
  appear on a separate line from its rows ("CLASSIC" above "T0"). Reconstruct the
  product for every row; never drop a product because its label cell looked empty.
- **Spanish number format**: `1.234,56` = 1234.56. Dots = thousands, comma =
  decimal. Strip `€`, `%`, unit suffixes before parsing.
- **Margins and discounts are not prices**: "margen", "descuento promocional",
  "% dto" columns must never land in p1..p6.
- **Coefficient tables are not prices**: values around 1.0–1.3 in indexed-product
  documents are usually loss coefficients (`Ai`, pérdidas) — skip them.
- **Tax variants**: when several price columns exist (sin IEE y sin IVA / con IEE /
  con IEE y con IVA), extract **sin IEE y sin IVA** — the backend applies taxes
  itself (`iva`, `impuestoElectrico`).
- **Consumption-band repetition**: tables that repeat identical prices per band
  (0–1.500 kWh, 1.501–3.000, …) describe ONE product — emit each distinct price
  set once, not one producto per band.
- **Multiple validity blocks**: when the same tariff appears under several
  "Inicio: <month>" / validity blocks, extract the **first (current) block only**.
- **Gas rows**: tariffs `GAS`, `RL.1`…`RL.6` are gas, not electricity — skip them.
- Documents about **excedentes / batería virtual / compensación** alone (no P1–P6
  price tables) yield an empty `producto` list.

## Units (€ vs cents, año vs mes vs día) — critical

**You never convert numbers.** You report the values exactly as printed and
declare the printed unit per producto in `unidadPotencia` / `unidadEnergia`.
Deterministic code converts afterwards.

Canonical units the system expects (the backend multiplies power × 365 and
energy × kWh):

- **Energy → €/kWh.** Printed forms: €/kWh (EUR_KWH) or cents — c€/kWh, cts,
  "céntimos" (CENT_KWH). Heuristic when the unit is unstated: energy values
  > 1 are almost certainly cents (electricity never exceeds 1.5 €/kWh in these
  proposals) → declare CENT_KWH.
- **Power → €/kW·día.** Printed forms vary by provider: €/kW·día
  (EUR_KW_DIA: ADX, REPSOL, TOTAL "Luz Fijo"), €/kW·año (EUR_KW_ANO:
  GESTERNOVA, ENDESA Grandes Cuentas, ELEIA Traderservices, TOTAL "Peninsula
  Resumen" blocks labeled €/kWaño), €/kW·mes (EUR_KW_MES: ENDESA MultiOferta).
  When several equivalent units are shown for the same price (ENDESA prints
  año + mes + día side by side), report the **€/kW·día** column if present,
  else the año column with EUR_KW_ANO.
- A single document may mix units across blocks/products (TOTAL "Peninsula
  Resumen" has €/kWaño blocks AND €/kWdia blocks) — declare the unit per
  producto, never assume document-wide consistency.

## Sanity rules (reject, don't guess)

- Any energy price > 1.5 €/kWh after cents conversion is wrong — re-check the
  column (likely a margin or annual-cost column bleeding into price slots).
- Power prices are typically 0.001–0.3 (€/kW·día) or 1–200 (€/kW·año); anything
  outside deserves a second look.
- If a table cannot be read with confidence, return an empty `producto` list
  rather than hallucinated numbers.

## Discounts

When applicable discounts are documented for a product (bienvenida,
promocional, permanencia…), report the **total additive percentage** in
`descuentoEnergiaPct` and keep the energy prices as printed (base). Deterministic
code applies the discount. Never apply percentages yourself, never report a
discounted number as if it were the printed one. Discounts apply to the
**energy term only**, never to power, unless the document explicitly says
otherwise.

## Provider selection rules (from business briefings, 2026-09-01)

Not every printed product belongs in the comparator: products that cannot be
mapped to the regulatory P1–P6 periods lack the transparency to be offered.
Extract ONLY the products listed here for these providers (plus nothing else).

### ENDESA

- **Grandes Cuentas 3.0TD / 6.1TD ("Tarifa Open")**: extract ONLY the
  **modalidad PLANA** energy price (flat, all periods), ALWAYS one producto
  per power band — every band, every run. Producto names MUST follow this
  exact template: `Tarifa Open {TARIFA} Plana ({BANDA})`, with BANDA copied
  verbatim from the row label: for 3.0TD `15-30 kW`, `30-50 kW`, `50-100 kW`,
  `>100 kW`; for 6.1TD `<30 kW`, `30-50 kW`, `50-100 kW`, `100-450 kW`
  (always check the printed labels). Skip Día, Laboral, Fin de Semana, Noche
  and Horas No Open columns entirely. Power: the shared P1–P6 table
  (€/kW·año → EUR_KW_ANO) repeated in each band producto.
- **Solar Plus & Batería Virtual**: energy = the column labeled **"Precio
  promocionado"** (0,148707 €/kWh in the 220726 doc — never the "Precio no
  promocionado" column, 0,159900), flat P1–P3; EXCLUDE the "Excedentaria"
  column. Power: Punta-llano/Valle (P1/P2) printed €/kW·año — copy both
  values even when equal.
- **MultiOferta Residencial (max 15 kW)**: extract ONLY `Tarifa Luz 24h`
  (first band Pc≤15kW, with descuentoEnergiaPct 20 = 10% bienvenida + 10%
  promocional; the 3% service discount is NOT applied) and
  `Tarifa Luz 3 Periodos` (no discount). Skip Tempo Open, Tu Otra Casa,
  Recarga en Casa and any 3A/5A/AD/ML price variants.

### IBERDROLA

(Source is the IBERDROLA "Resumen" Excel — pending xlsx support; rules
recorded for when it lands, and for any Iberdrola PDF.)

- Discounts apply to the **energy term only**: declare them in
  `descuentoEnergiaPct` (Plan Exclusivo 15%, Plan Empresas 10%, Impulsa 20%,
  Exclusivo 30%…).
- Product whitelist: 2.0TD (≤10 kW and >10 kW variants): Plan Exclusivo
  15%TE/1P TP, Plan Exclusivo Permanencia 15%TE/1P TP, Plan Especial Plus,
  Plan Estable. 3.0TD: Plan Impulsa, Plan Impulsa 24 Plus, Plan Impulsa
  Estable, Plan Empresas 10%TE, Plan Exclusivo 15%TE, Plan Exclusivo 30%TE.
  6.1TD: Plan Exclusivo 15%TE, Plan Empresas 10%TE, Plan Exclusivo 15%/30%TE.
- Power printed €/kW·año → EUR_KW_ANO.

### REPSOL

- **Product whitelist** — extract ONLY these 5 products (skip all other 2.0TD,
  3.0TD, 6.1TD, indexed, solar, and GAS rows):
  - **2.0TD** (`POTENCIA HASTA 10kW`):
    - `Tarifa Sin Horarios 2.0TD_PB RES <10KW AV`
    - `Tarifa Sin Horarios Hogar 2.0TD_PB RES <10KW AV + SVA`
    - `Tarifa Sin Horarios 2.0TD_PB RES <10KW MV`
    - `Batería Virtual 2.0TD_PB RES <15KW GdO MV`
  - **3.0TD** (`POTENCIA CONTRATADA DE +10kW`):
    - `Tarifa Empresa 3.0 3.0TD_PB SUPERCLIENTE L8`
- **Flat energy on 2.0TD (`TE1` → `P1`–`P3`)**: Repsol prints the single 24h
  energy price for the 4 whitelisted 2.0TD products only in the `TE1` column
  (`TE2`–`TE6` blank). Because 2.0TD uses three energy periods, repeat that
  printed `TE1` value across `p1`, `p2`, and `p3` (`p4`–`p6` = `null`).
- **Final prices (no discounts)**: printed prices are final
  (`descuentoEnergiaPct = null`). Energy is printed in cents (`c€/kWh` →
  `unidadEnergia = "CENT_KWH"`); power is printed in `€/kW·día`
  (`unidadPotencia = "EUR_KW_DIA"`, `P1`–`P2` for 2.0TD, `P1`–`P6` for 3.0TD).

## Known provider notes

- **ADX**: campaigns CLASSIC / CHEFF / PPA in APP and BRIEL variants. Product
  names: "CLASSIC T0…T4", "U0…U3" (ÚNICA — energy nearly flat across periods);
  product label may be split across two lines. Rows carry 12 numeric cells:
  6 power then 6 energy. Power in €/kW·día. 2.0TD rows: power P1–P2, energy
  P1–P3. 6.1TD rows may be entirely empty for U-products.
- **ELEIA**: products "TDE 2.0/3.0"; energy often printed in cents (CENT_KWH).
  "OFERTAS BASE PERSONALIZADAS" layout: energy-only (peajes incluidos, power not
  itemized → unidadPotencia NONE), two "Inicio: <month>" blocks (take the
  first), includes 6.2TD–6.4TD and a gas section to skip. "TRADER SERVICES" is
  indexed: extract the "componente fijado" tables (sin IEE y sin IVA columns)
  and ignore the Ai/PMMi coefficient tables; power printed in €/kW·año. Its
  "Descuento Promocional Aplicado" is already reflected in the printed prices —
  do NOT declare a discount for it (descuentoEnergiaPct = null).
- **TOTAL (TotalEnergies)**: "Luz Fijo Clásica TE1…TE4 / TER". The "Peninsula
  Electricidad Resumen" layout stacks many blocks (CLASICA, CLASICA LIBRE with
  consumption bands, CLASICA TE1…TE5 + UNICA, TEMPO 2/3 AÑOS) and mixes
  €/kWaño and €/kWdia blocks — keep each block's printed unit; `―` = null;
  "P1-P6" single column = flat energy for UNICA products. In the "Peninsula
  Resumen", UNICA sub-tables carry ONLY energy — the power values printed next
  to them belong to the paired main product (e.g. CLASICA TE1); never copy
  power into UNICA productos. Combined product
  names like "JAZZ TE1* / ROCK TE1*" keep the " / " separator verbatim.
  The "RESIDENCIAL" layout repeats products per commercial version (consumption
  bands, DUAL, DAZN packages…): emit one producto per version, named exactly
  `{PRODUCTO} ({VERSION})` with the version as printed (`SOLO LUZ < 4.000
  kWh/año`, `SOLO LUZ ≥ 4.000 kWh/año`, `DUAL`, …) — parentheses, not dashes.
  In the DAZN section, keep the sub-variant: `(DAZN Fútbol o Motor)`,
  `(DAZN Premium)`. Never add words that are not printed (e.g. "Paquetes").
- **GESTERNOVA**: campaigns "2.0TD/3.0TD ECO BRIEL", "Oferta Única" (one energy
  price repeated across periods), "24MESES". Power in €/kW·año, energy in €/kWh
  with up to 8 decimals — keep full precision. Ignore "Precio Excedentes" lines.
- **ENDESA**: extract ONLY the whitelisted products (see "Provider selection
  rules"). Layout notes: "Grandes Cuentas 3.0TD/6.1TD" use inline notation
  `P1: 31,095368 P2: …`, power shown per año/mes/día (take año). "MultiOferta
  Residencial" uses €/kW·mes power and banded tables — take the first band
  (Pc≤15kW); discount annotations are not prices; skip término variable (TV).
- **IBERDROLA**: "Plan Empresa FLEX" is a **scanned PDF** (no text layer) —
  requires the vision path. "Solar Cloud / Batería Virtual" docs are
  excedentes-only → empty `producto`.
- **REPSOL**: extract ONLY the 5 whitelisted products (see "Provider selection
  rules"). One row per product; column blocks TE1–TE6 (energy, printed in
  **cents c€/kWh** → declare CENT_KWH, do not convert) then TP1–TP6 (power,
  €/kW·día → EUR_KW_DIA). For the 4 whitelisted 2.0TD flat tariffs, repeat
  the single printed TE1 value across `p1`–`p3` (`p4`–`p6` = `null`).
  Channel codes (A/S/C/SC/P) and GAS rows are not extracted.
- New providers: apply the general rules; do not force-fit the above.

## Canonical product names (registry)

Product names are identity keys: the same product must extract to the same
string in every campaign document. Use exactly these strings for known families:

- **TOTAL "Luz Fijo Clásica"**: the product name comes from the price-TABLE
  titles, not the marketing tariff name: `CLÁSICA BASE TE1` … `CLÁSICA BASE
  TE4`, `CLÁSICA BASE TER`, plus `… UNICA` when the UNICA flat-price table
  exists. ("Tarifa CLÁSICA TE1" in the legal text is NOT the product name.)
- **ADX**: `BRIEL CHEFF 1`…`4`, `BRIEL PPA 1`…`4`, `CLASSIC T0`…`T4`,
  `CLASSIC U0`…`U3` (U = ÚNICA, near-flat energy).
- **ELEIA "Luz APP"**: `ELEIA TDE0`…`TDE3`, `ELEIA BOE0`…`BOE3`.
- **ELEIA Traderservices**: `Trader Services 2 S3126` (drop the "Producto"
  prefix the document header prints).

For providers/families not listed, use the most complete verbatim printed name
(and add the family to this registry once reviewed).

## Banded prices and flat prices

- Some documents band prices by contracted power (ENDESA MultiOferta: Pc≤15kW,
  15<Pc≤50kW, …). Extract the band matching the document's scope — a
  "Residencial max 15 kW" document uses the Pc≤15kW band.
- Flat energy prices (TOTAL UNICA, ENDESA Tempo Open / Tu Otra Casa, REPSOL
  2.0TD Sin Horarios / Batería Virtual where only TE1 is printed) repeat the
  same value across **only the periods the tariff uses**: 2.0TD → P1–P3,
  3.0TD/6.xTD → P1–P6. Never fill P4–P6 for a 2.0TD product.
- Some PDFs mix Spanish (0,198840) and English (0.198840) decimal formats in
  the same table — read both.

## Scanned documents

If the PDF yields no usable text (scanned images), fall back to reading rendered
page images (vision). IBERDROLA "Plan Empresa FLEX" is the known case.

## Working with the eval harness

Golden outputs live in `eval/golden/` (captured from the legacy Docling parsers
by `eval/capture_golden.py`; text surveys in `eval/surveys/`). After any change
to this skill, re-run extraction on every corpus PDF and compare with
`eval/run_eval.py` — price-exact parity is the regression gate. Providers the
legacy parsers could not handle (GESTERNOVA, ELEIA Peninsula, ENDESA, IBERDROLA,
REPSOL) have no Docling golden: their baseline is bootstrapped from agent output
reviewed by a human.
