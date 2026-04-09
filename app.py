#!/usr/bin/env python3
"""
HAQQUNA - Victim Documentation System
Based on the Berkeley Protocol on Digital Open Source Investigations
Fully offline system for documenting survivors, forcibly disappeared, and deceased victims.
"""

import os
import sys
import socket
import sqlite3
import subprocess
import hashlib
import json
import base64
import secrets
import time
import re
import shutil
import zipfile
from datetime import datetime, timedelta
from functools import wraps
from io import BytesIO
from urllib.parse import quote

from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    jsonify, send_file, session, g, make_response, send_from_directory
)
from markupsafe import Markup
from werkzeug.security import generate_password_hash, check_password_hash


def safe_int(value, default=None):
    """Safely convert a value to int, returning default if conversion fails."""
    if value is None or value == '':
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

# ---------------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'registry.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')

app = Flask(__name__)

# Persist secret_key so sessions survive restarts
SECRET_KEY_FILE = os.path.join(BASE_DIR, '.secret_key')
if os.path.exists(SECRET_KEY_FILE):
    with open(SECRET_KEY_FILE, 'r') as f:
        app.secret_key = f.read().strip()
else:
    _generated_key = secrets.token_hex(32)
    with open(SECRET_KEY_FILE, 'w') as f:
        f.write(_generated_key)
    try:
        os.chmod(SECRET_KEY_FILE, 0o600)
    except OSError:
        pass
    app.secret_key = _generated_key

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB per request
app.permanent_session_lifetime = timedelta(hours=8)


def generate_csrf_token():
    """Generate or retrieve a CSRF token for the current session."""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


def validate_csrf_token():
    """Validate CSRF token on state-changing requests.  Returns True if valid."""
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return True
    # Skip CSRF for JSON API calls (they use X-Requested-With header)
    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    token = request.form.get('_csrf_token') or request.headers.get('X-CSRF-Token')
    return token and token == session.get('_csrf_token')


@app.before_request
def csrf_protect():
    """Enforce CSRF protection on all POST/PUT/DELETE requests."""
    if request.method in ('POST', 'PUT', 'DELETE'):
        # Exempt the public entry form AJAX submissions and API endpoints
        if request.endpoint and request.endpoint.startswith('api_'):
            pass  # API endpoints use JSON / X-Requested-With
        elif request.is_json:
            pass
        elif not validate_csrf_token():
            print(f"   🔒 CSRF REJECTED: {request.method} {request.path} (endpoint: {request.endpoint})")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                from flask import abort
                abort(403)
            flash('انتهت صلاحية النموذج. يرجى المحاولة مرة أخرى.', 'error')
            return redirect(request.referrer or url_for('index'))


@app.before_request
def check_session_timeout():
    """Auto-logout after 8 hours of inactivity."""
    if session.get('is_admin') and session.get('login_time'):
        if time.time() - session['login_time'] > 8 * 3600:
            session.clear()
            flash('انتهت الجلسة، يرجى تسجيل الدخول مجدداً', 'error')
            return redirect(url_for('admin_login'))


@app.before_request
def enforce_role_permissions():
    """Enforce role-based access control.
    - admin: full access
    - data_entry: entry form only (submit new records)
    - viewer: read-only access to dashboard, records list, record detail
    """
    if not session.get('is_admin'):
        return
    role = session.get('user_role', 'admin')
    if role == 'admin':
        return

    endpoint = request.endpoint or ''
    # Common allowed endpoints for all logged-in roles
    common_allowed = ('admin_login', 'admin_logout', 'static', 'uploaded_file')

    # Common endpoints for all roles: notifications + edit suggestions + record browsing
    shared_endpoints = ('notification_stream', 'api_notifications_unread',
                        'api_notifications_mark_read', 'suggest_record_edit',
                        'admin_records', 'admin_record_detail', 'api_records')

    if role == 'data_entry':
        # data_entry can access entry form, submit, browse records, suggest edits, notifications
        allowed = common_allowed + ('entry_form', 'entry_submit', 'admin_dashboard',
                                     'api_draft_save', 'api_draft_load', 'api_draft_clear') + shared_endpoints
        if endpoint not in allowed:
            flash('صلاحيتك محدودة بصفحة إدخال البيانات والسجلات فقط', 'error')
            return redirect(url_for('entry_form'))

    elif role == 'viewer':
        # Viewer: read-only + suggest edits + notifications
        viewer_write_allowed = common_allowed + shared_endpoints
        if request.method != 'GET':
            if endpoint not in viewer_write_allowed:
                flash('ليس لديك صلاحية لتنفيذ هذا الإجراء (مشاهد فقط)', 'error')
                return redirect(request.referrer or url_for('admin_dashboard'))
        viewer_allowed = common_allowed + (
            'admin_dashboard', 'admin_dashboard_print', 'admin_records', 'admin_record_detail',
            'admin_record_pdf', 'api_stats', 'api_records_export',
        ) + shared_endpoints
        if endpoint not in viewer_allowed:
            flash('صلاحيتك محدودة بمشاهدة السجلات فقط', 'error')
            return redirect(url_for('admin_dashboard'))

ADMIN_PASSWORD_FILE = os.path.join(BASE_DIR, 'admin_password.hash')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')


def _get_admin_password_hash():
    """Read the hashed admin password from file, create default if missing."""
    if os.path.exists(ADMIN_PASSWORD_FILE):
        with open(ADMIN_PASSWORD_FILE, 'r') as f:
            return f.read().strip()
    # First run: use env var or generate random password (never hardcode in source)
    default_password = os.environ.get('HAQQUNA_DEFAULT_PASSWORD', '')
    if not default_password:
        default_password = secrets.token_urlsafe(16)
        import sys
        print(f"[HAQQUNA] Generated initial admin password: {default_password}", file=sys.stderr)
        print(f"[HAQQUNA] Set HAQQUNA_DEFAULT_PASSWORD env var to override.", file=sys.stderr)
    default_hash = generate_password_hash(default_password)
    with open(ADMIN_PASSWORD_FILE, 'w') as f:
        f.write(default_hash)
    return default_hash


def _set_admin_password(new_password):
    """Save a new hashed admin password."""
    with open(ADMIN_PASSWORD_FILE, 'w') as f:
        f.write(generate_password_hash(new_password))


# Login rate limiting
_login_attempts = {}  # {ip: [(timestamp, ...), ...]}
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 15

def _normalize_children(children):
    """Normalize children data: map camelCase keys to snake_case."""
    for c in children:
        if 'birthYear' in c and 'birth_year' not in c:
            c['birth_year'] = c['birthYear']
        if 'healthDetails' in c and 'health_notes' not in c:
            c['health_notes'] = c['healthDetails']
        if 'healthStatus' in c and 'health_notes' not in c:
            c['health_notes'] = c.get('healthDetails', '')
        if 'job' in c and 'employment' not in c:
            c['employment'] = c['job']
        if 'university' in c and 'school' not in c:
            c['school'] = c['university']
    return children


# Register JSON filter for templates
@app.template_filter('from_json')
def from_json_filter(value):
    """Parse JSON string to Python object in templates."""
    try:
        data = json.loads(value) if value else []
        if isinstance(data, list):
            _normalize_children(data)
        return data
    except (json.JSONDecodeError, TypeError):
        return []

# All available PDF columns definition
PDF_COLUMNS = [
    ('id', '#'),
    ('first_name', 'الاسم'),
    ('father_name', 'الأب'),
    ('last_name', 'الكنية'),
    ('mother_name', 'اسم الأم'),
    ('status', 'الحالة'),
    ('province', 'المحافظة'),
    ('national_id', 'الرقم الوطني'),
    ('family_book_number', 'رقم دفتر العائلة'),
    ('phone', 'الهاتف'),
    ('contact_phone', 'رقم التواصل'),
    ('gender', 'الجنس'),
    ('birth_year', 'سنة الميلاد'),
    ('arrest_year', 'سنة الاعتقال'),
    ('arrest_month', 'شهر الاعتقال'),
    ('arrest_day', 'يوم الاعتقال'),
    ('arrest_authority', 'الجهة'),
    ('arrest_place', 'مكان الاحتجاز'),
    ('arrest_reason', 'سبب الاعتقال'),
    ('arrest_causer', 'المتسبب بالاعتقال'),
    ('release_year', 'سنة الإفراج'),
    ('death_year', 'سنة الوفاة'),
    ('death_place', 'مكان الوفاة'),
    ('spouse_name', 'الزوج/ة'),
    ('spouse_phone', 'هاتف الزوج/ة'),
    ('ex_spouse_name', 'الزوج/ة السابق/ة'),
    ('kids_count', 'عدد الأطفال'),
    ('kids_under_18_count', 'قاصرين'),
    ('education', 'التعليم'),
    ('edu_type', 'نوع الدراسة'),
    ('edu_specialization', 'الاختصاص'),
    ('edu_university', 'الجامعة/المعهد'),
    ('address', 'العنوان'),
    ('housing_type', 'السكن'),
    ('rent_amount', 'الإيجار'),
    ('employment', 'العمل'),
    ('profession', 'المهنة'),
    ('employer', 'جهة العمل'),
    ('marital', 'الحالة الاجتماعية'),
    ('blood_type', 'زمرة الدم'),
    ('chronic', 'أمراض مزمنة'),
    ('has_hypertension', 'ضغط دم'),
    ('has_diabetes', 'سكري'),
    ('other_diseases', 'أمراض أخرى'),
    ('has_special_needs', 'احتياجات خاصة'),
    ('special_needs_details', 'تفاصيل الاحتياجات'),
    ('breadwinner', 'المعيل'),
    ('breadwinner_job', 'مهنة المعيل'),
    ('breadwinner_relation', 'صلة المعيل'),
    ('guardian_name', 'ولي الأمر'),
    ('guardian_relation', 'صلة ولي الأمر'),
    ('guardian_phone', 'هاتف ولي الأمر'),
    ('case_type', 'نوع الحالة'),
    ('evidence_level', 'مستوى الأدلة'),
    ('verification_status', 'حالة التحقق'),
    ('evidence_sources_count', 'عدد مصادر الأدلة'),
    ('digital_evidence_type', 'نوع الدليل الرقمي'),
    ('digital_evidence_url_status', 'حالة رابط الدليل'),
    ('digital_evidence_person_name', 'الاسم في الدليل'),
    ('civil_registry_status', 'حالة السجل المدني'),
    ('has_conflicting_info', 'معلومات متضاربة'),
    ('last_known_location', 'آخر مكان معروف'),
    ('last_known_alive_date', 'آخر تاريخ حياة'),
    ('reporter_name', 'المبلغ'),
    ('reporter_relation', 'صلة المبلغ'),
    ('reporter_phone', 'هاتف المبلغ'),
    ('collector_name', 'جامع البيانات'),
    ('collection_date', 'تاريخ الجمع'),
    ('legal', 'مشاكل قانونية'),
    ('assoc_name', 'الجمعية'),
    ('service_type', 'نوع الخدمة'),
    ('is_officially_registered', 'مسجل رسمياً'),
    ('notes', 'ملاحظات'),
    ('children_summary', 'تفاصيل الأطفال'),
    ('minors_summary', 'أسماء القاصرين'),
    ('kids_u13_names', 'أسماء أطفال تحت 13'),
    ('kids_u13_ages', 'أعمار أطفال تحت 13'),
]

# Default columns for PDF
DEFAULT_PDF_COLS = [
    'id', 'first_name', 'father_name', 'last_name', 'status',
    'province', 'national_id', 'arrest_year', 'arrest_authority',
    'arrest_place', 'spouse_name', 'kids_count', 'kids_under_18_count', 'education'
]

# ---------------------------------------------------------------------------
# Syrian provinces and authorities constants
# ---------------------------------------------------------------------------
PROVINCES = [
    'اللاذقية', 'دمشق', 'ريف دمشق', 'حلب', 'حمص', 'حماة',
    'إدلب', 'درعا', 'السويداء', 'القنيطرة', 'الرقة',
    'دير الزور', 'الحسكة', 'طرطوس', 'أخرى'
]

ARREST_AUTHORITIES = [
    'الأمن العسكري', 'الأمن السياسي', 'أمن الدولة',
    'المخابرات الجوية', 'الدفاع الوطني', 'الشرطة العسكرية',
    'الأمن الجنائي', 'الجيش', 'حاجز أمني', 'دورية مشتركة',
    'غير معروف', 'أخرى'
]

DETENTION_FACILITIES = [
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

STATUS_MAP = {
    'survivor': 'ناجٍ',
    'enforced': 'مغيّب قسراً',
    'deceased': 'متوفى'
}

STATUS_COLORS = {
    'survivor': '#27ae60',
    'enforced': '#e67e22',
    'deceased': '#c0392b'
}

EVIDENCE_LEVELS = [
    ('high', 'عالي - أدلة موثقة متعددة'),
    ('medium', 'متوسط - دليل واحد موثق'),
    ('low', 'منخفض - شهادة شفهية فقط'),
    ('unverified', 'غير مُتحقق منه')
]

VERIFICATION_STATUSES = [
    ('Verified', 'تم التحقق'),
    ('Corroborated', 'مؤيَّد بأدلة'),
    ('Unverified', 'لم يُتحقق منه'),
    ('Conflicting', 'معلومات متضاربة')
]

DIGITAL_EVIDENCE_TYPES = [
    ('caesar_files', 'ملفات قيصر'),
    ('leaked_database', 'تسريبات قاعدة بيانات'),
    ('social_media', 'وسائل التواصل الاجتماعي'),
    ('news_report', 'تقرير إخباري'),
    ('ngo_report', 'تقرير منظمة'),
    ('civil_registry', 'سجل مدني'),
    ('official_document', 'وثيقة رسمية'),
    ('other', 'أخرى')
]

DOCUMENT_TYPES = [
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
]

CIVIL_REGISTRY_STATUSES = [
    ('alive', 'حي في السجل المدني'),
    ('deceased', 'متوفى في السجل المدني'),
    ('unknown', 'غير معروف'),
    ('not_checked', 'لم يتم التحقق')
]

CASE_TYPES = [
    ('enforced_disappearance_no_info', 'اختفاء قسري - لا معلومات'),
    ('enforced_disappearance_leaked_confirmed_dead', 'اختفاء قسري - تسريبات تؤكد الوفاة - مؤكد بالنفوس'),
    ('enforced_disappearance_leaked_not_confirmed', 'اختفاء قسري - تسريبات تؤكد الوفاة - غير مؤكد بالنفوس'),
    ('enforced_disappearance_civil_registry_dead', 'اختفاء قسري - متوفى بحسب النفوس'),
    ('enforced_disappearance_witnesses_alive_registry', 'اختفاء قسري - شهود - حي بالنفوس'),
    ('survivor_documented', 'ناجٍ - لديه وثائق'),
    ('survivor_undocumented', 'ناجٍ - بدون وثائق'),
    ('deceased_caesar_files', 'متوفى - ملفات قيصر')
]

BLOOD_TYPES = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']

EDUCATION_LEVELS = [
    'أمّي', 'ابتدائية', 'إعدادية', 'ثانوية', 'معهد', 'بكالوريوس', 'ماجستير', 'دكتوراه'
]

EDU_TYPES = ['علمي', 'أدبي', 'شرعي', 'مهني', 'تجاري', 'صناعي', 'نسوي', 'أخرى']

MARITAL_STATUSES = [
    ('single', 'أعزب/عزباء'),
    ('married', 'متزوج/ة'),
    ('divorced', 'مطلق/ة'),
    ('widowed', 'أرمل/ة')
]

HOUSING_TYPES = ['ملك', 'إيجار', 'رهن', 'مستضاف', 'أخرى']

# Address area classifications (neighborhoods / districts)
ADDRESS_AREAS = [
    'الرمل الجنوبي', 'قنينص', 'الحفة', 'الصليبة', 'العوينة',
    'الأشرفية', 'بستان الصيداوي', 'الطابيات', 'شيخ ضاهر',
    'حي القصور', 'مرتقلا', 'شارع انطاكيا', 'حي السجن',
    'مشروع القلعة', 'شارع ميسلون', 'سوق الداية', 'الريجي',
    'شارع بور سعيد', 'حي الفاروس', 'طريق الحرش', 'خارج اللاذقية', 'أخرى'
]

# Map of known addresses to their area classification
ADDRESS_TO_AREA = {
    'اللاذقية -سوق التجار -بناء رومينزا': 'العوينة',
    'جامع المشاطي': 'العوينة',
    'اللاذقية': 'شيخ ضاهر',
    'شارع هنانو': 'شيخ ضاهر',
    '٨ اذار': 'شيخ ضاهر',
    'ساحه حلوم': 'حي السجن',
    'الرمل الشمالي': 'حي السجن',
    'اوغاريت': 'الصليبة',
    'ابي تمام': 'الصليبة',
    'مشروع ب': 'الصليبة',
    'الأشرفية': 'الصليبة',
    'بستان الصيداوي': 'الصليبة',
    ' بستان الصيداوي': 'الصليبة',
    'اللاذقية خلف فرن الكرامة': 'الصليبة',
    'طريق المستودعات': 'الصليبة',
    'شارع الغافقي قرب جامع الجديد': 'الصليبة',
    'قرب جامعة الشام': 'الصليبة',
    'شارع بغداد - المشفى الوطني': 'الصليبة',
    'جامع ياسين': 'الصليبة',
    'ساحة اليمن': 'طريق الحرش',
    'جامع خالد ابن الوليد': 'طريق الحرش',
    'مقابل فندق ريفيرا': 'مشروع القلعة',
    'مشروع السابع': 'قنينص',
    'الرويسة بسنادا': 'قنينص',
    'نزلة خالد ابن الوليد': 'الرمل الجنوبي',
    'مشروع ب بجانب مدرسة الاشتراكية': 'الرمل الجنوبي',
    'المشروع الثاني': 'الرمل الجنوبي',
    'تركيا': 'خارج اللاذقية',
    'صليب التركمان': 'خارج اللاذقية',
    'ابن هاني': 'خارج اللاذقية',
    'جبلة ، العمارة': 'خارج اللاذقية',
    'البصه شيخ الحمى': 'خارج اللاذقية',
    'مخيم سلمى ١ - خربة الجوز': 'خارج اللاذقية',
    'البدروسية': 'خارج اللاذقية',
    'سلمى': 'خارج اللاذقية',
    'الحب والرويسة': 'خارج اللاذقية',
    'دمشق / صهيا': 'خارج اللاذقية',
    'تركيا - غازي عنتاب': 'خارج اللاذقية',
    'وادي الشيخان': 'خارج اللاذقية',
}

CHRONIC_DISEASES = [
    'ضغط الدم', 'السكري', 'الربو', 'أمراض القلب', 'الكلى',
    'الكبد', 'السرطان', 'الصرع', 'الثلاسيميا', 'فقر الدم',
    'التهاب المفاصل', 'هشاشة العظام', 'الغدة الدرقية',
    'أمراض الجهاز الهضمي', 'أمراض الجهاز التنفسي',
    'أمراض نفسية', 'اكتئاب', 'اضطراب ما بعد الصدمة (PTSD)',
    'إعاقة حركية', 'إعاقة بصرية', 'إعاقة سمعية',
    'أخرى'
]

REPORTER_RELATIONS = [
    'أم', 'أب', 'أخ', 'أخت', 'زوج/ة', 'ابن/ة', 'قريب',
    'صديق', 'جار', 'زميل', 'الشخص نفسه', 'أخرى'
]

# Arrest authority normalization: keyword-based grouping
# Maps a canonical name to keywords that identify it
AUTHORITY_GROUPS = {
    'أمن الدولة': ['دول'],           # covers الدولة, الدوله, دولة, لادوله, الادوله
    'الأمن العسكري': ['عسكر', 'العسمري'],  # covers العسكري, عسكري, العسمري (typo), عسكر
    'الأمن السياسي': ['سياس'],       # covers السياسي, سياسي
    'المخابرات الجوية': ['جوي', 'جويه', 'الجوية', 'مخابرات جو'],  # covers الجوية, الجويه, جويه, الجوي
    'الدفاع الوطني': ['دفاع'],       # covers الدفاع الوطني, دفاع لوطني
    'غير معروف': ['مجهول', 'لا نعلم', 'غير معروف', 'لاتعلم', 'مجهولة', 'غير معروفة'],
}


def normalize_authority(name):
    """Normalize arrest authority name to canonical form."""
    if not name:
        return name
    name_clean = name.strip()
    for canonical, keywords in AUTHORITY_GROUPS.items():
        for kw in keywords:
            if kw in name_clean:
                return canonical
    return name_clean


def record_has_child_in_age_range(record, age_from=None, age_to=None):
    """Check if a record has at least one child within the given age range."""
    current_year = datetime.now().year
    try:
        children = json.loads(record['children_data']) if record['children_data'] else []
        _normalize_children(children)
    except (json.JSONDecodeError, TypeError):
        return False
    if not children:
        return False
    for child in children:
        age = None
        if child.get('birth_year'):
            try:
                age = current_year - int(child['birth_year'])
            except (ValueError, TypeError):
                pass
        elif child.get('age'):
            try:
                age = int(child['age'])
            except (ValueError, TypeError):
                pass
        if age is not None:
            if age_from is not None and age < age_from:
                continue
            if age_to is not None and age > age_to:
                continue
            return True
    return False


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=30)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
        g.db.execute("PRAGMA busy_timeout=15000")
    return g.db


def db_execute_with_retry(db, sql, params=None, max_retries=3):
    """Execute DB query with retry logic for concurrent access."""
    for attempt in range(max_retries):
        try:
            if params:
                result = db.execute(sql, params)
            else:
                result = db.execute(sql)
            db.commit()
            return result
        except sqlite3.OperationalError as e:
            if 'locked' in str(e) and attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise


def log_audit(action, entity_type, entity_id=None, details='', changed_by=None):
    """Log an admin action to the audit trail (Berkeley Protocol: chain of custody)."""
    try:
        db = get_db()
        ip = request.remote_addr if request else ''
        if changed_by is None:
            changed_by = session.get('username', session.get('display_name', 'admin'))
        # Store structured JSON details for Berkeley Protocol compliance
        if isinstance(details, str):
            structured_details = json.dumps({
                'changed_by': changed_by,
                'description': details,
            }, ensure_ascii=False)
        else:
            if 'changed_by' not in details:
                details['changed_by'] = changed_by
            structured_details = json.dumps(details, ensure_ascii=False)
        db.execute(
            "INSERT INTO audit_log (action, entity_type, entity_id, details, ip_address, user_id) VALUES (?,?,?,?,?,?)",
            (action, entity_type, entity_id, structured_details, ip, changed_by)
        )
        db.commit()
    except Exception as e:
        import sys
        print(f"[AUDIT LOG ERROR] {e}", file=sys.stderr)


@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def migrate_db():
    """Ensure all Berkeley Protocol columns exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # -- Create records table if it doesn't exist (fresh install) --
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            first_name TEXT NOT NULL DEFAULT '',
            father_name TEXT NOT NULL DEFAULT '',
            last_name TEXT NOT NULL DEFAULT '',
            gender TEXT NOT NULL DEFAULT '',
            mother_name TEXT NOT NULL DEFAULT '',
            birth_day INTEGER,
            birth_month INTEGER,
            birth_year INTEGER,
            province TEXT NOT NULL DEFAULT '',
            national_id TEXT NOT NULL DEFAULT '',
            phone TEXT,
            blood_type TEXT,
            photo_path TEXT,
            document_path TEXT,
            arrest_day INTEGER,
            arrest_month INTEGER,
            arrest_year INTEGER,
            arrest_place TEXT NOT NULL DEFAULT '',
            arrest_authority TEXT NOT NULL DEFAULT '',
            arrest_reason TEXT NOT NULL DEFAULT '',
            arrest_causer TEXT,
            status TEXT,
            release_day INTEGER,
            release_month INTEGER,
            release_year INTEGER,
            death_day INTEGER,
            death_month INTEGER,
            death_year INTEGER,
            marital TEXT,
            guardian_name TEXT,
            guardian_relation TEXT,
            guardian_phone TEXT,
            spouse_name TEXT,
            spouse_phone TEXT,
            has_kids TEXT,
            kids_count INTEGER,
            children_data TEXT,
            ex_spouse_name TEXT,
            has_kids_w TEXT,
            kids_count_w INTEGER,
            children_data_w TEXT,
            address TEXT NOT NULL DEFAULT '',
            housing_type TEXT NOT NULL DEFAULT '',
            employment TEXT,
            profession TEXT,
            employer TEXT,
            breadwinner TEXT,
            chronic TEXT,
            diseases TEXT,
            education TEXT,
            edu_type TEXT,
            edu_specialization TEXT,
            edu_university TEXT,
            kids_under_18_count INTEGER DEFAULT 0,
            legal TEXT,
            legal_details TEXT,
            assoc TEXT,
            assoc_name TEXT,
            service_type TEXT,
            notes TEXT,
            breadwinner_job TEXT,
            death_place TEXT,
            rent_amount TEXT,
            has_hypertension INTEGER,
            has_diabetes INTEGER,
            other_diseases TEXT,
            is_officially_registered INTEGER,
            has_special_needs INTEGER,
            special_needs_details TEXT,
            breadwinner_relation TEXT,
            breadwinner_relation_other TEXT
        )
    """)

    cursor.execute("PRAGMA table_info(records)")
    existing = {row[1] for row in cursor.fetchall()}

    new_columns = {
        'case_type': "TEXT DEFAULT ''",
        'reporter_name': "TEXT DEFAULT ''",
        'reporter_relation': "TEXT DEFAULT ''",
        'reporter_phone': "TEXT DEFAULT ''",
        'reporter_id': "TEXT DEFAULT ''",
        'informant_consent': "INTEGER DEFAULT 0",
        'witnesses_data': "TEXT DEFAULT '[]'",
        'digital_evidence_type': "TEXT DEFAULT ''",
        'digital_evidence_url': "TEXT DEFAULT ''",
        'digital_evidence_url_status': "TEXT DEFAULT ''",
        'digital_evidence_screenshot_path': "TEXT DEFAULT ''",
        'digital_evidence_date': "TEXT DEFAULT ''",
        'digital_evidence_description': "TEXT DEFAULT ''",
        'digital_evidence_person_name': "TEXT DEFAULT ''",
        'digital_evidence_death_date': "TEXT DEFAULT ''",
        'civil_registry_status': "TEXT DEFAULT ''",
        'civil_registry_date': "TEXT DEFAULT ''",
        'civil_registry_document_path': "TEXT DEFAULT ''",
        'has_conflicting_info': "INTEGER DEFAULT 0",
        'conflicting_info_details': "TEXT DEFAULT ''",
        'evidence_level': "TEXT DEFAULT 'unverified'",
        'evidence_sources_count': "INTEGER DEFAULT 0",
        'last_known_alive_date': "TEXT DEFAULT ''",
        'last_known_location': "TEXT DEFAULT ''",
        'detention_facilities_data': "TEXT DEFAULT '[]'",
        'source_type': "TEXT DEFAULT ''",
        'source_url': "TEXT DEFAULT ''",
        'collection_date': "TEXT DEFAULT ''",
        'collector_name': "TEXT DEFAULT ''",
        'verification_status': "TEXT DEFAULT 'Unverified'",
        'methodology_notes': "TEXT DEFAULT ''",
        'cause_number': "TEXT DEFAULT ''",
        'record_slug': "TEXT DEFAULT ''",
        'photo_hash': "TEXT DEFAULT ''",
        'document_hash': "TEXT DEFAULT ''",
        'survivor_cv_path': "TEXT DEFAULT ''",
        'survivor_cv_text': "TEXT DEFAULT ''",
        'survivor_cv_photo_path': "TEXT DEFAULT ''",
        'family_book_number': "TEXT DEFAULT ''",
        'address_area': "TEXT DEFAULT ''",
        'deleted_at': "TEXT DEFAULT NULL",
        # Berkeley Protocol: link collector to volunteers table for provenance
        'collector_id': "INTEGER DEFAULT NULL",
        # Berkeley Protocol: hash for digital evidence screenshots
        'screenshot_hash': "TEXT DEFAULT ''",
        # Renamed from children_data_w for clarity
        'spouse_previous_children_data': "TEXT DEFAULT '[]'",
        # Berkeley Protocol: structured methodology type
        'methodology_type': "TEXT DEFAULT ''",
    }

    for col, typedef in new_columns.items():
        if col not in existing:
            try:
                cursor.execute(f"ALTER TABLE records ADD COLUMN {col} {typedef}")
            except sqlite3.OperationalError:
                pass

    # -- Volunteers table --
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS volunteers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            national_id TEXT DEFAULT '',
            province TEXT DEFAULT '',
            address TEXT DEFAULT '',
            role TEXT DEFAULT '',
            specialization TEXT DEFAULT '',
            join_date TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # Migrate volunteers: add individual name fields
    cursor.execute("PRAGMA table_info(volunteers)")
    vol_existing = {row[1] for row in cursor.fetchall()}
    vol_new_cols = {
        'first_name': "TEXT DEFAULT ''",
        'last_name': "TEXT DEFAULT ''",
        'father_name': "TEXT DEFAULT ''",
        'mother_name': "TEXT DEFAULT ''",
    }
    for col, typedef in vol_new_cols.items():
        if col not in vol_existing:
            try:
                cursor.execute(f"ALTER TABLE volunteers ADD COLUMN {col} {typedef}")
            except sqlite3.OperationalError:
                pass

    # -- Members table --
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            father_name TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            national_id TEXT DEFAULT '',
            birth_year INTEGER DEFAULT 0,
            gender TEXT DEFAULT '',
            province TEXT DEFAULT '',
            address TEXT DEFAULT '',
            membership_type TEXT DEFAULT '',
            membership_number TEXT DEFAULT '',
            join_date TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # Migrate members: add individual name fields
    cursor.execute("PRAGMA table_info(members)")
    mem_existing = {row[1] for row in cursor.fetchall()}
    mem_new_cols = {
        'first_name': "TEXT DEFAULT ''",
        'last_name': "TEXT DEFAULT ''",
        'mother_name': "TEXT DEFAULT ''",
    }
    for col, typedef in mem_new_cols.items():
        if col not in mem_existing:
            try:
                cursor.execute(f"ALTER TABLE members ADD COLUMN {col} {typedef}")
            except sqlite3.OperationalError:
                pass

    # -- Member payments table --
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS member_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            month_number INTEGER NOT NULL,
            period_label TEXT DEFAULT '',
            payment_date TEXT DEFAULT '',
            status TEXT DEFAULT 'unpaid',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
        )
    """)

    # -- Record services table --
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS record_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL,
            service_name TEXT NOT NULL,
            service_date TEXT DEFAULT '',
            provider TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
        )
    """)

    # -- Custom lists table --
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS custom_lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # -- Custom list items table --
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS custom_list_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            list_id INTEGER NOT NULL,
            record_id INTEGER NOT NULL,
            added_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (list_id) REFERENCES custom_lists(id) ON DELETE CASCADE,
            FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE,
            UNIQUE(list_id, record_id)
        )
    """)

    # -- Custom list manual entries --
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS custom_list_manual_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            list_id INTEGER NOT NULL,
            full_name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            added_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (list_id) REFERENCES custom_lists(id) ON DELETE CASCADE
        )
    """)

    # Migrate manual items table with extra fields
    cursor.execute("PRAGMA table_info(custom_list_manual_items)")
    mi_existing = {row[1] for row in cursor.fetchall()}
    mi_new_cols = {
        'father_name': "TEXT DEFAULT ''",
        'mother_name': "TEXT DEFAULT ''",
        'national_id': "TEXT DEFAULT ''",
        'family_book_number': "TEXT DEFAULT ''",
        'address': "TEXT DEFAULT ''",
        'province': "TEXT DEFAULT ''",
        'kids_count': "INTEGER DEFAULT 0",
        'marital': "TEXT DEFAULT ''",
        'status': "TEXT DEFAULT ''",
    }
    for col, typedef in mi_new_cols.items():
        if col not in mi_existing:
            try:
                cursor.execute(f"ALTER TABLE custom_list_manual_items ADD COLUMN {col} {typedef}")
            except sqlite3.OperationalError:
                pass

    # -- Volunteer attendance table --
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS volunteer_attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            volunteer_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            check_in TEXT DEFAULT '',
            check_out TEXT DEFAULT '',
            hours REAL DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (volunteer_id) REFERENCES volunteers(id) ON DELETE CASCADE
        )
    """)

    # -- Volunteer activities table --
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS volunteer_activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            date TEXT DEFAULT '',
            description TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # -- Volunteer activity participation (many-to-many) --
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS volunteer_activity_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id INTEGER NOT NULL,
            volunteer_id INTEGER NOT NULL,
            role TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            FOREIGN KEY (activity_id) REFERENCES volunteer_activities(id) ON DELETE CASCADE,
            FOREIGN KEY (volunteer_id) REFERENCES volunteers(id) ON DELETE CASCADE,
            UNIQUE(activity_id, volunteer_id)
        )
    """)

    # -- Audit log table --
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now','localtime')),
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            details TEXT DEFAULT '',
            ip_address TEXT DEFAULT ''
        )
    """)

    # -- record_changes table (field-level change history) --
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS record_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL,
            field_name TEXT NOT NULL,
            old_value TEXT DEFAULT '',
            new_value TEXT DEFAULT '',
            changed_by TEXT DEFAULT '',
            changed_at TEXT DEFAULT (datetime('now','localtime')),
            ip_address TEXT DEFAULT '',
            FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
        )
    """)

    # -- record_links table (cross-references between records) --
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS record_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id_a INTEGER NOT NULL,
            record_id_b INTEGER NOT NULL,
            link_type TEXT NOT NULL DEFAULT 'related',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (record_id_a) REFERENCES records(id) ON DELETE CASCADE,
            FOREIGN KEY (record_id_b) REFERENCES records(id) ON DELETE CASCADE
        )
    """)

    # -- Record companions table (people who were with a survivor) --
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS record_companions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL,
            first_name TEXT DEFAULT '',
            father_name TEXT DEFAULT '',
            last_name TEXT DEFAULT '',
            mother_name TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            linked_record_id INTEGER,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE,
            FOREIGN KEY (linked_record_id) REFERENCES records(id) ON DELETE SET NULL
        )
    """)

    # -- Add record_status column for verification workflow --
    cursor.execute("PRAGMA table_info(records)")
    rec_existing = {row[1] for row in cursor.fetchall()}
    if 'record_status' not in rec_existing:
        try:
            cursor.execute("ALTER TABLE records ADD COLUMN record_status TEXT DEFAULT 'draft'")
        except sqlite3.OperationalError:
            pass

    # -- Users table (multi-user with roles) --
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT DEFAULT '',
            role TEXT NOT NULL DEFAULT 'viewer',
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            last_login TEXT
        )
    """)

    # -- Saved search filters table --
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_filters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            filter_data TEXT NOT NULL DEFAULT '{}',
            entity_type TEXT NOT NULL DEFAULT 'records',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # -- Berkeley Protocol: record_witnesses table (migrated from witnesses_data JSON) --
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS record_witnesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL,
            name TEXT DEFAULT '',
            relation TEXT DEFAULT '',
            contact TEXT DEFAULT '',
            testimony_summary TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
        )
    """)

    # -- Berkeley Protocol: record_detentions table (migrated from detention_facilities_data JSON) --
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS record_detentions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL,
            facility_name TEXT DEFAULT '',
            date_from TEXT DEFAULT '',
            date_to TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
        )
    """)

    # -- Berkeley Protocol: record_documents table (multiple evidence uploads per record) --
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS record_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL,
            doc_type TEXT NOT NULL DEFAULT 'other',
            file_path TEXT NOT NULL,
            file_hash TEXT DEFAULT '',
            original_filename TEXT DEFAULT '',
            description TEXT DEFAULT '',
            document_date TEXT DEFAULT '',
            source_url TEXT DEFAULT '',
            uploaded_by TEXT DEFAULT '',
            uploaded_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            draft_data TEXT DEFAULT '{}',
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            sender TEXT DEFAULT '',
            target_users TEXT DEFAULT '*',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            is_read_by TEXT DEFAULT '[]'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_edits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL,
            submitted_by TEXT NOT NULL,
            edit_data TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            reviewed_by TEXT DEFAULT '',
            reviewed_at TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
        )
    """)

    # -- Add user_id column to audit_log for Berkeley Protocol chain of custody --
    cursor.execute("PRAGMA table_info(audit_log)")
    audit_existing = {row[1] for row in cursor.fetchall()}
    if 'user_id' not in audit_existing:
        try:
            cursor.execute("ALTER TABLE audit_log ADD COLUMN user_id TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass

    # -- Migrate witnesses_data JSON -> record_witnesses table --
    try:
        witness_count = cursor.execute("SELECT COUNT(*) FROM record_witnesses").fetchone()[0]
        if witness_count == 0:
            rows = cursor.execute("SELECT id, witnesses_data FROM records WHERE witnesses_data IS NOT NULL AND witnesses_data != '' AND witnesses_data != '[]'").fetchall()
            for row in rows:
                try:
                    witnesses = json.loads(row[1])
                    for w in witnesses:
                        if isinstance(w, dict):
                            cursor.execute(
                                "INSERT INTO record_witnesses (record_id, name, relation, contact, testimony_summary) VALUES (?,?,?,?,?)",
                                (row[0], w.get('name', ''), w.get('relation', ''), w.get('contact', w.get('phone', '')), w.get('testimony', w.get('notes', '')))
                            )
                except (json.JSONDecodeError, TypeError):
                    pass
    except sqlite3.OperationalError:
        pass

    # -- Migrate detention_facilities_data JSON -> record_detentions table --
    try:
        detention_count = cursor.execute("SELECT COUNT(*) FROM record_detentions").fetchone()[0]
        if detention_count == 0:
            rows = cursor.execute("SELECT id, detention_facilities_data FROM records WHERE detention_facilities_data IS NOT NULL AND detention_facilities_data != '' AND detention_facilities_data != '[]'").fetchall()
            for row in rows:
                try:
                    facilities = json.loads(row[1])
                    for f in facilities:
                        if isinstance(f, dict):
                            cursor.execute(
                                "INSERT INTO record_detentions (record_id, facility_name, date_from, date_to, notes) VALUES (?,?,?,?,?)",
                                (row[0], f.get('name', f.get('facility', '')), f.get('from', f.get('date_from', '')), f.get('to', f.get('date_to', '')), f.get('notes', ''))
                            )
                        elif isinstance(f, str):
                            cursor.execute(
                                "INSERT INTO record_detentions (record_id, facility_name) VALUES (?,?)",
                                (row[0], f)
                            )
                except (json.JSONDecodeError, TypeError):
                    pass
    except sqlite3.OperationalError:
        pass

    # -- Seed initial admin user from existing password hash (activate users system) --
    try:
        user_count = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if user_count == 0:
            admin_pw_file = os.path.join(BASE_DIR, 'admin_password.hash')
            if os.path.exists(admin_pw_file):
                with open(admin_pw_file, 'r') as f:
                    pw_hash = f.read().strip()
                if pw_hash:
                    cursor.execute(
                        "INSERT INTO users (username, password_hash, display_name, role, is_active) VALUES (?,?,?,?,?)",
                        ('admin', pw_hash, 'مدير النظام', 'admin', 1)
                    )
    except sqlite3.OperationalError:
        pass

    # -- Migrate spouse_previous_children_data from children_data_w --
    try:
        cursor.execute("PRAGMA table_info(records)")
        rec_cols = {row[1] for row in cursor.fetchall()}
        if 'spouse_previous_children_data' in rec_cols and 'children_data_w' in rec_cols:
            cursor.execute("""
                UPDATE records SET spouse_previous_children_data = children_data_w
                WHERE (spouse_previous_children_data IS NULL OR spouse_previous_children_data = '' OR spouse_previous_children_data = '[]')
                AND children_data_w IS NOT NULL AND children_data_w != '' AND children_data_w != '[]'
            """)
    except sqlite3.OperationalError:
        pass

    # -- Database indexes for performance --
    index_statements = [
        "CREATE INDEX IF NOT EXISTS idx_records_status ON records(status)",
        "CREATE INDEX IF NOT EXISTS idx_records_province ON records(province)",
        "CREATE INDEX IF NOT EXISTS idx_records_gender ON records(gender)",
        "CREATE INDEX IF NOT EXISTS idx_records_arrest_year ON records(arrest_year)",
        "CREATE INDEX IF NOT EXISTS idx_records_birth_year ON records(birth_year)",
        "CREATE INDEX IF NOT EXISTS idx_records_created_at ON records(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_records_collection_date ON records(collection_date)",
        "CREATE INDEX IF NOT EXISTS idx_records_first_name ON records(first_name)",
        "CREATE INDEX IF NOT EXISTS idx_records_last_name ON records(last_name)",
        "CREATE INDEX IF NOT EXISTS idx_records_national_id ON records(national_id)",
        "CREATE INDEX IF NOT EXISTS idx_records_phone ON records(phone)",
        "CREATE INDEX IF NOT EXISTS idx_records_marital ON records(marital)",
        "CREATE INDEX IF NOT EXISTS idx_records_education ON records(education)",
        "CREATE INDEX IF NOT EXISTS idx_records_housing_type ON records(housing_type)",
        "CREATE INDEX IF NOT EXISTS idx_records_evidence_level ON records(evidence_level)",
        "CREATE INDEX IF NOT EXISTS idx_records_verification_status ON records(verification_status)",
        "CREATE INDEX IF NOT EXISTS idx_records_record_status ON records(record_status)",
        "CREATE INDEX IF NOT EXISTS idx_records_status_province ON records(status, province)",
        "CREATE INDEX IF NOT EXISTS idx_records_name ON records(first_name, father_name, last_name)",
        "CREATE INDEX IF NOT EXISTS idx_records_deleted_at ON records(deleted_at)",
        "CREATE INDEX IF NOT EXISTS idx_volunteers_status ON volunteers(status)",
        "CREATE INDEX IF NOT EXISTS idx_volunteers_full_name ON volunteers(full_name)",
        "CREATE INDEX IF NOT EXISTS idx_members_status ON members(status)",
        "CREATE INDEX IF NOT EXISTS idx_members_full_name ON members(full_name)",
        "CREATE INDEX IF NOT EXISTS idx_audit_log_entity_type ON audit_log(entity_type)",
        "CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_member_payments_member_id ON member_payments(member_id)",
        "CREATE INDEX IF NOT EXISTS idx_member_payments_status ON member_payments(status)",
        "CREATE INDEX IF NOT EXISTS idx_custom_list_items_list_id ON custom_list_items(list_id)",
        "CREATE INDEX IF NOT EXISTS idx_record_changes_record_id ON record_changes(record_id)",
        "CREATE INDEX IF NOT EXISTS idx_record_links_a ON record_links(record_id_a)",
        "CREATE INDEX IF NOT EXISTS idx_record_links_b ON record_links(record_id_b)",
        "CREATE INDEX IF NOT EXISTS idx_records_address_area ON records(address_area)",
        "CREATE INDEX IF NOT EXISTS idx_records_status_gender_marital ON records(status, gender, marital)",
        "CREATE INDEX IF NOT EXISTS idx_record_companions_record_id ON record_companions(record_id)",
        "CREATE INDEX IF NOT EXISTS idx_record_services_record_id ON record_services(record_id)",
        "CREATE INDEX IF NOT EXISTS idx_records_address ON records(address)",
        # New composite indexes for common query patterns
        "CREATE INDEX IF NOT EXISTS idx_records_deleted_status ON records(deleted_at, status)",
        "CREATE INDEX IF NOT EXISTS idx_records_deleted_province ON records(deleted_at, province)",
        "CREATE INDEX IF NOT EXISTS idx_record_changes_changed_at ON record_changes(changed_at)",
        "CREATE INDEX IF NOT EXISTS idx_record_witnesses_record_id ON record_witnesses(record_id)",
        "CREATE INDEX IF NOT EXISTS idx_record_detentions_record_id ON record_detentions(record_id)",
        "CREATE INDEX IF NOT EXISTS idx_record_detentions_facility ON record_detentions(facility_name)",
        "CREATE INDEX IF NOT EXISTS idx_record_documents_record_id ON record_documents(record_id)",
    ]
    for stmt in index_statements:
        try:
            cursor.execute(stmt)
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()


# Run migrations at module load to ensure schema is up-to-date
migrate_db()


# ---------------------------------------------------------------------------
# Berkeley Protocol: Cached stats function (eliminates duplicate COUNT queries)
# ---------------------------------------------------------------------------
def _get_cached_stats(db):
    """Get all record counts in a single query, cached per-request in Flask g."""
    if hasattr(g, '_cached_stats'):
        return g._cached_stats

    row = db.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status='survivor' THEN 1 ELSE 0 END) as survivors,
            SUM(CASE WHEN status='enforced' THEN 1 ELSE 0 END) as enforced,
            SUM(CASE WHEN status='deceased' THEN 1 ELSE 0 END) as deceased,
            SUM(CASE WHEN gender='male' THEN 1 ELSE 0 END) as males,
            SUM(CASE WHEN gender='female' THEN 1 ELSE 0 END) as females,
            SUM(CASE WHEN chronic IS NOT NULL AND chronic != '' AND chronic != 'لا' THEN 1 ELSE 0 END) as chronic,
            SUM(CASE WHEN has_special_needs = 1 THEN 1 ELSE 0 END) as special_needs,
            SUM(CASE WHEN has_hypertension = 1 THEN 1 ELSE 0 END) as hypertension,
            SUM(CASE WHEN has_diabetes = 1 THEN 1 ELSE 0 END) as diabetes,
            SUM(CASE WHEN housing_type = 'إيجار' THEN 1 ELSE 0 END) as paying_rent,
            SUM(CASE WHEN breadwinner = '' OR breadwinner = 'لا يوجد' OR breadwinner IS NULL THEN 1 ELSE 0 END) as no_breadwinner,
            SUM(CASE WHEN first_name='' OR status='' OR province='' OR gender='' OR phone='' OR national_id='' THEN 1 ELSE 0 END) as incomplete
        FROM records WHERE deleted_at IS NULL
    """).fetchone()

    stats = {
        'total': row['total'] or 0,
        'survivors': row['survivors'] or 0,
        'enforced': row['enforced'] or 0,
        'deceased': row['deceased'] or 0,
        'males': row['males'] or 0,
        'females': row['females'] or 0,
        'health': {
            'chronic': row['chronic'] or 0,
            'special_needs': row['special_needs'] or 0,
            'hypertension': row['hypertension'] or 0,
            'diabetes': row['diabetes'] or 0,
            'paying_rent': row['paying_rent'] or 0,
            'no_breadwinner': row['no_breadwinner'] or 0,
        },
        'incomplete_records': row['incomplete'] or 0,
    }
    g._cached_stats = stats
    return stats


# ---------------------------------------------------------------------------
# Berkeley Protocol: Application-level record validation
# ---------------------------------------------------------------------------
def validate_record(form_data):
    """Validate record data and return list of (field, error_message) tuples."""
    errors = []
    current_year = datetime.now().year

    # Date sanity checks
    for field, label in [('arrest_year', 'سنة الاعتقال'), ('birth_year', 'سنة الولادة')]:
        val = form_data.get(field, '')
        if val and val != '':
            try:
                year = int(val)
                if year < 1900 or year > current_year + 1:
                    errors.append((field, f'{label} يجب أن يكون بين 1900 و {current_year}'))
            except (ValueError, TypeError):
                errors.append((field, f'{label} يجب أن يكون رقماً'))

    # Status validation
    status = form_data.get('status', '')
    if status and status not in ('survivor', 'enforced', 'deceased'):
        errors.append(('status', 'الحالة غير صالحة'))

    # Evidence level validation
    evidence = form_data.get('evidence_level', '')
    if evidence and evidence not in ('high', 'medium', 'low', 'unverified', ''):
        errors.append(('evidence_level', 'مستوى الأدلة غير صالح'))

    # Verification status validation
    verification = form_data.get('verification_status', '')
    if verification and verification not in ('Verified', 'Corroborated', 'Unverified', 'Conflicting', ''):
        errors.append(('verification_status', 'حالة التحقق غير صالحة'))

    # Phone format (basic: digits, +, spaces, dashes)
    phone = form_data.get('phone', '')
    if phone and not re.match(r'^[\d\s\-\+\(\)]+$', phone):
        errors.append(('phone', 'رقم الهاتف غير صالح'))

    return errors


# Volunteer statuses
VOLUNTEER_STATUSES = [
    ('active', 'نشط'),
    ('inactive', 'غير نشط'),
    ('suspended', 'معلّق'),
]

VOLUNTEER_ROLES = [
    'جامع بيانات', 'محقق ميداني', 'مدقق معلومات', 'مترجم',
    'دعم نفسي', 'مستشار قانوني', 'إداري', 'متطوع عام', 'أخرى'
]

# Member statuses
MEMBER_STATUSES = [
    ('active', 'نشط'),
    ('inactive', 'غير نشط'),
    ('suspended', 'معلّق'),
    ('honorary', 'فخري'),
]

MEMBERSHIP_TYPES = [
    'عضو مؤسس', 'عضو عامل', 'عضو منتسب', 'عضو فخري',
    'عضو داعم', 'أخرى'
]


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    """Decorator that checks user role. Admin role can access everything."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get('is_admin'):
                return redirect(url_for('admin_login'))
            user_role = session.get('user_role', 'admin')
            if user_role not in roles and user_role != 'admin':
                flash('ليس لديك صلاحية للوصول لهذه الصفحة', 'error')
                return redirect(url_for('admin_dashboard'))
            return f(*args, **kwargs)
        return decorated
    return decorator


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'pdf', 'doc', 'docx'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_upload(file_obj, subfolder='documents'):
    if file_obj and file_obj.filename and allowed_file(file_obj.filename):
        ext = file_obj.filename.rsplit('.', 1)[1].lower()
        filename = f"{int(time.time()*1000)}-{secrets.token_hex(4)}.{ext}"
        folder = os.path.join(app.config['UPLOAD_FOLDER'], subfolder)
        os.makedirs(folder, exist_ok=True)
        filepath = os.path.join(folder, filename)
        file_obj.save(filepath)

        # Compute hash for integrity
        file_obj.seek(0)
        file_hash = hashlib.sha256(file_obj.read()).hexdigest()
        return filename, file_hash
    return None, None


# ---------------------------------------------------------------------------
# Template context
# ---------------------------------------------------------------------------
@app.context_processor
def inject_constants():
    return {
        'csrf_token': generate_csrf_token,
        'PROVINCES': PROVINCES,
        'ARREST_AUTHORITIES': ARREST_AUTHORITIES,
        'DETENTION_FACILITIES': DETENTION_FACILITIES,
        'STATUS_MAP': STATUS_MAP,
        'STATUS_COLORS': STATUS_COLORS,
        'EVIDENCE_LEVELS': EVIDENCE_LEVELS,
        'VERIFICATION_STATUSES': VERIFICATION_STATUSES,
        'DIGITAL_EVIDENCE_TYPES': DIGITAL_EVIDENCE_TYPES,
        'CIVIL_REGISTRY_STATUSES': CIVIL_REGISTRY_STATUSES,
        'CASE_TYPES': CASE_TYPES,
        'BLOOD_TYPES': BLOOD_TYPES,
        'EDUCATION_LEVELS': EDUCATION_LEVELS,
        'EDU_TYPES': EDU_TYPES,
        'MARITAL_STATUSES': MARITAL_STATUSES,
        'HOUSING_TYPES': HOUSING_TYPES,
        'ADDRESS_AREAS': ADDRESS_AREAS,
        'ADDRESS_TO_AREA': ADDRESS_TO_AREA,
        'CHRONIC_DISEASES': CHRONIC_DISEASES,
        'REPORTER_RELATIONS': REPORTER_RELATIONS,
        'PDF_COLUMNS': PDF_COLUMNS,
        'DEFAULT_PDF_COLS': DEFAULT_PDF_COLS,
        'VOLUNTEER_STATUSES': VOLUNTEER_STATUSES,
        'VOLUNTEER_ROLES': VOLUNTEER_ROLES,
        'MEMBER_STATUSES': MEMBER_STATUSES,
        'MEMBERSHIP_TYPES': MEMBERSHIP_TYPES,
        'METHODOLOGY_TYPES': METHODOLOGY_TYPES,
        'DOCUMENT_TYPES': DOCUMENT_TYPES,
        'STATUS_LABELS': STATUS_LABELS,
        'VALID_STATUS_TRANSITIONS': VALID_STATUS_TRANSITIONS,
        'user_role': session.get('user_role', 'admin'),
        'display_name': session.get('display_name', ''),
        'username': session.get('username', ''),
        'FIELD_TOOLTIPS': FIELD_TOOLTIPS,
    }


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------
@app.errorhandler(413)
def request_entity_too_large(error):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': False, 'error': 'حجم الملفات كبير جداً. الحد الأقصى 15MB لكل ملف.'}), 413
    flash('حجم الملفات كبير جداً. الحد الأقصى 15MB لكل ملف. يرجى تقليل حجم الصور قبل الرفع.', 'error')
    return redirect(url_for('entry_form'))


@app.errorhandler(400)
def bad_request(error):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': False, 'error': 'طلب غير صالح. يرجى التحقق من البيانات المدخلة.'}), 400
    flash('حدث خطأ في البيانات المرسلة. يرجى المحاولة مرة أخرى.', 'error')
    return redirect(url_for('entry_form'))


@app.errorhandler(500)
def internal_error(error):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': False, 'error': 'خطأ في الخادم. يرجى المحاولة مرة أخرى لاحقاً.'}), 500
    flash('حدث خطأ في الخادم. يرجى المحاولة مرة أخرى لاحقاً.', 'error')
    return redirect(url_for('entry_form'))


# ---------------------------------------------------------------------------
# Routes – Data entry (login required)
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    return render_template('index.html')


@app.route('/entry', methods=['GET'])
@admin_required
def entry_form():
    db = get_db()
    volunteer_names = db.execute(
        "SELECT DISTINCT full_name FROM (SELECT full_name FROM volunteers WHERE status='active' UNION SELECT full_name FROM members WHERE status='active') ORDER BY full_name"
    ).fetchall()
    return render_template('entry.html', volunteer_names=[v['full_name'] for v in volunteer_names])


@app.route('/api/draft/save', methods=['POST'])
def api_draft_save():
    """Save form draft to server (survives IP changes)."""
    if not session.get('is_admin'):
        return jsonify({'success': False}), 401
    username = session.get('username', '')
    if not username:
        return jsonify({'success': False}), 401
    draft_data = request.get_json(silent=True) or {}
    db = get_db()
    db.execute("""INSERT INTO user_drafts (username, draft_data, updated_at)
        VALUES (?, ?, datetime('now','localtime'))
        ON CONFLICT(username) DO UPDATE SET draft_data=excluded.draft_data, updated_at=excluded.updated_at""",
        (username, json.dumps(draft_data, ensure_ascii=False)))
    db.commit()
    return jsonify({'success': True})


@app.route('/api/draft/load')
def api_draft_load():
    """Load saved draft from server."""
    if not session.get('is_admin'):
        return jsonify({'success': False}), 401
    username = session.get('username', '')
    if not username:
        return jsonify({'success': False}), 401
    db = get_db()
    row = db.execute("SELECT draft_data, updated_at FROM user_drafts WHERE username=?", (username,)).fetchone()
    if row and row['draft_data']:
        return jsonify({'success': True, 'draft': json.loads(row['draft_data']), 'updated_at': row['updated_at']})
    return jsonify({'success': False, 'draft': None})


@app.route('/api/draft/clear', methods=['POST'])
def api_draft_clear():
    """Clear saved draft from server."""
    if not session.get('is_admin'):
        return jsonify({'success': False}), 401
    username = session.get('username', '')
    if not username:
        return jsonify({'success': False}), 401
    db = get_db()
    db.execute("DELETE FROM user_drafts WHERE username=?", (username,))
    db.commit()
    return jsonify({'success': True})


REQUIRED_ENTRY_FIELDS = {
    'first_name': 'الاسم',
    'last_name': 'الكنية',
    'status': 'الحالة',
    'province': 'المحافظة',
    'gender': 'الجنس',
}


def _validate_entry(form):
    """Validate entry form data. Returns (errors, warnings) lists."""
    errors = []
    warnings = []

    # Required fields
    for field, label in REQUIRED_ENTRY_FIELDS.items():
        if not form.get(field, '').strip():
            errors.append(f'الحقل "{label}" مطلوب')

    # Phone format (warning only)
    phone = form.get('phone', '').strip().replace(' ', '').replace('-', '')
    if phone and not re.match(r'^\+?\d{7,15}$', phone):
        warnings.append('صيغة رقم الهاتف غير معتادة')

    # National ID format (warning only)
    nid = form.get('national_id', '').strip().replace(' ', '')
    if nid and not re.match(r'^\d{11}$', nid):
        warnings.append('الرقم الوطني يجب أن يكون 11 رقماً')

    # Date logic with range validation
    current_year = datetime.now().year
    birth_year = int(form.get('birth_year', 0) or 0)
    arrest_year = int(form.get('arrest_year', 0) or 0)
    death_year = int(form.get('death_year', 0) or 0)
    release_year = int(form.get('release_year', 0) or 0)

    # Range checks (Berkeley Protocol: data quality)
    for year_val, label in [(birth_year, 'سنة الميلاد'), (arrest_year, 'سنة الاعتقال'),
                             (death_year, 'سنة الوفاة'), (release_year, 'سنة الإفراج')]:
        if year_val and (year_val < 1900 or year_val > current_year + 1):
            errors.append(f'{label} يجب أن يكون بين 1900 و {current_year}')

    if birth_year and death_year and death_year < birth_year:
        errors.append('سنة الوفاة لا يمكن أن تكون قبل سنة الميلاد')
    if birth_year and arrest_year and arrest_year < birth_year:
        errors.append('سنة الاعتقال لا يمكن أن تكون قبل سنة الميلاد')
    if arrest_year and release_year and release_year < arrest_year:
        errors.append('سنة الإفراج لا يمكن أن تكون قبل سنة الاعتقال')

    # Status validation
    status = form.get('status', '')
    if status and status not in ('survivor', 'enforced', 'deceased'):
        errors.append('حالة الشخص غير صالحة')

    # Evidence level validation
    evidence = form.get('evidence_level', '')
    if evidence and evidence not in ('high', 'medium', 'low', 'unverified', ''):
        errors.append('مستوى الأدلة غير صالح')

    return errors, warnings


@app.route('/entry', methods=['POST'])
@admin_required
def entry_submit():
    db = get_db()
    form = request.form
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    force = form.get('force', '') == 'true'
    submitter = session.get('username', 'unknown')

    print(f"\n{'='*60}")
    print(f"📝 NEW ENTRY SUBMISSION from user: {submitter}")
    print(f"   Name: {form.get('first_name', '')} {form.get('father_name', '')} {form.get('last_name', '')}")
    print(f"   Status: {form.get('status', '')} | Province: {form.get('province', '')}")
    print(f"   AJAX: {is_ajax} | Force: {force}")
    print(f"{'='*60}")

    # Validate
    errors, warnings = _validate_entry(form)
    if errors and not force:
        print(f"   ❌ VALIDATION FAILED: {errors}")
        if warnings:
            print(f"   ⚠️  Warnings: {warnings}")
        if is_ajax:
            return jsonify({'success': False, 'errors': errors, 'warnings': warnings})
        for e in errors:
            flash(e, 'error')
        return redirect(url_for('entry_form'))

    if warnings:
        print(f"   ⚠️  Warnings (non-blocking): {warnings}")

    print(f"   ✅ Validation passed")

    # Duplicate detection
    if not force:
        first = form.get('first_name', '').strip()
        father = form.get('father_name', '').strip()
        last = form.get('last_name', '').strip()
        nid = form.get('national_id', '').strip()
        dup = None
        if nid:
            dup = db.execute("SELECT id, first_name, father_name, last_name FROM records WHERE deleted_at IS NULL AND national_id=? AND national_id != ''", (nid,)).fetchone()
        if not dup and first and last:
            dup = db.execute("SELECT id, first_name, father_name, last_name FROM records WHERE deleted_at IS NULL AND first_name=? AND father_name=? AND last_name=?",
                             (first, father, last)).fetchone()
        if dup:
            dup_name = ' '.join(filter(None, [dup['first_name'], dup['father_name'], dup['last_name']]))
            msg = f'يوجد سجل مشابه: {dup_name} (#{dup["id"]}). أضف force=true للحفظ رغم ذلك.'
            print(f"   ⚠️  DUPLICATE DETECTED: {dup_name} (#{dup['id']})")
            if is_ajax:
                return jsonify({'success': False, 'duplicate': True, 'existing_id': dup['id'], 'message': msg, 'warnings': warnings})
            flash(msg, 'error')
            return redirect(url_for('entry_form'))

    # Handle file uploads
    photo_path, photo_hash = '', ''
    doc_path, doc_hash = '', ''
    screenshot_path = ''
    civil_doc_path = ''
    cv_path = ''
    cv_photo_path = ''

    if 'photo' in request.files:
        photo_path, photo_hash = save_upload(request.files['photo'], 'photos')
        photo_path = photo_path or ''
        photo_hash = photo_hash or ''

    if 'document' in request.files:
        doc_path, doc_hash = save_upload(request.files['document'], 'documents')
        doc_path = doc_path or ''
        doc_hash = doc_hash or ''

    screenshot_hash = ''
    if 'digital_evidence_screenshot' in request.files:
        screenshot_path, screenshot_hash = save_upload(request.files['digital_evidence_screenshot'], 'screenshots')
        screenshot_path = screenshot_path or ''
        screenshot_hash = screenshot_hash or ''

    if 'civil_registry_document' in request.files:
        civil_doc_path, _ = save_upload(request.files['civil_registry_document'], 'documents')
        civil_doc_path = civil_doc_path or ''

    if 'survivor_cv' in request.files:
        cv_path, _ = save_upload(request.files['survivor_cv'], 'documents')
        cv_path = cv_path or ''

    if 'survivor_cv_photo' in request.files:
        cv_photo_path, _ = save_upload(request.files['survivor_cv_photo'], 'photos')
        cv_photo_path = cv_photo_path or ''

    # Witnesses JSON
    witnesses = form.get('witnesses_data', '[]')

    # Detention facilities JSON
    detention_facilities = form.get('detention_facilities_data', '[]')

    # Children data JSON
    children_data = form.get('children_data', '[]')
    children_data_w = form.get('children_data_w', '[]')

    # Process chronic diseases checkboxes
    chronic_list = form.getlist('chronic_list')
    chronic_value = '، '.join(chronic_list) if chronic_list else form.get('chronic', '')
    has_hypertension = 1 if 'ضغط الدم' in chronic_list else int(form.get('has_hypertension', 0) or 0)
    has_diabetes = 1 if 'السكري' in chronic_list else int(form.get('has_diabetes', 0) or 0)

    # Determine record_slug
    slug = f"{form.get('first_name', '')}-{form.get('last_name', '')}-{int(time.time())}".replace(' ', '-')

    print(f"   📥 Inserting record into database...")
    try:
        db.execute("""INSERT INTO records (
        first_name, father_name, last_name, gender, mother_name,
        birth_day, birth_month, birth_year, province, national_id, family_book_number,
        phone, blood_type, photo_path, document_path,
        arrest_day, arrest_month, arrest_year, arrest_place,
        arrest_authority, arrest_reason, arrest_causer,
        status, release_day, release_month, release_year,
        death_day, death_month, death_year, death_place,
        marital, guardian_name, guardian_relation, guardian_phone,
        spouse_name, spouse_phone, has_kids, kids_count, children_data,
        ex_spouse_name, has_kids_w, kids_count_w, children_data_w,
        address, housing_type, rent_amount,
        employment, profession, employer, breadwinner,
        breadwinner_job, breadwinner_relation, breadwinner_relation_other,
        chronic, diseases, has_hypertension, has_diabetes, other_diseases,
        has_special_needs, special_needs_details,
        education, edu_type, edu_specialization, edu_university,
        kids_under_18_count, is_officially_registered,
        legal, legal_details, assoc, assoc_name, service_type,
        notes,
        case_type, reporter_name, reporter_relation, reporter_phone, reporter_id,
        informant_consent, witnesses_data,
        digital_evidence_type, digital_evidence_url, digital_evidence_url_status,
        digital_evidence_screenshot_path, digital_evidence_date,
        digital_evidence_description, digital_evidence_person_name,
        digital_evidence_death_date,
        civil_registry_status, civil_registry_date, civil_registry_document_path,
        has_conflicting_info, conflicting_info_details,
        evidence_level, evidence_sources_count,
        last_known_alive_date, last_known_location,
        detention_facilities_data,
        source_type, source_url, collection_date, collector_name,
        verification_status, methodology_notes, methodology_type,
        record_slug, photo_hash, document_hash,
        survivor_cv_path, survivor_cv_text, survivor_cv_photo_path,
        address_area, screenshot_hash
    ) VALUES (
        ?,?,?,?,?, ?,?,?,?,?,?, ?,?,?,?, ?,?,?,?,
        ?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?,?,
        ?,?,?,?, ?,?,?, ?,?,?,?, ?,?,?, ?,?,?,?,?,
        ?,?, ?,?,?,?, ?,?, ?,?,?,?,?, ?,
        ?,?,?,?,?, ?,?, ?,?,?, ?,?, ?,?, ?,
        ?,?,?, ?,?, ?,?, ?,?, ?,
        ?,?,?,?, ?,?, ?,?,?,?, ?,?,?,?,?
    )""", (
        form.get('first_name', ''), form.get('father_name', ''), form.get('last_name', ''),
        form.get('gender', ''), form.get('mother_name', ''),
        int(form.get('birth_day', 0) or 0), int(form.get('birth_month', 0) or 0),
        int(form.get('birth_year', 0) or 0),
        form.get('province', ''), form.get('national_id', ''),
        form.get('family_book_number', ''),
        form.get('phone', ''), form.get('blood_type', ''),
        photo_path, doc_path,
        int(form.get('arrest_day', 0) or 0), int(form.get('arrest_month', 0) or 0),
        int(form.get('arrest_year', 0) or 0), form.get('arrest_place', ''),
        form.get('arrest_authority', ''), form.get('arrest_reason', ''),
        form.get('arrest_causer', ''),
        form.get('status', ''), int(form.get('release_day', 0) or 0),
        int(form.get('release_month', 0) or 0), int(form.get('release_year', 0) or 0),
        int(form.get('death_day', 0) or 0), int(form.get('death_month', 0) or 0),
        int(form.get('death_year', 0) or 0), form.get('death_place', ''),
        form.get('marital', ''), form.get('guardian_name', ''),
        form.get('guardian_relation', ''), form.get('guardian_phone', ''),
        form.get('spouse_name', ''), form.get('spouse_phone', ''),
        form.get('has_kids', 'no'), int(form.get('kids_count', 0) or 0),
        children_data,
        form.get('ex_spouse_name', ''), form.get('has_kids_w', 'no'),
        int(form.get('kids_count_w', 0) or 0), children_data_w,
        form.get('address', ''), form.get('housing_type', ''),
        form.get('rent_amount', ''),
        form.get('employment', ''), form.get('profession', ''),
        form.get('employer', ''), form.get('breadwinner', ''),
        form.get('breadwinner_job', ''), form.get('breadwinner_relation', ''),
        form.get('breadwinner_relation_other', ''),
        chronic_value, form.get('diseases', ''),
        has_hypertension,
        has_diabetes, form.get('other_diseases', ''),
        int(form.get('has_special_needs', 0) or 0),
        form.get('special_needs_details', ''),
        form.get('education', ''), form.get('edu_type', ''),
        form.get('edu_specialization', ''), form.get('edu_university', ''),
        int(form.get('kids_under_18_count', 0) or 0),
        int(form.get('is_officially_registered', 0) or 0),
        form.get('legal', ''), form.get('legal_details', ''),
        form.get('assoc', ''), form.get('assoc_name', ''),
        form.get('service_type', ''),
        form.get('notes', ''),
        form.get('case_type', ''), form.get('reporter_name', ''),
        form.get('reporter_relation', ''), form.get('reporter_phone', ''),
        form.get('reporter_id', ''),
        1 if form.get('informant_consent') else 0,
        witnesses,
        form.get('digital_evidence_type', ''), form.get('digital_evidence_url', ''),
        form.get('digital_evidence_url_status', ''),
        screenshot_path, form.get('digital_evidence_date', ''),
        form.get('digital_evidence_description', ''),
        form.get('digital_evidence_person_name', ''),
        form.get('digital_evidence_death_date', ''),
        form.get('civil_registry_status', ''), form.get('civil_registry_date', ''),
        civil_doc_path,
        1 if form.get('has_conflicting_info') else 0,
        form.get('conflicting_info_details', ''),
        form.get('evidence_level', 'unverified'),
        int(form.get('evidence_sources_count', 0) or 0),
        form.get('last_known_alive_date', ''), form.get('last_known_location', ''),
        detention_facilities,
        form.get('source_type', ''), form.get('source_url', ''), form.get('collection_date', ''),
        form.get('collector_name', ''),
        'Unverified', form.get('methodology_notes', ''), form.get('methodology_type', ''),
        slug, photo_hash, doc_hash,
        cv_path, form.get('survivor_cv_text', ''), cv_photo_path,
        form.get('address_area', ''), screenshot_hash
    ))
        print(f"   ✅ INSERT executed successfully")  # noqa: E131
    except Exception as e:
        print(f"   ❌ INSERT FAILED: {type(e).__name__}: {e}")
        if is_ajax:
            return jsonify({'success': False, 'errors': [f'خطأ في قاعدة البيانات: {e}']})
        flash(f'خطأ في قاعدة البيانات: {e}', 'error')
        return redirect(url_for('entry_form'))

    # Use retry logic for concurrent access
    try:
        for attempt in range(3):
            try:
                db.commit()
                print(f"   ✅ COMMIT successful (attempt {attempt + 1})")
                break
            except sqlite3.OperationalError as e:
                if 'locked' in str(e) and attempt < 2:
                    print(f"   ⏳ DB locked, retrying... (attempt {attempt + 1})")
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise
    except Exception as e:
        print(f"   ❌ COMMIT FAILED: {type(e).__name__}: {e}")
        if is_ajax:
            return jsonify({'success': False, 'errors': [f'خطأ في حفظ البيانات: {e}']})
        flash(f'خطأ في حفظ البيانات: {e}', 'error')
        return redirect(url_for('entry_form'))

    # Save additional documents to record_documents table
    new_record_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    print(f"   📋 New record ID: #{new_record_id}")
    doc_count = int(form.get('record_doc_count', 0) or 0)
    for i in range(doc_count):
        file_key = f'record_doc_file_{i}'
        if file_key in request.files and request.files[file_key].filename:
            doc_path, doc_hash = save_upload(request.files[file_key], 'documents')
            if doc_path:
                db.execute("""INSERT INTO record_documents
                    (record_id, doc_type, file_path, file_hash, original_filename,
                     description, document_date, source_url, uploaded_by)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (new_record_id, form.get(f'record_doc_type_{i}', 'other'),
                     doc_path, doc_hash or '', request.files[file_key].filename,
                     form.get(f'record_doc_desc_{i}', ''),
                     form.get(f'record_doc_date_{i}', ''),
                     form.get(f'record_doc_url_{i}', ''),
                     form.get('collector_name', '')))
    if doc_count > 0:
        db.commit()

    # Save companions to record_companions table
    comp_count = int(form.get('companions_count', 0) or 0)
    for i in range(comp_count):
        comp_first = form.get(f'comp_first_{i}', '').strip()
        if not comp_first:
            continue
        db.execute("""INSERT INTO record_companions
            (record_id, first_name, father_name, last_name, mother_name, notes)
            VALUES (?,?,?,?,?,?)""",
            (new_record_id, comp_first,
             form.get(f'comp_father_{i}', '').strip(),
             form.get(f'comp_last_{i}', '').strip(),
             form.get(f'comp_mother_{i}', '').strip(),
             form.get(f'comp_notes_{i}', '').strip()))
    if comp_count > 0:
        db.commit()

    log_audit('record_create', 'record', details=form.get('first_name', '') + ' ' + form.get('last_name', ''))
    resp_msg = 'تم حفظ السجل بنجاح. شكراً لمساهمتك في التوثيق.'
    if warnings:
        resp_msg += ' (تنبيهات: ' + '، '.join(warnings) + ')'

    print(f"   🎉 RECORD SAVED SUCCESSFULLY: #{new_record_id}")
    print(f"   Name: {form.get('first_name', '')} {form.get('father_name', '')} {form.get('last_name', '')}")
    print(f"   Documents: {doc_count} | Companions: {comp_count}")
    print(f"{'='*60}\n")

    if is_ajax:
        return jsonify({'success': True, 'message': resp_msg, 'warnings': warnings, 'record_id': new_record_id})

    flash(resp_msg, 'success')
    return redirect(url_for('entry_form'))


# ---------------------------------------------------------------------------
# Routes – Admin
# ---------------------------------------------------------------------------
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        ip = request.remote_addr or '0.0.0.0'
        now = time.time()
        # Clean old attempts and check rate limit
        cutoff = now - LOGIN_LOCKOUT_MINUTES * 60
        _login_attempts[ip] = [t for t in _login_attempts.get(ip, []) if t > cutoff]
        if len(_login_attempts[ip]) >= LOGIN_MAX_ATTEMPTS:
            remaining = int((cutoff + LOGIN_LOCKOUT_MINUTES * 60 - now + _login_attempts[ip][0]) / 60) + 1
            flash(f'تم حظر تسجيل الدخول لمدة {remaining} دقائق بسبب محاولات كثيرة', 'error')
            return render_template('admin_login.html')

        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        # Try multi-user login first
        authenticated = False
        user_role = 'admin'
        display_name = ''
        if username:
            db = get_db()
            user = db.execute("SELECT * FROM users WHERE username=? AND is_active=1", (username,)).fetchone()
            if user and check_password_hash(user['password_hash'], password):
                authenticated = True
                user_role = user['role']
                display_name = user['display_name'] or username
                db.execute("UPDATE users SET last_login=datetime('now','localtime') WHERE id=?", (user['id'],))
                db.commit()

        # Fall back to legacy admin password
        if not authenticated:
            pw_hash = _get_admin_password_hash()
            if check_password_hash(pw_hash, password):
                authenticated = True
                user_role = 'admin'
                display_name = 'مدير النظام'

        if authenticated:
            session.clear()
            session['is_admin'] = True
            session['user_role'] = user_role
            session['display_name'] = display_name
            session['username'] = username or 'admin'  # Berkeley Protocol: chain of custody tracking
            session['login_time'] = time.time()
            session.permanent = True
            _login_attempts.pop(ip, None)
            log_audit('login', 'user', 0, {'description': f'User logged in: {username or "admin"} ({user_role})'})
            # Redirect based on role
            if user_role == 'data_entry':
                return redirect(url_for('entry_form'))
            return redirect(url_for('admin_dashboard'))
        _login_attempts.setdefault(ip, []).append(now)
        attempts_left = LOGIN_MAX_ATTEMPTS - len(_login_attempts[ip])
        msg = 'كلمة المرور غير صحيحة'
        if attempts_left <= 2:
            msg += f' ({attempts_left} محاولات متبقية)'
        flash(msg, 'error')
    return render_template('admin_login.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))


@app.route('/admin/change-password', methods=['GET', 'POST'])
@admin_required
def admin_change_password():
    if request.method == 'POST':
        current = request.form.get('current_password', '')
        new_pw = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        if not check_password_hash(_get_admin_password_hash(), current):
            flash('كلمة المرور الحالية غير صحيحة', 'error')
        elif len(new_pw) < 6:
            flash('كلمة المرور الجديدة يجب أن تكون 6 أحرف على الأقل', 'error')
        elif new_pw != confirm:
            flash('كلمة المرور الجديدة غير متطابقة', 'error')
        else:
            _set_admin_password(new_pw)
            flash('تم تغيير كلمة المرور بنجاح', 'success')
            return redirect(url_for('admin_dashboard'))
    return render_template('admin_change_password.html')


@app.route('/admin/users')
@admin_required
def admin_users():
    """User management page (admin only)."""
    if session.get('user_role', 'admin') != 'admin':
        flash('فقط المدير يمكنه إدارة المستخدمين', 'error')
        return redirect(url_for('admin_dashboard'))
    db = get_db()
    users = db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    role_labels = {'admin': 'مدير', 'data_entry': 'إدخال بيانات', 'viewer': 'مشاهد'}
    return render_template('admin_users.html', users=users, role_labels=role_labels)


@app.route('/admin/users/add', methods=['POST'])
@admin_required
def admin_user_add():
    if session.get('user_role', 'admin') != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    display_name = request.form.get('display_name', '').strip()
    role = request.form.get('role', 'viewer')
    if not username or not password:
        flash('اسم المستخدم وكلمة المرور مطلوبان', 'error')
        return redirect(url_for('admin_users'))
    if role not in ('admin', 'data_entry', 'viewer'):
        role = 'viewer'
    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if existing:
        flash('اسم المستخدم موجود مسبقاً', 'error')
        return redirect(url_for('admin_users'))
    db.execute(
        "INSERT INTO users (username, password_hash, display_name, role) VALUES (?, ?, ?, ?)",
        (username, generate_password_hash(password), display_name, role)
    )
    db.commit()
    log_audit('user_create', 'user', 0, f'Created user: {username} ({role})')
    flash(f'تم إضافة المستخدم {username}', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<int:user_id>/toggle', methods=['POST'])
@admin_required
def admin_user_toggle(user_id):
    if session.get('user_role', 'admin') != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if user:
        new_status = 0 if user['is_active'] else 1
        db.execute("UPDATE users SET is_active=? WHERE id=?", (new_status, user_id))
        db.commit()
        log_audit('user_toggle', 'user', user_id, f'{"activated" if new_status else "deactivated"} {user["username"]}')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<int:user_id>/reset-password', methods=['POST'])
@admin_required
def admin_user_reset_password(user_id):
    if session.get('user_role', 'admin') != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403
    new_pw = request.form.get('new_password', '')
    if len(new_pw) < 6:
        flash('كلمة المرور يجب أن تكون 6 أحرف على الأقل', 'error')
        return redirect(url_for('admin_users'))
    db = get_db()
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new_pw), user_id))
    db.commit()
    log_audit('user_reset_password', 'user', user_id)
    flash('تم تغيير كلمة المرور', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def admin_user_delete(user_id):
    """Delete a user account (admin only)."""
    if session.get('user_role', 'admin') != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        flash('المستخدم غير موجود', 'error')
        return redirect(url_for('admin_users'))
    if user['username'] == session.get('username'):
        flash('لا يمكنك حذف حسابك الخاص', 'error')
        return redirect(url_for('admin_users'))
    username = user['username']
    db.execute("DELETE FROM users WHERE id=?", (user_id,))
    db.execute("DELETE FROM user_drafts WHERE username=?", (username,))
    db.commit()
    log_audit('user_delete', 'user', user_id, f'Deleted user: {username}')
    print(f"   🗑️ USER DELETED: {username} (ID: {user_id})")
    flash(f'تم حذف المستخدم {username}', 'success')
    return redirect(url_for('admin_users'))


# ---------------------------------------------------------------------------
# Notifications system (SSE-based real-time push)
# ---------------------------------------------------------------------------
_notification_subscribers = []  # list of queue.Queue objects for SSE

@app.route('/admin/notifications')
@admin_required
def admin_notifications():
    """Notifications management page (admin only)."""
    if session.get('user_role', 'admin') != 'admin':
        flash('فقط المدير يمكنه إدارة الإشعارات', 'error')
        return redirect(url_for('admin_dashboard'))
    db = get_db()
    notifications = db.execute("SELECT * FROM notifications ORDER BY created_at DESC LIMIT 100").fetchall()
    users = db.execute("SELECT username, display_name, role FROM users WHERE is_active=1 ORDER BY display_name").fetchall()
    return render_template('admin_notifications.html', notifications=notifications, users=users)


@app.route('/admin/notifications/send', methods=['POST'])
@admin_required
def admin_notification_send():
    """Send a notification to all or specific users."""
    if session.get('user_role', 'admin') != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403
    message = request.form.get('message', '').strip()
    target = request.form.get('target', '*')  # '*' = all, or comma-separated usernames
    if not message:
        flash('الرسالة مطلوبة', 'error')
        return redirect(url_for('admin_notifications'))
    db = get_db()
    sender = session.get('display_name', session.get('username', 'admin'))
    db.execute("INSERT INTO notifications (message, sender, target_users) VALUES (?,?,?)",
               (message, sender, target))
    db.commit()
    # Push to all SSE subscribers
    import queue
    notif_data = json.dumps({
        'message': message,
        'sender': sender,
        'target': target,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M')
    }, ensure_ascii=False)
    dead = []
    for q in _notification_subscribers:
        try:
            q.put_nowait(notif_data)
        except queue.Full:
            dead.append(q)
    for q in dead:
        _notification_subscribers.remove(q)
    print(f"   🔔 NOTIFICATION SENT to {'all' if target == '*' else target}: {message[:50]}...")
    flash('تم إرسال الإشعار', 'success')
    return redirect(url_for('admin_notifications'))


@app.route('/api/notifications/stream')
@admin_required
def notification_stream():
    """SSE endpoint for real-time notifications."""
    import queue
    q = queue.Queue(maxsize=50)
    _notification_subscribers.append(q)
    username = session.get('username', '')

    def generate():
        try:
            while True:
                try:
                    data = q.get(timeout=30)
                    # Filter by target
                    parsed = json.loads(data)
                    target = parsed.get('target', '*')
                    if target == '*' or username in target.split(','):
                        yield f"data: {data}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        except GeneratorExit:
            pass
        finally:
            if q in _notification_subscribers:
                _notification_subscribers.remove(q)

    return app.response_class(generate(), mimetype='text/event-stream',
                              headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/api/notifications/unread')
@admin_required
def api_notifications_unread():
    """Get unread notification count and recent messages."""
    username = session.get('username', '')
    db = get_db()
    notifs = db.execute(
        "SELECT * FROM notifications ORDER BY created_at DESC LIMIT 20").fetchall()
    unread = []
    for n in notifs:
        target = n['target_users']
        if target != '*' and username not in target.split(','):
            continue
        read_by = json.loads(n['is_read_by'] or '[]')
        if username not in read_by:
            unread.append({
                'id': n['id'], 'message': n['message'],
                'sender': n['sender'], 'time': n['created_at']
            })
    return jsonify({'count': len(unread), 'notifications': unread[:10]})


@app.route('/api/notifications/mark-read', methods=['POST'])
@admin_required
def api_notifications_mark_read():
    """Mark notifications as read for current user."""
    username = session.get('username', '')
    notif_ids = request.get_json(silent=True) or {}
    ids = notif_ids.get('ids', [])
    db = get_db()
    for nid in ids:
        row = db.execute("SELECT is_read_by FROM notifications WHERE id=?", (nid,)).fetchone()
        if row:
            read_by = json.loads(row['is_read_by'] or '[]')
            if username not in read_by:
                read_by.append(username)
                db.execute("UPDATE notifications SET is_read_by=? WHERE id=?",
                           (json.dumps(read_by), nid))
    db.commit()
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# Pending edits (user suggestions awaiting admin approval)
# ---------------------------------------------------------------------------
@app.route('/record/<int:record_id>/suggest-edit', methods=['GET', 'POST'])
@admin_required
def suggest_record_edit(record_id):
    """Allow non-admin users to suggest edits to a record."""
    db = get_db()
    record = db.execute("SELECT * FROM records WHERE id=? AND deleted_at IS NULL", (record_id,)).fetchone()
    if not record:
        flash('السجل غير موجود', 'error')
        return redirect(url_for('entry_form'))

    if request.method == 'POST':
        edit_data = {}
        editable_fields = [
            # Personal
            'first_name', 'father_name', 'last_name', 'mother_name', 'gender',
            'birth_day', 'birth_month', 'birth_year', 'province', 'national_id',
            'family_book_number', 'phone', 'blood_type',
            # Status & arrest
            'status', 'case_type',
            'arrest_day', 'arrest_month', 'arrest_year', 'arrest_place',
            'arrest_authority', 'arrest_reason', 'arrest_causer',
            'last_known_location', 'last_known_alive_date',
            # Release & death
            'release_day', 'release_month', 'release_year',
            'death_day', 'death_month', 'death_year', 'death_place',
            # Family
            'marital', 'guardian_name', 'guardian_relation', 'guardian_phone',
            'spouse_name', 'spouse_phone', 'ex_spouse_name',
            # Housing & employment
            'address', 'address_area', 'housing_type', 'rent_amount',
            'employment', 'profession', 'employer',
            'breadwinner', 'breadwinner_job', 'breadwinner_relation', 'breadwinner_relation_other',
            # Education
            'education', 'edu_type', 'edu_specialization', 'edu_university',
            # Health
            'chronic', 'other_diseases', 'special_needs_details',
            # Legal & associations
            'legal', 'legal_details', 'assoc', 'assoc_name', 'service_type',
            # Reporter
            'reporter_name', 'reporter_relation', 'reporter_phone', 'reporter_id',
            # Digital evidence
            'digital_evidence_type', 'digital_evidence_url', 'digital_evidence_url_status',
            'digital_evidence_date', 'digital_evidence_person_name',
            'digital_evidence_death_date', 'digital_evidence_description',
            # Civil registry
            'civil_registry_status', 'civil_registry_date',
            'conflicting_info_details',
            # Methodology
            'notes', 'methodology_notes', 'methodology_type', 'source_url', 'source_type',
            'survivor_cv_text',
        ]
        for field in editable_fields:
            new_val = request.form.get(field, '').strip()
            old_val = str(record[field] or '').strip() if record[field] is not None else ''
            if new_val and new_val != old_val:
                edit_data[field] = {'old': old_val, 'new': new_val}

        # Checkbox/integer fields
        for checkbox_field, label in [('has_special_needs', 'ذوي احتياجات خاصة'),
                                       ('is_officially_registered', 'مسجل رسمياً'),
                                       ('informant_consent', 'موافقة المُبلِّغ'),
                                       ('has_conflicting_info', 'معلومات متضاربة')]:
            new_val = '1' if request.form.get(checkbox_field) else '0'
            old_val = str(record[checkbox_field] or 0)
            if new_val != old_val:
                edit_data[checkbox_field] = {'old': old_val, 'new': new_val}

        # JSON fields: children_data, witnesses_data
        for json_field in ['children_data', 'witnesses_data', 'detention_facilities_data']:
            new_val = request.form.get(json_field, '').strip()
            if new_val:
                old_val = str(record[json_field] or '[]')
                if new_val != old_val:
                    edit_data[json_field] = {'old': old_val, 'new': new_val}

        # Handle file uploads
        file_uploads = [
            ('photo', 'photos', 'photo_path', 'photo_hash'),
            ('document', 'documents', 'document_path', 'document_hash'),
            ('digital_evidence_screenshot', 'screenshots', 'digital_evidence_screenshot_path', None),
            ('civil_registry_document', 'documents', 'civil_registry_document_path', None),
            ('survivor_cv', 'documents', 'survivor_cv_path', None),
            ('survivor_cv_photo', 'photos', 'survivor_cv_photo_path', None),
        ]
        for file_key, subfolder, path_field, hash_field in file_uploads:
            if file_key in request.files and request.files[file_key].filename:
                saved_path, saved_hash = save_upload(request.files[file_key], subfolder)
                if saved_path:
                    edit_data[path_field] = {'old': record[path_field] or '', 'new': saved_path}
                    if hash_field:
                        edit_data[hash_field] = {'old': record[hash_field] or '', 'new': saved_hash or ''}

        if not edit_data:
            flash('لم يتم تغيير أي بيانات', 'error')
            return redirect(url_for('suggest_record_edit', record_id=record_id))

        submitter = session.get('username', 'unknown')
        db.execute(
            "INSERT INTO pending_edits (record_id, submitted_by, edit_data) VALUES (?,?,?)",
            (record_id, submitter, json.dumps(edit_data, ensure_ascii=False)))
        db.commit()
        log_audit('suggest_edit', 'record', record_id, f'Edit suggestion by {submitter}')
        print(f"   📝 EDIT SUGGESTION: Record #{record_id} by {submitter} ({len(edit_data)} fields)")
        flash('تم إرسال اقتراح التعديل للمراجعة من قبل المدير', 'success')
        return redirect(url_for('suggest_record_edit', record_id=record_id))

    # GET: show suggestion form with children parsed
    children = []
    try:
        children = json.loads(record['children_data'] or '[]')
    except (json.JSONDecodeError, TypeError):
        pass
    return render_template('suggest_edit.html', record=record, children=children)


@app.route('/admin/pending-edits')
@admin_required
def admin_pending_edits():
    """Admin page to review pending edit suggestions."""
    if session.get('user_role', 'admin') != 'admin':
        flash('فقط المدير يمكنه مراجعة التعديلات', 'error')
        return redirect(url_for('admin_dashboard'))
    db = get_db()
    pending = db.execute("""
        SELECT pe.*, r.first_name, r.father_name, r.last_name
        FROM pending_edits pe
        JOIN records r ON r.id = pe.record_id
        ORDER BY pe.status = 'pending' DESC, pe.created_at DESC
        LIMIT 200
    """).fetchall()
    return render_template('admin_pending_edits.html', pending=pending)


@app.route('/admin/pending-edits/<int:edit_id>/approve', methods=['POST'])
@admin_required
def admin_approve_edit(edit_id):
    """Approve a pending edit and apply changes to the record."""
    if session.get('user_role', 'admin') != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403
    db = get_db()
    edit = db.execute("SELECT * FROM pending_edits WHERE id=?", (edit_id,)).fetchone()
    if not edit or edit['status'] != 'pending':
        flash('التعديل غير موجود أو تم مراجعته مسبقاً', 'error')
        return redirect(url_for('admin_pending_edits'))

    edit_data = json.loads(edit['edit_data'])
    record_id = edit['record_id']

    # Apply each field change
    for field, change in edit_data.items():
        new_val = change['new']
        db.execute(f"UPDATE records SET {field}=? WHERE id=?", (new_val, record_id))

    reviewer = session.get('username', 'admin')
    db.execute("""UPDATE pending_edits SET status='approved', reviewed_by=?,
        reviewed_at=datetime('now','localtime') WHERE id=?""", (reviewer, edit_id))
    db.commit()
    log_audit('approve_edit', 'record', record_id,
              f'Approved edit #{edit_id} by {edit["submitted_by"]} ({len(edit_data)} fields)')
    print(f"   ✅ EDIT APPROVED: #{edit_id} for record #{record_id} by {reviewer}")
    flash('تم الموافقة على التعديل وتطبيقه', 'success')
    return redirect(url_for('admin_pending_edits'))


@app.route('/admin/pending-edits/<int:edit_id>/reject', methods=['POST'])
@admin_required
def admin_reject_edit(edit_id):
    """Reject a pending edit."""
    if session.get('user_role', 'admin') != 'admin':
        return jsonify({'error': 'غير مصرح'}), 403
    db = get_db()
    edit = db.execute("SELECT * FROM pending_edits WHERE id=?", (edit_id,)).fetchone()
    if not edit or edit['status'] != 'pending':
        flash('التعديل غير موجود أو تم مراجعته مسبقاً', 'error')
        return redirect(url_for('admin_pending_edits'))

    reason = request.form.get('reason', '')
    reviewer = session.get('username', 'admin')
    db.execute("""UPDATE pending_edits SET status='rejected', reviewed_by=?,
        reviewed_at=datetime('now','localtime'), notes=? WHERE id=?""",
               (reviewer, reason, edit_id))
    db.commit()
    log_audit('reject_edit', 'record', edit['record_id'],
              f'Rejected edit #{edit_id} by {edit["submitted_by"]}')
    print(f"   ❌ EDIT REJECTED: #{edit_id} for record #{edit['record_id']} by {reviewer}")
    flash('تم رفض التعديل', 'info')
    return redirect(url_for('admin_pending_edits'))


@app.route('/admin')
@admin_required
def admin_dashboard():
    db = get_db()

    # Statistics (uses cached single-query function to eliminate duplicate COUNTs)
    cs = _get_cached_stats(db)
    total = cs['total']
    survivors = cs['survivors']
    enforced = cs['enforced']
    deceased = cs['deceased']
    males = cs['males']
    females = cs['females']

    # Province distribution
    province_stats = db.execute(
        "SELECT province, COUNT(*) as cnt FROM records WHERE deleted_at IS NULL GROUP BY province ORDER BY cnt DESC"
    ).fetchall()

    # Authority distribution (with normalization of aliases)
    raw_authority_stats = db.execute(
        "SELECT arrest_authority, COUNT(*) as cnt FROM records WHERE deleted_at IS NULL AND arrest_authority IS NOT NULL AND arrest_authority != '' GROUP BY arrest_authority ORDER BY cnt DESC"
    ).fetchall()

    # Merge counts using keyword-based normalization
    merged = {}
    for row in raw_authority_stats:
        key = normalize_authority(row['arrest_authority'])
        merged[key] = merged.get(key, 0) + row['cnt']

    # Sort by count descending and limit to 15
    authority_stats = sorted(merged.items(), key=lambda x: x[1], reverse=True)[:15]

    # Year distribution
    year_stats = db.execute(
        "SELECT arrest_year, COUNT(*) as cnt FROM records WHERE deleted_at IS NULL AND arrest_year > 0 GROUP BY arrest_year ORDER BY arrest_year"
    ).fetchall()

    # Age distribution (D2)
    current_year = datetime.now().year
    age_brackets = {'0-17': 0, '18-30': 0, '31-45': 0, '46-60': 0, '60+': 0, 'غير محدد': 0}
    birth_years = db.execute("SELECT birth_year FROM records WHERE deleted_at IS NULL").fetchall()
    for row in birth_years:
        by = row['birth_year'] or 0
        if by <= 0:
            age_brackets['غير محدد'] += 1
        else:
            age = current_year - by
            if age < 18:
                age_brackets['0-17'] += 1
            elif age <= 30:
                age_brackets['18-30'] += 1
            elif age <= 45:
                age_brackets['31-45'] += 1
            elif age <= 60:
                age_brackets['46-60'] += 1
            else:
                age_brackets['60+'] += 1

    # Health & vulnerability stats (D3) - from cached stats
    health_stats = cs['health']

    # Education breakdown (D4)
    edu_stats = db.execute(
        "SELECT education, COUNT(*) as cnt FROM records WHERE deleted_at IS NULL AND education IS NOT NULL AND education != '' GROUP BY education ORDER BY cnt DESC"
    ).fetchall()

    # Member payment summary (D5)
    payment_stats = {'total_due': 0, 'total_paid': 0, 'paid_count': 0, 'unpaid_count': 0}
    try:
        ps = db.execute("SELECT status, COUNT(*) as cnt, SUM(amount) as total FROM member_payments GROUP BY status").fetchall()
        for p in ps:
            if p['status'] == 'paid':
                payment_stats['paid_count'] = p['cnt']
                payment_stats['total_paid'] = p['total'] or 0
            else:
                payment_stats['unpaid_count'] = p['cnt']
            payment_stats['total_due'] += p['total'] or 0
    except (sqlite3.OperationalError, TypeError, KeyError) as e:
        app.logger.warning(f"Payment stats error: {e}")

    # Volunteer summary (D6)
    vol_stats = {
        'active': db.execute("SELECT COUNT(*) FROM volunteers WHERE status='active'").fetchone()[0],
        'total_hours': 0,
        'total_activities': db.execute("SELECT COUNT(*) FROM volunteer_activities").fetchone()[0],
    }
    try:
        h = db.execute("SELECT SUM(hours) FROM volunteer_attendance").fetchone()[0]
        vol_stats['total_hours'] = round(h or 0, 1)
    except (sqlite3.OperationalError, TypeError) as e:
        app.logger.warning(f"Volunteer hours error: {e}")

    # Data completeness (D1) - uses cached incomplete count
    total_profiles = total + vol_stats['active'] + db.execute("SELECT COUNT(*) FROM members").fetchone()[0]
    incomplete_records = cs['incomplete_records']
    incomplete_vols = db.execute(
        "SELECT COUNT(*) FROM volunteers WHERE phone='' OR national_id='' OR role=''"
    ).fetchone()[0]
    incomplete_members = db.execute(
        "SELECT COUNT(*) FROM members WHERE phone='' OR national_id='' OR membership_type=''"
    ).fetchone()[0]
    completion_pct = round((1 - (incomplete_records + incomplete_vols + incomplete_members) / max(total_profiles, 1)) * 100)

    stats = {
        'total': total, 'survivors': survivors, 'enforced': enforced,
        'deceased': deceased, 'males': males, 'females': females,
        'province_stats': province_stats, 'authority_stats': authority_stats,
        'year_stats': year_stats,
        'age_brackets': age_brackets,
        'health_stats': health_stats,
        'edu_stats': edu_stats,
        'payment_stats': payment_stats,
        'vol_stats': vol_stats,
        'completion_pct': completion_pct,
        'incomplete_records': incomplete_records,
        'incomplete_vols': incomplete_vols,
        'incomplete_members': incomplete_members,
    }

    return render_template('admin_dashboard.html', stats=stats)


@app.route('/admin/dashboard/print')
@admin_required
def admin_dashboard_print():
    """Printable statistics report for the dashboard."""
    db = get_db()

    total = db.execute("SELECT COUNT(*) FROM records WHERE deleted_at IS NULL").fetchone()[0]
    survivors = db.execute("SELECT COUNT(*) FROM records WHERE deleted_at IS NULL AND status='survivor'").fetchone()[0]
    enforced = db.execute("SELECT COUNT(*) FROM records WHERE deleted_at IS NULL AND status='enforced'").fetchone()[0]
    deceased = db.execute("SELECT COUNT(*) FROM records WHERE deleted_at IS NULL AND status='deceased'").fetchone()[0]
    males = db.execute("SELECT COUNT(*) FROM records WHERE deleted_at IS NULL AND gender='male'").fetchone()[0]
    females = db.execute("SELECT COUNT(*) FROM records WHERE deleted_at IS NULL AND gender='female'").fetchone()[0]

    province_stats = db.execute(
        "SELECT province, COUNT(*) as cnt FROM records WHERE deleted_at IS NULL GROUP BY province ORDER BY cnt DESC"
    ).fetchall()

    health_stats = {
        'chronic': db.execute("SELECT COUNT(*) FROM records WHERE deleted_at IS NULL AND chronic IS NOT NULL AND chronic != '' AND chronic != 'لا'").fetchone()[0],
        'special_needs': db.execute("SELECT COUNT(*) FROM records WHERE deleted_at IS NULL AND has_special_needs = 1").fetchone()[0],
        'hypertension': db.execute("SELECT COUNT(*) FROM records WHERE deleted_at IS NULL AND has_hypertension = 1").fetchone()[0],
        'diabetes': db.execute("SELECT COUNT(*) FROM records WHERE deleted_at IS NULL AND has_diabetes = 1").fetchone()[0],
    }

    edu_stats = db.execute(
        "SELECT education, COUNT(*) as cnt FROM records WHERE deleted_at IS NULL AND education IS NOT NULL AND education != '' GROUP BY education ORDER BY cnt DESC"
    ).fetchall()

    stats = {
        'total': total, 'survivors': survivors, 'enforced': enforced,
        'deceased': deceased, 'males': males, 'females': females,
        'province_stats': province_stats, 'health_stats': health_stats,
        'edu_stats': edu_stats, 'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }
    return render_template('admin_dashboard_print.html', stats=stats)


def compute_need_score(record):
    """Compute a vulnerability/need score (higher = more in need).
    Factors: widow with kids, many minor children, young kids, rent,
    chronic diseases, special needs, low education, no breadwinner."""
    score = 0
    current_year = datetime.now().year

    # Widow/wife of missing (married male deceased/enforced) = very high need
    if record['gender'] == 'male' and record['marital'] == 'married' and record['status'] in ('deceased', 'enforced'):
        score += 30

    # Number of minor children (under 18)
    kids_u18 = record['kids_under_18_count'] or 0
    score += kids_u18 * 8  # 8 points per minor child

    # Young children (under 6) get extra points
    try:
        children = json.loads(record['children_data'] or '[]')
        for c in children:
            age = None
            if c.get('birth_year'):
                age = current_year - int(c['birth_year'])
            elif c.get('age'):
                age = int(c['age'])
            if age is not None and age < 6:
                score += 5  # extra for very young children
    except (json.JSONDecodeError, TypeError):
        pass

    # Rent (paying rent = more vulnerable)
    if record['housing_type'] == 'إيجار':
        score += 10
    rent = record['rent_amount'] or ''
    if rent:
        try:
            rent_val = int(str(rent).replace(',', '').strip())
            if rent_val > 0:
                score += min(rent_val // 50000, 10)  # up to 10 extra points for high rent
        except (ValueError, TypeError):
            pass

    # Chronic diseases
    chronic = record['chronic'] or ''
    if chronic and chronic not in ('لا', ''):
        disease_count = len([d for d in chronic.split('، ') if d.strip()])
        score += 5 + disease_count * 2

    if record['has_hypertension']:
        score += 3
    if record['has_diabetes']:
        score += 3

    # Special needs
    if record['has_special_needs']:
        score += 12

    # Low education
    edu = record['education'] or ''
    low_edu = ['أمّي', 'ابتدائية', 'إعدادية']
    if edu in low_edu:
        score += 6

    # No breadwinner or self-breadwinner for deceased/enforced
    breadwinner = record['breadwinner'] or ''
    if not breadwinner or breadwinner == 'لا يوجد':
        score += 8

    # Legal problems
    legal = record['legal'] or ''
    if legal == 'نعم':
        score += 4

    return score


def _filters_from_request_args(args):
    """Build a filters dict from request.args (or any MultiDict).
    Used by admin_records, api_records, and PDF/Excel export routes."""
    status_list = args.getlist('status') if hasattr(args, 'getlist') else [args.get('status', '')]
    expanded = []
    for s in status_list:
        if ',' in s:
            expanded.extend(s.split(','))
        elif s:
            expanded.append(s)
    status_list = expanded

    return {
        'status': ','.join(status_list),
        'status_list': status_list,
        'province': args.get('province', ''),
        'gender': args.get('gender', ''),
        'arrest_authority': args.get('arrest_authority', ''),
        'arrest_place': args.get('arrest_place', ''),
        'arrest_year_from': args.get('arrest_year_from', ''),
        'arrest_year_to': args.get('arrest_year_to', ''),
        'birth_year_from': args.get('birth_year_from', ''),
        'birth_year_to': args.get('birth_year_to', ''),
        'marital': args.get('marital', ''),
        'education': args.get('education', ''),
        'education_max': args.get('education_max', ''),
        'housing_type': args.get('housing_type', ''),
        'blood_type': args.get('blood_type', ''),
        'has_kids': args.get('has_kids', ''),
        'has_kids_under_18': args.get('has_kids_under_18', ''),
        'minor_age_threshold': args.get('minor_age_threshold', ''),
        'kids_max_age': args.get('kids_max_age', ''),
        'has_photo': args.get('has_photo', ''),
        'has_document': args.get('has_document', ''),
        'case_type': args.get('case_type', ''),
        'evidence_level': args.get('evidence_level', ''),
        'verification_status': args.get('verification_status', ''),
        'civil_registry_status': args.get('civil_registry_status', ''),
        'digital_evidence_type': args.get('digital_evidence_type', ''),
        'has_conflicting_info': args.get('has_conflicting_info', ''),
        'search': args.get('search', ''),
        'has_special_needs': args.get('has_special_needs', ''),
        'chronic': args.get('chronic', ''),
        'breadwinner': args.get('breadwinner', ''),
        'has_hypertension': args.get('has_hypertension', ''),
        'has_diabetes': args.get('has_diabetes', ''),
        'is_registered': args.get('is_registered', ''),
        'has_legal': args.get('has_legal', ''),
        'has_assoc': args.get('has_assoc', ''),
        'reporter_relation': args.get('reporter_relation', ''),
        'widows_filter': args.get('widows_filter', ''),
        'spouse_search': args.get('spouse_search', ''),
        'child_name_search': args.get('child_name_search', ''),
        'child_education': args.get('child_education', ''),
        'employment': args.get('employment', ''),
        'profession': args.get('profession', ''),
        'address_search': args.get('address_search', ''),
        'arrest_reason': args.get('arrest_reason', ''),
        'death_year_from': args.get('death_year_from', ''),
        'death_year_to': args.get('death_year_to', ''),
        'release_year_from': args.get('release_year_from', ''),
        'release_year_to': args.get('release_year_to', ''),
        'notes_search': args.get('notes_search', ''),
        'employer': args.get('employer', ''),
        'breadwinner_relation': args.get('breadwinner_relation', ''),
        'age_from': args.get('age_from', ''),
        'age_to': args.get('age_to', ''),
        'has_guardian': args.get('has_guardian', ''),
        'digital_evidence_url_status': args.get('digital_evidence_url_status', ''),
        'kids_age_from': args.get('kids_age_from', ''),
        'kids_age_to': args.get('kids_age_to', ''),
        'collector_name': args.get('collector_name', ''),
        'sort_by_need': args.get('sort_by_need', ''),
        'created_from': args.get('created_from', ''),
        'created_to': args.get('created_to', ''),
        'collection_date_from': args.get('collection_date_from', ''),
        'collection_date_to': args.get('collection_date_to', ''),
        'source_type': args.get('source_type', ''),
        'has_phone': args.get('has_phone', ''),
        'family_book_number': args.get('family_book_number', ''),
        'national_id_search': args.get('national_id_search', ''),
        'has_rent': args.get('has_rent', ''),
        'detention_facility_search': args.get('detention_facility_search', ''),
        'record_status': args.get('record_status', ''),
        'service_name': args.get('service_name', ''),
        'service_count_min': args.get('service_count_min', ''),
        'service_provider': args.get('service_provider', ''),
        'last_service_from': args.get('last_service_from', ''),
        'last_service_to': args.get('last_service_to', ''),
        'service_filter_mode': args.get('service_filter_mode', ''),
    }


def _build_record_filter_conditions(filters):
    """Build SQL conditions and params from a filters dict.

    Used by admin_records, api_export_to_list, and other endpoints that
    need to filter the records table with the same logic.

    Args:
        filters: dict with filter keys and string values.
                 Uses .get() so missing keys are safe.
    Returns:
        (conditions, params) - lists for building WHERE clause.
    """
    conditions = ["deleted_at IS NULL"]
    params = []

    status_list = filters.get('status_list') or []
    if not status_list and filters.get('status'):
        raw = filters['status']
        if isinstance(raw, list):
            status_list = raw
        elif isinstance(raw, str) and ',' in raw:
            status_list = [s.strip() for s in raw.split(',') if s.strip()]
        elif raw:
            status_list = [raw]

    if filters.get('record_status'):
        conditions.append("record_status = ?")
        params.append(filters['record_status'])
    if status_list:
        if len(status_list) == 1:
            conditions.append("status = ?")
            params.append(status_list[0])
        else:
            placeholders = ','.join(['?'] * len(status_list))
            conditions.append(f"status IN ({placeholders})")
            params.extend(status_list)
    if filters.get('province'):
        conditions.append("province = ?")
        params.append(filters['province'])
    if filters.get('gender'):
        conditions.append("gender = ?")
        params.append(filters['gender'])
    if filters.get('arrest_authority'):
        matching_keywords = None
        for canonical, keywords in AUTHORITY_GROUPS.items():
            if filters['arrest_authority'] == canonical:
                matching_keywords = keywords
                break
            for kw in keywords:
                if kw in filters['arrest_authority']:
                    matching_keywords = keywords
                    break
            if matching_keywords:
                break
        if matching_keywords:
            or_clauses = ' OR '.join(['arrest_authority LIKE ?' for _ in matching_keywords])
            conditions.append(f"({or_clauses})")
            params.extend([f"%{kw}%" for kw in matching_keywords])
        else:
            conditions.append("arrest_authority LIKE ?")
            params.append(f"%{filters['arrest_authority']}%")
    if filters.get('arrest_place'):
        conditions.append("arrest_place LIKE ?")
        params.append(f"%{filters['arrest_place']}%")
    if filters.get('arrest_year_from') and safe_int(filters['arrest_year_from']) is not None:
        conditions.append("arrest_year >= ?")
        params.append(safe_int(filters['arrest_year_from']))
    if filters.get('arrest_year_to') and safe_int(filters['arrest_year_to']) is not None:
        conditions.append("arrest_year <= ?")
        params.append(safe_int(filters['arrest_year_to']))
    if filters.get('birth_year_from') and safe_int(filters['birth_year_from']) is not None:
        conditions.append("birth_year >= ?")
        params.append(safe_int(filters['birth_year_from']))
    if filters.get('birth_year_to') and safe_int(filters['birth_year_to']) is not None:
        conditions.append("birth_year <= ?")
        params.append(safe_int(filters['birth_year_to']))
    if filters.get('marital'):
        conditions.append("marital = ?")
        params.append(filters['marital'])
    if filters.get('education'):
        conditions.append("education = ?")
        params.append(filters['education'])
    if filters.get('education_max'):
        edu_order = ['أمّي', 'ابتدائية', 'إعدادية', 'ثانوية', 'معهد', 'بكالوريوس', 'ماجستير', 'دكتوراه']
        try:
            max_idx = edu_order.index(filters['education_max'])
            included = edu_order[:max_idx + 1]
            placeholders = ','.join(['?'] * len(included))
            conditions.append(f"education IN ({placeholders})")
            params.extend(included)
        except ValueError:
            pass
    if filters.get('housing_type'):
        conditions.append("housing_type = ?")
        params.append(filters['housing_type'])
    if filters.get('blood_type'):
        conditions.append("blood_type = ?")
        params.append(filters['blood_type'])
    if filters.get('has_kids') == 'yes':
        conditions.append("has_kids = 'yes'")
    elif filters.get('has_kids') == 'no':
        conditions.append("(has_kids = 'no' OR has_kids IS NULL OR has_kids = '')")
    minor_threshold = safe_int(filters.get('minor_age_threshold'), 18)
    if filters.get('has_kids_under_18') == 'yes':
        if minor_threshold == 18:
            conditions.append("kids_under_18_count > 0")
        else:
            conditions.append("(children_data IS NOT NULL AND children_data != '' AND children_data != '[]')")
    elif filters.get('has_kids_under_18') == 'no':
        if minor_threshold == 18:
            conditions.append("(kids_under_18_count = 0 OR kids_under_18_count IS NULL)")
    if filters.get('kids_max_age'):
        conditions.append("(children_data IS NOT NULL AND children_data != '' AND children_data != '[]')")
    if filters.get('has_photo') == 'yes':
        conditions.append("photo_path IS NOT NULL AND photo_path != ''")
    elif filters.get('has_photo') == 'no':
        conditions.append("(photo_path IS NULL OR photo_path = '')")
    if filters.get('has_document') == 'yes':
        conditions.append("document_path IS NOT NULL AND document_path != ''")
    elif filters.get('has_document') == 'no':
        conditions.append("(document_path IS NULL OR document_path = '')")
    if filters.get('case_type'):
        conditions.append("case_type = ?")
        params.append(filters['case_type'])
    if filters.get('evidence_level'):
        conditions.append("evidence_level = ?")
        params.append(filters['evidence_level'])
    if filters.get('verification_status'):
        conditions.append("verification_status = ?")
        params.append(filters['verification_status'])
    if filters.get('civil_registry_status'):
        conditions.append("civil_registry_status = ?")
        params.append(filters['civil_registry_status'])
    if filters.get('digital_evidence_type'):
        conditions.append("digital_evidence_type = ?")
        params.append(filters['digital_evidence_type'])
    if filters.get('has_conflicting_info') == '1':
        conditions.append("has_conflicting_info = 1")
    if filters.get('has_special_needs') == '1':
        conditions.append("has_special_needs = 1")
    if filters.get('chronic') == 'yes':
        conditions.append("(chronic = 'نعم' OR has_hypertension = 1 OR has_diabetes = 1 OR (other_diseases IS NOT NULL AND other_diseases != ''))")
    if filters.get('breadwinner'):
        conditions.append("breadwinner LIKE ?")
        params.append(f"%{filters['breadwinner']}%")
    if filters.get('has_hypertension') == '1':
        conditions.append("has_hypertension = 1")
    if filters.get('has_diabetes') == '1':
        conditions.append("has_diabetes = 1")
    if filters.get('is_registered') == '1':
        conditions.append("is_officially_registered = 1")
    elif filters.get('is_registered') == '0':
        conditions.append("(is_officially_registered = 0 OR is_officially_registered IS NULL)")
    if filters.get('has_legal') == 'yes':
        conditions.append("legal = 'نعم'")
    if filters.get('has_assoc') == 'yes':
        conditions.append("assoc = 'yes'")
    elif filters.get('has_assoc') == 'no':
        conditions.append("(assoc != 'yes' OR assoc IS NULL OR assoc = '')")
    if filters.get('reporter_relation'):
        conditions.append("reporter_relation = ?")
        params.append(filters['reporter_relation'])
    if filters.get('widows_filter') == 'widows_deceased':
        conditions.append("status IN ('deceased') AND gender = 'male' AND marital = 'married'")
    elif filters.get('widows_filter') == 'widows_enforced':
        conditions.append("status = 'enforced' AND gender = 'male' AND marital = 'married'")
    elif filters.get('widows_filter') == 'widows_all':
        conditions.append("status IN ('deceased', 'enforced') AND gender = 'male' AND marital = 'married'")
    elif filters.get('widows_filter') == 'widows_with_minors':
        conditions.append("status IN ('deceased', 'enforced') AND gender = 'male' AND marital = 'married' AND kids_under_18_count > 0")
    if filters.get('spouse_search'):
        conditions.append("spouse_name LIKE ?")
        params.append(f"%{filters['spouse_search']}%")
    if filters.get('child_name_search'):
        conditions.append("children_data LIKE ?")
        params.append(f"%{filters['child_name_search']}%")
    if filters.get('child_education'):
        conditions.append("children_data LIKE ?")
        params.append(f"%{filters['child_education']}%")
    if filters.get('employment'):
        conditions.append("employment LIKE ?")
        params.append(f"%{filters['employment']}%")
    if filters.get('profession'):
        conditions.append("profession LIKE ?")
        params.append(f"%{filters['profession']}%")
    if filters.get('address_search'):
        conditions.append("address LIKE ?")
        params.append(f"%{filters['address_search']}%")
    if filters.get('arrest_reason'):
        conditions.append("arrest_reason LIKE ?")
        params.append(f"%{filters['arrest_reason']}%")
    if filters.get('death_year_from') and safe_int(filters['death_year_from']) is not None:
        conditions.append("death_year >= ?")
        params.append(safe_int(filters['death_year_from']))
    if filters.get('death_year_to') and safe_int(filters['death_year_to']) is not None:
        conditions.append("death_year <= ?")
        params.append(safe_int(filters['death_year_to']))
    if filters.get('release_year_from') and safe_int(filters['release_year_from']) is not None:
        conditions.append("release_year >= ?")
        params.append(safe_int(filters['release_year_from']))
    if filters.get('release_year_to') and safe_int(filters['release_year_to']) is not None:
        conditions.append("release_year <= ?")
        params.append(safe_int(filters['release_year_to']))
    if filters.get('notes_search'):
        conditions.append("(notes LIKE ? OR methodology_notes LIKE ?)")
        params.extend([f"%{filters['notes_search']}%"] * 2)
    if filters.get('employer'):
        conditions.append("employer LIKE ?")
        params.append(f"%{filters['employer']}%")
    if filters.get('breadwinner_relation'):
        conditions.append("breadwinner_relation = ?")
        params.append(filters['breadwinner_relation'])
    if filters.get('age_from') and safe_int(filters['age_from']) is not None:
        current_year = datetime.now().year
        max_birth_year = current_year - safe_int(filters['age_from'])
        conditions.append("birth_year <= ? AND birth_year > 0")
        params.append(max_birth_year)
    if filters.get('age_to') and safe_int(filters['age_to']) is not None:
        current_year = datetime.now().year
        min_birth_year = current_year - safe_int(filters['age_to'])
        conditions.append("birth_year >= ?")
        params.append(min_birth_year)
    if filters.get('has_guardian') == 'yes':
        conditions.append("guardian_name IS NOT NULL AND guardian_name != ''")
    elif filters.get('has_guardian') == 'no':
        conditions.append("(guardian_name IS NULL OR guardian_name = '')")
    if filters.get('digital_evidence_url_status'):
        conditions.append("digital_evidence_url_status = ?")
        params.append(filters['digital_evidence_url_status'])
    if filters.get('collector_name'):
        conditions.append("collector_name = ?")
        params.append(filters['collector_name'])
    if filters.get('created_from'):
        conditions.append("created_at >= ?")
        params.append(filters['created_from'])
    if filters.get('created_to'):
        conditions.append("created_at <= ?")
        params.append(filters['created_to'] + ' 23:59:59')
    if filters.get('collection_date_from'):
        conditions.append("collection_date >= ?")
        params.append(filters['collection_date_from'])
    if filters.get('collection_date_to'):
        conditions.append("collection_date <= ?")
        params.append(filters['collection_date_to'])
    if filters.get('source_type'):
        conditions.append("source_type = ?")
        params.append(filters['source_type'])
    if filters.get('has_phone') == 'yes':
        conditions.append("(phone IS NOT NULL AND phone != '')")
    elif filters.get('has_phone') == 'no':
        conditions.append("(phone IS NULL OR phone = '')")
    if filters.get('family_book_number'):
        conditions.append("family_book_number LIKE ?")
        params.append(f"%{filters['family_book_number']}%")
    if filters.get('national_id_search'):
        conditions.append("national_id LIKE ?")
        params.append(f"%{filters['national_id_search']}%")
    if filters.get('has_rent') == 'yes':
        conditions.append("rent_amount IS NOT NULL AND rent_amount != '' AND rent_amount != '0'")
    elif filters.get('has_rent') == 'no':
        conditions.append("(rent_amount IS NULL OR rent_amount = '' OR rent_amount = '0')")
    if filters.get('detention_facility_search'):
        conditions.append("detention_facilities_data LIKE ?")
        params.append(f"%{filters['detention_facility_search']}%")
    # Service filters (subqueries on record_services)
    svc_mode = filters.get('service_filter_mode', '') or 'received'
    if svc_mode == 'not_received' and filters.get('service_name'):
        conditions.append(
            "NOT EXISTS (SELECT 1 FROM record_services rs WHERE rs.record_id = records.id AND rs.service_name = ?)"
        )
        params.append(filters['service_name'])
    elif filters.get('service_name') and filters.get('service_count_min'):
        conditions.append(
            "(SELECT COUNT(*) FROM record_services rs WHERE rs.record_id = records.id AND rs.service_name = ?) >= ?"
        )
        params.append(filters['service_name'])
        params.append(safe_int(filters['service_count_min'], 1))
    elif filters.get('service_name'):
        conditions.append(
            "EXISTS (SELECT 1 FROM record_services rs WHERE rs.record_id = records.id AND rs.service_name = ?)"
        )
        params.append(filters['service_name'])
    elif filters.get('service_count_min'):
        conditions.append(
            "(SELECT COUNT(*) FROM record_services rs WHERE rs.record_id = records.id) >= ?"
        )
        params.append(safe_int(filters['service_count_min'], 1))
    if filters.get('service_provider'):
        conditions.append(
            "EXISTS (SELECT 1 FROM record_services rs WHERE rs.record_id = records.id AND rs.provider = ?)"
        )
        params.append(filters['service_provider'])
    if filters.get('last_service_from'):
        conditions.append(
            "EXISTS (SELECT 1 FROM record_services rs WHERE rs.record_id = records.id AND rs.service_date >= ?)"
        )
        params.append(filters['last_service_from'])
    if filters.get('last_service_to'):
        conditions.append(
            "(SELECT MAX(rs.service_date) FROM record_services rs WHERE rs.record_id = records.id) <= ?"
        )
        params.append(filters['last_service_to'])
    if filters.get('search'):
        search_term = f"%{filters['search']}%"
        conditions.append("""(
            first_name LIKE ? OR father_name LIKE ? OR last_name LIKE ?
            OR mother_name LIKE ? OR national_id LIKE ? OR phone LIKE ?
            OR address LIKE ? OR notes LIKE ? OR reporter_name LIKE ?
            OR (COALESCE(first_name,'') || ' ' || COALESCE(father_name,'') || ' ' || COALESCE(last_name,'')) LIKE ?
        )""")
        params.extend([search_term] * 10)

    return conditions, params


@app.route('/admin/records')
@admin_required
def admin_records():
    db = get_db()
    page = safe_int(request.args.get('page'), 1)
    per_page = safe_int(request.args.get('per_page'), 25)

    # Build filter query using shared helper
    filters = _filters_from_request_args(request.args)
    status_list = filters['status_list']
    conditions, params = _build_record_filter_conditions(filters)

    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    # For kids age filtering, we need post-filter since children_data is JSON
    kids_age_from = safe_int(filters.get('kids_age_from'))
    kids_age_to = safe_int(filters.get('kids_age_to'))
    kids_max_age = safe_int(filters.get('kids_max_age'))
    needs_kids_age_filter = kids_age_from is not None or kids_age_to is not None or kids_max_age is not None
    # Custom minor age threshold also needs post-filter
    needs_minor_threshold_filter = filters['has_kids_under_18'] in ('yes', 'no') and minor_threshold != 18

    if needs_kids_age_filter:
        # Must ensure records have children
        if "has_kids = 'yes'" not in ' '.join(conditions):
            conditions_with_kids = conditions + ["(children_data IS NOT NULL AND children_data != '' AND children_data != '[]')"]
            where = " WHERE " + " AND ".join(conditions_with_kids)

    # Sort
    sort_by = request.args.get('sort', 'id')
    sort_dir = request.args.get('dir', 'desc')
    allowed_sorts = ['id', 'first_name', 'last_name', 'status', 'province', 'arrest_year', 'created_at']
    if sort_by not in allowed_sorts:
        sort_by = 'id'
    if sort_dir not in ('asc', 'desc'):
        sort_dir = 'desc'

    sort_by_need = filters['sort_by_need'] == '1'
    needs_post_filter = needs_kids_age_filter or needs_minor_threshold_filter or sort_by_need
    if needs_post_filter:
        # Fetch all matching records, then filter by children age, then paginate
        all_records = db.execute(
            f"SELECT * FROM records{where} ORDER BY {sort_by} {sort_dir}", params
        ).fetchall()
        if kids_age_from is not None or kids_age_to is not None:
            all_records = [r for r in all_records if record_has_child_in_age_range(r, kids_age_from, kids_age_to)]
        if kids_max_age is not None:
            all_records = [r for r in all_records if record_has_child_in_age_range(r, 0, kids_max_age)]
        if needs_minor_threshold_filter:
            if filters['has_kids_under_18'] == 'yes':
                all_records = [r for r in all_records if record_has_child_in_age_range(r, 0, minor_threshold - 1)]
            elif filters['has_kids_under_18'] == 'no':
                all_records = [r for r in all_records if not record_has_child_in_age_range(r, 0, minor_threshold - 1)]
        if sort_by_need:
            all_records = sorted(all_records, key=lambda r: compute_need_score(r), reverse=True)
        count = len(all_records)
        offset = (page - 1) * per_page
        records = all_records[offset:offset + per_page]
    else:
        count = db.execute(f"SELECT COUNT(*) FROM records{where}", params).fetchone()[0]
        offset = (page - 1) * per_page
        records = db.execute(
            f"SELECT * FROM records{where} ORDER BY {sort_by} {sort_dir} LIMIT ? OFFSET ?",
            params + [per_page, offset]
        ).fetchall()

    total_pages = (count + per_page - 1) // per_page

    # Build filter_params for URL generation in templates
    filter_params = {k: v for k, v in filters.items() if v and k != 'status_list'}
    # For multi-select status, use first value for URL compat (pagination uses &status=)
    if status_list:
        filter_params['status'] = status_list[0] if len(status_list) == 1 else ','.join(status_list)
    else:
        filter_params.pop('status', None)

    # Fetch active volunteers for collector_name filter dropdown
    volunteer_names = db.execute(
        "SELECT DISTINCT full_name FROM (SELECT full_name FROM volunteers WHERE status='active' UNION SELECT full_name FROM members WHERE status='active') ORDER BY full_name"
    ).fetchall()

    # Fetch distinct service names and providers for filter dropdowns
    service_names = db.execute(
        "SELECT DISTINCT service_name FROM record_services WHERE service_name != '' ORDER BY service_name"
    ).fetchall()
    service_providers = db.execute(
        "SELECT DISTINCT provider FROM record_services WHERE provider != '' ORDER BY provider"
    ).fetchall()

    # Compute need scores if sorting by need
    need_scores = {}
    if sort_by_need:
        need_scores = {r['id']: compute_need_score(r) for r in records}

    from datetime import timedelta
    today = datetime.now().date()
    return render_template('admin_records.html',
        records=records, filters=filters, page=page,
        per_page=per_page, total_pages=total_pages, total_count=count,
        sort_by=sort_by, sort_dir=sort_dir, filter_params=filter_params,
        volunteer_names=[v['full_name'] for v in volunteer_names],
        need_scores=need_scores,
        service_names=[s['service_name'] for s in service_names],
        service_providers=[s['provider'] for s in service_providers],
        today_date=today.isoformat(),
        week_ago_date=(today - timedelta(days=7)).isoformat(),
        month_ago_date=(today - timedelta(days=30)).isoformat(),
    )


@app.route('/api/saved_filters')
@admin_required
def api_saved_filters():
    """List saved search filters."""
    db = get_db()
    entity = request.args.get('entity_type', 'records')
    filters = db.execute(
        "SELECT id, name, filter_data, created_at FROM saved_filters WHERE entity_type=? ORDER BY name",
        (entity,)
    ).fetchall()
    return jsonify([{'id': f['id'], 'name': f['name'], 'filter_data': json.loads(f['filter_data']), 'created_at': f['created_at']} for f in filters])


@app.route('/api/saved_filters', methods=['POST'])
@admin_required
def api_save_filter():
    """Save current search filters."""
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'الاسم مطلوب'}), 400
    filter_data = data.get('filter_data', {})
    entity_type = data.get('entity_type', 'records')
    db = get_db()
    db.execute(
        "INSERT INTO saved_filters (name, filter_data, entity_type) VALUES (?, ?, ?)",
        (name, json.dumps(filter_data, ensure_ascii=False), entity_type)
    )
    db.commit()
    return jsonify({'success': True})


@app.route('/api/saved_filters/<int:filter_id>', methods=['DELETE'])
@admin_required
def api_delete_filter(filter_id):
    """Delete a saved filter."""
    db = get_db()
    db.execute("DELETE FROM saved_filters WHERE id = ?", (filter_id,))
    db.commit()
    return jsonify({'success': True})


@app.route('/api/records')
@admin_required
def api_records():
    """AJAX endpoint for filtering records without full page reload."""
    db = get_db()
    page = safe_int(request.args.get('page'), 1)
    per_page = safe_int(request.args.get('per_page'), 25)

    # Build filters dict from request args (reuse shared logic)
    filters = _filters_from_request_args(request.args)
    conditions, params = _build_record_filter_conditions(filters)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    # Sort
    sort_by = request.args.get('sort', 'id')
    sort_dir = request.args.get('dir', 'desc')
    allowed_sorts = ['id', 'first_name', 'last_name', 'status', 'province', 'arrest_year', 'created_at']
    if sort_by not in allowed_sorts:
        sort_by = 'id'
    if sort_dir not in ('asc', 'desc'):
        sort_dir = 'desc'

    count = db.execute(f"SELECT COUNT(*) FROM records{where}", params).fetchone()[0]
    offset = (page - 1) * per_page
    records = db.execute(
        f"SELECT id, first_name, father_name, last_name, status, province, arrest_year, "
        f"arrest_authority, phone, spouse_phone, guardian_phone, reporter_phone, spouse_name, "
        f"marital, gender, kids_under_18_count, record_status "
        f"FROM records{where} ORDER BY {sort_by} {sort_dir} LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()

    total_pages = (count + per_page - 1) // per_page

    rows = []
    for r in records:
        phone = r['phone'] or r['spouse_phone'] or r['guardian_phone'] or r['reporter_phone'] or ''
        phone_source = ''
        if phone and not r['phone']:
            if r['spouse_phone'] == phone:
                phone_source = 'زوج/ة'
            elif r['guardian_phone'] == phone:
                phone_source = 'ولي أمر'
            else:
                phone_source = 'مبلغ'
        rows.append({
            'id': r['id'],
            'first_name': r['first_name'] or '',
            'father_name': r['father_name'] or '',
            'last_name': r['last_name'] or '',
            'status': r['status'] or '',
            'province': r['province'] or '',
            'arrest_year': r['arrest_year'] if r['arrest_year'] else '',
            'arrest_authority': r['arrest_authority'] or '',
            'phone': phone,
            'phone_source': phone_source,
            'spouse_name': r['spouse_name'] or '',
            'is_widow': bool(r['spouse_name'] and r['marital'] == 'married' and r['gender'] == 'male' and r['status'] in ('deceased', 'enforced')),
            'widow_type': 'أرملة' if r['status'] == 'deceased' else 'زوجة مغيّب' if r['status'] == 'enforced' else '',
            'kids_under_18': r['kids_under_18_count'] if r['kids_under_18_count'] else '',
            'record_status': r['record_status'] or 'draft',
        })

    return jsonify({
        'records': rows,
        'total_count': count,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
    })


@app.route('/admin/record/<int:record_id>')
@admin_required
def admin_record_detail(record_id):
    db = get_db()
    record = db.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
    if not record:
        flash('السجل غير موجود', 'error')
        return redirect(url_for('admin_records'))
    # Fetch linked records
    links = db.execute("""
        SELECT rl.*,
            CASE WHEN rl.record_id_a = ? THEN rl.record_id_b ELSE rl.record_id_a END as linked_id
        FROM record_links rl
        WHERE rl.record_id_a = ? OR rl.record_id_b = ?
        ORDER BY rl.created_at DESC
    """, (record_id, record_id, record_id)).fetchall()
    linked_records = []
    for link in links:
        lr = db.execute("SELECT id, first_name, father_name, last_name, status, province FROM records WHERE id = ?",
                        (link['linked_id'],)).fetchone()
        if lr:
            linked_records.append({
                'link_id': link['id'],
                'record': lr,
                'link_type': link['link_type'],
                'notes': link['notes'],
            })
    # Fetch change history (last 20)
    changes = db.execute(
        "SELECT * FROM record_changes WHERE record_id = ? ORDER BY changed_at DESC LIMIT 20",
        (record_id,)
    ).fetchall()
    services = db.execute(
        "SELECT * FROM record_services WHERE record_id=? ORDER BY created_at DESC", (record_id,)
    ).fetchall()
    companions = db.execute(
        "SELECT * FROM record_companions WHERE record_id=? ORDER BY created_at DESC", (record_id,)
    ).fetchall()
    # Fetch linked record info for companions that have been linked
    companions_with_links = []
    for comp in companions:
        comp_data = dict(comp)
        if comp['linked_record_id']:
            lr = db.execute("SELECT id, first_name, father_name, last_name, status, province FROM records WHERE id=?",
                            (comp['linked_record_id'],)).fetchone()
            comp_data['linked_record'] = lr
        else:
            comp_data['linked_record'] = None
        companions_with_links.append(comp_data)
    record_documents = db.execute(
        "SELECT * FROM record_documents WHERE record_id=? ORDER BY uploaded_at DESC", (record_id,)
    ).fetchall()
    return_to = request.args.get('return_to', '')
    return render_template('admin_record_detail.html', record=record, services=services,
                           linked_records=linked_records, changes=changes,
                           companions=companions_with_links, return_to=return_to,
                           record_documents=record_documents)


@app.route('/admin/record/<int:record_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_record_edit(record_id):
    db = get_db()
    record = db.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
    if not record:
        flash('السجل غير موجود', 'error')
        return redirect(url_for('admin_records'))

    # Berkeley Protocol: Prevent editing locked records
    if (record['record_status'] or 'draft') == 'locked':
        user_role = session.get('user_role', 'admin')
        if user_role != 'admin':
            flash('هذا السجل مقفل ولا يمكن تعديله. يجب فتحه أولاً بواسطة المدير.', 'error')
            return redirect(url_for('admin_record_detail', record_id=record_id))
        flash('تحذير: هذا السجل مقفل. التعديلات ستُسجَّل في سجل التغييرات.', 'warning')

    if request.method == 'POST':
        form = request.form

        # Handle file uploads - keep old if no new file
        photo_path = record['photo_path'] or ''
        photo_hash = record['photo_hash'] or ''
        doc_path = record['document_path'] or ''
        doc_hash = record['document_hash'] or ''
        screenshot_path = record['digital_evidence_screenshot_path'] or ''
        civil_doc_path = record['civil_registry_document_path'] or ''
        cv_path = record['survivor_cv_path'] or ''
        cv_photo_path = record['survivor_cv_photo_path'] or ''

        # Allow URL-based photo/document paths (for old DB records with URLs)
        photo_url = form.get('photo_url', '').strip()
        doc_url = form.get('document_url', '').strip()
        if photo_url:
            photo_path = photo_url
            photo_hash = ''
        if doc_url:
            doc_path = doc_url
            doc_hash = ''

        if 'photo' in request.files and request.files['photo'].filename:
            new_photo, new_hash = save_upload(request.files['photo'], 'photos')
            if new_photo:
                photo_path, photo_hash = new_photo, new_hash

        if 'document' in request.files and request.files['document'].filename:
            new_doc, new_hash = save_upload(request.files['document'], 'documents')
            if new_doc:
                doc_path, doc_hash = new_doc, new_hash

        if 'digital_evidence_screenshot' in request.files and request.files['digital_evidence_screenshot'].filename:
            new_ss, _ = save_upload(request.files['digital_evidence_screenshot'], 'screenshots')
            if new_ss:
                screenshot_path = new_ss

        if 'civil_registry_document' in request.files and request.files['civil_registry_document'].filename:
            new_cd, _ = save_upload(request.files['civil_registry_document'], 'documents')
            if new_cd:
                civil_doc_path = new_cd

        if 'survivor_cv' in request.files and request.files['survivor_cv'].filename:
            new_cv, _ = save_upload(request.files['survivor_cv'], 'documents')
            if new_cv:
                cv_path = new_cv

        if 'survivor_cv_photo' in request.files and request.files['survivor_cv_photo'].filename:
            new_cvp, _ = save_upload(request.files['survivor_cv_photo'], 'photos')
            if new_cvp:
                cv_photo_path = new_cvp

        # Process chronic diseases checkboxes
        chronic_list = form.getlist('chronic_list')
        chronic_value = '، '.join(chronic_list) if chronic_list else form.get('chronic', '')
        edit_has_hypertension = 1 if 'ضغط الدم' in chronic_list else int(form.get('has_hypertension', 0) or 0)
        edit_has_diabetes = 1 if 'السكري' in chronic_list else int(form.get('has_diabetes', 0) or 0)

        db.execute("""UPDATE records SET
            first_name=?, father_name=?, last_name=?, gender=?, mother_name=?,
            birth_day=?, birth_month=?, birth_year=?, province=?, national_id=?,
            family_book_number=?,
            phone=?, blood_type=?, photo_path=?, document_path=?,
            arrest_day=?, arrest_month=?, arrest_year=?, arrest_place=?,
            arrest_authority=?, arrest_reason=?, arrest_causer=?,
            status=?, release_day=?, release_month=?, release_year=?,
            death_day=?, death_month=?, death_year=?, death_place=?,
            marital=?, guardian_name=?, guardian_relation=?, guardian_phone=?,
            spouse_name=?, spouse_phone=?, has_kids=?, kids_count=?, children_data=?,
            ex_spouse_name=?, has_kids_w=?, kids_count_w=?, children_data_w=?,
            address=?, housing_type=?, rent_amount=?,
            employment=?, profession=?, employer=?, breadwinner=?,
            breadwinner_job=?, breadwinner_relation=?, breadwinner_relation_other=?,
            chronic=?, diseases=?, has_hypertension=?, has_diabetes=?, other_diseases=?,
            has_special_needs=?, special_needs_details=?,
            education=?, edu_type=?, edu_specialization=?, edu_university=?,
            kids_under_18_count=?, is_officially_registered=?,
            legal=?, legal_details=?, assoc=?, assoc_name=?, service_type=?,
            notes=?,
            case_type=?, reporter_name=?, reporter_relation=?, reporter_phone=?, reporter_id=?,
            informant_consent=?, witnesses_data=?,
            digital_evidence_type=?, digital_evidence_url=?, digital_evidence_url_status=?,
            digital_evidence_screenshot_path=?, digital_evidence_date=?,
            digital_evidence_description=?, digital_evidence_person_name=?,
            digital_evidence_death_date=?,
            civil_registry_status=?, civil_registry_date=?, civil_registry_document_path=?,
            has_conflicting_info=?, conflicting_info_details=?,
            evidence_level=?, evidence_sources_count=?,
            last_known_alive_date=?, last_known_location=?,
            detention_facilities_data=?,
            source_type=?, source_url=?, collection_date=?, collector_name=?,
            verification_status=?, methodology_notes=?, methodology_type=?,
            photo_hash=?, document_hash=?,
            survivor_cv_path=?, survivor_cv_text=?, survivor_cv_photo_path=?,
            address_area=?
        WHERE id=?""", (
            form.get('first_name', ''), form.get('father_name', ''), form.get('last_name', ''),
            form.get('gender', ''), form.get('mother_name', ''),
            int(form.get('birth_day', 0) or 0), int(form.get('birth_month', 0) or 0),
            int(form.get('birth_year', 0) or 0),
            form.get('province', ''), form.get('national_id', ''),
            form.get('family_book_number', ''),
            form.get('phone', ''), form.get('blood_type', ''),
            photo_path, doc_path,
            int(form.get('arrest_day', 0) or 0), int(form.get('arrest_month', 0) or 0),
            int(form.get('arrest_year', 0) or 0), form.get('arrest_place', ''),
            form.get('arrest_authority', ''), form.get('arrest_reason', ''),
            form.get('arrest_causer', ''),
            form.get('status', ''), int(form.get('release_day', 0) or 0),
            int(form.get('release_month', 0) or 0), int(form.get('release_year', 0) or 0),
            int(form.get('death_day', 0) or 0), int(form.get('death_month', 0) or 0),
            int(form.get('death_year', 0) or 0), form.get('death_place', ''),
            form.get('marital', ''), form.get('guardian_name', ''),
            form.get('guardian_relation', ''), form.get('guardian_phone', ''),
            form.get('spouse_name', ''), form.get('spouse_phone', ''),
            form.get('has_kids', 'no'), int(form.get('kids_count', 0) or 0),
            form.get('children_data', '[]'),
            form.get('ex_spouse_name', ''), form.get('has_kids_w', 'no'),
            int(form.get('kids_count_w', 0) or 0), form.get('children_data_w', '[]'),
            form.get('address', ''), form.get('housing_type', ''),
            form.get('rent_amount', ''),
            form.get('employment', ''), form.get('profession', ''),
            form.get('employer', ''), form.get('breadwinner', ''),
            form.get('breadwinner_job', ''), form.get('breadwinner_relation', ''),
            form.get('breadwinner_relation_other', ''),
            chronic_value, form.get('diseases', ''),
            edit_has_hypertension,
            edit_has_diabetes, form.get('other_diseases', ''),
            int(form.get('has_special_needs', 0) or 0),
            form.get('special_needs_details', ''),
            form.get('education', ''), form.get('edu_type', ''),
            form.get('edu_specialization', ''), form.get('edu_university', ''),
            int(form.get('kids_under_18_count', 0) or 0),
            int(form.get('is_officially_registered', 0) or 0),
            form.get('legal', ''), form.get('legal_details', ''),
            form.get('assoc', ''), form.get('assoc_name', ''),
            form.get('service_type', ''),
            form.get('notes', ''),
            form.get('case_type', ''), form.get('reporter_name', ''),
            form.get('reporter_relation', ''), form.get('reporter_phone', ''),
            form.get('reporter_id', ''),
            1 if form.get('informant_consent') else 0,
            form.get('witnesses_data', '[]'),
            form.get('digital_evidence_type', ''), form.get('digital_evidence_url', ''),
            form.get('digital_evidence_url_status', ''),
            screenshot_path, form.get('digital_evidence_date', ''),
            form.get('digital_evidence_description', ''),
            form.get('digital_evidence_person_name', ''),
            form.get('digital_evidence_death_date', ''),
            form.get('civil_registry_status', ''), form.get('civil_registry_date', ''),
            civil_doc_path,
            1 if form.get('has_conflicting_info') else 0,
            form.get('conflicting_info_details', ''),
            form.get('evidence_level', 'unverified'),
            int(form.get('evidence_sources_count', 0) or 0),
            form.get('last_known_alive_date', ''), form.get('last_known_location', ''),
            form.get('detention_facilities_data', '[]'),
            form.get('source_type', ''), form.get('source_url', ''), form.get('collection_date', ''),
            form.get('collector_name', ''),
            form.get('verification_status', 'Unverified'),
            form.get('methodology_notes', ''), form.get('methodology_type', ''),
            photo_hash, doc_hash,
            cv_path, form.get('survivor_cv_text', ''), cv_photo_path,
            form.get('address_area', ''),
            record_id
        ))

        # Track field-level changes (Berkeley Protocol: chain of custody)
        new_record = db.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
        ip = request.remote_addr or ''
        changed_by = session.get('username', session.get('display_name', 'admin'))
        skip_fields = {'id', 'created_at', 'updated_at', 'record_slug'}
        changed_fields = []
        for key in record.keys():
            if key in skip_fields:
                continue
            old_val = str(record[key] or '')
            new_val = str(new_record[key] or '')
            if old_val != new_val:
                db.execute(
                    "INSERT INTO record_changes (record_id, field_name, old_value, new_value, changed_by, ip_address) VALUES (?,?,?,?,?,?)",
                    (record_id, key, old_val, new_val, changed_by, ip)
                )
                changed_fields.append(key)

        # Save new additional documents
        doc_count = int(form.get('record_doc_count', 0) or 0)
        for i in range(doc_count):
            file_key = f'record_doc_file_{i}'
            if file_key in request.files and request.files[file_key].filename:
                doc_path, doc_hash = save_upload(request.files[file_key], 'documents')
                if doc_path:
                    db.execute("""INSERT INTO record_documents
                        (record_id, doc_type, file_path, file_hash, original_filename,
                         description, document_date, source_url, uploaded_by)
                        VALUES (?,?,?,?,?,?,?,?,?)""",
                        (record_id, form.get(f'record_doc_type_{i}', 'other'),
                         doc_path, doc_hash or '', request.files[file_key].filename,
                         form.get(f'record_doc_desc_{i}', ''),
                         form.get(f'record_doc_date_{i}', ''),
                         form.get(f'record_doc_url_{i}', ''),
                         changed_by))

        # Delete documents marked for removal
        docs_to_delete = form.getlist('delete_doc_ids')
        for doc_id in docs_to_delete:
            db.execute("DELETE FROM record_documents WHERE id=? AND record_id=?", (doc_id, record_id))

        db.commit()
        log_audit('record_edit', 'record', record_id, {
            'fields_changed': changed_fields,
            'description': f'Edited {len(changed_fields)} fields',
        })
        flash('تم تحديث السجل بنجاح', 'success')
        return_to = request.form.get('return_to', '').strip()
        if return_to and return_to.startswith('/'):
            # Strip any existing fragment then append highlight anchor
            base = return_to.split('#')[0]
            return redirect(base + f'#highlight-{record_id}')
        return redirect(url_for('admin_record_detail', record_id=record_id))

    volunteer_names = db.execute(
        "SELECT DISTINCT full_name FROM (SELECT full_name FROM volunteers WHERE status='active' UNION SELECT full_name FROM members WHERE status='active') ORDER BY full_name"
    ).fetchall()
    services = db.execute(
        "SELECT * FROM record_services WHERE record_id=? ORDER BY created_at DESC", (record_id,)
    ).fetchall()
    record_documents = db.execute(
        "SELECT * FROM record_documents WHERE record_id=? ORDER BY uploaded_at DESC", (record_id,)
    ).fetchall()
    return_to = request.args.get('return_to', '')
    return render_template('admin_record_edit.html', record=record,
                           volunteer_names=[v['full_name'] for v in volunteer_names],
                           services=services, record_documents=record_documents,
                           return_to=return_to)


@app.route('/admin/record/<int:record_id>/history')
@admin_required
def admin_record_history(record_id):
    """Full change history for a record."""
    db = get_db()
    record = db.execute("SELECT id, first_name, father_name, last_name FROM records WHERE id = ?", (record_id,)).fetchone()
    if not record:
        flash('السجل غير موجود', 'error')
        return redirect(url_for('admin_records'))
    field_filter = request.args.get('field', '')
    if field_filter:
        changes = db.execute(
            "SELECT * FROM record_changes WHERE record_id = ? AND field_name = ? ORDER BY changed_at DESC",
            (record_id, field_filter)
        ).fetchall()
    else:
        changes = db.execute(
            "SELECT * FROM record_changes WHERE record_id = ? ORDER BY changed_at DESC LIMIT 500",
            (record_id,)
        ).fetchall()
    # Get distinct field names for the filter dropdown
    fields = db.execute(
        "SELECT DISTINCT field_name FROM record_changes WHERE record_id = ? ORDER BY field_name",
        (record_id,)
    ).fetchall()
    return render_template('admin_record_history.html', record=record, changes=changes,
                           fields=[f['field_name'] for f in fields], field_filter=field_filter)


@app.route('/admin/record/<int:record_id>/link', methods=['POST'])
@admin_required
def admin_record_link(record_id):
    """Create a link between two records."""
    db = get_db()
    linked_id = int(request.form.get('linked_id', 0))
    link_type = request.form.get('link_type', 'related')
    notes = request.form.get('notes', '')
    if not linked_id or linked_id == record_id:
        flash('يرجى اختيار سجل صحيح للربط', 'error')
        return redirect(url_for('admin_record_detail', record_id=record_id))
    # Check if link already exists
    existing = db.execute(
        "SELECT id FROM record_links WHERE (record_id_a=? AND record_id_b=?) OR (record_id_a=? AND record_id_b=?)",
        (record_id, linked_id, linked_id, record_id)
    ).fetchone()
    if existing:
        flash('الربط موجود بالفعل', 'error')
        return redirect(url_for('admin_record_detail', record_id=record_id))
    db.execute(
        "INSERT INTO record_links (record_id_a, record_id_b, link_type, notes) VALUES (?,?,?,?)",
        (record_id, linked_id, link_type, notes)
    )
    db.commit()
    log_audit('record_link', 'record', record_id, f'linked to {linked_id} as {link_type}')
    flash('تم ربط السجلات بنجاح', 'success')
    return redirect(url_for('admin_record_detail', record_id=record_id))


@app.route('/admin/record/<int:record_id>/unlink/<int:link_id>', methods=['POST'])
@admin_required
def admin_record_unlink(record_id, link_id):
    """Remove a link between two records."""
    db = get_db()
    db.execute("DELETE FROM record_links WHERE id = ?", (link_id,))
    db.commit()
    log_audit('record_unlink', 'record', record_id, f'removed link {link_id}')
    flash('تم إزالة الربط', 'success')
    return redirect(url_for('admin_record_detail', record_id=record_id))


@app.route('/admin/record/<int:record_id>/companion/add', methods=['POST'])
@admin_required
def admin_record_add_companion(record_id):
    """Add a companion (person who was with the survivor)."""
    db = get_db()
    first_name = request.form.get('comp_first_name', '').strip()
    father_name = request.form.get('comp_father_name', '').strip()
    last_name = request.form.get('comp_last_name', '').strip()
    mother_name = request.form.get('comp_mother_name', '').strip()
    notes = request.form.get('comp_notes', '').strip()
    if not first_name and not last_name:
        flash('يجب إدخال اسم الشخص', 'error')
        return redirect(url_for('admin_record_detail', record_id=record_id))
    db.execute("""
        INSERT INTO record_companions (record_id, first_name, father_name, last_name, mother_name, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (record_id, first_name, father_name, last_name, mother_name, notes))
    db.commit()
    full_name = ' '.join(filter(None, [first_name, father_name, last_name]))
    log_audit('companion_add', 'record', record_id, full_name)
    flash('تمت إضافة الشخص المرافق بنجاح', 'success')
    return redirect(url_for('admin_record_detail', record_id=record_id))


@app.route('/admin/record/<int:record_id>/companion/<int:comp_id>/delete', methods=['POST'])
@admin_required
def admin_record_delete_companion(record_id, comp_id):
    """Remove a companion."""
    db = get_db()
    db.execute("DELETE FROM record_companions WHERE id = ? AND record_id = ?", (comp_id, record_id))
    db.commit()
    log_audit('companion_delete', 'record', record_id, f'companion {comp_id}')
    flash('تم حذف الشخص المرافق', 'success')
    return redirect(url_for('admin_record_detail', record_id=record_id))


@app.route('/admin/record/<int:record_id>/companion/<int:comp_id>/link', methods=['POST'])
@admin_required
def admin_record_link_companion(record_id, comp_id):
    """Link a companion to an existing record for cross-referencing."""
    db = get_db()
    linked_record_id = int(request.form.get('linked_record_id', 0))
    if linked_record_id:
        db.execute("UPDATE record_companions SET linked_record_id = ? WHERE id = ? AND record_id = ?",
                   (linked_record_id, comp_id, record_id))
        db.commit()
        log_audit('companion_link', 'record', record_id, f'companion {comp_id} -> record {linked_record_id}')
        flash('تم ربط المرافق بسجل موجود', 'success')
    return redirect(url_for('admin_record_detail', record_id=record_id))


def _score_name_match(comp_parts, record):
    """Score how well a companion's name parts match a record. Higher = better match."""
    score = 0
    rec_fields = {
        'first_name': (record['first_name'] or '').strip(),
        'father_name': (record['father_name'] or '').strip(),
        'last_name': (record['last_name'] or '').strip(),
        'mother_name': (record['mother_name'] or '').strip(),
    }
    rec_values = [v.lower() for v in rec_fields.values() if v]

    # Exact field-to-field matches (strongest signal)
    for comp_field, comp_val in comp_parts.items():
        if not comp_val:
            continue
        comp_lower = comp_val.lower()
        rec_val = rec_fields.get(comp_field, '').lower()
        if rec_val and comp_lower == rec_val:
            score += 10  # Exact match in same field
        elif rec_val and comp_lower in rec_val:
            score += 6   # Partial match in same field
        elif rec_val and rec_val in comp_lower:
            score += 5   # Record value contained in companion value

    # Cross-field matches (e.g. companion first_name matches record father_name)
    for comp_field, comp_val in comp_parts.items():
        if not comp_val:
            continue
        comp_lower = comp_val.lower()
        for rec_field, rec_val in rec_fields.items():
            if rec_field == comp_field or not rec_val:
                continue
            if comp_lower == rec_val.lower():
                score += 4  # Exact match in different field
            elif comp_lower in rec_val.lower() or rec_val.lower() in comp_lower:
                score += 2  # Partial cross-field match

    # Bonus: first_name + last_name both match (strong identifier even without father)
    cf = (comp_parts.get('first_name') or '').lower()
    cl = (comp_parts.get('last_name') or '').lower()
    rf = rec_fields['first_name'].lower()
    rl = rec_fields['last_name'].lower()
    if cf and cl and cf == rf and cl == rl:
        score += 8  # Both first+last exact match bonus

    return score


@app.route('/api/companion_cross_ref/<int:record_id>')
@admin_required
def api_companion_cross_ref(record_id):
    """Find existing records that match companion names using deep fuzzy search."""
    db = get_db()
    companions = db.execute(
        "SELECT * FROM record_companions WHERE record_id = ? AND linked_record_id IS NULL",
        (record_id,)
    ).fetchall()
    results = []
    for comp in companions:
        comp_parts = {
            'first_name': (comp['first_name'] or '').strip(),
            'father_name': (comp['father_name'] or '').strip(),
            'last_name': (comp['last_name'] or '').strip(),
            'mother_name': (comp['mother_name'] or '').strip(),
        }
        name_parts = [v for v in comp_parts.values() if v]
        if not name_parts:
            continue

        # Strategy: run multiple queries from precise to broad, collect candidates
        candidates_dict = {}  # id -> row (dedup)

        # Query 1: Records matching 2+ name parts (high precision, fast)
        if len(name_parts) >= 2:
            and_conditions = []
            and_params = []
            for part in name_parts:
                and_conditions.append(
                    "(first_name LIKE ? OR father_name LIKE ? OR last_name LIKE ? OR mother_name LIKE ?)"
                )
                and_params.extend([f'%{part}%'] * 4)
            # At least 2 conditions must match — use pairwise AND combos
            from itertools import combinations
            pair_clauses = []
            pair_params = []
            for combo in combinations(range(len(and_conditions)), min(2, len(and_conditions))):
                pair_clauses.append("(" + " AND ".join(and_conditions[i] for i in combo) + ")")
                for i in combo:
                    pair_params.extend(and_params[i*4:(i+1)*4])
            q1 = (
                "SELECT id, first_name, father_name, last_name, mother_name, status, province "
                "FROM records WHERE deleted_at IS NULL "
                f"AND ({' OR '.join(pair_clauses)}) AND id != ? LIMIT 50"
            )
            pair_params.append(record_id)
            for r in db.execute(q1, pair_params).fetchall():
                candidates_dict[r['id']] = r

        # Query 2: Exact field matches (first_name=X AND last_name=Y, etc.)
        if comp_parts['first_name'] and comp_parts['last_name']:
            for r in db.execute(
                "SELECT id, first_name, father_name, last_name, mother_name, status, province "
                "FROM records WHERE deleted_at IS NULL AND first_name LIKE ? AND last_name LIKE ? AND id != ? LIMIT 10",
                (f"%{comp_parts['first_name']}%", f"%{comp_parts['last_name']}%", record_id)
            ).fetchall():
                candidates_dict[r['id']] = r

        if comp_parts['first_name'] and comp_parts['father_name']:
            for r in db.execute(
                "SELECT id, first_name, father_name, last_name, mother_name, status, province "
                "FROM records WHERE deleted_at IS NULL AND first_name LIKE ? AND father_name LIKE ? AND id != ? LIMIT 10",
                (f"%{comp_parts['first_name']}%", f"%{comp_parts['father_name']}%", record_id)
            ).fetchall():
                candidates_dict[r['id']] = r

        # Query 3: Broad single-part match (only if we have few candidates)
        if len(candidates_dict) < 5:
            or_conditions = []
            or_params = []
            # Use the rarest name part (not first_name which is often common like محمد)
            rare_parts = [p for p in [comp_parts.get('last_name'), comp_parts.get('father_name'), comp_parts.get('mother_name')] if p]
            if not rare_parts:
                rare_parts = name_parts[:1]
            for part in rare_parts:
                or_conditions.append(
                    "(first_name LIKE ? OR father_name LIKE ? OR last_name LIKE ? OR mother_name LIKE ?)"
                )
                or_params.extend([f'%{part}%'] * 4)
            if or_conditions:
                q3 = (
                    "SELECT id, first_name, father_name, last_name, mother_name, status, province "
                    "FROM records WHERE deleted_at IS NULL "
                    f"AND ({' OR '.join(or_conditions)}) AND id != ? LIMIT 20"
                )
                or_params.append(record_id)
                for r in db.execute(q3, or_params).fetchall():
                    candidates_dict[r['id']] = r

        # Score and rank all collected candidates
        scored = []
        for r in candidates_dict.values():
            s = _score_name_match(comp_parts, r)
            if s >= 4:
                scored.append((s, r))
        scored.sort(key=lambda x: -x[0])

        matches = []
        for s, r in scored[:8]:
            name = ' '.join(filter(None, [r['first_name'], r['father_name'], r['last_name']]))
            mother = r['mother_name'] or ''
            matches.append({
                'id': r['id'],
                'name': name,
                'mother_name': mother,
                'status': r['status'],
                'province': r['province'],
                'score': s,
            })
        if matches:
            results.append({
                'companion_id': comp['id'],
                'companion_name': ' '.join(filter(None, [comp_parts['first_name'], comp_parts['father_name'], comp_parts['last_name']])),
                'matches': matches,
            })
    return jsonify(results)


@app.route('/api/search_records_for_link')
@admin_required
def api_search_records_for_link():
    """Search records by name for linking UI — deep search across all name fields."""
    q = request.args.get('q', '').strip()
    exclude_id = safe_int(request.args.get('exclude'), 0)
    if len(q) < 2:
        return jsonify([])
    db = get_db()

    # Split query into individual words for multi-word search
    words = [w.strip() for w in q.split() if w.strip()]

    # Strategy 1: Full query as single term
    full_term = f"%{q}%"
    # Strategy 2: Each word individually
    conditions = [
        "(COALESCE(first_name,'') || ' ' || COALESCE(father_name,'') || ' ' || COALESCE(last_name,'')) LIKE ?"
    ]
    params = [full_term]

    for word in words:
        conditions.append(
            "(first_name LIKE ? OR father_name LIKE ? OR last_name LIKE ? OR mother_name LIKE ?)"
        )
        params.extend([f'%{word}%'] * 4)

    query = (
        "SELECT id, first_name, father_name, last_name, mother_name, status, province "
        "FROM records WHERE deleted_at IS NULL "
        f"AND ({' OR '.join(conditions)}) AND id != ? LIMIT 20"
    )
    params.append(exclude_id)
    records = db.execute(query, params).fetchall()

    # Score results: more matching words = higher rank
    scored = []
    for r in records:
        rec_full = f"{r['first_name'] or ''} {r['father_name'] or ''} {r['last_name'] or ''} {r['mother_name'] or ''}".lower()
        s = sum(1 for w in words if w.lower() in rec_full)
        # Bonus for exact first_name match
        if words and (r['first_name'] or '').lower() == words[0].lower():
            s += 2
        scored.append((s, r))
    scored.sort(key=lambda x: -x[0])

    return jsonify([{
        'id': r['id'],
        'name': f"{r['first_name']} {r['father_name']} {r['last_name']}".strip(),
        'mother_name': r['mother_name'] or '',
        'status': r['status'],
        'province': r['province'],
    } for _, r in scored[:10]])


@app.route('/api/search_unlinked_companions')
@admin_required
def api_search_unlinked_companions():
    """Search all unlinked companions across all records to find cross-references.

    Matches current record's person (or its companions) against unlinked companions
    in OTHER records. This reveals when the same person appears as a companion
    in multiple records, indicating they were detained together.
    """
    record_id = safe_int(request.args.get('record_id'), 0)
    if not record_id:
        return jsonify([])
    db = get_db()

    # Get the main record's details
    record = db.execute(
        "SELECT first_name, father_name, last_name, mother_name FROM records WHERE id = ?",
        (record_id,)
    ).fetchone()
    if not record:
        return jsonify([])

    # Collect all name parts to search: from the record itself + its companions
    search_names = []
    # The record's own name
    rec_parts = {
        'first_name': (record['first_name'] or '').strip(),
        'father_name': (record['father_name'] or '').strip(),
        'last_name': (record['last_name'] or '').strip(),
        'mother_name': (record['mother_name'] or '').strip(),
    }
    if any(rec_parts.values()):
        search_names.append({
            'label': f"{rec_parts['first_name']} {rec_parts['father_name']} {rec_parts['last_name']}".strip(),
            'source': 'record',
            'source_id': record_id,
            'parts': rec_parts,
        })

    # The record's companions
    companions = db.execute(
        "SELECT id, first_name, father_name, last_name, mother_name FROM record_companions WHERE record_id = ?",
        (record_id,)
    ).fetchall()
    for comp in companions:
        c_parts = {
            'first_name': (comp['first_name'] or '').strip(),
            'father_name': (comp['father_name'] or '').strip(),
            'last_name': (comp['last_name'] or '').strip(),
            'mother_name': (comp['mother_name'] or '').strip(),
        }
        if any(c_parts.values()):
            search_names.append({
                'label': ' '.join(filter(None, c_parts.values())),
                'source': 'companion',
                'source_id': comp['id'],
                'parts': c_parts,
            })

    # Get all unlinked companions from OTHER records
    all_unlinked = db.execute(
        """SELECT c.id, c.record_id, c.first_name, c.father_name, c.last_name, c.mother_name, c.notes,
                  r.first_name AS rec_first, r.father_name AS rec_father, r.last_name AS rec_last,
                  r.status AS rec_status, r.province AS rec_province
           FROM record_companions c
           JOIN records r ON c.record_id = r.id AND r.deleted_at IS NULL
           WHERE c.record_id != ? AND c.linked_record_id IS NULL""",
        (record_id,)
    ).fetchall()

    results = []
    for search in search_names:
        matches = []
        for uc in all_unlinked:
            uc_parts = {
                'first_name': (uc['first_name'] or '').strip(),
                'father_name': (uc['father_name'] or '').strip(),
                'last_name': (uc['last_name'] or '').strip(),
                'mother_name': (uc['mother_name'] or '').strip(),
            }
            # Use the scoring function, treating unlinked companion as a "record"
            score = _score_name_match(search['parts'], uc)
            if score >= 4:
                rec_name = f"{uc['rec_first']} {uc['rec_father']} {uc['rec_last']}".strip()
                comp_name = ' '.join(filter(None, [uc['first_name'], uc['father_name'], uc['last_name']]))
                matches.append({
                    'companion_id': uc['id'],
                    'companion_name': comp_name,
                    'mother_name': uc['mother_name'] or '',
                    'notes': uc['notes'] or '',
                    'record_id': uc['record_id'],
                    'record_name': rec_name,
                    'record_status': uc['rec_status'] or '',
                    'record_province': uc['rec_province'] or '',
                    'score': score,
                })
        matches.sort(key=lambda x: -x['score'])
        if matches:
            results.append({
                'search_label': search['label'],
                'search_source': search['source'],
                'matches': matches[:10],
            })

    return jsonify(results)


# Berkeley Protocol: Valid record status transitions (workflow enforcement)
VALID_STATUS_TRANSITIONS = {
    'draft': ['reviewed'],           # data_entry or admin
    'reviewed': ['draft', 'verified'],  # verified: admin only
    'verified': ['reviewed', 'locked'], # admin only
    'locked': ['verified'],             # admin only (unlock requires reason)
}
STATUS_LABELS = {'draft': 'مسودة', 'reviewed': 'مراجَع', 'verified': 'موثّق', 'locked': 'مقفل'}

# Berkeley Protocol: Minimum required fields per record_status level
BERKELEY_REQUIRED_FIELDS = {
    'reviewed': ['first_name', 'father_name', 'last_name', 'status', 'source_type', 'collector_name', 'collection_date'],
    'verified': ['first_name', 'father_name', 'last_name', 'status', 'source_type', 'collector_name', 'collection_date',
                 'evidence_level', 'verification_status'],
    'locked': ['first_name', 'father_name', 'last_name', 'status', 'source_type', 'collector_name', 'collection_date',
               'evidence_level', 'verification_status'],
}

# Berkeley Protocol: Structured methodology types
METHODOLOGY_TYPES = [
    ('interview', 'مقابلة شخصية'),
    ('document_review', 'مراجعة وثائق'),
    ('open_source', 'تحقيق مصادر مفتوحة'),
    ('field_visit', 'زيارة ميدانية'),
    ('remote_interview', 'مقابلة عن بعد'),
    ('database_cross_ref', 'تقاطع قواعد بيانات'),
    ('witness_testimony', 'شهادة شاهد'),
    ('other', 'أخرى'),
]

# Field tooltips: descriptions and examples for every field (shown as ? buttons)
FIELD_TOOLTIPS = {
    # --- المُبلِّغ ---
    'status': 'تصنيف حالة الشخص الموثَّق.\nناجٍ: شخص أُفرج عنه أو هرب\nمغيّب قسراً: لا يُعرف مصيره بعد الاعتقال\nمتوفى: مؤكد الوفاة',
    'case_type': 'تصنيف فرعي أكثر تفصيلاً. يتغير حسب تصنيف الحالة المختار.\nمثال: ناجٍ - لديه وثائق، اختفاء قسري - لا معلومات بعد الاعتقال',
    'reporter_name': 'اسم الشخص الذي يقدم المعلومات (المُبلِّغ). قد يكون أحد أفراد العائلة أو شاهد عيان.\nمثال: أحمد محمد العلي',
    'reporter_relation': 'علاقة المُبلِّغ بالضحية.\nمثال: أخ، أم، زوجة، جار، صديق، محامي، مصدر مجهول',
    'reporter_phone': 'رقم هاتف المُبلِّغ للتواصل لاحقاً.\nمثال: 0912345678',
    'reporter_id': 'الرقم الوطني للمُبلِّغ لتوثيق هويته.\nمثال: 01234567890',
    'collector_name': 'اسم الموظف أو المتطوع الذي جمع هذه البيانات ميدانياً. مهم لبروتوكول بيركلي (سلسلة الحفظ).\nمثال: سارة أحمد',
    'collection_date': 'التاريخ الذي تم فيه جمع هذه المعلومات فعلياً (ليس تاريخ الإدخال في النظام).\nمثال: 2024-03-15',
    'informant_consent': 'هل وافق المُبلِّغ على جمع واستخدام هذه المعلومات لأغراض التوثيق؟ مطلوب وفق بروتوكول بيركلي.',
    # --- البيانات الشخصية ---
    'first_name': 'الاسم الأول للشخص الموثَّق.\nمثال: محمد',
    'father_name': 'اسم والد الشخص الموثَّق. يساعد في التمييز بين الأشخاص الذين يحملون نفس الاسم.\nمثال: أحمد',
    'last_name': 'اسم العائلة (الكنية).\nمثال: الحسين',
    'mother_name': 'اسم الأم الكامل. يساعد في التحقق من الهوية.\nمثال: فاطمة علي الخالد',
    'gender': 'جنس الشخص الموثَّق.\nذكر أو أنثى',
    'birth_day': 'يوم الميلاد (1-31). اتركه فارغاً إذا غير معروف.',
    'birth_month': 'شهر الميلاد (1-12). اتركه فارغاً إذا غير معروف.',
    'birth_year': 'سنة الميلاد. مهم لتحديد العمر.\nمثال: 1990',
    'blood_type': 'فصيلة الدم إن كانت معروفة.\nمثال: A+, B-, O+, AB+',
    'national_id': 'رقم الهوية الوطنية أو جواز السفر.\nمثال: 01234567890',
    'phone': 'رقم هاتف الشخص الموثَّق (للناجين فقط).\nمثال: 0912345678',
    'province': 'المحافظة التي ينتمي إليها الشخص أو كان يقيم فيها.',
    'address': 'العنوان التفصيلي: الحي، الشارع، أقرب معلم.\nمثال: حي الميدان - شارع النصر - بجانب المسجد الكبير',
    'address_area': 'المنطقة أو الناحية ضمن المحافظة.\nمثال: ريف دمشق الشرقي',
    'housing_type': 'نوع السكن الحالي.\nملك: يملك المسكن\nإيجار: مستأجر\nنزوح: نازح في مسكن مؤقت\nإيواء: في مركز إيواء',
    'rent_amount': 'مبلغ الإيجار الشهري بالليرة (إن كان مستأجراً).\nمثال: 500000',
    'photo': 'صورة شخصية للشخص الموثَّق. تساعد في التعرف والمطابقة.\nصيغ مقبولة: JPG, PNG\nالحد الأقصى: 15MB',
    'document': 'وثيقة رسمية (هوية، جواز سفر، شهادة).\nصيغ مقبولة: JPG, PNG, PDF\nالحد الأقصى: 15MB',
    # --- الاعتقال ---
    'arrest_day': 'يوم الاعتقال. اتركه فارغاً إذا غير معروف بدقة.',
    'arrest_month': 'شهر الاعتقال (1-12).',
    'arrest_year': 'سنة الاعتقال.\nمثال: 2012',
    'arrest_place': 'مكان الاعتقال بأكبر قدر من التفصيل.\nمثال: حاجز المزة - دمشق\nمثال: من المنزل - حي برزة',
    'arrest_authority': 'الجهة المسؤولة عن الاعتقال.\nمثال: المخابرات الجوية، الأمن العسكري، الشرطة العسكرية',
    'arrest_reason': 'السبب المعلن أو المفترض للاعتقال.\nمثال: مظاهرات، نشاط سياسي، تخلف عن الخدمة العسكرية',
    'arrest_causer': 'الشخص أو الجهة التي تسببت بالاعتقال (إن عُرف).\nمثال: تقرير من مخبر، حاجز عشوائي',
    # --- الإفراج ---
    'release_day': 'يوم الإفراج. للناجين فقط.',
    'release_month': 'شهر الإفراج (1-12).',
    'release_year': 'سنة الإفراج.\nمثال: 2015',
    # --- الوفاة ---
    'death_day': 'يوم الوفاة إن كان معروفاً.',
    'death_month': 'شهر الوفاة (1-12).',
    'death_year': 'سنة الوفاة.\nمثال: 2013',
    'death_place': 'مكان الوفاة إن كان معروفاً.\nمثال: فرع فلسطين، سجن صيدنايا',
    # --- الأسرة ---
    'marital': 'الحالة الاجتماعية الحالية.\nأعزب، متزوج، أرمل، مطلق',
    'spouse_name': 'اسم الزوج/الزوجة الحالي(ة).\nمثال: فاطمة أحمد',
    'spouse_phone': 'رقم هاتف الزوج/الزوجة.\nمثال: 0912345678',
    'ex_spouse_name': 'اسم الزوج/الزوجة السابق(ة) في حال الطلاق.',
    'has_kids': 'هل لدى الشخص أطفال؟\nنعم أو لا',
    'kids_count': 'عدد الأطفال الإجمالي.',
    'guardian_name': 'اسم الوصي أو ولي الأمر (في حال كان الشخص قاصراً أو عاجزاً).\nمثال: عمه خالد محمد',
    'guardian_relation': 'صلة قرابة الوصي بالشخص.\nمثال: عم، جد، خال',
    'guardian_phone': 'رقم هاتف الوصي.',
    # --- التعليم والعمل ---
    'education': 'أعلى مستوى تعليمي وصل إليه.\nابتدائي، إعدادي، ثانوي، معهد، جامعي، ماجستير، دكتوراه',
    'edu_type': 'نوع التعليم.\nأكاديمي، مهني/صناعي، شرعي، تجاري',
    'edu_specialization': 'التخصص الدراسي.\nمثال: هندسة مدنية، طب بشري، محاسبة',
    'edu_university': 'اسم الجامعة أو المعهد.\nمثال: جامعة دمشق، جامعة حلب',
    'employment': 'الحالة الوظيفية الحالية.\nيعمل، عاطل عن العمل، متقاعد، طالب',
    'profession': 'المهنة أو الحرفة.\nمثال: مدرس، مهندس، حداد، سائق',
    'employer': 'جهة العمل إن وجدت.\nمثال: وزارة التربية، القطاع الخاص',
    # --- الصحة ---
    'chronic': 'الأمراض المزمنة المعروفة.\nمثال: ضغط دم، سكري، قلب، ربو',
    'has_hypertension': 'هل يعاني من ارتفاع ضغط الدم؟\n1 = نعم، 0 = لا',
    'has_diabetes': 'هل يعاني من مرض السكري؟\n1 = نعم، 0 = لا',
    'has_special_needs': 'هل لديه احتياجات خاصة (إعاقة جسدية أو ذهنية)؟\n1 = نعم، 0 = لا',
    'special_needs_details': 'تفاصيل الاحتياجات الخاصة.\nمثال: إعاقة حركية - كرسي متحرك',
    # --- المعيل ---
    'breadwinner': 'هل الشخص هو المعيل الرئيسي لعائلته؟\nنعم أو لا',
    'breadwinner_job': 'عمل المعيل الحالي أو البديل.\nمثال: أخوه يعمل في ورشة',
    'breadwinner_relation': 'صلة المعيل البديل بالعائلة.\nمثال: الأخ الأكبر، الأم، العم',
    # --- القانون ---
    'legal': 'هل هناك إجراءات قانونية متعلقة بالحالة؟\nنعم أو لا',
    'legal_details': 'تفاصيل الوضع القانوني.\nمثال: تم رفع دعوى أمام محكمة الإرهاب، لا يوجد محامٍ',
    'is_officially_registered': 'هل الحالة مسجلة رسمياً لدى جهة حكومية أو منظمة دولية؟\n1 = نعم، 0 = لا',
    'cause_number': 'رقم القضية أو الدعوى إن وجد.\nمثال: 1234/2024',
    # --- السجل المدني ---
    'civil_registry_status': 'حالة الشخص في السجل المدني (النفوس).\nحي: مسجل كحي\nمتوفى: تم تسجيل الوفاة\nمفقود: لا توجد معلومات',
    'civil_registry_date': 'تاريخ آخر تحديث في السجل المدني.\nمثال: 2023-06-15',
    'civil_registry_document': 'صورة إخراج القيد أو وثيقة السجل المدني.\nصيغ مقبولة: JPG, PNG, PDF',
    'family_book_number': 'رقم دفتر العائلة.\nمثال: 123456',
    # --- الأدلة والتوثيق ---
    'evidence_level': 'مستوى قوة الأدلة المتوفرة وفق بروتوكول بيركلي.\nغير موثق: لم يتم التحقق بعد\nضعيف: مصدر واحد غير مؤكد\nمتوسط: أكثر من مصدر أو وثيقة جزئية\nقوي: عدة مصادر مستقلة مع وثائق\nمؤكد: أدلة قاطعة ووثائق رسمية',
    'evidence_sources_count': 'عدد المصادر المستقلة التي تؤكد المعلومات.\nمثال: 3 (إذا تم التحقق من 3 مصادر مختلفة)',
    'verification_status': 'حالة التحقق من المعلومات.\nUnverified: لم يتم التحقق\nPartially Verified: تم التحقق جزئياً\nVerified: تم التحقق بالكامل\nContradicted: توجد تناقضات',
    'source_type': 'كيف تم الحصول على المعلومات. مطلوب للترقية من مسودة.\nمقابلة مباشرة: جلسة شخصية مع المُبلِّغ\nمقابلة هاتفية: عبر الهاتف\nوثائق رسمية: أوراق حكومية أو قانونية\nمصادر مفتوحة: إنترنت، إعلام، تقارير منظمات\nشهادة شاهد: رواية شخص حاضر\nتسريبات: معلومات مسربة من جهات رسمية\nإحالة: من منظمة أو جهة أخرى',
    'methodology_notes': 'ملاحظات حول منهجية جمع البيانات.\nمثال: مقابلة شخصية في مكتب الجمعية، استغرقت ساعتين، تم التسجيل الصوتي بموافقة المُبلِّغ',
    'methodology_type': 'نوع المنهجية المتبعة في جمع المعلومات.\nمقابلة شخصية، مراجعة وثائق، تحقيق مصادر مفتوحة، زيارة ميدانية',
    'notes': 'ملاحظات إضافية عامة لا تندرج تحت حقل محدد.\nمثال: الحالة بحاجة لمتابعة قانونية عاجلة',
    # --- الأدلة الرقمية ---
    'digital_evidence_type': 'نوع الدليل الرقمي المتوفر.\nفيديو، صورة، منشور على وسائل التواصل، مستند إلكتروني، تسجيل صوتي',
    'digital_evidence_url': 'رابط الدليل الرقمي على الإنترنت.\nمثال: رابط منشور فيسبوك، رابط فيديو يوتيوب، رابط تقرير',
    'digital_evidence_description': 'وصف مختصر للدليل الرقمي ومحتواه.\nمثال: فيديو يظهر لحظة الاعتقال على حاجز المزة',
    'digital_evidence_screenshot': 'لقطة شاشة للدليل الرقمي (مهم في حال حذف المحتوى الأصلي).',
    'digital_evidence_person_name': 'اسم الشخص المذكور في الدليل الرقمي.',
    'digital_evidence_death_date': 'تاريخ الوفاة المذكور في الدليل الرقمي (إن وجد).',
    # --- السيرة الذاتية ---
    'survivor_cv': 'ملف السيرة الذاتية للناجي (ملف مرفق).\nصيغ مقبولة: صور، PDF، Word',
    'survivor_cv_text': 'نص السيرة الذاتية أو ملخص قصة الناجي مكتوباً.',
    'survivor_cv_photo': 'صورة إضافية مرفقة بسيرة الناجي.',
    # --- التحقق والقفل ---
    'record_status': 'حالة السجل في سير عمل بروتوكول بيركلي:\nمسودة: سجل جديد لم يُراجع بعد\nمراجَع: تمت مراجعته من قبل شخص آخر\nموثّق: تم التحقق من المعلومات من مصادر مستقلة\nمقفل: السجل نهائي ولا يمكن تعديله',
    # --- الشهود ---
    'witnesses': 'بيانات الشهود الذين يمكنهم تأكيد المعلومات.\nالاسم: اسم الشاهد\nالصلة: علاقته بالضحية\nالهاتف: للتواصل\nالشهادة: ملخص ما شاهده',
    # --- مرافق الاحتجاز ---
    'detention_facilities': 'مراكز الاحتجاز التي تم احتجاز الشخص فيها.\nاسم المرفق، تاريخ الدخول والخروج، ملاحظات',
    # --- التضارب ---
    'has_conflicting_info': 'هل توجد معلومات متضاربة من مصادر مختلفة حول هذه الحالة؟\n1 = نعم، 0 = لا',
    'conflicting_info_details': 'تفاصيل التضارب في المعلومات.\nمثال: مصدر يقول أُفرج عنه عام 2015، ومصدر آخر يقول لا يزال معتقلاً',
    'last_known_alive_date': 'آخر تاريخ معروف كان فيه الشخص على قيد الحياة.\nمثال: 2013-08-20',
    'last_known_location': 'آخر مكان معروف كان فيه الشخص.\nمثال: فرع المخابرات الجوية - المزة',
    # --- الوثائق المتعددة ---
    'source_url': 'رابط المصدر الأصلي للمعلومات. حتى لو كان الرابط محذوفاً الآن، وثّقه هنا لإثبات المصدر.\nمثال: رابط الموقع الإخباري الذي نشر تسريبات عن المعتقلين',
    'extra_documents': 'يمكنك رفع عدة وثائق لهذه الحالة: أوامر محكمة، كروت زيارة سجين، أوراق إفراج، لقطات شاشة تسريبات، شهادات وفاة.\nكل وثيقة تُحفظ مع بصمتها الرقمية SHA-256 لضمان سلامة سلسلة الحفظ.',
    'digital_evidence_url_status': 'حالة رابط الدليل الرقمي:\nفعّال: الرابط يعمل\nمحذوف: كان موجوداً وحُذف\nمؤرشف: متاح في أرشيف الإنترنت\nغير معروف: لم يتم التحقق\nلم يكن هناك رابط: وصلت اللقطة عبر واتساب أو شخصياً\nالرابط غير متاح (نُسي): الأهل لا يتذكرون الرابط',
}


@app.route('/admin/record/<int:record_id>/verify', methods=['POST'])
@admin_required
def admin_record_verify(record_id):
    """Change record verification status with Berkeley Protocol workflow enforcement."""
    db = get_db()
    record = db.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
    if not record:
        flash('السجل غير موجود', 'error')
        return redirect(url_for('admin_records'))
    new_status = request.form.get('record_status', '')
    valid_statuses = ['draft', 'reviewed', 'verified', 'locked']
    if new_status not in valid_statuses:
        flash('حالة غير صالحة', 'error')
        return redirect(url_for('admin_record_detail', record_id=record_id))

    old_status = record['record_status'] or 'draft'
    user_role = session.get('user_role', 'admin')

    # Enforce workflow transitions
    allowed_next = VALID_STATUS_TRANSITIONS.get(old_status, [])
    if new_status not in allowed_next:
        flash(f'لا يمكن الانتقال من {STATUS_LABELS.get(old_status, old_status)} إلى {STATUS_LABELS.get(new_status, new_status)} مباشرة', 'error')
        return redirect(url_for('admin_record_detail', record_id=record_id))

    # Admin-only transitions
    if new_status in ('verified', 'locked') and user_role != 'admin':
        flash('فقط المدير يمكنه توثيق أو قفل السجلات', 'error')
        return redirect(url_for('admin_record_detail', record_id=record_id))
    if old_status == 'locked' and user_role != 'admin':
        flash('فقط المدير يمكنه فتح السجلات المقفلة', 'error')
        return redirect(url_for('admin_record_detail', record_id=record_id))

    # Berkeley Protocol: Check mandatory fields before advancing
    required_fields = BERKELEY_REQUIRED_FIELDS.get(new_status, [])
    missing = [f for f in required_fields if not (record[f] if f in record.keys() else '')]
    if missing:
        field_labels = {
            'first_name': 'الاسم', 'father_name': 'اسم الأب', 'last_name': 'الكنية',
            'status': 'الحالة', 'source_type': 'نوع المصدر', 'collector_name': 'اسم جامع البيانات',
            'collection_date': 'تاريخ الجمع', 'evidence_level': 'مستوى الأدلة',
            'verification_status': 'حالة التحقق',
        }
        missing_labels = [field_labels.get(f, f) for f in missing]
        flash(f'لا يمكن الترقية: الحقول التالية مطلوبة: {", ".join(missing_labels)}', 'error')
        return redirect(url_for('admin_record_detail', record_id=record_id))

    db.execute("UPDATE records SET record_status = ? WHERE id = ?", (new_status, record_id))
    # Track the change with chain of custody
    ip = request.remote_addr or ''
    changed_by = session.get('username', session.get('display_name', 'admin'))
    db.execute(
        "INSERT INTO record_changes (record_id, field_name, old_value, new_value, changed_by, ip_address) VALUES (?,?,?,?,?,?)",
        (record_id, 'record_status', old_status, new_status, changed_by, ip)
    )
    db.commit()
    log_audit('record_verify', 'record', record_id, {
        'transition': f'{old_status} -> {new_status}',
        'description': f'Status changed from {old_status} to {new_status}',
    })
    flash(f'تم تغيير حالة السجل إلى: {STATUS_LABELS.get(new_status, new_status)}', 'success')
    return redirect(url_for('admin_record_detail', record_id=record_id))


@app.route('/admin/record/<int:record_id>/verify-integrity', methods=['POST'])
@admin_required
def admin_record_verify_integrity(record_id):
    """Berkeley Protocol: Verify file integrity by recomputing SHA256 hashes."""
    db = get_db()
    record = db.execute("SELECT id, photo_path, photo_hash, document_path, document_hash, "
                        "digital_evidence_screenshot_path, screenshot_hash FROM records WHERE id = ?",
                        (record_id,)).fetchone()
    if not record:
        return jsonify({'error': 'السجل غير موجود'}), 404

    results = {}
    file_checks = [
        ('photo', record['photo_path'], record['photo_hash']),
        ('document', record['document_path'], record['document_hash']),
        ('screenshot', record['digital_evidence_screenshot_path'], record.get('screenshot_hash', '')),
    ]

    for label, file_path, stored_hash in file_checks:
        if not file_path:
            results[label] = {'status': 'no_file', 'message': 'لا يوجد ملف'}
            continue
        full_path = os.path.join(BASE_DIR, file_path) if not os.path.isabs(file_path) else file_path
        if not os.path.exists(full_path):
            results[label] = {'status': 'missing', 'message': 'الملف مفقود'}
            continue
        # Recompute hash
        sha256 = hashlib.sha256()
        with open(full_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        current_hash = sha256.hexdigest()

        if not stored_hash:
            # Store hash for first time
            hash_col = f'{label}_hash'
            if label == 'screenshot':
                hash_col = 'screenshot_hash'
            try:
                db.execute(f"UPDATE records SET {hash_col} = ? WHERE id = ?", (current_hash, record_id))
                db.commit()
            except sqlite3.OperationalError:
                pass
            results[label] = {'status': 'initialized', 'message': 'تم حساب البصمة لأول مرة', 'hash': current_hash}
        elif current_hash == stored_hash:
            results[label] = {'status': 'verified', 'message': 'سلامة الملف مؤكدة ✓', 'hash': current_hash}
        else:
            results[label] = {'status': 'tampered', 'message': 'تحذير: الملف تم تعديله!',
                              'stored_hash': stored_hash, 'current_hash': current_hash}

    log_audit('integrity_check', 'record', record_id, {
        'results': {k: v['status'] for k, v in results.items()},
    })
    return jsonify({'record_id': record_id, 'integrity': results})


@app.route('/admin/record/<int:record_id>/delete', methods=['POST'])
@admin_required
def admin_record_delete(record_id):
    db = get_db()
    db.execute("UPDATE records SET deleted_at = datetime('now','localtime') WHERE id = ? AND deleted_at IS NULL", (record_id,))
    db.commit()
    log_audit('record_soft_delete', 'record', record_id)
    flash(Markup('تم حذف السجل. <a href="' + url_for('admin_record_restore', record_id=record_id) + '">تراجع</a>'), 'success')
    return redirect(url_for('admin_records'))


@app.route('/admin/record/<int:record_id>/restore', methods=['GET', 'POST'])
@admin_required
def admin_record_restore(record_id):
    db = get_db()
    db.execute("UPDATE records SET deleted_at = NULL WHERE id = ?", (record_id,))
    db.commit()
    log_audit('record_restore', 'record', record_id)
    flash('تم استعادة السجل بنجاح', 'success')
    return redirect(url_for('admin_record_detail', record_id=record_id))


@app.route('/admin/trash')
@admin_required
def admin_trash():
    db = get_db()
    records = db.execute(
        "SELECT id, first_name, father_name, last_name, status, province, deleted_at "
        "FROM records WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC"
    ).fetchall()
    return render_template('admin_trash.html', records=records)


@app.route('/admin/trash/empty', methods=['POST'])
@admin_required
def admin_trash_empty():
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM records WHERE deleted_at IS NOT NULL").fetchone()[0]
    db.execute("DELETE FROM records WHERE deleted_at IS NOT NULL")
    db.commit()
    log_audit('trash_empty', 'record', 0, f'Permanently deleted {count} records')
    flash(f'تم حذف {count} سجل نهائياً', 'success')
    return redirect(url_for('admin_trash'))


# ---------------------------------------------------------------------------
# PDF Export
# ---------------------------------------------------------------------------
@app.route('/admin/record/<int:record_id>/pdf')
@admin_required
def record_pdf(record_id):
    db = get_db()
    record = db.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
    if not record:
        flash('السجل غير موجود', 'error')
        return redirect(url_for('admin_records'))

    # Read logo as base64
    logo_path = os.path.join(BASE_DIR, 'logo.jpg')
    logo_b64 = ''
    if os.path.exists(logo_path):
        with open(logo_path, 'rb') as f:
            logo_b64 = base64.b64encode(f.read()).decode()

    # Read photo as base64 if exists (local file only; URLs won't work in PDF)
    photo_b64 = ''
    photo_url = ''
    if record['photo_path']:
        if record['photo_path'].startswith('http://') or record['photo_path'].startswith('https://'):
            photo_url = record['photo_path']
        else:
            photo_file = os.path.join(UPLOAD_FOLDER, 'photos', record['photo_path'])
            if os.path.exists(photo_file):
                with open(photo_file, 'rb') as f:
                    photo_b64 = base64.b64encode(f.read()).decode()

    html = render_template('pdf_record.html',
        record=record, logo_b64=logo_b64, photo_b64=photo_b64, photo_url=photo_url)

    from weasyprint import HTML
    pdf_bytes = HTML(string=html, base_url=BASE_DIR).write_pdf()

    response = make_response(pdf_bytes)
    name = f"{record['first_name']}_{record['last_name']}_{record['id']}"
    safe_name = f"record_{record['id']}"
    encoded_name = quote(f"record_{name}.pdf")
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f"inline; filename={safe_name}.pdf; filename*=UTF-8''{encoded_name}"
    return response


def build_pdf_filter_conditions(args):
    """Build SQL filter conditions from request args. Shared by PDF route and filtered IDs API.
    Now delegates to the unified _build_record_filter_conditions."""
    filters = _filters_from_request_args(args)
    conditions, params = _build_record_filter_conditions(filters)
    return conditions, params, filters['status_list']


@app.route('/admin/records/pdf', methods=['GET', 'POST'])
@admin_required
def records_list_pdf():
    db = get_db()

    # Use POST data if available, otherwise GET
    args = request.form if request.method == 'POST' else request.args

    conditions, params, pdf_status_list = build_pdf_filter_conditions(args)

    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    # Check if post-filtering is needed
    pdf_kids_age_from = safe_int(args.get('kids_age_from'))
    pdf_kids_age_to = safe_int(args.get('kids_age_to'))
    pdf_kids_max_age = safe_int(args.get('kids_max_age'))
    pdf_minor_threshold = safe_int(args.get('minor_age_threshold'), 18)
    needs_post_filter = (pdf_kids_age_from is not None or pdf_kids_age_to is not None
                         or pdf_kids_max_age is not None
                         or (args.get('has_kids_under_18') in ('yes', 'no') and pdf_minor_threshold != 18))

    # When post-filtering is needed, fetch all records (no LIMIT) so the post-filter
    # sees the full result set, then apply LIMIT afterwards
    sql_limit = "" if needs_post_filter else " LIMIT 500"
    records = db.execute(
        f"SELECT * FROM records{where} ORDER BY id DESC{sql_limit}", params
    ).fetchall()

    # Post-filter by kids age range if specified
    if pdf_kids_age_from is not None or pdf_kids_age_to is not None:
        records = [r for r in records if record_has_child_in_age_range(r, pdf_kids_age_from, pdf_kids_age_to)]
    if pdf_kids_max_age is not None:
        records = [r for r in records if record_has_child_in_age_range(r, 0, pdf_kids_max_age)]
    # Post-filter for custom minor age threshold
    if args.get('has_kids_under_18') in ('yes', 'no') and pdf_minor_threshold != 18:
        if args['has_kids_under_18'] == 'yes':
            records = [r for r in records if record_has_child_in_age_range(r, 0, pdf_minor_threshold - 1)]
        else:
            records = [r for r in records if not record_has_child_in_age_range(r, 0, pdf_minor_threshold - 1)]

    # If user provided an explicit ordered list of record IDs (from the picker),
    # use that order, fetching any extra IDs the user added via search.
    record_order = args.getlist('record_order')
    if record_order:
        ordered_ids = [int(x) for x in record_order if x.isdigit()]
        # Build lookup from already-fetched records
        rec_map = {r['id']: r for r in records}
        # Find IDs we don't have yet (added via search)
        missing_ids = [rid for rid in ordered_ids if rid not in rec_map]
        if missing_ids:
            placeholders = ','.join(['?'] * len(missing_ids))
            extra = db.execute(f"SELECT * FROM records WHERE deleted_at IS NULL AND id IN ({placeholders})", missing_ids).fetchall()
            for r in extra:
                rec_map[r['id']] = r
        # Rebuild records in the user's custom order
        records = [rec_map[rid] for rid in ordered_ids if rid in rec_map]

    # Apply record limit
    pdf_limit = args.get('pdf_limit', '').strip()
    if pdf_limit and pdf_limit.isdigit() and int(pdf_limit) > 0:
        records = records[:int(pdf_limit)]

    logo_path = os.path.join(BASE_DIR, 'logo.jpg')
    logo_b64 = ''
    if os.path.exists(logo_path):
        with open(logo_path, 'rb') as f:
            logo_b64 = base64.b64encode(f.read()).decode()

    # Get selected columns (or use defaults)
    selected_cols = args.getlist('cols')
    if not selected_cols:
        selected_cols = DEFAULT_PDF_COLS

    # Build column headers for PDF
    col_map = dict(PDF_COLUMNS)
    pdf_cols = [(c, col_map.get(c, c)) for c in selected_cols if c in col_map]

    # Build filter description
    filter_desc = []
    if pdf_status_list:
        status_labels = [STATUS_MAP.get(s, s) for s in pdf_status_list]
        filter_desc.append(f"الحالة: {' + '.join(status_labels)}")
    if args.get('province'):
        filter_desc.append(f"المحافظة: {args['province']}")
    if args.get('gender'):
        filter_desc.append(f"الجنس: {'ذكر' if args['gender']=='male' else 'أنثى'}")
    if args.get('marital'):
        marital_map = dict(MARITAL_STATUSES)
        filter_desc.append(f"الحالة الاجتماعية: {marital_map.get(args['marital'], args['marital'])}")
    if args.get('education') or args.get('education_max'):
        edu_val = args.get('education') or f"حتى {args.get('education_max')}"
        filter_desc.append(f"التحصيل العلمي: {edu_val}")
    if args.get('has_kids_under_18') == 'yes':
        _mt = safe_int(args.get('minor_age_threshold'), 18)
        filter_desc.append(f"لديه أطفال قاصرين (تحت {_mt})")
    elif args.get('has_kids_under_18') == 'no':
        _mt = safe_int(args.get('minor_age_threshold'), 18)
        filter_desc.append(f"بدون أطفال قاصرين (تحت {_mt})")
    if args.get('has_special_needs') == '1':
        filter_desc.append("ذوي احتياجات خاصة")
    widows_f = args.get('widows_filter', '')
    if widows_f:
        widows_labels = {
            'widows_deceased': 'أرامل الشهداء',
            'widows_enforced': 'زوجات المغيّبين',
            'widows_all': 'جميع الأرامل',
            'widows_with_minors': 'أرامل لديهم قاصرين',
        }
        filter_desc.append(widows_labels.get(widows_f, widows_f))
    if args.get('has_hypertension') == '1':
        filter_desc.append("ضغط دم")
    if args.get('has_diabetes') == '1':
        filter_desc.append("سكري")
    if args.get('chronic') == 'yes':
        filter_desc.append("أمراض مزمنة")

    show_sum = args.get('show_sum') == '1'
    sum_cols_requested = args.getlist('sum_cols')

    # Virtual columns that don't exist in the database
    VIRTUAL_COLS = {'children_summary', 'minors_summary', 'kids_u13_names', 'kids_u13_ages'}

    # Pre-calculate sums for selected numeric columns if requested
    col_sums = {}
    if show_sum and sum_cols_requested:
        sum_cols_set = set(sum_cols_requested)
        for col_key, col_label in pdf_cols:
            if col_key not in sum_cols_set or col_key in VIRTUAL_COLS:
                continue
            total_val = 0
            has_numeric = False
            for r in records:
                try:
                    val = r[col_key]
                    if val is not None and val != '' and str(val).strip():
                        num = int(val) if isinstance(val, int) else float(str(val).strip())
                        total_val += num
                        has_numeric = True
                except (ValueError, TypeError, KeyError, IndexError):
                    pass
            if has_numeric:
                col_sums[col_key] = int(total_val) if total_val == int(total_val) else round(total_val, 2)

    html = render_template('pdf_list.html',
        records=records, logo_b64=logo_b64, filter_desc=filter_desc,
        total=len(records), pdf_cols=pdf_cols, selected_cols=selected_cols,
        show_sum=show_sum, col_sums=col_sums,
        current_year=datetime.now().year,
        minor_age_threshold=pdf_minor_threshold)

    from weasyprint import HTML
    pdf_bytes = HTML(string=html, base_url=BASE_DIR).write_pdf()

    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename=records_report_{int(time.time())}.pdf'
    return response


# ---------------------------------------------------------------------------
# Export: records list → Excel
# ---------------------------------------------------------------------------
def _format_cell_value(record, col_key, current_year, minor_threshold=18):
    """Format a record's column value for Excel export (mirrors PDF template logic)."""
    if col_key == 'status':
        return STATUS_MAP.get(record['status'], record['status'] or '-')
    if col_key == 'gender':
        return {'male': 'ذكر', 'female': 'أنثى'}.get(record['gender'], '-')
    if col_key == 'marital':
        mmap = dict(MARITAL_STATUSES)
        return mmap.get(record['marital'], record['marital'] or '-')
    if col_key == 'case_type':
        cmap = dict(CASE_TYPES)
        return cmap.get(record['case_type'], record['case_type'] or '-')
    if col_key == 'evidence_level':
        emap = dict(EVIDENCE_LEVELS)
        return emap.get(record['evidence_level'], record['evidence_level'] or '-')
    if col_key == 'verification_status':
        vmap = dict(VERIFICATION_STATUSES)
        return vmap.get(record['verification_status'], record['verification_status'] or '-')
    if col_key == 'digital_evidence_type':
        dmap = dict(DIGITAL_EVIDENCE_TYPES)
        return dmap.get(record['digital_evidence_type'], record['digital_evidence_type'] or '-')
    if col_key == 'civil_registry_status':
        crmap = dict(CIVIL_REGISTRY_STATUSES)
        return crmap.get(record['civil_registry_status'], record['civil_registry_status'] or '-')
    if col_key == 'contact_phone':
        return (record['phone'] or record['spouse_phone'] or
                record['guardian_phone'] or record['reporter_phone'] or '-')
    if col_key in ('has_special_needs', 'has_hypertension', 'has_diabetes',
                    'has_conflicting_info', 'is_officially_registered'):
        return 'نعم' if record[col_key] else '-'
    if col_key == 'kids_count':
        return record['kids_count'] if record['has_kids'] == 'yes' else '-'
    if col_key == 'kids_under_18_count':
        return record['kids_under_18_count'] if record['kids_under_18_count'] else '-'
    if col_key == 'children_summary':
        try:
            children = json.loads(record['children_data'] or '[]')
        except (json.JSONDecodeError, TypeError):
            children = []
        if not children:
            return '-'
        parts = []
        for c in children:
            name = c.get('name', '')
            if c.get('birth_year'):
                parts.append(f"{name}({c['birth_year']})")
            elif c.get('age'):
                parts.append(f"{name}(~{current_year - int(c['age'])})")
            else:
                parts.append(name)
        return ', '.join(parts)
    if col_key == 'minors_summary':
        try:
            children = json.loads(record['children_data'] or '[]')
        except (json.JSONDecodeError, TypeError):
            children = []
        mt = minor_threshold
        minors = []
        for c in children:
            if c.get('birth_year') and (current_year - int(c['birth_year'])) < mt:
                minors.append(c)
            elif c.get('age') and int(c['age']) < mt:
                minors.append(c)
        if not minors:
            return '-'
        parts = []
        for c in minors:
            name = c.get('name', '')
            if c.get('birth_year'):
                parts.append(f"{name}({c['birth_year']})")
            elif c.get('age'):
                parts.append(f"{name}(~{current_year - int(c['age'])})")
            else:
                parts.append(name)
        return ', '.join(parts)
    if col_key == 'kids_u13_names':
        try:
            children = json.loads(record['children_data'] or '[]')
        except (json.JSONDecodeError, TypeError):
            children = []
        mt = minor_threshold
        names = [c.get('name', '') for c in children
                 if (c.get('birth_year') and (current_year - int(c['birth_year'])) < mt)
                 or (c.get('age') and int(c['age']) < mt)]
        return ', '.join(names) if names else '-'
    if col_key == 'kids_u13_ages':
        try:
            children = json.loads(record['children_data'] or '[]')
        except (json.JSONDecodeError, TypeError):
            children = []
        mt = minor_threshold
        ages = []
        for c in children:
            if c.get('birth_year') and (current_year - int(c['birth_year'])) < mt:
                ages.append(str(current_year - int(c['birth_year'])))
            elif c.get('age') and int(c['age']) < mt:
                ages.append(str(int(c['age'])))
        return ', '.join(ages) if ages else '-'
    # Default
    val = record[col_key] if col_key in record.keys() else ''
    return val if val not in (None, '') else '-'


@app.route('/admin/records/excel', methods=['GET', 'POST'])
@admin_required
def records_list_excel():
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    db = get_db()
    args = request.form if request.method == 'POST' else request.args

    conditions, params, pdf_status_list = build_pdf_filter_conditions(args)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    # Check if post-filtering is needed (same logic as PDF route)
    pdf_kids_age_from = safe_int(args.get('kids_age_from'))
    pdf_kids_age_to = safe_int(args.get('kids_age_to'))
    pdf_kids_max_age = safe_int(args.get('kids_max_age'))
    pdf_minor_threshold = safe_int(args.get('minor_age_threshold'), 18)
    needs_post_filter = (pdf_kids_age_from is not None or pdf_kids_age_to is not None
                         or pdf_kids_max_age is not None
                         or (args.get('has_kids_under_18') in ('yes', 'no') and pdf_minor_threshold != 18))

    sql_limit = "" if needs_post_filter else " LIMIT 500"
    records = db.execute(
        f"SELECT * FROM records{where} ORDER BY id DESC{sql_limit}", params
    ).fetchall()

    # Post-filters (same as PDF)
    if pdf_kids_age_from is not None or pdf_kids_age_to is not None:
        records = [r for r in records if record_has_child_in_age_range(r, pdf_kids_age_from, pdf_kids_age_to)]
    if pdf_kids_max_age is not None:
        records = [r for r in records if record_has_child_in_age_range(r, 0, pdf_kids_max_age)]
    if args.get('has_kids_under_18') in ('yes', 'no') and pdf_minor_threshold != 18:
        if args['has_kids_under_18'] == 'yes':
            records = [r for r in records if record_has_child_in_age_range(r, 0, pdf_minor_threshold - 1)]
        else:
            records = [r for r in records if not record_has_child_in_age_range(r, 0, pdf_minor_threshold - 1)]

    # Custom record ordering
    record_order = args.getlist('record_order')
    if record_order:
        ordered_ids = [int(x) for x in record_order if x.isdigit()]
        rec_map = {r['id']: r for r in records}
        missing_ids = [rid for rid in ordered_ids if rid not in rec_map]
        if missing_ids:
            placeholders = ','.join(['?'] * len(missing_ids))
            extra = db.execute(f"SELECT * FROM records WHERE deleted_at IS NULL AND id IN ({placeholders})", missing_ids).fetchall()
            for r in extra:
                rec_map[r['id']] = r
        records = [rec_map[rid] for rid in ordered_ids if rid in rec_map]

    pdf_limit = args.get('pdf_limit', '').strip()
    if pdf_limit and pdf_limit.isdigit() and int(pdf_limit) > 0:
        records = records[:int(pdf_limit)]

    selected_cols = args.getlist('cols')
    if not selected_cols:
        selected_cols = DEFAULT_PDF_COLS
    col_map = dict(PDF_COLUMNS)
    excel_cols = [(c, col_map.get(c, c)) for c in selected_cols if c in col_map]
    current_year = datetime.now().year

    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = 'السجلات'
    ws.sheet_view.rightToLeft = True

    # Styles
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color='1a5276', end_color='1a5276', fill_type='solid')
    header_font_white = Font(bold=True, size=11, color='FFFFFF')
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    wrap_alignment = Alignment(horizontal='right', vertical='center', wrap_text=True)

    # Write headers
    for col_idx, (col_key, col_label) in enumerate(excel_cols, 1):
        cell = ws.cell(row=1, column=col_idx, value=col_label)
        cell.font = header_font_white
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = thin_border

    # Write data rows
    for row_idx, record in enumerate(records, 2):
        for col_idx, (col_key, _) in enumerate(excel_cols, 1):
            val = _format_cell_value(record, col_key, current_year, pdf_minor_threshold)
            cell = ws.cell(row=row_idx, column=col_idx, value=val if val != '-' else '')
            cell.alignment = wrap_alignment
            cell.border = thin_border

    # Auto-fit column widths (approximate)
    for col_idx, (col_key, col_label) in enumerate(excel_cols, 1):
        max_len = len(col_label)
        for row_idx in range(2, min(len(records) + 2, 50)):
            cell_val = str(ws.cell(row=row_idx, column=col_idx).value or '')
            max_len = max(max_len, min(len(cell_val), 40))
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = max_len + 4

    # Freeze header row
    ws.freeze_panes = 'A2'

    # Write to buffer
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f'records_report_{int(time.time())}.xlsx'
    return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=filename)


# ---------------------------------------------------------------------------
# Export: VCF contacts (Android-compatible vCard)
# ---------------------------------------------------------------------------
@app.route('/admin/records/vcf', methods=['GET', 'POST'])
@admin_required
def records_export_vcf():
    """Export filtered records as a .vcf file for importing contacts on Android."""
    db = get_db()
    args = request.form if request.method == 'POST' else request.args

    conditions, params, pdf_status_list = build_pdf_filter_conditions(args)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    # Check if post-filtering is needed (same logic as PDF/Excel routes)
    pdf_kids_age_from = safe_int(args.get('kids_age_from'))
    pdf_kids_age_to = safe_int(args.get('kids_age_to'))
    pdf_kids_max_age = safe_int(args.get('kids_max_age'))
    pdf_minor_threshold = safe_int(args.get('minor_age_threshold'), 18)
    needs_post_filter = (pdf_kids_age_from is not None or pdf_kids_age_to is not None
                         or pdf_kids_max_age is not None
                         or (args.get('has_kids_under_18') in ('yes', 'no') and pdf_minor_threshold != 18))

    sql_limit = "" if needs_post_filter else " LIMIT 500"
    records = db.execute(
        f"SELECT * FROM records{where} ORDER BY id DESC{sql_limit}", params
    ).fetchall()

    # Post-filters (same as PDF/Excel)
    if pdf_kids_age_from is not None or pdf_kids_age_to is not None:
        records = [r for r in records if record_has_child_in_age_range(r, pdf_kids_age_from, pdf_kids_age_to)]
    if pdf_kids_max_age is not None:
        records = [r for r in records if record_has_child_in_age_range(r, 0, pdf_kids_max_age)]
    if args.get('has_kids_under_18') in ('yes', 'no') and pdf_minor_threshold != 18:
        if args['has_kids_under_18'] == 'yes':
            records = [r for r in records if record_has_child_in_age_range(r, 0, pdf_minor_threshold - 1)]
        else:
            records = [r for r in records if not record_has_child_in_age_range(r, 0, pdf_minor_threshold - 1)]

    # Custom record ordering
    record_order = args.getlist('record_order')
    if record_order:
        ordered_ids = [int(x) for x in record_order if x.isdigit()]
        rec_map = {r['id']: r for r in records}
        missing_ids = [rid for rid in ordered_ids if rid not in rec_map]
        if missing_ids:
            placeholders = ','.join(['?'] * len(missing_ids))
            extra = db.execute(f"SELECT * FROM records WHERE deleted_at IS NULL AND id IN ({placeholders})", missing_ids).fetchall()
            for r in extra:
                rec_map[r['id']] = r
        records = [rec_map[rid] for rid in ordered_ids if rid in rec_map]

    pdf_limit = args.get('pdf_limit', '').strip()
    if pdf_limit and pdf_limit.isdigit() and int(pdf_limit) > 0:
        records = records[:int(pdf_limit)]

    # Build VCF content (vCard 2.1 for maximum Android compatibility)
    def vcf_escape(text):
        """Escape special characters in vCard text values and strip newlines."""
        if not text:
            return ''
        text = text.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ')
        return text.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')

    vcf_lines = []
    status_map = {'survivor': 'ناجٍ', 'enforced': 'مغيّب قسراً', 'deceased': 'متوفى'}

    for rec in records:
        first = vcf_escape(rec['first_name'] or '')
        father = vcf_escape(rec['father_name'] or '')
        last = vcf_escape(rec['last_name'] or '')
        full_name = ' '.join(part for part in [first, father, last] if part)
        if not full_name:
            continue

        vcf_lines.append('BEGIN:VCARD')
        vcf_lines.append('VERSION:2.1')
        vcf_lines.append(f'FN;CHARSET=UTF-8:{full_name}')
        vcf_lines.append(f'N;CHARSET=UTF-8:{last};{first};{father};;')

        # Phone numbers
        phone = (rec['phone'] or '').strip()
        spouse_phone = (rec['spouse_phone'] or '').strip()
        guardian_phone = (rec['guardian_phone'] or '').strip()
        reporter_phone = (rec['reporter_phone'] or '').strip()

        if phone:
            vcf_lines.append(f'TEL;CELL:{phone}')
        if spouse_phone:
            vcf_lines.append(f'TEL;HOME:{spouse_phone}')
        if guardian_phone:
            vcf_lines.append(f'TEL;WORK:{guardian_phone}')
        if reporter_phone:
            vcf_lines.append(f'TEL;VOICE:{reporter_phone}')

        # Organization / title
        if rec['assoc_name']:
            vcf_lines.append(f'ORG;CHARSET=UTF-8:{vcf_escape(rec["assoc_name"])}')

        if rec['profession']:
            vcf_lines.append(f'TITLE;CHARSET=UTF-8:{vcf_escape(rec["profession"])}')

        # Address
        address = vcf_escape((rec['address'] or '').strip())
        province = vcf_escape((rec['province'] or '').strip())
        if address or province:
            vcf_lines.append(f'ADR;HOME;CHARSET=UTF-8:;;{address};;{province};;')

        # Birthday (only emit full YYYY-MM-DD dates for compatibility)
        birth_year = rec['birth_year'] or ''
        birth_month = rec['birth_month'] or ''
        birth_day = rec['birth_day'] or ''
        if birth_year and birth_month and birth_day:
            try:
                bday = f'{int(birth_year):04d}-{int(birth_month):02d}-{int(birth_day):02d}'
                vcf_lines.append(f'BDAY:{bday}')
            except (ValueError, TypeError):
                pass

        # Note field - pack useful info
        rec_keys = rec.keys()
        note_parts = []
        status_label = status_map.get(rec['status'], rec['status'] or '')
        if status_label:
            note_parts.append(f'الحالة: {status_label}')
        if rec['national_id']:
            note_parts.append(f'الرقم الوطني: {rec["national_id"]}')
        if rec['mother_name']:
            note_parts.append(f'الأم: {rec["mother_name"]}')
        if rec['spouse_name']:
            note_parts.append(f'الزوج/ة: {rec["spouse_name"]}')
            if spouse_phone:
                note_parts.append(f'هاتف الزوج/ة: {spouse_phone}')
        if rec['guardian_name']:
            note_parts.append(f'ولي الأمر: {rec["guardian_name"]}')
            if guardian_phone:
                note_parts.append(f'هاتف ولي الأمر: {guardian_phone}')
        if rec['reporter_name']:
            note_parts.append(f'المبلغ: {rec["reporter_name"]}')
            if reporter_phone:
                note_parts.append(f'هاتف المبلغ: {reporter_phone}')
        if rec['marital']:
            note_parts.append(f'الحالة الاجتماعية: {rec["marital"]}')
        if rec['education']:
            note_parts.append(f'التعليم: {rec["education"]}')
        if rec['employment']:
            note_parts.append(f'العمل: {rec["employment"]}')
        if rec['blood_type']:
            note_parts.append(f'زمرة الدم: {rec["blood_type"]}')
        if rec['chronic']:
            note_parts.append(f'أمراض مزمنة: {rec["chronic"]}')
        if rec['has_special_needs']:
            note_parts.append(f'احتياجات خاصة: {rec["special_needs_details"] or "نعم"}')
        if rec['arrest_year']:
            note_parts.append(f'سنة الاعتقال: {rec["arrest_year"]}')
        if rec['arrest_authority']:
            note_parts.append(f'الجهة: {rec["arrest_authority"]}')
        if rec['arrest_place']:
            note_parts.append(f'مكان الاحتجاز: {rec["arrest_place"]}')
        if rec['notes']:
            note_parts.append(f'ملاحظات: {rec["notes"]}')
        if 'family_book_number' in rec_keys and rec['family_book_number']:
            note_parts.append(f'رقم دفتر العائلة: {rec["family_book_number"]}')

        if note_parts:
            note_text = '\\n'.join(vcf_escape(p) for p in note_parts)
            vcf_lines.append(f'NOTE;CHARSET=UTF-8:{note_text}')

        vcf_lines.append('END:VCARD')
        vcf_lines.append('')

    vcf_content = '\r\n'.join(vcf_lines)
    buf = BytesIO(vcf_content.encode('utf-8'))
    buf.seek(0)

    filename = f'contacts_{int(time.time())}.vcf'
    return send_file(buf, mimetype='text/x-vcard',
                     as_attachment=True, download_name=filename)


# ---------------------------------------------------------------------------
# Export: kids missing birth dates
# ---------------------------------------------------------------------------
@app.route('/admin/export/kids_no_birthdate')
@admin_required
def export_kids_no_birthdate():
    """Export a text file listing people who have kids with no birth date, showing
    full name, phone, and kids' names."""
    db = get_db()
    rows = db.execute(
        "SELECT id, first_name, father_name, last_name, phone, children_data "
        "FROM records WHERE deleted_at IS NULL AND has_kids = 'yes' AND children_data IS NOT NULL AND children_data != '' AND children_data != '[]' "
        "ORDER BY id DESC"
    ).fetchall()

    lines = []
    lines.append("سجلات أطفال بدون تاريخ ميلاد")
    lines.append("=" * 50)
    lines.append("")
    count = 0
    for r in rows:
        try:
            children = json.loads(r['children_data']) if r['children_data'] else []
            _normalize_children(children)
        except (json.JSONDecodeError, TypeError):
            continue
        # Find children with no birth_year and no age
        kids_no_bd = [c for c in children if not c.get('birth_year') and not c.get('age')]
        if not kids_no_bd:
            continue
        count += 1
        full_name = ' '.join(filter(None, [r['first_name'], r['father_name'], r['last_name']]))
        phone = r['phone'] or '-'
        kid_names = ', '.join(c.get('name', '؟') for c in kids_no_bd)
        lines.append(f"#{r['id']}  {full_name}")
        lines.append(f"    الهاتف: {phone}")
        lines.append(f"    أطفال بدون تاريخ ميلاد: {kid_names}")
        lines.append("")

    lines.insert(3, f"العدد: {count}")
    lines.insert(4, "")

    content = '\n'.join(lines)
    response = make_response(content)
    response.headers['Content-Type'] = 'text/plain; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename=kids_no_birthdate_{int(time.time())}.txt'
    return response


# ---------------------------------------------------------------------------
# API endpoints for dynamic data
# ---------------------------------------------------------------------------
@app.route('/api/stats')
@admin_required
def api_stats():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM records WHERE deleted_at IS NULL").fetchone()[0]
    survivors = db.execute("SELECT COUNT(*) FROM records WHERE deleted_at IS NULL AND status='survivor'").fetchone()[0]
    enforced = db.execute("SELECT COUNT(*) FROM records WHERE deleted_at IS NULL AND status='enforced'").fetchone()[0]
    deceased = db.execute("SELECT COUNT(*) FROM records WHERE deleted_at IS NULL AND status='deceased'").fetchone()[0]
    return jsonify({
        'total': total, 'survivors': survivors,
        'enforced': enforced, 'deceased': deceased
    })


def serialize_record_for_picker(r, minor_threshold=18):
    """Serialize a database row to a dict with all PDF column values."""
    col_keys = [k for k, _ in PDF_COLUMNS]
    current_year = datetime.now().year

    # Helper to safely get a value from sqlite3.Row
    def _get(key, default=''):
        try:
            v = r[key]
            return v if v is not None else default
        except (IndexError, KeyError):
            return default

    rec = {}
    for k in col_keys:
        if k == 'children_summary':
            try:
                cd = _get('children_data', '')
                ch = json.loads(cd) if cd else []
                _normalize_children(ch)
                parts = []
                for c in ch:
                    name = c.get('name', '')
                    if c.get('birth_year'):
                        parts.append(f"{name}({c['birth_year']})")
                    elif c.get('age'):
                        parts.append(f"{name}(~{current_year - int(c['age'])})")
                    else:
                        parts.append(name)
                rec[k] = ', '.join(parts) if parts else '-'
            except Exception:
                rec[k] = '-'
        elif k == 'minors_summary':
            try:
                cd = _get('children_data', '')
                ch = json.loads(cd) if cd else []
                _normalize_children(ch)
                parts = []
                for c in ch:
                    age = None
                    if c.get('birth_year'):
                        try: age = current_year - int(c['birth_year'])
                        except (ValueError, TypeError): pass
                    elif c.get('age'):
                        try: age = int(c['age'])
                        except (ValueError, TypeError): pass
                    if age is not None and age < minor_threshold:
                        name = c.get('name', '')
                        if c.get('birth_year'):
                            parts.append(f"{name}({c['birth_year']})")
                        elif c.get('age'):
                            parts.append(f"{name}(~{current_year - int(c['age'])})")
                        else:
                            parts.append(name)
                rec[k] = ', '.join(parts) if parts else '-'
            except Exception:
                rec[k] = '-'
        elif k == 'kids_u13_names':
            try:
                cd = _get('children_data', '')
                ch = json.loads(cd) if cd else []
                _normalize_children(ch)
                names = []
                for c in ch:
                    age = None
                    if c.get('birth_year'):
                        try: age = current_year - int(c['birth_year'])
                        except (ValueError, TypeError): pass
                    elif c.get('age'):
                        try: age = int(c['age'])
                        except (ValueError, TypeError): pass
                    if age is not None and age < 13:
                        names.append(c.get('name', ''))
                rec[k] = ', '.join(names) if names else '-'
            except Exception:
                rec[k] = '-'
        elif k == 'kids_u13_ages':
            try:
                cd = _get('children_data', '')
                ch = json.loads(cd) if cd else []
                _normalize_children(ch)
                ages = []
                for c in ch:
                    age = None
                    if c.get('birth_year'):
                        try: age = current_year - int(c['birth_year'])
                        except (ValueError, TypeError): pass
                    elif c.get('age'):
                        try: age = int(c['age'])
                        except (ValueError, TypeError): pass
                    if age is not None and age < 13:
                        ages.append(str(age))
                rec[k] = ', '.join(ages) if ages else '-'
            except Exception:
                rec[k] = '-'
        elif k == 'status':
            rec[k] = STATUS_MAP.get(_get('status'), _get('status') or '-')
        elif k == 'gender':
            gmap = {'male': 'ذكر', 'female': 'أنثى'}
            rec[k] = gmap.get(_get('gender'), _get('gender') or '-')
        elif k == 'marital':
            mmap = dict(MARITAL_STATUSES)
            rec[k] = mmap.get(_get('marital'), _get('marital') or '-')
        elif k == 'case_type':
            cmap = dict(CASE_TYPES)
            rec[k] = cmap.get(_get('case_type'), _get('case_type') or '-')
        else:
            val = _get(k, '')
            rec[k] = str(val) if val is not None and val != '' else '-'
    return rec


@app.route('/api/search_records')
@admin_required
def api_search_records():
    """Search records by name for the PDF record picker."""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    db = get_db()
    s = f"%{q}%"
    rows = db.execute(
        "SELECT * FROM records WHERE deleted_at IS NULL AND (first_name LIKE ? OR father_name LIKE ? OR last_name LIKE ? "
        "OR (COALESCE(first_name,'') || ' ' || COALESCE(father_name,'') || ' ' || COALESCE(last_name,'')) LIKE ?) "
        "ORDER BY id DESC LIMIT 20", (s, s, s, s)
    ).fetchall()
    return jsonify([serialize_record_for_picker(r) for r in rows])


@app.route('/api/filtered_record_ids')
@admin_required
def api_filtered_record_ids():
    """Return filtered records with all fields for the PDF record picker."""
    db = get_db()
    conditions, params, _ = build_pdf_filter_conditions(request.args)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    rows = db.execute(
        f"SELECT * FROM records{where} ORDER BY id DESC LIMIT 500", params
    ).fetchall()

    # Post-filter by kids age range if specified
    if request.args.get('kids_age_from') or request.args.get('kids_age_to'):
        age_from = safe_int(request.args.get('kids_age_from'))
        age_to = safe_int(request.args.get('kids_age_to'))
        rows = [r for r in rows if record_has_child_in_age_range(r, age_from, age_to)]

    # Post-filter for custom minor age threshold
    api_minor_threshold = safe_int(request.args.get('minor_age_threshold'), 18)
    if request.args.get('has_kids_under_18') in ('yes', 'no') and api_minor_threshold != 18:
        if request.args['has_kids_under_18'] == 'yes':
            rows = [r for r in rows if record_has_child_in_age_range(r, 0, api_minor_threshold - 1)]
        else:
            rows = [r for r in rows if not record_has_child_in_age_range(r, 0, api_minor_threshold - 1)]

    return jsonify([serialize_record_for_picker(r, minor_threshold=api_minor_threshold) for r in rows])


# ---------------------------------------------------------------------------
# Volunteers management
# ---------------------------------------------------------------------------
@app.route('/admin/volunteers')
@admin_required
def admin_volunteers():
    db = get_db()
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '')
    role_filter = request.args.get('role', '')

    where = []
    params = []
    if search:
        where.append("(full_name LIKE ? OR phone LIKE ? OR national_id LIKE ? OR specialization LIKE ?)")
        params.extend([f'%{search}%'] * 4)
    if status_filter:
        where.append("status = ?")
        params.append(status_filter)
    if role_filter:
        where.append("role = ?")
        params.append(role_filter)

    where_clause = " AND ".join(where) if where else "1=1"
    volunteers = db.execute(
        f"""SELECT v.*,
            COALESCE(att.days, 0) as attendance_days,
            COALESCE(att.total_hours, 0) as attendance_hours,
            COALESCE(act.activity_count, 0) as activity_count
        FROM volunteers v
        LEFT JOIN (
            SELECT volunteer_id, COUNT(*) as days, SUM(hours) as total_hours
            FROM volunteer_attendance GROUP BY volunteer_id
        ) att ON v.id = att.volunteer_id
        LEFT JOIN (
            SELECT volunteer_id, COUNT(*) as activity_count
            FROM volunteer_activity_participants GROUP BY volunteer_id
        ) act ON v.id = act.volunteer_id
        WHERE {where_clause}
        ORDER BY v.created_at DESC""", params
    ).fetchall()

    total = db.execute("SELECT COUNT(*) FROM volunteers").fetchone()[0]
    active = db.execute("SELECT COUNT(*) FROM volunteers WHERE status='active'").fetchone()[0]

    return render_template('admin_volunteers.html',
                           volunteers=volunteers,
                           total=total,
                           active_count=active,
                           filters={'search': search, 'status': status_filter, 'role': role_filter})


@app.route('/admin/volunteer/add', methods=['GET', 'POST'])
@admin_required
def admin_volunteer_add():
    if request.method == 'POST':
        db = get_db()
        first_name = request.form.get('first_name', '').strip()
        father_name = request.form.get('father_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        mother_name = request.form.get('mother_name', '').strip()
        full_name = ' '.join(filter(None, [first_name, father_name, last_name]))
        db.execute("""
            INSERT INTO volunteers (full_name, first_name, last_name, father_name, mother_name,
                                    phone, email, national_id, province,
                                    address, role, specialization, join_date, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            full_name, first_name, last_name, father_name, mother_name,
            request.form.get('phone', '').strip(),
            request.form.get('email', '').strip(),
            request.form.get('national_id', '').strip(),
            request.form.get('province', ''),
            request.form.get('address', '').strip(),
            request.form.get('role', ''),
            request.form.get('specialization', '').strip(),
            request.form.get('join_date', ''),
            request.form.get('status', 'active'),
            request.form.get('notes', '').strip(),
        ))
        db.commit()
        log_audit('volunteer_create', 'volunteer', details=full_name)
        flash('تم إضافة المتطوع بنجاح', 'success')
        return redirect(url_for('admin_volunteers'))
    return render_template('admin_volunteer_form.html', volunteer=None)


@app.route('/admin/volunteer/<int:vid>/edit', methods=['GET', 'POST'])
@admin_required
def admin_volunteer_edit(vid):
    db = get_db()
    volunteer = db.execute("SELECT * FROM volunteers WHERE id=?", (vid,)).fetchone()
    if not volunteer:
        flash('المتطوع غير موجود', 'error')
        return redirect(url_for('admin_volunteers'))

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        father_name = request.form.get('father_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        mother_name = request.form.get('mother_name', '').strip()
        full_name = ' '.join(filter(None, [first_name, father_name, last_name]))
        db.execute("""
            UPDATE volunteers SET full_name=?, first_name=?, last_name=?, father_name=?, mother_name=?,
                                  phone=?, email=?, national_id=?, province=?,
                                  address=?, role=?, specialization=?, join_date=?, status=?,
                                  notes=?, updated_at=datetime('now','localtime')
            WHERE id=?
        """, (
            full_name, first_name, last_name, father_name, mother_name,
            request.form.get('phone', '').strip(),
            request.form.get('email', '').strip(),
            request.form.get('national_id', '').strip(),
            request.form.get('province', ''),
            request.form.get('address', '').strip(),
            request.form.get('role', ''),
            request.form.get('specialization', '').strip(),
            request.form.get('join_date', ''),
            request.form.get('status', 'active'),
            request.form.get('notes', '').strip(),
            vid,
        ))
        db.commit()
        log_audit('volunteer_edit', 'volunteer', vid)
        flash('تم تعديل بيانات المتطوع بنجاح', 'success')
        return redirect(url_for('admin_volunteers'))
    return render_template('admin_volunteer_form.html', volunteer=volunteer)


@app.route('/admin/volunteer/<int:vid>/delete', methods=['POST'])
@admin_required
def admin_volunteer_delete(vid):
    db = get_db()
    db.execute("DELETE FROM volunteers WHERE id=?", (vid,))
    db.commit()
    log_audit('volunteer_delete', 'volunteer', vid)
    flash('تم حذف المتطوع', 'success')
    return redirect(url_for('admin_volunteers'))


@app.route('/api/volunteers')
@admin_required
def api_volunteers_list():
    """API endpoint returning active volunteer names for filter dropdowns."""
    db = get_db()
    vols = db.execute(
        "SELECT id, full_name, role FROM volunteers WHERE status='active' ORDER BY full_name"
    ).fetchall()
    return jsonify([{'id': v['id'], 'name': v['full_name'], 'role': v['role']} for v in vols])


# ---------------------------------------------------------------------------
# Volunteer Evaluation System
# ---------------------------------------------------------------------------

@app.route('/admin/volunteer/<int:vid>/evaluation')
@admin_required
def admin_volunteer_evaluation(vid):
    db = get_db()
    volunteer = db.execute("SELECT * FROM volunteers WHERE id=?", (vid,)).fetchone()
    if not volunteer:
        flash('المتطوع غير موجود', 'error')
        return redirect(url_for('admin_volunteers'))

    # Attendance records
    attendance = db.execute(
        "SELECT * FROM volunteer_attendance WHERE volunteer_id=? ORDER BY date DESC", (vid,)
    ).fetchall()

    # Activities participated in
    activities = db.execute("""
        SELECT va.*, vap.role as participant_role, vap.notes as participant_notes
        FROM volunteer_activities va
        JOIN volunteer_activity_participants vap ON va.id = vap.activity_id
        WHERE vap.volunteer_id = ?
        ORDER BY va.date DESC
    """, (vid,)).fetchall()

    # Stats
    total_days = len(attendance)
    total_hours = sum(a['hours'] for a in attendance if a['hours'])
    total_activities = len(activities)

    # Monthly breakdown
    monthly = {}
    for a in attendance:
        month = a['date'][:7] if a['date'] else 'غير محدد'
        monthly.setdefault(month, {'days': 0, 'hours': 0})
        monthly[month]['days'] += 1
        monthly[month]['hours'] += a['hours'] or 0

    return render_template('admin_volunteer_evaluation.html',
                           volunteer=volunteer,
                           attendance=attendance,
                           activities=activities,
                           total_days=total_days,
                           total_hours=total_hours,
                           total_activities=total_activities,
                           monthly=monthly,
                           today=datetime.now().strftime('%Y-%m-%d'))


@app.route('/admin/volunteer/<int:vid>/attendance/add', methods=['POST'])
@admin_required
def admin_volunteer_attendance_add(vid):
    db = get_db()
    date = request.form.get('date', '').strip()
    check_in = request.form.get('check_in', '').strip()
    check_out = request.form.get('check_out', '').strip()
    notes = request.form.get('notes', '').strip()

    hours = 0
    if check_in and check_out:
        try:
            from datetime import datetime as dt
            t1 = dt.strptime(check_in, '%H:%M')
            t2 = dt.strptime(check_out, '%H:%M')
            diff = (t2 - t1).total_seconds() / 3600
            hours = round(diff, 1) if diff > 0 else 0
        except ValueError:
            pass

    db.execute("""
        INSERT INTO volunteer_attendance (volunteer_id, date, check_in, check_out, hours, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (vid, date, check_in, check_out, hours, notes))
    db.commit()
    flash('تم تسجيل الحضور', 'success')
    return redirect(url_for('admin_volunteer_evaluation', vid=vid))


@app.route('/admin/volunteer/attendance/<int:aid>/delete', methods=['POST'])
@admin_required
def admin_volunteer_attendance_delete(aid):
    db = get_db()
    att = db.execute("SELECT volunteer_id FROM volunteer_attendance WHERE id=?", (aid,)).fetchone()
    if att:
        db.execute("DELETE FROM volunteer_attendance WHERE id=?", (aid,))
        db.commit()
        flash('تم حذف سجل الحضور', 'success')
        return redirect(url_for('admin_volunteer_evaluation', vid=att['volunteer_id']))
    return redirect(url_for('admin_volunteers'))


@app.route('/admin/activities')
@admin_required
def admin_activities():
    db = get_db()
    activities = db.execute("""
        SELECT va.*, COUNT(vap.id) as participant_count
        FROM volunteer_activities va
        LEFT JOIN volunteer_activity_participants vap ON va.id = vap.activity_id
        GROUP BY va.id
        ORDER BY va.date DESC
    """).fetchall()
    return render_template('admin_activities.html', activities=activities)


@app.route('/admin/activity/add', methods=['GET', 'POST'])
@admin_required
def admin_activity_add():
    db = get_db()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        date = request.form.get('date', '').strip()
        description = request.form.get('description', '').strip()
        volunteer_ids = request.form.getlist('volunteer_ids')

        if not name:
            flash('اسم النشاط مطلوب', 'error')
            volunteers = db.execute("SELECT id, full_name FROM volunteers WHERE status='active' ORDER BY full_name").fetchall()
            return render_template('admin_activity_form.html', activity=None, volunteers=volunteers, selected_ids=[])

        cursor = db.execute("""
            INSERT INTO volunteer_activities (name, date, description) VALUES (?, ?, ?)
        """, (name, date, description))
        activity_id = cursor.lastrowid

        for v_id in volunteer_ids:
            try:
                db.execute("""
                    INSERT INTO volunteer_activity_participants (activity_id, volunteer_id)
                    VALUES (?, ?)
                """, (activity_id, int(v_id)))
            except Exception:
                pass

        db.commit()
        flash('تم إضافة النشاط بنجاح', 'success')
        return redirect(url_for('admin_activities'))

    volunteers = db.execute("SELECT id, full_name FROM volunteers WHERE status='active' ORDER BY full_name").fetchall()
    return render_template('admin_activity_form.html', activity=None, volunteers=volunteers, selected_ids=[])


@app.route('/admin/activity/<int:aid>/edit', methods=['GET', 'POST'])
@admin_required
def admin_activity_edit(aid):
    db = get_db()
    activity = db.execute("SELECT * FROM volunteer_activities WHERE id=?", (aid,)).fetchone()
    if not activity:
        flash('النشاط غير موجود', 'error')
        return redirect(url_for('admin_activities'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        date = request.form.get('date', '').strip()
        description = request.form.get('description', '').strip()
        volunteer_ids = request.form.getlist('volunteer_ids')

        db.execute("UPDATE volunteer_activities SET name=?, date=?, description=? WHERE id=?",
                   (name, date, description, aid))

        db.execute("DELETE FROM volunteer_activity_participants WHERE activity_id=?", (aid,))
        for v_id in volunteer_ids:
            try:
                db.execute("""
                    INSERT INTO volunteer_activity_participants (activity_id, volunteer_id)
                    VALUES (?, ?)
                """, (aid, int(v_id)))
            except Exception:
                pass

        db.commit()
        flash('تم تعديل النشاط بنجاح', 'success')
        return redirect(url_for('admin_activities'))

    volunteers = db.execute("SELECT id, full_name FROM volunteers WHERE status='active' ORDER BY full_name").fetchall()
    selected_ids = [p['volunteer_id'] for p in
                    db.execute("SELECT volunteer_id FROM volunteer_activity_participants WHERE activity_id=?", (aid,)).fetchall()]
    return render_template('admin_activity_form.html', activity=activity, volunteers=volunteers, selected_ids=selected_ids)


@app.route('/admin/activity/<int:aid>/delete', methods=['POST'])
@admin_required
def admin_activity_delete(aid):
    db = get_db()
    db.execute("DELETE FROM volunteer_activities WHERE id=?", (aid,))
    db.commit()
    flash('تم حذف النشاط', 'success')
    return redirect(url_for('admin_activities'))


# ---------------------------------------------------------------------------
# Members management
# ---------------------------------------------------------------------------
@app.route('/admin/members')
@admin_required
def admin_members():
    db = get_db()
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '')
    membership_type_filter = request.args.get('membership_type', '')

    where = []
    params = []
    if search:
        where.append("(full_name LIKE ? OR phone LIKE ? OR national_id LIKE ? OR membership_number LIKE ?)")
        params.extend([f'%{search}%'] * 4)
    if status_filter:
        where.append("status = ?")
        params.append(status_filter)
    if membership_type_filter:
        where.append("membership_type = ?")
        params.append(membership_type_filter)

    where_clause = " AND ".join(where) if where else "1=1"
    members = db.execute(
        f"SELECT * FROM members WHERE {where_clause} ORDER BY created_at DESC", params
    ).fetchall()

    total = db.execute("SELECT COUNT(*) FROM members").fetchone()[0]
    active = db.execute("SELECT COUNT(*) FROM members WHERE status='active'").fetchone()[0]

    return render_template('admin_members.html',
                           members=members,
                           total=total,
                           active_count=active,
                           filters={'search': search, 'status': status_filter,
                                    'membership_type': membership_type_filter})


@app.route('/admin/member/add', methods=['GET', 'POST'])
@admin_required
def admin_member_add():
    if request.method == 'POST':
        db = get_db()
        first_name = request.form.get('first_name', '').strip()
        father_name = request.form.get('father_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        mother_name = request.form.get('mother_name', '').strip()
        full_name = ' '.join(filter(None, [first_name, father_name, last_name]))
        db.execute("""
            INSERT INTO members (full_name, first_name, last_name, father_name, mother_name,
                                 phone, email, national_id,
                                 birth_year, gender, province, address,
                                 membership_type, membership_number, join_date, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            full_name, first_name, last_name, father_name, mother_name,
            request.form.get('phone', '').strip(),
            request.form.get('email', '').strip(),
            request.form.get('national_id', '').strip(),
            int(request.form.get('birth_year', 0) or 0),
            request.form.get('gender', ''),
            request.form.get('province', ''),
            request.form.get('address', '').strip(),
            request.form.get('membership_type', ''),
            request.form.get('membership_number', '').strip(),
            request.form.get('join_date', ''),
            request.form.get('status', 'active'),
            request.form.get('notes', '').strip(),
        ))
        db.commit()
        log_audit('member_create', 'member', details=full_name)
        flash('تم إضافة المنتسب بنجاح', 'success')
        return redirect(url_for('admin_members'))
    return render_template('admin_member_form.html', member=None)


@app.route('/admin/member/<int:mid>/edit', methods=['GET', 'POST'])
@admin_required
def admin_member_edit(mid):
    db = get_db()
    member = db.execute("SELECT * FROM members WHERE id=?", (mid,)).fetchone()
    if not member:
        flash('المنتسب غير موجود', 'error')
        return redirect(url_for('admin_members'))

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        father_name = request.form.get('father_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        mother_name = request.form.get('mother_name', '').strip()
        full_name = ' '.join(filter(None, [first_name, father_name, last_name]))
        db.execute("""
            UPDATE members SET full_name=?, first_name=?, last_name=?, father_name=?, mother_name=?,
                               phone=?, email=?, national_id=?,
                               birth_year=?, gender=?, province=?, address=?,
                               membership_type=?, membership_number=?, join_date=?, status=?,
                               notes=?, updated_at=datetime('now','localtime')
            WHERE id=?
        """, (
            full_name, first_name, last_name, father_name, mother_name,
            request.form.get('phone', '').strip(),
            request.form.get('email', '').strip(),
            request.form.get('national_id', '').strip(),
            int(request.form.get('birth_year', 0) or 0),
            request.form.get('gender', ''),
            request.form.get('province', ''),
            request.form.get('address', '').strip(),
            request.form.get('membership_type', ''),
            request.form.get('membership_number', '').strip(),
            request.form.get('join_date', ''),
            request.form.get('status', 'active'),
            request.form.get('notes', '').strip(),
            mid,
        ))
        db.commit()
        log_audit('member_edit', 'member', mid)
        flash('تم تعديل بيانات المنتسب بنجاح', 'success')
        return redirect(url_for('admin_members'))
    return render_template('admin_member_form.html', member=member)


@app.route('/admin/member/<int:mid>/delete', methods=['POST'])
@admin_required
def admin_member_delete(mid):
    db = get_db()
    db.execute("DELETE FROM members WHERE id=?", (mid,))
    db.commit()
    log_audit('member_delete', 'member', mid)
    flash('تم حذف المنتسب', 'success')
    return redirect(url_for('admin_members'))


@app.route('/api/members')
@admin_required
def api_members_list():
    """API endpoint returning active member names for filter dropdowns."""
    db = get_db()
    mems = db.execute(
        "SELECT id, full_name, membership_type FROM members WHERE status='active' ORDER BY full_name"
    ).fetchall()
    return jsonify([{'id': m['id'], 'name': m['full_name'], 'type': m['membership_type']} for m in mems])


# ---------------------------------------------------------------------------
# Member payments
# ---------------------------------------------------------------------------
MONTHLY_FEE = 15000       # Regular monthly fee (SYP)
FIRST_MONTH_FEE = 25000   # First month fee (SYP)


def compute_expected_fee(month_number):
    """Return the expected fee for a given month number.
    Month 1 = 25000, all others = 15000."""
    if month_number == 1:
        return FIRST_MONTH_FEE
    return MONTHLY_FEE


@app.route('/admin/member/<int:mid>/payments')
@admin_required
def admin_member_payments(mid):
    db = get_db()
    member = db.execute("SELECT * FROM members WHERE id=?", (mid,)).fetchone()
    if not member:
        flash('المنتسب غير موجود', 'error')
        return redirect(url_for('admin_members'))

    payments = db.execute(
        "SELECT * FROM member_payments WHERE member_id=? ORDER BY month_number ASC", (mid,)
    ).fetchall()

    # Summary stats
    total_paid = sum(p['amount'] for p in payments if p['status'] == 'paid')
    total_due = sum(p['amount'] for p in payments if p['status'] == 'unpaid')
    paid_count = sum(1 for p in payments if p['status'] == 'paid')
    unpaid_count = sum(1 for p in payments if p['status'] == 'unpaid')

    return render_template('admin_member_payments.html',
                           member=member, payments=payments,
                           total_paid=total_paid, total_due=total_due,
                           paid_count=paid_count, unpaid_count=unpaid_count,
                           MONTHLY_FEE=MONTHLY_FEE, FIRST_MONTH_FEE=FIRST_MONTH_FEE)


@app.route('/admin/member/<int:mid>/payments/generate', methods=['POST'])
@admin_required
def admin_member_generate_payments(mid):
    """Generate payment rows for N months starting from last recorded month."""
    db = get_db()
    member = db.execute("SELECT * FROM members WHERE id=?", (mid,)).fetchone()
    if not member:
        flash('المنتسب غير موجود', 'error')
        return redirect(url_for('admin_members'))

    num_months = int(request.form.get('num_months', 12))
    if num_months < 1 or num_months > 60:
        num_months = 12

    # Find the last month_number already generated
    last = db.execute(
        "SELECT MAX(month_number) as mx FROM member_payments WHERE member_id=?", (mid,)
    ).fetchone()
    start = (last['mx'] or 0) + 1

    for i in range(num_months):
        mn = start + i
        amount = compute_expected_fee(mn)
        db.execute("""
            INSERT INTO member_payments (member_id, amount, month_number, period_label, status)
            VALUES (?, ?, ?, ?, 'unpaid')
        """, (mid, amount, mn, f'الشهر {mn}'))
    db.commit()
    flash(f'تم توليد {num_months} شهر من الدفعات (من الشهر {start} إلى {start + num_months - 1})', 'success')
    return redirect(url_for('admin_member_payments', mid=mid))


@app.route('/admin/member/<int:mid>/payment/<int:pid>/toggle', methods=['POST'])
@admin_required
def admin_member_toggle_payment(mid, pid):
    """Toggle payment status between paid/unpaid."""
    db = get_db()
    payment = db.execute("SELECT * FROM member_payments WHERE id=? AND member_id=?", (pid, mid)).fetchone()
    if not payment:
        flash('الدفعة غير موجودة', 'error')
        return redirect(url_for('admin_member_payments', mid=mid))

    new_status = 'unpaid' if payment['status'] == 'paid' else 'paid'
    pay_date = datetime.now().strftime('%Y-%m-%d') if new_status == 'paid' else ''
    db.execute("UPDATE member_payments SET status=?, payment_date=? WHERE id=?",
               (new_status, pay_date, pid))
    db.commit()
    return redirect(url_for('admin_member_payments', mid=mid))


@app.route('/admin/member/<int:mid>/payment/<int:pid>/delete', methods=['POST'])
@admin_required
def admin_member_delete_payment(mid, pid):
    db = get_db()
    db.execute("DELETE FROM member_payments WHERE id=? AND member_id=?", (pid, mid))
    db.commit()
    flash('تم حذف الدفعة', 'success')
    return redirect(url_for('admin_member_payments', mid=mid))


# ---------------------------------------------------------------------------
# Record services
# ---------------------------------------------------------------------------
@app.route('/admin/record/<int:record_id>/service/add', methods=['POST'])
@admin_required
def admin_record_add_service(record_id):
    db = get_db()
    record = db.execute("SELECT id FROM records WHERE deleted_at IS NULL AND id=?", (record_id,)).fetchone()
    if not record:
        flash('السجل غير موجود', 'error')
        return redirect(url_for('admin_records'))

    db.execute("""
        INSERT INTO record_services (record_id, service_name, service_date, provider, notes)
        VALUES (?, ?, ?, ?, ?)
    """, (
        record_id,
        request.form.get('service_name', '').strip(),
        request.form.get('service_date', ''),
        request.form.get('provider', '').strip(),
        request.form.get('service_notes', '').strip(),
    ))
    db.commit()
    flash('تم إضافة الخدمة بنجاح', 'success')
    return redirect(url_for('admin_record_edit', record_id=record_id) + '#services-section')


@app.route('/admin/record/<int:record_id>/service/<int:sid>/delete', methods=['POST'])
@admin_required
def admin_record_delete_service(record_id, sid):
    db = get_db()
    db.execute("DELETE FROM record_services WHERE id=? AND record_id=?", (sid, record_id))
    db.commit()
    flash('تم حذف الخدمة', 'success')
    return redirect(url_for('admin_record_edit', record_id=record_id) + '#services-section')


@app.route('/admin/record/<int:record_id>/document/<int:doc_id>/delete', methods=['POST'])
@admin_required
def admin_record_delete_document(record_id, doc_id):
    db = get_db()
    db.execute("DELETE FROM record_documents WHERE id=? AND record_id=?", (doc_id, record_id))
    db.commit()
    log_audit('document_delete', 'record', record_id, {'document_id': doc_id})
    flash('تم حذف الوثيقة', 'success')
    return_to = request.form.get('return_to', '')
    if return_to == 'detail':
        return redirect(url_for('admin_record_detail', record_id=record_id) + '#documents-section')
    return redirect(url_for('admin_record_edit', record_id=record_id) + '#documents-section')


# ---------------------------------------------------------------------------
# Kids search
# ---------------------------------------------------------------------------
@app.route('/admin/kids')
@admin_required
def admin_kids_search():
    """Search children across all records by education level."""
    db = get_db()
    args = request.args
    edu_filter = args.get('education', '').strip()
    school_filter = args.get('school', '').strip()
    age_from = args.get('age_from', '')
    age_to = args.get('age_to', '')
    gender_filter = args.get('gender', '')

    current_year = datetime.now().year
    records = db.execute(
        "SELECT id, first_name, father_name, last_name, province, address, phone, children_data "
        "FROM records WHERE deleted_at IS NULL AND children_data IS NOT NULL AND children_data != '' AND children_data != '[]'"
    ).fetchall()

    kids = []
    for rec in records:
        try:
            children = json.loads(rec['children_data'])
        except (json.JSONDecodeError, TypeError):
            continue
        for child in children:
            if not child.get('name'):
                continue
            # Calculate age
            child_age = None
            if child.get('birth_year'):
                try:
                    child_age = current_year - int(child['birth_year'])
                except (ValueError, TypeError):
                    pass
            elif child.get('age'):
                try:
                    child_age = int(child['age'])
                except (ValueError, TypeError):
                    pass

            # Apply filters
            if edu_filter and edu_filter not in (child.get('education') or ''):
                continue
            if school_filter and school_filter.lower() not in (child.get('school') or child.get('university') or '').lower():
                continue
            if gender_filter and child.get('gender', '') != gender_filter:
                continue
            if age_from:
                try:
                    if child_age is None or child_age < int(age_from):
                        continue
                except ValueError:
                    pass
            if age_to:
                try:
                    if child_age is None or child_age > int(age_to):
                        continue
                except ValueError:
                    pass

            kids.append({
                'name': child.get('name', ''),
                'gender': child.get('gender', ''),
                'birth_year': child.get('birth_year', ''),
                'age': child_age,
                'education': child.get('education', ''),
                'school': child.get('school') or child.get('university') or '',
                'employment': child.get('employment') or child.get('job') or '',
                'health_notes': child.get('health_notes') or child.get('healthDetails') or '',
                'special_needs': child.get('special_needs', ''),
                'parent_id': rec['id'],
                'parent_name': ' '.join(filter(None, [rec['first_name'], rec['father_name'], rec['last_name']])),
                'parent_phone': rec['phone'] or '',
                'parent_province': rec['province'] or '',
            })

    # Collect unique education levels for filter dropdown
    all_edu = set()
    for rec in records:
        try:
            for c in json.loads(rec['children_data']):
                if c.get('education'):
                    all_edu.add(c['education'])
        except (json.JSONDecodeError, TypeError):
            pass
    edu_levels = sorted(all_edu)

    return render_template('admin_kids_search.html', kids=kids, edu_levels=edu_levels,
                           filters={'education': edu_filter, 'school': school_filter,
                                    'age_from': age_from, 'age_to': age_to, 'gender': gender_filter})


@app.route('/admin/kids/pdf')
@admin_required
def admin_kids_pdf():
    """Export kids search results as PDF."""
    # Reuse same logic
    db = get_db()
    args = request.args
    edu_filter = args.get('education', '').strip()
    school_filter = args.get('school', '').strip()
    age_from = args.get('age_from', '')
    age_to = args.get('age_to', '')
    gender_filter = args.get('gender', '')

    current_year = datetime.now().year
    records = db.execute(
        "SELECT id, first_name, father_name, last_name, province, phone, children_data "
        "FROM records WHERE deleted_at IS NULL AND children_data IS NOT NULL AND children_data != '' AND children_data != '[]'"
    ).fetchall()

    kids = []
    for rec in records:
        try:
            children = json.loads(rec['children_data'])
        except (json.JSONDecodeError, TypeError):
            continue
        for child in children:
            if not child.get('name'):
                continue
            child_age = None
            if child.get('birth_year'):
                try:
                    child_age = current_year - int(child['birth_year'])
                except (ValueError, TypeError):
                    pass
            elif child.get('age'):
                try:
                    child_age = int(child['age'])
                except (ValueError, TypeError):
                    pass
            if edu_filter and edu_filter not in (child.get('education') or ''):
                continue
            if school_filter and school_filter.lower() not in (child.get('school') or child.get('university') or '').lower():
                continue
            if gender_filter and child.get('gender', '') != gender_filter:
                continue
            if age_from:
                try:
                    if child_age is None or child_age < int(age_from):
                        continue
                except ValueError:
                    pass
            if age_to:
                try:
                    if child_age is None or child_age > int(age_to):
                        continue
                except ValueError:
                    pass
            kids.append({
                'name': child.get('name', ''),
                'gender': child.get('gender', ''),
                'age': child_age,
                'education': child.get('education', ''),
                'school': child.get('school') or child.get('university') or '',
                'parent_name': ' '.join(filter(None, [rec['first_name'], rec['father_name'], rec['last_name']])),
                'parent_phone': rec['phone'] or '',
                'parent_province': rec['province'] or '',
            })

    title = 'بحث الأطفال'
    if edu_filter:
        title += f' - {edu_filter}'
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    html = render_template('pdf_kids.html', kids=kids, title=title, filters=args, now=now)
    try:
        from weasyprint import HTML as WeasyHTML
        pdf_bytes = WeasyHTML(string=html, base_url=BASE_DIR).write_pdf()
        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'inline; filename=kids_search.pdf'
        return response
    except Exception:
        return html


@app.route('/admin/kids/excel')
@admin_required
def admin_kids_excel():
    """Export kids search results as Excel."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    db = get_db()
    args = request.args
    edu_filter = args.get('education', '').strip()
    school_filter = args.get('school', '').strip()
    age_from = args.get('age_from', '')
    age_to = args.get('age_to', '')
    gender_filter = args.get('gender', '')

    current_year = datetime.now().year
    records = db.execute(
        "SELECT id, first_name, father_name, last_name, province, phone, children_data "
        "FROM records WHERE deleted_at IS NULL AND children_data IS NOT NULL AND children_data != '' AND children_data != '[]'"
    ).fetchall()

    kids = []
    for rec in records:
        try:
            children = json.loads(rec['children_data'])
        except (json.JSONDecodeError, TypeError):
            continue
        for child in children:
            if not child.get('name'):
                continue
            child_age = None
            if child.get('birth_year'):
                try:
                    child_age = current_year - int(child['birth_year'])
                except (ValueError, TypeError):
                    pass
            elif child.get('age'):
                try:
                    child_age = int(child['age'])
                except (ValueError, TypeError):
                    pass
            if edu_filter and edu_filter not in (child.get('education') or ''):
                continue
            if school_filter and school_filter.lower() not in (child.get('school') or child.get('university') or '').lower():
                continue
            if gender_filter and child.get('gender', '') != gender_filter:
                continue
            if age_from:
                try:
                    if child_age is None or child_age < int(age_from):
                        continue
                except ValueError:
                    pass
            if age_to:
                try:
                    if child_age is None or child_age > int(age_to):
                        continue
                except ValueError:
                    pass
            kids.append({
                'name': child.get('name', ''),
                'gender': 'ذكر' if child.get('gender') == 'male' else 'أنثى' if child.get('gender') == 'female' else '',
                'age': child_age or '',
                'education': child.get('education', ''),
                'school': child.get('school') or child.get('university') or '',
                'parent_name': ' '.join(filter(None, [rec['first_name'], rec['father_name'], rec['last_name']])),
                'parent_phone': rec['phone'] or '',
                'province': rec['province'] or '',
            })

    wb = Workbook()
    ws = wb.active
    ws.title = 'أطفال'
    ws.sheet_view.rightToLeft = True

    headers = ['#', 'اسم الطفل', 'الجنس', 'العمر', 'التحصيل العلمي', 'الدراسة الحالية', 'اسم ولي الأمر', 'الهاتف', 'المحافظة']
    hfont = Font(bold=True, color='FFFFFF', size=11)
    hfill = PatternFill(start_color='1565C0', end_color='1565C0', fill_type='solid')
    thin_border = Border(
        left=Side(style='thin', color='CCCCCC'),
        right=Side(style='thin', color='CCCCCC'),
        bottom=Side(style='thin', color='CCCCCC'),
    )
    for i, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=i, value=h)
        cell.font = hfont
        cell.fill = hfill
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = thin_border

    for idx, kid in enumerate(kids, 1):
        ws.cell(row=idx+1, column=1, value=idx).border = thin_border
        ws.cell(row=idx+1, column=2, value=kid['name']).border = thin_border
        ws.cell(row=idx+1, column=3, value=kid['gender']).border = thin_border
        ws.cell(row=idx+1, column=4, value=kid['age']).border = thin_border
        ws.cell(row=idx+1, column=5, value=kid['education']).border = thin_border
        ws.cell(row=idx+1, column=6, value=kid['school']).border = thin_border
        ws.cell(row=idx+1, column=7, value=kid['parent_name']).border = thin_border
        ws.cell(row=idx+1, column=8, value=kid['parent_phone']).border = thin_border
        ws.cell(row=idx+1, column=9, value=kid['province']).border = thin_border

    widths = [5, 20, 8, 8, 18, 22, 25, 16, 14]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name='kids_search.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ---------------------------------------------------------------------------
# Custom lists
# ---------------------------------------------------------------------------
@app.route('/admin/lists')
@admin_required
def admin_custom_lists():
    db = get_db()
    lists = db.execute("""
        SELECT cl.*,
            (SELECT COUNT(*) FROM custom_list_items WHERE list_id=cl.id) +
            (SELECT COUNT(*) FROM custom_list_manual_items WHERE list_id=cl.id) as item_count
        FROM custom_lists cl
        ORDER BY cl.created_at DESC
    """).fetchall()
    return render_template('admin_custom_lists.html', lists=lists)


@app.route('/admin/list/create', methods=['POST'])
@admin_required
def admin_create_list():
    name = request.form.get('name', '').strip()
    desc = request.form.get('description', '').strip()
    if not name:
        flash('يرجى إدخال اسم القائمة', 'error')
        return redirect(url_for('admin_custom_lists'))
    db = get_db()
    db.execute("INSERT INTO custom_lists (name, description) VALUES (?, ?)", (name, desc))
    db.commit()
    flash(f'تم إنشاء القائمة: {name}', 'success')
    return redirect(url_for('admin_custom_lists'))


@app.route('/admin/lists/merge', methods=['POST'])
@admin_required
def admin_merge_lists():
    """Merge two custom lists into a new one."""
    list_a = int(request.form.get('list_a', 0) or 0)
    list_b = int(request.form.get('list_b', 0) or 0)
    merged_name = request.form.get('merged_name', '').strip()

    if not list_a or not list_b:
        flash('يرجى اختيار قائمتين', 'error')
        return redirect(url_for('admin_custom_lists'))
    if list_a == list_b:
        flash('لا يمكن دمج قائمة مع نفسها', 'error')
        return redirect(url_for('admin_custom_lists'))
    if not merged_name:
        flash('يرجى إدخال اسم للقائمة الجديدة', 'error')
        return redirect(url_for('admin_custom_lists'))

    db = get_db()
    la = db.execute("SELECT * FROM custom_lists WHERE id=?", (list_a,)).fetchone()
    lb = db.execute("SELECT * FROM custom_lists WHERE id=?", (list_b,)).fetchone()
    if not la or not lb:
        flash('إحدى القائمتين غير موجودة', 'error')
        return redirect(url_for('admin_custom_lists'))

    # Create new merged list
    desc = f'دمج: {la["name"]} + {lb["name"]}'
    db.execute("INSERT INTO custom_lists (name, description) VALUES (?, ?)", (merged_name, desc))
    new_lid = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Copy record items from both lists (avoid duplicates)
    items_a = db.execute("SELECT record_id FROM custom_list_items WHERE list_id=?", (list_a,)).fetchall()
    items_b = db.execute("SELECT record_id FROM custom_list_items WHERE list_id=?", (list_b,)).fetchall()
    seen_records = set()
    inserted = 0
    for item in items_a + items_b:
        rid = item['record_id']
        if rid not in seen_records:
            seen_records.add(rid)
            db.execute("INSERT INTO custom_list_items (list_id, record_id) VALUES (?, ?)", (new_lid, rid))
            inserted += 1

    # Copy manual items from both lists (avoid duplicates by full_name)
    manual_a = db.execute("SELECT * FROM custom_list_manual_items WHERE list_id=?", (list_a,)).fetchall()
    manual_b = db.execute("SELECT * FROM custom_list_manual_items WHERE list_id=?", (list_b,)).fetchall()
    seen_manual = set()
    for item in manual_a + manual_b:
        key = (item['full_name'] or '').strip()
        if key and key not in seen_manual:
            seen_manual.add(key)
            db.execute("""INSERT INTO custom_list_manual_items
                (list_id, full_name, phone, father_name, national_id, province, address, notes)
                VALUES (?,?,?,?,?,?,?,?)""",
                (new_lid, item['full_name'], item['phone'] or '', item['father_name'] or '',
                 item['national_id'] or '', item['province'] or '', item['address'] or '', item['notes'] or ''))

    db.commit()
    total = inserted + len(seen_manual)
    log_audit('list_merge', 'custom_list', new_lid, f'Merged lists {list_a}+{list_b} -> {total} items')
    flash(f'تم دمج القائمتين في "{merged_name}" ({total} سجل)', 'success')
    return redirect(url_for('admin_custom_list_detail', lid=new_lid))


@app.route('/admin/list/<int:lid>')
@admin_required
def admin_custom_list_detail(lid):
    db = get_db()
    clist = db.execute("SELECT * FROM custom_lists WHERE id=?", (lid,)).fetchone()
    if not clist:
        flash('القائمة غير موجودة', 'error')
        return redirect(url_for('admin_custom_lists'))

    items = db.execute("""
        SELECT r.*, cli.id as item_id, cli.added_at
        FROM custom_list_items cli
        JOIN records r ON cli.record_id = r.id
        WHERE cli.list_id = ?
        ORDER BY cli.added_at DESC
    """, (lid,)).fetchall()

    manual_items = db.execute(
        "SELECT * FROM custom_list_manual_items WHERE list_id=? ORDER BY added_at DESC", (lid,)
    ).fetchall()

    return render_template('admin_custom_list_detail.html',
                           clist=clist, items=items, manual_items=manual_items,
                           PDF_COLUMNS=PDF_COLUMNS,
                           PROVINCES=PROVINCES,
                           MARITAL_STATUSES=MARITAL_STATUSES,
                           STATUS_CHOICES=[('survivor', 'ناجٍ'), ('enforced', 'مغيّب قسرياً'), ('deceased', 'متوفى')])


@app.route('/admin/list/<int:lid>/pdf', methods=['GET', 'POST'])
@admin_required
def admin_custom_list_pdf(lid):
    db = get_db()
    clist = db.execute("SELECT * FROM custom_lists WHERE id=?", (lid,)).fetchone()
    if not clist:
        flash('القائمة غير موجودة', 'error')
        return redirect(url_for('admin_custom_lists'))

    items = db.execute("""
        SELECT r.*, cli.added_at
        FROM custom_list_items cli
        JOIN records r ON cli.record_id = r.id
        WHERE cli.list_id = ?
        ORDER BY cli.added_at ASC
    """, (lid,)).fetchall()

    manual_items = db.execute(
        "SELECT * FROM custom_list_manual_items WHERE list_id=? ORDER BY added_at ASC", (lid,)
    ).fetchall()

    # Determine selected columns
    args = request.form if request.method == 'POST' else request.args
    selected_cols = args.getlist('cols')
    col_map = dict(PDF_COLUMNS)
    if selected_cols:
        pdf_cols = [(k, col_map[k]) for k in selected_cols if k in col_map]
    else:
        pdf_cols = [('first_name', 'الاسم'), ('father_name', 'الأب'), ('last_name', 'الكنية'),
                    ('phone', 'الهاتف'), ('status', 'الحالة'), ('notes', 'ملاحظات')]

    # Logo
    logo_b64 = ''
    logo_path = os.path.join(BASE_DIR, 'static', 'img', 'logo.jpg')
    if os.path.exists(logo_path):
        with open(logo_path, 'rb') as f:
            logo_b64 = base64.b64encode(f.read()).decode()

    current_year = datetime.now().year
    total_count = len(items) + len(manual_items)
    html = render_template('pdf_custom_list.html',
                           clist=clist, items=items, manual_items=manual_items,
                           total_count=total_count, logo_b64=logo_b64,
                           pdf_cols=pdf_cols, current_year=current_year,
                           STATUS_MAP=STATUS_MAP,
                           MARITAL_STATUSES=MARITAL_STATUSES,
                           CASE_TYPES=CASE_TYPES,
                           EVIDENCE_LEVELS=EVIDENCE_LEVELS,
                           VERIFICATION_STATUSES=VERIFICATION_STATUSES,
                           DIGITAL_EVIDENCE_TYPES=DIGITAL_EVIDENCE_TYPES,
                           CIVIL_REGISTRY_STATUSES=CIVIL_REGISTRY_STATUSES,
                           now=datetime.now().strftime('%Y-%m-%d'))

    from weasyprint import HTML
    pdf_bytes = HTML(string=html, base_url=BASE_DIR).write_pdf()

    response = make_response(pdf_bytes)
    encoded_name = quote(f"list_{clist['name']}.pdf")
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f"inline; filename=list_{lid}.pdf; filename*=UTF-8''{encoded_name}"
    return response


@app.route('/admin/list/<int:lid>/excel', methods=['GET', 'POST'])
@admin_required
def admin_custom_list_excel(lid):
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter

    db = get_db()
    clist = db.execute("SELECT * FROM custom_lists WHERE id=?", (lid,)).fetchone()
    if not clist:
        flash('القائمة غير موجودة', 'error')
        return redirect(url_for('admin_custom_lists'))

    items = db.execute("""
        SELECT r.*, cli.added_at
        FROM custom_list_items cli
        JOIN records r ON cli.record_id = r.id
        WHERE cli.list_id = ?
        ORDER BY cli.added_at ASC
    """, (lid,)).fetchall()

    manual_items = db.execute(
        "SELECT * FROM custom_list_manual_items WHERE list_id=? ORDER BY added_at ASC", (lid,)
    ).fetchall()

    # Determine selected columns
    args = request.form if request.method == 'POST' else request.args
    selected_cols = args.getlist('cols')
    col_map = dict(PDF_COLUMNS)
    if selected_cols:
        pdf_cols = [(k, col_map[k]) for k in selected_cols if k in col_map]
    else:
        pdf_cols = [('first_name', 'الاسم'), ('father_name', 'الأب'), ('last_name', 'الكنية'),
                    ('phone', 'الهاتف'), ('status', 'الحالة'), ('notes', 'ملاحظات')]

    current_year = datetime.now().year

    wb = Workbook()
    ws = wb.active
    ws.title = clist['name'][:31]
    ws.sheet_view.rightToLeft = True

    header_fill = PatternFill(start_color='1a5276', end_color='1a5276', fill_type='solid')
    header_font = Font(bold=True, size=11, color='FFFFFF')
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    wrap_align = Alignment(horizontal='right', vertical='center', wrap_text=True)

    # Header row: # + selected columns
    headers = ['#'] + [label for _, label in pdf_cols]
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = thin_border

    row_num = 2
    counter = 1

    # Manual items first
    manual_col_map = {
        'first_name': 'full_name', 'father_name': 'father_name',
        'mother_name': 'mother_name', 'national_id': 'national_id',
        'family_book_number': 'family_book_number',
        'phone': 'phone', 'contact_phone': 'phone',
        'province': 'province', 'address': 'address',
        'kids_count': 'kids_count', 'marital': 'marital',
        'status': 'status', 'notes': 'notes',
    }
    mmap = dict(MARITAL_STATUSES)
    for m in manual_items:
        cell = ws.cell(row=row_num, column=1, value=counter)
        cell.alignment = wrap_align
        cell.border = thin_border
        for col_idx, (col_key, _) in enumerate(pdf_cols, 2):
            if col_key in manual_col_map:
                raw = m[manual_col_map[col_key]]
                if col_key == 'status':
                    val = STATUS_MAP.get(raw, raw or '')
                elif col_key == 'marital':
                    val = mmap.get(raw, raw or '')
                elif col_key == 'kids_count':
                    val = raw if raw else ''
                else:
                    val = raw or ''
            else:
                val = ''
            cell = ws.cell(row=row_num, column=col_idx, value=val)
            cell.alignment = wrap_align
            cell.border = thin_border
        row_num += 1
        counter += 1

    # Record items using _format_cell_value
    for r in items:
        cell = ws.cell(row=row_num, column=1, value=counter)
        cell.alignment = wrap_align
        cell.border = thin_border
        for col_idx, (col_key, _) in enumerate(pdf_cols, 2):
            val = _format_cell_value(r, col_key, current_year)
            cell = ws.cell(row=row_num, column=col_idx, value=val)
            cell.alignment = wrap_align
            cell.border = thin_border
        row_num += 1
        counter += 1

    # Auto-fit widths
    ws.column_dimensions['A'].width = 6
    for i in range(len(pdf_cols)):
        ws.column_dimensions[get_column_letter(i + 2)].width = 18

    ws.freeze_panes = 'A2'

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f'list_{lid}_{int(time.time())}.xlsx'
    return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=filename)


@app.route('/admin/list/<int:lid>/vcf', methods=['GET', 'POST'])
@admin_required
def admin_custom_list_vcf(lid):
    """Export custom list contacts as a .vcf file for Android import."""
    db = get_db()
    clist = db.execute("SELECT * FROM custom_lists WHERE id=?", (lid,)).fetchone()
    if not clist:
        flash('القائمة غير موجودة', 'error')
        return redirect(url_for('admin_custom_lists'))

    items = db.execute("""
        SELECT r.*
        FROM custom_list_items cli
        JOIN records r ON cli.record_id = r.id
        WHERE cli.list_id = ?
        ORDER BY cli.added_at ASC
    """, (lid,)).fetchall()

    manual_items = db.execute(
        "SELECT * FROM custom_list_manual_items WHERE list_id=? ORDER BY added_at ASC", (lid,)
    ).fetchall()

    status_map = {'survivor': 'ناجٍ', 'enforced': 'مغيّب قسراً', 'deceased': 'متوفى'}

    def vcf_escape(text):
        """Escape special characters in vCard text values and strip newlines."""
        if not text:
            return ''
        text = text.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ')
        return text.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')

    vcf_lines = []

    # Manual items
    for mi in manual_items:
        full_name = vcf_escape((mi['full_name'] or '').strip())
        if not full_name:
            continue
        vcf_lines.append('BEGIN:VCARD')
        vcf_lines.append('VERSION:2.1')
        vcf_lines.append(f'FN;CHARSET=UTF-8:{full_name}')
        vcf_lines.append(f'N;CHARSET=UTF-8:{full_name};;;;')
        phone = (mi['phone'] or '').strip()
        if phone:
            vcf_lines.append(f'TEL;CELL:{phone}')
        note_parts = []
        if mi['status']:
            note_parts.append(f'الحالة: {status_map.get(mi["status"], mi["status"])}')
        if mi['notes']:
            note_parts.append(f'ملاحظات: {mi["notes"]}')
        if note_parts:
            note_text = '\\n'.join(vcf_escape(p) for p in note_parts)
            vcf_lines.append(f'NOTE;CHARSET=UTF-8:{note_text}')
        vcf_lines.append('END:VCARD')
        vcf_lines.append('')

    # Record items (same logic as main VCF export)
    for rec in items:
        first = vcf_escape(rec['first_name'] or '')
        father = vcf_escape(rec['father_name'] or '')
        last = vcf_escape(rec['last_name'] or '')
        full_name = ' '.join(part for part in [first, father, last] if part)
        if not full_name:
            continue

        vcf_lines.append('BEGIN:VCARD')
        vcf_lines.append('VERSION:2.1')
        vcf_lines.append(f'FN;CHARSET=UTF-8:{full_name}')
        vcf_lines.append(f'N;CHARSET=UTF-8:{last};{first};{father};;')

        phone = (rec['phone'] or '').strip()
        spouse_phone = (rec['spouse_phone'] or '').strip()
        guardian_phone = (rec['guardian_phone'] or '').strip()
        reporter_phone = (rec['reporter_phone'] or '').strip()

        if phone:
            vcf_lines.append(f'TEL;CELL:{phone}')
        if spouse_phone:
            vcf_lines.append(f'TEL;HOME:{spouse_phone}')
        if guardian_phone:
            vcf_lines.append(f'TEL;WORK:{guardian_phone}')
        if reporter_phone:
            vcf_lines.append(f'TEL;VOICE:{reporter_phone}')

        if rec['profession']:
            vcf_lines.append(f'TITLE;CHARSET=UTF-8:{vcf_escape(rec["profession"])}')

        address = vcf_escape((rec['address'] or '').strip())
        province = vcf_escape((rec['province'] or '').strip())
        if address or province:
            vcf_lines.append(f'ADR;HOME;CHARSET=UTF-8:;;{address};;{province};;')

        birth_year = rec['birth_year'] or ''
        birth_month = rec['birth_month'] or ''
        birth_day = rec['birth_day'] or ''
        if birth_year and birth_month and birth_day:
            try:
                bday = f'{int(birth_year):04d}-{int(birth_month):02d}-{int(birth_day):02d}'
                vcf_lines.append(f'BDAY:{bday}')
            except (ValueError, TypeError):
                pass

        note_parts = []
        status_label = status_map.get(rec['status'], rec['status'] or '')
        if status_label:
            note_parts.append(f'الحالة: {status_label}')
        if rec['national_id']:
            note_parts.append(f'الرقم الوطني: {rec["national_id"]}')
        if rec['mother_name']:
            note_parts.append(f'الأم: {rec["mother_name"]}')
        if rec['spouse_name']:
            note_parts.append(f'الزوج/ة: {rec["spouse_name"]}')
        if rec['notes']:
            note_parts.append(f'ملاحظات: {rec["notes"]}')
        if note_parts:
            note_text = '\\n'.join(vcf_escape(p) for p in note_parts)
            vcf_lines.append(f'NOTE;CHARSET=UTF-8:{note_text}')

        vcf_lines.append('END:VCARD')
        vcf_lines.append('')

    vcf_content = '\r\n'.join(vcf_lines)
    buf = BytesIO(vcf_content.encode('utf-8'))
    buf.seek(0)

    filename = f'list_{lid}_contacts_{int(time.time())}.vcf'
    return send_file(buf, mimetype='text/x-vcard',
                     as_attachment=True, download_name=filename)


@app.route('/admin/list/<int:lid>/whatsapp', methods=['POST'])
@admin_required
def admin_list_whatsapp(lid):
    """Launch Playwright automation to create a WhatsApp group from list contacts."""
    data = request.get_json()
    group_name = data.get('group_name', '').strip()
    phones = data.get('phones', [])

    if not phones:
        return jsonify({'error': 'لا توجد أرقام هواتف'}), 400
    if not group_name:
        return jsonify({'error': 'يرجى إدخال اسم المجموعة'}), 400

    try:
        from whatsapp_group import create_whatsapp_group
        import threading

        # Run in a thread so the HTTP request doesn't block
        def run_automation():
            create_whatsapp_group(group_name, phones, headless=False)

        t = threading.Thread(target=run_automation, daemon=True)
        t.start()
        return jsonify({'ok': True, 'message': f'جاري إنشاء المجموعة مع {len(phones)} رقم...'})
    except ImportError:
        return jsonify({'error': 'Playwright غير مثبت. قم بتشغيل: pip install playwright && playwright install chromium'}), 500
    except Exception as e:
        app.logger.error(f"WhatsApp group creation error: {e}")
        return jsonify({'error': 'حدث خطأ داخلي أثناء إنشاء المجموعة'}), 500


@app.route('/admin/list/<int:lid>/delete', methods=['POST'])
@admin_required
def admin_delete_list(lid):
    db = get_db()
    db.execute("DELETE FROM custom_list_items WHERE list_id=?", (lid,))
    db.execute("DELETE FROM custom_list_manual_items WHERE list_id=?", (lid,))
    db.execute("DELETE FROM custom_lists WHERE id=?", (lid,))
    db.commit()
    flash('تم حذف القائمة', 'success')
    return redirect(url_for('admin_custom_lists'))


@app.route('/api/export_to_list', methods=['POST'])
@admin_required
def api_export_to_list():
    """Bulk-add filtered records to an existing or new custom list.

    Accepts either:
      - record_ids: explicit list of IDs (legacy, from visible table)
      - filters + limit: re-query the DB to get ALL matching IDs
    """
    data = request.get_json() or {}
    list_id = data.get('list_id')
    list_name = data.get('list_name', '').strip()
    record_ids = data.get('record_ids', [])
    filters = data.get('filters')
    limit = data.get('limit', 0)

    # If no explicit record_ids, query the DB for matching IDs
    if not record_ids:
        if filters is None:
            filters = {}
        db = get_db()
        conditions, params = _build_record_filter_conditions(filters)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""

        # Check if post-filtering is needed (kids age range, custom minor threshold)
        kids_age_from = safe_int(filters.get('kids_age_from'))
        kids_age_to = safe_int(filters.get('kids_age_to'))
        kids_max_age = safe_int(filters.get('kids_max_age'))
        minor_threshold = safe_int(filters.get('minor_age_threshold'), 18)
        needs_kids_post = kids_age_from is not None or kids_age_to is not None or kids_max_age is not None
        needs_minor_post = filters.get('has_kids_under_18') in ('yes', 'no') and minor_threshold != 18

        if needs_kids_post or needs_minor_post:
            # Fetch full records for post-filtering
            rows = db.execute(f"SELECT * FROM records{where} ORDER BY id DESC", params).fetchall()
            if kids_age_from is not None or kids_age_to is not None:
                rows = [r for r in rows if record_has_child_in_age_range(r, kids_age_from, kids_age_to)]
            if kids_max_age is not None:
                rows = [r for r in rows if record_has_child_in_age_range(r, 0, kids_max_age)]
            if needs_minor_post:
                if filters.get('has_kids_under_18') == 'yes':
                    rows = [r for r in rows if record_has_child_in_age_range(r, 0, minor_threshold - 1)]
                elif filters.get('has_kids_under_18') == 'no':
                    rows = [r for r in rows if not record_has_child_in_age_range(r, 0, minor_threshold - 1)]
            if limit and int(limit) > 0:
                rows = rows[:int(limit)]
            record_ids = [row['id'] for row in rows]
        else:
            sql = f"SELECT id FROM records{where} ORDER BY id DESC"
            if limit and int(limit) > 0:
                sql += f" LIMIT {int(limit)}"
            rows = db.execute(sql, params).fetchall()
            record_ids = [row['id'] for row in rows]

    if not record_ids:
        return jsonify({'error': 'لا توجد سجلات'}), 400

    db = get_db()
    if list_name and not list_id:
        # Create new list
        cur = db.execute("INSERT INTO custom_lists (name, description) VALUES (?, ?)",
                         (list_name, ''))
        list_id = cur.lastrowid
    elif not list_id:
        return jsonify({'error': 'يرجى اختيار قائمة أو إدخال اسم جديد'}), 400

    added = 0
    for rid in record_ids:
        try:
            db.execute("INSERT INTO custom_list_items (list_id, record_id) VALUES (?, ?)",
                       (list_id, rid))
            added += 1
        except sqlite3.IntegrityError:
            pass
    db.commit()
    return jsonify({'ok': True, 'added': added, 'list_id': list_id})


@app.route('/api/custom_lists_json')
@admin_required
def api_custom_lists_json():
    """Return all custom lists as JSON for the export-to-list modal."""
    db = get_db()
    lists = db.execute("""
        SELECT cl.id, cl.name,
            (SELECT COUNT(*) FROM custom_list_items WHERE list_id=cl.id) +
            (SELECT COUNT(*) FROM custom_list_manual_items WHERE list_id=cl.id) as item_count
        FROM custom_lists cl ORDER BY cl.created_at DESC
    """).fetchall()
    return jsonify([{'id': l['id'], 'name': l['name'], 'count': l['item_count']} for l in lists])


@app.route('/api/add_record_to_list', methods=['POST'])
@admin_required
def api_add_record_to_list():
    """Add a single record to a custom list via AJAX."""
    data = request.get_json()
    record_id = data.get('record_id')
    list_id = data.get('list_id')
    new_list_name = (data.get('new_list_name') or '').strip()

    if not record_id:
        return jsonify({'success': False, 'error': 'سجل غير محدد'}), 400

    db = get_db()

    # Create new list if requested
    if new_list_name:
        cursor = db.execute("INSERT INTO custom_lists (name) VALUES (?)", (new_list_name,))
        db.commit()
        list_id = cursor.lastrowid
    elif not list_id:
        return jsonify({'success': False, 'error': 'قائمة غير محددة'}), 400

    try:
        db.execute("INSERT INTO custom_list_items (list_id, record_id) VALUES (?, ?)",
                   (list_id, record_id))
        db.commit()
        list_name = db.execute("SELECT name FROM custom_lists WHERE id=?", (list_id,)).fetchone()
        return jsonify({'success': True, 'list_name': list_name['name'] if list_name else '', 'list_id': list_id})
    except sqlite3.IntegrityError:
        list_name = db.execute("SELECT name FROM custom_lists WHERE id=?", (list_id,)).fetchone()
        return jsonify({'success': False, 'error': 'السجل موجود مسبقاً في القائمة', 'list_name': list_name['name'] if list_name else ''})


@app.route('/admin/list/<int:lid>/add', methods=['POST'])
@admin_required
def admin_list_add_record(lid):
    record_id = request.form.get('record_id', type=int)
    if not record_id:
        flash('يرجى اختيار سجل', 'error')
        return redirect(url_for('admin_custom_list_detail', lid=lid))
    db = get_db()
    try:
        db.execute("INSERT INTO custom_list_items (list_id, record_id) VALUES (?, ?)",
                   (lid, record_id))
        db.commit()
        flash('تم إضافة السجل للقائمة', 'success')
    except sqlite3.IntegrityError:
        flash('السجل موجود مسبقاً في هذه القائمة', 'error')
    return redirect(url_for('admin_custom_list_detail', lid=lid))


@app.route('/admin/list/<int:lid>/remove/<int:item_id>', methods=['POST'])
@admin_required
def admin_list_remove_record(lid, item_id):
    db = get_db()
    db.execute("DELETE FROM custom_list_items WHERE id=? AND list_id=?", (item_id, lid))
    db.commit()
    flash('تم حذف السجل من القائمة', 'success')
    return redirect(url_for('admin_custom_list_detail', lid=lid))


@app.route('/admin/list/<int:lid>/add_manual', methods=['POST'])
@admin_required
def admin_list_add_manual(lid):
    name = request.form.get('full_name', '').strip()
    if not name:
        flash('يرجى إدخال الاسم', 'error')
        return redirect(url_for('admin_custom_list_detail', lid=lid))
    db = get_db()
    db.execute("""
        INSERT INTO custom_list_manual_items (
            list_id, full_name, father_name, mother_name,
            national_id, family_book_number, phone, province,
            address, kids_count, marital, status, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        lid, name,
        request.form.get('father_name', '').strip(),
        request.form.get('mother_name', '').strip(),
        request.form.get('national_id', '').strip(),
        request.form.get('family_book_number', '').strip(),
        request.form.get('phone', '').strip(),
        request.form.get('province', '').strip(),
        request.form.get('address', '').strip(),
        int(request.form.get('kids_count', 0) or 0),
        request.form.get('marital', '').strip(),
        request.form.get('status', '').strip(),
        request.form.get('notes', '').strip(),
    ))
    db.commit()
    flash(f'تم إضافة: {name}', 'success')
    return redirect(url_for('admin_custom_list_detail', lid=lid))


@app.route('/admin/list/<int:lid>/remove_manual/<int:mid>', methods=['POST'])
@admin_required
def admin_list_remove_manual(lid, mid):
    db = get_db()
    db.execute("DELETE FROM custom_list_manual_items WHERE id=? AND list_id=?", (mid, lid))
    db.commit()
    flash('تم الحذف من القائمة', 'success')
    return redirect(url_for('admin_custom_list_detail', lid=lid))


@app.route('/admin/list/<int:lid>/add_volunteer', methods=['POST'])
@admin_required
def admin_list_add_volunteer(lid):
    vid = request.form.get('volunteer_id', type=int)
    if not vid:
        flash('يرجى اختيار متطوع', 'error')
        return redirect(url_for('admin_custom_list_detail', lid=lid))
    db = get_db()
    v = db.execute("SELECT full_name, phone FROM volunteers WHERE id=?", (vid,)).fetchone()
    if not v:
        flash('المتطوع غير موجود', 'error')
        return redirect(url_for('admin_custom_list_detail', lid=lid))
    db.execute("""
        INSERT INTO custom_list_manual_items (list_id, full_name, phone, notes)
        VALUES (?, ?, ?, ?)
    """, (lid, v['full_name'], v['phone'] or '', 'متطوع'))
    db.commit()
    flash(f"تم إضافة المتطوع: {v['full_name']}", 'success')
    return redirect(url_for('admin_custom_list_detail', lid=lid))


@app.route('/admin/list/<int:lid>/add_member', methods=['POST'])
@admin_required
def admin_list_add_member(lid):
    mid = request.form.get('member_id', type=int)
    if not mid:
        flash('يرجى اختيار منتسب', 'error')
        return redirect(url_for('admin_custom_list_detail', lid=lid))
    db = get_db()
    m = db.execute("SELECT full_name, father_name, phone FROM members WHERE id=?", (mid,)).fetchone()
    if not m:
        flash('المنتسب غير موجود', 'error')
        return redirect(url_for('admin_custom_list_detail', lid=lid))
    name = f"{m['full_name']} {m['father_name'] or ''}".strip()
    db.execute("""
        INSERT INTO custom_list_manual_items (list_id, full_name, phone, notes)
        VALUES (?, ?, ?, ?)
    """, (lid, name, m['phone'] or '', 'منتسب'))
    db.commit()
    flash(f'تم إضافة المنتسب: {name}', 'success')
    return redirect(url_for('admin_custom_list_detail', lid=lid))


@app.route('/api/search_for_list')
@admin_required
def api_search_for_list():
    """Search records, volunteers, and members for adding to custom lists."""
    q = request.args.get('q', '').strip()
    source = request.args.get('source', 'all')  # all, records, volunteers, members
    if len(q) < 2:
        return jsonify([])
    db = get_db()
    term = f'%{q}%'
    results = []

    # Search records
    if source in ('all', 'records'):
        rows = db.execute("""
            SELECT id, first_name, father_name, last_name, phone, status, province
            FROM records
            WHERE deleted_at IS NULL AND (first_name LIKE ? OR father_name LIKE ? OR last_name LIKE ?
                  OR national_id LIKE ? OR phone LIKE ?
                  OR (COALESCE(first_name,'') || ' ' || COALESCE(father_name,'') || ' ' || COALESCE(last_name,'')) LIKE ?)
            ORDER BY first_name LIMIT 15
        """, (term, term, term, term, term, term)).fetchall()
        for r in rows:
            status_ar = STATUS_MAP.get(r['status'], r['status'] or '')
            results.append({
                'id': r['id'],
                'source': 'record',
                'name': f"{r['first_name']} {r['father_name'] or ''} {r['last_name'] or ''}".strip(),
                'phone': r['phone'] or '',
                'detail': f"{status_ar} — {r['province'] or ''}",
            })

    # Search volunteers
    if source in ('all', 'volunteers'):
        vols = db.execute("""
            SELECT id, full_name, phone, role, specialization, province
            FROM volunteers
            WHERE full_name LIKE ? OR phone LIKE ? OR national_id LIKE ? OR specialization LIKE ?
            ORDER BY full_name LIMIT 15
        """, (term, term, term, term)).fetchall()
        for v in vols:
            detail_parts = [v['role'] or '', v['specialization'] or '', v['province'] or '']
            detail = ' — '.join(p for p in detail_parts if p)
            results.append({
                'id': v['id'],
                'source': 'volunteer',
                'name': v['full_name'],
                'phone': v['phone'] or '',
                'detail': detail or 'متطوع',
            })

    # Search members
    if source in ('all', 'members'):
        mems = db.execute("""
            SELECT id, full_name, father_name, phone, membership_type, membership_number, province
            FROM members
            WHERE full_name LIKE ? OR phone LIKE ? OR national_id LIKE ? OR membership_number LIKE ?
                  OR (COALESCE(full_name,'') || ' ' || COALESCE(father_name,'')) LIKE ?
            ORDER BY full_name LIMIT 15
        """, (term, term, term, term, term)).fetchall()
        for m in mems:
            detail_parts = [m['membership_type'] or '', m['membership_number'] or '', m['province'] or '']
            detail = ' — '.join(p for p in detail_parts if p)
            results.append({
                'id': m['id'],
                'source': 'member',
                'name': f"{m['full_name']} {m['father_name'] or ''}".strip(),
                'phone': m['phone'] or '',
                'detail': detail or 'منتسب',
            })

    return jsonify(results)


# ---------------------------------------------------------------------------
# Uploaded files serving
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# KDE Connect SMS Integration
# ---------------------------------------------------------------------------
@app.route('/api/kdeconnect/devices')
@admin_required
def api_kdeconnect_devices():
    """List available KDE Connect devices that are reachable."""
    try:
        result = subprocess.run(
            ['kdeconnect-cli', '--list-available', '--id-name-only'],
            capture_output=True, text=True, timeout=5
        )
        devices = []
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            # Format: "device_id name" or "device_id - name"
            parts = line.split(' ', 1)
            if len(parts) == 2:
                dev_id = parts[0].strip()
                dev_name = parts[1].strip().lstrip('- ').strip()
                devices.append({'id': dev_id, 'name': dev_name})
        # If --id-name-only is not supported, fallback
        if not devices and result.stdout.strip():
            for line in result.stdout.strip().split('\n'):
                line = line.strip()
                if line and ':' in line:
                    # "- DeviceName: deviceId"
                    name_part, _, id_part = line.rpartition(':')
                    dev_name = name_part.strip().lstrip('- ').strip()
                    dev_id = id_part.strip()
                    if dev_id and dev_name:
                        devices.append({'id': dev_id, 'name': dev_name})
        return jsonify(devices)
    except FileNotFoundError:
        return jsonify({'error': 'kdeconnect-cli غير مثبت. يرجى تثبيته: sudo apt install kdeconnect'}), 500
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'انتهت مهلة الاتصال بـ KDE Connect'}), 500
    except Exception as e:
        app.logger.error(f"KDE Connect devices error: {e}")
        return jsonify({'error': 'حدث خطأ داخلي'}), 500


@app.route('/api/kdeconnect/send_sms', methods=['POST'])
@admin_required
def api_kdeconnect_send_sms():
    """Send an SMS via KDE Connect."""
    data = request.get_json()
    device_id = data.get('device_id', '').strip()
    phone = data.get('phone', '').strip()
    message = data.get('message', '').strip()

    if not device_id:
        return jsonify({'error': 'يرجى اختيار جهاز'}), 400
    if not phone:
        return jsonify({'error': 'يرجى إدخال رقم الهاتف'}), 400
    if not message:
        return jsonify({'error': 'يرجى إدخال نص الرسالة'}), 400

    try:
        result = subprocess.run(
            ['kdeconnect-cli', '--send-sms', message, '--destination', phone, '-d', device_id],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip() or 'فشل إرسال الرسالة'
            return jsonify({'error': err}), 500
        return jsonify({'ok': True, 'message': 'تم إرسال الرسالة بنجاح'})
    except FileNotFoundError:
        return jsonify({'error': 'kdeconnect-cli غير مثبت'}), 500
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'انتهت مهلة الإرسال'}), 500
    except Exception as e:
        app.logger.error(f"KDE Connect SMS error: {e}")
        return jsonify({'error': 'حدث خطأ داخلي'}), 500


@app.route('/api/kdeconnect/send_sms_bulk', methods=['POST'])
@admin_required
def api_kdeconnect_send_sms_bulk():
    """Send the same SMS to multiple phone numbers via KDE Connect."""
    data = request.get_json()
    device_id = data.get('device_id', '').strip()
    phones = data.get('phones', [])
    message = data.get('message', '').strip()

    if not device_id:
        return jsonify({'error': 'يرجى اختيار جهاز'}), 400
    if not phones:
        return jsonify({'error': 'لا توجد أرقام هواتف'}), 400
    if not message:
        return jsonify({'error': 'يرجى إدخال نص الرسالة'}), 400

    sent = 0
    failed = 0
    errors = []
    for phone in phones:
        phone = phone.strip()
        if not phone:
            continue
        try:
            result = subprocess.run(
                ['kdeconnect-cli', '--send-sms', message, '--destination', phone, '-d', device_id],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                failed += 1
                errors.append(phone)
            else:
                sent += 1
        except Exception:
            failed += 1
            errors.append(phone)
        # Small delay between messages to avoid overwhelming
        time.sleep(0.5)

    return jsonify({
        'ok': True,
        'sent': sent,
        'failed': failed,
        'errors': errors,
        'message': f'تم إرسال {sent} رسالة بنجاح' + (f'، فشل {failed}' if failed else '')
    })


@app.route('/uploads/<path:filename>')
@admin_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def get_lan_ip():
    """Detect the actual LAN IP address so other devices can connect.

    Works offline by trying multiple methods: UDP socket trick (works even
    without internet if a default gateway is configured), hostname -I,
    ip route, and hostname resolution.
    """
    # Method 1: UDP socket trick - connect to a non-routable address.
    # Works on most systems even without internet; only needs a default route.
    for target in ("10.255.255.255", "8.8.8.8"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(2)
            s.connect((target, 1))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            pass

    # Method 2: hostname -I (Linux)
    try:
        result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, timeout=5)
        ips = result.stdout.strip().split()
        for ip in ips:
            if not ip.startswith("127.") and ':' not in ip:  # skip IPv6
                return ip
    except Exception:
        pass

    # Method 3: ip route (Linux)
    try:
        result = subprocess.run(['ip', 'route', 'get', '1'], capture_output=True, text=True, timeout=5)
        for part in result.stdout.split():
            if part.count('.') == 3:
                try:
                    socket.inet_aton(part)
                    if not part.startswith("127."):
                        return part
                except socket.error:
                    continue
    except Exception:
        pass

    # Method 4: hostname resolution
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass

    return "0.0.0.0"


CONFIG_FILE = os.path.join(BASE_DIR, 'server_config.json')


def load_server_config():
    """Load server configuration (fixed IP, port) from server_config.json."""
    defaults = {'fixed_ip': '', 'port': 5000}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                cfg = json.load(f)
            defaults.update(cfg)
        except Exception:
            pass
    return defaults


def save_server_config(cfg):
    """Save server configuration to server_config.json."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=2)


AREA_GROUPS_FILE = os.path.join(BASE_DIR, 'area_groups.json')


def load_area_groups():
    """Load saved area groups from JSON file.

    Structure: [{"name": "قنينص", "sub_addresses": ["شارع الثورة", "حي النور", ...]}, ...]
    Each group is a main area with sub-addresses classified under it.
    """
    if os.path.exists(AREA_GROUPS_FILE):
        try:
            with open(AREA_GROUPS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return []


def save_area_groups(groups):
    """Persist area groups to JSON file."""
    with open(AREA_GROUPS_FILE, 'w', encoding='utf-8') as f:
        json.dump(groups, f, ensure_ascii=False, indent=2)


@app.route('/admin/location-report')
@admin_required
def admin_location_report():
    """Location report with geographic distribution charts and area grouping."""
    db = get_db()
    data_source = request.args.get('source', 'records')
    status_filter = request.args.get('status', '')

    # Build query based on source
    has_area_col = False
    if data_source == 'volunteers':
        base_q = "SELECT province, address FROM volunteers WHERE 1=1"
        params = []
        if status_filter:
            base_q += " AND status = ?"
            params.append(status_filter)
    elif data_source == 'members':
        base_q = "SELECT province, address FROM members WHERE 1=1"
        params = []
        if status_filter:
            base_q += " AND status = ?"
            params.append(status_filter)
    else:
        base_q = "SELECT province, address, address_area FROM records WHERE deleted_at IS NULL"
        has_area_col = True
        params = []
        if status_filter:
            base_q += " AND status = ?"
            params.append(status_filter)

    rows = db.execute(base_q, params).fetchall()

    # Province distribution + area counts from DB
    province_counts = {}
    address_counts = {}
    area_counts = {}
    for r in rows:
        prov = r['province'] or 'غير محدد'
        province_counts[prov] = province_counts.get(prov, 0) + 1
        addr = (r['address'] or '').strip()
        if addr:
            address_counts[addr] = address_counts.get(addr, 0) + 1
        if has_area_col:
            area = (r['address_area'] or '').strip()
            if not area and addr:
                area = ADDRESS_TO_AREA.get(addr, '')
            if area:
                area_counts[area] = area_counts.get(area, 0) + 1

    province_sorted = sorted(province_counts.items(), key=lambda x: x[1], reverse=True)
    address_sorted = sorted(address_counts.items(), key=lambda x: x[1], reverse=True)
    area_sorted = sorted(area_counts.items(), key=lambda x: x[1], reverse=True)

    # Load area groups and compute totals
    area_groups = load_area_groups()
    classified_addresses = set()
    group_data = []
    for grp in area_groups:
        subs = grp.get('sub_addresses', [])
        sub_details = []
        grp_total = 0
        for addr in subs:
            cnt = address_counts.get(addr, 0)
            grp_total += cnt
            sub_details.append({'address': addr, 'count': cnt})
            classified_addresses.add(addr)
        group_data.append({
            'name': grp['name'],
            'sub_addresses': sub_details,
            'total': grp_total,
        })

    group_data_sorted = sorted(group_data, key=lambda x: x['total'], reverse=True)

    # Unclassified addresses (not assigned to any area)
    unclassified = [(a, c) for a, c in address_sorted if a not in classified_addresses]

    # Available statuses
    if data_source == 'volunteers':
        statuses = [r[0] for r in db.execute("SELECT DISTINCT status FROM volunteers WHERE status IS NOT NULL AND status != ''").fetchall()]
    elif data_source == 'members':
        statuses = [r[0] for r in db.execute("SELECT DISTINCT status FROM members WHERE status IS NOT NULL AND status != ''").fetchall()]
    else:
        statuses = ['survivor', 'enforced', 'deceased']

    return render_template('admin_location_report.html',
                           data_source=data_source,
                           status_filter=status_filter,
                           statuses=statuses,
                           province_data=province_sorted,
                           address_data=address_sorted,
                           group_data=group_data_sorted,
                           area_groups=area_groups,
                           unclassified=unclassified,
                           total=len(rows),
                           PROVINCES=PROVINCES,
                           area_data=area_sorted,
                           ADDRESS_TO_AREA=ADDRESS_TO_AREA,
                           report_date=datetime.now().strftime('%Y-%m-%d'))


@app.route('/api/area-groups', methods=['GET', 'POST', 'DELETE'])
@admin_required
def api_area_groups():
    """CRUD API for area groups (main areas with sub-addresses)."""
    if request.method == 'GET':
        return jsonify(load_area_groups())

    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'error': 'اسم المنطقة مطلوب'}), 400
        sub_addresses = data.get('sub_addresses', [])
        if not sub_addresses:
            return jsonify({'error': 'يجب إضافة عنوان فرعي واحد على الأقل'}), 400

        groups = load_area_groups()
        existing = next((g for g in groups if g['name'] == name), None)
        if existing:
            existing['sub_addresses'] = sub_addresses
        else:
            groups.append({'name': name, 'sub_addresses': sub_addresses})
        save_area_groups(groups)
        return jsonify({'ok': True, 'groups': groups})

    if request.method == 'DELETE':
        data = request.get_json(silent=True) or {}
        name = data.get('name', '')
        groups = load_area_groups()
        groups = [g for g in groups if g['name'] != name]
        save_area_groups(groups)
        return jsonify({'ok': True, 'groups': groups})


@app.route('/admin/server-config', methods=['GET', 'POST'])
@admin_required
def admin_server_config():
    cfg = load_server_config()
    if request.method == 'POST':
        cfg['fixed_ip'] = request.form.get('fixed_ip', '').strip()
        try:
            cfg['port'] = int(request.form.get('port', 5000))
        except ValueError:
            cfg['port'] = 5000
        save_server_config(cfg)
        flash('تم حفظ إعدادات الخادم. أعد تشغيل التطبيق لتطبيق التغييرات.', 'success')
        return redirect(url_for('admin_server_config'))
    lan_ip = get_lan_ip()
    return render_template('admin_server_config.html', config=cfg, current_ip=lan_ip)


@app.route('/api/network')
@admin_required
def api_network():
    """Return network graph data for relationship visualization."""
    db = get_db()
    # Get all records (nodes)
    records = db.execute(
        "SELECT id, first_name, father_name, last_name, status, province "
        "FROM records WHERE deleted_at IS NULL"
    ).fetchall()

    nodes = []
    node_ids = set()
    for r in records:
        node_ids.add(r['id'])
        nodes.append({
            'id': r['id'],
            'name': ' '.join(filter(None, [r['first_name'], r['father_name'], r['last_name']])),
            'status': r['status'] or '',
            'province': r['province'] or '',
        })

    edges = []
    # record_links
    links = db.execute("SELECT record_id_a, record_id_b, link_type, notes FROM record_links").fetchall()
    for l in links:
        if l['record_id_a'] in node_ids and l['record_id_b'] in node_ids:
            edges.append({
                'source': l['record_id_a'], 'target': l['record_id_b'],
                'type': l['link_type'], 'label': l['notes'] or l['link_type'],
            })

    # companions with linked records
    comps = db.execute(
        "SELECT record_id, linked_record_id, first_name, last_name "
        "FROM record_companions WHERE linked_record_id IS NOT NULL"
    ).fetchall()
    for c in comps:
        if c['record_id'] in node_ids and c['linked_record_id'] in node_ids:
            edges.append({
                'source': c['record_id'], 'target': c['linked_record_id'],
                'type': 'companion',
                'label': ' '.join(filter(None, [c['first_name'], c['last_name']])) or 'رفيق',
            })

    # Only include nodes that have at least one edge
    connected_ids = set()
    for e in edges:
        connected_ids.add(e['source'])
        connected_ids.add(e['target'])
    nodes = [n for n in nodes if n['id'] in connected_ids]

    return jsonify({'nodes': nodes, 'edges': edges})


@app.route('/admin/network')
@admin_required
def admin_network():
    """Family/relationship network visualization."""
    return render_template('admin_network.html')


@app.route('/admin/dedup')
@admin_required
def admin_dedup():
    """Batch deduplication scanner - finds potential duplicate records."""
    db = get_db()
    records = db.execute(
        "SELECT id, first_name, father_name, last_name, national_id, phone, province, status "
        "FROM records WHERE deleted_at IS NULL ORDER BY first_name, last_name"
    ).fetchall()

    duplicates = []
    seen = {}  # key -> list of record dicts

    for r in records:
        # Key 1: exact name match (first + father + last)
        name_key = f"{(r['first_name'] or '').strip()}|{(r['father_name'] or '').strip()}|{(r['last_name'] or '').strip()}"
        if name_key and name_key != '||':
            seen.setdefault(('name', name_key), []).append(r)

        # Key 2: national_id match
        nid = (r['national_id'] or '').strip()
        if nid:
            seen.setdefault(('nid', nid), []).append(r)

        # Key 3: phone match
        phone = (r['phone'] or '').strip()
        if phone:
            seen.setdefault(('phone', phone), []).append(r)

    # Collect groups with >1 match
    dup_groups = []
    seen_ids = set()
    for (match_type, key), group in seen.items():
        if len(group) > 1:
            ids = tuple(sorted(r['id'] for r in group))
            if ids not in seen_ids:
                seen_ids.add(ids)
                type_labels = {'name': 'تطابق الاسم', 'nid': 'تطابق الرقم الوطني', 'phone': 'تطابق الهاتف'}
                dup_groups.append({
                    'match_type': type_labels.get(match_type, match_type),
                    'match_value': key,
                    'records': [dict(r) for r in group],
                })

    return render_template('admin_dedup.html', groups=dup_groups, total_groups=len(dup_groups))


@app.route('/admin/missing-details')
@admin_required
def admin_missing_details():
    """Show profiles with missing/incomplete fields across volunteers, members, and records."""
    db = get_db()
    profile_type = request.args.get('type', 'all')
    sort = request.args.get('sort', 'missing_desc')
    field_filter = request.args.get('field', '')

    results = []

    def _is_empty(val, is_int=False):
        if is_int:
            return not val or val == 0
        return not val or not str(val).strip()

    # --- Volunteers ---
    volunteer_fields = [
        ('phone', 'الهاتف'),
        ('email', 'البريد الإلكتروني'),
        ('national_id', 'الرقم الوطني'),
        ('province', 'المحافظة'),
        ('address', 'العنوان'),
        ('role', 'الدور'),
        ('specialization', 'التخصص'),
        ('join_date', 'تاريخ الانضمام'),
    ]
    if profile_type in ('all', 'volunteers'):
        volunteers = db.execute("SELECT * FROM volunteers ORDER BY full_name").fetchall()
        for v in volunteers:
            missing = [label for col, label in volunteer_fields if _is_empty(v[col])]
            if missing:
                results.append({
                    'type': 'متطوع',
                    'type_key': 'volunteers',
                    'id': v['id'],
                    'name': v['full_name'],
                    'phone': v['phone'] or '',
                    'missing': missing,
                    'missing_count': len(missing),
                    'total_fields': len(volunteer_fields),
                    'edit_url': url_for('admin_volunteer_edit', vid=v['id']),
                    'priority': len(missing) * 5,
                })

    # --- Members ---
    member_fields = [
        ('father_name', 'اسم الأب'),
        ('phone', 'الهاتف'),
        ('email', 'البريد الإلكتروني'),
        ('national_id', 'الرقم الوطني'),
        ('birth_year', 'سنة الميلاد'),
        ('gender', 'الجنس'),
        ('province', 'المحافظة'),
        ('address', 'العنوان'),
        ('membership_type', 'نوع العضوية'),
        ('membership_number', 'رقم العضوية'),
        ('join_date', 'تاريخ الانضمام'),
    ]
    if profile_type in ('all', 'members'):
        members = db.execute("SELECT * FROM members ORDER BY full_name").fetchall()
        for m in members:
            missing = [label for col, label in member_fields
                       if _is_empty(m[col], is_int=(col == 'birth_year'))]
            if missing:
                results.append({
                    'type': 'منتسب',
                    'type_key': 'members',
                    'id': m['id'],
                    'name': m['full_name'],
                    'phone': m['phone'] or '',
                    'missing': missing,
                    'missing_count': len(missing),
                    'total_fields': len(member_fields),
                    'edit_url': url_for('admin_member_edit', mid=m['id']),
                    'priority': len(missing) * 5,
                })

    # --- Records (status-aware) ---
    record_base_fields = [
        ('first_name', 'الاسم'),
        ('father_name', 'اسم الأب'),
        ('last_name', 'الكنية'),
        ('mother_name', 'اسم الأم'),
        ('gender', 'الجنس'),
        ('status', 'الحالة'),
        ('province', 'المحافظة'),
        ('national_id', 'الرقم الوطني'),
        ('family_book_number', 'رقم دفتر العائلة'),
        ('phone', 'الهاتف'),
        ('birth_year', 'سنة الميلاد'),
        ('marital', 'الحالة الاجتماعية'),
        ('address', 'العنوان'),
        ('housing_type', 'نوع السكن'),
        ('reporter_name', 'اسم المبلّغ'),
        ('reporter_relation', 'صلة المبلّغ'),
        ('photo_path', 'الصورة'),
    ]
    # Fields checked only when status is known
    record_arrest_fields = [
        ('arrest_year', 'سنة الاعتقال'),
        ('arrest_authority', 'جهة الاعتقال'),
        ('arrest_place', 'مكان الاحتجاز'),
        ('arrest_reason', 'سبب الاعتقال'),
    ]
    record_survivor_fields = [
        ('release_year', 'سنة الإفراج'),
    ]
    record_deceased_fields = [
        ('death_year', 'سنة الوفاة'),
        ('death_place', 'مكان الوفاة'),
    ]
    if profile_type in ('all', 'records'):
        records = db.execute("SELECT * FROM records WHERE deleted_at IS NULL ORDER BY id").fetchall()
        for r in records:
            # Build status-aware field list
            fields_to_check = list(record_base_fields)
            rec_status = r['status'] or ''
            if rec_status in ('enforced', 'survivor', 'deceased'):
                fields_to_check.extend(record_arrest_fields)
            if rec_status == 'survivor':
                fields_to_check.extend(record_survivor_fields)
            if rec_status == 'deceased':
                fields_to_check.extend(record_deceased_fields)

            int_cols = {'birth_year', 'arrest_year', 'release_year', 'death_year'}
            missing = [label for col, label in fields_to_check
                       if _is_empty(r[col], is_int=(col in int_cols))]
            if missing:
                full_name = ' '.join(filter(None, [r['first_name'], r['father_name'], r['last_name']]))
                # Priority = missing fields weight + vulnerability score
                need = compute_need_score(r)
                priority = len(missing) * 5 + need
                results.append({
                    'type': 'سجل',
                    'type_key': 'records',
                    'id': r['id'],
                    'name': full_name or f"سجل #{r['id']}",
                    'phone': r['phone'] or r['spouse_phone'] or r['reporter_phone'] or '',
                    'missing': missing,
                    'missing_count': len(missing),
                    'total_fields': len(fields_to_check),
                    'edit_url': url_for('admin_record_edit', record_id=r['id']),
                    'priority': priority,
                })

    # Filter by specific missing field
    if field_filter:
        results = [r for r in results if field_filter in r['missing']]

    # Collect all unique missing field names for the dropdown
    all_fields = sorted(set(f for r in results for f in r['missing']))

    # Sort results
    if sort == 'missing_asc':
        results.sort(key=lambda x: x['missing_count'])
    elif sort == 'name':
        results.sort(key=lambda x: x['name'])
    elif sort == 'priority_desc':
        results.sort(key=lambda x: x.get('priority', 0), reverse=True)
    else:  # missing_desc (default)
        results.sort(key=lambda x: x['missing_count'], reverse=True)

    # Summary counts
    summary = {
        'total': len(results),
        'volunteers': sum(1 for r in results if r['type_key'] == 'volunteers'),
        'members': sum(1 for r in results if r['type_key'] == 'members'),
        'records': sum(1 for r in results if r['type_key'] == 'records'),
    }

    return render_template('admin_missing_details.html',
                           results=results, summary=summary,
                           profile_type=profile_type, sort=sort,
                           field_filter=field_filter, all_fields=all_fields)


@app.route('/admin/missing-details/excel')
@admin_required
def admin_missing_details_excel():
    """Export missing details report as Excel."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    # Reuse the same logic by calling the view function internals
    # Re-fetch data inline to avoid circular dependency
    db = get_db()
    profile_type = request.args.get('type', 'all')
    field_filter = request.args.get('field', '')

    results = []

    def _is_empty(val, is_int=False):
        if is_int:
            return not val or val == 0
        return not val or not str(val).strip()

    volunteer_fields = [
        ('phone', 'الهاتف'), ('email', 'البريد الإلكتروني'),
        ('national_id', 'الرقم الوطني'), ('province', 'المحافظة'),
        ('address', 'العنوان'), ('role', 'الدور'),
        ('specialization', 'التخصص'), ('join_date', 'تاريخ الانضمام'),
    ]
    if profile_type in ('all', 'volunteers'):
        for v in db.execute("SELECT * FROM volunteers ORDER BY full_name").fetchall():
            missing = [label for col, label in volunteer_fields if _is_empty(v[col])]
            if missing:
                results.append({'type': 'متطوع', 'id': v['id'], 'name': v['full_name'],
                                'phone': v['phone'] or '', 'missing': missing,
                                'total': len(volunteer_fields)})

    member_fields = [
        ('father_name', 'اسم الأب'), ('phone', 'الهاتف'),
        ('email', 'البريد الإلكتروني'), ('national_id', 'الرقم الوطني'),
        ('birth_year', 'سنة الميلاد'), ('gender', 'الجنس'),
        ('province', 'المحافظة'), ('address', 'العنوان'),
        ('membership_type', 'نوع العضوية'), ('membership_number', 'رقم العضوية'),
        ('join_date', 'تاريخ الانضمام'),
    ]
    if profile_type in ('all', 'members'):
        for m in db.execute("SELECT * FROM members ORDER BY full_name").fetchall():
            missing = [label for col, label in member_fields
                       if _is_empty(m[col], is_int=(col == 'birth_year'))]
            if missing:
                results.append({'type': 'منتسب', 'id': m['id'], 'name': m['full_name'],
                                'phone': m['phone'] or '', 'missing': missing,
                                'total': len(member_fields)})

    record_base = [
        ('first_name', 'الاسم'), ('father_name', 'اسم الأب'),
        ('last_name', 'الكنية'), ('mother_name', 'اسم الأم'),
        ('gender', 'الجنس'), ('status', 'الحالة'),
        ('province', 'المحافظة'), ('national_id', 'الرقم الوطني'),
        ('family_book_number', 'رقم دفتر العائلة'),
        ('phone', 'الهاتف'), ('birth_year', 'سنة الميلاد'),
        ('marital', 'الحالة الاجتماعية'), ('address', 'العنوان'),
        ('housing_type', 'نوع السكن'), ('reporter_name', 'اسم المبلّغ'),
        ('reporter_relation', 'صلة المبلّغ'), ('photo_path', 'الصورة'),
    ]
    arrest_f = [('arrest_year', 'سنة الاعتقال'), ('arrest_authority', 'جهة الاعتقال'),
                ('arrest_place', 'مكان الاحتجاز'), ('arrest_reason', 'سبب الاعتقال')]
    survivor_f = [('release_year', 'سنة الإفراج')]
    deceased_f = [('death_year', 'سنة الوفاة'), ('death_place', 'مكان الوفاة')]
    int_cols = {'birth_year', 'arrest_year', 'release_year', 'death_year'}

    if profile_type in ('all', 'records'):
        for r in db.execute("SELECT * FROM records WHERE deleted_at IS NULL ORDER BY id").fetchall():
            fields = list(record_base)
            s = r['status'] or ''
            if s in ('enforced', 'survivor', 'deceased'):
                fields.extend(arrest_f)
            if s == 'survivor':
                fields.extend(survivor_f)
            if s == 'deceased':
                fields.extend(deceased_f)
            missing = [label for col, label in fields if _is_empty(r[col], is_int=(col in int_cols))]
            if missing:
                name = ' '.join(filter(None, [r['first_name'], r['father_name'], r['last_name']]))
                results.append({'type': 'سجل', 'id': r['id'], 'name': name or f"سجل #{r['id']}",
                                'phone': r['phone'] or r['spouse_phone'] or r['reporter_phone'] or '',
                                'missing': missing, 'total': len(fields)})

    if field_filter:
        results = [r for r in results if field_filter in r['missing']]
    results.sort(key=lambda x: len(x['missing']), reverse=True)

    # Build Excel
    wb = Workbook()
    ws = wb.active
    ws.title = 'التفاصيل الناقصة'
    ws.sheet_view.rightToLeft = True

    header_font = Font(bold=True, color='FFFFFF', size=11)
    header_fill = PatternFill(start_color='1565C0', end_color='1565C0', fill_type='solid')
    header_align = Alignment(horizontal='center', vertical='center')
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )

    headers = ['#', 'النوع', 'الاسم', 'الهاتف', 'الاكتمال %', 'الحقول الناقصة']
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border

    for row_idx, r in enumerate(results, 2):
        pct = int(((r['total'] - len(r['missing'])) / r['total']) * 100) if r['total'] else 0
        values = [r['id'], r['type'], r['name'], r['phone'], f"{pct}%",
                  '، '.join(r['missing'])]
        for col_idx, val in enumerate(values, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.border = thin_border
            cell.alignment = Alignment(horizontal='right' if col_idx != 5 else 'center',
                                       vertical='center', wrap_text=(col_idx == 6))

    # Auto-width
    for col_idx in range(1, len(headers) + 1):
        ws.column_dimensions[chr(64 + col_idx) if col_idx <= 26 else 'A'].width = \
            max(12, min(50, max((len(str(ws.cell(row=r, column=col_idx).value or ''))
                                 for r in range(1, len(results) + 2)), default=12)))

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name='missing_details.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.route('/admin/audit-log')
@admin_required
def admin_audit_log():
    db = get_db()
    page = safe_int(request.args.get('page'), 1)
    per_page = 50
    entity_type = request.args.get('entity_type', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = "SELECT * FROM audit_log WHERE 1=1"
    params = []
    if entity_type:
        query += " AND entity_type=?"
        params.append(entity_type)
    if date_from:
        query += " AND timestamp >= ?"
        params.append(date_from)
    if date_to:
        query += " AND timestamp <= ?"
        params.append(date_to + ' 23:59:59')

    total = db.execute(query.replace("SELECT *", "SELECT COUNT(*)"), params).fetchone()[0]
    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])
    logs = db.execute(query, params).fetchall()

    return render_template('admin_audit_log.html', logs=logs, total=total,
                           page=page, per_page=per_page, entity_type=entity_type,
                           date_from=date_from, date_to=date_to)


# ---------------------------------------------------------------------------
# Routes – Backup & Import
# ---------------------------------------------------------------------------
@app.route('/admin/backup')
@admin_required
def admin_backup():
    """Backup management page."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    backups = []
    for f in sorted(os.listdir(BACKUP_DIR), reverse=True):
        fp = os.path.join(BACKUP_DIR, f)
        if os.path.isfile(fp):
            size = os.path.getsize(fp)
            size_mb = round(size / (1024 * 1024), 2)
            mtime = datetime.fromtimestamp(os.path.getmtime(fp)).strftime('%Y-%m-%d %H:%M')
            backups.append({'name': f, 'size': size_mb, 'date': mtime})
    return render_template('admin_backup.html', backups=backups)


@app.route('/admin/backup/create', methods=['POST'])
@admin_required
def admin_backup_create():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'registry_{ts}.db'
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    shutil.copy2(DB_PATH, backup_path)

    # Also zip uploads if they exist and aren't too large
    uploads_dir = app.config['UPLOAD_FOLDER']
    if os.path.exists(uploads_dir) and os.listdir(uploads_dir):
        zip_name = f'uploads_{ts}.zip'
        zip_path = os.path.join(BACKUP_DIR, zip_name)
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(uploads_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, BASE_DIR)
                    zf.write(file_path, arcname)

    log_audit('backup_create', 'system', details=backup_name)
    flash(f'تم إنشاء النسخة الاحتياطية: {backup_name}', 'success')
    return redirect(url_for('admin_backup'))


@app.route('/admin/backup/download/<filename>')
@admin_required
def admin_backup_download(filename):
    # Validate path to prevent directory traversal
    fp = os.path.join(BACKUP_DIR, filename)
    if not os.path.commonpath([BACKUP_DIR, os.path.realpath(fp)]) == BACKUP_DIR:
        flash('ملف غير صالح', 'error')
        return redirect(url_for('admin_backup'))
    return send_from_directory(BACKUP_DIR, filename, as_attachment=True)


@app.route('/admin/backup/<filename>/delete', methods=['POST'])
@admin_required
def admin_backup_delete(filename):
    fp = os.path.join(BACKUP_DIR, filename)
    if os.path.exists(fp) and os.path.commonpath([BACKUP_DIR, os.path.realpath(fp)]) == BACKUP_DIR:
        os.remove(fp)
        log_audit('backup_delete', 'system', details=filename)
        flash('تم حذف النسخة الاحتياطية', 'success')
    else:
        flash('الملف غير موجود', 'error')
    return redirect(url_for('admin_backup'))


@app.route('/admin/backup/restore', methods=['POST'])
@admin_required
def admin_backup_restore():
    backup_file = request.form.get('filename', '')
    fp = os.path.join(BACKUP_DIR, backup_file)
    if not os.path.exists(fp) or not backup_file.endswith('.db') or \
       os.path.commonpath([BACKUP_DIR, os.path.realpath(fp)]) != BACKUP_DIR:
        flash('ملف النسخة الاحتياطية غير صالح', 'error')
        return redirect(url_for('admin_backup'))

    # Safety backup before restore
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    safety = os.path.join(BACKUP_DIR, f'pre_restore_{ts}.db')
    shutil.copy2(DB_PATH, safety)

    # Close current connection and restore
    db = g.pop('db', None)
    if db:
        db.close()
    shutil.copy2(fp, DB_PATH)

    log_audit('backup_restore', 'system', details=f'Restored from {backup_file}, safety backup: pre_restore_{ts}.db')
    flash(f'تم استعادة قاعدة البيانات من {backup_file}', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/import', methods=['GET', 'POST'])
@admin_required
def admin_import():
    if request.method == 'POST':
        from openpyxl import load_workbook
        file = request.files.get('file')
        import_type = request.form.get('import_type', 'records')
        if not file or not file.filename:
            flash('يرجى اختيار ملف', 'error')
            return redirect(url_for('admin_import'))

        try:
            wb = load_workbook(file, read_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(min_row=2, values_only=True))
            headers = [cell.value for cell in ws[1]]
            wb.close()
        except Exception as e:
            flash(f'خطأ في قراءة الملف: {e}', 'error')
            return redirect(url_for('admin_import'))

        db = get_db()
        inserted = 0
        skipped = []

        if import_type == 'records':
            col_map = {h: i for i, h in enumerate(headers) if h}
            for row_num, row in enumerate(rows, 2):
                def g(col):
                    idx = col_map.get(col)
                    return str(row[idx]).strip() if idx is not None and idx < len(row) and row[idx] else ''

                def gi(col):
                    """Get integer value or 0."""
                    v = g(col)
                    try:
                        return int(float(v)) if v else 0
                    except (ValueError, TypeError):
                        return 0

                first = g('first_name') or g('الاسم')
                last = g('last_name') or g('الكنية')
                if not first:
                    skipped.append(f'سطر {row_num}: الاسم مطلوب')
                    continue

                slug = f"{first}-{last}-{int(time.time())}-{row_num}".replace(' ', '-')
                try:
                    db.execute("""INSERT INTO records (
                        first_name, father_name, last_name, mother_name,
                        gender, birth_day, birth_month, birth_year, blood_type,
                        national_id, phone, province, address, address_area,
                        housing_type, rent_amount, status, marital, case_type,
                        arrest_day, arrest_month, arrest_year,
                        arrest_place, arrest_authority, arrest_reason, arrest_causer,
                        release_day, release_month, release_year,
                        death_day, death_month, death_year, death_place,
                        spouse_name, spouse_phone, has_kids, kids_count,
                        guardian_name, guardian_relation, guardian_phone,
                        education, edu_type, edu_specialization, edu_university,
                        employment, profession, employer,
                        chronic, has_hypertension, has_diabetes,
                        has_special_needs, special_needs_details,
                        breadwinner, breadwinner_job, breadwinner_relation,
                        legal, legal_details, is_officially_registered,
                        civil_registry_status, civil_registry_date, family_book_number,
                        reporter_name, reporter_relation, reporter_phone, reporter_id,
                        informant_consent, evidence_level, source_type,
                        collection_date, collector_name, methodology_notes,
                        notes, record_slug
                    ) VALUES (
                        ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                        ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                        ?,?,?,?,?,?,?
                    )""", (
                        first,
                        g('father_name') or g('اسم الأب'),
                        last,
                        g('mother_name') or g('اسم الأم'),
                        g('gender') or g('الجنس'),
                        gi('birth_day') or gi('يوم الميلاد') or None,
                        gi('birth_month') or gi('شهر الميلاد') or None,
                        gi('birth_year') or gi('سنة الميلاد') or None,
                        g('blood_type') or g('فصيلة الدم'),
                        g('national_id') or g('الرقم الوطني'),
                        g('phone') or g('الهاتف'),
                        g('province') or g('المحافظة'),
                        g('address') or g('العنوان'),
                        g('address_area') or g('المنطقة'),
                        g('housing_type') or g('نوع السكن'),
                        g('rent_amount') or g('مبلغ الإيجار'),
                        g('status') or g('الحالة'),
                        g('marital') or g('الحالة الاجتماعية'),
                        g('case_type') or g('نوع القضية'),
                        gi('arrest_day') or gi('يوم الاعتقال') or None,
                        gi('arrest_month') or gi('شهر الاعتقال') or None,
                        gi('arrest_year') or gi('سنة الاعتقال') or None,
                        g('arrest_place') or g('مكان الاعتقال'),
                        g('arrest_authority') or g('جهة الاعتقال'),
                        g('arrest_reason') or g('سبب الاعتقال'),
                        g('arrest_causer') or g('المتسبب بالاعتقال'),
                        gi('release_day') or gi('يوم الإفراج') or None,
                        gi('release_month') or gi('شهر الإفراج') or None,
                        gi('release_year') or gi('سنة الإفراج') or None,
                        gi('death_day') or gi('يوم الوفاة') or None,
                        gi('death_month') or gi('شهر الوفاة') or None,
                        gi('death_year') or gi('سنة الوفاة') or None,
                        g('death_place') or g('مكان الوفاة'),
                        g('spouse_name') or g('اسم الزوج/ة'),
                        g('spouse_phone') or g('هاتف الزوج/ة'),
                        g('has_kids') or g('لديه أطفال'),
                        gi('kids_count') or gi('عدد الأطفال') or None,
                        g('guardian_name') or g('اسم الوصي'),
                        g('guardian_relation') or g('صلة الوصي'),
                        g('guardian_phone') or g('هاتف الوصي'),
                        g('education') or g('التعليم'),
                        g('edu_type') or g('نوع التعليم'),
                        g('edu_specialization') or g('التخصص'),
                        g('edu_university') or g('الجامعة/المعهد'),
                        g('employment') or g('العمل'),
                        g('profession') or g('المهنة'),
                        g('employer') or g('جهة العمل'),
                        g('chronic') or g('أمراض مزمنة'),
                        gi('has_hypertension') or gi('ضغط') or None,
                        gi('has_diabetes') or gi('سكري') or None,
                        gi('has_special_needs') or gi('احتياجات خاصة') or None,
                        g('special_needs_details') or g('تفاصيل الاحتياجات'),
                        g('breadwinner') or g('المعيل'),
                        g('breadwinner_job') or g('عمل المعيل'),
                        g('breadwinner_relation') or g('صلة المعيل'),
                        g('legal') or g('وضع قانوني'),
                        g('legal_details') or g('تفاصيل قانونية'),
                        gi('is_officially_registered') or gi('مسجل رسمياً') or None,
                        g('civil_registry_status') or g('حالة السجل المدني'),
                        g('civil_registry_date') or g('تاريخ السجل المدني'),
                        g('family_book_number') or g('رقم دفتر العائلة'),
                        g('reporter_name') or g('اسم المبلّغ'),
                        g('reporter_relation') or g('صلة المبلّغ'),
                        g('reporter_phone') or g('هاتف المبلّغ'),
                        g('reporter_id') or g('هوية المبلّغ'),
                        gi('informant_consent') or gi('موافقة المبلّغ') or None,
                        g('evidence_level') or g('مستوى الأدلة') or 'unverified',
                        g('source_type') or g('نوع المصدر'),
                        g('collection_date') or g('تاريخ الجمع'),
                        g('collector_name') or g('اسم الجامع'),
                        g('methodology_notes') or g('ملاحظات المنهجية'),
                        g('notes') or g('ملاحظات'),
                        slug,
                    ))
                    inserted += 1
                except Exception as e:
                    skipped.append(f'سطر {row_num}: {e}')

        elif import_type == 'volunteers':
            col_map = {h: i for i, h in enumerate(headers) if h}
            for row_num, row in enumerate(rows, 2):
                def g(col):
                    idx = col_map.get(col)
                    return str(row[idx]).strip() if idx is not None and idx < len(row) and row[idx] else ''

                name = g('full_name') or g('الاسم')
                if not name:
                    skipped.append(f'سطر {row_num}: الاسم مطلوب')
                    continue
                try:
                    db.execute("INSERT INTO volunteers (full_name, phone, email, national_id, province, address, role, specialization) VALUES (?,?,?,?,?,?,?,?)",
                               (name, g('phone') or g('الهاتف'), g('email') or g('البريد'),
                                g('national_id') or g('الرقم الوطني'), g('province') or g('المحافظة'),
                                g('address') or g('العنوان'), g('role') or g('الدور'),
                                g('specialization') or g('التخصص')))
                    inserted += 1
                except Exception as e:
                    skipped.append(f'سطر {row_num}: {e}')

        elif import_type == 'members':
            col_map = {h: i for i, h in enumerate(headers) if h}
            for row_num, row in enumerate(rows, 2):
                def g(col):
                    idx = col_map.get(col)
                    return str(row[idx]).strip() if idx is not None and idx < len(row) and row[idx] else ''

                name = g('full_name') or g('الاسم')
                if not name:
                    skipped.append(f'سطر {row_num}: الاسم مطلوب')
                    continue
                try:
                    db.execute("INSERT INTO members (full_name, father_name, phone, email, national_id, province, address, membership_type) VALUES (?,?,?,?,?,?,?,?)",
                               (name, g('father_name') or g('اسم الأب'),
                                g('phone') or g('الهاتف'), g('email') or g('البريد'),
                                g('national_id') or g('الرقم الوطني'), g('province') or g('المحافظة'),
                                g('address') or g('العنوان'), g('membership_type') or g('نوع العضوية')))
                    inserted += 1
                except Exception as e:
                    skipped.append(f'سطر {row_num}: {e}')

        elif import_type == 'services':
            col_map = {h: i for i, h in enumerate(headers) if h}
            for row_num, row in enumerate(rows, 2):
                def g(col):
                    idx = col_map.get(col)
                    return str(row[idx]).strip() if idx is not None and idx < len(row) and row[idx] else ''

                service_name = g('service_name') or g('اسم الخدمة')
                if not service_name:
                    skipped.append(f'سطر {row_num}: اسم الخدمة مطلوب')
                    continue

                # Resolve record_id: try numeric ID first, then name search
                record_id_val = g('record_id') or g('رقم السجل')
                record_id = None
                if record_id_val:
                    try:
                        record_id = int(float(record_id_val))
                        exists = db.execute("SELECT id FROM records WHERE id=? AND deleted_at IS NULL", (record_id,)).fetchone()
                        if not exists:
                            skipped.append(f'سطر {row_num}: السجل رقم {record_id} غير موجود')
                            continue
                    except (ValueError, TypeError):
                        skipped.append(f'سطر {row_num}: رقم السجل غير صالح: {record_id_val}')
                        continue

                if not record_id:
                    record_name = g('record_name') or g('الاسم (بديل عن الرقم)')
                    if not record_name:
                        skipped.append(f'سطر {row_num}: رقم السجل أو الاسم مطلوب')
                        continue
                    # Search by name parts
                    name_parts = record_name.split()
                    if len(name_parts) >= 2:
                        match = db.execute(
                            "SELECT id FROM records WHERE deleted_at IS NULL AND first_name LIKE ? AND (last_name LIKE ? OR father_name LIKE ?) LIMIT 1",
                            (f'%{name_parts[0]}%', f'%{name_parts[-1]}%', f'%{name_parts[-1]}%')
                        ).fetchone()
                    else:
                        match = db.execute(
                            "SELECT id FROM records WHERE deleted_at IS NULL AND first_name LIKE ? LIMIT 1",
                            (f'%{name_parts[0]}%',)
                        ).fetchone()
                    if not match:
                        skipped.append(f'سطر {row_num}: لم يتم العثور على سجل باسم "{record_name}"')
                        continue
                    record_id = match['id']

                try:
                    db.execute(
                        "INSERT INTO record_services (record_id, service_name, service_date, provider, notes) VALUES (?,?,?,?,?)",
                        (record_id, service_name,
                         g('service_date') or g('تاريخ الخدمة'),
                         g('provider') or g('مقدم الخدمة'),
                         g('notes') or g('ملاحظات'))
                    )
                    inserted += 1
                except Exception as e:
                    skipped.append(f'سطر {row_num}: {e}')

        db.commit()
        log_audit('bulk_import', import_type, details=f'{inserted} inserted, {len(skipped)} skipped')
        flash(f'تم استيراد {inserted} سجل بنجاح' + (f'، تم تخطي {len(skipped)} سطر' if skipped else ''), 'success')
        if skipped:
            for s in skipped[:10]:
                flash(s, 'error')
        return redirect(url_for('admin_import'))

    return render_template('admin_import.html')


@app.route('/admin/import/template')
@admin_required
def admin_import_template():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    import_type = request.args.get('type', 'records')
    wb = Workbook()
    ws = wb.active
    ws.sheet_view.rightToLeft = True

    # Each entry: (Arabic header, English db column name, column width, example/hint)
    if import_type == 'services':
        columns = [
            ('رقم السجل', 'record_id', 14, '101'),
            ('الاسم (بديل عن الرقم)', 'record_name', 22, 'أحمد محمد الأحمد'),
            ('اسم الخدمة', 'service_name', 24, 'مساعدة قانونية / دعم نفسي / مساعدة مادية'),
            ('تاريخ الخدمة', 'service_date', 16, '2024-06-15'),
            ('مقدم الخدمة', 'provider', 22, 'منظمة حقنا'),
            ('ملاحظات', 'notes', 30, ''),
        ]
        ws.title = 'خدمات'
    elif import_type == 'volunteers':
        columns = [
            ('الاسم', 'full_name', 22, 'أحمد محمد'),
            ('الهاتف', 'phone', 16, '0912345678'),
            ('البريد', 'email', 24, 'example@email.com'),
            ('الرقم الوطني', 'national_id', 18, ''),
            ('المحافظة', 'province', 16, 'دمشق'),
            ('العنوان', 'address', 24, ''),
            ('الدور', 'role', 16, 'ميداني / إداري'),
            ('التخصص', 'specialization', 20, ''),
        ]
        ws.title = 'متطوعون'
    elif import_type == 'members':
        columns = [
            ('الاسم', 'full_name', 22, 'أحمد'),
            ('اسم الأب', 'father_name', 18, 'محمد'),
            ('الهاتف', 'phone', 16, '0912345678'),
            ('البريد', 'email', 24, 'example@email.com'),
            ('الرقم الوطني', 'national_id', 18, ''),
            ('المحافظة', 'province', 16, 'دمشق'),
            ('العنوان', 'address', 24, ''),
            ('نوع العضوية', 'membership_type', 18, 'عامل / داعم'),
        ]
        ws.title = 'منتسبون'
    else:
        columns = [
            # --- المعلومات الأساسية ---
            ('الاسم', 'first_name', 18, 'أحمد'),
            ('اسم الأب', 'father_name', 18, 'محمد'),
            ('الكنية', 'last_name', 18, 'الأحمد'),
            ('اسم الأم', 'mother_name', 18, 'فاطمة'),
            ('الجنس', 'gender', 12, 'ذكر / أنثى'),
            ('يوم الميلاد', 'birth_day', 12, '15'),
            ('شهر الميلاد', 'birth_month', 12, '6'),
            ('سنة الميلاد', 'birth_year', 12, '1990'),
            ('فصيلة الدم', 'blood_type', 12, 'A+ / B- / O+'),
            ('الرقم الوطني', 'national_id', 18, ''),
            ('الهاتف', 'phone', 16, '0912345678'),
            ('المحافظة', 'province', 16, 'دمشق'),
            ('العنوان', 'address', 24, ''),
            ('المنطقة', 'address_area', 18, ''),
            ('نوع السكن', 'housing_type', 14, 'ملك / إيجار'),
            ('مبلغ الإيجار', 'rent_amount', 14, ''),
            # --- الحالة ---
            ('الحالة', 'status', 14, 'survivor / enforced / deceased'),
            ('الحالة الاجتماعية', 'marital', 16, 'أعزب / متزوج / أرمل / مطلق'),
            ('نوع القضية', 'case_type', 16, ''),
            # --- معلومات الاعتقال ---
            ('يوم الاعتقال', 'arrest_day', 12, '1'),
            ('شهر الاعتقال', 'arrest_month', 12, '3'),
            ('سنة الاعتقال', 'arrest_year', 12, '2012'),
            ('مكان الاعتقال', 'arrest_place', 22, ''),
            ('جهة الاعتقال', 'arrest_authority', 20, ''),
            ('سبب الاعتقال', 'arrest_reason', 22, ''),
            ('المتسبب بالاعتقال', 'arrest_causer', 20, ''),
            # --- الإفراج ---
            ('يوم الإفراج', 'release_day', 12, ''),
            ('شهر الإفراج', 'release_month', 12, ''),
            ('سنة الإفراج', 'release_year', 12, ''),
            # --- الوفاة ---
            ('يوم الوفاة', 'death_day', 12, ''),
            ('شهر الوفاة', 'death_month', 12, ''),
            ('سنة الوفاة', 'death_year', 12, ''),
            ('مكان الوفاة', 'death_place', 20, ''),
            # --- الأسرة ---
            ('اسم الزوج/ة', 'spouse_name', 20, ''),
            ('هاتف الزوج/ة', 'spouse_phone', 16, ''),
            ('لديه أطفال', 'has_kids', 12, 'نعم / لا'),
            ('عدد الأطفال', 'kids_count', 12, '3'),
            ('اسم الوصي', 'guardian_name', 20, ''),
            ('صلة الوصي', 'guardian_relation', 16, ''),
            ('هاتف الوصي', 'guardian_phone', 16, ''),
            # --- التعليم والعمل ---
            ('التعليم', 'education', 16, 'جامعي / ثانوي / إعدادي / ابتدائي'),
            ('نوع التعليم', 'edu_type', 16, ''),
            ('التخصص', 'edu_specialization', 18, ''),
            ('الجامعة/المعهد', 'edu_university', 20, ''),
            ('العمل', 'employment', 16, ''),
            ('المهنة', 'profession', 18, ''),
            ('جهة العمل', 'employer', 20, ''),
            # --- الصحة ---
            ('أمراض مزمنة', 'chronic', 20, ''),
            ('ضغط', 'has_hypertension', 10, '0 / 1'),
            ('سكري', 'has_diabetes', 10, '0 / 1'),
            ('احتياجات خاصة', 'has_special_needs', 14, '0 / 1'),
            ('تفاصيل الاحتياجات', 'special_needs_details', 22, ''),
            # --- المعيل ---
            ('المعيل', 'breadwinner', 14, ''),
            ('عمل المعيل', 'breadwinner_job', 18, ''),
            ('صلة المعيل', 'breadwinner_relation', 16, ''),
            # --- القانون ---
            ('وضع قانوني', 'legal', 14, ''),
            ('تفاصيل قانونية', 'legal_details', 22, ''),
            ('مسجل رسمياً', 'is_officially_registered', 14, '0 / 1'),
            # --- السجل المدني ---
            ('حالة السجل المدني', 'civil_registry_status', 18, ''),
            ('تاريخ السجل المدني', 'civil_registry_date', 16, ''),
            ('رقم دفتر العائلة', 'family_book_number', 16, ''),
            # --- المبلّغ ---
            ('اسم المبلّغ', 'reporter_name', 20, ''),
            ('صلة المبلّغ', 'reporter_relation', 16, ''),
            ('هاتف المبلّغ', 'reporter_phone', 16, ''),
            ('هوية المبلّغ', 'reporter_id', 16, ''),
            ('موافقة المبلّغ', 'informant_consent', 14, '0 / 1'),
            # --- التوثيق ---
            ('مستوى الأدلة', 'evidence_level', 16, 'unverified / low / medium / high'),
            ('نوع المصدر', 'source_type', 16, ''),
            ('تاريخ الجمع', 'collection_date', 14, '2024-01-15'),
            ('اسم الجامع', 'collector_name', 18, ''),
            ('ملاحظات المنهجية', 'methodology_notes', 24, ''),
            ('ملاحظات', 'notes', 28, ''),
        ]
        ws.title = 'سجلات'

    # --- Row 1: Arabic headers ---
    hfont = Font(bold=True, color='FFFFFF', size=11)
    hfill = PatternFill(start_color='1565C0', end_color='1565C0', fill_type='solid')
    thin_border = Border(
        left=Side(style='thin', color='CCCCCC'),
        right=Side(style='thin', color='CCCCCC'),
        bottom=Side(style='thin', color='CCCCCC'),
    )

    for i, (ar, en, width, hint) in enumerate(columns, 1):
        cell = ws.cell(row=1, column=i, value=ar)
        cell.font = hfont
        cell.fill = hfill
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = thin_border
        col_letter = cell.column_letter
        ws.column_dimensions[col_letter].width = width

    # --- Row 2: English column names (for developer reference) ---
    enfont = Font(italic=True, color='888888', size=9)
    enfill = PatternFill(start_color='E3F2FD', end_color='E3F2FD', fill_type='solid')
    for i, (ar, en, width, hint) in enumerate(columns, 1):
        cell = ws.cell(row=2, column=i, value=en)
        cell.font = enfont
        cell.fill = enfill
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin_border

    # --- Row 3: Example/hint values ---
    hintfont = Font(color='999999', size=9)
    for i, (ar, en, width, hint) in enumerate(columns, 1):
        if hint:
            cell = ws.cell(row=3, column=i, value=hint)
            cell.font = hintfont
            cell.alignment = Alignment(horizontal='center')
            cell.border = thin_border

    # Freeze header rows
    ws.freeze_panes = 'A4'

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name=f'template_{import_type}.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='HAQQUNA - Victim Documentation System')
    parser.add_argument('--ip', type=str, default='', help='Fixed IP address to bind/display (e.g. 192.168.1.100)')
    parser.add_argument('--port', type=int, default=0, help='Port number (default: 5000)')
    parser.add_argument('--init-db', action='store_true',
                        help='Initialize the database and set admin password, then exit')
    parser.add_argument('--reset-password', action='store_true',
                        help='Reset the admin password, then exit')
    args = parser.parse_args()

    # --- Init DB command: create fresh database + set admin password ---
    if args.init_db:
        print("\n" + "="*60)
        print("  HAQQUNA - Database Initialization")
        print("="*60)
        db_exists = os.path.exists(DB_PATH)
        if db_exists:
            size_kb = os.path.getsize(DB_PATH) / 1024
            print(f"  Database already exists: {DB_PATH} ({size_kb:.0f} KB)")
            print("  Running migrations to ensure schema is up-to-date...")
        else:
            print(f"  Creating new database: {DB_PATH}")
        migrate_db()
        record_count = 0
        try:
            conn = sqlite3.connect(DB_PATH)
            record_count = conn.execute("SELECT COUNT(*) FROM records WHERE deleted_at IS NULL").fetchone()[0]
            conn.close()
        except Exception:
            pass
        print(f"  Database ready. Records: {record_count}")
        print("="*60)
        # Set admin password
        pw = os.environ.get('HAQQUNA_DEFAULT_PASSWORD', '')
        if pw:
            print(f"  Using password from HAQQUNA_DEFAULT_PASSWORD env var.")
        else:
            import getpass
            try:
                pw = getpass.getpass("  Enter new admin password (min 6 chars): ")
                if len(pw) < 6:
                    print("  ERROR: Password must be at least 6 characters.")
                    sys.exit(1)
                pw2 = getpass.getpass("  Confirm password: ")
                if pw != pw2:
                    print("  ERROR: Passwords do not match.")
                    sys.exit(1)
            except (EOFError, KeyboardInterrupt):
                # Non-interactive: generate a random password
                pw = secrets.token_urlsafe(12)
                print(f"\n  (Non-interactive) Generated admin password: {pw}")
        _set_admin_password(pw)
        # Ensure admin user exists in users table
        conn = sqlite3.connect(DB_PATH)
        existing = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
        pw_hash = generate_password_hash(pw)
        if existing:
            conn.execute("UPDATE users SET password_hash=?, is_active=1 WHERE username='admin'", (pw_hash,))
        else:
            conn.execute(
                "INSERT INTO users (username, password_hash, display_name, role, is_active) VALUES (?,?,?,?,?)",
                ('admin', pw_hash, 'مدير النظام', 'admin', 1)
            )
        conn.commit()
        conn.close()
        print("  Admin password set successfully.")
        print(f"  Username: admin")
        print("="*60)
        print("  Run 'python app.py' to start the server.\n")
        sys.exit(0)

    # --- Reset password command ---
    if args.reset_password:
        print("\n" + "="*60)
        print("  HAQQUNA - Reset Admin Password")
        print("="*60)
        pw = os.environ.get('HAQQUNA_DEFAULT_PASSWORD', '')
        if pw:
            print(f"  Using password from HAQQUNA_DEFAULT_PASSWORD env var.")
        else:
            import getpass
            try:
                pw = getpass.getpass("  Enter new admin password (min 6 chars): ")
                if len(pw) < 6:
                    print("  ERROR: Password must be at least 6 characters.")
                    sys.exit(1)
                pw2 = getpass.getpass("  Confirm password: ")
                if pw != pw2:
                    print("  ERROR: Passwords do not match.")
                    sys.exit(1)
            except (EOFError, KeyboardInterrupt):
                pw = secrets.token_urlsafe(12)
                print(f"\n  (Non-interactive) Generated admin password: {pw}")
        _set_admin_password(pw)
        # Also update the users table
        if os.path.exists(DB_PATH):
            pw_hash = generate_password_hash(pw)
            conn = sqlite3.connect(DB_PATH)
            conn.execute("UPDATE users SET password_hash=? WHERE username='admin'", (pw_hash,))
            conn.commit()
            conn.close()
        print("  Admin password reset successfully.")
        print(f"  Username: admin")
        print("="*60 + "\n")
        sys.exit(0)

    migrate_db()

    # Load config: command-line args override config file
    cfg = load_server_config()
    fixed_ip = args.ip or cfg.get('fixed_ip', '')
    port = args.port or cfg.get('port', 5000)

    lan_ip = fixed_ip if fixed_ip else get_lan_ip()

    print("\n" + "="*60)
    print("  HAQQUNA - نظام توثيق الضحايا")
    print("  Berkeley Protocol Documentation System")
    print("="*60)
    print(f"  Local:      http://localhost:{port}")
    print(f"  Network:    http://{lan_ip}:{port}")
    if fixed_ip:
        print(f"  Fixed IP:   {fixed_ip} (configured)")
    print(f"  Admin:      http://{lan_ip}:{port}/admin")
    print(f"  Data Entry: http://{lan_ip}:{port}/entry")
    if not os.path.exists(ADMIN_PASSWORD_FILE):
        print(f"  NOTE:       No admin password set! Run: python app.py --init-db")
    else:
        print(f"  Password:   (stored in admin_password.hash)")
    print("="*60)
    print(f"  * Other devices on your network can connect using:")
    print(f"    http://{lan_ip}:{port}")
    if not fixed_ip:
        print(f"  * To set a fixed IP, run: python app.py --ip 192.168.1.100")
        print(f"    or configure in Admin > Server Config")
    print("="*60 + "\n")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
