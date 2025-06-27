# 📄 PDF-to-JSON Legal Document Parser

This tool extracts structured content from legal documents in **PDF format** and outputs a normalized **JSON file** using PyMuPDF (fitz) for robust text extraction and **layout-based article/section splitting**. Optionally, it uses an LLM (Mistral-7B via OpenRouter) to generate summaries, intentions, and keywords for each article and the document as a whole.

---

## 🎯 Objective

Convert municipal legal regulations (e.g. *Personalverordnung*) from PDF into structured, machine-readable JSON format with:

- Document-level metadata (title, date, etc.)
- **Section-aware, layout-based article extraction**
- **LLM-powered summaries, intentions, and keywords**
- **Automatic column and section detection**

---

## 🛠️ Installation

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

Required packages:
- `PyMuPDF` - For PDF text extraction with layout information
- `jsonschema` - For JSON validation
- `requests` - For LLM API calls
- `python-dotenv` - For loading API keys from `.env`

2. (Optional, for LLM enhancement) Set up your OpenRouter API key:
   - Create a `.env` file in the project root with:
     ```
     OPENROUTER_API_KEY=your_openrouter_api_key_here
     ```

---

## 📥 Input

- Format: `.pdf`
- Language: German (but parser is language-agnostic if structure is consistent)
- Structure: Legal documents with numbered articles in **two-column layout**
  - **Left column**: Article titles and headings
  - **Right column**: Article content
  - **Sections**: Detected by Roman numerals and titles

Example input file: `documents/test.pdf`

---

## 📤 Output

A single `.json` file with the following structure:

```json
{
  "document_title": "Personalverordnung der Politischen Gemeinde Wila",
  "document_date": "05.12.2018",
  "document_summary": "...",           // Only if LLM enhancement is enabled
  "document_intention": "...",         // Only if LLM enhancement is enabled
  "document_keywords": "...",          // Only if LLM enhancement is enabled
  "sections": [
    {
      "section_title": "I. Allgemeine Bestimmungen",
      "articles": [
        {
          "article_number": "1",
          "article_title": "Allgemeines",
          "article_content": "Dieser Verordnung untersteht das Personal der Politischen Gemeinde Wila.",
          "article_summary": "Regelt die Zuständigkeit des Personals der Politischen Gemeinde Wila", // LLM
          "article_intention": "Regelung der Zuständigkeit und Kompetenz für die Anstellung und Entlassung des Personals der Gemeinde Wila", // LLM
          "article_keywords": "Personal, Gemeinde Wila, Zuständigkeit, Anstellung, Entlassung, Gemeinderat, Gemeindeschreiber" // LLM
        }
        // ... more articles ...
      ]
    }
    // ... more sections ...
  ]
}
```

---

## 🚀 Usage

### Basic Usage

Parse a PDF and save to JSON:
```bash
python main.py input.pdf output.json
```

- By default, LLM enhancement (summaries, intentions, keywords) is enabled if the API key is set.
- If the API key is missing, only structural parsing is performed (no summaries/keywords).

---

## 🔧 Features

### Layout-Based Parsing

- **Extracts text blocks with coordinates** (`get_text("dict")`)
- **Detects column separation** by analyzing x-coordinate gaps
- **Groups articles under sections** using Roman numerals and titles
- **Categorizes text by position** (left column = title, right column = content)
- **Handles multi-line titles and content**

### Article & Section Detection

- **Section detection:** Roman numerals (e.g., `I.`, `II.`, etc.) and titles
- **Article detection:**
  - `Article 1: Title`
  - `Art. 1: Title`
  - `§ 1: Title`
  - `Section 1: Title`
  - `1. Title`
- **Fallback methods:**
  - Y-coordinate grouping
  - Column-based splitting
  - Sequential numbering

### LLM Enhancement (Optional)

- **Summaries, intentions, and keywords** for each article and the document as a whole
- Uses [OpenRouter](https://openrouter.ai/) with Mistral-7B
- Requires `OPENROUTER_API_KEY` in `.env`

### Metadata Extraction

- Document title from first meaningful text block
- Date patterns (various formats supported)

---

## 📁 Project Structure

```
rag/
├── main.py                 # Main CLI interface
├── requirements.txt        # Python dependencies
├── parser/
│   ├── __init__.py
│   ├── parse_pdf.py        # Core PDF parsing logic with layout analysis
│   └── llm_openrouter.py   # LLM enhancement logic (OpenRouter API)
├── documents/
│   ├── test.pdf            # Example PDF file
│   └── test.json           # Example output JSON
├── llm_responses/          # (Optional) Raw LLM responses (if DEV_MODE enabled)
└── readme.md               # This file
```

---

## 🧪 Testing

- Use your own PDF files in the `documents/` directory.
- Run the parser as shown above and inspect the output JSON.
- Example output is provided in `documents/test.json`.

---

## 🤝 Contributing

To extend the parser:

1. **Adjust column/section detection** in `find_column_separator()` and `split_into_sections_and_articles_with_layout()`
2. **Add new article patterns** in `split_into_sections_and_articles_with_layout()`
3. **Enhance layout analysis** in `extract_text_with_layout()`
4. **Improve LLM prompts or postprocessing** in `llm_openrouter.py`

---

## 📄 License

This project is designed for legal document processing and automation.
