from __future__ import annotations

import unittest

from latent_trace_tomography.collection import CompletionRecord


class CollectionContractTests(unittest.TestCase):
    def test_raw_evidence_keeps_telemetry_outside_text(self) -> None:
        record = CompletionRecord(
            text="FINAL: ACCEPT",
            provider_name="example",
            model_alias="opaque-endpoint",
            requested_params={"temperature": 0.0},
            transmitted_params={},
            timestamp_utc="2026-07-17T00:00:00Z",
            latency_ms=42.0,
            usage={"output_tokens": 3},
        )
        self.assertEqual(record.text, "FINAL: ACCEPT")
        self.assertNotIn("42", record.text)
        self.assertNotIn("output_tokens", record.text)


if __name__ == "__main__":
    unittest.main()
