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

# Fixed Arabic reshaper — preserve diacritics (harakat)
_reshaper = arabic_reshaper.ArabicReshaper(configuration={
    'delete_harakat': False,
    'delete_tatweel': False,
    'support_zwj': True,
    'support_ligatures': True,
    'RIAL SIGN': True,
})

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
    reshaped = _reshaper.reshape(text)
    return get_display(reshaped)

def make_styles():
    s = {}
    s['title'] = ParagraphStyle('Title', fontName='AmiriBold', fontSize=26,
        leading=38, alignment=TA_CENTER, textColor=PRIMARY, wordWrap='RTL')
    s['subtitle'] = ParagraphStyle('Subtitle', fontName='Amiri', fontSize=14,
        leading=22, alignment=TA_CENTER, textColor=SECONDARY, wordWrap='RTL')
    s['h1'] = ParagraphStyle('H1', fontName='AmiriBold', fontSize=18,
        leading=28, alignment=TA_RIGHT, textColor=PRIMARY, spaceBefore=16,
        spaceAfter=8, wordWrap='RTL')
    s['h2'] = ParagraphStyle('H2', fontName='AmiriBold', fontSize=14,
        leading=22, alignment=TA_RIGHT, textColor=SECONDARY, spaceBefore=12,
        spaceAfter=6, wordWrap='RTL')
    s['h3'] = ParagraphStyle('H3', fontName='AmiriBold', fontSize=11,
        leading=18, alignment=TA_RIGHT, textColor=DARK_TEXT, spaceBefore=8,
        spaceAfter=5, wordWrap='RTL')
    s['body'] = ParagraphStyle('Body', fontName='Amiri', fontSize=10,
        leading=17, alignment=TA_RIGHT, textColor=DARK_TEXT, wordWrap='RTL')
    s['body_center'] = ParagraphStyle('BodyCenter', fontName='Amiri', fontSize=10,
        leading=17, alignment=TA_CENTER, textColor=DARK_TEXT, wordWrap='RTL')
    s['bullet'] = ParagraphStyle('Bullet', fontName='Amiri', fontSize=9.5,
        leading=15, alignment=TA_RIGHT, textColor=DARK_TEXT, leftIndent=12,
        wordWrap='RTL')
    s['small'] = ParagraphStyle('Small', fontName='Amiri', fontSize=9,
        leading=14, alignment=TA_RIGHT, textColor=MEDIUM_TEXT, wordWrap='RTL')
    s['small_center'] = ParagraphStyle('SmallCenter', fontName='Amiri', fontSize=9,
        leading=14, alignment=TA_CENTER, textColor=MEDIUM_TEXT, wordWrap='RTL')
    s['th'] = ParagraphStyle('TH', fontName='AmiriBold', fontSize=8.5,
        leading=13, alignment=TA_CENTER, textColor=white, wordWrap='RTL')
    s['tc'] = ParagraphStyle('TC', fontName='Amiri', fontSize=8.5,
        leading=12, alignment=TA_CENTER, textColor=DARK_TEXT, wordWrap='RTL')
    s['tcr'] = ParagraphStyle('TCR', fontName='Amiri', fontSize=8.5,
        leading=12, alignment=TA_RIGHT, textColor=DARK_TEXT, wordWrap='RTL')
    s['tc_small'] = ParagraphStyle('TCSmall', fontName='Amiri', fontSize=8,
        leading=11, alignment=TA_CENTER, textColor=DARK_TEXT, wordWrap='RTL')
    s['tc_opt'] = ParagraphStyle('TCOpt', fontName='Amiri', fontSize=7.5,
        leading=10, alignment=TA_RIGHT, textColor=MEDIUM_TEXT, wordWrap='RTL')
    s['footer'] = ParagraphStyle('Footer', fontName='Amiri', fontSize=8,
        leading=12, alignment=TA_CENTER, textColor=MEDIUM_TEXT, wordWrap='RTL')
    return s


def draw_workflow_diagram(width):
    h = 420
    d = Drawing(width, h)
    steps = [
        ('1', ar('الحالة والمُبلِّغ'), PRIMARY),
        ('2', ar('البيانات الشخصية'), SECONDARY),
        ('3', ar('الاعتقال والاحتجاز'), PURPLE),
        ('4', ar('الأدلة والتحقق'), WARN),
        ('5', ar('العائلة والاجتماعي'), ACCENT),
        ('6', ar('السكن والصحة'), HexColor('#e74c3c')),
        ('7', ar('القانوني والحفظ'), HexColor('#2c3e50')),
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
                     label, fontName='AmiriBold', fontSize=10,
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
    h = 80
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
        d.add(Rect(x, y, block_w, 55, fillColor=color, strokeColor=None, rx=6, ry=6))
        d.add(String(x + block_w / 2, y + 25, title,
                     fontName='AmiriBold', fontSize=13, fillColor=white,
                     textAnchor='middle'))
    return d


def draw_status_diagram(width):
    h = 75
    d = Drawing(width, h)
    statuses = [
        (ar('ناجٍ'), ACCENT),
        (ar('مغيّب قسراً'), WARN),
        (ar('متوفى'), DANGER),
    ]
    spacing = width / 3
    for i, (title, color) in enumerate(statuses):
        cx = width - spacing * i - spacing / 2
        d.add(Circle(cx, 45, 22, fillColor=color, strokeColor=None))
        d.add(String(cx, 40, title, fontName='AmiriBold', fontSize=11,
                     fillColor=white, textAnchor='middle'))
    return d


def draw_verification_flow(width):
    h = 55
    d = Drawing(width, h)
    stages = [
        (ar('مسودة'), HexColor('#95a5a6')),
        (ar('مراجَع'), WARN),
        (ar('موثّق'), PURPLE),
        (ar('مقفل'), ACCENT),
    ]
    box_w = 85
    total_w = len(stages) * box_w + (len(stages) - 1) * 30
    start_x = (width - total_w) / 2 + total_w
    for i, (label, color) in enumerate(stages):
        x = start_x - (i + 1) * (box_w + 30) + 30
        d.add(Rect(x, 12, box_w, 32, fillColor=color, strokeColor=None, rx=6, ry=6))
        d.add(String(x + box_w / 2, 24, label,
                     fontName='AmiriBold', fontSize=12, fillColor=white,
                     textAnchor='middle'))
        if i < len(stages) - 1:
            d.add(Line(x - 2, 28, x - 28, 28, strokeColor=BORDER, strokeWidth=2))
            ax = x - 15
            d.add(Polygon(points=[ax - 6, 33, ax - 6, 23, ax - 14, 28],
                          fillColor=BORDER, strokeColor=None))
    return d


def info_box(text, style, color=LIGHT_BG, border_color=SECONDARY):
    tbl = Table([[Paragraph(ar(text), style)]], colWidths=[450])
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), color),
        ('BOX', (0, 0), (-1, -1), 1.5, border_color),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return tbl


def header_line():
    return HRFlowable(width="100%", thickness=1.5, color=SECONDARY,
                      spaceAfter=6, spaceBefore=3)


def field_table(styles, fields):
    """fields: list of (field_name, field_type, required, options_text)"""
    data = [[
        Paragraph(ar('الخيارات المتاحة'), styles['th']),
        Paragraph(ar('النوع'), styles['th']),
        Paragraph(ar('*'), styles['th']),
        Paragraph(ar('اسم الحقل'), styles['th']),
    ]]
    for name, ftype, req, opts in fields:
        req_txt = '*' if req else ''
        data.append([
            Paragraph(ar(opts) if opts else '', styles['tc_opt']),
            Paragraph(ar(ftype), styles['tc_small']),
            Paragraph(req_txt, styles['tc']),
            Paragraph(ar(name), styles['tcr']),
        ])

    tbl = Table(data, colWidths=[200, 60, 20, 180])
    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHTER_BG, white]),
    ]
    for i, (_, _, req, _) in enumerate(fields, 1):
        if req:
            style_cmds.append(('BACKGROUND', (1, i), (2, i), HexColor('#fdecea')))
    tbl.setStyle(TableStyle(style_cmds))
    return tbl


def opts_table(styles, options, ncols=3):
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
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [LIGHTER_BG, white]),
    ]))
    return tbl


def code_label_table(styles, items, title_a, title_b):
    data = [[
        Paragraph(ar(title_a), styles['th']),
        Paragraph(ar(title_b), styles['th']),
    ]]
    for code, label in items:
        data.append([
            Paragraph(code if code.isascii() else ar(code), styles['tc']),
            Paragraph(ar(label), styles['tc']),
        ])
    tbl = Table(data, colWidths=[180, 280])
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHTER_BG, white]),
    ]))
    return tbl


def build_pdf(output_path):
    styles = make_styles()
    page_w, page_h = A4

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        rightMargin=1.6 * cm, leftMargin=1.6 * cm,
        topMargin=1.6 * cm, bottomMargin=1.6 * cm
    )

    story = []

    # ════════════════════════ COVER ════════════════════════
    story.append(Spacer(1, 1.5 * cm))
    logo_path = '/home/user/dd/logo.jpg'
    if os.path.exists(logo_path):
        story.append(Image(logo_path, width=4 * cm, height=4 * cm, hAlign='CENTER'))
        story.append(Spacer(1, 0.6 * cm))

    story.append(Paragraph(ar('جمعية حقنا'), styles['title']))
    story.append(HRFlowable(width="50%", thickness=3, color=PRIMARY,
                            spaceAfter=8, spaceBefore=4, hAlign='CENTER'))
    story.append(Paragraph(ar('بروتوكول التوثيق الشامل'), styles['title']))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(ar('دليل إجراءات توثيق حالات الاختفاء القسري والاعتقال'), styles['subtitle']))
    story.append(Paragraph(ar('جميع الحقول والخيارات المتاحة في النظام'), styles['subtitle']))
    story.append(Spacer(1, 0.5 * cm))
    story.append(info_box(
        'وفقاً لبروتوكول بيركلي للتحقيقات الرقمية في المصادر المفتوحة',
        styles['body_center'], color=HexColor('#f0f4f8'), border_color=PRIMARY
    ))
    story.append(Spacer(1, 1.5 * cm))
    story.append(Paragraph(ar('الإصدار ٣.٠'), styles['body_center']))
    story.append(Paragraph(ar('وثيقة سرية للاستخدام الداخلي فقط'), styles['small_center']))
    story.append(PageBreak())

    # ════════════════════════ TOC ════════════════════════
    story.append(Paragraph(ar('فهرس المحتويات'), styles['h1']))
    story.append(header_line())
    toc = [
        '١. المقدمة والإحصائيات',
        '٢. مخطط سير عملية التوثيق',
        '٣. الخطوة ١: الحالة والمُبلِّغ',
        '٤. الخطوة ٢: البيانات الشخصية والمرفقات',
        '٥. الخطوة ٣: الاعتقال والاحتجاز والمرافقون',
        '٦. الخطوة ٤: الأدلة والتحقق والشهود',
        '٧. الخطوة ٥: العائلة والبيانات الاجتماعية',
        '٨. الخطوة ٦: السكن والتعليم والصحة',
        '٩. الخطوة ٧: القانوني والملاحظات والمنهجية',
        '١٠. تصنيف الحالات والأنواع الفرعية',
        '١١. مستويات الأدلة وحالات التحقق',
        '١٢. سلسلة الحفظ ومسار المراجعة',
        '١٣. إدارة المتطوعين والأعضاء',
        '١٤. ملحق: مراكز الاحتجاز (٢٣ مركز)',
        '١٥. ملحق: الحقول الإلزامية',
    ]
    for t in toc:
        story.append(Paragraph(ar(t), styles['body']))
    story.append(PageBreak())

    # ════════════════════════ 1. INTRO ════════════════════════
    story.append(Paragraph(ar('١. المقدمة والإحصائيات'), styles['h1']))
    story.append(header_line())
    story.append(Paragraph(ar(
        'يُحدد هذا البروتوكول جميع إجراءات وحقول وخيارات نظام توثيق حالات الاختفاء القسري '
        'والاعتقال التعسفي في سوريا. مصمم وفق بروتوكول بيركلي للتحقيقات الرقمية.'
    ), styles['body']))
    story.append(Spacer(1, 5))
    for s in [
        'إجمالي الخطوات: ٧ خطوات متتابعة',
        'إجمالي الحقول: أكثر من ١٢٠ حقل (بما فيها الأقسام الديناميكية)',
        'الحقول الإلزامية: ١٤ حقل',
        'القوائم المنسدلة: أكثر من ٣٥ قائمة',
        'حقول رفع الملفات: ١٠ حقول (JPG, PNG, PDF) حتى 15MB لكل ملف',
        'مربعات التحقق: ٢٢ مرض مزمن + خيارات متعددة',
        'علامات المنهجية: ١٦ علامة وصفية',
        'مراكز الاحتجاز: ٢٣ مركز موثق',
        'الجهات الأمنية: ١٢ جهة',
        'المحافظات: ١٥ محافظة',
        'أنواع الأدلة الرقمية: ٨ أنواع',
        'أنواع الوثائق: ١٢ نوع',
        'أدوار المتطوعين: ٩ أدوار',
    ]:
        story.append(Paragraph(ar(f'• {s}'), styles['bullet']))

    story.append(Spacer(1, 6))
    story.append(info_box(
        'ملاحظة: النظام يعمل بدون اتصال بالإنترنت (Offline-First) مع مزامنة تلقائية.',
        styles['body_center'], color=HexColor('#eafaf1'), border_color=ACCENT
    ))
    story.append(PageBreak())

    # ════════════════════════ 2. WORKFLOW ════════════════════════
    story.append(Paragraph(ar('٢. مخطط سير عملية التوثيق'), styles['h1']))
    story.append(header_line())
    story.append(draw_workflow_diagram(460))
    story.append(PageBreak())

    # ════════════════════════ 3. STEP 1 ════════════════════════
    story.append(Paragraph(ar('٣. الخطوة ١: الحالة والمُبلِّغ'), styles['h1']))
    story.append(header_line())
    story.append(Paragraph(ar('تحديد تصنيف الحالة وبيانات المُبلِّغ ومصدر المعلومات.'), styles['body']))
    story.append(Spacer(1, 4))
    story.append(field_table(styles, [
        ('تصنيف الحالة (status)', 'قائمة', True,
         'ناجٍ (survivor) | مغيّب قسراً (enforced) | متوفى (deceased)'),
        ('نوع الحالة التفصيلي (case_type)', 'قائمة ديناميكية', False,
         '٨ أنواع تتغير حسب التصنيف - انظر قسم ١٠'),
        ('اسم المُبلِّغ (reporter_name)', 'نص', True, ''),
        ('صلة المُبلِّغ بالضحية (reporter_relation)', 'قائمة', True,
         '١٢ خيار - انظر أدناه'),
        ('هاتف المُبلِّغ (reporter_phone)', 'هاتف', False, ''),
        ('رقم هوية المُبلِّغ (reporter_id)', 'نص', False, 'الرقم الوطني'),
        ('اسم جامع البيانات (collector_name)', 'نص + قائمة مقترحة', False,
         'مهم لسلسلة الحفظ (بيركلي)'),
        ('تاريخ جمع البيانات (collection_date)', 'تاريخ', False,
         'يُملأ تلقائياً بتاريخ اليوم'),
        ('نوع المصدر (source_type)', 'قائمة', True,
         '٨ خيارات - انظر أدناه'),
        ('موافقة المُبلِّغ (informant_consent)', 'مربع تحقق', False,
         'الموافقة الواعية وفق بروتوكول بيركلي'),
    ]))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('خيارات تصنيف الحالة (٣ خيارات):'), styles['h3']))
    story.append(code_label_table(styles, [
        ('survivor', 'ناجٍ (شخص أُفرج عنه / هرب)'),
        ('enforced', 'مغيّب قسراً (لا يُعرف مصيره)'),
        ('deceased', 'متوفى (مؤكد الوفاة)'),
    ], 'الرمز', 'التصنيف'))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('خيارات صلة المُبلِّغ بالضحية (١٢ خيار):'), styles['h3']))
    story.append(opts_table(styles, [
        'أم', 'أب', 'أخ', 'أخت', 'زوج/ة', 'ابن/ة',
        'قريب', 'صديق', 'جار', 'زميل', 'الشخص نفسه', 'أخرى'
    ], ncols=4))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('خيارات نوع المصدر (٨ خيارات):'), styles['h3']))
    story.append(opts_table(styles, [
        'مقابلة مباشرة', 'مقابلة هاتفية', 'وثائق رسمية',
        'مصادر مفتوحة (إنترنت / إعلام)', 'شهادة شاهد', 'تسريبات',
        'إحالة من منظمة / جهة أخرى', 'أخرى'
    ], ncols=2))

    story.append(PageBreak())

    # ════════════════════════ 4. STEP 2 ════════════════════════
    story.append(Paragraph(ar('٤. الخطوة ٢: البيانات الشخصية والمرفقات'), styles['h1']))
    story.append(header_line())
    story.append(field_table(styles, [
        ('الاسم الأول (first_name)', 'نص', True, ''),
        ('اسم الأب (father_name)', 'نص', True, ''),
        ('الكنية / اسم العائلة (last_name)', 'نص', True, ''),
        ('اسم الأم (mother_name)', 'نص', True, ''),
        ('الجنس (gender)', 'قائمة', True, 'ذكر (male) | أنثى (female)'),
        ('تاريخ الميلاد: اليوم (birth_day)', 'رقم', False, '٠ - ٣١'),
        ('تاريخ الميلاد: الشهر (birth_month)', 'رقم', False, '٠ - ١٢'),
        ('تاريخ الميلاد: السنة (birth_year)', 'رقم', False, '١٩٠٠ - ٢٠٢٦'),
        ('المحافظة (province)', 'قائمة', True, '١٥ محافظة - انظر أدناه'),
        ('الرقم الوطني (national_id)', 'نص', True, '١١ رقم'),
        ('رقم دفتر العائلة (family_book_number)', 'نص', False, ''),
        ('رقم الهاتف (phone)', 'هاتف', False, 'مخفي للمتوفين والمغيّبين'),
        ('زمرة الدم (blood_type)', 'قائمة', False,
         'A+ | A- | B+ | B- | AB+ | AB- | O+ | O-'),
        ('صورة شخصية (photo)', 'رفع ملف', False, 'JPG, PNG حتى 15MB'),
        ('وثيقة هوية (document)', 'رفع ملف', False, 'JPG, PNG, PDF حتى 15MB'),
    ]))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('خيارات المحافظات (١٥ محافظة):'), styles['h3']))
    story.append(opts_table(styles, [
        'اللاذقية', 'دمشق', 'ريف دمشق', 'حلب', 'حمص', 'حماة',
        'إدلب', 'درعا', 'السويداء', 'القنيطرة', 'الرقة',
        'دير الزور', 'الحسكة', 'طرطوس', 'أخرى'
    ], ncols=5))

    story.append(Spacer(1, 4))
    story.append(Paragraph(ar('خيارات زمرة الدم (٨ خيارات):'), styles['h3']))
    story.append(opts_table(styles, [
        'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'
    ], ncols=4))

    story.append(PageBreak())

    # ════════════════════════ 5. STEP 3 ════════════════════════
    story.append(Paragraph(ar('٥. الخطوة ٣: الاعتقال والاحتجاز والمرافقون'), styles['h1']))
    story.append(header_line())

    story.append(Paragraph(ar('حقول الاعتقال الأساسية:'), styles['h2']))
    story.append(field_table(styles, [
        ('تاريخ الاعتقال: اليوم (arrest_day)', 'رقم', False, '٠ - ٣١'),
        ('تاريخ الاعتقال: الشهر (arrest_month)', 'رقم', False, '٠ - ١٢'),
        ('تاريخ الاعتقال: السنة (arrest_year)', 'رقم', False, '٢٠٠٠ - ٢٠٢٦'),
        ('الجهة المعتقِلة (arrest_authority)', 'قائمة', True,
         '١٢ جهة - انظر أدناه'),
        ('مكان الاحتجاز / المعتقل (arrest_place)', 'قائمة', False,
         '٢٣ مركز - انظر ملحق ١٤'),
        ('سبب الاعتقال (arrest_reason)', 'نص', True,
         'مثال: مظاهرة، تقرير كيدي، حاجز...'),
        ('المتسبب بالاعتقال (arrest_causer)', 'نص', False, 'اسم الشخص أو الجهة'),
        ('آخر مكان معروف (last_known_location)', 'نص', False, ''),
        ('آخر تاريخ عُرف أنه حي (last_known_alive_date)', 'تاريخ', False, ''),
    ]))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('خيارات الجهة المعتقِلة (١٢ جهة):'), styles['h3']))
    story.append(opts_table(styles, [
        'الأمن العسكري', 'الأمن السياسي', 'أمن الدولة',
        'المخابرات الجوية', 'الدفاع الوطني', 'الشرطة العسكرية',
        'الأمن الجنائي', 'الجيش', 'حاجز أمني',
        'دورية مشتركة', 'غير معروف', 'أخرى'
    ], ncols=3))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('حقول الناجين فقط (تظهر عند اختيار "ناجٍ"):'), styles['h2']))
    story.append(field_table(styles, [
        ('تاريخ الإفراج: اليوم (release_day)', 'رقم', False, '٠ - ٣١'),
        ('تاريخ الإفراج: الشهر (release_month)', 'رقم', False, '٠ - ١٢'),
        ('تاريخ الإفراج: السنة (release_year)', 'رقم', False, '٢٠٠٠ - ٢٠٢٦'),
        ('ملخص التجربة (survivor_cv)', 'رفع ملف', False, 'صورة/PDF/DOC حتى 15MB'),
        ('صورة بعد الإفراج (survivor_cv_photo)', 'رفع ملف', False, 'صورة حتى 15MB'),
        ('وصف تجربة الاعتقال (survivor_cv_text)', 'نص طويل', False, 'وصف مختصر للتجربة'),
    ]))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('حقول المتوفين فقط (تظهر عند اختيار "متوفى"):'), styles['h2']))
    story.append(field_table(styles, [
        ('تاريخ الوفاة: اليوم (death_day)', 'رقم', False, '٠ - ٣١'),
        ('تاريخ الوفاة: الشهر (death_month)', 'رقم', False, '٠ - ١٢'),
        ('تاريخ الوفاة: السنة (death_year)', 'رقم', False, '٢٠٠٠ - ٢٠٢٦'),
        ('مكان الوفاة (death_place)', 'نص', False, ''),
    ]))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('المرافقون (ديناميكي - عدد غير محدود):'), styles['h2']))
    story.append(field_table(styles, [
        ('الاسم الأول للمرافق (comp_first_N)', 'نص', False, ''),
        ('اسم أب المرافق (comp_father_N)', 'نص', False, ''),
        ('كنية المرافق (comp_last_N)', 'نص', False, ''),
        ('اسم أم المرافق (comp_mother_N)', 'نص', False, ''),
        ('ملاحظة (comp_notes_N)', 'نص', False, 'مثال: كان معه في نفس الزنزانة'),
    ]))

    story.append(PageBreak())

    # ════════════════════════ 6. STEP 4 ════════════════════════
    story.append(Paragraph(ar('٦. الخطوة ٤: الأدلة والتحقق والشهود'), styles['h1']))
    story.append(header_line())

    story.append(Paragraph(ar('الأدلة الرقمية الأساسية:'), styles['h2']))
    story.append(field_table(styles, [
        ('نوع الدليل الرقمي (digital_evidence_type)', 'قائمة', False,
         '٨ أنواع - انظر أدناه'),
        ('مستوى الأدلة (evidence_level)', 'قائمة', False,
         '٤ مستويات - انظر أدناه'),
        ('عدد مصادر الأدلة (evidence_sources_count)', 'رقم', False, ''),
    ]))

    story.append(Spacer(1, 4))
    story.append(Paragraph(ar('خيارات نوع الدليل الرقمي (٨ أنواع):'), styles['h3']))
    story.append(code_label_table(styles, [
        ('caesar_files', 'ملفات قيصر'),
        ('leaked_database', 'تسريبات قاعدة بيانات'),
        ('social_media', 'وسائل التواصل الاجتماعي'),
        ('news_report', 'تقرير إخباري'),
        ('ngo_report', 'تقرير منظمة'),
        ('civil_registry', 'سجل مدني'),
        ('official_document', 'وثيقة رسمية'),
        ('other', 'أخرى'),
    ], 'الرمز', 'النوع'))

    story.append(Spacer(1, 4))
    story.append(Paragraph(ar('خيارات مستوى الأدلة (٤ مستويات):'), styles['h3']))
    story.append(code_label_table(styles, [
        ('high', 'عالي - أدلة موثقة متعددة'),
        ('medium', 'متوسط - دليل واحد موثق'),
        ('low', 'منخفض - شهادة شفهية فقط'),
        ('unverified', 'غير مُتحقق منه'),
    ], 'الرمز', 'المستوى'))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('تفاصيل الدليل الرقمي (تظهر عند اختيار نوع):'), styles['h2']))
    story.append(field_table(styles, [
        ('رابط الدليل (digital_evidence_url)', 'رابط', False, ''),
        ('حالة الرابط (digital_evidence_url_status)', 'قائمة', False,
         '٦ خيارات - انظر أدناه'),
        ('رابط المصدر الأصلي (source_url)', 'رابط', False, 'حتى لو محذوف'),
        ('لقطة شاشة (digital_evidence_screenshot)', 'رفع ملف', False, 'صورة/PDF حتى 15MB'),
        ('تاريخ الدليل (digital_evidence_date)', 'تاريخ', False, ''),
        ('الاسم الوارد في الدليل (digital_evidence_person_name)', 'نص', False, ''),
        ('تاريخ الوفاة في الدليل (digital_evidence_death_date)', 'تاريخ', False, ''),
        ('وصف الدليل (digital_evidence_description)', 'نص طويل', False, ''),
    ]))

    story.append(Spacer(1, 4))
    story.append(Paragraph(ar('خيارات حالة الرابط (٦ خيارات):'), styles['h3']))
    story.append(code_label_table(styles, [
        ('active', 'فعّال'),
        ('deleted', 'محذوف'),
        ('archived', 'مؤرشف'),
        ('unknown', 'غير معروف'),
        ('no_url', 'لم يكن هناك رابط أصلاً'),
        ('url_forgotten', 'الرابط غير متاح (نُسي)'),
    ], 'الرمز', 'الحالة'))

    story.append(PageBreak())

    # Civil registry
    story.append(Paragraph(ar('حالة السجل المدني (النفوس):'), styles['h2']))
    story.append(field_table(styles, [
        ('حالة السجل المدني (civil_registry_status)', 'قائمة', False,
         '٤ خيارات - انظر أدناه'),
        ('تاريخ مراجعة النفوس (civil_registry_date)', 'تاريخ', False, ''),
        ('وثيقة من النفوس (civil_registry_document)', 'رفع ملف', False, 'إخراج قيد حتى 15MB'),
    ]))

    story.append(Spacer(1, 4))
    story.append(Paragraph(ar('خيارات حالة السجل المدني (٤ خيارات):'), styles['h3']))
    story.append(code_label_table(styles, [
        ('alive', 'حي في السجل المدني'),
        ('deceased', 'متوفى في السجل المدني'),
        ('unknown', 'غير معروف'),
        ('not_checked', 'لم يتم التحقق'),
    ], 'الرمز', 'الحالة'))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('وثائق وأدلة إضافية (ديناميكي - عدد غير محدود):'), styles['h2']))
    story.append(field_table(styles, [
        ('نوع الوثيقة (record_doc_type_N)', 'قائمة', False,
         '١٢ نوع - انظر أدناه'),
        ('تاريخ الوثيقة (record_doc_date_N)', 'تاريخ', False, ''),
        ('الملف (record_doc_file_N)', 'رفع ملف', False, 'صورة/PDF/DOC حتى 15MB'),
        ('رابط المصدر (record_doc_url_N)', 'رابط', False, ''),
        ('وصف مختصر (record_doc_desc_N)', 'نص', False, ''),
    ]))

    story.append(Spacer(1, 4))
    story.append(Paragraph(ar('خيارات نوع الوثيقة (١٢ نوع):'), styles['h3']))
    story.append(code_label_table(styles, [
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
    ], 'الرمز', 'النوع'))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('معلومات متضاربة:'), styles['h2']))
    story.append(field_table(styles, [
        ('يوجد تضارب (has_conflicting_info)', 'مربع تحقق', False, ''),
        ('تفاصيل التضارب (conflicting_info_details)', 'نص طويل', False, 'يظهر عند التحقق'),
    ]))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('الشهود (ديناميكي - عدد غير محدود):'), styles['h2']))
    story.append(field_table(styles, [
        ('اسم الشاهد (w-name)', 'نص', False, 'الاسم الكامل'),
        ('هاتف الشاهد (w-phone)', 'هاتف', False, ''),
        ('صلة الشاهد بالضحية (w-relation)', 'نص', False, ''),
        ('شهادته (w-testimony)', 'نص طويل', False, 'ماذا شهد هذا الشخص؟'),
    ]))

    story.append(PageBreak())

    # ════════════════════════ 7. STEP 5 ════════════════════════
    story.append(Paragraph(ar('٧. الخطوة ٥: العائلة والبيانات الاجتماعية'), styles['h1']))
    story.append(header_line())

    story.append(Paragraph(ar('البيانات العائلية:'), styles['h2']))
    story.append(field_table(styles, [
        ('الحالة الاجتماعية (marital)', 'قائمة', False,
         '٤ خيارات - انظر أدناه'),
        ('اسم ولي الأمر / المعرّف (guardian_name)', 'نص', False, ''),
        ('صلة ولي الأمر (guardian_relation)', 'نص', False, ''),
        ('هاتف ولي الأمر (guardian_phone)', 'هاتف', False, ''),
    ]))

    story.append(Spacer(1, 4))
    story.append(Paragraph(ar('خيارات الحالة الاجتماعية (٤ خيارات):'), styles['h3']))
    story.append(code_label_table(styles, [
        ('single', 'أعزب/عزباء'),
        ('married', 'متزوج/ة'),
        ('divorced', 'مطلق/ة'),
        ('widowed', 'أرمل/ة'),
    ], 'الرمز', 'الحالة'))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('بيانات الزوج/ة (تظهر عند متزوج/أرمل):'), styles['h2']))
    story.append(field_table(styles, [
        ('اسم الزوج/ة (spouse_name)', 'نص', False, ''),
        ('هاتف الزوج/ة (spouse_phone)', 'هاتف', False, ''),
    ]))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('بيانات الزوج/ة السابق/ة (تظهر عند مطلق):'), styles['h2']))
    story.append(field_table(styles, [
        ('اسم الزوج/ة السابق/ة (ex_spouse_name)', 'نص', False, ''),
        ('هل يوجد أطفال من الزواج السابق (has_kids_w)', 'قائمة', False, 'نعم | لا'),
        ('عدد الأطفال (kids_count_w)', 'رقم', False, 'يظهر عند نعم'),
    ]))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('المسح الاجتماعي للأطفال (ديناميكي - عدد غير محدود لكل طفل):'), styles['h2']))
    story.append(field_table(styles, [
        ('اسم الطفل (ec-name)', 'نص', False, ''),
        ('جنس الطفل (ec-gender)', 'قائمة', False, 'ذكر | أنثى'),
        ('سنة ميلاد الطفل (ec-birth)', 'رقم', False, '١٩٠٠ - ٢٠٢٦'),
        ('التحصيل العلمي (ec-edu)', 'قائمة', False,
         'أمّي | ابتدائية | إعدادية | ثانوية | معهد | بكالوريوس | ماجستير | دكتوراه'),
        ('شو عم يدرس هلق؟ (ec-school)', 'نص', False, 'إذا عم يكمل دراسة'),
        ('العمل (ec-work)', 'نص', False, ''),
        ('ملاحظات صحية (ec-health)', 'نص', False, ''),
        ('احتياجات خاصة (ec-special)', 'اختيار', False, 'نعم | لا'),
    ]))

    story.append(PageBreak())

    # ════════════════════════ 8. STEP 6 ════════════════════════
    story.append(Paragraph(ar('٨. الخطوة ٦: السكن والتعليم والصحة'), styles['h1']))
    story.append(header_line())

    story.append(Paragraph(ar('البيانات السكنية والاقتصادية:'), styles['h2']))
    story.append(field_table(styles, [
        ('المنطقة / الحي (address_area)', 'قائمة', False, '٢٢ منطقة - انظر أدناه'),
        ('العنوان الحالي (address)', 'نص + قائمة مقترحة', True, ''),
        ('نوع السكن (housing_type)', 'قائمة', True, '٥ خيارات - انظر أدناه'),
        ('مبلغ الإيجار (rent_amount)', 'نص', False, 'بالليرة السورية'),
        ('الوضع الوظيفي (employment)', 'نص', False, 'مخفي للمتوفين/المغيّبين'),
        ('المهنة (profession)', 'نص', False, 'مخفي للمتوفين/المغيّبين'),
        ('جهة العمل (employer)', 'نص', False, 'مخفي للمتوفين/المغيّبين'),
        ('المعيل (breadwinner)', 'نص', False, 'اسم المعيل'),
        ('مهنة المعيل (breadwinner_job)', 'نص', False, ''),
        ('صلة المعيل (breadwinner_relation)', 'قائمة', False,
         'نفس خيارات صلة المُبلِّغ (١٢ خيار)'),
    ]))

    story.append(Spacer(1, 4))
    story.append(Paragraph(ar('خيارات المنطقة / الحي (٢٢ منطقة):'), styles['h3']))
    story.append(opts_table(styles, [
        'الرمل الجنوبي', 'قنينص', 'الحفة', 'الصليبة', 'العوينة',
        'الأشرفية', 'بستان الصيداوي', 'الطابيات', 'شيخ ضاهر',
        'حي القصور', 'مرتقلا', 'شارع انطاكيا', 'حي السجن',
        'مشروع القلعة', 'شارع ميسلون', 'سوق الداية', 'الريجي',
        'شارع بور سعيد', 'حي الفاروس', 'طريق الحرش', 'خارج اللاذقية', 'أخرى'
    ], ncols=4))

    story.append(Spacer(1, 4))
    story.append(Paragraph(ar('خيارات نوع السكن (٥ خيارات):'), styles['h3']))
    story.append(opts_table(styles, ['ملك', 'إيجار', 'رهن', 'مستضاف', 'أخرى'], ncols=5))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('التحصيل العلمي:'), styles['h2']))
    story.append(field_table(styles, [
        ('المستوى التعليمي (education)', 'قائمة', False, '٨ خيارات - انظر أدناه'),
        ('نوع الدراسة (edu_type)', 'قائمة', False, '٨ خيارات - انظر أدناه'),
        ('الاختصاص (edu_specialization)', 'نص', False, ''),
        ('الجامعة / المعهد (edu_university)', 'نص', False, ''),
    ]))

    story.append(Spacer(1, 4))
    story.append(Paragraph(ar('خيارات المستوى التعليمي (٨ خيارات):'), styles['h3']))
    story.append(opts_table(styles, [
        'أمّي', 'ابتدائية', 'إعدادية', 'ثانوية',
        'معهد', 'بكالوريوس', 'ماجستير', 'دكتوراه'
    ], ncols=4))

    story.append(Spacer(1, 4))
    story.append(Paragraph(ar('خيارات نوع الدراسة (٨ خيارات):'), styles['h3']))
    story.append(opts_table(styles, [
        'علمي', 'أدبي', 'شرعي', 'مهني',
        'تجاري', 'صناعي', 'نسوي', 'أخرى'
    ], ncols=4))

    story.append(PageBreak())

    # Health
    story.append(Paragraph(ar('الحالة الصحية (مخفية للمتوفين والمغيّبين):'), styles['h2']))
    story.append(field_table(styles, [
        ('الأمراض المزمنة (chronic_list)', 'مربعات تحقق', False,
         '٢٢ مرض - انظر أدناه'),
        ('أمراض أخرى (other_diseases)', 'نص', False, 'أمراض غير مذكورة'),
        ('احتياجات خاصة (has_special_needs)', 'مربع تحقق', False, ''),
        ('تفاصيل الاحتياجات (special_needs_details)', 'نص', False, 'يظهر عند التحقق'),
    ]))

    story.append(Spacer(1, 4))
    story.append(Paragraph(ar('قائمة الأمراض المزمنة (٢٢ مرض):'), styles['h3']))
    story.append(opts_table(styles, [
        'ضغط الدم', 'السكري', 'الربو',
        'أمراض القلب', 'الكلى', 'الكبد',
        'السرطان', 'الصرع', 'الثلاسيميا',
        'فقر الدم', 'التهاب المفاصل', 'هشاشة العظام',
        'الغدة الدرقية', 'أمراض الجهاز الهضمي', 'أمراض الجهاز التنفسي',
        'أمراض نفسية', 'اكتئاب', 'اضطراب ما بعد الصدمة (PTSD)',
        'إعاقة حركية', 'إعاقة بصرية', 'إعاقة سمعية',
        'أخرى'
    ], ncols=3))

    story.append(PageBreak())

    # ════════════════════════ 9. STEP 7 ════════════════════════
    story.append(Paragraph(ar('٩. الخطوة ٧: القانوني والملاحظات والمنهجية'), styles['h1']))
    story.append(header_line())

    story.append(Paragraph(ar('المشاكل القانونية والجمعيات:'), styles['h2']))
    story.append(field_table(styles, [
        ('هل يوجد مشاكل قانونية؟ (legal)', 'قائمة', False, 'نعم | لا'),
        ('تفاصيل المشاكل القانونية (legal_details)', 'نص طويل', False, 'يظهر عند "نعم"'),
        ('مسجل لدى جمعية؟ (assoc)', 'قائمة', False, 'نعم | لا'),
        ('اسم الجمعية (assoc_name)', 'نص', False, 'يظهر عند "نعم"'),
        ('نوع الخدمة المطلوبة (service_type)', 'نص', False, 'توثيق، مساعدة قانونية، إلخ'),
        ('مسجل رسمياً (is_officially_registered)', 'مربع تحقق', False,
         'مسجل رسمياً لدى الجهات المعنية'),
    ]))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('الملاحظات والمنهجية:'), styles['h2']))
    story.append(field_table(styles, [
        ('ملاحظات إضافية (notes)', 'نص طويل', False, ''),
        ('نوع المنهجية (methodology_type)', 'قائمة', False, '٨ أنواع - انظر أدناه'),
        ('ملاحظات المنهجية (methodology_notes)', 'نص طويل', False, ''),
    ]))

    story.append(Spacer(1, 4))
    story.append(Paragraph(ar('خيارات نوع المنهجية (٨ أنواع):'), styles['h3']))
    story.append(code_label_table(styles, [
        ('interview', 'مقابلة شخصية'),
        ('document_review', 'مراجعة وثائق'),
        ('open_source', 'تحقيق مصادر مفتوحة'),
        ('field_visit', 'زيارة ميدانية'),
        ('remote_interview', 'مقابلة عن بعد'),
        ('database_cross_ref', 'تقاطع قواعد بيانات'),
        ('witness_testimony', 'شهادة شاهد'),
        ('other', 'أخرى'),
    ], 'الرمز', 'النوع'))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('علامات المنهجية (Tags) - ١٦ علامة وصفية:'), styles['h2']))
    story.append(Paragraph(ar('يمكن اختيار عدة علامات لتصنيف طريقة جمع البيانات:'), styles['body']))
    story.append(Spacer(1, 3))
    story.append(opts_table(styles, [
        'مقابلة مباشرة', 'مقابلة هاتفية', 'مقابلة عبر الإنترنت',
        'شهادة شاهد عيان', 'شهادة أحد الأقارب', 'تسريبات قيصر',
        'وثائق رسمية', 'بيانات السجل المدني', 'تقارير إعلامية',
        'منشورات وسائل التواصل', 'تقارير منظمات حقوقية', 'أرشيف رقمي',
        'تحليل صور/فيديو', 'تقاطع معلومات من مصادر متعددة', 'زيارة ميدانية',
        'بلاغ مجهول'
    ], ncols=3))

    story.append(PageBreak())

    # ════════════════════════ 10. CASE TYPES ════════════════════════
    story.append(Paragraph(ar('١٠. تصنيف الحالات والأنواع الفرعية'), styles['h1']))
    story.append(header_line())

    story.append(Paragraph(ar('التصنيفات الرئيسية (٣):'), styles['h3']))
    story.append(draw_status_diagram(460))
    story.append(Spacer(1, 8))

    story.append(Paragraph(ar('الأنواع الفرعية (٨ أنواع - تتغير ديناميكياً):'), styles['h3']))
    ct_data = [[
        Paragraph(ar('الرمز'), styles['th']),
        Paragraph(ar('الرئيسي'), styles['th']),
        Paragraph(ar('النوع الفرعي'), styles['th']),
    ]]
    for subtype, main_type, code in [
        ('اختفاء قسري - لا معلومات', 'مغيّب قسراً', 'enforced_disappearance_no_info'),
        ('اختفاء قسري - تسريبات تؤكد الوفاة (مؤكد بالنفوس)', 'مغيّب/متوفى', 'enforced_disappearance_leaked_confirmed_dead'),
        ('اختفاء قسري - تسريبات تؤكد الوفاة (غير مؤكد)', 'مغيّب/متوفى', 'enforced_disappearance_leaked_not_confirmed'),
        ('اختفاء قسري - متوفى بحسب النفوس', 'مغيّب/متوفى', 'enforced_disappearance_civil_registry_dead'),
        ('اختفاء قسري - شهود (حي بالنفوس)', 'مغيّب قسراً', 'enforced_disappearance_witnesses_alive_registry'),
        ('ناجٍ - لديه وثائق', 'ناجٍ', 'survivor_documented'),
        ('ناجٍ - بدون وثائق', 'ناجٍ', 'survivor_undocumented'),
        ('متوفى - ملفات قيصر', 'متوفى', 'deceased_caesar_files'),
    ]:
        ct_data.append([
            Paragraph(code, styles['tc_small']),
            Paragraph(ar(main_type), styles['tc']),
            Paragraph(ar(subtype), styles['tcr']),
        ])
    ct_tbl = Table(ct_data, colWidths=[200, 70, 190])
    ct_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHTER_BG, white]),
    ]))
    story.append(ct_tbl)

    story.append(PageBreak())

    # ════════════════════════ 11. EVIDENCE ════════════════════════
    story.append(Paragraph(ar('١١. مستويات الأدلة وحالات التحقق'), styles['h1']))
    story.append(header_line())

    story.append(Paragraph(ar('مستويات قوة الأدلة:'), styles['h3']))
    story.append(draw_evidence_levels(460))
    story.append(Spacer(1, 8))

    story.append(Paragraph(ar('حالات التحقق (٤ حالات):'), styles['h3']))
    story.append(code_label_table(styles, [
        ('Verified', 'تم التحقق - مصادر مستقلة متعددة'),
        ('Corroborated', 'مؤيَّد بأدلة - أدلة جزئية أو مصدر إضافي'),
        ('Unverified', 'لم يُتحقق منه - بانتظار التحقق'),
        ('Conflicting', 'معلومات متضاربة - تناقضات بين المصادر'),
    ], 'الرمز', 'الحالة'))

    story.append(PageBreak())

    # ════════════════════════ 12. CHAIN OF CUSTODY ════════════════════════
    story.append(Paragraph(ar('١٢. سلسلة الحفظ الرقمية ومسار المراجعة'), styles['h1']))
    story.append(header_line())

    story.append(Paragraph(ar('مسار حالة السجل (٤ مراحل):'), styles['h3']))
    story.append(draw_verification_flow(460))
    story.append(Spacer(1, 8))

    story.append(Paragraph(ar('تسميات حالات السجل:'), styles['h3']))
    story.append(code_label_table(styles, [
        ('draft', 'مسودة'),
        ('reviewed', 'مراجَع'),
        ('verified', 'موثّق'),
        ('locked', 'مقفل'),
    ], 'الرمز', 'الحالة'))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('الانتقالات المسموحة بين الحالات:'), styles['h3']))
    trans_data = [[
        Paragraph(ar('الحالات المسموح الانتقال إليها'), styles['th']),
        Paragraph(ar('من'), styles['th']),
    ]]
    for from_s, to_s in [
        ('مسودة (draft)', 'مراجَع (reviewed)'),
        ('مراجَع (reviewed)', 'مسودة (draft) أو موثّق (verified)'),
        ('موثّق (verified)', 'مراجَع (reviewed) أو مقفل (locked)'),
        ('مقفل (locked)', 'موثّق (verified) - يتطلب سبب'),
    ]:
        trans_data.append([
            Paragraph(ar(to_s), styles['tcr']),
            Paragraph(ar(from_s), styles['tc']),
        ])
    trans_tbl = Table(trans_data, colWidths=[300, 160])
    trans_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHTER_BG, white]),
    ]))
    story.append(trans_tbl)

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('الحقول الإلزامية حسب مرحلة التحقق (بيركلي):'), styles['h3']))
    berk_data = [[
        Paragraph(ar('الحقول الإلزامية'), styles['th']),
        Paragraph(ar('المرحلة'), styles['th']),
    ]]
    for stage, fields in [
        ('مراجَع (reviewed)',
         'first_name, father_name, last_name, status, source_type, collector_name, collection_date'),
        ('موثّق (verified)',
         'كل حقول المراجعة + evidence_level + verification_status'),
        ('مقفل (locked)',
         'كل حقول التوثيق - لا يمكن التعديل بعد القفل'),
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
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHTER_BG, white]),
    ]))
    story.append(berk_tbl)

    story.append(Spacer(1, 8))
    story.append(Paragraph(ar('عناصر سلسلة الحفظ:'), styles['h3']))
    for item in [
        'اسم جامع البيانات (collector_name)',
        'تاريخ الجمع (collection_date)',
        'المعرّف الفريد (UUID) لكل حالة',
        'طابع زمني: تاريخ الإنشاء (created_at) وآخر تعديل',
        'بصمة رقمية SHA-256 لكل ملف مرفق (photo_hash, document_hash, screenshot_hash)',
        'سجل التعديلات (record_changes) لتتبع كل تغيير',
        'حذف ناعم (deleted_at) بدل الحذف النهائي',
    ]:
        story.append(Paragraph(ar(f'• {item}'), styles['bullet']))

    story.append(PageBreak())

    # ════════════════════════ 13. VOLUNTEERS ════════════════════════
    story.append(Paragraph(ar('١٣. إدارة المتطوعين والأعضاء'), styles['h1']))
    story.append(header_line())

    story.append(Paragraph(ar('حالات المتطوعين (٣ حالات):'), styles['h3']))
    story.append(code_label_table(styles, [
        ('active', 'نشط'),
        ('inactive', 'غير نشط'),
        ('suspended', 'معلّق'),
    ], 'الرمز', 'الحالة'))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('أدوار المتطوعين (٩ أدوار):'), styles['h3']))
    story.append(opts_table(styles, [
        'جامع بيانات', 'محقق ميداني', 'مدقق معلومات',
        'مترجم', 'دعم نفسي', 'مستشار قانوني',
        'إداري', 'متطوع عام', 'أخرى'
    ], ncols=3))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('حالات الأعضاء (٤ حالات):'), styles['h3']))
    story.append(code_label_table(styles, [
        ('active', 'نشط'),
        ('inactive', 'غير نشط'),
        ('suspended', 'معلّق'),
        ('honorary', 'فخري'),
    ], 'الرمز', 'الحالة'))

    story.append(Spacer(1, 6))
    story.append(Paragraph(ar('أنواع العضوية (٦ أنواع):'), styles['h3']))
    story.append(opts_table(styles, [
        'عضو مؤسس', 'عضو عامل', 'عضو منتسب',
        'عضو فخري', 'عضو داعم', 'أخرى'
    ], ncols=3))

    story.append(PageBreak())

    # ════════════════════════ 14. DETENTION FACILITIES ════════════════════════
    story.append(Paragraph(ar('١٤. ملحق: مراكز الاحتجاز المعروفة (٢٣ مركز)'), styles['h1']))
    story.append(header_line())

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
    fac_data = [[
        Paragraph(ar('المركز'), styles['th']),
        Paragraph('#', styles['th']),
    ]]
    for i, f in enumerate(facilities, 1):
        fac_data.append([
            Paragraph(ar(f), styles['tcr']),
            Paragraph(str(i), styles['tc']),
        ])
    fac_tbl = Table(fac_data, colWidths=[410, 50])
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

    # ════════════════════════ 15. REQUIRED FIELDS ════════════════════════
    story.append(Paragraph(ar('١٥. ملحق: الحقول الإلزامية (١٤ حقل)'), styles['h1']))
    story.append(header_line())

    req_data = [[
        Paragraph(ar('الخطوة'), styles['th']),
        Paragraph(ar('الحقل'), styles['th']),
    ]]
    for step, field in [
        ('١', 'تصنيف الحالة (status)'),
        ('١', 'اسم المُبلِّغ (reporter_name)'),
        ('١', 'صلة المُبلِّغ بالضحية (reporter_relation)'),
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
    ]:
        req_data.append([
            Paragraph(ar(step), styles['tc']),
            Paragraph(ar(field), styles['tcr']),
        ])
    req_tbl = Table(req_data, colWidths=[50, 410])
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
    story.append(info_box(
        'ملاحظة: لا يحتوي النظام حالياً على حقول لأساليب التعذيب أو العنف. '
        'يتم توثيق هذه المعلومات ضمن حقل "وصف تجربة الاعتقال" (survivor_cv_text) '
        'وحقل "ملاحظات إضافية" (notes) كنص حر.',
        styles['body'], color=HexColor('#fef9e7'), border_color=WARN
    ))

    # ════════════════════════ CLOSING ════════════════════════
    story.append(Spacer(1, 1.5 * cm))
    story.append(HRFlowable(width="70%", thickness=2, color=PRIMARY,
                            spaceAfter=14, spaceBefore=6, hAlign='CENTER'))
    story.append(Paragraph(ar('جمعية حقنا'), styles['title']))
    story.append(Paragraph(ar('نحو عدالة انتقالية شاملة وتوثيق يحفظ الحقوق'), styles['subtitle']))
    story.append(Spacer(1, 0.5 * cm))
    story.append(info_box(
        'وثيقة سرية للاستخدام الداخلي لمتطوعي جمعية حقنا فقط.',
        styles['body_center'], color=HexColor('#fdedec'), border_color=DANGER
    ))
    story.append(Spacer(1, 0.8 * cm))
    story.append(Paragraph(ar('تم تطوير هذا النظام بشكل خاص لمتطوعي جمعية حقنا'), styles['body_center']))
    story.append(Paragraph(ar('من قبل: مهند حسون'), styles['body_center']))
    story.append(Paragraph('bugmuha@gmail.com', styles['body_center']))

    def add_page_number(canvas, doc):
        page_num = canvas.getPageNumber()
        canvas.saveState()
        canvas.setFont('Amiri', 8)
        canvas.setFillColor(MEDIUM_TEXT)
        text = ar(f'جمعية حقنا - بروتوكول التوثيق الشامل - صفحة {page_num}')
        canvas.drawCentredString(page_w / 2, 1.0 * cm, text)
        canvas.restoreState()

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    print(f'PDF generated: {output_path}')


if __name__ == '__main__':
    build_pdf('/home/user/dd/haqquna_protocol_ar.pdf')
