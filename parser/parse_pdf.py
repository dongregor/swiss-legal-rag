from turtle import title
import fitz  # PyMuPDF
import re
from typing import List, Dict, Any
import logging
import parser.llm_openrouter as llm_openrouter
from parser.llm_openrouter import analyze_articles_batch_with_mistral, analyze_document_with_mistral

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_text_with_layout(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Extract text from PDF with layout information using PyMuPDF.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        List of text blocks with positioning information
    """
    try:
        doc = fitz.open(pdf_path)
        all_blocks = []
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            # Get text blocks with positioning information
            blocks = page.get_text("dict")
            
            for block in blocks.get("blocks", []):
                if "lines" in block:  # Text block
                    for line in block["lines"]:
                        for span in line["spans"]:
                            all_blocks.append({
                                'text': span['text'],
                                'bbox': span['bbox'],  # [x0, y0, x1, y1]
                                'page': page_num,
                                'font': span.get('font', ''),
                                'size': span.get('size', 0),
                                'flags': span.get('flags', 0)  # bold, italic, etc.
                            })
            
        doc.close()
        return all_blocks
        
    except Exception as e:
        logger.error(f"Error extracting text with layout from PDF {pdf_path}: {e}")
        raise


def find_column_separator(blocks: List[Dict[str, Any]]) -> float:
    """
    Find the x-coordinate that separates left and right columns.
    
    Args:
        blocks: List of text blocks with positioning information
        
    Returns:
        X-coordinate that separates columns
    """
    if not blocks:
        return 0
    
    # Get all x-coordinates where text starts
    x_positions = []
    for block in blocks:
        if block['text'].strip():
            x_positions.append(block['bbox'][0])  # x0 coordinate
    
    if not x_positions:
        return 0
    
    # Find the most common gap between text positions
    x_positions.sort()
    gaps = []
    for i in range(1, len(x_positions)):
        gap = x_positions[i] - x_positions[i-1]
        if gap > 20:  # Minimum gap threshold
            gaps.append((x_positions[i-1], x_positions[i], gap))
    
    if gaps:
        # Find the largest gap
        largest_gap = max(gaps, key=lambda x: x[2])
        # Return the midpoint of the largest gap
        return (largest_gap[0] + largest_gap[1]) / 2
    
    # Fallback: use median position
    return sorted(x_positions)[len(x_positions)//2]


def split_into_sections_and_articles_with_layout(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Split text blocks into sections and group articles under each section based on layout and patterns.
    Handles cases where the section numeral and title are in separate blocks.
    Returns a list of sections, each with a section_title and articles list.
    """
    # Regex for section numeral (e.g., 'I.', 'II.', 'III.', 'I', 'II', etc.)
    section_numeral_pattern = re.compile(r'^[IVX]+\.?\s*$')
    # Article patterns as before
    article_patterns = [
        r'Article\s+(\d+)[:\s]*([^\n]*)',  # Article 1: Title
        r'Art\.\s*(\d+)[:\s]*([^\n]*)',    # Art. 1: Title
        r'§\s*(\d+)[:\s]*([^\n]*)',        # § 1: Title
        r'Section\s+(\d+)[:\s]*([^\n]*)',  # Section 1: Title
        r'(\d+)\.\s*([^\n]*)',             # 1. Title
    ]
    
    sections = []
    current_section = None
    current_article = None
    current_title_blocks = []
    current_content_blocks = []
    column_separator = find_column_separator(blocks)
    i = 0
    while i < len(blocks):
        text = blocks[i]['text'].strip()
        if not text:
            i += 1
            continue
        # Section numeral detection (standalone Roman numeral)
        if section_numeral_pattern.match(text):
            # Look ahead for the next non-empty block(s) to form the section title
            numeral = text.rstrip('.')
            j = i + 1
            title_parts = []
            while j < len(blocks):
                next_text = blocks[j]['text'].strip()
                if next_text:
                    # If the next block is also a single capital letter (e.g., 'A.'), treat as sub-section, not main section
                    if re.match(r'^[A-Z]\.?$', next_text):
                        title_parts.append(next_text.rstrip('.'))
                        j += 1
                        continue
                    title_parts.append(next_text)
                    break
                j += 1
            section_title = numeral
            if title_parts:
                section_title += '. ' + ' '.join(title_parts)
            # Save previous article if exists
            if current_article:
                current_article['article_title'] = ' '.join([b['text'] for b in current_title_blocks]).strip()
                current_article['article_content'] = ' '.join([b['text'] for b in current_content_blocks]).strip()
                if current_section:
                    current_section['articles'].append(current_article)
                current_article = None
                current_title_blocks = []
                current_content_blocks = []
            # Save previous section if exists
            if current_section:
                sections.append(current_section)
            # Start new section
            current_section = {
                'section_title': section_title.strip(),
                'articles': []
            }
            i = j + 1
            continue
        # Article detection
        article_found = False
        for pattern in article_patterns:
            match = re.match(pattern, text, re.IGNORECASE)
            if match:
                # Save previous article if exists
                if current_article:
                    current_article['article_title'] = ' '.join([b['text'] for b in current_title_blocks]).strip()
                    current_article['article_content'] = ' '.join([b['text'] for b in current_content_blocks]).strip()
                    if current_section:
                        current_section['articles'].append(current_article)
                # Start new article
                article_num = match.group(1)
                title_text = match.group(2).strip() if len(match.groups()) > 1 else ""
                current_article = {
                    'article_number': article_num,
                    'article_title': '',
                    'article_content': ''
                }
                current_title_blocks = []
                current_content_blocks = []
                if title_text:
                    current_title_blocks.append({'text': title_text})
                article_found = True
                break
        # If not a new article, categorize block by position
        if not article_found and current_article:
            if blocks[i]['bbox'][0] < column_separator:
                current_title_blocks.append(blocks[i])
            else:
                current_content_blocks.append(blocks[i])
        i += 1
    # Save last article and section
    if current_article:
        current_article['article_title'] = ' '.join([b['text'] for b in current_title_blocks]).strip()
        current_article['article_content'] = ' '.join([b['text'] for b in current_content_blocks]).strip()
        if current_section:
            current_section['articles'].append(current_article)
    if current_section:
        sections.append(current_section)
    return sections


def extract_metadata_from_blocks(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extract metadata from text blocks.
    
    Args:
        blocks: List of text blocks with positioning information
        
    Returns:
        Dictionary containing metadata
    """
    import datetime
    months_en = {m: i for i, m in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'], 1)}
    months_de = {m: i for i, m in enumerate(['Januar','Februar','März','April','Mai','Juni','Juli','August','September','Oktober','November','Dezember'], 1)}
    metadata = {
        'title': '',
        'date': '',
    }
    
    # Extract title from first few blocks (likely at top of page)
    sorted_blocks = sorted(blocks, key=lambda x: (x['page'], x['bbox'][1], x['bbox'][0]))
    
    for block in sorted_blocks[:10]:
        text = block['text'].strip()
        if text and not metadata['title']:
            # Skip common headers/footers
            if not re.match(r'^(Page|Seite|©|Copyright)', text, re.IGNORECASE):
                metadata['title'] = text[:200]  # Limit title length
                break
    
    # Extract date patterns (including German months)
    all_text = ' '.join([block['text'] for block in blocks])
    date_patterns = [
        r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b',
        r'\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b',
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b',
        r'\b(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+(\d{1,2}),?\s+(\d{4})\b',
        r'\b(\d{1,2})\.\s*(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s*(\d{4})\b',
    ]
    found_date = ''
    for pattern in date_patterns:
        match = re.search(pattern, all_text, re.IGNORECASE)
        if match:
            try:
                if pattern == date_patterns[0]:  # dd/mm/yyyy or dd-mm-yyyy
                    d, m, y = match.groups()
                    if len(y) == 2:
                        y = '20' + y if int(y) < 50 else '19' + y
                    dt = datetime.date(int(y), int(m), int(d))
                elif pattern == date_patterns[1]:  # yyyy-mm-dd
                    y, m, d = match.groups()
                    dt = datetime.date(int(y), int(m), int(d))
                elif pattern == date_patterns[2]:  # English month
                    month, day, year = match.groups()
                    m = months_en[month.capitalize()]
                    dt = datetime.date(int(year), m, int(day))
                elif pattern == date_patterns[3]:  # German month
                    month, day, year = match.groups()
                    m = months_de[month.capitalize()]
                    dt = datetime.date(int(year), m, int(day))
                elif pattern == date_patterns[4]:  # 12. März 2023
                    day, month, year = match.groups()
                    m = months_de[month.capitalize()]
                    dt = datetime.date(int(year), m, int(day))
                found_date = dt.strftime('%d.%m.%Y')
                break
            except Exception:
                continue
    metadata['date'] = found_date
    
    return metadata


def parse_pdf(pdf_path: str, enhance: bool = True) -> Dict[str, Any]:
    """
    Main function to parse a PDF and extract articles grouped by section using layout information.
    Args:
        pdf_path: Path to the PDF file
        enhance: If False, skip LLM enhancement (summaries, intentions, keywords)
    Returns:
        Dictionary containing parsed document structure with sections and grouped articles
    """
    logger.info(f"Parsing PDF with layout: {pdf_path}")
    blocks = extract_text_with_layout(pdf_path)
    metadata = extract_metadata_from_blocks(blocks)
    sections = split_into_sections_and_articles_with_layout(blocks)
    sections = clean_section_article_text(sections)
    document_summary = document_intention = document_keywords = None
    if enhance:
        # Enhance the whole document first
        all_article_texts = []
        for section in sections:
            for article in section.get('articles', []):
                all_article_texts.append(article.get('article_content', ''))
        full_text = '\n'.join(all_article_texts)
        logger.info("Enhancing the document as a whole...")
        doc_result = analyze_document_with_mistral(full_text)
        document_summary = doc_result.get('summary', '')
        document_intention = doc_result.get('intention', '')
        document_keywords = doc_result.get('keywords', '')
        document_title_enhanced = doc_result.get('title', '')
        # Enhance articles section by section in batches of 5
        for section_idx, section in enumerate(sections):
            articles = section.get('articles', [])
            if not articles:
                continue
            BATCH_SIZE = 5
            for i in range(0, len(articles), BATCH_SIZE):
                batch = articles[i:i+BATCH_SIZE]
                batch_texts = [a.get('article_content', '') for a in batch]
                logger.info(f"Enhancing articles {i+1}-{i+len(batch)} in section {section_idx+1}: {section.get('section_title', '')}")
                llm_results = analyze_articles_batch_with_mistral(batch_texts)
                for article, llm_result in zip(batch, llm_results):
                    article['article_summary'] = llm_result.get('summary', '')
                    article['article_intention'] = llm_result.get('intention', '')
                    article['article_keywords'] = llm_result.get('keywords', '')
        logger.info(f"LLM enhancement complete for all articles and document.")
    else:
        logger.info("Skipping LLM enhancement (summaries, intentions, keywords)")
    # Build result dict with enhanced document fields before sections
    result = {}
    result['document_title'] = document_title_enhanced if enhance and document_title_enhanced else metadata.get('title', '')
    result['document_date'] = metadata.get('date', '')
    if enhance:
        result['document_summary'] = document_summary
        result['document_intention'] = document_intention
        result['document_keywords'] = document_keywords
    result['sections'] = sections
    logger.info(f"Successfully parsed {sum(len(s['articles']) for s in sections)} articles in {len(sections)} sections from {pdf_path}")
    return result


def join_broken_words(text: str) -> str:
    """
    Join words that are split across lines with hyphens (e.g., 'Be-\nbenamt' -> 'Benbenamt').
    Args:
        text: Text to process
    Returns:
        Text with broken words joined
    """
    if not text:
        return text
    # Remove hyphen at end of line followed by optional whitespace and a lowercase letter
    # Also handle cases where a hyphen is followed by a line break and then a capital letter
    text = re.sub(r'-\s*\n?\s*([a-zA-ZäöüÄÖÜß])', r'\1', text)
    # Remove any remaining explicit line breaks
    text = text.replace('\n', ' ')
    return text


def remove_trailing_page_numbers(text: str) -> str:
    """
    Remove page numbers (e.g., '7', 'Seite 7', 'Page 7') from the end of the text.
    Args:
        text: Text to process
    Returns:
        Text with trailing page numbers removed
    """
    if not text:
        return text
    # Remove patterns like 'Seite 7', 'Page 7', or just a number at the end
    text = re.sub(r'(Seite|Page)?\s*\d+\s*$', '', text, flags=re.IGNORECASE)
    # Remove any extra whitespace
    text = re.sub(r'\s+$', '', text)
    return text


def remove_section_titles_from_title(title: str) -> str:
    """
    Remove everything after the first section marker (e.g., 'A.', 'I.', 'II.', etc.) in the title.
    """
    # Pattern for section marker: Roman numerals or single capital letter, followed by dot
    section_marker = re.search(r'(\s{0,2}(?:[IVX]+\.|[A-Z]\.)\s*)', title)
    if section_marker:
        # Keep only the part before the first section marker
        cleaned = title[:section_marker.start()].strip()
    else:
        cleaned = title.strip()
    # Remove extra whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned


def clean_section_article_text(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Clean up section and article text for all sections and their articles.
    """
    for section in sections:
        if 'section_title' in section:
            section['section_title'] = re.sub(r'\s+', ' ', join_broken_words(section['section_title'])).strip()
        for article in section.get('articles', []):
            if 'article_title' in article:
                article['article_title'] = join_broken_words(article['article_title'])
                article['article_title'] = remove_section_titles_from_title(article['article_title'])
                article['article_title'] = re.sub(r'\s+', ' ', article['article_title']).strip()
            if 'article_content' in article:
                content = article['article_content']
                content = join_broken_words(content)
                # Remove standalone page numbers (1-3 digits) with at least 4 spaces before and after, or at start/end
                content = re.sub(r'(?:^|[ ]{4,})(\d{1,3})(?=[ ]{4,}|$)', '', content)
                content = remove_trailing_page_numbers(content)
                content = re.sub(r'\s+', ' ', content).strip()
                article['article_content'] = content
    return sections


if __name__ == "__main__":
    import argparse
    import os
    import json
    parser = argparse.ArgumentParser(description="Parse a PDF and extract articles (optionally with LLM enhancement)")
    parser.add_argument("pdf_path", type=str, help="Path to the PDF file")
    parser.add_argument("--no-enhance", action="store_true", help="Skip LLM enhancement (summaries, intentions, keywords)")
    parser.add_argument("--dev", action="store_true", help="Save raw LLM responses to llm_responses directory (DEV_MODE)")
    args = parser.parse_args()
    # Set DEV_MODE in llm_openrouter if --dev is provided
    if args.dev:
        llm_openrouter.DEV_MODE = True
    result = parse_pdf(args.pdf_path, enhance=not args.no_enhance)
    print(f"Document Title: {result['document_title']}")
    print(f"Document Date: {result['document_date']}")
    print(f"Total Sections: {len(result['sections'])}")
    for i, section in enumerate(result['sections'][:3]):  # Show first 3 sections
        print(f"\nSection {i+1}: {section['section_title']}")
        for j, article in enumerate(section['articles'][:3]):  # Show first 3 articles in each section
            print(f"Article {j+1}: {article['article_title']}")
            print(f"Content preview: {article['article_content'][:100]}...")
    # Save result to JSON file
    json_path = os.path.splitext(args.pdf_path)[0] + ".json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\nFull result saved to {json_path}") 