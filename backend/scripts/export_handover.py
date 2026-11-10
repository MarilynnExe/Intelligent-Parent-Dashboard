"""Export docs/HANDOVER.md to Word and PDF using an isolated LibreOffice profile.
Requires LibreOffice on PATH; adds no application dependency.
"""
import html
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]

def inline(text):
    text = html.escape(text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', lambda m: f'{m[1]} ({m[2]})', text)

def render(markdown):
    blocks, table, code, paragraph = [], [], None, []
    def flush_paragraph():
        if paragraph:
            blocks.append('<p>'+inline(' '.join(paragraph))+'</p>');paragraph.clear()
    def flush_table():
        if not table:return
        rows=[]
        for index,line in enumerate(table):
            if re.fullmatch(r'[| :\-]+',line):continue
            tag='th' if index==0 else 'td'
            rows.append('<tr>'+''.join(f'<{tag}>{inline(cell.strip())}</{tag}>' for cell in line.strip('|').split('|'))+'</tr>')
        blocks.append('<table>'+''.join(rows)+'</table>');table.clear()
    for line in markdown.splitlines():
        if line.startswith('```'):
            flush_paragraph();flush_table()
            if code is None:code=[]
            else:blocks.append('<pre>'+html.escape('\n'.join(code))+'</pre>');code=None
            continue
        if code is not None:code.append(line);continue
        if line.startswith('|'):flush_paragraph();table.append(line);continue
        flush_table()
        if not line.strip():flush_paragraph();continue
        heading=re.match(r'^(#{1,6}) (.*)',line)
        if heading:
            flush_paragraph();n=len(heading[1]);blocks.append(f'<h{n}>{inline(heading[2])}</h{n}>')
        elif re.match(r'^\d+\. ',line):
            flush_paragraph();blocks.append('<p>'+inline(line)+'</p>')
        else:paragraph.append(line)
    flush_paragraph();flush_table()
    return '''<!DOCTYPE html><html><head><meta charset="utf-8"><title>Intelligent Parent Dashboard — Handover</title><style>
    @page {size:A4; margin:1.8cm;} body {font-family:Arial,sans-serif;font-size:10pt;line-height:1.35;color:#1e293b;}
    h1 {font-size:23pt;color:#5b21b6;} h2 {font-size:15pt;color:#5b21b6;margin-top:20pt;page-break-after:avoid;}
    table {border-collapse:collapse;width:100%;font-size:9pt;margin:10pt 0;} td,th {border:1px solid #cbd5e1;padding:6pt;text-align:left;vertical-align:top;} th {background:#ede9fe;} tr {page-break-inside:avoid;}
    pre {font-family:monospace;font-size:8pt;background:#f1f5f9;white-space:pre-wrap;} code {font-family:monospace;font-size:9pt;}
    </style></head><body>'''+''.join(blocks)+'</body></html>'

def main():
    with tempfile.TemporaryDirectory(prefix='ipd-handover-export-') as tmp:
        temp=Path(tmp);source=temp/'HANDOVER.html';source.write_text(render((ROOT/'docs/HANDOVER.md').read_text()))
        profile=f'-env:UserInstallation={(temp/"office-profile").as_uri()}'
        subprocess.run(['libreoffice',profile,'--headless','--convert-to','docx:Office Open XML Text','--outdir',str(ROOT/'docs'),str(source)],check=True)
        # HTML import can choose table widths wider than the document's text area.
        # Constrain table/grid/cell widths before producing either shareable format.
        document = ROOT/'docs/HANDOVER.docx'
        with zipfile.ZipFile(document) as archive:
            parts = {name:archive.read(name) for name in archive.namelist()}
        xml = parts['word/document.xml'].decode()
        def fit_table(match):
            table = match.group(0)
            width = re.search(r'<w:tblW[^>]*w:w="(\d+)"',table)
            if not width or int(width[1]) <= 9866:return table
            factor = 9866/int(width[1])
            return re.sub(r'(<w:(?:tblW|gridCol|tcW)\b[^>]*?\bw:w=")(\d+)',lambda m:m[1]+str(round(int(m[2])*factor)),table)
        xml = re.sub(r'<w:tbl>.*?</w:tbl>',fit_table,xml,flags=re.S)
        parts['word/document.xml'] = xml.encode()
        with zipfile.ZipFile(document,'w',zipfile.ZIP_DEFLATED) as archive:
            for name,data in parts.items():archive.writestr(name,data)
        subprocess.run(['libreoffice',profile,'--headless','--convert-to','pdf' ,'--outdir',str(ROOT/'docs'),str(ROOT/'docs/HANDOVER.docx')],check=True)
    print('Exported docs/HANDOVER.docx and docs/HANDOVER.pdf')

if __name__=='__main__':main()
