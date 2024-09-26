import chromadb
import grep_ast
from pathlib import Path

from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
from llama_index.core import StorageContext
from llama_index.readers.file import FlatReader
from llama_index.core.node_parser import CodeSplitter
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.embeddings.ollama import OllamaEmbedding

# TODO: seperate methods for loading and retrieval

def main():
    repo_dir = "/home/sikfeng/raid/auto-sw-dev/continue"
    query = "auto-complete"

    #extensions = ["js", "jsx", "ts", "tsx", "py"]
    extensions = ["js"]

    chroma_client = chromadb.EphemeralClient()

    embed_model = OllamaEmbedding(
        model_name="nomic-embed-text",
        base_url="http://localhost:11434",
        ollama_additional_kwargs={"mirostat": 0},
    )

    nodes = {}
    for extension in extensions:
        # TODO: make try catch block narrower
        try:
            print("Parsing", extension)
            reader = SimpleDirectoryReader(input_dir=repo_dir, recursive=True, required_exts=["." + extension], file_extractor={"." + extension: FlatReader()})
            documents = reader.load_data()
            print("Documents:", len(documents))

            parser = CodeSplitter.from_defaults(
                language = grep_ast.filename_to_lang("file." + extension),
            )
            nodes[extension] = parser.get_nodes_from_documents(documents)
            print("Nodes:", len(nodes[extension]))

            chroma_collection = chroma_client.get_or_create_collection("ext-" + extension)
            vector_store = ChromaVectorStore(chroma_collection=chroma_collection)

            # TODO: if index not persisted
            if True:
                storage_context = StorageContext.from_defaults(vector_store=vector_store)
                index = VectorStoreIndex(
                    nodes[extension], storage_context=storage_context, embed_model=embed_model, show_progress=True,
                )
                """
                index = VectorStoreIndex.from_documents(
                    documents, storage_context=storage_context, embed_model=embed_model, show_progress=True,
                )
                """
                storage_context.persist(persist_dir=Path(repo_dir) / extension)
            else:
                # TODO: load index
                pass
                storage_context = StorageContext.from_defaults(
                    vector_store=ChromaVectorStore.from_persist_dir(
                        persist_dir=Path(repo_dir) / extension
                    ),
                    index_store=VectorStoreIndex.from_persist_dir(persist_dir=Path(repo_dir) / extension),
                )
                index = load_index_from_storage(storage_context)

            # TODO: update index if necessary
            # https://docs.llamaindex.ai/en/stable/module_guides/indexing/document_management/
            # https://python.langchain.com/docs/how_to/indexing/

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
        except:
            print("Failed:", extension)


if __name__ == "__main__":
    main()

