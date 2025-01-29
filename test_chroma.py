# test_chroma.py

import chromadb
from chromadb.config import Settings
import openai
import os
import uuid
import logging

# 配置日志记录
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")

# 从环境变量读取 OpenAI API 密钥
openai.api_key = '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'

# 初始化 ChromaDB，使用 PersistentClient 并指定持久化目录，同时禁用遥测
persist_dir = "./temp_chroma"
if not os.path.exists(persist_dir):
    os.makedirs(persist_dir)
    logging.debug(f"Created persist_directory at {persist_dir}")

# 使用新的 PersistentClient 初始化方式
chroma_client = chromadb.PersistentClient(
    path=persist_dir,
    settings=Settings(anonymized_telemetry=False)  # 禁用遥测
)
collection = chroma_client.get_or_create_collection(name="test_collection")

# 示例文本块
texts = [
    "这是第一个测试文本块，用于验证 ChromaDB 的嵌入和存储功能。",
    "这是第二个测试文本块，确保多个文本块能够被正确处理。"
]

# 获取嵌入
def get_embedding(text):
    try:
        resp = openai.Embedding.create(
            model="text-embedding-ada-002",
            input=text
        )
        logging.debug(f"Generated embedding for text: {text[:50]}...")
        return resp["data"][0]["embedding"]
    except openai.error.OpenAIError as e:
        logging.exception("Error generating embedding:")
        return None

embeddings = [get_embedding(text) for text in texts]

# 存储到 ChromaDB
for i, (text, emb) in enumerate(zip(texts, embeddings)):
    if emb:
        doc_id = str(uuid.uuid4())
        try:
            logging.debug(f"Adding chunk {i} with doc_id {doc_id}")
            collection.add(
                documents=[text],
                embeddings=[emb],
                ids=[doc_id],
                metadatas=[{"chunk_index": i}]
            )
            logging.debug(f"Successfully added chunk {i} to ChromaDB.")
        except Exception as e:
            logging.exception(f"Error embedding/storing chunk {i}: {text[:100]}")
            continue
    else:
        logging.warning(f"Embedding failed for chunk {i}. Skipping...")

logging.debug("Finished embedding and storing all chunks in ChromaDB.")

# 查询 ChromaDB
logging.debug("Starting query process.")
for i, text in enumerate(texts):
    emb = embeddings[i]
    if emb:
        try:
            logging.debug(f"Querying chunk {i}")
            results = collection.query(
                query_embeddings=[emb],
                n_results=1
            )
            logging.debug(f"Query result for chunk {i}: {results}")
        except Exception as e:
            logging.exception(f"Error querying chunk {i}:")
logging.debug("Finished query process.")
