import json
from pathlib import Path
from canonical_formatter.schemas.requirement import CanonicalRequirementSet
from canonical_formatter.schemas.srs import SRSDocument
from canonical_formatter.agents.formatting import FORMATS, write_all

data = json.loads(Path("outputs/cache.json").read_text(encoding="utf-8"))
canonical = CanonicalRequirementSet.model_validate(data["canonical"])
srs = SRSDocument.model_validate(data["srs"])

for fmt in FORMATS:
    paths = write_all(canonical, srs, fmt)
    print(fmt, "->", {k: str(v) for k, v in paths.items()})