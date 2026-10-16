import zipfile
import re

with zipfile.ZipFile('d:/Coding/Major Project/FieldNotes/FieldNotes_MongoDB_Project_Report.docx') as z:
    doc_xml = z.read('word/document.xml').decode('utf-8')
    matches = re.findall(r'<w:drawing.*?</w:drawing>', doc_xml)
    print(f'Total drawings in document.xml: {len(matches)}')
    for i, m in enumerate(matches):
        rId = re.findall(r'r:embed="([^"]+)"', m)
        docPr = re.findall(r'<wp:docPr[^>]*name="([^"]*)"', m)
        print(f'Drawing {i+1}: embed={rId}, name={docPr}')
