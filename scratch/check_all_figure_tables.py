import docx
import zipfile
import re

doc = docx.Document('d:/Coding/Major Project/FieldNotes/FieldNotes_MongoDB_Project_Report.docx')

print("=== CHECKING ALL TABLES FOR FIGURES AND IMAGES ===")
for i, tbl in enumerate(doc.tables):
    txt = ""
    for r in tbl.rows:
        for c in r.cells:
            txt += c.text + "\n"
    tbl_xml = tbl._tbl.xml
    has_drawing = "<w:drawing" in tbl_xml
    draw_match = re.findall(r'r:embed="([^"]+)"', tbl_xml)
    
    # Check if this table has figure info or image
    if has_drawing or "Figure" in txt or "SCREENSHOT" in txt or len(tbl.rows) == 1:
        # Get preceding paragraph
        print(f"Table {i+1} (Rows: {len(tbl.rows)}, Cols: {len(tbl.columns)}):")
        print(f"  Has drawing: {has_drawing}, embed: {draw_match}")
        snippet = txt.strip()[:100].replace('\n', ' ')
        print(f"  Text snippet: {snippet}")
