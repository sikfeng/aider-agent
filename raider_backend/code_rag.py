import asyncio
import logging
from pathlib import Path
from typing import List

import chromadb
import grep_ast
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
from llama_index.core.node_parser import CodeSplitter
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.readers.file import FlatReader
from llama_index.vector_stores.chroma import ChromaVectorStore

from raider_backend import utils

from chromadb.config import Settings
client = chromadb.Client(Settings(anonymized_telemetry=False))


class CodeRAG:
    def __init__(self, repo_dir: str, extensions: List[str]):
        self.repo_dir = repo_dir
        self.extensions = extensions

        self.logger = logging.getLogger(__class__.__name__)

        self.chroma_client = chromadb.PersistentClient(path=str(Path(self.repo_dir) / ".chroma_db"))
        self.embed_model = OllamaEmbedding(
            model_name="nomic-embed-text",
            base_url="http://localhost:11434",
            ollama_additional_kwargs={"mirostat": 0},
        )
        # TODO: create option to disable this
        asyncio.create_task(self.update())


    async def update(self):
        while True:
            self.update_db()
            await asyncio.sleep(5)


    def update_db(self):
        nodes = {}

        # TODO: dont seperate the extensions, use metadata to determine the extension, in one database
        for extension in self.extensions:
            chroma_collection = self.chroma_client.get_or_create_collection("ext-" + extension)
            vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
            index = VectorStoreIndex.from_vector_store(
                vector_store,
                embed_model=self.embed_model,
            )

            try:
                self.logger.debug("Parsing %s", extension)
                reader = SimpleDirectoryReader(
                    input_dir=self.repo_dir,
                    recursive=True,
                    required_exts=["." + extension],
                    file_extractor={"." + extension: FlatReader()},
                )
                documents = reader.load_data(show_progress=True)
                self.logger.debug("Documents found: %s", len(documents))
            except ValueError:
                self.logger.debug("Failed to find documents of extension %s", extension)
                continue

            collection_info = chroma_collection.get()
            db_files: set[str] = {file_metadata["file_path"] for file_metadata in collection_info["metadatas"]}

            repo_files = reader.list_resources()

            to_delete_files = db_files - set(repo_files)
            to_add_files = set(repo_files) - db_files
            to_update_files: set[str] = set()

            for file_path in set(repo_files) - to_delete_files - to_add_files:
                modified_files = chroma_collection.get(
                    limit=1, # Only necessary to know of existence, hence 1 is sufficient
                    where={
                        "$and": [
                            {"file_path": file_path},
                            {"last_modified_time": {"$lt": utils.get_last_modified_time(file_path)}}
                        ]
                    }
                )
                if modified_files["ids"]:
                    to_update_files.add(file_path)

            self.logger.info("Files to delete: %s", to_delete_files)
            self.logger.info("Files to add: %s", to_add_files)
            self.logger.info("Files to update: %s", to_update_files)

            to_delete_files.update(to_update_files)
            to_add_files.update(to_update_files)

            to_delete_files = list(to_delete_files)
            to_add_files = list(to_add_files)

            if to_delete_files:
                to_delete_ids = chroma_collection.get(where={"file_path": {"$in": list(to_delete_files)}})["ids"]
                chroma_collection.delete(ids=to_delete_ids)
                self.logger.info("Deleted %s from db", to_delete_files)

            if to_add_files:
                reader = SimpleDirectoryReader(
                    input_files=to_add_files,
                    required_exts=["." + extension],
                    file_extractor={"." + extension: FlatReader()},
                )
                documents = reader.load_data()
                for document in documents:
                    document.metadata["last_modified_time"] = utils.get_last_modified_time(document.metadata["file_path"])
                parser = CodeSplitter.from_defaults(
                    language = grep_ast.filename_to_lang("file." + extension),
                )
                nodes[extension] = parser.get_nodes_from_documents(documents)

                index.insert_nodes(nodes[extension], show_progress=True)
                self.logger.info("Added %s to db", to_add_files)

            # TODO: an idea that I have is to generate keywords based on each snippet, on what feature it has
            # something like https://docs.llamaindex.ai/en/stable/examples/index_structs/doc_summary/DocSummary/
            # then we can use tf-idf to index
            # we then somehow use the two similarity scores (weighted average? some power mean with some $p$?)
            # https://docs.llamaindex.ai/en/stable/examples/retrievers/reciprocal_rerank_fusion/

            # actually, we might need to consider the superclass of methods and their imports, which means we have some kind of graph
            # may need to go up the tree

            # do some filtering with metadata
            # https://docs.llamaindex.ai/en/stable/examples/vector_stores/chroma_auto_retriever/


    def retrieve(self, query: str) -> List[str]:

        retrieved_nodes = []

        for extension in self.extensions:
            chroma_collection = self.chroma_client.get_or_create_collection("ext-" + extension)
            vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
            index = VectorStoreIndex.from_vector_store(
                vector_store,
                embed_model=self.embed_model,
            )

            retriever = index.as_retriever(similarity_top_k=5)
            nodes = retriever.retrieve(query)

            # TODO: perform reranking
            retrieved_nodes += [node.get_text() for node in nodes]

        return retrieved_nodes
