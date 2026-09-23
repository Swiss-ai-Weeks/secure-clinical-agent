import copy
import io
import json
import math
import os
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "ingestion"))

from note_vectors import (  # noqa: E402
    MODEL,
    ModelTokenizer,
    VectorPreparationError,
    chunk_note,
    embed_inputs,
    input_text,
)
from notes import (  # noqa: E402
    NotesError,
    embed_prepared,
    main,
    prepare_note,
    publish_prepared,
    save_prepared,
)
from patient360.deid import IdentityHints  # noqa: E402
from vector_test_support import TokenizerTestCase  # noqa: E402


class ChunkTests(TokenizerTestCase):
    def chunks(self, text):
        return chunk_note(text, self.tokenizer, note_id="opaque-note", deid_version="test-policy")

    def test_exact_offsets_unicode_whitespace_and_repeated_headings(self):
        body = ("Café 🩺 — no pain.\tRepeated  spaces remain.\n" * 45) + "\nLast line.\n"
        text = "Introductory text.\n\n## History\n" + body + "## Plan\nContinue exercise.\n"
        chunks = self.chunks(text)
        self.assertGreater(len(chunks), 3)
        coverage = set()
        for chunk in chunks:
            start, end = chunk["start_offset"], chunk["end_offset"]
            self.assertEqual(text[start:end], chunk["text"])
            coverage.update(range(start, end))
            self.assertLessEqual(self.tokenizer.content_count(input_text(chunk)), 512)
            self.assertEqual(chunk["content_token_count"], self.tokenizer.content_count(input_text(chunk)))
            self.assertEqual(chunk["input_token_count"], self.tokenizer.input_count(input_text(chunk)))
            if chunk["heading_context"]:
                hs, he = chunk["heading_start_offset"], chunk["heading_end_offset"]
                self.assertEqual(text[hs:he], chunk["heading_context"])
                self.assertNotIn(chunk["heading_context"], chunk["text"])
                coverage.update(range(hs, he))
        self.assertTrue(all(i in coverage for i, character in enumerate(text) if not character.isspace()))
        history = [c for c in chunks if c["heading_context"] == "## History"]
        self.assertGreater(len(history), 1)
        for left, right in zip(history, history[1:], strict=False):
            self.assertGreater(right["end_offset"], left["end_offset"])
            self.assertLessEqual(right["start_offset"], left["end_offset"])
            overlap = text[right["start_offset"] : left["end_offset"]]
            self.assertLessEqual(self.tokenizer.content_count(overlap), 64)

    def test_long_unbroken_text_and_source_heading_only_are_not_lost(self):
        text = "# Heading only\n## Content\n" + "α" * 1800
        chunks = self.chunks(text)
        self.assertEqual(chunks[0]["text"], "# Heading only\n")
        self.assertEqual(chunks[-1]["end_offset"], len(text))
        self.assertTrue(all(c["content_token_count"] <= 512 for c in chunks))

    def test_heading_that_exhausts_budget_fails_instead_of_truncating(self):
        with self.assertRaisesRegex(VectorPreparationError, "heading_or_body_exceeds_budget"):
            self.chunks("## " + "x" * 600 + "\nA body sentence.")

    def test_preparation_ids_change_with_content_policy_and_tokenizer(self):
        first = self.chunks("## Plan\nContinue exercise.")
        self.assertEqual(first, self.chunks("## Plan\nContinue exercise."))
        other = self.chunks("## Plan\nStop exercise.")
        self.assertNotEqual(first[0]["preparation_chunk_id"], other[0]["preparation_chunk_id"])
        other = chunk_note(
            "## Plan\nContinue exercise.", self.tokenizer, note_id="opaque-note", deid_version="new-policy"
        )
        self.assertNotEqual(first[0]["preparation_chunk_id"], other[0]["preparation_chunk_id"])
        self.tokenizer.policy_id = "changed-tokenizer-policy"
        self.assertNotEqual(
            first[0]["preparation_chunk_id"],
            self.chunks("## Plan\nContinue exercise.")[0]["preparation_chunk_id"],
        )

    def test_no_missing_or_wrong_tokenizer_fallback(self):
        for path, reason in (
            ("", "required"),
            ("/nonexistent/tokenizer", "unavailable"),
            (self.tokenizer_path, "hash_mismatch"),
        ):
            with self.subTest(reason=reason), self.assertRaisesRegex(VectorPreparationError, reason):
                ModelTokenizer(path)


class EmbeddingTests(TokenizerTestCase):
    def response(self, body):
        return {
            "model": MODEL,
            "data": [{"index": i, "embedding": [float(i + 1)] * 2048} for i in range(len(body["input"]))],
            "usage": {
                "prompt_tokens": sum(self.tokenizer.input_count(t, body["input_type"]) for t in body["input"])
            },
        }

    def test_reorders_response_indices_and_batches_without_truncation(self):
        calls = []

        def request(body):
            calls.append(body)
            result = self.response(body)
            result["data"].reverse()
            return result

        vectors = embed_inputs(["harmless text"] * 10, self.tokenizer, request)
        self.assertEqual([len(c["input"]) for c in calls], [8, 2])
        self.assertTrue(all(c["truncate"] == "NONE" and c["input_type"] == "passage" for c in calls))
        self.assertEqual([v[0] for v in vectors], [1, 2, 3, 4, 5, 6, 7, 8, 1, 2])

    def test_rejects_malformed_or_incompatible_outputs(self):
        def duplicate(r):
            r["data"][1]["index"] = 0

        def missing(r):
            r["data"][0].pop("index")

        def out_of_range(r):
            r["data"][0]["index"] = 9

        def wrong_model(r):
            r["model"] = "other"

        def wrong_count(r):
            r["data"].pop()

        def wrong_dimension(r):
            r["data"][0]["embedding"] = [1.0]

        def zero(r):
            r["data"][0]["embedding"] = [0.0] * 2048

        def nan(r):
            r["data"][0]["embedding"][0] = float("nan")

        def infinity(r):
            r["data"][0]["embedding"][0] = float("inf")

        def string(r):
            r["data"][0]["embedding"][0] = "1"

        def boolean(r):
            r["data"][0]["index"] = True

        def missing_usage(r):
            r.pop("usage")

        def wrong_usage(r):
            r["usage"]["prompt_tokens"] += 1

        for mutate in (
            duplicate,
            missing,
            out_of_range,
            wrong_model,
            wrong_count,
            wrong_dimension,
            zero,
            nan,
            infinity,
            string,
            boolean,
            missing_usage,
            wrong_usage,
        ):
            with self.subTest(case=mutate.__name__):

                def request(body, mutate=mutate):
                    result = self.response(body)
                    mutate(result)
                    return result

                with self.assertRaises(VectorPreparationError):
                    embed_inputs(["first", "second"], self.tokenizer, request)

    def test_preflights_all_inputs_before_sending_any_request(self):
        with patch("notes._http_json") as request:
            with self.assertRaisesRegex(VectorPreparationError, "chunk_token_limit"):
                embed_inputs(["fine"] * 8 + ["x" * 600], self.tokenizer, request)
            request.assert_not_called()

    def test_model_never_sees_removed_canaries_and_artifact_stays_unpublished(self):
        raw = "## History of Example Person\nExample Person reports no pain."
        prepared = prepare_note("opaque-note", raw, IdentityHints(names=("Example Person",)))

        def http(method, url, body, key):
            self.assertNotIn("Example Person", json.dumps(body))
            self.assertTrue(body["input"][0].startswith("## History of <PERSON>\n\n"))
            return self.response(body)

        with patch("notes._http_json", side_effect=http):
            embedded = embed_prepared(prepared, "http://embed")
        self.assertEqual(embedded["stage"], "embedded")
        self.assertFalse(embedded["published"])
        self.assertNotIn("vector", prepared["chunks"][0])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "restricted" / "embedded.json"
            save_prepared(path, embedded)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(json.loads(path.read_text()), embedded)

    def test_failed_sanitization_and_changed_artifacts_never_reach_model(self):
        prepared = prepare_note("opaque-note", "A harmless note.")
        for mutation in ("ok", "text", "chunks", "chunk_policy_id", "preparation_id", "tokenizer_sha256"):
            changed = copy.deepcopy(prepared)
            changed[mutation] = False if mutation == "ok" else "tampered"
            with (
                patch("notes._http_json") as request,
                self.assertRaises((NotesError, VectorPreparationError)),
            ):
                embed_prepared(changed, "http://embed")
            request.assert_not_called()

    def test_no_publication_from_unverified_preparation(self):
        prepared = prepare_note("opaque-note", "A harmless note.")
        with patch("notes._http_json") as request:
            record = publish_prepared(prepared, {"patient_key": "opaque"}, qdrant_url="http://store", api_key="")
        request.assert_not_called()
        self.assertFalse(record["published"])
        self.assertEqual(record["ledger"], "withhold")

    def test_cli_prepares_restricted_artifacts_without_model_or_store_calls(self):
        prepared = prepare_note("p101-admission-2026-09-10", "Harmless library opening hours.")
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("notes.first_cohort", return_value=[prepared]),
            patch("notes._http_json") as request,
            redirect_stdout(io.StringIO()) as output,
        ):
            status = main(["--prepare-only", "--output", tmp])
            self.assertEqual(status, 0)
            request.assert_not_called()
            self.assertEqual(json.loads(output.getvalue())["published"], 0)
            files = list(Path(tmp).rglob("*.json"))
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].name, "chunked.json")
            self.assertEqual(stat.S_IMODE(files[0].stat().st_mode), 0o600)

    def test_cli_later_batch_failure_keeps_chunks_but_no_partial_embedded_artifact(self):
        prepared = prepare_note("p101-admission-2026-09-10", "The library opens at nine. " * 200)
        self.assertGreater(len(prepared["chunks"]), 8)
        calls = []

        def http(method, url, body, key):
            calls.append(body)
            if len(calls) == 2:
                raise RuntimeError("untrusted server response with source text")
            return self.response(body)

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("notes.first_cohort", return_value=[prepared]),
            patch("notes._http_json", side_effect=http),
            redirect_stdout(io.StringIO()) as output,
        ):
            status = main(["--embed-only", "--embed-url", "http://embed", "--output", tmp])
            self.assertEqual(status, 2)
            self.assertEqual(len(calls), 2)
            summary = json.loads(output.getvalue())
            self.assertEqual(summary["embedded"], 0)
            self.assertEqual(summary["reasons"], {"embedding_service_unavailable": 1})
            self.assertEqual([p.name for p in Path(tmp).rglob("*.json")], ["chunked.json"])
            self.assertNotIn("source text", output.getvalue())


@unittest.skipUnless(os.environ.get("RUN_EMBEDDING_LIVE_TESTS") == "1", "live NIM probes opt in")
class LiveEmbeddingTests(unittest.TestCase):
    def test_harmless_section_chunks_use_actual_tokenizer_and_model(self):
        tokenizer = ModelTokenizer(os.environ["PATIENT360_EMBED_TOKENIZER"])
        text = "## Library hours\n" + ("The library opens at nine.\n" * 140)
        prepared = prepare_note("harmless-live-probe", text, tokenizer=tokenizer)
        embedded = embed_prepared(
            prepared, os.environ.get("PATIENT360_EMBED_URL", "http://127.0.0.1:8001"), tokenizer=tokenizer
        )
        self.assertGreater(len(embedded["chunks"]), 1)
        self.assertFalse(embedded["published"])
        for chunk in embedded["chunks"]:
            self.assertEqual(text[chunk["start_offset"] : chunk["end_offset"]], chunk["text"])
            self.assertEqual(chunk["heading_context"], "## Library hours")
            self.assertLessEqual(chunk["content_token_count"], 512)
            self.assertEqual(len(chunk["vector"]), 2048)
            self.assertTrue(all(math.isfinite(x) for x in chunk["vector"]))


if __name__ == "__main__":
    unittest.main()
