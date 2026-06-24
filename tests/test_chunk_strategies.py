from __future__ import annotations

from code_rag.apps.chunking.strategies import PythonChunker, RegexChunker, TextChunker
from code_rag.config.settings import Settings
from code_rag.domain.enums.chunk_kind import ChunkKind


def _text_chunker(**overrides) -> TextChunker:
    return TextChunker(Settings(**overrides))


def test_python_chunker_extracts_class_and_methods() -> None:
    chunker = PythonChunker(Settings(), _text_chunker())
    source = "import os\n\n\nclass Service:\n    def run(self):\n        return os.getcwd()\n"

    chunks = chunker.chunk(source)

    kinds = {chunk.symbol_name: chunk.kind for chunk in chunks}
    assert kinds["Service"] == ChunkKind.CLASS_DEFINITION
    assert kinds["run"] == ChunkKind.METHOD_DEFINITION
    run = next(chunk for chunk in chunks if chunk.symbol_name == "run")
    assert run.parent_symbol == "Service"
    assert "os" in run.imports


def test_python_chunker_falls_back_to_fixed_size_on_syntax_error() -> None:
    chunker = PythonChunker(Settings(), _text_chunker())

    chunks = chunker.chunk("def broken(:\n")

    assert chunks
    assert all(chunk.kind == ChunkKind.FILE for chunk in chunks)


def test_regex_chunker_returns_empty_when_no_declarations() -> None:
    chunker = RegexChunker(Settings(), _text_chunker())

    assert chunker.chunk("plain prose with no code declarations") == []


def test_regex_chunker_flags_test_cases() -> None:
    chunker = RegexChunker(Settings(), _text_chunker())

    chunks = chunker.chunk("function testLogin() {\n  assert(true);\n}\n")

    assert chunks[0].kind == ChunkKind.TEST_CASE


def test_text_chunker_overlap_carries_context() -> None:
    chunker = _text_chunker(max_chunk_chars=10, chunk_overlap_lines=1)

    chunks = chunker.fixed_size_chunks("a\nb\nc\nd\n", ChunkKind.FILE)

    assert len(chunks) > 1
    # Consecutive windows overlap by one line.
    assert chunks[1].line_start <= chunks[0].line_end


def test_text_chunker_markdown_splits_on_headings() -> None:
    chunker = _text_chunker()

    chunks = chunker.markdown_chunks("# Title\nbody\n## Section\nmore\n")

    assert [chunk.symbol_name for chunk in chunks] == ["Title", "Section"]
