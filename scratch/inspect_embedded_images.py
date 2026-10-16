import zipfile
import re

with zipfile.ZipFile('d:/Coding/Major Project/FieldNotes/FieldNotes_MongoDB_Project_Report.docx') as z:
    doc_xml = z.read('word/document.xml').decode('utf-8')

# Find all tables or paragraphs where r:embed="rIdX" appears
for rid in ["rId6", "rId7", "rId8", "rId9", "rId10", "rId11"]:
    pos = doc_xml.find(f'r:embed="{rid}"')
    if pos != -1:
        start = max(0, pos - 500)
        end = min(len(doc_xml), pos + 500)
        window = doc_xml[start:end]
        # Find preceding heading or paragraph text
        pre_matches = re.findall(r'<w:t[^>]*>(.*?)</w:t>', doc_xml[max(0, pos - 1500):pos])
        post_matches = re.findall(r'<w:t[^>]*>(.*?)</w:t>', doc_xml[pos:min(len(doc_xml), pos + 1500)])
        print(f"=== {rid} ===")
        print("  Preceding text:", " ".join(pre_matches[-8:]))
        print("  Post text:", " ".join(post_matches[:8]))
