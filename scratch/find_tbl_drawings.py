import zipfile
import re

with zipfile.ZipFile('d:/Coding/Major Project/FieldNotes/FieldNotes_MongoDB_Project_Report.docx') as z:
    doc_xml = z.read('word/document.xml').decode('utf-8')

for i, match in enumerate(re.finditer(r'<w:tbl.*?</w:tbl>', doc_xml)):
    tbl_str = match.group(0)
    if '<w:drawing' in tbl_str:
        # Extract all text inside this table
        texts = re.findall(r'<w:t[^>]*>(.*?)</w:t>', tbl_str)
        print(f"Table containing drawing: texts={texts}")
        # Look at the text immediately preceding this table
        preceding = doc_xml[max(0, match.start() - 400):match.start()]
        pre_text = re.findall(r'<w:t[^>]*>(.*?)</w:t>', preceding)
        print(f"  Preceding heading/text: {' '.join(pre_text[-5:])}")
