import os
import requests
import json
from dotenv import load_dotenv
import re
import logging
import datetime
import os as _os

load_dotenv()

OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
OPENROUTER_API_URL = 'https://openrouter.ai/api/v1/chat/completions'
MODEL = 'mistralai/mistral-7b-instruct'

# Set DEV_MODE to True to save LLM responses to disk (llm_responses directory)
DEV_MODE = False

HEADERS = {
    'Authorization': f'Bearer {OPENROUTER_API_KEY}',
    'Content-Type': 'application/json',
}

logger = logging.getLogger(__name__)

def _save_llm_response(raw_content: str, identifier: str):
    if not DEV_MODE:
        return
    dir_path = _os.path.join(_os.getcwd(), 'llm_responses')
    _os.makedirs(dir_path, exist_ok=True)
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    filename = f'{identifier}_{timestamp}.txt'
    file_path = _os.path.join(dir_path, filename)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(raw_content)
    logger.info(f"Saved LLM response to {file_path}")


def analyze_articles_batch_with_mistral(article_texts: list) -> list:
    """
    Calls Mistral 7B via OpenRouter to summarize, generate intention, and keywords for a batch of articles.
    Returns a list of dicts with 'summary', 'intention', and 'keywords' for each article.
    """
    numbered_articles = "\n".join([f"Artikel {i+1}:\n{txt}" for i, txt in enumerate(article_texts)])
    prompt = f"""
    Analysiere die folgenden rechtlichen Artikel. Gib ein JSON-Array zurück, wobei jedes Element folgende Felder enthält:
    - summary: eine prägnante Zusammenfassung auf Deutsch (genau ein Satz, nicht mit 'Dieser Artikel regelt', 'Dieser Artikel beschreibt', 'Dieser Artikel handelt von' oder ähnlichen generischen Phrasen beginnen, sondern direkt mit dem Inhalt starten)
    - intention: der Zweck oder das Ziel des Artikels auf Deutsch (genau ein Satz, nicht mit 'Dieser Artikel regelt', 'Dieser Artikel beschreibt', 'Dieser Artikel handelt von' oder ähnlichen generischen Phrasen beginnen, sondern klar und spezifisch den Zweck oder das Ziel benennen, nicht nur den Inhalt wiederholen oder allgemein beschreiben. Z.B. 'Schutz der Angestellten vor ungerechtfertigter Kündigung.')
    - keywords: 3-6 relevante Stichwörter auf Deutsch, kommasepariert
    Die Reihenfolge im Array muss der Reihenfolge der Artikel entsprechen.
    {numbered_articles}
    """
    data = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 1024,
        "temperature": 0.2
    }
    try:
        response = requests.post(OPENROUTER_API_URL, headers=HEADERS, json=data)
        response.raise_for_status()
        result = response.json()
        content = result['choices'][0]['message']['content']
        _save_llm_response(content, 'batch')
        # Remove code block markers if present
        content = re.sub(r'^```json|^```python|^```', '', content.strip(), flags=re.IGNORECASE)
        content = re.sub(r'```$', '', content.strip(), flags=re.IGNORECASE)
        content = content.strip()
        try:
            parsed = json.loads(content)
            if isinstance(parsed, list) and all(isinstance(x, dict) for x in parsed):
                return parsed
            if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                out = []
                for x in parsed:
                    try:
                        out.append(json.loads(x))
                    except Exception:
                        logger.warning(f"Failed to parse JSON from LLM batch element: {x}")
                        out.append({"summary": "", "intention": "", "keywords": "", "raw": x})
                return out
            if isinstance(parsed, dict):
                return [parsed]
        except Exception:
            logger.warning(f"Failed to parse JSON from LLM batch response: {content}")
        return [{"summary": "", "intention": "", "keywords": "", "raw": content}] * len(article_texts)
    except Exception as e:
        logger.error(f"API error in analyze_articles_batch_with_mistral: {e}\nRequest data: {data}")
        return [{"summary": "", "intention": "", "keywords": "", "error": str(e)}] * len(article_texts)

def analyze_document_with_mistral(document_text: str) -> dict:
    """
    Calls Mistral 7B via OpenRouter to summarize, generate intention, keywords, and title for the entire document.
    Returns a dict with 'summary', 'intention', 'keywords', and 'title'.
    """
    prompt = f"""
    Analyze the following legal document as a whole. Return a JSON object with:
    - title: a suitable, concise document title in German
    - summary: a concise summary in German (exactly one sentence, do not start with 'Dieses Dokument regelt', 'Dieses Dokument beschreibt', 'Dieses Dokument handelt von' or similar generic phrases, but start directly with the content)
    - intention: the purpose or goal of the document in German (exactly one sentence, do not start with 'Dieses Dokument regelt', 'Dieses Dokument beschreibt', 'Dieses Dokument handelt von' or similar generic phrases, but clearly and specifically state the purpose or goal, not just repeat or generally describe the content. E.g., 'Schaffung klarer Rahmenbedingungen für das Gemeindepersonal.')
    - keywords: 3-6 relevant keywords in German, comma-separated
    Document:
    {document_text}
    """
    data = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 512,
        "temperature": 0.2
    }
    try:
        response = requests.post(OPENROUTER_API_URL, headers=HEADERS, json=data)
        response.raise_for_status()
        result = response.json()
        content = result['choices'][0]['message']['content']
        _save_llm_response(content, 'document')
        try:
            return json.loads(content)
        except Exception:
            logger.warning(f"Failed to parse JSON from LLM document response: {content}")
            return {"summary": "", "intention": "", "keywords": "", "title": "", "raw": content}
    except Exception as e:
        logger.error(f"API error in analyze_document_with_mistral: {e}\nRequest data: {data}")
        return {"summary": "", "intention": "", "keywords": "", "title": "", "error": str(e)} 