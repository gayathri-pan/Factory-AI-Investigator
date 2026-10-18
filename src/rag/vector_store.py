
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)
from sentence_transformers import SentenceTransformer

from rag.document_loader import ManualDocumentLoader


class FactoryVectorStore:
    """Local Qdrant vector store for machine-aware manual retrieval."""

    def __init__(
        self,
        collection_name="factory_manuals",
        embedding_model="BAAI/bge-small-en-v1.5",
        qdrant_path="data/qdrant",
    ):
        self.collection_name = collection_name

        # Resolve storage consistently from the project root.
        self.project_root = Path(__file__).resolve().parents[2]
        path = Path(qdrant_path)

        if not path.is_absolute():
            path = self.project_root / path

        self.qdrant_path = path.resolve()
        self.qdrant_path.mkdir(parents=True, exist_ok=True)

        print("\nLoading embedding model...")
        self.embedding_model = SentenceTransformer(embedding_model)
        self.vector_size = self.embedding_model.get_embedding_dimension()

        print(f"Embedding dimension: {self.vector_size}")
        print(f"Qdrant storage: {self.qdrant_path}")

        self.client = QdrantClient(path=str(self.qdrant_path))

    def create_collection(self, recreate=False):
        """Create the collection; reset it only when explicitly requested."""
        existing = [
            collection.name
            for collection in self.client.get_collections().collections
        ]

        if self.collection_name in existing:
            if not recreate:
                print(
                    f"Collection already exists: {self.collection_name}"
                )
                return

            print(
                f"Recreating collection: {self.collection_name}. "
                "Existing indexed data will be deleted."
            )
            self.client.delete_collection(
                collection_name=self.collection_name
            )

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=self.vector_size,
                distance=Distance.COSINE,
            ),
        )

        print(f"Collection created: {self.collection_name}")

    def add_documents(self, chunks):
        """Embed chunks and store their text and metadata in Qdrant."""
        if not chunks:
            raise ValueError("No document chunks provided for indexing.")

        texts = [chunk.page_content for chunk in chunks]

        print(f"\nCreating embeddings for {len(texts)} chunks...")

        embeddings = self.embedding_model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=True,
        )

        points = []

        for index, (chunk, embedding) in enumerate(
            zip(chunks, embeddings)
        ):
            payload = {
                "text": chunk.page_content,
                "source": chunk.metadata["source"],
                "file_path": chunk.metadata["file_path"],
                "machine_id": chunk.metadata.get("machine_id"),
                "machine_specific": chunk.metadata.get(
                    "machine_specific", False
                ),
                "chunk_index": index,
            }

            points.append(
                PointStruct(
                    id=index,
                    vector=embedding.tolist(),
                    payload=payload,
                )
            )

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True,
        )

        stored_count = self.client.count(
            collection_name=self.collection_name,
            exact=True,
        ).count

        print(f"Chunks submitted: {len(points)}")
        print(f"Points currently stored: {stored_count}")

    def search(
        self,
        query,
        top_k=5,
        machine_id=None,
        include_global=True,
    ):
        """
        Search semantically.

        If machine_id is supplied, search that machine's documents.
        General documents are also included when include_global=True.
        """
        if not query.strip():
            raise ValueError("Search query cannot be empty.")

        if top_k < 1:
            raise ValueError("top_k must be at least 1.")

        query_embedding = self.embedding_model.encode(
            query,
            normalize_embeddings=True,
        )

        query_filter = None

        if machine_id is not None:
            conditions = [
                FieldCondition(
                    key="machine_id",
                    match=MatchValue(value=machine_id),
                )
            ]

            if include_global:
                conditions.append(
                    FieldCondition(
                        key="machine_specific",
                        match=MatchValue(value=False),
                    )
                )

            # OR: matching machine-specific documents or global documents.
            query_filter = Filter(should=conditions)

        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding.tolist(),
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )

        return results.points


def main():
    print("=" * 60)
    print("FACTORY AI INVESTIGATOR - VECTOR STORE")
    print("=" * 60)

    # 1. Load and split the manuals.
    loader = ManualDocumentLoader()
    documents = loader.load_documents()
    chunks = loader.split_documents(documents)

    print(f"\nDocuments loaded: {len(documents)}")
    print(f"Chunks created: {len(chunks)}")

    # 2. Initialize Qdrant.
    vector_store = FactoryVectorStore()

    # Full rebuild: intentionally remove the old collection and re-index
    # the current manuals. Do this when rebuilding the entire knowledge base.
    vector_store.create_collection(recreate=True)

    # 3. Embed and index the current chunks.
    vector_store.add_documents(chunks)

    # 4. Test machine-aware semantic search.
    query = (
        "For M-104, what should maintenance inspect when "
        "hydraulic pressure changes together with rising temperature?"
    )

    print("\n" + "=" * 60)
    print("MACHINE-AWARE SEMANTIC SEARCH TEST")
    print("=" * 60)
    print(f"\nMachine: M-104")
    print(f"Query: {query}")

    results = vector_store.search(
        query=query,
        top_k=5,
        machine_id="M-104",
        include_global=True,
    )

    for index, result in enumerate(results, start=1):
        payload = result.payload or {}

        print("\n" + "-" * 60)
        print(f"Result {index}")
        print(f"Score: {result.score:.4f}")
        print(f"Source: {payload.get('source')}")
        print(f"Machine ID: {payload.get('machine_id')}")
        print(f"Machine-specific: {payload.get('machine_specific')}")
        print(f"Text:\n{payload.get('text', '')}")

    if not results:
        print("No matching documents were retrieved.")


if __name__ == "__main__":
    main()
