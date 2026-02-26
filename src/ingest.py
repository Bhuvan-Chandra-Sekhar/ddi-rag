""" makin the json files in RAW document into txt files in the processed folder for makin the data ready for the RAG """
import json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import os

# When running as a script, __file__ is defined and safe to use
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_FOLDER = PROJECT_ROOT / "data" / "raw"
PROCESSED_FOLDER = PROJECT_ROOT / "data" / "processed"

PROCESSED_FOLDER.mkdir(parents=True, exist_ok=True)

def process_file(file_path):
    saved_count = 0
    
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = data.get("results", [])

    for drug in results:
        openfda = drug.get("openfda", {})
        generic_names = openfda.get("generic_name")
        interactions = drug.get("drug_interactions")

        if not generic_names or not interactions:
            continue

        # Build a filesystem-safe, reasonably short filename
        base_name = generic_names[0].lower().replace(" ", "_").replace("/", "_")
        drug_name = base_name[:80]
        interaction_text = "\n".join(interactions)

        readable_text = (
            f"Drug: {drug_name}\n\n"
            f"=== Drug Interactions ===\n"
            f"{interaction_text}\n"
        )

        output_file = PROCESSED_FOLDER / f"{drug_name}.txt"

        # Avoid rewriting if already processed
        if not output_file.exists():
            with open(output_file, "w", encoding="utf-8") as out:
                out.write(readable_text)
            saved_count += 1

    print(f"{file_path.name} → Saved {saved_count} drugs")
    return saved_count


if __name__ == "__main__":
    files = list(RAW_FOLDER.glob("drug-label-*.json"))
    print(f"Found {len(files)} files")
    
    total_saved = 0

    # Use all CPU cores
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
        results = executor.map(process_file, files)
    
    total_saved = sum(results)
    
    print(f"\nTotal processed drug files saved: {total_saved}")