import json
import os
import re
from dotenv import load_dotenv
from google import genai
from google.genai.types import GenerateContentConfig, HttpOptions

load_dotenv()

class EvidenceGate:
    """
    Filters retrieved evidence and assesses whether it is
    sufficient for a grounded factory investigation.
    """

    def __init__(
        self,
        min_relevance_score=0.70,
    ):
        self.min_relevance_score = min_relevance_score
        self.model_name = os.getenv("LLM_MODEL", "gemini-3.5-flash")
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "asia-south1")

        if not project:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT is not set. "
                "Set it to your Google Cloud project ID."
            )

        self.client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
            http_options=HttpOptions(api_version="v1"),
        )

    def evaluate(self, evidence, investigation_package):

        # Step 1: Filter by semantic relevance.
        relevant_evidence = [
            item
            for item in evidence
            if item.get("semantic_score", 0)
            >= self.min_relevance_score
        ]

        # Step 2: Fail safely if no relevant evidence exists.
        if not relevant_evidence:
            return {
                "sufficient": False,
                "reason": "No evidence passed the relevance threshold.",
                "evidence": [],
                "rejected_count": len(evidence),
                "missing_information": [
                    "Relevant technical documentation"
                ],
            }

        # Step 3: Require actual passage text for assessment.
        passages = []
        for item in relevant_evidence:
            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                return {
                    "sufficient": False,
                    "reason": (
                        "Evidence is missing passage text; "
                        "sufficiency cannot be assessed."
                    ),
                    "evidence": [],
                    "rejected_count": (
                        len(evidence) - len(relevant_evidence)
                    ),
                    "missing_information": [
                        "Technical passage text"
                    ],
                }
            passages.append({
                "evidence_id": item.get("evidence_id"),
                "source": item.get("source"),
                "text": text,
            })

        # Step 4: Ask the LLM to assess evidence sufficiency.
        assessment_input = {
            "investigation_query": (
                investigation_package.get("investigation_query", "")
            ),
            "machine": investigation_package.get("machine", {}),
            "anomaly_event": investigation_package.get(
                "anomaly_event", {}
            ),
            "machine_logs": investigation_package.get(
                "machine_logs", []
            ),
            "maintenance_history": investigation_package.get(
                "maintenance_history", []
            ),
            "historical_incidents": investigation_package.get(
                "historical_incidents", []
            ),
            "technical_evidence": [
                {
                    "evidence_id": item.get("evidence_id"),
                    "source": item.get("source"),
                    "semantic_score": item.get("semantic_score"),
                    "text": item.get("text"),
                }
                for item in relevant_evidence
            ],
        }

        # Preserve cloud context and the scope of each evidence source.
        for key in (
            "sensor_summary",
            "sensor_summary_scope",
            "machine_logs_scope",
            "machine_metadata_scope",
            "history_scope",
            "investigation_cutoff",
            "analysis_mode",
        ):
            assessment_input[key] = investigation_package.get(key)

        
        prompt = f"""
        You are an evidence sufficiency assessor for an industrial
        machine investigation.
        Assess whether the supplied information provides an adequate
        technical evidence base to investigate the current machine
        anomaly and produce a qualified, evidence-grounded report.
        The input may contain:
        - Current machine anomaly measurements
        - Machine operational logs
        - Maintenance history
        - Historical incidents
        - Relevant technical manual or SOP passages
        Consider all available evidence categories together.
        Distinguish clearly between:
        - Current observations directly supported by the data
        - Historical clues that may help frame hypotheses
        - Technical guidance supported by supplied documents
        - Missing information and unresolved uncertainties
        Historical incidents may suggest possible explanations but
        do not prove the current machine has the same fault.
        Do not determine or confirm the root cause.
        Do not invent facts or assume missing information.
        Do not use hardcoded keyword matching.
        Do not treat a hypothesis as a confirmed finding.
        EVIDENCE SUFFICIENCY DECISION RULES

        DECISION RUBRIC — APPLY THIS BEFORE EVALUATING MISSING INFORMATION
        This gate decides whether a qualified technical investigation report
        can be written. It does NOT decide whether a root cause is confirmed,
        whether the machine is safe, or whether physical work is authorized.

        Set "sufficient": true for a preliminary, uncertainty-qualified report
        when the current anomaly event contains identifiable event information
        (such as machine identity, event time, or recorded anomaly metrics) AND
        at least one non-empty, relevant technical passage has passed the
        program's relevance filter. Use available maintenance and historical
        records as supporting context when present. The report can explicitly
        state that the meaning or severity of some readings cannot be determined.

        Missing units, normal operating limits, baseline values, anomaly-window
        logs, maintenance records, historical records, or safety procedures do
        NOT individually make the evidence insufficient. List the gaps and
        explain their effect on interpretation. In particular, do not require
        operational logs or validated operating limits before a qualified
        preliminary report can be generated when the anomaly data and relevant
        technical passages are available.

        Set "sufficient": false only when the current event/anomaly information
        is absent or too incomplete to identify what is being investigated, or
        the supplied technical passages do not provide any meaningful technical
        context for the event. Missing corroboration is not evidence that the
        anomaly is false. Do not use uncertainty about root cause as a reason
        to reject the report; uncertainty must be preserved in the report.

        1. Evaluate technical evidence sufficiency separately from
        safety-procedure availability.
        2. Set "sufficient" to true when the available technical
        evidence supports a meaningful investigation, including
        an investigation that must retain uncertainty about the
        root cause.
        3. Missing plant-specific safety procedures alone must NOT
        cause "sufficient" to be false when the technical evidence
        is otherwise adequate.
        4. Set "sufficient" to false only when the technical evidence
        itself is inadequate to support a meaningful investigation,
        such as when essential anomaly data or relevant supporting
        evidence is unavailable or too incomplete to assess.
        5. When safety procedures are missing, list only gaps supported
        by the documented machine configuration, the proposed activity,
        and the supplied evidence. Relevant gaps may include:
        - Plant-specific lockout/tagout (LOTO) procedures
        - Required PPE specifications
        - Approved emergency shutdown and verification procedures
        - Isolation and de-energization verification procedures
        - Other applicable, system-specific safety procedures
        Include pressure-relief or hydraulic depressurization procedures
        as a confirmed missing requirement only when the supplied
        evidence establishes that a relevant hydraulic system is present.
        If a pressure value is supplied but its sensor meaning or associated
        system is unknown, identify that sensor/system mapping as unresolved.
        State that the applicability of hydraulic-specific procedures cannot
        yet be determined; do not report them as a confirmed requirement.
        6. Missing safety procedures are a limitation on physical
        inspection and operational decisions. They do not, by
        themselves, prevent a technical evidence assessment or
        qualified report from being generated.
        SAFETY AND EVIDENCE BOUNDARIES
        - Do not generate, recommend, or infer operational safety
        actions or procedures, including shutdown steps, cooling
        actions, isolation, depressurization, or LOTO steps.
        - Do not provide physical inspection instructions or tests
        that are not explicitly supported by applicable, supplied,
        approved plant-specific procedures.
        - Do not fill missing procedure gaps with general knowledge
        or assumed industry practices.
        - Determine whether a system-specific procedure applies from
        supplied machine metadata, technical documentation, logs, and
        maintenance records. A generic field named "pressure" does not
        establish the presence of a hydraulic system.
        - When pressure-system identity is unknown, report the associated
        system as unresolved. Do not state hydraulic depressurization
        documentation as a confirmed missing requirement unless a relevant
        hydraulic system is established by the evidence.
        - The "missing_information" array may identify the unresolved
        pressure-sensor system mapping, but must distinguish this uncertainty
        from an established missing safety procedure.
        - Do not assume that a logged emergency shutdown proves the
        machine is stopped, de-energized, isolated, or safe.
        - Do not infer that the machine is safe to inspect, operate,
        or restart.
        - If approved safety procedures are absent, identify this
        limitation explicitly. State that appropriate methods and
        safety requirements must be determined by authorized
        personnel using approved plant-specific procedures.
        - Never interpret "sufficient": true as authorization to
        perform physical work or as confirmation that the machine
        is safe.
        OUTPUT REQUIREMENTS
        Return only a JSON object conforming to the response schema supplied
        with this request. Do not wrap the JSON in Markdown code fences.
        The "reason" must:
        - Explain why the technical evidence is or is not adequate
        to investigate the anomaly.
        - Distinguish observations from possible explanations.
        - Mention important contradictions or uncertainties in the
        supplied evidence when relevant.
        - Explicitly state when safety-procedure gaps limit physical
        investigation or operational decisions.
        - Avoid declaring a root cause or recommending procedures.
        The "missing_information" array must contain specific gaps
        supported by the assessment. Include missing safety procedures
        when relevant to the documented machine configuration and
        proposed activity. If hydraulic-system presence is unverified,
        identify the pressure-system mapping as unresolved rather than
        listing hydraulic pressure-relief/depressurization procedures as
        a confirmed missing requirement. Do not invent gaps that are not
        justified by the supplied input.
        Set "sufficient" to false only when the technical evidence
        is inadequate for a meaningful investigation. Do not set it
        to false solely because approved safety procedures are absent.
        Investigation data:
        {json.dumps(assessment_input, default=str)}
        """

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=GenerateContentConfig(
                    temperature=0,
                    max_output_tokens=8192,
                    response_mime_type="application/json",
                    response_json_schema={
                        "type": "object",
                        "properties": {
                            "sufficient": {"type": "boolean"},
                            "reason": {"type": "string"},
                            "missing_information": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": [
                            "sufficient",
                            "reason",
                            "missing_information",
                        ],
                        "additionalProperties": False,
                    },
                ),
            )
            content = response.text
            # Prefer the SDK's parsed structured-output value when available.
            # Fall back to validating the text because parsed may be None for
            # some model/API responses.
            parsed = getattr(response, "parsed", None)
            if isinstance(parsed, dict):
                result = parsed
            else:
                if not isinstance(content, str):
                    raise ValueError("LLM response is not text")
                # Support JSON returned inside a Markdown code fence.
                content = content.strip()
                content = re.sub(
                    r"^\s*```(?:json)?\s*|\s*```\s*$",
                    "",
                    content,
                    flags=re.IGNORECASE,
                )
                result = json.loads(content)
            # Step 5: Validate the response before trusting it.
            if not isinstance(result.get("sufficient"), bool):
                raise ValueError("Invalid sufficient field")
            if not isinstance(result.get("reason"), str):
                raise ValueError("Invalid reason field")
            missing = result.get("missing_information")
            if (
                not isinstance(missing, list)
                or not all(isinstance(item, str) for item in missing)
            ):
                raise ValueError("Invalid missing_information field")
            sufficient = result["sufficient"]
            return {
                "sufficient": sufficient,
                "reason": result["reason"],
                "evidence": (
                    relevant_evidence if sufficient else []
                ),
                "rejected_count": (
                    len(evidence) - len(relevant_evidence)
                ),
                "missing_information": missing,
            }
        except Exception as exc:
            # Fail closed: an invalid response or API failure
            # must never allow report generation to proceed.
            if isinstance(exc, json.JSONDecodeError):
                candidates = getattr(response, "candidates", None) or []
                candidate = candidates[0] if candidates else None
                finish_reason = getattr(candidate, "finish_reason", None)
                finish_message = getattr(candidate, "finish_message", None)
                raw_text = content if isinstance(content, str) else getattr(response, "text", None)
                preview = repr(raw_text[:1200]) if isinstance(raw_text, str) else repr(raw_text)
                error_detail = (
                    "The model response was not valid JSON "
                    f"(line {exc.lineno}, column {exc.colno}). "
                    f"finish_reason={finish_reason!r}; "
                    f"finish_message={finish_message!r}; "
                    f"response_preview={preview}"
                )
            else:
                error_detail = str(exc)
            return {
                "sufficient": False,
                "reason": (
                    "Evidence sufficiency assessment failed. "
                    "Investigation report generation must stop. "
                    f"Details: {error_detail}"
                ),
                "evidence": [],
                "rejected_count": (
                    len(evidence) - len(relevant_evidence)
                ),
                "missing_information": [
                    "A successful evidence sufficiency assessment"
                ],
            }
