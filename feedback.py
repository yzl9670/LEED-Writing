# feedback.py

import os
import logging
import openai
import PyPDF2
from docx import Document
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
import chromadb
from chromadb.config import Settings

# 配置日志记录
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("feedback.log"),
        logging.StreamHandler()
    ]
)


openai.api_key = os.getenv('OPENAI_API_KEY')

if not openai.api_key:
    logging.error("OpenAI API key not found. Please set the OPENAI_API_KEY environment variable.")
    raise EnvironmentError("OpenAI API key not found. Please set the OPENAI_API_KEY environment variable.")

# Initialize ChromaDB, use PersistentClient and specify the persistence directory, and disable telemetry
persist_dir = "./temp_chroma"
if not os.path.exists(persist_dir):
    os.makedirs(persist_dir)
    logging.debug(f"Created persist_directory at {persist_dir}")

chroma_client = chromadb.PersistentClient(
    path=persist_dir,
    settings=Settings(anonymized_telemetry=False)  # Disable Telemetry
)
collection = chroma_client.get_or_create_collection(name="student_texts")

def chunk_text(full_text, chunk_size=400):
    """
    Chunking text for subsequent embedding generation and retrieval
    """
    logging.debug("Start chunking text.")
    if not full_text:
        logging.error("Text is empty, cannot chunk.")
        return []
    lines = []
    start = 0
    while start < len(full_text):
        end = start + chunk_size
        piece = full_text[start:end].strip()
        if piece:  # Make sure each piece is not empty
            lines.append(piece)
        start = end
    logging.debug(f"Total chunks created: {len(lines)}")
    return lines

def get_embeddings(texts):
    """Call OpenAI batch embedding generation interface"""
    try:
        resp = openai.Embedding.create(
            model="text-embedding-ada-002",
            input=texts
        )
        logging.debug(f"Generated embeddings for {len(texts)} texts.")
        return [item["embedding"] for item in resp["data"]]
    except openai.error.OpenAIError as e:
        logging.exception("Error generating embeddings:")
        return [None] * len(texts)

def get_embedding(text):
    """Calling OpenAI embedding generation interface"""
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

def process_leed_item(item_name, collection):
    """
    Work on a single LEED project to generate feedback
    """
    logging.debug(f"Processing item: {item_name}")
    item_query = f"LEED item: {item_name}. Check compliance or missing info."
    try:
        item_emb = get_embedding(item_query)
        if not item_emb:
            return f"Failed to generate embedding for item: {item_name}"

        results = collection.query(
            query_embeddings=[item_emb],
            n_results=3,
        )
        relevant_docs = results.get("documents", [[]])[0]  # Check if the return value is empty

        if not relevant_docs:
            return f"No relevant documents found for item: {item_name}"

        context_text = "\n\n".join([f"Excerpt:\n{doc}" for doc in relevant_docs])
        prompt = f"""
        You are an experienced LEED BD+C reviewer.
        We focus on the item: {item_name}.

        Below are the most relevant excerpts from the student's text:
        {context_text}

        Task:
        1) Assess whether the student's text sufficiently addresses {item_name}.
        2) If the requirements are not fully met, list any missing or unclear aspects and provide a concise recommendation (under 100 words total).

        Respond strictly according to the instructions above, with no additional commentary or information.
        """
        gpt_resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You provide item-by-item LEED compliance feedback."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=150  # Adjust as needed
        )
        return gpt_resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logging.exception(f"Error processing item {item_name}:")
        return f"Error processing item {item_name}: {e}"

def process_leed_items(items, collection):
    """
    Work on multiple LEED projects, generating detailed feedback
    """
    logging.debug("Processing multiple LEED items.")
    detailed_feedback = []

    for item in items:
        item_name = item['name']
        feedback = process_leed_item(item_name, collection)
        if feedback != "This item is well addressed.":
            detailed_feedback.append(f"**{item_name}**:\n{feedback}")

    # Merge detailed feedback
    if detailed_feedback:
        detailed_feedback_str = "\n\n".join(detailed_feedback)
        final_feedback = f"=== Detailed LEED Item Feedback ===\n{detailed_feedback_str}"
    else:
        final_feedback = "All items are well addressed."

    logging.info("Feedback generation completed.")
    return final_feedback


def get_feedback(user_input=None, file_path=None, rubrics=None, leed_scores=None):
    """
    Core functionality: Get text from user input or file -> Classify -> Analyze LEED project -> Return feedback
    """

    # ========== 1. Reading input text ==========
    logging.debug("Start reading input text.")
    text = ""
    if file_path:
        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext == ".docx":
                logging.debug(f"Reading DOCX file: {file_path}")
                doc = Document(file_path)
                text = "\n".join(para.text for para in doc.paragraphs)
            elif ext == ".pdf":
                logging.debug(f"Reading PDF file: {file_path}")
                with open(file_path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        t = page.extract_text()
                        if t:
                            text += t
            else:
                logging.error(f"Unsupported file type: {ext}")
                return "Unsupported file type.", {}, ""
        except Exception as e:
            logging.exception("Error reading file:")
            return f"Error reading file: {e}", {}, ""
    elif user_input:
        logging.debug("Using user-provided input text.")
        text = user_input.strip()
    else:
        logging.error("No input provided.")
        return "No input provided.", {}, ""

    if len(text) < 50:
        logging.warning("Input text is too short.")
        return "Your writing is too short to get meaningful feedback.", {}, ""

    # ========== 2. Check if it is LEED Narrative ==========
    logging.debug("Classifying input as LEED Narrative or not.")
    classification_prompt = f"""
    Determine if the following text is specifically discussing a LEED Narrative for building certification. 
    If yes, respond with "LEED Narrative". 
    If not, respond "Not LEED Narrative".

    Text:
    {text}
    """
    try:
        cls_resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You classify if text is a LEED Narrative."},
                {"role": "user", "content": classification_prompt}
            ],
            temperature=0.0,
            timeout=10
        )
        cls_result = cls_resp["choices"][0]["message"]["content"].strip().lower()
        logging.debug(f"Classification result: {cls_result}")
    except openai.error.OpenAIError as e:
        logging.exception("Error calling OpenAI API:")
        return f"Error checking narrative type: {e}", {}, ""

    if "leed narrative" not in cls_result:
        logging.info("Input text is not related to LEED Narrative.")
        return "This passage is not related to LEED Narrative.", {}, ""

    logging.info("Input classified as LEED Narrative.")
    narrative_msg = "This passage is identified as part of a LEED Narrative."

    # ========== 3. Preparing for LEED Points ==========
    logging.debug("Preparing LEED scores.")
    item_dict = {}
    total_score = 0.0
    if leed_scores:
        try:
            total_score = float(leed_scores.get("total_score", 0))
            for k, v in leed_scores.items():
                if k == "total_score":
                    continue
                val = float(v)
                if val > 0:
                    item_dict[k] = val
        except (ValueError, TypeError) as e:
            logging.error(f"Invalid LEED scores provided: {e}")
            return f"Invalid LEED scores provided: {e}", {}, ""
    else:
        logging.info("No LEED scores provided.")
    
    logging.debug(f"LEED items to evaluate: {item_dict}")
    pass_msg = f"Total score is {total_score}. {'Pass (>=40)!' if total_score >= 40 else 'Less than 40, does not meet the LEED requirement.'}"

    # ========== 4. Block, embed and process LEED projects ==========
    logging.debug("Chunking text for analysis.")
    chunks = chunk_text(text, chunk_size=400)
    logging.debug(f"Total chunks created: {len(chunks)}")

    logging.debug("Embedding and storing text chunks in Chroma DB.")
    embeddings = get_embeddings(chunks)
    for i, (c, emb) in enumerate(zip(chunks, embeddings)):
        if not emb:
            logging.warning(f"Embedding failed for chunk {i}. Skipping...")
            continue
        doc_id = str(uuid.uuid4())
        try:
            collection.add(
                documents=[c],
                embeddings=[emb],
                ids=[doc_id],
                metadatas=[{"chunk_index": i}]
            )
            logging.debug(f"Successfully added chunk {i} to ChromaDB.")
        except Exception as e:
            logging.exception(f"Error embedding/storing chunk {i}: {c[:100]}")
            continue

    logging.debug("Finished embedding and storing all chunks in ChromaDB.")

    # Working on LEED projects
    logging.debug("Processing LEED items in parallel.")
    item_feedbacks = []
    if item_dict:
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(process_leed_item, item_name, collection): item_name
                for item_name in item_dict
            }

            for f in as_completed(futures):
                iname = futures[f]
                try:
                    result_text = f.result()
                    logging.debug(f"Feedback for {iname}: {result_text}")
                    if result_text != "This item is well addressed.":
                        item_feedbacks.append((iname, result_text))
                except Exception as e:
                    logging.exception(f"Error processing item {iname}:")
                    item_feedbacks.append((iname, f"Error processing item {iname}: {e}"))
    else:
        logging.info("No LEED items to process.")

    # Incorporate LEED Project Feedback
    if item_feedbacks:
        detailed_feedback_str = "\n\n".join([f"**{k}**:\n{v}" for k, v in item_feedbacks])
        final_feedback = f"=== Detailed LEED Item Feedback ===\n{detailed_feedback_str}"
    else:
        final_feedback = "All items are well addressed."

    logging.info("Feedback generation completed.")
    return final_feedback, leed_scores, ""
