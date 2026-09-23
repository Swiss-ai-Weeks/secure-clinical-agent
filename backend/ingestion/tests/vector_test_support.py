"""Small real byte-level tokenizer for deterministic offline worker tests."""

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from note_vectors import ModelTokenizer  # noqa: E402


class TokenizerTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        try:
            from tokenizers import Tokenizer, models, pre_tokenizers, processors, trainers
        except ImportError:
            self.skipTest("Install backend/ingestion/requirements-vector.txt")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "tokenizer.json"
        tokenizer = Tokenizer(models.BPE(unk_token="[UNK]"))
        tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
        tokenizer.train_from_iterator(
            ["A harmless tokenizer fixture."],
            trainers.BpeTrainer(
                vocab_size=258,
                initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
                special_tokens=["<|begin_of_text|>", "[UNK]"],
                show_progress=False,
            ),
        )
        tokenizer.post_processor = processors.TemplateProcessing(
            single="<|begin_of_text|> $A",
            special_tokens=[("<|begin_of_text|>", 0)],
        )
        tokenizer.save(str(path))
        self.tokenizer = ModelTokenizer(path, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        self.tokenizer_path = path
        patched = patch("notes._tokenizer", return_value=self.tokenizer)
        patched.start()
        self.addCleanup(patched.stop)
