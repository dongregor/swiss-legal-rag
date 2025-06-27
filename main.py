import argparse
import json
from parser.parse_pdf import parse_pdf


def main():
    parser = argparse.ArgumentParser(description='PDF-to-JSON Legal Document Parser')
    parser.add_argument('pdf_path', type=str, help='Path to the input PDF file')
    parser.add_argument('output_path', type=str, help='Path to the output JSON file')
    args = parser.parse_args()

    try:
        result = parse_pdf(args.pdf_path)
        with open(args.output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f'Parsing {args.pdf_path} and saving to {args.output_path}')
    except Exception as e:
        print(f'Error: {e}')

if __name__ == '__main__':
    main() 