import argparse
import gzip
import hashlib
import json
import os
import tarfile
import tempfile
from pathlib import Path

from google.cloud import storage
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

from rag.vector_store import FactoryVectorStore
from rag.retriever import FactoryRetriever


PROJECT_ID = "project-e64210d0-f317-4050-833"
BUCKET_NAME = "factory-ai-investigator-data-e64210d0-f317-4050-833"


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class CloudFactoryVectorStore(FactoryVectorStore):
    """Restore exported assets and reuse the existing search method."""

    def __init__(self, prefix="rag-artifacts/v1"):
        # Intentionally do not initialize the original local database.
        self.client = None
        self._temporary_directory = tempfile.TemporaryDirectory(
            prefix="factory-rag-"
        )
        self.asset_dir = Path(self._temporary_directory.name)

        try:
            self._load_assets(prefix)
        except Exception:
            self.close()
            raise

    def _load_assets(self, prefix):
        storage_client = storage.Client(
            project=os.getenv("GOOGLE_CLOUD_PROJECT", PROJECT_ID)
        )

        try:
            bucket = storage_client.bucket(BUCKET_NAME)

            def download(filename):
                destination = self.asset_dir / filename
                print(f"Downloading {prefix}/{filename}")
                bucket.blob(
                    f"{prefix}/{filename}"
                ).download_to_filename(str(destination))
                return destination

            manifest_path = download("manifest.json")
            manifest = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )

            if manifest["embedding_model_status"] != "exported_and_verified":
                raise ValueError("Embedding model has not been verified.")

            if (
                manifest["vector_size"] != 384
                or manifest["distance"] != "Cosine"
                or manifest["normalize_embeddings"] is not True
            ):
                raise ValueError("Unexpected vector configuration.")

            # Fixed filenames avoid interpreting arbitrary manifest paths.
            if manifest["points_file"] != "manual_points.jsonl.gz":
                raise ValueError("Unexpected points filename.")

            if (
                manifest["embedding_model_archive"]
                != "embedding_model.tar.gz"
            ):
                raise ValueError("Unexpected model archive filename.")

            points_path = download("manual_points.jsonl.gz")
            model_archive = download("embedding_model.tar.gz")
        finally:
            storage_client.close()

        if sha256_file(points_path) != manifest["points_sha256"]:
            raise ValueError("Points checksum mismatch.")

        if (
            sha256_file(model_archive)
            != manifest["embedding_model_sha256"]
        ):
            raise ValueError("Embedding model checksum mismatch.")

        # Python 3.12 supports the safer data extraction filter.
        with tarfile.open(model_archive, "r:gz") as archive:
            archive.extractall(self.asset_dir, filter="data")

        model_dir = self.asset_dir / "embedding_model"
        self.embedding_model = SentenceTransformer(
            str(model_dir),
            device="cpu",
            local_files_only=True,
        )

        self.vector_size = self.embedding_model.get_embedding_dimension()
        if self.vector_size != manifest["vector_size"]:
            raise ValueError("Model and stored vector dimensions differ.")

        self.collection_name = manifest["collection_name"]
        self.knowledge_base_version = manifest["knowledge_base_version"]
        self.manifest = manifest

        # Each application instance gets its own small in-memory collection.
        self.client = QdrantClient(":memory:")
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=self.vector_size,
                distance=Distance.COSINE,
            ),
        )

        with gzip.open(points_path, "rt", encoding="utf-8") as handle:
            points = [
                PointStruct(**json.loads(line))
                for line in handle
                if line.strip()
            ]

        if len(points) != manifest["point_count"]:
            raise ValueError("Exported point count differs from manifest.")

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True,
        )

        stored_count = self.client.count(
            collection_name=self.collection_name,
            exact=True,
        ).count

        if stored_count != manifest["point_count"]:
            raise ValueError("Restored Qdrant point count mismatch.")

        # Archives are no longer needed after loading.
        model_archive.unlink()
        points_path.unlink()

        print(f"Knowledge-base version: {self.knowledge_base_version}")
        print(f"Restored points: {stored_count}")
        print(f"Embedding dimension: {self.vector_size}")
        print("Cloud RAG assets ready.")

    def close(self):
        try:
            if self.client is not None:
                self.client.close()
                self.client = None
        finally:
            self._temporary_directory.cleanup()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--machine-id", default="M-103")
    parser.add_argument(
        "--query",
        default=(
            "Conveyor drive troubleshooting documentation for "
            "temperature, vibration, pressure, rotational speed "
            "and power consumption observations. "
            "Identify applicable sensor meanings and operating specifications."
        ),
    )
    args = parser.parse_args()

    vector_store = CloudFactoryVectorStore()

    try:
        retriever = FactoryRetriever(
            top_k=3,
            vector_store=vector_store,
        )
        evidence = retriever.retrieve(
            query=args.query,
            machine_id=args.machine_id,
            include_global=True,
        )

        for item in evidence:
            allowed = item["machine_match"] or (
                item["machine_id"] is None
                and item["machine_specific"] is False
            )
            if not allowed:
                raise ValueError("Out-of-scope evidence returned.")

        print(json.dumps(evidence, indent=2, allow_nan=False))
    finally:
        vector_store.close()


if __name__ == "__main__":
    main()