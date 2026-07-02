import io
import re
import markdown
import weasyprint
import docx
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH

def markdown_to_pdf(md_text):
    """
    Converts markdown text to PDF bytes using WeasyPrint with executive-style CSS.
    """
    # Parse markdown to HTML
    html_body = markdown.markdown(md_text)
    
    # Wrap in standard professional print template
    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            @page {{
                size: letter;
                margin: 0.75in 0.75in 0.75in 0.75in;
                @bottom-right {{
                    content: counter(page);
                    font-family: Arial, sans-serif;
                    font-size: 8pt;
                    color: #718096;
                }}
            }}
            body {{
                font-family: Arial, "Helvetica Neue", Helvetica, sans-serif;
                font-size: 10pt;
                line-height: 1.45;
                color: #2d3748;
                margin: 0;
                padding: 0;
            }}
            h1 {{
                text-align: center;
                font-size: 18pt;
                margin-top: 0;
                margin-bottom: 6px;
                color: #1a202c;
                font-weight: bold;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            h2 {{
                font-size: 12pt;
                color: #2b6cb0; /* Sleek Slate Blue */
                border-bottom: 1.5px solid #2b6cb0;
                padding-bottom: 2px;
                margin-top: 16px;
                margin-bottom: 8px;
                text-transform: uppercase;
                font-weight: bold;
            }}
            h3 {{
                font-size: 10.5pt;
                margin-top: 10px;
                margin-bottom: 4px;
                color: #1a202c;
                font-weight: bold;
            }}
            p {{
                margin-top: 0;
                margin-bottom: 6px;
            }}
            ul {{
                margin-top: 0;
                margin-bottom: 8px;
                padding-left: 18px;
            }}
            li {{
                margin-bottom: 3px;
            }}
            strong {{
                font-weight: bold;
                color: #1a202c;
            }}
            em {{
                font-style: italic;
            }}
            hr {{
                border: 0;
                border-top: 1px solid #e2e8f0;
                margin: 10px 0;
            }}
            /* Header/Contact paragraph styling */
            p.contact-header {{
                text-align: center;
                font-size: 9pt;
                color: #4a5568;
                margin-bottom: 12px;
                line-height: 1.2;
            }}
        </style>
    </head>
    <body>
        {html_body}
    </body>
    </html>
    """
    
    # WeasyPrint renders the HTML to a PDF byte stream
    return weasyprint.HTML(string=full_html).write_pdf()

def markdown_to_docx(md_text):
    """
    Converts markdown text to a professional DOCX file.
    """
    doc = docx.Document()
    
    # Set 1-inch margins
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)
        
    # Configure base font styles
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Arial'
    font.size = Pt(10.5)
    font.color.rgb = docx.shared.RGBColor(45, 55, 72) # #2d3748
    
    lines = md_text.split('\n')
    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue
            
        # Parse titles and sections
        if line_str.startswith('# '):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(line_str[2:])
            run.font.size = Pt(18)
            run.font.bold = True
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(8)
            
        elif line_str.startswith('## '):
            p = doc.add_paragraph()
            run = p.add_run(line_str[3:])
            run.font.size = Pt(13)
            run.font.bold = True
            run.font.color.rgb = docx.shared.RGBColor(43, 108, 176) # #2b6cb0 (Slate Blue)
            p.paragraph_format.space_before = Pt(14)
            p.paragraph_format.space_after = Pt(6)
            
        elif line_str.startswith('### '):
            p = doc.add_paragraph()
            run = p.add_run(line_str[4:])
            run.font.size = Pt(11)
            run.font.bold = True
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after = Pt(4)
            
        elif line_str.startswith('- ') or line_str.startswith('* '):
            p = doc.add_paragraph(style='List Bullet')
            text_content = line_str[2:]
            _parse_inline_docx_formatting(p, text_content)
            p.paragraph_format.space_after = Pt(3)
            
        else:
            p = doc.add_paragraph()
            _parse_inline_docx_formatting(p, line_str)
            p.paragraph_format.space_after = Pt(6)
            
    # Save to a byte stream
    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream.read()

def _parse_inline_docx_formatting(paragraph, text):
    """
    Helper to parse markdown bold (**) and italic (*) in paragraphs
    """
    # Regex to split on bold/italic markers
    tokens = re.split(r'(\*\*.*?\*\*|\*.*?\*)', text)
    for token in tokens:
        if token.startswith('**') and token.endswith('**'):
            run = paragraph.add_run(token[2:-2])
            run.bold = True
        elif token.startswith('*') and token.endswith('*'):
            run = paragraph.add_run(token[1:-1])
            run.italic = True
        else:
            paragraph.add_run(token)
