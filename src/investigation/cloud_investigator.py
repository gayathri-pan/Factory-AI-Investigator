import argparse
import json

from investigation.cloud_context_builder import (
    CloudInvestigationContextBuilder,
)
from investigation.evidence_gate import EvidenceGate
from rag.cloud_vector_store import CloudFactoryVectorStore
from rag.retriever import FactoryRetriever
from investigation.report_generator import InvestigationReportGenerator
from investigation.report_store import InvestigationReportStore
from investigation.replay_context_builder import (
    ReplayInvestigationContextBuilder,
)


class CloudFactoryInvestigator:
    """Assemble cloud evidence and assess it for one selected event."""

    def __init__(self, context_builder, retriever, evidence_gate):
        # Dependencies are shared, rather than loaded on every request.
        self.context_builder = context_builder
        self.retriever = retriever
        self.evidence_gate = evidence_gate

    @staticmethod
    def build_rag_query(context):
        machine = context["machine"]
        summary = context["sensor_summary"]

        observations = []
        for sensor in (
            "temperature",
            "vibration",
            "pressure",
            "rpm",
            "power_consumption",
        ):
            if summary.get(f"valid_{sensor}_count", 0) > 0:
                observations.append(
                    f"{sensor}: minimum={summary.get(f'min_{sensor}')}, "
                    f"maximum={summary.get(f'max_{sensor}')}, "
                    f"mean={summary.get(f'mean_{sensor}')}"
                )

        # Use current event logs, not historical root causes, to help
        # identify relevant documentation.
        log_context = [
            {
                "component": record.get("component"),
                "message": record.get("message"),
            }
            for record in context.get("machine_logs", [])[:10]
        ]

        return (
            f"Machine: {machine['machine_id']}; "
            f"name: {machine.get('machine_name', 'unknown')}; "
            f"type: {machine.get('machine_type', 'unknown')}. "
            "A sensor-window classifier flagged this event. "
            f"Recorded sensor summaries: {'; '.join(observations)}. "
            f"Event-window logs: {json.dumps(log_context)}. "
            "Retrieve applicable technical documentation about these sensors "
            "and machine systems, documented fault symptoms, and evidence "
            "needed to assess possible causes. "
            "Summary extrema do not establish trends. "
            "Do not assume units, operating limits, abnormal direction, "
            "sensor mapping, or a confirmed fault."
        )

    def assess_event(self, event_id):
        context = self.context_builder.build_context(event_id)
        machine_id = context["anomaly_event"]["machine_id"]

        query = self.build_rag_query(context)
        evidence = self.retriever.retrieve(
            query=query,
            machine_id=machine_id,
            include_global=True,
        )

        for item in evidence:
            eligible = item["machine_match"] or (
                item["machine_id"] is None
                and item["machine_specific"] is False
            )
            if not eligible:
                raise ValueError("Out-of-scope technical evidence.")

        package = {
            **context,
            "investigation_query": query,
            "knowledge_base_version": (
                self.retriever.vector_store.knowledge_base_version
            ),
            "technical_evidence": evidence,
        }

        gate_result = self.evidence_gate.evaluate(
            evidence=evidence,
            investigation_package=package,
        )

        # Preserve the original candidates for traceability.
        package["retrieved_evidence"] = evidence

        # Only accepted evidence can reach the later report generator.
        package["technical_evidence"] = gate_result["evidence"]
        package["evidence_gate"] = {
            key: value
            for key, value in gate_result.items()
            if key != "evidence"
        }

        return package


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id", required=True)
    parser.add_argument(
        "--simulation-id",
        help="Use a replay event from this Firestore simulation.",
    )
    args = parser.parse_args()

    if args.simulation_id:
        context_builder = ReplayInvestigationContextBuilder(
            simulation_id=args.simulation_id,
        )
    else:
        context_builder = CloudInvestigationContextBuilder()

    vector_store = None

    try:
        vector_store = CloudFactoryVectorStore()
        retriever = FactoryRetriever(
            top_k=3,
            vector_store=vector_store,
        )
        investigator = CloudFactoryInvestigator(
            context_builder=context_builder,
            retriever=retriever,
            evidence_gate=EvidenceGate(min_relevance_score=0.70),
        )

        package = investigator.assess_event(args.event_id)

        print("\nINVESTIGATION QUERY")
        print(package["investigation_query"])

        print("\nRETRIEVED EVIDENCE")
        for item in package["retrieved_evidence"]:
            print(
                item["evidence_id"],
                item["source"],
                f"score={item['semantic_score']:.4f}",
            )

        print("\nEVIDENCE GATE RESULT")
        print(json.dumps(package["evidence_gate"], indent=2))

        print(
            "\nAccepted evidence count:",
            len(package["technical_evidence"]),
        )

        if package["evidence_gate"]["sufficient"] is not True:
            print("\nReport not generated: evidence gate did not pass.")
        else:
            # Align the existing report prompt with the context builder's
            # newer log-scope field name.
            package["machine_logs_scope"]["records_found"] = (
                package["machine_logs_scope"]["records_returned"]
            )

            print("\nGenerating the investigation report...")
            generator = InvestigationReportGenerator()
            report = generator.generate_report(package)
            store = InvestigationReportStore()
            try:
                investigation_id = store.save_completed(
                    package=package,
                    report=report,
                    model_name=generator.model_name,
                )
                print(f"\nSaved investigation: {investigation_id}")

                saved = store.get_report(investigation_id)

                if saved is None:
                    raise RuntimeError("Saved report could not be retrieved.")

                if saved["report_markdown"] != report:
                    raise RuntimeError("Saved report text differs from original.")

                if saved["event_id"] != package["anomaly_event"]["event_id"]:
                    raise RuntimeError("Saved report has an incorrect event ID.")

                print("BigQuery report read-back: PASS")
                print("Saved status:", saved["status"])
                print("Saved machine:", saved["machine_id"])
            finally:
                store.close()

            print("\n" + "=" * 60)
            print("VALIDATED REPORT STRUCTURE")
            print("=" * 60)
            print(report)
        
    finally:
        if vector_store is not None:
            vector_store.close()
        context_builder.close()


if __name__ == "__main__":
    main()