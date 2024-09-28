import chromadb
import grep_ast
from pathlib import Path

from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
from llama_index.core import StorageContext
from llama_index.readers.file import FlatReader
from llama_index.core.node_parser import CodeSplitter
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.embeddings.ollama import OllamaEmbedding

def get_last_modified_time(file_path: str):
    path = Path(file_path).resolve()
    last_modified = path.stat().st_mtime
    return last_modified

# TODO: seperate methods for loading and retrieval

def main():
    repo_dir = "/home/sikfeng/raid/auto-sw-dev/raider-backend"
    query = "auto-complete"

    #extensions = ["js", "jsx", "ts", "tsx", "py"]
    extensions = ["py"]

    chroma_client = chromadb.PersistentClient(path=str(Path(repo_dir) / ".chroma_db"))

    embed_model = OllamaEmbedding(
        model_name="nomic-embed-text",
        base_url="http://localhost:11434",
        ollama_additional_kwargs={"mirostat": 0},
    )

    # TODO: handle different extensions together
    nodes = {}
    for extension in extensions:
        chroma_collection = chroma_client.get_or_create_collection("ext-" + extension)
        vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
        index = VectorStoreIndex.from_vector_store(
            vector_store,
            embed_model=embed_model,
        )

        try:
            print("Parsing", extension)
            reader = SimpleDirectoryReader(
                input_dir=repo_dir,
                recursive=True,
                required_exts=["." + extension],
                file_extractor={"." + extension: FlatReader()},
            )
            documents = reader.load_data(show_progress=True)
            print("Documents:", len(documents))
        except ValueError:
            print("Failed to find documents:", extension)
            continue

        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        collection_info = chroma_collection.get()
        db_files = {file_metadata["file_path"] for file_metadata in collection_info["metadatas"]}

        repo_files = reader.list_resources()

        to_delete_files = db_files - set(repo_files)
        to_add_files = set(repo_files) - db_files
        to_update_files = set()

        for file_path in set(repo_files) - to_delete_files - to_add_files:
            modified_files = chroma_collection.get(
                limit=1, # Only necessary to know of existence, hence 1 is sufficient
                where={
                    "$and": [
                        {"file_path": file_path},
                        {"last_modified_time": {"$lt": get_last_modified_time(file_path)}}
                    ]
                }
            )
            if modified_files["ids"]:
                print(modified_files)
                to_update_files.add(file_path)

        print("Files to delete:", to_delete_files)
        print("Files to add:", to_add_files)
        print("Files to update:", to_update_files)

        to_delete_files.update(to_update_files)
        to_add_files.update(to_update_files)

        to_delete_files = list(to_delete_files)
        to_add_files = list(to_add_files)

        if to_delete_files:
            #to_delete_ids = [collection_info["ids"][i] for i in range(chroma_collection.count()) if collection_info["metadatas"][i]["file_path"] in to_delete_files]
            to_delete_ids = chroma_collection.get(where={"file_path": {"$in": list(to_delete_files)}})["ids"]
            chroma_collection.delete(ids=to_delete_ids)
            print("Deleted")
        
        if to_add_files:
            reader = SimpleDirectoryReader(
                input_files=to_add_files,
                required_exts=["." + extension],
                file_extractor={"." + extension: FlatReader()},
            )
            documents = reader.load_data()
            for document in documents:
                document.metadata["last_modified_time"] = get_last_modified_time(document.metadata["file_path"])
            parser = CodeSplitter.from_defaults(
                language = grep_ast.filename_to_lang("file." + extension),
            )
            nodes[extension] = parser.get_nodes_from_documents(documents)

            index.insert_nodes(nodes[extension], show_progress=True)
            print("Added")


        # TODO: an idea that I have is to generate keywords based on each snippet, on what feature it has
        # something like https://docs.llamaindex.ai/en/stable/examples/index_structs/doc_summary/DocSummary/
        # then we can use tf-idf to index
        # we then somehow use the two similarity scores (weighted average? some power mean with some $p$?)
        # https://docs.llamaindex.ai/en/stable/examples/retrievers/reciprocal_rerank_fusion/

        # actually, we might need to consider the superclass of methods and their imports, which means we have some kind of graph
        # may need to go up the tree

        # do some filtering with metadata
        # https://docs.llamaindex.ai/en/stable/examples/vector_stores/chroma_auto_retriever/
    
        retriever = index.as_retriever()
        nodes = retriever.retrieve(query)
        print(nodes)


if __name__ == "__main__":
    main()

