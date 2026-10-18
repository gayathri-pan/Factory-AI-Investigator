
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from investigation.investigator import FactoryInvestigator
from investigation.evidence_gate import EvidenceGate


def main():
    # Collect real investigation context and RAG evidence.
    investigator = FactoryInvestigator(top_k=3)
    investigation = investigator.investigate()

    evidence = investigation["technical_evidence"]

    print("\n" + "=" * 60)
    print("TESTING EVIDENCE GATE")
    print("=" * 60)

    print(f"Retrieved evidence: {len(evidence)}")

    # Inspect the actual fields returned by your retriever.
    for item in evidence:
        print(
            f"\nID: {item.get('evidence_id')}"
            f"\nSource: {item.get('source')}"
            f"\nSemantic score: {item.get('semantic_score')}"
            f"\nHas passage text: "
            f"{bool(item.get('text'))}"
        )
        
    print("\n--- Retrieved passage contents ---")
    for item in evidence:
        print(f"\nEvidence ID: {item.get('evidence_id')}")
        print(f"Source: {item.get('source')}")
        print(f"Text:\n{item.get('text', '[No text found]')}")
        print("-" * 60)

    # Assess relevance and evidence sufficiency.
    gate = EvidenceGate(min_relevance_score=0.70)

    result = gate.evaluate(
        evidence=evidence,
        investigation_package=investigation,
    )

    print("\n" + "-" * 60)
    print("EVIDENCE GATE RESULT")
    print("-" * 60)
    print("Sufficient:", result["sufficient"])
    print("Reason:", result["reason"])
    print("Rejected:", result["rejected_count"])
    print("Missing information:", result["missing_information"])
    print("Evidence passed:", len(result["evidence"]))


if __name__ == "__main__":
    main()
