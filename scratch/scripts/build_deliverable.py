#!/usr/bin/env python3
"""
Sprint 1 Deliverable Build Pipeline
===================================
Compiles Markdown specification (`docs/sprint-1/SRS.md`) and Mermaid diagrams
(`docs/sprint-1/diagrams/`) into finalized, portal-ready submission packages:
  - deliverables/sprint-1/Sprint1_Release1_SRS.docx
  - deliverables/sprint-1/Sprint1_Release1_SRS.pdf
  - deliverables/sprint-1/Team1_Sprint1_Release1_Submission.zip

Usage:
    python3 scratch/scripts/build_deliverable.py
"""

import os
import re
import glob
import zipfile
import struct
import subprocess
import urllib.request
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn


def get_png_dimensions(file_path: str):
    """Read width and height in pixels from a PNG header."""
    with open(file_path, 'rb') as f:
        data = f.read(24)
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            w, h = struct.unpack('>LL', data[16:24])
            return w, h
    return 1000, 1000


def render_diagrams(diagrams_dir: str, output_dir: str) -> dict:
    """Render all .mmd diagrams in diagrams_dir to PNG via Kroki."""
    os.makedirs(output_dir, exist_ok=True)
    rendered_map = {}
    mmd_files = sorted(glob.glob(os.path.join(diagrams_dir, "*.mmd")))

    print(f"[1/4] Rendering {len(mmd_files)} Mermaid UML diagrams...")
    for mmd_path in mmd_files:
        name = os.path.splitext(os.path.basename(mmd_path))[0]
        png_path = os.path.join(output_dir, f"{name}.png")
        if not os.path.exists(png_path) or os.path.getmtime(mmd_path) > os.path.getmtime(png_path):
            with open(mmd_path, "r", encoding="utf-8") as f:
                content = f.read()
            req = urllib.request.Request(
                "https://kroki.io/mermaid/png",
                data=content.encode("utf-8"),
                headers={"Content-Type": "text/plain; charset=utf-8", "User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = resp.read()
                with open(png_path, "wb") as out_f:
                    out_f.write(data)
            print(f"  ✓ Rendered {name}.png ({len(data):,} bytes)")
        else:
            print(f"  ✓ Up to date: {name}.png")
        rendered_map[name] = png_path
    return rendered_map


def set_cell_background(cell, hex_color: str):
    """Set background color for a docx table cell."""
    shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    cell._tc.get_or_add_tcPr().append(shading_elm)


def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Set inner padding for a table cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)


def build_docx_from_markdown(md_path: str, docx_path: str, diagrams: dict):
    """Parse SRS.md and construct an IEEE-styled Word document."""
    print(f"[2/4] Compiling {md_path} into {docx_path}...")
    doc = Document()

    # Configure Margins (0.75 in for diagrams and readable tables)
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)

    # Styles
    normal_style = doc.styles['Normal']
    normal_style.font.name = 'Times New Roman'
    normal_style.font.size = Pt(11)
    normal_style.font.color.rgb = RGBColor(0x22, 0x22, 0x22)

    with open(md_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    i = 0
    in_table = False
    table_lines = []

    def flush_table(lines_to_flush):
        if not lines_to_flush:
            return
        parsed_rows = []
        for line in lines_to_flush:
            stripped = line.strip()
            if re.match(r'^\|?\s*:?-+:?\s*\|', stripped):
                continue  # skip separator
            cells = [c.strip() for c in stripped.strip('|').split('|')]
            if cells:
                parsed_rows.append(cells)

        if not parsed_rows:
            return

        num_cols = max(len(r) for r in parsed_rows)
        tbl = doc.add_table(rows=len(parsed_rows), cols=num_cols)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER

        for row_idx, row_data in enumerate(parsed_rows):
            is_header = (row_idx == 0)
            row = tbl.rows[row_idx]
            for col_idx in range(num_cols):
                cell = row.cells[col_idx]
                text = row_data[col_idx] if col_idx < len(row_data) else ""
                # Clean markdown bold/italics in cell
                cleaned_text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
                cleaned_text = re.sub(r'\*(.*?)\*', r'\1', cleaned_text)
                cell.text = cleaned_text

                # Formatting
                p = cell.paragraphs[0]
                p.paragraph_format.space_after = Pt(2)
                p.paragraph_format.space_before = Pt(2)
                if p.runs:
                    run = p.runs[0]
                    run.font.name = 'Times New Roman'
                    if is_header:
                        run.font.bold = True
                        run.font.size = Pt(10)
                        set_cell_background(cell, "2B4C7E")
                        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                    else:
                        run.font.size = Pt(9.5)
                        if row_idx % 2 == 1:
                            set_cell_background(cell, "F4F6F9")
                set_cell_margins(cell, top=80, bottom=80, left=120, right=120)
        doc.add_paragraph().paragraph_format.space_after = Pt(4)

    # Numbered academic figure list
    figure_list = [
        ("Figure 1: UML Use-Case Model — Actor Interactions and System Boundary", diagrams.get("use_case_diagram")),
        ("Figure 2: Initial UML Class Diagram — Core Domain Entities and Multiplicities", diagrams.get("class_diagram")),
        ("Figure 3: Activity Diagram — Order Scheduling and Drone Assignment Workflow", diagrams.get("activity_order_scheduling")),
        ("Figure 4: Activity Diagram — In-Flight Exception and Return-to-Base Recovery", diagrams.get("activity_exception_handling")),
        ("Figure 5: State Machine Diagram — Delivery Order Lifecycle", diagrams.get("state_order_lifecycle")),
        ("Figure 6: State Machine Diagram — Drone Operational Status Transitions", diagrams.get("state_drone_lifecycle")),
    ]

    current_section = ""

    while i < len(lines):
        raw_line = lines[i]
        line = raw_line.strip()

        # Table detection
        if line.startswith('|'):
            in_table = True
            table_lines.append(line)
            i += 1
            continue
        elif in_table:
            in_table = False
            flush_table(table_lines)
            table_lines = []

        if not line:
            i += 1
            continue

        # Horizontal Rule
        if line in ['---', '***', '___']:
            i += 1
            continue

        # Headings
        if line.startswith('# '):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(line[2:])
            run.font.name = 'Times New Roman'
            run.font.size = Pt(22)
            run.font.bold = True
            run.font.color.rgb = RGBColor(0x1A, 0x36, 0x5D)
            p.paragraph_format.space_before = Pt(18)
            p.paragraph_format.space_after = Pt(6)
        elif line.startswith('## '):
            current_section = line[3:]
            # Major section breaks for readability
            if any(sec in current_section for sec in ["9. System Models", "10. External Interfaces", "16. Appendices"]):
                doc.add_page_break()
            p = doc.add_paragraph()
            run = p.add_run(current_section)
            run.font.name = 'Times New Roman'
            run.font.size = Pt(15)
            run.font.bold = True
            run.font.color.rgb = RGBColor(0x2B, 0x4C, 0x7E)
            p.paragraph_format.space_before = Pt(14)
            p.paragraph_format.space_after = Pt(4)

        elif line == '<!-- EMBED_FIGURES -->':
            for fig_caption, img_path in figure_list:
                if img_path and os.path.exists(img_path):
                    # Force dedicated page for each diagram to prevent cutoff
                    doc.add_page_break()

                    # Calculate proportional scaling to fit printable bounds (max 6.6 in width, max 8.0 in height)
                    w_px, h_px = get_png_dimensions(img_path)
                    aspect = h_px / w_px
                    max_w = 6.6
                    max_h = 8.0

                    if aspect > (max_h / max_w):
                        target_h = max_h
                        target_w = max_h / aspect
                    else:
                        target_w = max_w
                        target_h = max_w * aspect

                    # Add image centered
                    img_p = doc.add_paragraph()
                    img_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    img_p.paragraph_format.space_before = Pt(6)
                    img_p.paragraph_format.space_after = Pt(8)
                    img_run = img_p.add_run()
                    img_run.add_picture(img_path, width=Inches(target_w), height=Inches(target_h))

                    # Add formal numbered academic caption
                    cap_p = doc.add_paragraph()
                    cap_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    cap_p.paragraph_format.space_after = Pt(12)
                    cap_run = cap_p.add_run(fig_caption)
                    cap_run.font.name = 'Times New Roman'
                    cap_run.font.bold = True
                    cap_run.font.size = Pt(10.5)
                    cap_run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

        elif line.startswith('### '):
            p = doc.add_paragraph()
            run = p.add_run(line[4:])
            run.font.name = 'Times New Roman'
            run.font.size = Pt(13)
            run.font.bold = True
            run.font.color.rgb = RGBColor(0x22, 0x22, 0x22)
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(2)
        elif line.startswith('#### '):
            p = doc.add_paragraph()
            run = p.add_run(line[5:])
            run.font.name = 'Times New Roman'
            run.font.size = Pt(11.5)
            run.font.bold = True
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after = Pt(2)
        elif line.startswith('- ') or line.startswith('• '):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.25)
            p.paragraph_format.first_line_indent = Inches(-0.15)
            bullet_run = p.add_run("• ")
            bullet_run.font.name = 'Times New Roman'
            bullet_run.font.bold = True
            text = line[2:]
            parts = re.split(r'(\*\*.*?\*\*)', text)
            for part in parts:
                if part.startswith('**') and part.endswith('**'):
                    r = p.add_run(part[2:-2])
                    r.font.name = 'Times New Roman'
                    r.font.bold = True
                else:
                    r = p.add_run(part)
                    r.font.name = 'Times New Roman'
            p.paragraph_format.space_after = Pt(2)
        elif re.match(r'^(\d+\.)\s*(.*)', line):
            m = re.match(r'^(\d+\.)\s*(.*)', line)
            num_str = m.group(1)
            text = m.group(2)
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.28)
            p.paragraph_format.first_line_indent = Inches(-0.28)
            r_num = p.add_run(num_str + " ")
            r_num.font.name = 'Times New Roman'
            r_num.font.bold = True
            parts = re.split(r'(\*\*.*?\*\*)', text)
            for part in parts:
                if part.startswith('**') and part.endswith('**'):
                    r = p.add_run(part[2:-2])
                    r.font.name = 'Times New Roman'
                    r.font.bold = True
                else:
                    r = p.add_run(part)
                    r.font.name = 'Times New Roman'
            p.paragraph_format.space_after = Pt(2)
        else:
            p = doc.add_paragraph()
            parts = re.split(r'(\*\*.*?\*\*)', line)
            for part in parts:
                if part.startswith('**') and part.endswith('**'):
                    r = p.add_run(part[2:-2])
                    r.font.bold = True
                else:
                    p.add_run(part)
            p.paragraph_format.space_after = Pt(4)

        i += 1

    if in_table:
        flush_table(table_lines)

    os.makedirs(os.path.dirname(docx_path), exist_ok=True)
    doc.save(docx_path)
    print(f"  ✓ Saved Word document ({os.path.getsize(docx_path):,} bytes)")


def convert_docx_to_pdf(docx_path: str, output_dir: str) -> str:
    """Convert .docx to .pdf using LibreOffice headless."""
    print(f"[3/4] Exporting PDF via LibreOffice...")
    cmd = [
        "libreoffice",
        "--headless",
        "--convert-to", "pdf",
        docx_path,
        "--outdir", output_dir
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    base_name = os.path.splitext(os.path.basename(docx_path))[0]
    pdf_path = os.path.join(output_dir, f"{base_name}.pdf")
    if os.path.exists(pdf_path):
        print(f"  ✓ Generated PDF: {pdf_path} ({os.path.getsize(pdf_path):,} bytes)")
        return pdf_path
    raise FileNotFoundError("PDF conversion failed")


def create_submission_zip(zip_path: str, files: list, folder_map: dict):
    """Package submission files into a clean zip archive."""
    print(f"[4/4] Creating submission archive: {zip_path}...")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for fpath in files:
            arcname = os.path.basename(fpath)
            zipf.write(fpath, arcname)
            print(f"  + Added: {arcname}")
        for arc_folder, src_folder in folder_map.items():
            for root, _, fnames in os.walk(src_folder):
                for fname in fnames:
                    full_p = os.path.join(root, fname)
                    rel_p = os.path.relpath(full_p, src_folder)
                    arc_p = os.path.join(arc_folder, rel_p)
                    zipf.write(full_p, arc_p)
                    print(f"  + Added: {arc_p}")
    print(f"  ✓ Final submission zip ready ({os.path.getsize(zip_path):,} bytes)!")


if __name__ == "__main__":
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    docs_dir = os.path.join(repo_root, "docs", "sprint-1")
    deliv_dir = os.path.join(repo_root, "deliverables", "sprint-1")
    scratch_diagrams = os.path.join(repo_root, "scratch", "rendered_diagrams")

    md_srs = os.path.join(docs_dir, "SRS.md")
    mmd_dir = os.path.join(docs_dir, "diagrams")
    out_docx = os.path.join(deliv_dir, "Sprint1_Release1_SRS.docx")
    out_zip = os.path.join(deliv_dir, "Team1_Sprint1_Release1_Submission.zip")

    # Step 1: Render diagrams
    diagram_map = render_diagrams(mmd_dir, scratch_diagrams)

    # Step 2: Build DOCX
    build_docx_from_markdown(md_srs, out_docx, diagram_map)

    # Step 3: Convert to PDF
    pdf_path = convert_docx_to_pdf(out_docx, deliv_dir)

    # Step 4: Assemble Zip
    create_submission_zip(
        out_zip,
        files=[out_docx, pdf_path],
        folder_map={"diagrams_high_res": scratch_diagrams}
    )

    print("\n============================================================")
    print("✨ SPRINT 1 DELIVERABLE BUILD COMPLETED SUCCESSFULLY! ✨")
    print("Deliverables ready in `deliverables/sprint-1/`:")
    print(f"  1. {os.path.basename(out_docx)}")
    print(f"  2. {os.path.basename(pdf_path)}")
    print(f"  3. {os.path.basename(out_zip)}")
    print("============================================================")
