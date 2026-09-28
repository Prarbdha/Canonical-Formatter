import json
from pathlib import Path


from canonical_formatter.graph.pipeline import build_pipeline


def test_pipeline_skeleton_runs():
    app = build_pipeline()
    initial_state = {
        "raw_input_path": "sample_data/sample.txt",
        "input_type": "text",
        "project_name": "",
        "errors": [],
    }
    result = app.invoke(initial_state)

    canonical_set = result.get("canonical_set")
    if canonical_set:
        print("\n--- Requirements (with acceptance criteria) ---")
        print(json.dumps(canonical_set.model_dump(), indent=2))

    srs = result.get("srs_content")
    if srs:
        print("\n--- SRS Content ---")
        print(json.dumps(srs.model_dump(), indent=2))
    else:
        print("\nSRS content is None — check errors")

    if result["errors"]:
        print("\n--- Errors ---")
        print(result["errors"])

        print("\nFinal document:", result.get("final_document_path"))

    if canonical_set and srs:
        Path("outputs").mkdir(exist_ok=True)
        Path("outputs/cache.json").write_text(
            json.dumps({"canonical": canonical_set.model_dump(mode="json"),
                        "srs": srs.model_dump(mode="json")}),
            encoding="utf-8",
        )    


if __name__ == "__main__":
    test_pipeline_skeleton_runs()