import os
import re
from chromadb import Client, Settings
from config import Config
import fitz  # PyMuPDF
import tempfile
import shutil
import datetime
import logging
import base64
from openai import OpenAI

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global client variables
client = None
openai_client = OpenAI(api_key=Config.OPENAI_API_KEY)

# Print environment info for debugging
from config import get_config
config = get_config()
logger.info(f"Running in {config.__name__} environment")

def extract_text_from_image(image_path):
    """Extract text from an image using OpenAI's GPT-4o model with OCR capabilities."""
    try:
        # Initialize OpenAI client
        client = OpenAI(api_key=Config.OPENAI_API_KEY)
        
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode("utf-8")
        
        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract all text from this image exactly as it appears, including mathematical symbols and equations. Preserve the original formatting, line breaks, and layout as much as possible. Don't correct any errors in the text."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            temperature=0.0,
            max_tokens=4000
        )
        
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Failed to extract text from image {image_path}: {e}")
        return ""

def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF using OpenAI's GPT-4o model with OCR capabilities."""
    try:
        text_parts = []
        pdf_document = fitz.open(pdf_path)
        client = OpenAI(api_key=Config.OPENAI_API_KEY)
        
        for page_num in range(pdf_document.page_count):
            page = pdf_document[page_num]
            
            # Try to get text directly first (works for text-based PDFs)
            text = page.get_text()
            if text.strip():
                text_parts.append(text.strip())
            else:
                # Use OCR for scanned pages
                pix = page.get_pixmap()
                with tempfile.TemporaryDirectory() as temp_dir:
                    img_path = os.path.join(temp_dir, f"page_{page_num}.png")
                    pix.save(img_path)
                    
                    with open(img_path, "rb") as image_file:
                        base64_image = base64.b64encode(image_file.read()).decode("utf-8")
                    
                    response = client.chat.completions.create(
                        model="gpt-4.1",
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "Extract all text from this image exactly as it appears, including mathematical symbols and equations. Preserve the original formatting, line breaks, and layout as much as possible. Don't correct any errors in the text."
                                    },
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/jpeg;base64,{base64_image}"
                                        }
                                    }
                                ]
                            }
                        ],
                        temperature=0.0,
                        max_tokens=4000
                    )
                    
                    text_parts.append(response.choices[0].message.content.strip())
        
        pdf_document.close()
        return "\n".join(text_parts)
    except Exception as e:
        logger.error(f"Failed to extract text from PDF {pdf_path}: {e}")
        return ""

def chunk_text(text, chunk_size=3500, overlap=200):
    """
    Splits text into overlapping chunks.
    :param text: The input string.
    :param chunk_size: Max size of each chunk (safe for 8k token LLMs and under OpenAI embedding limit).
    :param overlap: Overlap between chunks.
    :return: List of text chunks.
    """
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start += chunk_size - overlap
    return chunks

def init_chromadb(documents_directory):
    global client
    try:
        # Initialize ChromaDB client with persistent settings
        # Use the project's chroma_db directory
        chroma_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
        
        # Ensure the directory exists and is writable
        os.makedirs(chroma_db_path, exist_ok=True)
        
        # Test write permissions in the directory
        try:
            test_file = os.path.join(chroma_db_path, "test_write")
            with open(test_file, "w") as f:
                f.write("test")
            if os.path.exists(test_file):
                os.remove(test_file)
        except Exception as e:
            logger.error(f"Failed to verify write permissions in {chroma_db_path}: {e}")
            raise
        
        client = Client(
            settings=Settings(
                is_persistent=True,
                persist_directory=chroma_db_path,
                allow_reset=False,
                anonymized_telemetry=False
            )
        )

        # Get or create a collection
        collection = client.get_or_create_collection(name="documents")

        # Walk through the documents directory
        for root, _, files in os.walk(documents_directory):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    content = ""
                    if file.lower().endswith(('.txt', '.md')):
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                    elif file.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp')):
                        content = extract_text_from_image(file_path)
                    elif file.lower().endswith('.pdf'):
                        content = extract_text_from_pdf(file_path)
                    
                    if content.strip():
                        year_match = re.search(r'(20\d{2})', file_path)
                        chunks = chunk_text(content, chunk_size=3500, overlap=200)
                        for i, chunk in enumerate(chunks):
                            chunk_id = f"{file_path}#chunk{i}"
                            metadata = {
                                "path": file_path,  # keep parent path as key
                                "year": year_match.group(1) if year_match else "unknown",
                                "chunk_index": i,
                                "n_chunks": len(chunks)
                            }
                            try:
                                embedding = encode_text(chunk)
                                collection.add(
                                    documents=[chunk],
                                    embeddings=[embedding],
                                    metadatas=[metadata],
                                    ids=[chunk_id]
                                )
                                logger.info(f"Document chunk added: {chunk_id}")
                            except Exception as chunk_e:
                                logger.error(f"Failed to embed chunk {chunk_id}: {chunk_e}")
                except Exception as e:
                    logger.error(f"Failed to load {file_path}: {e}")
    except Exception as e:
        logger.error(f"Failed to initialize ChromaDB: {e}")
        raise

def encode_text(text):
    """Encode text using OpenAI's text-embedding-3-large model"""
    try:
        # Convert text to list if it's a single string
        if isinstance(text, str):
            text = [text]
        
        # Get embeddings from OpenAI
        response = openai_client.embeddings.create(
            input=text,
            model="text-embedding-3-large",
            dimensions=1536  # Explicitly set to match ChromaDB's expectation
        )
        
        # Return first embedding if single text, or all embeddings if multiple
        embeddings = [embedding.embedding for embedding in response.data]
        return embeddings[0] if len(embeddings) == 1 else embeddings
    except Exception as e:
        logger.error(f"OpenAI embedding failed: {e}")
        raise

def enhance_query_with_year_and_subject(query: str) -> str:
    """Enhance the query with year and subject information for better document retrieval."""
    # Define keywords to look for with variations, slang and common typos
    math_keywords = [
        "mathe", "mathematik", "matheprüfung", "mathematikprüfung", 
        "math", "mathprüfung", "mathepruefung", "mathematikpruefung",
        "gleichungen", "funktionen", "analysis", "algebra", "geometrie",
        "stochastik", "rechnen", "zahlen", "brüche", "bruchrechnung",
        "mathearbeit", "matheklausur", "mathetest", "prüfungsaufgaben",
        "prüfung", "prüf", "prüfungsvorbereitung", "aufgaben", "lösungen"
    ]
    
    german_keywords = [
        "deutsch", "german", "sprachprüfung", "sprachpruefung", "deutschprüfung",
        "deutschpruefung", "aufsatz", "textverständnis", "textverstaendnis",
        "sprache", "deutschklausur", "deutschtest", "deutscharbeit",
        "sprachtest", "sprachprüf", "sprachpruef", "textanalyse",
        "interpretation", "erörterung", "grammatik", "rechtschreibung",
        "diktat", "literatur", "leseverstehen", "schreiben", "schriftlich",
        "mündlich", "muendlich", "prüf", "prüfung", "pruefung"
    ]
    
    query = query.lower().strip()

    # Year variations including '20XX' format and common typos
    year_keywords = []
    for year in range(2015, 2025):
        year_str = str(year)
        year_keywords.extend([
            year_str,
            f"'{year_str[2:]}",  # '15, '16 etc.
            f"{year_str}er",      # 2015er, 2016er
            year_str.replace("20", ""),  # 15, 16 etc.
            year_str.replace("201", "2001"),  # Common typo (20015)
            year_str.replace("20", "2")       # Common typo (215)
        ])
    
    # Check if query contains any year reference
    found_year = None
    for year in year_keywords:
        if year in query:
            found_year = year
            break
    
    # Check subject
    found_subject = None
    math_matches = [k for k in math_keywords if k in query]
    german_matches = [k for k in german_keywords if k in query]
    if math_matches or german_matches:
        # Pick the subject with the most matches (or the longer keyword if tie)
        if len(german_matches) > len(math_matches):
            found_subject = "Deutsch"
        elif len(math_matches) > len(german_matches):
            found_subject = "Mathematik"
        elif len(german_matches) == len(math_matches) and len(german_matches) > 0:
            # If tied, pick the subject with the longest match
            if max(map(len, german_matches)) >= max(map(len, math_matches)):
                found_subject = "Deutsch"
            else:
                found_subject = "Mathematik"

    # Logging detection
    logger.info(f"[RAG][QUERY_ENHANCE] Query='{query}', Found year='{found_year}', Found subject='{found_subject}', Math matches={math_matches}, German matches={german_matches}")
    
    # If we found both year and subject, enhance the query with repeated year+subject terms
    if found_year and found_subject:
        enhanced_terms = []
        subject_terms = math_keywords if found_subject == "Mathematik" else german_keywords
        
        # Repeat year + each keyword multiple times (3-5x) for emphasis
        for term in subject_terms:
            enhanced_terms.extend([
                f"{found_year} {term}", f"{term} {found_year}",
                f"{found_year} {term}", f"{term} {found_year}",
                f"{found_year} {term}", f"{term} {found_year}",
                f"{found_year} {found_subject}", f"{found_subject} {found_year}",
                f"{found_year} prüfung", f"prüfung {found_year}"
            ])
        
        # Add some variations with common prefixes/suffixes
        enhanced_terms.extend([
            f"{found_subject}prüfung {found_year}",
            f"{found_year} {found_subject}prüfung",
            f"{found_subject} prüfung {found_year}",
            f"{found_year} {found_subject} prüfung",
            f"prüfungsaufgaben {found_subject} {found_year}",
            f"lösungen {found_subject} {found_year}"
        ])
        
        # Combine with original query and remove duplicates while preserving order
        all_terms = enhanced_terms + [query]
        unique_terms = []
        seen = set()
        for term in all_terms:
            if term not in seen:
                seen.add(term)
                unique_terms.append(term)
        
        return " ".join(unique_terms)
    return query

def query_context(prompt: str, n_results: int = 1, similarity_threshold: float = 0.95) -> str:
    """
    Instead of using ChromaDB and vector search, perform a direct keyword document lookup
    based on year/subject. Return all .txt and .md contents from the relevant directory.
    """
    try:
        enhanced_prompt = enhance_query_with_year_and_subject(prompt)
        logger.info(f"[SEARCH] Original query: {prompt}")
        logger.info(f"[SEARCH] Enhanced query: {enhanced_prompt}")

        # Extract year and subject
        found_year = None
        for year in [str(y) for y in range(2015, 2025)]:
            if year in enhanced_prompt:
                found_year = year
                break

        found_subject = None
        if "mathe" in enhanced_prompt or "math" in enhanced_prompt or "mathematik" in enhanced_prompt:
            found_subject = "Mathematik"
        elif "deutsch" in enhanced_prompt or "german" in enhanced_prompt or "sprach" in enhanced_prompt:
            found_subject = "Deutsch"

        logger.info(f"[SEARCH] Found year: {found_year} | Found subject: {found_subject}")

        # If no subject or year could be determined, fallback to nothing
        if not found_year or not found_subject:
            logger.warning("[SEARCH] No year or subject found in query for direct search.")
            return ""

        # Find matching text/markdown files in RAG_scannable_documents/<subject>/<year>/
        base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "RAG_scannable_documents", found_subject, found_year)
        if not os.path.isdir(base_dir):
            logger.warning(f"[SEARCH] No directory found for subject/year: {base_dir}")
            return ""

        result_texts = []
        for fname in os.listdir(base_dir):
            path = os.path.join(base_dir, fname)
            if fname.lower().endswith(".txt") or fname.lower().endswith(".md"):
                try:
                    with open(path, encoding="utf-8") as f:
                        doc = f.read()
                        result_texts.append(doc)
                        logger.info(f"[SEARCH] Loaded: {fname}")
                except Exception as e:
                    logger.error(f"[SEARCH] Failed to read {fname}: {e}")

        if not result_texts:
            logger.warning(f"[SEARCH] No text files found in {base_dir}")
            return ""
        return "\n\n---\n\n".join(result_texts)
    except Exception as e:
        logger.error(f"[SEARCH] Exception: {e}")
        return ""

def process_uploaded_file(file_path: str, destination_dir: str = "RAG_SCANNABLE_DOCUMENTS", return_text_only: bool = False) -> tuple[str, str] | str:
    """
    Process an uploaded file with robust error handling.
    
    Args:
        file_path: Path to the file to process
        destination_dir: Directory to store processed files (default: "RAG_SCANNABLE_DOCUMENTS")
        return_text_only: If True, only returns extracted text without RAG processing
        
    Returns:
        tuple(content, destination_path) if return_text_only=False
        str (content) if return_text_only=True
    """
    try:
        # First extract the content regardless of return_text_only
        content = ""
        if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp')):
            content = extract_text_from_image(file_path)
        elif file_path.lower().endswith('.pdf'):
            content = extract_text_from_pdf(file_path)
        else:
            raise ValueError("Unsupported file type")
            
        if not content.strip():
            raise ValueError("No text could be extracted from the file")
        
        return content
        
    except Exception as e:
        logger.error(f"Failed to process uploaded file {file_path}: {e}")
        raise