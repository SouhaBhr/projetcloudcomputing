import os
import functions_framework
from cloudevents.http import CloudEvent

_mongo_client = None
_collection = None
_embeddings = None

def get_collection():
    global _mongo_client, _collection
    if _collection is None:
        from pymongo import MongoClient
        MONGO_URI = os.environ.get("MONGO_URI")
        if not MONGO_URI:
            raise ValueError("MONGO_URI environment variable not set")
        _mongo_client = MongoClient(MONGO_URI)
        _collection = _mongo_client["smartstudy"]["context"]
    return _collection

def get_embeddings():
    global _embeddings
    if _embeddings is None:
        from langchain_google_vertexai import VertexAIEmbeddings
        _embeddings = VertexAIEmbeddings(
            model_name="text-embedding-005",
            project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
            location=os.environ.get("LOCATION", "europe-west1")
        )
    return _embeddings


def load_pdf_robust(local_path: str):
    """
    Charge un PDF avec fallback : essaie d'abord PyMuPDFLoader (plus tolérant),
    puis PyPDFLoader si ça échoue. Lève une exception si les deux échouent.
    """
    from langchain_community.document_loaders import PyMuPDFLoader, PyPDFLoader

    # Try 1 : PyMuPDFLoader (first choice, more robust to weird PDFs)
    try:
        loader = PyMuPDFLoader(local_path)
        documents = loader.load()
        print(f"PyMuPDFLoader OK: {len(documents)} pages")
        return documents
    except Exception as e:
        print(f"PyMuPDFLoader failed: {type(e).__name__}: {e}. Trying PyPDFLoader...")

    # Try 2 : PyPDFLoader (fallback)
    try:
        loader = PyPDFLoader(local_path)
        documents = loader.load()
        print(f"PyPDFLoader OK: {len(documents)} pages")
        return documents
    except Exception as e:
        print(f"PyPDFLoader also failed: {type(e).__name__}: {e}")
        raise RuntimeError(f"Cannot parse PDF: both loaders failed. Last error: {e}")


@functions_framework.cloud_event
def process_pdf(cloud_event: CloudEvent):
    data = cloud_event.data
    bucket_name = data["bucket"]
    file_name = data["name"]

    print(f"Triggered for {file_name} in {bucket_name}")

    if not file_name.endswith(".pdf"):
        print("Not a PDF, skipping.")
        return

    try:
        from google.cloud import storage
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        from langchain_mongodb import MongoDBAtlasVectorSearch

        # Download
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(file_name)
        local_path = f"/tmp/{os.path.basename(file_name)}"
        blob.download_to_filename(local_path)
        print(f"Downloaded {file_name} to {local_path}")

        # Load PDF
        documents = load_pdf_robust(local_path)

        if not documents:
            print(f"No content extracted from {file_name}, skipping.")
            return

        # Split
        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        split_docs = splitter.split_documents(documents)
        for doc in split_docs:
            doc.metadata["source"] = file_name

        vector_store = MongoDBAtlasVectorSearch(
            collection=get_collection(),
            embedding=get_embeddings(),
            index_name="vector_index",
        )

        vector_store.add_documents(split_docs)
        print(f"Inserted {len(split_docs)} chunks from {file_name}")

    except Exception as e:
        print(f"ERROR processing {file_name}: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise