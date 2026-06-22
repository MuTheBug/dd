#!/usr/bin/env python3
"""
Generate a comprehensive Arabic PDF describing the Haqquna documentation protocols.
Includes EVERY form field and EVERY selectable option.
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

pdfmetrics.registerFont(TTFont('Amiri', '/tmp/fonts/Amiri-Regular.ttf'))
pdfmetrics.registerFont(TTFont('AmiriBold', '/tmp/fonts/Amiri-Bold.ttf'))
pdfmetrics.registerFontFamily('Amiri', normal='Amiri', bold='AmiriBold')

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
PURPLE = HexColor('#8e44ad')

def ar(text):
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)

def make_styles():
    s = {}
    s['title'] = ParagraphStyle('Title', fontName='AmiriBold', fontSize=28,
        leading=40, alignment=TA_CENTER, textColor=PRIMARY, wordWrap='RTL')
    s['subtitle'] = ParagraphStyle('Subtitle', fontName='Amiri', fontSize=16,
        leading=24, alignment=TA_CENTER, textColor=SECONDARY, wordWrap='RTL')
    s['h1'] = ParagraphStyle('H1', fontName='AmiriBold', fontSize=20,
        leading=30, alignment=TA_RIGHT, textColor=PRIMARY, spaceBefore=20,
        spaceAfter=10, wordWrap='RTL')
    s['h2'] = ParagraphStyle('H2', fontName='AmiriBold', fontSize=15,
        leading=23, alignment=TA_RIGHT, textColor=SECONDARY, spaceBefore=14,
        spaceAfter=8, wordWrap='RTL')
    s['h3'] = ParagraphStyle('H3', fontName='AmiriBold', fontSize=12,
        leading=19, alignment=TA_RIGHT, textColor=DARK_TEXT, spaceBefore=10,
        spaceAfter=6, wordWrap='RTL')
    s['body'] = ParagraphStyle('Body', fontName='Amiri', fontSize=11,
        leading=18, alignment=TA_RIGHT, textColor=DARK_TEXT, wordWrap='RTL')
    s['body_center'] = ParagraphStyle('BodyCenter', fontName='Amiri', fontSize=11,
        leading=18, alignment=TA_CENTER, textColor=DARK_TEXT, wordWrap='RTL')
    s['bullet'] = ParagraphStyle('Bullet', fontName='Amiri', fontSize=10,
        leading=16, alignment=TA_RIGHT, textColor=DARK_TEXT, leftIndent=15,
        wordWrap='RTL')
    s['small'] = ParagraphStyle('Small', fontName='Amiri', fontSize=9,
        leading=14, alignment=TA_RIGHT, textColor=MEDIUM_TEXT, wordWrap='RTL')
    s['small_center'] = ParagraphStyle('SmallCenter', fontName='Amiri', fontSize=9,
        leading=14, alignment=TA_CENTER, textColor=MEDIUM_TEXT, wordWrap='RTL')
    s['th'] = ParagraphStyle('TH', fontName='AmiriBold', fontSize=9,
        leading=14, alignment=TA_CENTER, textColor=white, wordWrap='RTL')
    s['tc'] = ParagraphStyle('TC', fontName='Amiri', fontSize=9,
        leading=13, alignment=TA_CENTER, textColor=DARK_TEXT, wordWrap='RTL')
    s['tcr'] = ParagraphStyle('TCR', fontName='Amiri', fontSize=9,
        leading=13, alignment=TA_RIGHT, textColor=DARK_TEXT, wordWrap='RTL')
    s['tc_small'] = ParagraphStyle('TCSmall', fontName='Amiri', fontSize=8,
        leading=12, alignment=TA_CENTER, textColor=DARK_TEXT, wordWrap='RTL')
    s['tc_opt'] = ParagraphStyle('TCOpt', fontName='Amiri', fontSize=8,
        leading=11, alignment=TA_RIGHT, textColor=MEDIUM_TEXT, wordWrap='RTL')
    s['footer'] = ParagraphStyle('Footer', fontName='Amiri', fontSize=9,
        leading=14, alignment=TA_CENTER, textColor=MEDIUM_TEXT, wordWrap='RTL')
    return s


def draw_workflow_diagram(width):
    h = 420
    d = Drawing(width, h)
    steps = [
        ('\xd9\xa1', ar('الحالة والمُبلِّغ'), PRIMARY),
        ('\xd9\xa2', ar('البيانات الشخصية'), SECONDARY),
        ('\xd9\xa3', ar('الاعتقال والاحتجاز'), PURPLE),
        ('\xd9\xa4', ar('الأدلة والتحقق'), WARN),
        ('\xd9\xa5', ar('العائلة والاجتماعي'), ACCENT),
        ('\xd9\xa6', ar('السكن والصحة'), HexColor('#e74c3c')),
        ('\xd9\xa7', ar('القانوني والحفظ'), HexColor('#2c3e50')),
    ]
    box_w = 140
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
    h = 90
    d = Drawing(width, h)
    levels = [
        (ar('عالي'), ACCENT),
        (ar('متوسط'), SECONDARY),
        (ar('منخفض'), WARN),
        (ar('غير متحقق'), DANGER),
    ]
    block_w = width / 4 - 8
    y = 10
    for i, (title, color) in enumerate(levels):
        x = width - (i + 1) * (block_w + 6)
        d.add(Rect(x, y, block_w, 60, fillColor=color, strokeColor=None, rx=6, ry=6))
        d.add(String(x + block_w / 2, y + 30, title,
                     fontName='AmiriBold', fontSize=14, fillColor=white,
                     textAnchor='middle'))
    return d


def draw_status_diagram(width):
    h = 80
    d = Drawing(width, h)
    statuses = [
        (ar('ناجٍ'), ACCENT),
        (ar('مغيّب قسراً'), WARN),
        (ar('متوفى'), DANGER),
    ]
    spacing = width / 3
    for i, (title, color) in enumerate(statuses):
        cx = width - spacing * i - spacing / 2
        d.add(Circle(cx, 48, 22, fillColor=color, strokeColor=None))
        d.add(String(cx, 43, title, fontName='AmiriBold', fontSize=11,
                     fillColor=white, textAnchor='middle'))
    return d


def draw_verification_flow(width):
    h = 60
    d = Drawing(width, h)
    stages = [
        (ar('جمع'), HexColor('#3498db')),
        (ar('مراجعة'), WARN),
        (ar('تحقق'), PURPLE),
        (ar('قفل'), ACCENT),
    ]
    box_w = 90
    total_w = len(stages) * box_w + (len(stages) - 1) * 30
    start_x = (width - total_w) / 2 + total_w
    for i, (label, color) in enumerate(stages):
        x = start_x - (i + 1) * (box_w + 30) + 30
        d.add(Rect(x, 15, box_w, 35, fillColor=color, strokeColor=None, rx=6, ry=6))
        d.add(String(x + box_w / 2, 28, label,
                     fontName='AmiriBold', fontSize=13, fillColor=white,
                     textAnchor='middle'))
        if i < len(stages) - 1:
            d.add(Line(x - 2, 32, x - 28, 32, strokeColor=BORDER, strokeWidth=2))
            ax = x - 15
            d.add(Polygon(points=[ax - 6, 37, ax - 6, 27, ax - 14, 32],
                          fillColor=BORDER, strokeColor=None))
    return d


def info_box(text, style, color=LIGHT_BG, border_color=SECONDARY):
    tbl = Table([[Paragraph(ar(text), style)]], colWidths=[440])
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), color),
        ('BOX', (0, 0), (-1, -1), 1.5, border_color),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return tbl


def header_line():
    return HRFlowable(width="100%", thickness=1.5, color=SECONDARY,
                      spaceAfter=8, spaceBefore=4)


def field_table(styles, fields, col_widths=None):
    """Create a field details table.
    fields: list of (field_name, field_type, required, options_text)
    """
    if col_widths is None:
        col_widths = [200, 70, 35, 155]

    data = [[
        Paragraph(ar('الخيارات المتاحة'), styles['th']),
        Paragraph(ar('النوع'), styles['th']),
        Paragraph(ar('إلزامي'), styles['th']),
        Paragraph(ar('اسم الحقل'), styles['th']),
    ]]
    for name, ftype, req, opts in fields:
        req_txt = ar('نعم') if req else ''
        data.append([
            Paragraph(ar(opts) if opts else '', styles['tc_opt']),
            Paragraph(ar(ftype), styles['tc_small']),
            Paragraph(req_txt, styles['tc']),
            Paragraph(ar(name), styles['tcr']),
        ])

    tbl = Table(data, colWidths=col_widths)
    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHTER_BG, white]),
    ]
    # Highlight required fields
    for i, (_, _, req, _) in enumerate(fields, 1):
        if req:
            style_cmds.append(('BACKGROUND', (1, i), (1, i), HexColor('#fdecea')))
    tbl.setStyle(TableStyle(style_cmds))
    return tbl


def options_table(styles, title, options, ncols=3):
    """Create a compact options list table."""
    rows = []
    row = []
    for opt in options:
        row.append(Paragraph(ar(opt), styles['tc']))
        if len(row) == ncols:
            rows.append(row)
            row = []
    if row:
        while len(row) < ncols:
            row.append(Paragraph('', styles['tc']))
        rows.append(row)

    col_w = 460 // ncols
    tbl = Table(rows, colWidths=[col_w] * ncols)
    tbl.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [LIGHTER_BG, white]),
    ]))
    return tbl


def build_pdf(output_path):
    styles = make_styles()
    page_w, page_h = A4

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        rightMargin=1.8 * cm, leftMargin=1.8 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm
    )

    story = []

    # ════════════════════════ COVER PAGE ════════════════════════
    story.append(Spacer(1, 2 * cm))
    logo_path = '/home/user/dd/logo.jpg'
    if os.path.exists(logo_path):
        story.append(Image(logo_path, width=4 * cm, height=4 * cm, hAlign='CENTER'))
        story.append(Spacer(1, 0.8 * cm))

    story.append(Paragraph(ar('جمعية حقنا'), styles['title']))
    story.append(Spacer(1, 0.3 * cm))
    story.append(HRFlowable(width="60%", thickness=3, color=PRIMARY,
                            spaceAfter=10, spaceBefore=4, hAlign='CENTER'))
    story.append(Paragraph(ar('بروتوكول التوثيق الشامل'), styles['title']))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(ar('دليل إجراءات توثيق حالات الاختفاء القسري والاعتقال'), styles['subtitle']))
    story.append(Paragraph(ar('مع جميع الحقول والخيارات المتاحة'), styles['subtitle']))
    story.append(Spacer(1, 0.6 * cm))

    story.append(info_box(
        'وفقاً لبروتوكول بيركلي للتحقيقات الرقمية في المصادر المفتوحة — الأمم المتحدة',
        styles['body_center'], color=HexColor('#f0f4f8'), border_color=PRIMARY
    ))

    story.append(Spacer(1, 2 * cm))
    story.append(Paragraph(ar('الإصدار ٢.٠ — ٢٠٢٥'), styles['body_center']))
    story.append(Paragraph(ar('وثيقة سرية — للاستخدام الداخلي فقط'), styles['small_center']))
    story.append(PageBreak())

    # ════════════════════════ TABLE OF CONTENTS ════════════════════════
    story.append(Paragraph(ar('فهرس المحتويات'), styles['h1']))
    story.append(header_line())

    toc = [
        ('١', 'المقدمة وأهداف البروتوكول'),
        ('٢', 'مخطط سير عملية التوثيق'),
        ('٣', 'الخطوة ١ — الحالة والمُبلِّغ (جميع الحقول والخيارات)'),
        ('٤', 'الخطوة ٢ — البيانات الشخصية (جميع الحقول والخيارات)'),
        ('٥', 'الخطوة ٣ — تفاصيل الاعتقال والاحتجاز (جميع الحقول والخيارات)'),
        ('٦', 'الخطوة ٤ — الأدلة والتحقق (جميع الحقول والخيارات)'),
        ('٧', 'الخطوة ٥ — العائلة والبيانات الاجتماعية (جميع الحقول والخيارات)'),
        ('٨', 'الخطوة ٦ — السكن والتعليم والصحة (جميع الحقول والخيارات)'),
        ('٩', 'الخطوة ٧ — القانوني والملاحظات والحفظ (جميع الحقول والخيارات)'),
        ('١٠', 'تصنيف الحالات والأنواع الفرعية'),
        ('١١', 'مستويات الأدلة وحالات التحقق'),
        ('١٢', 'سلسلة الحفظ الرقمية ومسار المراجعة'),
        ('١٣', 'الملاحق: المحافظات، الجهات الأمنية، مراكز الاحتجاز'),
    ]
    for num, title in toc:
        story.append(Paragraph(ar(f'{title} ......... {num}'), styles['body']))
    story.append(PageBreak())

    # ════════════════════════ SECTION 1: INTRO ════════════════════════
    story.append(Paragraph(ar('١. المقدمة وأهداف البروتوكول'), styles['h1']))
    story.append(header_line())
    story.append(Paragraph(ar(
        'يُحدد هذا البروتوكول الإجراءات المعتمدة لتوثيق حالات الاختفاء القسري والاعتقال التعسفي '
        'في سوريا. تم تصميمه ليتوافق مع المعايير الدولية لحقوق الإنسان وبروتوكول بيركلي '
        'للتحقيقات الرقمية في المصادر المفتوحة الصادر عن مكتب الأمم المتحدة لحقوق الإنسان.'
    ), styles['body']))
    story.append(Spacer(1, 6))

    story.append(Paragraph(ar('الأهداف الرئيسية:'), styles['h3']))
    for obj in [
        'توثيق منهجي ودقيق لكل حالة وفق معايير موحدة',
        'ضمان سلامة البيانات وسلسلة الحفظ الرقمية لإمكانية استخدامها كأدلة قانونية',
        'حماية هوية المُبلِّغين والشهود وضمان سرية المعلومات',
        'تمكين التحقق المتبادل من المعلومات عبر مصادر متعددة',
        'بناء قاعدة بيانات شاملة تخدم جهود المحاسبة والعدالة الانتقالية',
        'دعم الأسر في البحث عن ذويهم المفقودين',
    ]:
        story.append(Paragraph(ar(f'• {obj}'), styles['bullet']))

    story.append(Spacer(1, 8))
    story.append(info_box(
        'يعمل النظام بشكل كامل دون اتصال بالإنترنت (Offline-First) مع مزامنة تلقائية عند توفر الاتصال.',
        styles['body_center'], color=HexColor('#eafaf1'), border_color=ACCENT
    ))

    story.append(Spacer(1, 8))
    story.append(Paragraph(ar('إحصائيات النموذج:'), styles['h3']))
    stats = [
        'إجمالي الخطوات: ٧ خطوات متتابعة',
        'إجمالي الحقول: أكثر من ١٢٠ حقل (بما فيها الأقسام الديناميكية)',
        'الحقول الإلزامية: ١٤ حقل أساسي',
        'حقول القوائم المنسدلة: أكثر من ٣٥ قائمة',
        'حقول رفع الملفات: ١٠ حقول',
        'حقول التاريخ: أكثر من ١٥ حقل',
    ]
    for s in stats:
        story.append(Paragraph(ar(f'• {s}'), styles['bullet']))
    story.append(PageBreak())

    # ════════════════════════ SECTION 2: WORKFLOW ════════════════════════
    story.append(Paragraph(ar('٢. مخطط سير عملية التوثيق'), styles['h1']))
    story.append(header_line())
    story.append(Paragraph(ar(
        'تتكون عملية التوثيق من سبع خطوات متتابعة. كل خطوة تجمع فئة محددة من البيانات.'
    ), styles['body']))
    story.append(Spacer(1, 6))
    story.append(draw_workflow_diagram(460))
    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # STEP 1: REPORTER & CLASSIFICATION
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph(ar('٣. الخطوة ١ — الحالة والمُبلِّغ'), styles['h1']))
    story.append(header_line())
    story.append(Paragraph(ar('تحديد تصنيف الحالة وبيانات الشخص المُبلِّغ ومصدر المعلومات.'), styles['body']))
    story.append(Spacer(1, 6))

    step1_fields = [
        ('تصنيف الحالة (status)', 'قائمة منسدلة', True,
         'ناجٍ (شخص أُفرج عنه / هرب) | مغيّب قسراً (لا يُعرف مصيره) | متوفى (مؤكد الوفاة)'),
        ('نوع الحالة التفصيلي (case_type)', 'قائمة ديناميكية', False,
         'يتغير بحسب التصنيف — انظر قسم ١٠'),
        ('اسم المُبلِّغ (reporter_name)', 'نص حر', True, 'الاسم الكامل للمُبلِّغ'),
        ('صلة المُبلِّغ بالضحية (reporter_relation)', 'قائمة منسدلة', True,
         'أم | أب | أخ | أخت | زوج/ة | ابن/ة | قريب | صديق | جار | زميل | الشخص نفسه | أخرى'),
        ('هاتف المُبلِّغ (reporter_phone)', 'رقم هاتف', False, ''),
        ('رقم هوية المُبلِّغ (reporter_id)', 'نص حر', False, 'الرقم الوطني'),
        ('اسم جامع البيانات (collector_name)', 'نص مع قائمة مقترحة', False,
         'اسم الموظف/المتطوع — مهم لسلسلة الحفظ'),
        ('تاريخ جمع البيانات (collection_date)', 'تاريخ', False,
         'يُملأ تلقائياً بتاريخ اليوم'),
        ('نوع المصدر (source_type)', 'قائمة منسدلة', True,
         'مقابلة مباشرة | مقابلة هاتفية | وثائق رسمية | مصادر مفتوحة (إنترنت/إعلام) | شهادة شاهد | تسريبات | إحالة من منظمة/جهة أخرى | أخرى'),
        ('موافقة المُبلِّغ (informant_consent)', 'مربع تحقق', False,
         'الموافقة الواعية على جمع المعلومات وفق بروتوكول بيركلي'),
    ]
    story.append(field_table(styles, step1_fields))

    story.append(Spacer(1, 8))
    story.append(Paragraph(ar('تفصيل خيارات صلة المُبلِّغ (١٢ خيار):'), styles['h3']))
    story.append(options_table(styles, '', [
        'أم', 'أب', 'أخ', 'أخت', 'زوج/ة', 'ابن/ة',
        'قريب', 'صديق', 'جار', 'زميل', 'الشخص نفسه', 'أخرى'
    ], ncols=4))

    story.append(Spacer(1, 8))
    story.append(Paragraph(ar('تفصيل خيارات نوع المصدر (٨ خيارات):'), styles['h3']))
    story.append(options_table(styles, '', [
        'مقابلة مباشرة', 'مقابلة هاتفية', 'وثائق رسمية',
        'مصادر مفتوحة (إنترنت / إعلام)', 'شهادة شاهد', 'تسريبات',
        'إحالة من منظمة / جهة أخرى', 'أخرى'
    ], ncols=2))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # STEP 2: PERSONAL DATA
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph(ar('٤. الخطوة ٢ — البيانات الشخصية'), styles['h1']))
    story.append(header_line())
    story.append(Paragraph(ar('البيانات الشخصية الأساسية للضحية والمرفقات.'), styles['body']))
    story.append(Spacer(1, 6))

    step2_fields = [
        ('الاسم الأول (first_name)', 'نص حر', True, ''),
        ('اسم الأب (father_name)', 'نص حر', True, ''),
        ('الكنية / اسم العائلة (last_name)', 'نص حر', True, ''),
        ('اسم الأم (mother_name)', 'نص حر', True, ''),
        ('الجنس (gender)', 'قائمة منسدلة', True,
         'ذكر (male) | أنثى (female)'),
        ('تاريخ الميلاد — اليوم (birth_day)', 'رقم', False, '١ إلى ٣١'),
        ('تاريخ الميلاد — الشهر (birth_month)', 'رقم', False, '١ إلى ١٢'),
        ('تاريخ الميلاد — السنة (birth_year)', 'رقم', False, '١٩٠٠ إلى ٢٠٢٦'),
        ('المحافظة (province)', 'قائمة منسدلة', True,
         '١٥ محافظة — انظر التفصيل أدناه'),
        ('الرقم الوطني (national_id)', 'نص حر', True, '١١ رقم'),
        ('رقم دفتر العائلة (family_book_number)', 'نص حر', False, ''),
        ('رقم الهاتف (phone)', 'رقم هاتف', False, 'للناجين فقط'),
        ('زمرة الدم (blood_type)', 'قائمة منسدلة', False,
         'A+ | A- | B+ | B- | AB+ | AB- | O+ | O-'),
        ('صورة شخصية (photo)', 'رفع ملف', False, 'JPG, PNG — حتى 15MB'),
        ('وثيقة هوية (document)', 'رفع ملف', False, 'JPG, PNG, PDF — حتى 15MB'),
    ]
    story.append(field_table(styles, step2_fields))

    story.append(Spacer(1, 8))
    story.append(Paragraph(ar('خيارات المحافظات (١٥ محافظة):'), styles['h3']))
    story.append(options_table(styles, '', [
        'اللاذقية', 'دمشق', 'ريف دمشق', 'حلب', 'حمص', 'حماة',
        'إدلب', 'درعا', 'السويداء', 'القنيطرة', 'الرقة',
        'دير الزور', 'الحسكة', 'طرطوس', 'أخرى'
    ], ncols=5))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('خيارات زمرة الدم (٨ خيارات):'), styles['h3']))
    story.append(options_table(styles, '', [
        'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'
    ], ncols=4))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # STEP 3: ARREST & DETENTION
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph(ar('٥. الخطوة ٣ — تفاصيل الاعتقال والاحتجاز'), styles['h1']))
    story.append(header_line())
    story.append(Paragraph(ar(
        'تفاصيل الاعتقال والاحتجاز والإفراج/الوفاة، بالإضافة إلى المرافقين.'
    ), styles['body']))
    story.append(Spacer(1, 6))

    story.append(Paragraph(ar('حقول الاعتقال الأساسية:'), styles['h2']))
    step3_main = [
        ('تاريخ الاعتقال — اليوم (arrest_day)', 'رقم', False, '١ إلى ٣١'),
        ('تاريخ الاعتقال — الشهر (arrest_month)', 'رقم', False, '١ إلى ١٢'),
        ('تاريخ الاعتقال — السنة (arrest_year)', 'رقم', False, '٢٠٠٠ إلى ٢٠٢٦'),
        ('الجهة المعتقِلة (arrest_authority)', 'قائمة منسدلة', True,
         '١٢ جهة — انظر التفصيل أدناه'),
        ('مكان الاحتجاز (arrest_place)', 'قائمة منسدلة', False,
         '٢٣ مركز — انظر التفصيل أدناه'),
        ('سبب الاعتقال (arrest_reason)', 'نص حر', True,
         'مثال: مظاهرة، تقرير كيدي، حاجز...'),
        ('المتسبب بالاعتقال (arrest_causer)', 'نص حر', False, 'اسم الشخص أو الجهة'),
        ('آخر مكان معروف (last_known_location)', 'نص حر', False, ''),
        ('آخر تاريخ عُرف أنه حي (last_known_alive_date)', 'تاريخ', False, ''),
    ]
    story.append(field_table(styles, step3_main))

    story.append(Spacer(1, 8))
    story.append(Paragraph(ar('خيارات الجهة المعتقِلة (١٢ جهة):'), styles['h3']))
    story.append(options_table(styles, '', [
        'الأمن العسكري', 'الأمن السياسي', 'أمن الدولة',
        'المخابرات الجوية', 'الدفاع الوطني', 'الشرطة العسكرية',
        'الأمن الجنائي', 'الجيش', 'حاجز أمني',
        'دورية مشتركة', 'غير معروف', 'أخرى'
    ], ncols=3))

    story.append(Spacer(1, 8))
    story.append(Paragraph(ar('خيارات مراكز الاحتجاز (٢٣ مركز):'), styles['h3']))
    story.append(options_table(styles, '', [
        'صيدنايا الامني (الاحمر)', 'صيدنايا القضائي (الابيض)',
        'فرع 215، بسرية المداهمة والاقتحام', 'فرع 216، فرع الدوريات',
        'فرع 227، فرع المنطقة', 'فرع 235 فرع فلسطين',
        'فرع 248، التحقيق العسكري', 'فرع 251، فرع الخطيب',
        'فرع 285، فرع التحقيق', 'فرع 293',
        'فرع 295، مكافحة الإرهاب', 'فرع الأمن العسكري',
        'فرع الأمن السياسي', 'فرع أمن الدولة',
        'فرع المخابرات الجوية', 'السجن المدني',
        'سجن تدمر', 'سجن عدرا',
        'سجن حمص المركزي', 'مطار المزة',
        'المدينة الرياضية', 'غير معروف', 'أخرى'
    ], ncols=2))

    story.append(PageBreak())

    # Survivor-only fields
    story.append(Paragraph(ar('حقول خاصة بالناجين (تظهر عند اختيار "ناجٍ"):'), styles['h2']))
    step3_survivor = [
        ('تاريخ الإفراج — اليوم (release_day)', 'رقم', False, '١ إلى ٣١'),
        ('تاريخ الإفراج — الشهر (release_month)', 'رقم', False, '١ إلى ١٢'),
        ('تاريخ الإفراج — السنة (release_year)', 'رقم', False, '٢٠٠٠ إلى ٢٠٢٦'),
        ('ملخص التجربة / السيرة الذاتية (survivor_cv)', 'رفع ملف', False, 'صورة أو PDF — حتى 15MB'),
        ('صورة بعد الإفراج (survivor_cv_photo)', 'رفع ملف', False, 'صورة — حتى 15MB'),
        ('وصف تجربة الاعتقال (survivor_cv_text)', 'نص طويل', False, 'وصف مختصر لتجربة الاعتقال والاحتجاز'),
    ]
    story.append(field_table(styles, step3_survivor))

    story.append(Spacer(1, 8))
    # Deceased-only fields
    story.append(Paragraph(ar('حقول خاصة بالمتوفين (تظهر عند اختيار "متوفى"):'), styles['h2']))
    step3_deceased = [
        ('تاريخ الوفاة — اليوم (death_day)', 'رقم', False, '١ إلى ٣١'),
        ('تاريخ الوفاة — الشهر (death_month)', 'رقم', False, '١ إلى ١٢'),
        ('تاريخ الوفاة — السنة (death_year)', 'رقم', False, '٢٠٠٠ إلى ٢٠٢٦'),
        ('مكان الوفاة (death_place)', 'نص حر', False, ''),
    ]
    story.append(field_table(styles, step3_deceased))

    story.append(Spacer(1, 8))
    # Companions
    story.append(Paragraph(ar('المرافقون (قسم ديناميكي — يمكن إضافة عدد غير محدود):'), styles['h2']))
    step3_comp = [
        ('الاسم الأول للمرافق (comp_first_N)', 'نص حر', False, ''),
        ('اسم أب المرافق (comp_father_N)', 'نص حر', False, ''),
        ('كنية المرافق (comp_last_N)', 'نص حر', False, ''),
        ('اسم أم المرافق (comp_mother_N)', 'نص حر', False, ''),
        ('ملاحظة عن المرافق (comp_notes_N)', 'نص حر', False, 'مثال: كان معه في نفس الزنزانة'),
    ]
    story.append(field_table(styles, step3_comp))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # STEP 4: EVIDENCE & VERIFICATION
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph(ar('٦. الخطوة ٤ — الأدلة والتحقق'), styles['h1']))
    story.append(header_line())
    story.append(Paragraph(ar(
        'توثيق الأدلة الرقمية والتحقق منها وفق بروتوكول بيركلي.'
    ), styles['body']))
    story.append(Spacer(1, 6))

    story.append(Paragraph(ar('الأدلة الرقمية الأساسية:'), styles['h2']))
    step4_main = [
        ('نوع الدليل الرقمي (digital_evidence_type)', 'قائمة منسدلة', False,
         '٨ أنواع — انظر التفصيل أدناه'),
        ('مستوى الأدلة (evidence_level)', 'قائمة منسدلة', False,
         'عالي | متوسط | منخفض | غير مُتحقق منه'),
        ('عدد مصادر الأدلة (evidence_sources_count)', 'رقم', False, 'عدد'),
    ]
    story.append(field_table(styles, step4_main))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('خيارات نوع الدليل الرقمي (٨ أنواع):'), styles['h3']))
    de_data = [[
        Paragraph(ar('الوصف'), styles['th']),
        Paragraph(ar('الرمز'), styles['th']),
        Paragraph(ar('النوع'), styles['th']),
    ]]
    de_types = [
        ('ملفات قيصر', 'caesar_files', 'صور المعتقلين المُسرَّبة من النظام'),
        ('تسريبات قاعدة بيانات', 'leaked_database', 'بيانات مُسرّبة من أجهزة أمنية'),
        ('وسائل التواصل الاجتماعي', 'social_media', 'منشورات أو رسائل ذات صلة'),
        ('تقرير إخباري', 'news_report', 'تغطية صحفية موثقة'),
        ('تقرير منظمة', 'ngo_report', 'تقارير من منظمات حقوقية'),
        ('سجل مدني', 'civil_registry', 'بيانات من سجلات النفوس'),
        ('وثيقة رسمية', 'official_document', 'أوامر محاكم، كروت زيارة'),
        ('أخرى', 'other', 'أي نوع آخر غير مصنف'),
    ]
    for name, code, desc in de_types:
        de_data.append([
            Paragraph(ar(desc), styles['tcr']),
            Paragraph(code, styles['tc']),
            Paragraph(ar(name), styles['tc']),
        ])
    de_tbl = Table(de_data, colWidths=[230, 100, 130])
    de_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHTER_BG, white]),
    ]))
    story.append(de_tbl)

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('خيارات مستوى الأدلة (٤ مستويات):'), styles['h3']))
    el_data = [[
        Paragraph(ar('المعايير'), styles['th']),
        Paragraph(ar('الرمز'), styles['th']),
        Paragraph(ar('المستوى'), styles['th']),
    ]]
    for name, code, criteria in [
        ('عالي - أدلة موثقة متعددة', 'high', 'وثائق رسمية + شهادات متطابقة + أدلة رقمية'),
        ('متوسط - دليل واحد موثق', 'medium', 'وثيقة واحدة أو شهادة مؤيدة'),
        ('منخفض - شهادة شفهية فقط', 'low', 'رواية شفهية واحدة بدون وثائق'),
        ('غير مُتحقق منه', 'unverified', 'معلومات أولية لم تخضع لتحقق'),
    ]:
        el_data.append([
            Paragraph(ar(criteria), styles['tcr']),
            Paragraph(code, styles['tc']),
            Paragraph(ar(name), styles['tc']),
        ])
    el_tbl = Table(el_data, colWidths=[210, 80, 170])
    el_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHTER_BG, white]),
    ]))
    story.append(el_tbl)

    story.append(PageBreak())

    # Digital evidence details
    story.append(Paragraph(ar('تفاصيل الدليل الرقمي (تظهر عند اختيار نوع دليل):'), styles['h2']))
    step4_details = [
        ('رابط الدليل (digital_evidence_url)', 'رابط URL', False, ''),
        ('حالة الرابط (digital_evidence_url_status)', 'قائمة منسدلة', False,
         'فعّال (active) | محذوف (deleted) | مؤرشف (archived) | غير معروف (unknown) | لم يكن هناك رابط أصلاً (no_url) | الرابط غير متاح - نُسي (url_forgotten)'),
        ('رابط المصدر الأصلي (source_url)', 'رابط URL', False, 'حتى لو كان محذوفاً'),
        ('لقطة شاشة للدليل (digital_evidence_screenshot)', 'رفع ملف', False, 'صورة أو PDF — حتى 15MB'),
        ('تاريخ الدليل الرقمي (digital_evidence_date)', 'تاريخ', False, ''),
        ('الاسم الوارد في الدليل (digital_evidence_person_name)', 'نص حر', False, 'الاسم كما ظهر في التسريبات'),
        ('تاريخ الوفاة الوارد في الدليل (digital_evidence_death_date)', 'تاريخ', False, ''),
        ('وصف الدليل (digital_evidence_description)', 'نص طويل', False, 'وصف تفصيلي'),
    ]
    story.append(field_table(styles, step4_details))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('خيارات حالة الرابط (٦ خيارات):'), styles['h3']))
    story.append(options_table(styles, '', [
        'فعّال (active)', 'محذوف (deleted)', 'مؤرشف (archived)',
        'غير معروف (unknown)', 'لم يكن هناك رابط أصلاً (no_url)', 'الرابط غير متاح - نُسي (url_forgotten)'
    ], ncols=2))

    story.append(Spacer(1, 8))
    # Civil Registry
    story.append(Paragraph(ar('حالة السجل المدني (النفوس):'), styles['h2']))
    step4_civil = [
        ('حالة السجل المدني (civil_registry_status)', 'قائمة منسدلة', False,
         'حي في السجل المدني (alive) | متوفى في السجل المدني (deceased) | غير معروف (unknown) | لم يتم التحقق (not_checked)'),
        ('تاريخ مراجعة النفوس (civil_registry_date)', 'تاريخ', False, ''),
        ('وثيقة من النفوس (civil_registry_document)', 'رفع ملف', False, 'إخراج قيد — حتى 15MB'),
    ]
    story.append(field_table(styles, step4_civil))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('خيارات حالة السجل المدني (٤ خيارات):'), styles['h3']))
    story.append(options_table(styles, '', [
        'حي في السجل المدني (alive)', 'متوفى في السجل المدني (deceased)',
        'غير معروف (unknown)', 'لم يتم التحقق (not_checked)'
    ], ncols=2))

    story.append(Spacer(1, 8))
    # Additional documents
    story.append(Paragraph(ar('وثائق وأدلة إضافية (ديناميكي — عدد غير محدود):'), styles['h2']))
    step4_docs = [
        ('نوع الوثيقة (record_doc_type_N)', 'قائمة منسدلة', False,
         '١٢ نوع — انظر التفصيل أدناه'),
        ('تاريخ الوثيقة (record_doc_date_N)', 'تاريخ', False, ''),
        ('الملف (record_doc_file_N)', 'رفع ملف', False, 'صورة أو PDF — حتى 15MB'),
        ('رابط المصدر (record_doc_url_N)', 'رابط URL', False, ''),
        ('وصف مختصر (record_doc_desc_N)', 'نص حر', False, ''),
    ]
    story.append(field_table(styles, step4_docs))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('خيارات نوع الوثيقة (١٢ نوع):'), styles['h3']))
    doc_types_data = [[
        Paragraph(ar('الرمز'), styles['th']),
        Paragraph(ar('النوع'), styles['th']),
    ]]
    for code, label in [
        ('court_order', 'أمر محكمة'),
        ('visit_card', 'كرت زيارة سجين'),
        ('release_paper', 'ورقة إفراج'),
        ('death_certificate', 'شهادة وفاة'),
        ('leaked_screenshot', 'لقطة شاشة تسريب'),
        ('witness_letter', 'رسالة / شهادة شاهد'),
        ('id_document', 'وثيقة هوية'),
        ('civil_registry_doc', 'إخراج قيد / سجل مدني'),
        ('medical_report', 'تقرير طبي'),
        ('ngo_report', 'تقرير منظمة'),
        ('photo_evidence', 'صورة كدليل'),
        ('other', 'أخرى'),
    ]:
        doc_types_data.append([
            Paragraph(code, styles['tc']),
            Paragraph(ar(label), styles['tc']),
        ])
    dt_tbl = Table(doc_types_data, colWidths=[200, 260])
    dt_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHTER_BG, white]),
    ]))
    story.append(dt_tbl)

    story.append(PageBreak())

    # Conflicting info + Witnesses
    story.append(Paragraph(ar('معلومات متضاربة:'), styles['h2']))
    step4_conflict = [
        ('يوجد تضارب في المعلومات (has_conflicting_info)', 'مربع تحقق', False, ''),
        ('تفاصيل التضارب (conflicting_info_details)', 'نص طويل', False, 'يظهر عند تحقق المربع'),
    ]
    story.append(field_table(styles, step4_conflict))

    story.append(Spacer(1, 8))
    story.append(Paragraph(ar('الشهود (قسم ديناميكي — عدد غير محدود):'), styles['h2']))
    step4_witnesses = [
        ('اسم الشاهد (witness_N_name)', 'نص حر', False, ''),
        ('صلة الشاهد (witness_N_relation)', 'نص حر', False, ''),
        ('هاتف الشاهد (witness_N_phone)', 'رقم هاتف', False, ''),
        ('شهادة الشاهد (witness_N_statement)', 'نص طويل', False, ''),
    ]
    story.append(field_table(styles, step4_witnesses))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # STEP 5: FAMILY & SOCIAL
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph(ar('٧. الخطوة ٥ — العائلة والبيانات الاجتماعية'), styles['h1']))
    story.append(header_line())

    story.append(Paragraph(ar('البيانات العائلية الأساسية:'), styles['h2']))
    step5_main = [
        ('الحالة الاجتماعية (marital)', 'قائمة منسدلة', False,
         'أعزب/عزباء (single) | متزوج/ة (married) | مطلق/ة (divorced) | أرمل/ة (widowed)'),
        ('اسم ولي الأمر / المعرّف (guardian_name)', 'نص حر', False, ''),
        ('صلة ولي الأمر (guardian_relation)', 'نص حر', False, ''),
        ('هاتف ولي الأمر (guardian_phone)', 'رقم هاتف', False, ''),
    ]
    story.append(field_table(styles, step5_main))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('خيارات الحالة الاجتماعية (٤ خيارات):'), styles['h3']))
    story.append(options_table(styles, '', [
        'أعزب/عزباء (single)', 'متزوج/ة (married)',
        'مطلق/ة (divorced)', 'أرمل/ة (widowed)'
    ], ncols=2))

    story.append(Spacer(1, 8))
    story.append(Paragraph(ar('بيانات الزوج/ة (تظهر عند اختيار متزوج/أرمل):'), styles['h2']))
    step5_spouse = [
        ('اسم الزوج/ة (spouse_name)', 'نص حر', False, ''),
        ('هاتف الزوج/ة (spouse_phone)', 'رقم هاتف', False, ''),
    ]
    story.append(field_table(styles, step5_spouse))

    story.append(Spacer(1, 8))
    story.append(Paragraph(ar('بيانات الزوج/ة السابق/ة (تظهر عند اختيار مطلق):'), styles['h2']))
    step5_ex = [
        ('اسم الزوج/ة السابق/ة (ex_spouse_name)', 'نص حر', False, ''),
        ('هل يوجد أطفال من الزواج السابق؟ (has_kids_w)', 'قائمة منسدلة', False, 'نعم | لا'),
        ('عدد الأطفال (kids_count_w)', 'رقم', False, 'يظهر عند اختيار نعم'),
    ]
    story.append(field_table(styles, step5_ex))

    story.append(Spacer(1, 8))
    story.append(Paragraph(ar('المسح الاجتماعي للأطفال (ديناميكي — عدد غير محدود):'), styles['h2']))
    step5_children = [
        ('اسم الطفل (child_N_name)', 'نص حر', False, ''),
        ('جنس الطفل (child_N_gender)', 'قائمة منسدلة', False, 'ذكر | أنثى'),
        ('سنة ميلاد الطفل (child_N_birth_year)', 'رقم', False, ''),
        ('ملاحظات صحية (child_N_health_notes)', 'نص طويل', False, ''),
    ]
    story.append(field_table(styles, step5_children))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # STEP 6: HOUSING, EDUCATION, HEALTH
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph(ar('٨. الخطوة ٦ — السكن والتعليم والصحة'), styles['h1']))
    story.append(header_line())

    story.append(Paragraph(ar('البيانات السكنية والاقتصادية:'), styles['h2']))
    step6_housing = [
        ('المنطقة / الحي (address_area)', 'قائمة منسدلة', False,
         '٢٢ منطقة — انظر التفصيل أدناه'),
        ('العنوان الحالي (address)', 'نص حر', True, 'العنوان التفصيلي'),
        ('نوع السكن (housing_type)', 'قائمة منسدلة', True,
         'ملك | إيجار | رهن | مستضاف | أخرى'),
        ('مبلغ الإيجار (rent_amount)', 'نص حر', False, 'بالليرة السورية'),
        ('الوضع الوظيفي (employment)', 'نص حر', False, 'للناجين فقط'),
        ('المهنة (profession)', 'نص حر', False, 'للناجين فقط'),
        ('جهة العمل (employer)', 'نص حر', False, 'للناجين فقط'),
        ('المعيل (breadwinner)', 'نص حر', False, 'اسم المعيل'),
        ('مهنة المعيل (breadwinner_job)', 'نص حر', False, ''),
        ('صلة المعيل بالضحية (breadwinner_relation)', 'قائمة منسدلة', False,
         'نفس خيارات صلة المُبلِّغ (١٢ خيار)'),
    ]
    story.append(field_table(styles, step6_housing))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('خيارات المنطقة / الحي (٢٢ منطقة):'), styles['h3']))
    story.append(options_table(styles, '', [
        'الرمل الجنوبي', 'قنينص', 'الحفة', 'الصليبة', 'العوينة',
        'الأشرفية', 'بستان الصيداوي', 'الطابيات', 'شيخ ضاهر',
        'حي القصور', 'مرتقلا', 'شارع انطاكيا', 'حي السجن',
        'مشروع القلعة', 'شارع ميسلون', 'سوق الداية', 'الريجي',
        'شارع بور سعيد', 'حي الفاروس', 'طريق الحرش', 'خارج اللاذقية', 'أخرى'
    ], ncols=4))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('خيارات نوع السكن (٥ خيارات):'), styles['h3']))
    story.append(options_table(styles, '', [
        'ملك', 'إيجار', 'رهن', 'مستضاف', 'أخرى'
    ], ncols=5))

    story.append(Spacer(1, 8))
    story.append(Paragraph(ar('التحصيل العلمي:'), styles['h2']))
    step6_edu = [
        ('المستوى التعليمي (education)', 'قائمة منسدلة', False,
         'أمّي | ابتدائية | إعدادية | ثانوية | معهد | بكالوريوس | ماجستير | دكتوراه'),
        ('نوع الدراسة (edu_type)', 'قائمة منسدلة', False,
         'علمي | أدبي | شرعي | مهني | تجاري | صناعي | نسوي | أخرى'),
        ('الاختصاص (edu_specialization)', 'نص حر', False, ''),
        ('الجامعة / المعهد (edu_university)', 'نص حر', False, ''),
    ]
    story.append(field_table(styles, step6_edu))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('خيارات المستوى التعليمي (٨ خيارات):'), styles['h3']))
    story.append(options_table(styles, '', [
        'أمّي', 'ابتدائية', 'إعدادية', 'ثانوية',
        'معهد', 'بكالوريوس', 'ماجستير', 'دكتوراه'
    ], ncols=4))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('خيارات نوع الدراسة (٨ خيارات):'), styles['h3']))
    story.append(options_table(styles, '', [
        'علمي', 'أدبي', 'شرعي', 'مهني',
        'تجاري', 'صناعي', 'نسوي', 'أخرى'
    ], ncols=4))

    story.append(PageBreak())

    # Health section
    story.append(Paragraph(ar('الحالة الصحية:'), styles['h2']))
    step6_health = [
        ('الأمراض المزمنة (chronic_list)', 'مربعات تحقق متعددة', False,
         '٢٢ مرض — انظر القائمة أدناه'),
        ('أمراض أخرى (other_diseases)', 'نص حر', False, 'أمراض غير مذكورة في القائمة'),
        ('احتياجات خاصة (has_special_needs)', 'مربع تحقق', False, ''),
        ('تفاصيل الاحتياجات (special_needs_details)', 'نص حر', False, 'يظهر عند التحقق'),
    ]
    story.append(field_table(styles, step6_health))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('قائمة الأمراض المزمنة (٢٢ مرض):'), styles['h3']))
    story.append(options_table(styles, '', [
        'ضغط الدم', 'السكري', 'الربو', 'أمراض القلب', 'الكلى',
        'الكبد', 'السرطان', 'الصرع', 'الثلاسيميا', 'فقر الدم',
        'التهاب المفاصل', 'هشاشة العظام', 'الغدة الدرقية',
        'أمراض الجهاز الهضمي', 'أمراض الجهاز التنفسي',
        'أمراض نفسية', 'اكتئاب', 'اضطراب ما بعد الصدمة (PTSD)',
        'إعاقة حركية', 'إعاقة بصرية', 'إعاقة سمعية',
        'أخرى'
    ], ncols=3))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # STEP 7: LEGAL & NOTES
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph(ar('٩. الخطوة ٧ — القانوني والملاحظات والحفظ'), styles['h1']))
    story.append(header_line())

    story.append(Paragraph(ar('المشاكل القانونية والجمعيات:'), styles['h2']))
    step7_legal = [
        ('هل يوجد مشاكل قانونية؟ (legal)', 'قائمة منسدلة', False, 'نعم | لا'),
        ('تفاصيل المشاكل القانونية (legal_details)', 'نص طويل', False, 'يظهر عند اختيار نعم'),
        ('مسجل لدى جمعية؟ (assoc)', 'قائمة منسدلة', False, 'نعم | لا'),
        ('اسم الجمعية (assoc_name)', 'نص حر', False, 'يظهر عند اختيار نعم'),
        ('نوع الخدمة المطلوبة (service_type)', 'نص حر', False, 'توثيق، مساعدة قانونية، إلخ'),
        ('مسجل رسمياً (is_officially_registered)', 'مربع تحقق', False,
         'مسجل رسمياً لدى الجهات المعنية'),
    ]
    story.append(field_table(styles, step7_legal))

    story.append(Spacer(1, 8))
    story.append(Paragraph(ar('الملاحظات والمنهجية:'), styles['h2']))
    step7_notes = [
        ('ملاحظات إضافية (notes)', 'نص طويل', False, 'أي معلومات لم تُذكر أعلاه'),
        ('نوع المنهجية (methodology_type)', 'قائمة منسدلة', False,
         '٨ أنواع — انظر التفصيل أدناه'),
        ('ملاحظات المنهجية (methodology_notes)', 'نص طويل', False, ''),
    ]
    story.append(field_table(styles, step7_notes))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('خيارات نوع المنهجية (٨ أنواع):'), styles['h3']))
    mt_data = [[
        Paragraph(ar('الرمز'), styles['th']),
        Paragraph(ar('النوع'), styles['th']),
    ]]
    for code, label in [
        ('interview', 'مقابلة شخصية'),
        ('document_review', 'مراجعة وثائق'),
        ('open_source', 'تحقيق مصادر مفتوحة'),
        ('field_visit', 'زيارة ميدانية'),
        ('remote_interview', 'مقابلة عن بعد'),
        ('database_cross_ref', 'تقاطع قواعد بيانات'),
        ('witness_testimony', 'شهادة شاهد'),
        ('other', 'أخرى'),
    ]:
        mt_data.append([
            Paragraph(code, styles['tc']),
            Paragraph(ar(label), styles['tc']),
        ])
    mt_tbl = Table(mt_data, colWidths=[200, 260])
    mt_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHTER_BG, white]),
    ]))
    story.append(mt_tbl)

    story.append(Spacer(1, 8))
    story.append(Paragraph(ar('علامات المنهجية (Tags) — ١٦ علامة وصفية:'), styles['h2']))
    story.append(Paragraph(ar('يمكن اختيار عدة علامات لكل حالة لتصنيف طريقة جمع البيانات:'), styles['body']))
    story.append(Spacer(1, 4))
    story.append(options_table(styles, '', [
        'مقابلة مباشرة', 'مقابلة هاتفية', 'مقابلة عبر الإنترنت',
        'شهادة شاهد عيان', 'شهادة أحد الأقارب', 'تسريبات قيصر',
        'وثائق رسمية', 'بيانات السجل المدني', 'تقارير إعلامية',
        'منشورات وسائل التواصل', 'تقارير منظمات حقوقية', 'أرشيف رقمي',
        'تحليل صور/فيديو', 'تقاطع معلومات من مصادر متعددة', 'زيارة ميدانية',
        'بلاغ مجهول'
    ], ncols=3))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # SECTION 10: CASE TYPES
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph(ar('١٠. تصنيف الحالات والأنواع الفرعية'), styles['h1']))
    story.append(header_line())
    story.append(Paragraph(ar(
        'يعتمد النظام تصنيفاً ثلاثياً رئيسياً مع ٨ أنواع فرعية تتغير ديناميكياً:'
    ), styles['body']))
    story.append(Spacer(1, 6))

    story.append(Paragraph(ar('التصنيفات الرئيسية:'), styles['h3']))
    story.append(draw_status_diagram(460))
    story.append(Spacer(1, 10))

    story.append(Paragraph(ar('جميع الأنواع الفرعية (٨ أنواع):'), styles['h3']))
    ct_data = [[
        Paragraph(ar('الرمز'), styles['th']),
        Paragraph(ar('التصنيف الرئيسي'), styles['th']),
        Paragraph(ar('النوع الفرعي'), styles['th']),
    ]]
    case_types = [
        ('اختفاء قسري - لا معلومات', 'مغيّب قسراً', 'enforced_disappearance_no_info'),
        ('اختفاء قسري - تسريبات تؤكد الوفاة (مؤكد بالنفوس)', 'مغيّب / متوفى', 'enforced_disappearance_leaked_confirmed_dead'),
        ('اختفاء قسري - تسريبات تؤكد الوفاة (غير مؤكد)', 'مغيّب / متوفى', 'enforced_disappearance_leaked_not_confirmed'),
        ('اختفاء قسري - متوفى بحسب النفوس', 'مغيّب / متوفى', 'enforced_disappearance_civil_registry_dead'),
        ('اختفاء قسري - شهود (حي بالنفوس)', 'مغيّب قسراً', 'enforced_disappearance_witnesses_alive_registry'),
        ('ناجٍ - لديه وثائق', 'ناجٍ', 'survivor_documented'),
        ('ناجٍ - بدون وثائق', 'ناجٍ', 'survivor_undocumented'),
        ('متوفى - ملفات قيصر', 'متوفى', 'deceased_caesar_files'),
    ]
    for subtype, main_type, code in case_types:
        ct_data.append([
            Paragraph(code, styles['tc_small']),
            Paragraph(ar(main_type), styles['tc']),
            Paragraph(ar(subtype), styles['tcr']),
        ])
    ct_tbl = Table(ct_data, colWidths=[200, 80, 180])
    ct_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHTER_BG, white]),
    ]))
    story.append(ct_tbl)

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # SECTION 11: EVIDENCE LEVELS & VERIFICATION
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph(ar('١١. مستويات الأدلة وحالات التحقق'), styles['h1']))
    story.append(header_line())

    story.append(Paragraph(ar('مستويات قوة الأدلة:'), styles['h3']))
    story.append(draw_evidence_levels(460))
    story.append(Spacer(1, 10))

    story.append(Paragraph(ar('حالات التحقق (٤ حالات):'), styles['h3']))
    ver_data = [[
        Paragraph(ar('الوصف'), styles['th']),
        Paragraph(ar('الرمز'), styles['th']),
        Paragraph(ar('الحالة'), styles['th']),
    ]]
    for label, code, desc in [
        ('تم التحقق', 'Verified', 'تم التحقق من صحة المعلومات من مصادر مستقلة متعددة'),
        ('مؤيَّد بأدلة', 'Corroborated', 'المعلومات مدعومة بأدلة جزئية أو مصدر إضافي'),
        ('لم يُتحقق منه', 'Unverified', 'المعلومات بانتظار عملية التحقق'),
        ('معلومات متضاربة', 'Conflicting', 'توجد تناقضات بين المصادر المختلفة'),
    ]:
        ver_data.append([
            Paragraph(ar(desc), styles['tcr']),
            Paragraph(code, styles['tc']),
            Paragraph(ar(label), styles['tc']),
        ])
    ver_tbl = Table(ver_data, colWidths=[240, 90, 130])
    ver_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHTER_BG, white]),
    ]))
    story.append(ver_tbl)

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # SECTION 12: CHAIN OF CUSTODY
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph(ar('١٢. سلسلة الحفظ الرقمية ومسار المراجعة'), styles['h1']))
    story.append(header_line())

    story.append(Paragraph(ar(
        'تُعد سلسلة الحفظ (Chain of Custody) من أهم متطلبات بروتوكول بيركلي. '
        'تضمن تتبع كل معلومة من لحظة جمعها حتى استخدامها كدليل.'
    ), styles['body']))
    story.append(Spacer(1, 6))

    story.append(Paragraph(ar('العناصر الأساسية:'), styles['h3']))
    for item in [
        'اسم جامع البيانات (collector_name) — يُسجَّل تلقائياً',
        'تاريخ الجمع (collection_date) — يُسجَّل تلقائياً',
        'المعرّف الفريد (UUID) — رمز فريد عالمياً لكل حالة',
        'الطوابع الزمنية — تاريخ الإنشاء وتاريخ آخر تعديل',
        'حالة المزامنة — مسودة، قيد المراجعة، مُراجَعة، مُتحقق منها، مقفلة',
        'المرفقات — كل ملف مرتبط بحقل محدد مع بصمة رقمية SHA-256',
    ]:
        story.append(Paragraph(ar(f'• {item}'), styles['bullet']))

    story.append(Spacer(1, 10))
    story.append(Paragraph(ar('مخطط مسار التحقق:'), styles['h3']))
    story.append(draw_verification_flow(460))
    story.append(Spacer(1, 10))

    story.append(Paragraph(ar('الحقول الإلزامية حسب مرحلة التحقق:'), styles['h3']))
    berk_data = [[
        Paragraph(ar('الحقول الإلزامية'), styles['th']),
        Paragraph(ar('المرحلة'), styles['th']),
    ]]
    for stage, fields in [
        ('مُراجَعة (Reviewed)',
         'first_name, father_name, last_name, status, source_type, collector_name, collection_date'),
        ('مُتحقق منها (Verified)',
         'جميع حقول المراجعة + evidence_level + verification_status'),
        ('مقفلة (Locked)',
         'جميع حقول التحقق — لا يمكن التعديل بعد القفل'),
    ]:
        berk_data.append([
            Paragraph(ar(fields), styles['tcr']),
            Paragraph(ar(stage), styles['tc']),
        ])
    berk_tbl = Table(berk_data, colWidths=[340, 120])
    berk_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHTER_BG, white]),
    ]))
    story.append(berk_tbl)

    story.append(Spacer(1, 10))
    story.append(Paragraph(ar('أمان البيانات:'), styles['h3']))
    for item in [
        'تخزين محلي مشفر على الجهاز (Offline-First)',
        'مزامنة عبر HTTPS مع مصادقة',
        'بصمة SHA-256 لكل وثيقة مرفقة',
        'الوصول محصور بالمتطوعين المعتمدين',
        'نسخ احتياطي مركزي محمي',
    ]:
        story.append(Paragraph(ar(f'• {item}'), styles['bullet']))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # SECTION 13: APPENDICES
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph(ar('١٣. الملاحق'), styles['h1']))
    story.append(header_line())

    # Appendix A: All required fields summary
    story.append(Paragraph(ar('ملحق أ: ملخص جميع الحقول الإلزامية (١٤ حقل)'), styles['h2']))
    req_data = [[
        Paragraph(ar('الخطوة'), styles['th']),
        Paragraph(ar('الحقل'), styles['th']),
    ]]
    required_fields = [
        ('١', 'تصنيف الحالة (status)'),
        ('١', 'اسم المُبلِّغ (reporter_name)'),
        ('١', 'صلة المُبلِّغ (reporter_relation)'),
        ('١', 'نوع المصدر (source_type)'),
        ('٢', 'الاسم الأول (first_name)'),
        ('٢', 'اسم الأب (father_name)'),
        ('٢', 'الكنية (last_name)'),
        ('٢', 'اسم الأم (mother_name)'),
        ('٢', 'الجنس (gender)'),
        ('٢', 'المحافظة (province)'),
        ('٢', 'الرقم الوطني (national_id)'),
        ('٣', 'الجهة المعتقِلة (arrest_authority)'),
        ('٣', 'سبب الاعتقال (arrest_reason)'),
        ('٦', 'العنوان الحالي (address)'),
    ]
    for step, field in required_fields:
        req_data.append([
            Paragraph(ar(step), styles['tc']),
            Paragraph(ar(field), styles['tcr']),
        ])
    req_tbl = Table(req_data, colWidths=[60, 400])
    req_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), DANGER),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#fdedec'), white]),
    ]))
    story.append(req_tbl)

    story.append(Spacer(1, 10))

    # Appendix B: Full detention facilities list
    story.append(Paragraph(ar('ملحق ب: مراكز الاحتجاز المعروفة (٢٣ مركز)'), styles['h2']))
    fac_data = [[
        Paragraph(ar('المركز'), styles['th']),
        Paragraph(ar('#'), styles['th']),
    ]]
    facilities = [
        'صيدنايا الامني (الاحمر)', 'صيدنايا القضائي (الابيض)',
        'فرع 215، بسرية المداهمة والاقتحام', 'فرع 216، فرع الدوريات',
        'فرع 227، فرع المنطقة', 'فرع 235 فرع فلسطين',
        'فرع 248، التحقيق العسكري', 'فرع 251، فرع الخطيب',
        'فرع 285، فرع التحقيق', 'فرع 293',
        'فرع 295، مكافحة الإرهاب', 'فرع الأمن العسكري',
        'فرع الأمن السياسي', 'فرع أمن الدولة',
        'فرع المخابرات الجوية', 'السجن المدني',
        'سجن تدمر', 'سجن عدرا',
        'سجن حمص المركزي', 'مطار المزة',
        'المدينة الرياضية', 'غير معروف', 'أخرى'
    ]
    for i, f in enumerate(facilities, 1):
        fac_data.append([
            Paragraph(ar(f), styles['tcr']),
            Paragraph(str(i), styles['tc']),
        ])
    fac_tbl = Table(fac_data, colWidths=[400, 60])
    fac_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHTER_BG, white]),
    ]))
    story.append(fac_tbl)

    story.append(PageBreak())

    # ════════════════════════ CLOSING ════════════════════════
    story.append(Spacer(1, 2 * cm))
    story.append(HRFlowable(width="80%", thickness=2, color=PRIMARY,
                            spaceAfter=16, spaceBefore=8, hAlign='CENTER'))
    story.append(Paragraph(ar('جمعية حقنا'), styles['title']))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(ar('نحو عدالة انتقالية شاملة وتوثيق يحفظ الحقوق'), styles['subtitle']))
    story.append(Spacer(1, 0.8 * cm))

    story.append(info_box(
        'هذه الوثيقة سرية ومخصصة للاستخدام الداخلي لمتطوعي جمعية حقنا فقط.',
        styles['body_center'], color=HexColor('#fdedec'), border_color=DANGER
    ))

    story.append(Spacer(1, 1 * cm))
    story.append(Paragraph(ar('تم تطوير هذا النظام بشكل خاص لمتطوعي جمعية حقنا'), styles['body_center']))
    story.append(Paragraph(ar('من قبل: مهند حسون'), styles['body_center']))
    story.append(Paragraph('bugmuha@gmail.com', styles['body_center']))

    def add_page_number(canvas, doc):
        page_num = canvas.getPageNumber()
        canvas.saveState()
        canvas.setFont('Amiri', 9)
        canvas.setFillColor(MEDIUM_TEXT)
        text = ar(f'جمعية حقنا — بروتوكول التوثيق الشامل — صفحة {page_num}')
        canvas.drawCentredString(page_w / 2, 1.2 * cm, text)
        canvas.restoreState()

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    print(f'PDF generated: {output_path}')


if __name__ == '__main__':
    output = '/home/user/dd/haqquna_protocol_ar.pdf'
    build_pdf(output)
