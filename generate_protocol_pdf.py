#!/usr/bin/env python3
"""
Generate a professional Arabic PDF describing the Haqquna documentation protocols.
Based on the Berkeley Protocol for Digital Open Source Investigations.
"""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_JUSTIFY
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, Image, KeepTogether
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Circle, Polygon
from reportlab.graphics import renderPDF
import arabic_reshaper
from bidi.algorithm import get_display

# ── Fonts ──────────────────────────────────────────────────────────────
pdfmetrics.registerFont(TTFont('Amiri', '/tmp/fonts/Amiri-Regular.ttf'))
pdfmetrics.registerFont(TTFont('AmiriBold', '/tmp/fonts/Amiri-Bold.ttf'))
pdfmetrics.registerFontFamily('Amiri', normal='Amiri', bold='AmiriBold')

# ── Colors ─────────────────────────────────────────────────────────────
PRIMARY = HexColor('#1a5276')
SECONDARY = HexColor('#2e86c1')
ACCENT = HexColor('#27ae60')
WARN = HexColor('#e67e22')
DANGER = HexColor('#c0392b')
LIGHT_BG = HexColor('#eaf2f8')
LIGHTER_BG = HexColor('#f8f9fa')
BORDER = HexColor('#d5dbdb')
DARK_TEXT = HexColor('#2c3e50')
MEDIUM_TEXT = HexColor('#5d6d7e')

# ── Arabic helper ──────────────────────────────────────────────────────
def ar(text):
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)

# ── Styles ─────────────────────────────────────────────────────────────
def make_styles():
    s = {}
    s['title'] = ParagraphStyle('Title', fontName='AmiriBold', fontSize=28,
        leading=40, alignment=TA_CENTER, textColor=PRIMARY, wordWrap='RTL')
    s['subtitle'] = ParagraphStyle('Subtitle', fontName='Amiri', fontSize=16,
        leading=24, alignment=TA_CENTER, textColor=SECONDARY, wordWrap='RTL')
    s['h1'] = ParagraphStyle('H1', fontName='AmiriBold', fontSize=20,
        leading=30, alignment=TA_RIGHT, textColor=PRIMARY, spaceBefore=20,
        spaceAfter=10, wordWrap='RTL')
    s['h2'] = ParagraphStyle('H2', fontName='AmiriBold', fontSize=16,
        leading=24, alignment=TA_RIGHT, textColor=SECONDARY, spaceBefore=14,
        spaceAfter=8, wordWrap='RTL')
    s['h3'] = ParagraphStyle('H3', fontName='AmiriBold', fontSize=13,
        leading=20, alignment=TA_RIGHT, textColor=DARK_TEXT, spaceBefore=10,
        spaceAfter=6, wordWrap='RTL')
    s['body'] = ParagraphStyle('Body', fontName='Amiri', fontSize=12,
        leading=20, alignment=TA_RIGHT, textColor=DARK_TEXT, wordWrap='RTL')
    s['body_center'] = ParagraphStyle('BodyCenter', fontName='Amiri', fontSize=12,
        leading=20, alignment=TA_CENTER, textColor=DARK_TEXT, wordWrap='RTL')
    s['bullet'] = ParagraphStyle('Bullet', fontName='Amiri', fontSize=11,
        leading=18, alignment=TA_RIGHT, textColor=DARK_TEXT, leftIndent=20,
        wordWrap='RTL')
    s['small'] = ParagraphStyle('Small', fontName='Amiri', fontSize=10,
        leading=15, alignment=TA_RIGHT, textColor=MEDIUM_TEXT, wordWrap='RTL')
    s['table_header'] = ParagraphStyle('TH', fontName='AmiriBold', fontSize=11,
        leading=16, alignment=TA_CENTER, textColor=white, wordWrap='RTL')
    s['table_cell'] = ParagraphStyle('TC', fontName='Amiri', fontSize=10,
        leading=15, alignment=TA_CENTER, textColor=DARK_TEXT, wordWrap='RTL')
    s['table_cell_r'] = ParagraphStyle('TCR', fontName='Amiri', fontSize=10,
        leading=15, alignment=TA_RIGHT, textColor=DARK_TEXT, wordWrap='RTL')
    s['footer'] = ParagraphStyle('Footer', fontName='Amiri', fontSize=9,
        leading=14, alignment=TA_CENTER, textColor=MEDIUM_TEXT, wordWrap='RTL')
    s['number_big'] = ParagraphStyle('NumBig', fontName='AmiriBold', fontSize=24,
        leading=30, alignment=TA_CENTER, textColor=PRIMARY)
    return s

# ── Drawing helpers ────────────────────────────────────────────────────
def draw_workflow_diagram(width):
    """Draw the 7-step documentation workflow as a professional flowchart."""
    h = 420
    d = Drawing(width, h)

    steps = [
        ('١', ar('الحالة والمُبلِّغ'), PRIMARY),
        ('٢', ar('البيانات الشخصية'), SECONDARY),
        ('٣', ar('تفاصيل الاعتقال'), HexColor('#8e44ad')),
        ('٤', ar('المرافقون'), WARN),
        ('٥', ar('الشهود'), ACCENT),
        ('٦', ar('العائلة والعنوان'), HexColor('#e74c3c')),
        ('٧', ar('ملاحظات وحفظ'), HexColor('#2c3e50')),
    ]

    box_w = 130
    box_h = 42
    gap = 14
    start_x = (width - box_w) / 2
    y = h - 30

    for i, (num, label, color) in enumerate(steps):
        by = y - i * (box_h + gap)
        d.add(Rect(start_x, by - box_h, box_w, box_h,
                    fillColor=color, strokeColor=None, rx=8, ry=8))
        d.add(String(start_x + box_w / 2, by - box_h + 26,
                     num, fontName='AmiriBold', fontSize=14,
                     fillColor=white, textAnchor='middle'))
        d.add(String(start_x + box_w / 2, by - box_h + 10,
                     label, fontName='AmiriBold', fontSize=11,
                     fillColor=white, textAnchor='middle'))

        if i < len(steps) - 1:
            arrow_x = start_x + box_w / 2
            arrow_top = by - box_h - 2
            arrow_bot = by - box_h - gap + 2
            d.add(Line(arrow_x, arrow_top, arrow_x, arrow_bot,
                       strokeColor=BORDER, strokeWidth=2))
            d.add(Polygon(
                points=[arrow_x - 5, arrow_bot + 6, arrow_x + 5, arrow_bot + 6,
                        arrow_x, arrow_bot],
                fillColor=BORDER, strokeColor=None))
    return d


def draw_evidence_levels(width):
    """Draw evidence level classification as colored blocks."""
    h = 100
    d = Drawing(width, h)

    levels = [
        (ar('عالي'), ar('أدلة موثقة متعددة'), ACCENT),
        (ar('متوسط'), ar('دليل واحد موثق'), SECONDARY),
        (ar('منخفض'), ar('شهادة شفهية فقط'), WARN),
        (ar('غير متحقق'), ar('بدون تحقق'), DANGER),
    ]

    block_w = width / 4 - 8
    y = 10
    for i, (title, desc, color) in enumerate(levels):
        x = width - (i + 1) * (block_w + 6)
        d.add(Rect(x, y, block_w, 70, fillColor=color, strokeColor=None, rx=6, ry=6))
        d.add(String(x + block_w / 2, y + 48, title,
                     fontName='AmiriBold', fontSize=13, fillColor=white,
                     textAnchor='middle'))
        d.add(String(x + block_w / 2, y + 18, desc,
                     fontName='Amiri', fontSize=9, fillColor=white,
                     textAnchor='middle'))
    return d


def draw_status_diagram(width):
    """Draw the 3 case statuses with colored circles."""
    h = 90
    d = Drawing(width, h)

    statuses = [
        (ar('ناجٍ'), ar('أُفرج عنه أو هرب'), ACCENT),
        (ar('مغيّب قسراً'), ar('لا يُعرف مصيره'), WARN),
        (ar('متوفى'), ar('مؤكد الوفاة'), DANGER),
    ]

    spacing = width / 3
    for i, (title, desc, color) in enumerate(statuses):
        cx = width - spacing * i - spacing / 2
        d.add(Circle(cx, 55, 22, fillColor=color, strokeColor=None))
        d.add(String(cx, 50, title, fontName='AmiriBold', fontSize=11,
                     fillColor=white, textAnchor='middle'))
        d.add(String(cx, 18, desc, fontName='Amiri', fontSize=9,
                     fillColor=DARK_TEXT, textAnchor='middle'))
    return d


def draw_verification_flow(width):
    """Draw verification workflow."""
    h = 70
    d = Drawing(width, h)

    stages = [
        (ar('جمع'), HexColor('#3498db')),
        (ar('مراجعة'), WARN),
        (ar('تحقق'), HexColor('#8e44ad')),
        (ar('قفل'), ACCENT),
    ]

    box_w = 90
    total_w = len(stages) * box_w + (len(stages) - 1) * 30
    start_x = (width - total_w) / 2 + total_w

    for i, (label, color) in enumerate(stages):
        x = start_x - (i + 1) * (box_w + 30) + 30
        d.add(Rect(x, 20, box_w, 40, fillColor=color, strokeColor=None, rx=6, ry=6))
        d.add(String(x + box_w / 2, 35, label,
                     fontName='AmiriBold', fontSize=13, fillColor=white,
                     textAnchor='middle'))
        if i < len(stages) - 1:
            ax = x - 15
            d.add(Line(x - 2, 40, x - 28, 40, strokeColor=BORDER, strokeWidth=2))
            d.add(Polygon(points=[ax - 6, 45, ax - 6, 35, ax - 14, 40],
                          fillColor=BORDER, strokeColor=None))
    return d


# ── Colored info box ───────────────────────────────────────────────────
def info_box(text, style, color=LIGHT_BG, border_color=SECONDARY):
    tbl = Table([[Paragraph(ar(text), style)]], colWidths=[440])
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), color),
        ('BOX', (0, 0), (-1, -1), 1.5, border_color),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 14),
        ('RIGHTPADDING', (0, 0), (-1, -1), 14),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return tbl


def header_line():
    return HRFlowable(width="100%", thickness=1.5, color=SECONDARY,
                      spaceAfter=10, spaceBefore=4)


# ── Build the document ─────────────────────────────────────────────────
def build_pdf(output_path):
    styles = make_styles()
    page_w, page_h = A4

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        rightMargin=2 * cm, leftMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm
    )

    story = []

    # ════════════════════════ COVER PAGE ════════════════════════
    story.append(Spacer(1, 2 * cm))

    # Logo
    logo_path = '/home/user/dd/logo.jpg'
    if os.path.exists(logo_path):
        story.append(Image(logo_path, width=4 * cm, height=4 * cm, hAlign='CENTER'))
        story.append(Spacer(1, 1 * cm))

    story.append(Paragraph(ar('جمعية حقنا'), styles['title']))
    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(width="60%", thickness=3, color=PRIMARY,
                            spaceAfter=12, spaceBefore=4, hAlign='CENTER'))
    story.append(Paragraph(ar('بروتوكول التوثيق الشامل'), styles['title']))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(ar('دليل إجراءات توثيق حالات الاختفاء القسري والاعتقال'), styles['subtitle']))
    story.append(Spacer(1, 0.8 * cm))

    story.append(info_box(
        'وفقاً لبروتوكول بيركلي للتحقيقات الرقمية في المصادر المفتوحة — الأمم المتحدة',
        styles['body_center'], color=HexColor('#f0f4f8'), border_color=PRIMARY
    ))

    story.append(Spacer(1, 2 * cm))
    story.append(Paragraph(ar('الإصدار ١.٠ — ٢٠٢٥'), styles['body_center']))
    story.append(Paragraph(ar('وثيقة سرية — للاستخدام الداخلي فقط'), styles['small']))

    story.append(PageBreak())

    # ════════════════════════ TABLE OF CONTENTS ════════════════════════
    story.append(Paragraph(ar('فهرس المحتويات'), styles['h1']))
    story.append(header_line())

    toc_items = [
        ('١', 'المقدمة وأهداف البروتوكول'),
        ('٢', 'الإطار القانوني والمرجعي'),
        ('٣', 'مراحل عملية التوثيق (٧ خطوات)'),
        ('٤', 'تصنيف الحالات'),
        ('٥', 'مستويات الأدلة والتحقق'),
        ('٦', 'منهجيات جمع البيانات'),
        ('٧', 'سلسلة الحفظ الرقمية'),
        ('٨', 'إدارة البيانات والأمان'),
        ('٩', 'مسار التحقق والمراجعة'),
        ('١٠', 'الملاحق'),
    ]
    for num, title in toc_items:
        story.append(Paragraph(
            ar(f'{title} ........................... {num}'),
            styles['body']
        ))
    story.append(PageBreak())

    # ════════════════════════ SECTION 1: INTRODUCTION ════════════════════════
    story.append(Paragraph(ar('١. المقدمة وأهداف البروتوكول'), styles['h1']))
    story.append(header_line())

    story.append(Paragraph(ar(
        'يُحدد هذا البروتوكول الإجراءات المعتمدة لتوثيق حالات الاختفاء القسري والاعتقال التعسفي '
        'في سوريا. تم تصميمه ليتوافق مع المعايير الدولية لحقوق الإنسان وبروتوكول بيركلي '
        'للتحقيقات الرقمية في المصادر المفتوحة الصادر عن مكتب الأمم المتحدة لحقوق الإنسان.'
    ), styles['body']))
    story.append(Spacer(1, 8))

    story.append(Paragraph(ar('الأهداف الرئيسية:'), styles['h3']))
    objectives = [
        'توثيق منهجي ودقيق لكل حالة اختفاء قسري أو اعتقال وفق معايير موحدة',
        'ضمان سلامة البيانات وسلسلة الحفظ الرقمية لإمكانية استخدامها كأدلة قانونية',
        'حماية هوية المُبلِّغين والشهود وضمان سرية المعلومات',
        'تمكين التحقق المتبادل من المعلومات عبر مصادر متعددة',
        'بناء قاعدة بيانات شاملة تخدم جهود المحاسبة والعدالة الانتقالية',
        'دعم الأسر في البحث عن ذويهم المفقودين',
    ]
    for obj in objectives:
        story.append(Paragraph(ar(f'• {obj}'), styles['bullet']))

    story.append(Spacer(1, 12))
    story.append(info_box(
        'ملاحظة: يعمل هذا النظام بشكل كامل دون اتصال بالإنترنت (Offline-First) '
        'مما يضمن استمرارية العمل الميداني في المناطق ذات الاتصال المحدود، '
        'مع مزامنة البيانات تلقائياً عند توفر الاتصال.',
        styles['body'], color=HexColor('#eafaf1'), border_color=ACCENT
    ))

    story.append(PageBreak())

    # ════════════════════════ SECTION 2: LEGAL FRAMEWORK ════════════════════════
    story.append(Paragraph(ar('٢. الإطار القانوني والمرجعي'), styles['h1']))
    story.append(header_line())

    story.append(Paragraph(ar(
        'يستند هذا البروتوكول إلى مجموعة من المراجع القانونية والمنهجية الدولية:'
    ), styles['body']))
    story.append(Spacer(1, 8))

    refs = [
        ('بروتوكول بيركلي', 'دليل الأمم المتحدة للتحقيقات الرقمية في المصادر المفتوحة — يحدد معايير جمع وحفظ وتحليل الأدلة الرقمية'),
        ('الاتفاقية الدولية', 'الاتفاقية الدولية لحماية جميع الأشخاص من الاختفاء القسري (٢٠٠٦)'),
        ('نظام روما الأساسي', 'المحكمة الجنائية الدولية — الاختفاء القسري كجريمة ضد الإنسانية'),
        ('قرارات مجلس الأمن', 'القرارات الأممية المتعلقة بالوضع السوري والمحاسبة'),
    ]

    ref_data = [[
        Paragraph(ar('الوصف'), styles['table_header']),
        Paragraph(ar('المرجع'), styles['table_header']),
    ]]
    for title, desc in refs:
        ref_data.append([
            Paragraph(ar(desc), styles['table_cell_r']),
            Paragraph(ar(title), styles['table_cell']),
        ])

    ref_table = Table(ref_data, colWidths=[340, 120])
    ref_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('BACKGROUND', (0, 1), (-1, -1), LIGHTER_BG),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHTER_BG, white]),
    ]))
    story.append(ref_table)

    story.append(PageBreak())

    # ════════════════════════ SECTION 3: 7-STEP PROCESS ════════════════════════
    story.append(Paragraph(ar('٣. مراحل عملية التوثيق'), styles['h1']))
    story.append(header_line())

    story.append(Paragraph(ar(
        'تتكون عملية التوثيق من سبع مراحل متتابعة، كل مرحلة تجمع فئة محددة '
        'من البيانات وفق نموذج موحد. يضمن هذا التسلسل شمولية التوثيق وعدم إغفال أي معلومة جوهرية.'
    ), styles['body']))
    story.append(Spacer(1, 10))

    # Workflow diagram
    story.append(Paragraph(ar('مخطط سير العمل:'), styles['h3']))
    story.append(draw_workflow_diagram(460))
    story.append(Spacer(1, 10))

    story.append(PageBreak())

    # ── Step details ──
    step_details = [
        ('المرحلة ١: الحالة والمُبلِّغ', [
            ('تصنيف الحالة', 'تحديد وضع الشخص الموثَّق: ناجٍ، مغيّب قسراً، أو متوفى'),
            ('نوع الحالة الفرعي', 'تصنيف تفصيلي يتغير ديناميكياً بحسب تصنيف الحالة الرئيسي'),
            ('بيانات المُبلِّغ', 'الاسم الكامل، رقم الهاتف، الرقم الوطني، صلة القرابة بالضحية'),
            ('نوع المصدر', 'تصنيف مصدر المعلومات (عائلة، شاهد عيان، مصدر رقمي، إلخ)'),
            ('موافقة المُبلِّغ', 'الحصول على موافقة صريحة لاستخدام المعلومات'),
            ('تاريخ الجمع', 'تسجيل تاريخ جمع البيانات واسم الموظف الجامع — ضروري لسلسلة الحفظ'),
        ]),
        ('المرحلة ٢: البيانات الشخصية', [
            ('الهوية الكاملة', 'الاسم الأول، اسم الأب، الكنية، اسم الأم، اسم الجد'),
            ('البيانات الديموغرافية', 'تاريخ الميلاد الكامل، الجنس، المحافظة، مكان الولادة'),
            ('الوثائق الرسمية', 'الرقم الوطني (١١ رقم)، رقم القيد المدني'),
            ('معلومات إضافية', 'الكنية/اللقب، اسم الشهرة، فصيلة الدم، علامات مميزة'),
            ('صورة شخصية', 'إمكانية إرفاق صورة للتعرف البصري'),
        ]),
        ('المرحلة ٣: تفاصيل الاعتقال والاحتجاز', [
            ('ظروف الاعتقال', 'تاريخ الاعتقال، الجهة المعتقِلة (١٢ جهة أمنية معروفة)، سبب الاعتقال'),
            ('مكان الاحتجاز', 'مراكز الاحتجاز المعروفة (٢٣ مركز موثق) بما فيها صيدنايا والفروع الأمنية'),
            ('معلومات الإفراج/الوفاة', 'تاريخ الإفراج أو الوفاة، ظروف الوفاة، تاريخ آخر معلومة'),
            ('الأدلة الرقمية', 'نوع الدليل (قيصر، تسريبات، سجل مدني)، حالة السجل المدني'),
            ('مستوى الأدلة', 'تصنيف قوة الأدلة المتوفرة (عالي، متوسط، منخفض، غير متحقق)'),
            ('التعارض', 'تسجيل أي تعارض في المعلومات المتوفرة من مصادر مختلفة'),
        ]),
        ('المرحلة ٤: المرافقون', [
            ('بيانات المرافقين', 'أسماء الأشخاص الذين اعتُقلوا مع الضحية'),
            ('تفاصيل إضافية', 'صلة القرابة، ظروف الاعتقال المشترك، آخر معلومة'),
            ('أهمية التوثيق', 'التقاطع مع حالات أخرى يعزز مصداقية الشهادات'),
        ]),
        ('المرحلة ٥: الشهود', [
            ('بيانات الشهود', 'أسماء شهود العيان على الاعتقال أو الاحتجاز'),
            ('شهادات إضافية', 'تفاصيل الشهادة، مدى موثوقيتها، تاريخ الإدلاء بها'),
            ('حماية الشهود', 'إمكانية حجب هوية الشاهد مع الاحتفاظ بمرجع داخلي'),
        ]),
        ('المرحلة ٦: العائلة والعنوان والوضع الاجتماعي', [
            ('الوضع العائلي', 'الحالة الاجتماعية، اسم الزوج/ة، عدد الأطفال، أسماء الأطفال وأعمارهم'),
            ('العنوان', 'العنوان الحالي، المنطقة (٢١ حي معروف)، نوع السكن'),
            ('التعليم والمهنة', 'المستوى التعليمي، نوع التعليم، المهنة'),
            ('الوضع الصحي', 'الأمراض المزمنة (٢٢ مرض محدد)، الاحتياجات الخاصة'),
            ('المعيل', 'هل الضحية معيل العائلة، صلة المعيل البديل'),
        ]),
        ('المرحلة ٧: الملاحظات والحفظ', [
            ('الوضع القانوني', 'وجود محامٍ، تفاصيل القضية القانونية'),
            ('العلاقة الجمعوية', 'العضوية في الجمعية، الخدمات المطلوبة'),
            ('المنهجية', 'نوع المنهجية المستخدمة في جمع البيانات (٨ أنواع)'),
            ('علامات المنهجية', 'إضافة علامات وصفية (Tags) لتصنيف البيانات'),
            ('ملاحظات عامة', 'أي ملاحظات إضافية مهمة'),
            ('الحفظ', 'حفظ كمسودة أو إرسال للمراجعة'),
        ]),
    ]

    for step_title, fields in step_details:
        story.append(Paragraph(ar(step_title), styles['h2']))

        tbl_data = [[
            Paragraph(ar('الوصف'), styles['table_header']),
            Paragraph(ar('البند'), styles['table_header']),
        ]]
        for field_name, field_desc in fields:
            tbl_data.append([
                Paragraph(ar(field_desc), styles['table_cell_r']),
                Paragraph(ar(field_name), styles['table_cell']),
            ])

        tbl = Table(tbl_data, colWidths=[340, 120])
        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHTER_BG, white]),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 10))

    story.append(PageBreak())

    # ════════════════════════ SECTION 4: CASE CLASSIFICATION ════════════════════════
    story.append(Paragraph(ar('٤. تصنيف الحالات'), styles['h1']))
    story.append(header_line())

    story.append(Paragraph(ar(
        'يعتمد النظام تصنيفاً ثلاثياً رئيسياً للحالات، مع تصنيفات فرعية '
        'تتغير ديناميكياً بحسب التصنيف الرئيسي المختار:'
    ), styles['body']))
    story.append(Spacer(1, 10))

    story.append(Paragraph(ar('التصنيفات الرئيسية:'), styles['h3']))
    story.append(draw_status_diagram(460))
    story.append(Spacer(1, 14))

    story.append(Paragraph(ar('التصنيفات الفرعية:'), styles['h3']))
    case_types = [
        ('اختفاء قسري - لا معلومات', 'مغيّب قسراً', 'لا تتوفر أي معلومات بعد الاعتقال'),
        ('اختفاء قسري - تسريبات تؤكد الوفاة (مؤكد بالنفوس)', 'مغيّب / متوفى', 'تسريبات + تأكيد من السجل المدني'),
        ('اختفاء قسري - تسريبات تؤكد الوفاة (غير مؤكد)', 'مغيّب / متوفى', 'تسريبات بدون تأكيد رسمي'),
        ('اختفاء قسري - متوفى بحسب النفوس', 'مغيّب / متوفى', 'السجل المدني يسجل الوفاة فقط'),
        ('اختفاء قسري - شهود (حي بالنفوس)', 'مغيّب قسراً', 'شهادات شهود + حي في السجل المدني'),
        ('ناجٍ - لديه وثائق', 'ناجٍ', 'أُفرج عنه ويملك وثائق إثبات'),
        ('ناجٍ - بدون وثائق', 'ناجٍ', 'أُفرج عنه بدون وثائق'),
        ('متوفى - ملفات قيصر', 'متوفى', 'تم التعرف عليه من ملفات قيصر'),
    ]

    ct_data = [[
        Paragraph(ar('الوصف'), styles['table_header']),
        Paragraph(ar('التصنيف الرئيسي'), styles['table_header']),
        Paragraph(ar('النوع الفرعي'), styles['table_header']),
    ]]
    for subtype, main_type, desc in case_types:
        ct_data.append([
            Paragraph(ar(desc), styles['table_cell_r']),
            Paragraph(ar(main_type), styles['table_cell']),
            Paragraph(ar(subtype), styles['table_cell_r']),
        ])

    ct_table = Table(ct_data, colWidths=[180, 100, 180])
    ct_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHTER_BG, white]),
    ]))
    story.append(ct_table)

    story.append(PageBreak())

    # ════════════════════════ SECTION 5: EVIDENCE LEVELS ════════════════════════
    story.append(Paragraph(ar('٥. مستويات الأدلة والتحقق'), styles['h1']))
    story.append(header_line())

    story.append(Paragraph(ar(
        'يُصنّف كل دليل وفق أربعة مستويات تعكس درجة الموثوقية والتوثيق. '
        'هذا التصنيف ضروري لتقييم جودة المعلومات واتخاذ قرارات مبنية على الأدلة.'
    ), styles['body']))
    story.append(Spacer(1, 10))

    story.append(Paragraph(ar('مستويات قوة الأدلة:'), styles['h3']))
    story.append(draw_evidence_levels(460))
    story.append(Spacer(1, 16))

    # Evidence level details
    ev_details = [
        ('عالي', 'أدلة موثقة متعددة', 'وثائق رسمية + شهادات متطابقة + أدلة رقمية', ACCENT),
        ('متوسط', 'دليل واحد موثق', 'وثيقة واحدة أو شهادة موثقة مؤيدة', SECONDARY),
        ('منخفض', 'شهادة شفهية فقط', 'رواية شفهية واحدة بدون وثائق داعمة', WARN),
        ('غير متحقق', 'بدون تحقق بعد', 'معلومات أولية لم تخضع لأي عملية تحقق', DANGER),
    ]
    ev_data = [[
        Paragraph(ar('المعايير'), styles['table_header']),
        Paragraph(ar('الوصف'), styles['table_header']),
        Paragraph(ar('المستوى'), styles['table_header']),
    ]]
    for level, desc, criteria, _ in ev_details:
        ev_data.append([
            Paragraph(ar(criteria), styles['table_cell_r']),
            Paragraph(ar(desc), styles['table_cell']),
            Paragraph(ar(level), styles['table_cell']),
        ])
    ev_table = Table(ev_data, colWidths=[240, 120, 100])
    ev_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHTER_BG, white]),
    ]))
    story.append(ev_table)
    story.append(Spacer(1, 14))

    # Verification statuses
    story.append(Paragraph(ar('حالات التحقق:'), styles['h3']))
    ver_items = [
        ('تم التحقق (Verified)', 'تم التحقق من صحة المعلومات من مصادر مستقلة متعددة'),
        ('مؤيَّد بأدلة (Corroborated)', 'المعلومات مدعومة بأدلة جزئية أو مصدر إضافي واحد'),
        ('لم يُتحقق منه (Unverified)', 'المعلومات بانتظار عملية التحقق'),
        ('معلومات متضاربة (Conflicting)', 'توجد تناقضات بين المصادر المختلفة'),
    ]
    for title, desc in ver_items:
        story.append(Paragraph(ar(f'• {title}: {desc}'), styles['bullet']))
    story.append(Spacer(1, 10))

    # Digital evidence types
    story.append(Paragraph(ar('أنواع الأدلة الرقمية:'), styles['h3']))
    digital_types = [
        'ملفات قيصر — صور المعتقلين المُسرَّبة من النظام السوري',
        'تسريبات قاعدة بيانات — بيانات مُسرّبة من أجهزة أمنية',
        'وسائل التواصل الاجتماعي — منشورات أو رسائل ذات صلة',
        'تقارير إخبارية — تغطية صحفية موثقة',
        'تقارير منظمات — تقارير من منظمات حقوقية دولية أو محلية',
        'سجل مدني — بيانات من سجلات النفوس الرسمية',
        'وثائق رسمية — أوامر محاكم، كروت زيارة، أوراق إفراج',
    ]
    for dt in digital_types:
        story.append(Paragraph(ar(f'• {dt}'), styles['bullet']))

    story.append(PageBreak())

    # ════════════════════════ SECTION 6: METHODOLOGIES ════════════════════════
    story.append(Paragraph(ar('٦. منهجيات جمع البيانات'), styles['h1']))
    story.append(header_line())

    story.append(Paragraph(ar(
        'يعتمد البروتوكول على ثماني منهجيات أساسية لجمع البيانات والتحقق منها. '
        'يُسجَّل نوع المنهجية المستخدمة لكل حالة كجزء من سلسلة الحفظ:'
    ), styles['body']))
    story.append(Spacer(1, 10))

    meth_data = [[
        Paragraph(ar('التطبيق'), styles['table_header']),
        Paragraph(ar('الوصف'), styles['table_header']),
        Paragraph(ar('المنهجية'), styles['table_header']),
    ]]
    methodologies = [
        ('مقابلة شخصية', 'لقاء مباشر مع المُبلِّغ أو الشاهد', 'التوثيق الأولي في المكتب أو الميدان'),
        ('مقابلة عن بعد', 'اتصال هاتفي أو عبر الإنترنت', 'الحالات في مناطق يصعب الوصول إليها'),
        ('مراجعة وثائق', 'فحص وثائق رسمية أو مُسرّبة', 'التحقق من الهوية وتفاصيل الاعتقال'),
        ('تحقيق مصادر مفتوحة', 'بحث في مصادر رقمية عامة', 'تقاطع المعلومات مع البيانات المتاحة'),
        ('زيارة ميدانية', 'زيارة موقع الحدث أو العائلة', 'جمع أدلة مادية وشهادات محلية'),
        ('تقاطع قواعد بيانات', 'مقارنة مع قواعد بيانات أخرى', 'التحقق من تكرار الحالات وتطابقها'),
        ('شهادة شاهد', 'تسجيل شهادة شاهد عيان', 'توثيق الروايات المباشرة'),
        ('أخرى', 'منهجيات غير مصنفة', 'حالات خاصة تتطلب أسلوباً مختلفاً'),
    ]
    for meth, desc, usage in methodologies:
        meth_data.append([
            Paragraph(ar(usage), styles['table_cell_r']),
            Paragraph(ar(desc), styles['table_cell_r']),
            Paragraph(ar(meth), styles['table_cell']),
        ])
    meth_table = Table(meth_data, colWidths=[180, 160, 120])
    meth_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHTER_BG, white]),
    ]))
    story.append(meth_table)

    story.append(Spacer(1, 14))
    story.append(info_box(
        'يمكن إضافة علامات وصفية (Tags) متعددة لكل حالة لتسهيل البحث والتصنيف لاحقاً. '
        'تشمل العلامات: شاهد عيان، وثائق رسمية، صور، تسريبات، تقاطع بيانات، '
        'مقابلة ميدانية، مقابلة هاتفية، تقرير طبي، إعلام، سجلات حكومية، '
        'وسائل تواصل اجتماعي، أرشيف، وغيرها.',
        styles['body'], color=HexColor('#fef9e7'), border_color=WARN
    ))

    story.append(PageBreak())

    # ════════════════════════ SECTION 7: CHAIN OF CUSTODY ════════════════════════
    story.append(Paragraph(ar('٧. سلسلة الحفظ الرقمية'), styles['h1']))
    story.append(header_line())

    story.append(Paragraph(ar(
        'تُعد سلسلة الحفظ (Chain of Custody) من أهم متطلبات بروتوكول بيركلي. '
        'تضمن تتبع كل معلومة من لحظة جمعها حتى استخدامها كدليل، '
        'مما يحفظ قيمتها القانونية والتوثيقية.'
    ), styles['body']))
    story.append(Spacer(1, 10))

    story.append(Paragraph(ar('العناصر الأساسية لسلسلة الحفظ:'), styles['h3']))
    chain_items = [
        'اسم جامع البيانات (collector_name) — يُسجَّل تلقائياً من إعدادات النظام',
        'تاريخ الجمع (collection_date) — يُسجَّل تلقائياً عند إنشاء الحالة',
        'المعرّف الفريد (UUID) — رمز فريد عالمياً يُولَّد تلقائياً لكل حالة',
        'الطوابع الزمنية — تاريخ الإنشاء (createdAt) وتاريخ آخر تعديل (updatedAt)',
        'حالة المزامنة — تتبع حالة البيانات: مسودة، قيد المراجعة، مُراجَعة، مُتحقق منها، مقفلة',
        'المرفقات — كل صورة أو وثيقة مرفقة مرتبطة بحقل محدد مع بيانات وصفية',
    ]
    for item in chain_items:
        story.append(Paragraph(ar(f'• {item}'), styles['bullet']))

    story.append(Spacer(1, 14))

    story.append(Paragraph(ar('الحقول الإلزامية حسب مرحلة التحقق:'), styles['h3']))
    story.append(Spacer(1, 6))

    berk_data = [[
        Paragraph(ar('الحقول الإلزامية'), styles['table_header']),
        Paragraph(ar('المرحلة'), styles['table_header']),
    ]]
    berk_stages = [
        ('مُراجَعة (Reviewed)', 'الاسم، اسم الأب، الكنية، التصنيف، نوع المصدر، اسم الجامع، تاريخ الجمع'),
        ('مُتحقق منها (Verified)', 'جميع حقول المراجعة + مستوى الأدلة + حالة التحقق'),
        ('مقفلة (Locked)', 'جميع حقول التحقق — لا يمكن التعديل بعد القفل'),
    ]
    for stage, fields in berk_stages:
        berk_data.append([
            Paragraph(ar(fields), styles['table_cell_r']),
            Paragraph(ar(stage), styles['table_cell']),
        ])
    berk_table = Table(berk_data, colWidths=[340, 120])
    berk_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHTER_BG, white]),
    ]))
    story.append(berk_table)

    story.append(PageBreak())

    # ════════════════════════ SECTION 8: DATA SECURITY ════════════════════════
    story.append(Paragraph(ar('٨. إدارة البيانات والأمان'), styles['h1']))
    story.append(header_line())

    story.append(Paragraph(ar(
        'نظراً للطبيعة الحساسة للبيانات الموثقة، يتبع النظام إجراءات أمنية صارمة:'
    ), styles['body']))
    story.append(Spacer(1, 10))

    story.append(Paragraph(ar('التخزين المحلي (Offline-First):'), styles['h3']))
    offline_items = [
        'جميع البيانات تُخزَّن محلياً على جهاز المتطوع باستخدام قاعدة بيانات مشفرة',
        'لا تتطلب العملية اتصالاً بالإنترنت — يمكن التوثيق في أي مكان',
        'المزامنة تحدث تلقائياً عند توفر الاتصال مع الخادم المركزي',
        'في حالة فشل المزامنة، تُحتفظ البيانات محلياً ويُعاد المحاولة لاحقاً',
    ]
    for item in offline_items:
        story.append(Paragraph(ar(f'• {item}'), styles['bullet']))

    story.append(Spacer(1, 10))
    story.append(Paragraph(ar('المزامنة الآمنة:'), styles['h3']))
    sync_items = [
        'تستخدم المزامنة بروتوكول HTTPS المشفر',
        'المصادقة عبر اسم مستخدم وكلمة مرور مخزنة بشكل آمن',
        'يتم إرسال البيانات بصيغة Multipart Form Data مع المرفقات',
        'كل عملية مزامنة تُسجَّل بطابع زمني وحالة (نجاح/فشل)',
    ]
    for item in sync_items:
        story.append(Paragraph(ar(f'• {item}'), styles['bullet']))

    story.append(Spacer(1, 10))
    story.append(Paragraph(ar('حماية البيانات الشخصية:'), styles['h3']))
    privacy_items = [
        'الوصول محصور بالمتطوعين المعتمدين فقط',
        'لا تُشارك البيانات مع أطراف ثالثة دون موافقة',
        'إمكانية حذف البيانات المحلية عند الضرورة',
        'النسخ الاحتياطي المركزي محمي بإجراءات أمنية متقدمة',
    ]
    for item in privacy_items:
        story.append(Paragraph(ar(f'• {item}'), styles['bullet']))

    story.append(PageBreak())

    # ════════════════════════ SECTION 9: VERIFICATION WORKFLOW ════════════════════════
    story.append(Paragraph(ar('٩. مسار التحقق والمراجعة'), styles['h1']))
    story.append(header_line())

    story.append(Paragraph(ar(
        'تمر كل حالة موثقة بمسار تحقق متدرج يضمن جودة البيانات ومصداقيتها:'
    ), styles['body']))
    story.append(Spacer(1, 10))

    story.append(Paragraph(ar('مخطط مسار التحقق:'), styles['h3']))
    story.append(draw_verification_flow(460))
    story.append(Spacer(1, 14))

    stages_detail = [
        ('١. جمع البيانات (Draft)', [
            'يقوم المتطوع الميداني بجمع البيانات من المُبلِّغ',
            'تُملأ جميع الحقول المتاحة وفق النموذج الموحد',
            'تُحفظ الحالة كمسودة محلياً على الجهاز',
            'يمكن العودة لتعديل المسودة في أي وقت',
        ]),
        ('٢. المراجعة (Reviewed)', [
            'يراجع المشرف البيانات المُدخلة للتأكد من اكتمالها',
            'يتم التحقق من وجود جميع الحقول الإلزامية',
            'يُراجع اتساق المعلومات داخلياً',
            'تُعاد الحالة للمتطوع في حالة وجود نقص',
        ]),
        ('٣. التحقق (Verified)', [
            'يتم التحقق المتبادل من مصادر مستقلة',
            'يُقارن مع حالات مشابهة في قاعدة البيانات',
            'يُحدَّد مستوى الأدلة وحالة التحقق',
            'تُضاف ملاحظات التحقق والمنهجية المستخدمة',
        ]),
        ('٤. القفل (Locked)', [
            'تُقفل الحالة بعد اكتمال التحقق',
            'لا يمكن تعديل البيانات بعد القفل إلا بإذن خاص',
            'تُحفظ كسجل نهائي صالح للاستخدام القانوني',
            'تُرسل إلى الأرشيف المركزي',
        ]),
    ]

    for stage_title, items in stages_detail:
        story.append(Paragraph(ar(stage_title), styles['h2']))
        for item in items:
            story.append(Paragraph(ar(f'• {item}'), styles['bullet']))
        story.append(Spacer(1, 6))

    story.append(PageBreak())

    # ════════════════════════ SECTION 10: APPENDIX ════════════════════════
    story.append(Paragraph(ar('١٠. الملاحق'), styles['h1']))
    story.append(header_line())

    # Appendix A: Provinces
    story.append(Paragraph(ar('ملحق أ: المحافظات السورية المعتمدة'), styles['h2']))
    provinces = [
        'اللاذقية', 'دمشق', 'ريف دمشق', 'حلب', 'حمص', 'حماة',
        'إدلب', 'درعا', 'السويداء', 'القنيطرة', 'الرقة',
        'دير الزور', 'الحسكة', 'طرطوس', 'أخرى'
    ]
    prov_data = [[Paragraph(ar('المحافظة'), styles['table_header'])]]
    for p in provinces:
        prov_data.append([Paragraph(ar(p), styles['table_cell'])])
    prov_table = Table(prov_data, colWidths=[200])
    prov_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHTER_BG, white]),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(prov_table)
    story.append(Spacer(1, 14))

    # Appendix B: Arrest Authorities
    story.append(Paragraph(ar('ملحق ب: الجهات الأمنية المعتقِلة'), styles['h2']))
    authorities = [
        'الأمن العسكري', 'الأمن السياسي', 'أمن الدولة',
        'المخابرات الجوية', 'الدفاع الوطني', 'الشرطة العسكرية',
        'الأمن الجنائي', 'الجيش', 'حاجز أمني', 'دورية مشتركة',
        'غير معروف', 'أخرى'
    ]
    auth_data = [[Paragraph(ar('الجهة'), styles['table_header'])]]
    for a in authorities:
        auth_data.append([Paragraph(ar(a), styles['table_cell'])])
    auth_table = Table(auth_data, colWidths=[200])
    auth_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHTER_BG, white]),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(auth_table)
    story.append(Spacer(1, 14))

    # Appendix C: Detention Facilities
    story.append(Paragraph(ar('ملحق ج: مراكز الاحتجاز المعروفة'), styles['h2']))
    facilities = [
        'صيدنايا الامني (الاحمر)', 'صيدنايا القضائي (الابيض)',
        'فرع 215، بسرية المداهمة والاقتحام', 'فرع 216، فرع الدوريات',
        'فرع 227، فرع المنطقة', 'فرع 235 فرع فلسطين',
        'فرع 248، التحقيق العسكري', 'فرع 251، فرع الخطيب',
        'فرع 285، فرع التحقيق', 'فرع 293',
        'فرع 295، مكافحة الإرهاب',
        'فرع الأمن العسكري', 'فرع الأمن السياسي',
        'فرع أمن الدولة', 'فرع المخابرات الجوية',
        'السجن المدني', 'سجن تدمر', 'سجن عدرا',
        'سجن حمص المركزي', 'مطار المزة',
        'المدينة الرياضية', 'غير معروف', 'أخرى'
    ]
    fac_data = [[
        Paragraph(ar('المركز'), styles['table_header']),
        Paragraph(ar('#'), styles['table_header']),
    ]]
    for i, f in enumerate(facilities, 1):
        fac_data.append([
            Paragraph(ar(f), styles['table_cell_r']),
            Paragraph(str(i), styles['table_cell']),
        ])
    fac_table = Table(fac_data, colWidths=[380, 40])
    fac_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHTER_BG, white]),
    ]))
    story.append(fac_table)

    story.append(PageBreak())

    # ════════════════════════ CLOSING ════════════════════════
    story.append(Spacer(1, 3 * cm))
    story.append(HRFlowable(width="80%", thickness=2, color=PRIMARY,
                            spaceAfter=20, spaceBefore=10, hAlign='CENTER'))

    story.append(Paragraph(ar('جمعية حقنا'), styles['title']))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(ar('نحو عدالة انتقالية شاملة وتوثيق يحفظ الحقوق'), styles['subtitle']))
    story.append(Spacer(1, 1 * cm))

    story.append(info_box(
        'هذه الوثيقة سرية ومخصصة للاستخدام الداخلي لمتطوعي جمعية حقنا فقط. '
        'يُمنع نسخها أو توزيعها دون إذن مسبق.',
        styles['body_center'], color=HexColor('#fdedec'), border_color=DANGER
    ))

    story.append(Spacer(1, 1.5 * cm))
    story.append(Paragraph(ar('تم تطوير هذا النظام بشكل خاص لمتطوعي جمعية حقنا'), styles['body_center']))
    story.append(Paragraph(ar('من قبل: مهند حسون'), styles['body_center']))
    story.append(Paragraph('bugmuha@gmail.com', styles['body_center']))

    # ── Page numbers ──
    def add_page_number(canvas, doc):
        page_num = canvas.getPageNumber()
        canvas.saveState()
        canvas.setFont('Amiri', 9)
        canvas.setFillColor(MEDIUM_TEXT)
        text = ar(f'جمعية حقنا — بروتوكول التوثيق — صفحة {page_num}')
        canvas.drawCentredString(page_w / 2, 1.2 * cm, text)
        canvas.restoreState()

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    print(f'PDF generated: {output_path}')


if __name__ == '__main__':
    output = '/home/user/dd/haqquna_protocol_ar.pdf'
    build_pdf(output)
