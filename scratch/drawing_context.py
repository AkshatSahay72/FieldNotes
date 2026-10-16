import zipfile
import re

with zipfile.ZipFile('d:/Coding/Major Project/FieldNotes/FieldNotes_MongoDB_Project_Report.docx') as z:
    doc_xml = z.read('word/document.xml').decode('utf-8')

for match in re.finditer(r'<w:drawing.*?</w:drawing>', doc_xml):
    start = max(0, match.start() - 300)
    end = min(len(doc_xml), match.end() + 300)
    surrounding = doc_xml[start:end]
    # Strip XML tags to see text
    text_snippet = re.sub(r'<[^>]+>', ' ', surrounding)
    text_snippet = ' '.join(text_snippet.split())
    print("--- DRAWING CONTEXT ---")
    print(text_snippet)
