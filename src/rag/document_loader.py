
from pathlib import Path
import re
import warnings

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


class ManualDocumentLoader:
    """Load Markdown machine manuals and split them into metadata-aware chunks."""

    def __init__(
        self,
        manual_dir="data/manuals",
        chunk_size=500,
        chunk_overlap=100,
    ):
        # Project root: factory-ai-investigator/
        self.project_root = Path(__file__).resolve().parents[2]

        # Resolve relative paths from the project root.
        manual_path = Path(manual_dir)
        if manual_path.is_absolute():
            self.manual_dir = manual_path
        else:
            self.manual_dir = self.project_root / manual_path

        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than zero.")

        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError(
                "chunk_overlap must be non-negative and smaller "
                "than chunk_size."
            )

        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def get_machine_metadata(self, file_path):
        """Infer machine scope from filenames beginning with M followed by digits."""
        filename = file_path.stem

        match = re.match(r"M(\d+)_", filename, re.IGNORECASE)

        if match:
            return {
                "machine_id": f"M-{match.group(1)}",
                "machine_specific": True,
            }

        # General documents, such as Safety_Procedures.md.
        return {
            "machine_id": None,
            "machine_specific": False,
        }

    def load_documents(self):
        """Load non-empty Markdown files and attach source metadata."""
        if not self.manual_dir.is_dir():
            raise FileNotFoundError(
                f"Manual directory does not exist: {self.manual_dir}"
            )

        # Sorting makes document loading and debugging reproducible.
        file_paths = sorted(
            self.manual_dir.glob("*.md"),
            key=lambda path: path.name.lower(),
        )

        if not file_paths:
            raise FileNotFoundError(
                f"No Markdown files found in: {self.manual_dir}"
            )

        documents = []

        for file_path in file_paths:
            text = file_path.read_text(encoding="utf-8")

            if not text.strip():
                warnings.warn(
                    f"Skipping empty Markdown file: {file_path.name}",
                    stacklevel=2,
                )
                continue

            machine_metadata = self.get_machine_metadata(file_path)

            document = Document(
                page_content=text,
                metadata={
                    "source": file_path.name,
                    "file_path": str(file_path.resolve()),
                    **machine_metadata,
                },
            )

            documents.append(document)

        if not documents:
            raise ValueError(
                f"No non-empty Markdown documents found in: "
                f"{self.manual_dir}"
            )

        return documents

    def split_documents(self, documents):
        """Split documents while retaining their metadata on each chunk."""
        return self.text_splitter.split_documents(documents)


def main():
    print("=" * 60)
    print("FACTORY AI INVESTIGATOR - DOCUMENT LOADER")
    print("=" * 60)

    loader = ManualDocumentLoader()
    documents = loader.load_documents()

    print(f"\nDocuments loaded: {len(documents)}")

    for document in documents:
        print(
            f" - {document.metadata['source']} "
            f"(machine_id={document.metadata['machine_id']})"
        )

    chunks = loader.split_documents(documents)

    print(f"\nTotal chunks: {len(chunks)}")
    print("\nFirst 5 chunks:")
    print("-" * 60)

    for i, chunk in enumerate(chunks[:5], start=1):
        print(f"\nChunk {i}")
        print(f"Source: {chunk.metadata['source']}")
        print(f"Machine ID: {chunk.metadata['machine_id']}")
        print(f"Machine-specific: {chunk.metadata['machine_specific']}")
        print(f"Characters: {len(chunk.page_content)}")
        print(f"Content:\n{chunk.page_content[:300]}...")


if __name__ == "__main__":
    main()
