
from rag.vector_store import FactoryVectorStore


class FactoryRetriever:
    """
    Retrieve semantically relevant evidence within the requested
    machine's scope, including general documentation when allowed.
    """

    def __init__(self, top_k=3, vector_store=None):
        if top_k < 1:
            raise ValueError("top_k must be at least 1.")

        self.top_k = top_k

        # Allow a shared vector store to be injected later, avoiding
        # unnecessary duplicate clients and embedding-model loads.
        self.vector_store = (
            vector_store
            if vector_store is not None
            else FactoryVectorStore()
        )

    def retrieve(self, query, machine_id=None, include_global=True):
        """
        Retrieve ranked evidence for a query.

        When machine_id is provided, search only that machine's documents
        and, if enabled, general documents such as Safety_Procedures.md.
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty.")

        candidate_k = max(self.top_k * 3, 10)

        results = self.vector_store.search(
            query=query,
            top_k=candidate_k,
            machine_id=machine_id,
            include_global=include_global,
        )

        evidence = []

        for result in results:
            payload = result.payload or {}

            semantic_score = float(result.score)
            document_machine_id = payload.get("machine_id")
            document_is_machine_specific = payload.get(
                "machine_specific", False
            )

            machine_match = (
                machine_id is not None
                and document_is_machine_specific
                and document_machine_id == machine_id
            )

            is_global_document = (
                document_machine_id is None
                and not document_is_machine_specific
            )

            # Machine scope is enforced by Qdrant filtering.
            # Rank eligible evidence by semantic similarity alone.
            final_score = semantic_score

            if machine_match:
                ranking_reason = (
                    f"Semantically relevant document scoped to "
                    f"{machine_id}."
                )
            elif is_global_document:
                ranking_reason = (
                    "Semantically relevant general documentation; "
                    "global guidance was included in the search."
                )
            else:
                ranking_reason = (
                    "Semantically relevant document; no matching "
                    "machine-specific scope was established."
                )

            evidence.append({
                "semantic_score": semantic_score,
                "final_score": final_score,
                "source": payload.get("source"),
                "text": payload.get("text", ""),
                "file_path": payload.get("file_path"),
                "machine_id": document_machine_id,

                # Preserve the actual metadata separately from whether
                # the document matches the requested machine.
                "machine_specific": document_is_machine_specific,
                "machine_match": machine_match,
                "ranking_reason": ranking_reason,
            })

        evidence.sort(
            key=lambda item: item["final_score"],
            reverse=True,
        )

        final_evidence = evidence[:self.top_k]

        for index, item in enumerate(final_evidence, start=1):
            item["evidence_id"] = f"E{index}"

        return final_evidence



def main():
    print("=" * 70)
    print("FACTORY AI INVESTIGATOR - MULTI-MACHINE RETRIEVAL TEST")
    print("=" * 70)

    retriever = FactoryRetriever(top_k=3)

    test_cases = [
        {
            "machine_id": "M-101",
            "query": "What should be checked when CNC spindle vibration and temperature increase?",
        },
        {
            "machine_id": "M-102",
            "query": "What should be inspected when milling tool condition changes and vibration increases?",
        },
        {
            "machine_id": "M-103",
            "query": "What should be checked when a conveyor has drive problems, belt tracking issues, or vibration?",
        },
        {
            "machine_id": "M-104",
            "query": "What should be inspected when hydraulic pressure changes while temperature and vibration increase?",
        },
        {
            "machine_id": "M-105",
            "query": "What should be checked when a robot joint has abnormal movement, vibration, or drive issues?",
        },
    ]

    for case in test_cases:
        machine_id = case["machine_id"]
        query = case["query"]

        print("\n" + "=" * 70)
        print(f"MACHINE: {machine_id}")
        print(f"QUERY: {query}")

        results = retriever.retrieve(
            query=query,
            machine_id=machine_id,
            include_global=True,
        )

        if not results:
            print("WARNING: No evidence retrieved.")
            continue

        for result in results:
            print("\n" + "-" * 50)
            print(
                f"{result['evidence_id']} | "
                f"Score: {result['semantic_score']:.4f}"
            )
            print(f"Source: {result['source']}")
            print(f"Document machine: {result['machine_id']}")
            print(f"Machine match: {result['machine_match']}")
            print(f"Reason: {result['ranking_reason']}")
            print(f"Text: {result['text'][:400]}")

        # Confirm that every returned result is either machine-specific
        # to this machine or is an explicitly global document.
        invalid_results = [
            result for result in results
            if not (
                result["machine_match"]
                or (
                    result["machine_id"] is None
                    and not result["machine_specific"]
                )
            )
        ]

        if invalid_results:
            print("\nFAIL: Out-of-scope document returned.")
        else:
            print("\nPASS: All results are within the requested scope.")

    # Separate test for general safety guidance.
    print("\n" + "=" * 70)
    print("GLOBAL SAFETY DOCUMENT TEST")
    print("=" * 70)

    safety_results = retriever.retrieve(
        query="What general safety precautions should be followed during machine inspection and maintenance?",
        machine_id="M-103",
        include_global=True,
    )

    for result in safety_results:
        print(
            f"{result['evidence_id']} | {result['source']} | "
            f"machine_id={result['machine_id']} | "
            f"score={result['semantic_score']:.4f}"
        )

    if any(
        result["source"] == "Safety_Procedures.md"
        for result in safety_results
    ):
        print("PASS: General safety guidance is retrievable.")
    else:
        print(
            "NOTE: Safety_Procedures.md was not in the top results. "
            "Review its relevance and the search ranking if needed."
        )


if __name__ == "__main__":
    main()

