"""Deterministic unit normalization and sanity validation.

The LLM declares the unit in which prices are printed (unidadPotencia /
unidadEnergia per producto) and never does arithmetic. This module applies the
conversion in code and strips the unit fields, so the response matches the
contract BmBackend already consumes.

Canonical units: energy EUR/kWh, power EUR/kW/day — the backend multiplies
power prices by 365 for annual costs (ProposalCalculationUtils.kt).
"""

import logging
import re

logger = logging.getLogger("price-agent.normalize")

POWER_TO_DAY = {"EUR_KW_DIA": 1.0, "EUR_KW_MES": 12.0 / 365.0, "EUR_KW_ANO": 1.0 / 365.0}
ENERGY_TO_EUR = {"EUR_KWH": 1.0, "CENT_KWH": 0.01}
PERIODS = ("p1", "p2", "p3", "p4", "p5", "p6")

ENERGY_MAX_EUR_KWH = 1.5
POWER_MAX_DAY = 0.5       # EUR/kW·day
POWER_MAX_YEAR = 300.0    # EUR/kW·year equivalent sanity bound


def _has_values(tarifas: list) -> bool:
    return any(t.get(p) is not None for t in tarifas for p in PERIODS)


def _scale(tarifas: list, factor: float) -> None:
    for tarifa in tarifas:
        for period in PERIODS:
            if tarifa.get(period) is not None:
                tarifa[period] = tarifa[period] * factor


def normalize_units(payload: dict) -> list[str]:
    """Convert printed-unit prices to canonical units, in place.

    Removes unidadPotencia/unidadEnergia from the payload. Returns
    human-readable notes (logged by the caller). Unknown units with actual
    values are left untouched and reported loudly.
    """
    notes = []
    for prod in payload.get("producto", []):
        pname = prod.get("name", "?")
        u_power = prod.pop("unidadPotencia", None)
        u_energy = prod.pop("unidadEnergia", None)

        potencia = (prod.get("preciosPotencia") or {}).get("tarifa", [])
        energia = (prod.get("preciosEnergia") or {}).get("tarifa", [])

        f_power = POWER_TO_DAY.get(u_power)
        f_energy = ENERGY_TO_EUR.get(u_energy)
        if f_power is None and _has_values(potencia):
            notes.append(f"{pname}: UNKNOWN unidadPotencia {u_power!r} (left as-is)")
        if f_energy is None and _has_values(energia):
            notes.append(f"{pname}: UNKNOWN unidadEnergia {u_energy!r} (left as-is)")

        if f_power not in (None, 1.0):
            _scale(potencia, f_power)
            notes.append(f"{pname}: potencia {u_power} -> EUR_KW_DIA")
        if f_energy not in (None, 1.0):
            _scale(energia, f_energy)
            notes.append(f"{pname}: energia {u_energy} -> EUR_KWH")
    return notes


def _discount(tarifas: list, pct: float) -> None:
    factor = 1.0 - pct / 100.0
    for tarifa in tarifas:
        for period in PERIODS:
            if tarifa.get(period) is not None:
                tarifa[period] = tarifa[period] * factor


def apply_discounts(payload: dict) -> list[str]:
    """Apply declared energy discounts (descuentoEnergiaPct) in code — the LLM
    declares, never calculates. Removes the field from the payload."""
    notes = []
    for prod in payload.get("producto", []):
        pct = prod.pop("descuentoEnergiaPct", None)
        if pct is None:
            continue
        energia = (prod.get("preciosEnergia") or {}).get("tarifa", [])
        if not energia:
            continue
        if not 0 <= pct < 100:
            notes.append(f"{prod.get('name', '?')}: implausible descuentoEnergiaPct {pct} (ignored)")
            continue
        _discount(energia, pct)
        notes.append(f"{prod.get('name', '?')}: energia -{pct}% applied")
    return notes


# Spanish 1.234,56 / plain 1234,56 / dot-decimal anomaly (0.198840, seen in
# ENDESA MultiOferta). Dot-decimals require >=4 fractional digits.
_NUMBER_RE = re.compile(r"\d{1,3}(?:\.\d{3})+,\d+|\d+,\d+|\d+\.\d{4,}")


def text_numbers(text: str) -> list[float]:
    """All numbers printed in the document's text layer, as floats."""
    numbers = []
    for match in _NUMBER_RE.finditer(text):
        raw = match.group(0)
        try:
            numbers.append(float(raw.replace(".", "").replace(",", "."))
                           if "," in raw else float(raw))
        except ValueError:
            continue
    return numbers


def ungrounded_values(payload: dict, printed: list[float]) -> list[tuple]:
    """Raw (as-printed, pre-conversion) values that do not appear anywhere in
    the source text — i.e. probable LLM digit slips. Returns (producto_index,
    kind key, tarifa_index, period, value) tuples."""
    missing = []
    for pi, prod in enumerate(payload.get("producto", [])):
        for key in ("preciosPotencia", "preciosEnergia"):
            for ti, tarifa in enumerate((prod.get(key) or {}).get("tarifa", [])):
                for period in PERIODS:
                    value = tarifa.get(period)
                    if value is None:
                        continue
                    if not any(abs(n - value) <= max(1e-7, 1e-6 * abs(n))
                               for n in printed):
                        missing.append((pi, key, ti, period, value))
    return missing


def null_values(payload: dict, locations: list[tuple]) -> None:
    for pi, key, ti, period, _ in locations:
        payload["producto"][pi][key]["tarifa"][ti][period] = None


def sanity_warnings(payload: dict) -> list[str]:
    """Flag implausible values. Logged, never silently mutated — the eval
    harness is the hard gate; these warnings exist so production anomalies
    show up in Loki."""
    warnings = []
    for prod in payload.get("producto", []):
        pname = prod.get("name", "?")
        for kind, key in (("potencia", "preciosPotencia"), ("energia", "preciosEnergia")):
            for tarifa in (prod.get(key) or {}).get("tarifa", []):
                for period in PERIODS:
                    value = tarifa.get(period)
                    if value is None:
                        continue
                    label = f"{pname}/{tarifa.get('name', '?')}/{kind}/{period}"
                    if kind == "energia" and value > ENERGY_MAX_EUR_KWH:
                        warnings.append(f"{label}: energy {value} > {ENERGY_MAX_EUR_KWH} EUR/kWh")
                    if kind == "potencia" and value > POWER_MAX_YEAR:
                        warnings.append(f"{label}: power {value} implausible in any unit")
    return warnings
