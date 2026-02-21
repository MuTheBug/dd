#!/usr/bin/env python3
"""
HAQQUNA - Victim Documentation System
Based on the Berkeley Protocol on Digital Open Source Investigations
Fully offline system for documenting survivors, forcibly disappeared, and deceased victims.
"""

import os
import sys
import sqlite3
import hashlib
import json
import base64
import secrets
import time
from datetime import datetime
from functools import wraps
from io import BytesIO
from urllib.parse import quote

from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    jsonify, send_file, session, g, make_response, send_from_directory
)

# ---------------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'registry.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

ADMIN_PASSWORD = 'haqquna2024'

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
    ('other', 'أخرى')
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

REPORTER_RELATIONS = [
    'أم', 'أب', 'أخ', 'أخت', 'زوج/ة', 'ابن/ة', 'قريب',
    'صديق', 'جار', 'زميل', 'الشخص نفسه', 'أخرى'
]


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def migrate_db():
    """Ensure all Berkeley Protocol columns exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

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
    }

    for col, typedef in new_columns.items():
        if col not in existing:
            try:
                cursor.execute(f"ALTER TABLE records ADD COLUMN {col} {typedef}")
            except sqlite3.OperationalError:
                pass

    conn.commit()
    conn.close()


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
        'REPORTER_RELATIONS': REPORTER_RELATIONS,
    }


# ---------------------------------------------------------------------------
# Routes – Public data entry
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/entry', methods=['GET'])
def entry_form():
    return render_template('entry.html')


@app.route('/entry', methods=['POST'])
def entry_submit():
    db = get_db()
    form = request.form

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

    if 'digital_evidence_screenshot' in request.files:
        screenshot_path, _ = save_upload(request.files['digital_evidence_screenshot'], 'screenshots')
        screenshot_path = screenshot_path or ''

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

    # Determine record_slug
    slug = f"{form.get('first_name', '')}-{form.get('last_name', '')}-{int(time.time())}".replace(' ', '-')

    db.execute("""INSERT INTO records (
        first_name, father_name, last_name, gender, mother_name,
        birth_day, birth_month, birth_year, province, national_id,
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
        source_type, collection_date, collector_name,
        verification_status, methodology_notes,
        record_slug, photo_hash, document_hash,
        survivor_cv_path, survivor_cv_text, survivor_cv_photo_path
    ) VALUES (
        ?,?,?,?,?, ?,?,?,?,?, ?,?,?,?, ?,?,?,?,
        ?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?,?,
        ?,?,?,?, ?,?,?, ?,?,?,?, ?,?,?, ?,?,?,?,?,
        ?,?, ?,?,?,?, ?,?, ?,?,?,?,?, ?,
        ?,?,?,?,?, ?,?, ?,?,?, ?,?, ?,?, ?,
        ?,?,?, ?,?, ?,?, ?,?, ?,
        ?,?,?, ?,?, ?,?,?, ?,?,?
    )""", (
        form.get('first_name', ''), form.get('father_name', ''), form.get('last_name', ''),
        form.get('gender', ''), form.get('mother_name', ''),
        int(form.get('birth_day', 0) or 0), int(form.get('birth_month', 0) or 0),
        int(form.get('birth_year', 0) or 0),
        form.get('province', ''), form.get('national_id', ''),
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
        form.get('chronic', ''), form.get('diseases', ''),
        int(form.get('has_hypertension', 0) or 0),
        int(form.get('has_diabetes', 0) or 0), form.get('other_diseases', ''),
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
        form.get('source_type', ''), form.get('collection_date', ''),
        form.get('collector_name', ''),
        'Unverified', form.get('methodology_notes', ''),
        slug, photo_hash, doc_hash,
        cv_path, form.get('survivor_cv_text', ''), cv_photo_path
    ))
    db.commit()

    flash('تم حفظ السجل بنجاح. شكراً لمساهمتك في التوثيق.', 'success')
    return redirect(url_for('entry_form'))


# ---------------------------------------------------------------------------
# Routes – Admin
# ---------------------------------------------------------------------------
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))
        flash('كلمة المرور غير صحيحة', 'error')
    return render_template('admin_login.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))


@app.route('/admin')
@admin_required
def admin_dashboard():
    db = get_db()

    # Statistics
    total = db.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    survivors = db.execute("SELECT COUNT(*) FROM records WHERE status='survivor'").fetchone()[0]
    enforced = db.execute("SELECT COUNT(*) FROM records WHERE status='enforced'").fetchone()[0]
    deceased = db.execute("SELECT COUNT(*) FROM records WHERE status='deceased'").fetchone()[0]
    males = db.execute("SELECT COUNT(*) FROM records WHERE gender='male'").fetchone()[0]
    females = db.execute("SELECT COUNT(*) FROM records WHERE gender='female'").fetchone()[0]

    # Province distribution
    province_stats = db.execute(
        "SELECT province, COUNT(*) as cnt FROM records GROUP BY province ORDER BY cnt DESC"
    ).fetchall()

    # Authority distribution
    authority_stats = db.execute(
        "SELECT arrest_authority, COUNT(*) as cnt FROM records GROUP BY arrest_authority ORDER BY cnt DESC LIMIT 15"
    ).fetchall()

    # Year distribution
    year_stats = db.execute(
        "SELECT arrest_year, COUNT(*) as cnt FROM records WHERE arrest_year > 0 GROUP BY arrest_year ORDER BY arrest_year"
    ).fetchall()

    stats = {
        'total': total, 'survivors': survivors, 'enforced': enforced,
        'deceased': deceased, 'males': males, 'females': females,
        'province_stats': province_stats, 'authority_stats': authority_stats,
        'year_stats': year_stats
    }

    return render_template('admin_dashboard.html', stats=stats)


@app.route('/admin/records')
@admin_required
def admin_records():
    db = get_db()
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 25))

    # Build filter query
    conditions = []
    params = []

    filters = {
        'status': request.args.get('status', ''),
        'province': request.args.get('province', ''),
        'gender': request.args.get('gender', ''),
        'arrest_authority': request.args.get('arrest_authority', ''),
        'arrest_place': request.args.get('arrest_place', ''),
        'arrest_year_from': request.args.get('arrest_year_from', ''),
        'arrest_year_to': request.args.get('arrest_year_to', ''),
        'birth_year_from': request.args.get('birth_year_from', ''),
        'birth_year_to': request.args.get('birth_year_to', ''),
        'marital': request.args.get('marital', ''),
        'education': request.args.get('education', ''),
        'education_max': request.args.get('education_max', ''),
        'housing_type': request.args.get('housing_type', ''),
        'blood_type': request.args.get('blood_type', ''),
        'has_kids': request.args.get('has_kids', ''),
        'has_kids_under_18': request.args.get('has_kids_under_18', ''),
        'kids_max_age': request.args.get('kids_max_age', ''),
        'has_photo': request.args.get('has_photo', ''),
        'has_document': request.args.get('has_document', ''),
        'case_type': request.args.get('case_type', ''),
        'evidence_level': request.args.get('evidence_level', ''),
        'verification_status': request.args.get('verification_status', ''),
        'civil_registry_status': request.args.get('civil_registry_status', ''),
        'digital_evidence_type': request.args.get('digital_evidence_type', ''),
        'has_conflicting_info': request.args.get('has_conflicting_info', ''),
        'search': request.args.get('search', ''),
        'has_special_needs': request.args.get('has_special_needs', ''),
        'chronic': request.args.get('chronic', ''),
        'breadwinner': request.args.get('breadwinner', ''),
        'has_hypertension': request.args.get('has_hypertension', ''),
        'has_diabetes': request.args.get('has_diabetes', ''),
        'is_registered': request.args.get('is_registered', ''),
        'has_legal': request.args.get('has_legal', ''),
        'has_assoc': request.args.get('has_assoc', ''),
        'reporter_relation': request.args.get('reporter_relation', ''),
        'widows_filter': request.args.get('widows_filter', ''),
        'spouse_search': request.args.get('spouse_search', ''),
    }

    if filters['status']:
        conditions.append("status = ?")
        params.append(filters['status'])
    if filters['province']:
        conditions.append("province = ?")
        params.append(filters['province'])
    if filters['gender']:
        conditions.append("gender = ?")
        params.append(filters['gender'])
    if filters['arrest_authority']:
        conditions.append("arrest_authority LIKE ?")
        params.append(f"%{filters['arrest_authority']}%")
    if filters['arrest_place']:
        conditions.append("arrest_place LIKE ?")
        params.append(f"%{filters['arrest_place']}%")
    if filters['arrest_year_from']:
        conditions.append("arrest_year >= ?")
        params.append(int(filters['arrest_year_from']))
    if filters['arrest_year_to']:
        conditions.append("arrest_year <= ?")
        params.append(int(filters['arrest_year_to']))
    if filters['birth_year_from']:
        conditions.append("birth_year >= ?")
        params.append(int(filters['birth_year_from']))
    if filters['birth_year_to']:
        conditions.append("birth_year <= ?")
        params.append(int(filters['birth_year_to']))
    if filters['marital']:
        conditions.append("marital = ?")
        params.append(filters['marital'])
    if filters['education']:
        conditions.append("education = ?")
        params.append(filters['education'])
    if filters['education_max']:
        # Education levels ordered from lowest to highest
        edu_order = ['أمّي', 'ابتدائية', 'إعدادية', 'ثانوية', 'معهد', 'بكالوريوس', 'ماجستير', 'دكتوراه']
        try:
            max_idx = edu_order.index(filters['education_max'])
            included = edu_order[:max_idx + 1]
            placeholders = ','.join(['?'] * len(included))
            conditions.append(f"education IN ({placeholders})")
            params.extend(included)
        except ValueError:
            pass
    if filters['housing_type']:
        conditions.append("housing_type = ?")
        params.append(filters['housing_type'])
    if filters['blood_type']:
        conditions.append("blood_type = ?")
        params.append(filters['blood_type'])
    if filters['has_kids'] == 'yes':
        conditions.append("has_kids = 'yes'")
    elif filters['has_kids'] == 'no':
        conditions.append("(has_kids = 'no' OR has_kids IS NULL OR has_kids = '')")
    if filters['has_kids_under_18'] == 'yes':
        conditions.append("kids_under_18_count > 0")
    elif filters['has_kids_under_18'] == 'no':
        conditions.append("(kids_under_18_count = 0 OR kids_under_18_count IS NULL)")
    if filters['kids_max_age']:
        # Children born after (current_year - max_age) are under that age
        current_year = datetime.now().year
        min_birth_year = current_year - int(filters['kids_max_age'])
        # Check children_data JSON for children with birth year >= min_birth_year
        # Since children_data is JSON, we check kids_under_18_count as proxy
        # and also filter by the age threshold using birth year calculation
        conditions.append("kids_under_18_count > 0")
    if filters['has_photo'] == 'yes':
        conditions.append("photo_path IS NOT NULL AND photo_path != ''")
    elif filters['has_photo'] == 'no':
        conditions.append("(photo_path IS NULL OR photo_path = '')")
    if filters['has_document'] == 'yes':
        conditions.append("document_path IS NOT NULL AND document_path != ''")
    elif filters['has_document'] == 'no':
        conditions.append("(document_path IS NULL OR document_path = '')")
    if filters['case_type']:
        conditions.append("case_type = ?")
        params.append(filters['case_type'])
    if filters['evidence_level']:
        conditions.append("evidence_level = ?")
        params.append(filters['evidence_level'])
    if filters['verification_status']:
        conditions.append("verification_status = ?")
        params.append(filters['verification_status'])
    if filters['civil_registry_status']:
        conditions.append("civil_registry_status = ?")
        params.append(filters['civil_registry_status'])
    if filters['digital_evidence_type']:
        conditions.append("digital_evidence_type = ?")
        params.append(filters['digital_evidence_type'])
    if filters['has_conflicting_info'] == '1':
        conditions.append("has_conflicting_info = 1")
    if filters['has_special_needs'] == '1':
        conditions.append("has_special_needs = 1")
    if filters['chronic'] == 'yes':
        conditions.append("chronic = 'نعم'")
    if filters['breadwinner']:
        conditions.append("breadwinner LIKE ?")
        params.append(f"%{filters['breadwinner']}%")
    if filters['has_hypertension'] == '1':
        conditions.append("has_hypertension = 1")
    if filters['has_diabetes'] == '1':
        conditions.append("has_diabetes = 1")
    if filters['is_registered'] == '1':
        conditions.append("is_officially_registered = 1")
    elif filters['is_registered'] == '0':
        conditions.append("(is_officially_registered = 0 OR is_officially_registered IS NULL)")
    if filters['has_legal'] == 'yes':
        conditions.append("legal = 'نعم'")
    if filters['has_assoc'] == 'yes':
        conditions.append("assoc = 'نعم'")
    if filters['reporter_relation']:
        conditions.append("reporter_relation = ?")
        params.append(filters['reporter_relation'])
    if filters['widows_filter'] == 'widows_deceased':
        # Widows of deceased detainees: male detainee died + was married
        conditions.append("status IN ('deceased') AND gender = 'male' AND marital = 'married'")
    elif filters['widows_filter'] == 'widows_enforced':
        # Wives of forcibly disappeared: male detainee enforced + married
        conditions.append("status = 'enforced' AND gender = 'male' AND marital = 'married'")
    elif filters['widows_filter'] == 'widows_all':
        # All widows (deceased or enforced, married males)
        conditions.append("status IN ('deceased', 'enforced') AND gender = 'male' AND marital = 'married'")
    elif filters['widows_filter'] == 'widows_with_minors':
        # Widows with minor children
        conditions.append("status IN ('deceased', 'enforced') AND gender = 'male' AND marital = 'married' AND kids_under_18_count > 0")
    if filters['spouse_search']:
        conditions.append("spouse_name LIKE ?")
        params.append(f"%{filters['spouse_search']}%")
    if filters['search']:
        search_term = f"%{filters['search']}%"
        conditions.append("""(
            first_name LIKE ? OR father_name LIKE ? OR last_name LIKE ?
            OR mother_name LIKE ? OR national_id LIKE ? OR phone LIKE ?
            OR address LIKE ? OR notes LIKE ? OR reporter_name LIKE ?
        )""")
        params.extend([search_term] * 9)

    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    # Count
    count = db.execute(f"SELECT COUNT(*) FROM records{where}", params).fetchone()[0]

    # Sort
    sort_by = request.args.get('sort', 'id')
    sort_dir = request.args.get('dir', 'desc')
    allowed_sorts = ['id', 'first_name', 'last_name', 'status', 'province', 'arrest_year', 'created_at']
    if sort_by not in allowed_sorts:
        sort_by = 'id'
    if sort_dir not in ('asc', 'desc'):
        sort_dir = 'desc'

    offset = (page - 1) * per_page
    records = db.execute(
        f"SELECT * FROM records{where} ORDER BY {sort_by} {sort_dir} LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()

    total_pages = (count + per_page - 1) // per_page

    # Build filter_params for URL generation in templates
    filter_params = {k: v for k, v in filters.items() if v}

    return render_template('admin_records.html',
        records=records, filters=filters, page=page,
        per_page=per_page, total_pages=total_pages, total_count=count,
        sort_by=sort_by, sort_dir=sort_dir, filter_params=filter_params
    )


@app.route('/admin/record/<int:record_id>')
@admin_required
def admin_record_detail(record_id):
    db = get_db()
    record = db.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
    if not record:
        flash('السجل غير موجود', 'error')
        return redirect(url_for('admin_records'))
    return render_template('admin_record_detail.html', record=record)


@app.route('/admin/record/<int:record_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_record_edit(record_id):
    db = get_db()
    record = db.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
    if not record:
        flash('السجل غير موجود', 'error')
        return redirect(url_for('admin_records'))

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

        db.execute("""UPDATE records SET
            first_name=?, father_name=?, last_name=?, gender=?, mother_name=?,
            birth_day=?, birth_month=?, birth_year=?, province=?, national_id=?,
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
            source_type=?, collection_date=?, collector_name=?,
            verification_status=?, methodology_notes=?,
            photo_hash=?, document_hash=?,
            survivor_cv_path=?, survivor_cv_text=?, survivor_cv_photo_path=?
        WHERE id=?""", (
            form.get('first_name', ''), form.get('father_name', ''), form.get('last_name', ''),
            form.get('gender', ''), form.get('mother_name', ''),
            int(form.get('birth_day', 0) or 0), int(form.get('birth_month', 0) or 0),
            int(form.get('birth_year', 0) or 0),
            form.get('province', ''), form.get('national_id', ''),
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
            form.get('chronic', ''), form.get('diseases', ''),
            int(form.get('has_hypertension', 0) or 0),
            int(form.get('has_diabetes', 0) or 0), form.get('other_diseases', ''),
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
            form.get('source_type', ''), form.get('collection_date', ''),
            form.get('collector_name', ''),
            form.get('verification_status', 'Unverified'),
            form.get('methodology_notes', ''),
            photo_hash, doc_hash,
            cv_path, form.get('survivor_cv_text', ''), cv_photo_path,
            record_id
        ))
        db.commit()
        flash('تم تحديث السجل بنجاح', 'success')
        return redirect(url_for('admin_record_detail', record_id=record_id))

    return render_template('admin_record_edit.html', record=record)


@app.route('/admin/record/<int:record_id>/delete', methods=['POST'])
@admin_required
def admin_record_delete(record_id):
    db = get_db()
    db.execute("DELETE FROM records WHERE id = ?", (record_id,))
    db.commit()
    flash('تم حذف السجل', 'success')
    return redirect(url_for('admin_records'))


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


@app.route('/admin/records/pdf')
@admin_required
def records_list_pdf():
    db = get_db()

    # Apply same filters as records page
    conditions = []
    params = []

    for key in ['status', 'province', 'gender', 'marital', 'education', 'housing_type', 'blood_type',
                'case_type', 'evidence_level', 'verification_status', 'civil_registry_status']:
        val = request.args.get(key, '')
        if val:
            conditions.append(f"{key} = ?")
            params.append(val)

    if request.args.get('arrest_authority'):
        conditions.append("arrest_authority LIKE ?")
        params.append(f"%{request.args['arrest_authority']}%")
    if request.args.get('arrest_place'):
        conditions.append("arrest_place LIKE ?")
        params.append(f"%{request.args['arrest_place']}%")
    if request.args.get('search'):
        s = f"%{request.args['search']}%"
        conditions.append("(first_name LIKE ? OR last_name LIKE ? OR national_id LIKE ?)")
        params.extend([s, s, s])
    if request.args.get('arrest_year_from'):
        conditions.append("arrest_year >= ?")
        params.append(int(request.args['arrest_year_from']))
    if request.args.get('arrest_year_to'):
        conditions.append("arrest_year <= ?")
        params.append(int(request.args['arrest_year_to']))
    if request.args.get('birth_year_from'):
        conditions.append("birth_year >= ?")
        params.append(int(request.args['birth_year_from']))
    if request.args.get('birth_year_to'):
        conditions.append("birth_year <= ?")
        params.append(int(request.args['birth_year_to']))
    if request.args.get('has_kids') == 'yes':
        conditions.append("has_kids = 'yes'")
    if request.args.get('has_kids_under_18') == 'yes':
        conditions.append("kids_under_18_count > 0")
    if request.args.get('has_special_needs') == '1':
        conditions.append("has_special_needs = 1")
    if request.args.get('chronic') == 'yes':
        conditions.append("chronic = 'نعم'")
    if request.args.get('has_hypertension') == '1':
        conditions.append("has_hypertension = 1")
    if request.args.get('has_diabetes') == '1':
        conditions.append("has_diabetes = 1")
    if request.args.get('has_conflicting_info') == '1':
        conditions.append("has_conflicting_info = 1")
    if request.args.get('is_registered') == '1':
        conditions.append("is_officially_registered = 1")
    if request.args.get('has_legal') == 'yes':
        conditions.append("legal = 'نعم'")
    if request.args.get('has_assoc') == 'yes':
        conditions.append("assoc = 'نعم'")
    if request.args.get('reporter_relation'):
        conditions.append("reporter_relation = ?")
        params.append(request.args['reporter_relation'])
    if request.args.get('education_max'):
        edu_order = ['أمّي', 'ابتدائية', 'إعدادية', 'ثانوية', 'معهد', 'بكالوريوس', 'ماجستير', 'دكتوراه']
        try:
            max_idx = edu_order.index(request.args['education_max'])
            included = edu_order[:max_idx + 1]
            placeholders = ','.join(['?'] * len(included))
            conditions.append(f"education IN ({placeholders})")
            params.extend(included)
        except ValueError:
            pass
    widows_f = request.args.get('widows_filter', '')
    if widows_f == 'widows_deceased':
        conditions.append("status IN ('deceased') AND gender = 'male' AND marital = 'married'")
    elif widows_f == 'widows_enforced':
        conditions.append("status = 'enforced' AND gender = 'male' AND marital = 'married'")
    elif widows_f == 'widows_all':
        conditions.append("status IN ('deceased', 'enforced') AND gender = 'male' AND marital = 'married'")
    elif widows_f == 'widows_with_minors':
        conditions.append("status IN ('deceased', 'enforced') AND gender = 'male' AND marital = 'married' AND kids_under_18_count > 0")
    if request.args.get('spouse_search'):
        conditions.append("spouse_name LIKE ?")
        params.append(f"%{request.args['spouse_search']}%")

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    records = db.execute(
        f"SELECT * FROM records{where} ORDER BY id DESC LIMIT 500", params
    ).fetchall()

    logo_path = os.path.join(BASE_DIR, 'logo.jpg')
    logo_b64 = ''
    if os.path.exists(logo_path):
        with open(logo_path, 'rb') as f:
            logo_b64 = base64.b64encode(f.read()).decode()

    # Build filter description
    filter_desc = []
    if request.args.get('status'):
        filter_desc.append(f"الحالة: {STATUS_MAP.get(request.args['status'], request.args['status'])}")
    if request.args.get('province'):
        filter_desc.append(f"المحافظة: {request.args['province']}")
    if request.args.get('gender'):
        filter_desc.append(f"الجنس: {'ذكر' if request.args['gender']=='male' else 'أنثى'}")
    if request.args.get('marital'):
        marital_map = dict(MARITAL_STATUSES)
        filter_desc.append(f"الحالة الاجتماعية: {marital_map.get(request.args['marital'], request.args['marital'])}")
    if request.args.get('education') or request.args.get('education_max'):
        edu_val = request.args.get('education') or f"حتى {request.args.get('education_max')}"
        filter_desc.append(f"التحصيل العلمي: {edu_val}")
    if request.args.get('has_kids_under_18') == 'yes':
        filter_desc.append("لديه أطفال قاصرين")
    if request.args.get('has_special_needs') == '1':
        filter_desc.append("ذوي احتياجات خاصة")
    if widows_f:
        widows_labels = {
            'widows_deceased': 'أرامل الشهداء',
            'widows_enforced': 'زوجات المغيّبين',
            'widows_all': 'جميع الأرامل',
            'widows_with_minors': 'أرامل لديهم قاصرين',
        }
        filter_desc.append(widows_labels.get(widows_f, widows_f))
    if request.args.get('has_hypertension') == '1':
        filter_desc.append("ضغط دم")
    if request.args.get('has_diabetes') == '1':
        filter_desc.append("سكري")
    if request.args.get('chronic') == 'yes':
        filter_desc.append("أمراض مزمنة")

    html = render_template('pdf_list.html',
        records=records, logo_b64=logo_b64, filter_desc=filter_desc,
        total=len(records))

    from weasyprint import HTML
    pdf_bytes = HTML(string=html, base_url=BASE_DIR).write_pdf()

    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename=records_report_{int(time.time())}.pdf'
    return response


# ---------------------------------------------------------------------------
# API endpoints for dynamic data
# ---------------------------------------------------------------------------
@app.route('/api/stats')
def api_stats():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    survivors = db.execute("SELECT COUNT(*) FROM records WHERE status='survivor'").fetchone()[0]
    enforced = db.execute("SELECT COUNT(*) FROM records WHERE status='enforced'").fetchone()[0]
    deceased = db.execute("SELECT COUNT(*) FROM records WHERE status='deceased'").fetchone()[0]
    return jsonify({
        'total': total, 'survivors': survivors,
        'enforced': enforced, 'deceased': deceased
    })


# ---------------------------------------------------------------------------
# Uploaded files serving
# ---------------------------------------------------------------------------
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    migrate_db()
    print("\n" + "="*60)
    print("  HAQQUNA - نظام توثيق الضحايا")
    print("  Berkeley Protocol Documentation System")
    print("="*60)
    print(f"  Admin:      http://0.0.0.0:5000/admin")
    print(f"  Data Entry: http://0.0.0.0:5000/entry")
    print(f"  Password:   {ADMIN_PASSWORD}")
    print("="*60 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=False)
