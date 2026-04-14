from dataclasses import dataclass, field
from pathlib import Path
import tomllib


@dataclass
class ReportConfig:
    name: str
    output_dir: Path
    naics_codes: list[str]
    naics_label: str
    soc_codes: list[str]
    soc_titles: list[str]
    soc_label: str
    msa_code: str
    msa_name: str
    state_code: str
    living_wage: float
    overview_xls: Path | None = None
    jpa_xls: Path | None = None
    occ_csv: Path | None = None


def load_config(path: str | Path) -> ReportConfig:
    path = Path(path)
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    report = raw["report"]
    industry = raw["industry"]
    occupation = raw["occupation"]
    geo = raw["geography"]
    manual = raw.get("manual_inputs", {})

    base_dir = path.parent

    def _resolve(p: str) -> Path | None:
        if not p:
            return None
        resolved = Path(p)
        if not resolved.is_absolute():
            resolved = base_dir / resolved
        return resolved

    return ReportConfig(
        name=report["name"],
        output_dir=base_dir / report.get("output_dir", "./output"),
        naics_codes=industry["naics_codes"],
        naics_label=industry.get("label", "Selected Industries"),
        soc_codes=occupation["soc_codes"],
        soc_titles=occupation.get("soc_titles", []),
        soc_label=occupation.get("label", "Selected Occupations"),
        msa_code=geo["msa_code"],
        msa_name=geo["msa_name"],
        state_code=geo.get("state_code", "48"),
        living_wage=float(geo.get("living_wage", "23.36")),
        overview_xls=_resolve(manual.get("overview_xls", "")),
        jpa_xls=_resolve(manual.get("jpa_xls", "")),
        occ_csv=_resolve(manual.get("occ_csv", "")),
    )
