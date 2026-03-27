import hashlib
import os
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import arabic_reshaper
from bidi.algorithm import get_display

def calculate_file_hash(file_path):
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}

def generate_pdf(records, title, columns, anonymize=False):
    # Register font
    font_path = os.path.join(os.getcwd(), 'static', 'fonts', 'Amiri-Regular.ttf')
    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont('Amiri', font_path))
        font_name = 'Amiri'
    else:
        font_name = 'Helvetica' # Fallback

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    elements = []

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='ArabicTitle', fontName=font_name, fontSize=18, alignment=1, spaceAfter=20))
    styles.add(ParagraphStyle(name='ArabicNormal', fontName=font_name, fontSize=10, alignment=2)) # Right aligned

    # Logo
    logo_path = os.path.join(os.getcwd(), 'static', 'img', 'logo.jpg')
    if os.path.exists(logo_path):
        im = Image(logo_path, width=50, height=50)
        im.hAlign = 'RIGHT'
        elements.append(im)
        elements.append(Spacer(1, 12))

    # Title
    reshaped_title = get_display(arabic_reshaper.reshape(title))
    elements.append(Paragraph(reshaped_title, styles['ArabicTitle']))

    # Table Data
    data = []
    # Header
    headers = [col['label'] for col in columns]
    reshaped_headers = [get_display(arabic_reshaper.reshape(h)) for h in headers]
    # Reverse columns for RTL visual order in LTR table
    data.append(reshaped_headers[::-1])

    for record in records:
        row = []
        for col in columns:
            if anonymize and col['field'] in ['first_name', 'father_name', 'last_name', 'mother_name', 'national_id', 'phone']:
                if col['field'] == 'first_name':
                    val = f"Record ID: {record.id}"
                else:
                    val = "---"
            else:
                val = getattr(record, col['field'])
                if val is None:
                    val = ""
                val = str(val)

            # Reshape Arabic text
            reshaped_val = get_display(arabic_reshaper.reshape(val))
            row.append(reshaped_val)
        # Reverse row for RTL
        data.append(row[::-1])

    # Table Style
    if not data:
        elements.append(Paragraph("No records found.", styles['Normal']))
    else:
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(table)

    doc.build(elements)

    buffer.seek(0)
    return buffer
