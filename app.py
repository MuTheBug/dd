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
app.secret_key = secrets.token_hex(32)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB per request
app.permanent_session_lifetime = timedelta(hours=8)


@app.before_request
def check_session_timeout():
    """Auto-logout after 8 hours of inactivity."""
    if session.get('is_admin') and session.get('login_time'):
        if time.time() - session['login_time'] > 8 * 3600:
            session.clear()
            flash('انتهت الجلسة، يرجى تسجيل الدخول مجدداً', 'error')
            return redirect(url_for('admin_login'))

ADMIN_PASSWORD_FILE = os.path.join(BASE_DIR, 'admin_password.hash')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')


def _get_admin_password_hash():
    """Read the hashed admin password from file, create default if missing."""
    if os.path.exists(ADMIN_PASSWORD_FILE):
        with open(ADMIN_PASSWORD_FILE, 'r') as f:
            return f.read().strip()
    # First run: create default hashed password
    default_hash = generate_password_hash('haqquna2024')
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


def log_audit(action, entity_type, entity_id=None, details=''):
    """Log an admin action to the audit trail."""
    try:
        db = get_db()
        ip = request.remote_addr if request else ''
        db.execute("INSERT INTO audit_log (action, entity_type, entity_id, details, ip_address) VALUES (?,?,?,?,?)",
                   (action, entity_type, entity_id, details, ip))
        db.commit()
    except Exception:
        pass  # Never let audit logging break the main operation


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
        'CHRONIC_DISEASES': CHRONIC_DISEASES,
        'REPORTER_RELATIONS': REPORTER_RELATIONS,
        'PDF_COLUMNS': PDF_COLUMNS,
        'DEFAULT_PDF_COLS': DEFAULT_PDF_COLS,
        'VOLUNTEER_STATUSES': VOLUNTEER_STATUSES,
        'VOLUNTEER_ROLES': VOLUNTEER_ROLES,
        'MEMBER_STATUSES': MEMBER_STATUSES,
        'MEMBERSHIP_TYPES': MEMBERSHIP_TYPES,
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
# Routes – Public data entry
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/entry', methods=['GET'])
def entry_form():
    db = get_db()
    volunteer_names = db.execute(
        "SELECT DISTINCT full_name FROM (SELECT full_name FROM volunteers WHERE status='active' UNION SELECT full_name FROM members WHERE status='active') ORDER BY full_name"
    ).fetchall()
    return render_template('entry.html', volunteer_names=[v['full_name'] for v in volunteer_names])


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

    # Date logic
    birth_year = int(form.get('birth_year', 0) or 0)
    arrest_year = int(form.get('arrest_year', 0) or 0)
    death_year = int(form.get('death_year', 0) or 0)
    release_year = int(form.get('release_year', 0) or 0)

    if birth_year and death_year and death_year < birth_year:
        errors.append('سنة الوفاة لا يمكن أن تكون قبل سنة الميلاد')
    if birth_year and arrest_year and arrest_year < birth_year:
        errors.append('سنة الاعتقال لا يمكن أن تكون قبل سنة الميلاد')
    if arrest_year and release_year and release_year < arrest_year:
        errors.append('سنة الإفراج لا يمكن أن تكون قبل سنة الاعتقال')

    return errors, warnings


@app.route('/entry', methods=['POST'])
def entry_submit():
    db = get_db()
    form = request.form
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    force = form.get('force', '') == 'true'

    # Validate
    errors, warnings = _validate_entry(form)
    if errors and not force:
        if is_ajax:
            return jsonify({'success': False, 'errors': errors, 'warnings': warnings})
        for e in errors:
            flash(e, 'error')
        return redirect(url_for('entry_form'))

    # Duplicate detection
    if not force:
        first = form.get('first_name', '').strip()
        father = form.get('father_name', '').strip()
        last = form.get('last_name', '').strip()
        nid = form.get('national_id', '').strip()
        dup = None
        if nid:
            dup = db.execute("SELECT id, first_name, father_name, last_name FROM records WHERE national_id=? AND national_id != ''", (nid,)).fetchone()
        if not dup and first and last:
            dup = db.execute("SELECT id, first_name, father_name, last_name FROM records WHERE first_name=? AND father_name=? AND last_name=?",
                             (first, father, last)).fetchone()
        if dup:
            dup_name = ' '.join(filter(None, [dup['first_name'], dup['father_name'], dup['last_name']]))
            msg = f'يوجد سجل مشابه: {dup_name} (#{dup["id"]}). أضف force=true للحفظ رغم ذلك.'
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

    # Process chronic diseases checkboxes
    chronic_list = form.getlist('chronic_list')
    chronic_value = '، '.join(chronic_list) if chronic_list else form.get('chronic', '')
    has_hypertension = 1 if 'ضغط الدم' in chronic_list else int(form.get('has_hypertension', 0) or 0)
    has_diabetes = 1 if 'السكري' in chronic_list else int(form.get('has_diabetes', 0) or 0)

    # Determine record_slug
    slug = f"{form.get('first_name', '')}-{form.get('last_name', '')}-{int(time.time())}".replace(' ', '-')

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
        source_type, collection_date, collector_name,
        verification_status, methodology_notes,
        record_slug, photo_hash, document_hash,
        survivor_cv_path, survivor_cv_text, survivor_cv_photo_path
    ) VALUES (
        ?,?,?,?,?, ?,?,?,?,?,?, ?,?,?,?, ?,?,?,?,
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
        form.get('source_type', ''), form.get('collection_date', ''),
        form.get('collector_name', ''),
        'Unverified', form.get('methodology_notes', ''),
        slug, photo_hash, doc_hash,
        cv_path, form.get('survivor_cv_text', ''), cv_photo_path
    ))

    # Use retry logic for concurrent access
    for attempt in range(3):
        try:
            db.commit()
            break
        except sqlite3.OperationalError as e:
            if 'locked' in str(e) and attempt < 2:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise

    log_audit('record_create', 'record', details=form.get('first_name', '') + ' ' + form.get('last_name', ''))
    resp_msg = 'تم حفظ السجل بنجاح. شكراً لمساهمتك في التوثيق.'
    if warnings:
        resp_msg += ' (تنبيهات: ' + '، '.join(warnings) + ')'
    if is_ajax:
        return jsonify({'success': True, 'message': resp_msg, 'warnings': warnings})

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

        pw_hash = _get_admin_password_hash()
        if check_password_hash(pw_hash, request.form.get('password', '')):
            session['is_admin'] = True
            session['login_time'] = time.time()
            session.permanent = True
            _login_attempts.pop(ip, None)
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

    # Authority distribution (with normalization of aliases)
    raw_authority_stats = db.execute(
        "SELECT arrest_authority, COUNT(*) as cnt FROM records WHERE arrest_authority IS NOT NULL AND arrest_authority != '' GROUP BY arrest_authority ORDER BY cnt DESC"
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
        "SELECT arrest_year, COUNT(*) as cnt FROM records WHERE arrest_year > 0 GROUP BY arrest_year ORDER BY arrest_year"
    ).fetchall()

    # Age distribution (D2)
    current_year = datetime.now().year
    age_brackets = {'0-17': 0, '18-30': 0, '31-45': 0, '46-60': 0, '60+': 0, 'غير محدد': 0}
    birth_years = db.execute("SELECT birth_year FROM records").fetchall()
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

    # Health & vulnerability stats (D3)
    health_stats = {
        'chronic': db.execute("SELECT COUNT(*) FROM records WHERE chronic IS NOT NULL AND chronic != '' AND chronic != 'لا'").fetchone()[0],
        'special_needs': db.execute("SELECT COUNT(*) FROM records WHERE has_special_needs = 1").fetchone()[0],
        'hypertension': db.execute("SELECT COUNT(*) FROM records WHERE has_hypertension = 1").fetchone()[0],
        'diabetes': db.execute("SELECT COUNT(*) FROM records WHERE has_diabetes = 1").fetchone()[0],
        'paying_rent': db.execute("SELECT COUNT(*) FROM records WHERE housing_type = 'إيجار'").fetchone()[0],
        'no_breadwinner': db.execute("SELECT COUNT(*) FROM records WHERE breadwinner = '' OR breadwinner = 'لا يوجد' OR breadwinner IS NULL").fetchone()[0],
    }

    # Education breakdown (D4)
    edu_stats = db.execute(
        "SELECT education, COUNT(*) as cnt FROM records WHERE education IS NOT NULL AND education != '' GROUP BY education ORDER BY cnt DESC"
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
    except Exception:
        pass

    # Volunteer summary (D6)
    vol_stats = {
        'active': db.execute("SELECT COUNT(*) FROM volunteers WHERE status='active'").fetchone()[0],
        'total_hours': 0,
        'total_activities': db.execute("SELECT COUNT(*) FROM volunteer_activities").fetchone()[0],
    }
    try:
        h = db.execute("SELECT SUM(hours) FROM volunteer_attendance").fetchone()[0]
        vol_stats['total_hours'] = round(h or 0, 1)
    except Exception:
        pass

    # Data completeness (D1) - quick count
    total_profiles = total + vol_stats['active'] + db.execute("SELECT COUNT(*) FROM members").fetchone()[0]
    # Simplified: count records with key missing fields
    incomplete_records = db.execute(
        "SELECT COUNT(*) FROM records WHERE first_name='' OR status='' OR province='' OR gender='' OR phone='' OR national_id=''"
    ).fetchone()[0]
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
    conditions = []
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

    # Build filter query
    conditions = []
    params = []

    # Status supports multi-select (via checkboxes or comma-separated)
    status_list = request.args.getlist('status')
    # Also handle comma-separated values (from pagination URLs)
    expanded = []
    for s in status_list:
        if ',' in s:
            expanded.extend(s.split(','))
        elif s:
            expanded.append(s)
    status_list = expanded

    filters = {
        'status': ','.join(status_list),  # kept for backward compat
        'status_list': status_list,
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
        'minor_age_threshold': request.args.get('minor_age_threshold', ''),
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
        'child_name_search': request.args.get('child_name_search', ''),
        'child_education': request.args.get('child_education', ''),
        'employment': request.args.get('employment', ''),
        'profession': request.args.get('profession', ''),
        'address_search': request.args.get('address_search', ''),
        'arrest_reason': request.args.get('arrest_reason', ''),
        'death_year_from': request.args.get('death_year_from', ''),
        'death_year_to': request.args.get('death_year_to', ''),
        'release_year_from': request.args.get('release_year_from', ''),
        'release_year_to': request.args.get('release_year_to', ''),
        'notes_search': request.args.get('notes_search', ''),
        'employer': request.args.get('employer', ''),
        'breadwinner_relation': request.args.get('breadwinner_relation', ''),
        'age_from': request.args.get('age_from', ''),
        'age_to': request.args.get('age_to', ''),
        'has_guardian': request.args.get('has_guardian', ''),
        'digital_evidence_url_status': request.args.get('digital_evidence_url_status', ''),
        'kids_age_from': request.args.get('kids_age_from', ''),
        'kids_age_to': request.args.get('kids_age_to', ''),
        'collector_name': request.args.get('collector_name', ''),
        'sort_by_need': request.args.get('sort_by_need', ''),
        'created_from': request.args.get('created_from', ''),
        'created_to': request.args.get('created_to', ''),
        'collection_date_from': request.args.get('collection_date_from', ''),
        'collection_date_to': request.args.get('collection_date_to', ''),
        'source_type': request.args.get('source_type', ''),
        'has_phone': request.args.get('has_phone', ''),
        'family_book_number': request.args.get('family_book_number', ''),
        'national_id_search': request.args.get('national_id_search', ''),
        'has_rent': request.args.get('has_rent', ''),
        'detention_facility_search': request.args.get('detention_facility_search', ''),
        'record_status': request.args.get('record_status', ''),
        'service_name': request.args.get('service_name', ''),
        'service_count_min': request.args.get('service_count_min', ''),
        'service_provider': request.args.get('service_provider', ''),
        'last_service_from': request.args.get('last_service_from', ''),
        'last_service_to': request.args.get('last_service_to', ''),
        'service_filter_mode': request.args.get('service_filter_mode', ''),
    }

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


@app.route('/api/records')
@admin_required
def api_records():
    """AJAX endpoint for filtering records without full page reload."""
    db = get_db()
    page = safe_int(request.args.get('page'), 1)
    per_page = safe_int(request.args.get('per_page'), 25)

    # Reuse the same filter logic as admin_records
    conditions = []
    params = []

    status_list = request.args.getlist('status')
    expanded = []
    for s in status_list:
        if ',' in s:
            expanded.extend(s.split(','))
        elif s:
            expanded.append(s)
    status_list = expanded

    # Simple equality filters
    simple_filters = {
        'province': 'province', 'gender': 'gender', 'marital': 'marital',
        'education': 'education', 'housing_type': 'housing_type',
        'blood_type': 'blood_type', 'case_type': 'case_type',
        'evidence_level': 'evidence_level', 'verification_status': 'verification_status',
        'civil_registry_status': 'civil_registry_status',
        'digital_evidence_type': 'digital_evidence_type',
        'reporter_relation': 'reporter_relation', 'collector_name': 'collector_name',
        'breadwinner_relation': 'breadwinner_relation',
        'digital_evidence_url_status': 'digital_evidence_url_status',
        'record_status': 'record_status',
    }

    if status_list:
        if len(status_list) == 1:
            conditions.append("status = ?")
            params.append(status_list[0])
        else:
            placeholders = ','.join(['?'] * len(status_list))
            conditions.append(f"status IN ({placeholders})")
            params.extend(status_list)

    for param_name, col_name in simple_filters.items():
        val = request.args.get(param_name, '')
        if val:
            conditions.append(f"{col_name} = ?")
            params.append(val)

    # LIKE filters
    like_filters = {
        'spouse_search': 'spouse_name', 'child_name_search': 'children_data',
        'child_education': 'children_data', 'employment': 'employment',
        'profession': 'profession', 'address_search': 'address',
        'arrest_reason': 'arrest_reason', 'employer': 'employer',
        'breadwinner': 'breadwinner', 'family_book_number': 'family_book_number',
        'national_id_search': 'national_id', 'detention_facility_search': 'detention_facilities_data',
        'arrest_place': 'arrest_place',
    }
    for param_name, col_name in like_filters.items():
        val = request.args.get(param_name, '')
        if val:
            conditions.append(f"{col_name} LIKE ?")
            params.append(f"%{val}%")

    # Range filters
    range_filters = [
        ('arrest_year_from', 'arrest_year', '>='), ('arrest_year_to', 'arrest_year', '<='),
        ('birth_year_from', 'birth_year', '>='), ('birth_year_to', 'birth_year', '<='),
        ('death_year_from', 'death_year', '>='), ('death_year_to', 'death_year', '<='),
        ('release_year_from', 'release_year', '>='), ('release_year_to', 'release_year', '<='),
    ]
    for param_name, col_name, op in range_filters:
        val = request.args.get(param_name, '')
        if val:
            conditions.append(f"{col_name} {op} ?")
            params.append(int(val))

    # Date range filters
    if request.args.get('created_from'):
        conditions.append("created_at >= ?")
        params.append(request.args['created_from'])
    if request.args.get('created_to'):
        conditions.append("created_at <= ?")
        params.append(request.args['created_to'] + ' 23:59:59')
    if request.args.get('collection_date_from'):
        conditions.append("collection_date >= ?")
        params.append(request.args['collection_date_from'])
    if request.args.get('collection_date_to'):
        conditions.append("collection_date <= ?")
        params.append(request.args['collection_date_to'])

    # Boolean/special filters
    if request.args.get('has_conflicting_info') == '1':
        conditions.append("has_conflicting_info = 1")
    if request.args.get('has_special_needs') == '1':
        conditions.append("has_special_needs = 1")
    if request.args.get('has_hypertension') == '1':
        conditions.append("has_hypertension = 1")
    if request.args.get('has_diabetes') == '1':
        conditions.append("has_diabetes = 1")
    if request.args.get('chronic') == 'yes':
        conditions.append("(chronic = 'نعم' OR has_hypertension = 1 OR has_diabetes = 1 OR (other_diseases IS NOT NULL AND other_diseases != ''))")
    if request.args.get('has_kids') == 'yes':
        conditions.append("has_kids = 'yes'")
    elif request.args.get('has_kids') == 'no':
        conditions.append("(has_kids = 'no' OR has_kids IS NULL OR has_kids = '')")
    if request.args.get('has_kids_under_18') == 'yes':
        conditions.append("kids_under_18_count > 0")
    elif request.args.get('has_kids_under_18') == 'no':
        conditions.append("(kids_under_18_count = 0 OR kids_under_18_count IS NULL)")
    if request.args.get('has_photo') == 'yes':
        conditions.append("photo_path IS NOT NULL AND photo_path != ''")
    elif request.args.get('has_photo') == 'no':
        conditions.append("(photo_path IS NULL OR photo_path = '')")
    if request.args.get('has_document') == 'yes':
        conditions.append("document_path IS NOT NULL AND document_path != ''")
    elif request.args.get('has_document') == 'no':
        conditions.append("(document_path IS NULL OR document_path = '')")
    if request.args.get('is_registered') == '1':
        conditions.append("is_officially_registered = 1")
    elif request.args.get('is_registered') == '0':
        conditions.append("(is_officially_registered = 0 OR is_officially_registered IS NULL)")
    if request.args.get('has_legal') == 'yes':
        conditions.append("legal = 'نعم'")
    if request.args.get('has_assoc') == 'yes':
        conditions.append("assoc = 'yes'")
    elif request.args.get('has_assoc') == 'no':
        conditions.append("(assoc != 'yes' OR assoc IS NULL OR assoc = '')")
    if request.args.get('has_phone') == 'yes':
        conditions.append("(phone IS NOT NULL AND phone != '')")
    elif request.args.get('has_phone') == 'no':
        conditions.append("(phone IS NULL OR phone = '')")
    if request.args.get('has_rent') == 'yes':
        conditions.append("rent_amount IS NOT NULL AND rent_amount != '' AND rent_amount != '0'")
    elif request.args.get('has_rent') == 'no':
        conditions.append("(rent_amount IS NULL OR rent_amount = '' OR rent_amount = '0')")
    if request.args.get('has_guardian') == 'yes':
        conditions.append("guardian_name IS NOT NULL AND guardian_name != ''")
    elif request.args.get('has_guardian') == 'no':
        conditions.append("(guardian_name IS NULL OR guardian_name = '')")

    # Widows filter
    wf = request.args.get('widows_filter', '')
    if wf == 'widows_deceased':
        conditions.append("status IN ('deceased') AND gender = 'male' AND marital = 'married'")
    elif wf == 'widows_enforced':
        conditions.append("status = 'enforced' AND gender = 'male' AND marital = 'married'")
    elif wf == 'widows_all':
        conditions.append("status IN ('deceased', 'enforced') AND gender = 'male' AND marital = 'married'")
    elif wf == 'widows_with_minors':
        conditions.append("status IN ('deceased', 'enforced') AND gender = 'male' AND marital = 'married' AND kids_under_18_count > 0")

    # Notes search
    if request.args.get('notes_search'):
        conditions.append("(notes LIKE ? OR methodology_notes LIKE ?)")
        params.extend([f"%{request.args['notes_search']}%"] * 2)

    # Text search
    search = request.args.get('search', '')
    if search:
        search_term = f"%{search}%"
        conditions.append("""(
            first_name LIKE ? OR father_name LIKE ? OR last_name LIKE ?
            OR mother_name LIKE ? OR national_id LIKE ? OR phone LIKE ?
            OR address LIKE ? OR notes LIKE ? OR reporter_name LIKE ?
            OR (COALESCE(first_name,'') || ' ' || COALESCE(father_name,'') || ' ' || COALESCE(last_name,'')) LIKE ?
        )""")
        params.extend([search_term] * 10)

    # Age range
    if request.args.get('age_from') and safe_int(request.args['age_from']) is not None:
        current_year = datetime.now().year
        max_birth_year = current_year - safe_int(request.args['age_from'])
        conditions.append("birth_year <= ? AND birth_year > 0")
        params.append(max_birth_year)
    if request.args.get('age_to') and safe_int(request.args['age_to']) is not None:
        current_year = datetime.now().year
        min_birth_year = current_year - safe_int(request.args['age_to'])
        conditions.append("birth_year >= ?")
        params.append(min_birth_year)

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
    return_to = request.args.get('return_to', '')
    return render_template('admin_record_detail.html', record=record, services=services,
                           linked_records=linked_records, changes=changes,
                           companions=companions_with_links, return_to=return_to)


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
            form.get('source_type', ''), form.get('collection_date', ''),
            form.get('collector_name', ''),
            form.get('verification_status', 'Unverified'),
            form.get('methodology_notes', ''),
            photo_hash, doc_hash,
            cv_path, form.get('survivor_cv_text', ''), cv_photo_path,
            record_id
        ))

        # Track field-level changes
        new_record = db.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
        ip = request.remote_addr or ''
        skip_fields = {'id', 'created_at', 'updated_at', 'record_slug'}
        for key in record.keys():
            if key in skip_fields:
                continue
            old_val = str(record[key] or '')
            new_val = str(new_record[key] or '')
            if old_val != new_val:
                db.execute(
                    "INSERT INTO record_changes (record_id, field_name, old_value, new_value, ip_address) VALUES (?,?,?,?,?)",
                    (record_id, key, old_val, new_val, ip)
                )

        db.commit()
        log_audit('record_edit', 'record', record_id)
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
    return_to = request.args.get('return_to', '')
    return render_template('admin_record_edit.html', record=record,
                           volunteer_names=[v['full_name'] for v in volunteer_names],
                           services=services, return_to=return_to)


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


@app.route('/api/companion_cross_ref/<int:record_id>')
@admin_required
def api_companion_cross_ref(record_id):
    """Find existing records that match companion names for cross-referencing."""
    db = get_db()
    companions = db.execute(
        "SELECT * FROM record_companions WHERE record_id = ? AND linked_record_id IS NULL",
        (record_id,)
    ).fetchall()
    results = []
    for comp in companions:
        matches = []
        parts = [comp['first_name'], comp['father_name'], comp['last_name']]
        parts = [p for p in parts if p]
        if not parts:
            continue
        conditions = []
        params = []
        for part in parts:
            if part:
                conditions.append("(first_name LIKE ? OR father_name LIKE ? OR last_name LIKE ?)")
                params.extend([f'%{part}%', f'%{part}%', f'%{part}%'])
        if conditions:
            query = f"SELECT id, first_name, father_name, last_name, status, province FROM records WHERE ({' OR '.join(conditions)}) AND id != ? LIMIT 5"
            params.append(record_id)
            found = db.execute(query, params).fetchall()
            for r in found:
                matches.append({
                    'id': r['id'],
                    'name': f"{r['first_name']} {r['father_name']} {r['last_name']}",
                    'status': r['status'],
                    'province': r['province'],
                })
        if matches:
            results.append({
                'companion_id': comp['id'],
                'companion_name': ' '.join(filter(None, [comp['first_name'], comp['father_name'], comp['last_name']])),
                'matches': matches,
            })
    return jsonify(results)


@app.route('/api/search_records_for_link')
@admin_required
def api_search_records_for_link():
    """Search records by name for linking UI."""
    q = request.args.get('q', '').strip()
    exclude_id = safe_int(request.args.get('exclude'), 0)
    if len(q) < 2:
        return jsonify([])
    db = get_db()
    search_term = f"%{q}%"
    records = db.execute(
        "SELECT id, first_name, father_name, last_name, status, province FROM records "
        "WHERE (first_name LIKE ? OR last_name LIKE ? OR father_name LIKE ? "
        "OR (COALESCE(first_name,'') || ' ' || COALESCE(father_name,'') || ' ' || COALESCE(last_name,'')) LIKE ?) "
        "AND id != ? LIMIT 10",
        (search_term, search_term, search_term, search_term, exclude_id)
    ).fetchall()
    return jsonify([{
        'id': r['id'],
        'name': f"{r['first_name']} {r['father_name']} {r['last_name']}",
        'status': r['status'],
        'province': r['province'],
    } for r in records])


@app.route('/admin/record/<int:record_id>/verify', methods=['POST'])
@admin_required
def admin_record_verify(record_id):
    """Change record verification status (draft -> reviewed -> verified -> locked)."""
    db = get_db()
    record = db.execute("SELECT id, record_status FROM records WHERE id = ?", (record_id,)).fetchone()
    if not record:
        flash('السجل غير موجود', 'error')
        return redirect(url_for('admin_records'))
    new_status = request.form.get('record_status', '')
    valid_statuses = ['draft', 'reviewed', 'verified', 'locked']
    if new_status not in valid_statuses:
        flash('حالة غير صالحة', 'error')
        return redirect(url_for('admin_record_detail', record_id=record_id))
    old_status = record['record_status'] or 'draft'
    db.execute("UPDATE records SET record_status = ? WHERE id = ?", (new_status, record_id))
    # Track the change
    ip = request.remote_addr or ''
    db.execute(
        "INSERT INTO record_changes (record_id, field_name, old_value, new_value, ip_address) VALUES (?,?,?,?,?)",
        (record_id, 'record_status', old_status, new_status, ip)
    )
    db.commit()
    log_audit('record_verify', 'record', record_id, f'{old_status} -> {new_status}')
    status_labels = {'draft': 'مسودة', 'reviewed': 'مراجَع', 'verified': 'موثّق', 'locked': 'مقفل'}
    flash(f'تم تغيير حالة السجل إلى: {status_labels.get(new_status, new_status)}', 'success')
    return redirect(url_for('admin_record_detail', record_id=record_id))


@app.route('/admin/record/<int:record_id>/delete', methods=['POST'])
@admin_required
def admin_record_delete(record_id):
    db = get_db()
    db.execute("DELETE FROM records WHERE id = ?", (record_id,))
    db.commit()
    log_audit('record_delete', 'record', record_id)
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


def build_pdf_filter_conditions(args):
    """Build SQL filter conditions from request args. Shared by PDF route and filtered IDs API."""
    conditions = []
    params = []

    pdf_status_list = args.getlist('status')
    expanded = []
    for s in pdf_status_list:
        if ',' in s:
            expanded.extend(s.split(','))
        elif s:
            expanded.append(s)
    pdf_status_list = expanded
    if pdf_status_list:
        if len(pdf_status_list) == 1:
            conditions.append("status = ?")
            params.append(pdf_status_list[0])
        else:
            placeholders = ','.join(['?'] * len(pdf_status_list))
            conditions.append(f"status IN ({placeholders})")
            params.extend(pdf_status_list)

    for key in ['province', 'gender', 'marital', 'education', 'housing_type', 'blood_type',
                'case_type', 'evidence_level', 'verification_status', 'civil_registry_status']:
        val = args.get(key, '')
        if val:
            conditions.append(f"{key} = ?")
            params.append(val)

    if args.get('arrest_authority'):
        aa = args['arrest_authority']
        matching_keywords = None
        for canonical, keywords in AUTHORITY_GROUPS.items():
            if aa == canonical:
                matching_keywords = keywords
                break
            for kw in keywords:
                if kw in aa:
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
            params.append(f"%{aa}%")
    if args.get('arrest_place'):
        conditions.append("arrest_place LIKE ?")
        params.append(f"%{args['arrest_place']}%")
    if args.get('search'):
        s = f"%{args['search']}%"
        conditions.append("""(
            first_name LIKE ? OR father_name LIKE ? OR last_name LIKE ?
            OR mother_name LIKE ? OR national_id LIKE ? OR phone LIKE ?
            OR address LIKE ? OR notes LIKE ? OR reporter_name LIKE ?
            OR (COALESCE(first_name,'') || ' ' || COALESCE(father_name,'') || ' ' || COALESCE(last_name,'')) LIKE ?
        )""")
        params.extend([s] * 10)
    if args.get('arrest_year_from') and safe_int(args['arrest_year_from']) is not None:
        conditions.append("arrest_year >= ?")
        params.append(safe_int(args['arrest_year_from']))
    if args.get('arrest_year_to') and safe_int(args['arrest_year_to']) is not None:
        conditions.append("arrest_year <= ?")
        params.append(safe_int(args['arrest_year_to']))
    if args.get('birth_year_from') and safe_int(args['birth_year_from']) is not None:
        conditions.append("birth_year >= ?")
        params.append(safe_int(args['birth_year_from']))
    if args.get('birth_year_to') and safe_int(args['birth_year_to']) is not None:
        conditions.append("birth_year <= ?")
        params.append(safe_int(args['birth_year_to']))
    if args.get('has_kids') == 'yes':
        conditions.append("has_kids = 'yes'")
    elif args.get('has_kids') == 'no':
        conditions.append("(has_kids = 'no' OR has_kids IS NULL OR has_kids = '')")
    pdf_minor_threshold = safe_int(args.get('minor_age_threshold'), 18)
    if args.get('has_kids_under_18') == 'yes':
        if pdf_minor_threshold == 18:
            conditions.append("kids_under_18_count > 0")
        else:
            conditions.append("(children_data IS NOT NULL AND children_data != '' AND children_data != '[]')")
    elif args.get('has_kids_under_18') == 'no':
        if pdf_minor_threshold == 18:
            conditions.append("(kids_under_18_count = 0 OR kids_under_18_count IS NULL)")
        else:
            pass  # post-filter
    if args.get('kids_max_age'):
        conditions.append("kids_under_18_count > 0")
    if args.get('has_photo') == 'yes':
        conditions.append("photo_path IS NOT NULL AND photo_path != ''")
    elif args.get('has_photo') == 'no':
        conditions.append("(photo_path IS NULL OR photo_path = '')")
    if args.get('has_document') == 'yes':
        conditions.append("document_path IS NOT NULL AND document_path != ''")
    elif args.get('has_document') == 'no':
        conditions.append("(document_path IS NULL OR document_path = '')")
    if args.get('digital_evidence_type'):
        conditions.append("digital_evidence_type = ?")
        params.append(args['digital_evidence_type'])
    if args.get('has_special_needs') == '1':
        conditions.append("has_special_needs = 1")
    if args.get('chronic') == 'yes':
        conditions.append("(chronic = 'نعم' OR has_hypertension = 1 OR has_diabetes = 1 OR (other_diseases IS NOT NULL AND other_diseases != ''))")
    if args.get('has_hypertension') == '1':
        conditions.append("has_hypertension = 1")
    if args.get('has_diabetes') == '1':
        conditions.append("has_diabetes = 1")
    if args.get('has_conflicting_info') == '1':
        conditions.append("has_conflicting_info = 1")
    if args.get('breadwinner'):
        conditions.append("breadwinner LIKE ?")
        params.append(f"%{args['breadwinner']}%")
    if args.get('is_registered') == '1':
        conditions.append("is_officially_registered = 1")
    elif args.get('is_registered') == '0':
        conditions.append("(is_officially_registered = 0 OR is_officially_registered IS NULL)")
    if args.get('has_legal') == 'yes':
        conditions.append("legal = 'نعم'")
    if args.get('has_assoc') == 'yes':
        conditions.append("assoc = 'yes'")
    elif args.get('has_assoc') == 'no':
        conditions.append("(assoc != 'yes' OR assoc IS NULL OR assoc = '')")
    if args.get('reporter_relation'):
        conditions.append("reporter_relation = ?")
        params.append(args['reporter_relation'])
    if args.get('education_max'):
        edu_order = ['أمّي', 'ابتدائية', 'إعدادية', 'ثانوية', 'معهد', 'بكالوريوس', 'ماجستير', 'دكتوراه']
        try:
            max_idx = edu_order.index(args['education_max'])
            included = edu_order[:max_idx + 1]
            placeholders = ','.join(['?'] * len(included))
            conditions.append(f"education IN ({placeholders})")
            params.extend(included)
        except ValueError:
            pass
    widows_f = args.get('widows_filter', '')
    if widows_f == 'widows_deceased':
        conditions.append("status IN ('deceased') AND gender = 'male' AND marital = 'married'")
    elif widows_f == 'widows_enforced':
        conditions.append("status = 'enforced' AND gender = 'male' AND marital = 'married'")
    elif widows_f == 'widows_all':
        conditions.append("status IN ('deceased', 'enforced') AND gender = 'male' AND marital = 'married'")
    elif widows_f == 'widows_with_minors':
        conditions.append("status IN ('deceased', 'enforced') AND gender = 'male' AND marital = 'married' AND kids_under_18_count > 0")
    if args.get('spouse_search'):
        conditions.append("spouse_name LIKE ?")
        params.append(f"%{args['spouse_search']}%")
    if args.get('child_name_search'):
        conditions.append("children_data LIKE ?")
        params.append(f"%{args['child_name_search']}%")
    if args.get('child_education'):
        conditions.append("children_data LIKE ?")
        params.append(f"%{args['child_education']}%")
    if args.get('employment'):
        conditions.append("employment LIKE ?")
        params.append(f"%{args['employment']}%")
    if args.get('profession'):
        conditions.append("profession LIKE ?")
        params.append(f"%{args['profession']}%")
    if args.get('address_search'):
        conditions.append("address LIKE ?")
        params.append(f"%{args['address_search']}%")
    if args.get('arrest_reason'):
        conditions.append("arrest_reason LIKE ?")
        params.append(f"%{args['arrest_reason']}%")
    if args.get('death_year_from') and safe_int(args['death_year_from']) is not None:
        conditions.append("death_year >= ?")
        params.append(safe_int(args['death_year_from']))
    if args.get('death_year_to') and safe_int(args['death_year_to']) is not None:
        conditions.append("death_year <= ?")
        params.append(safe_int(args['death_year_to']))
    if args.get('release_year_from') and safe_int(args['release_year_from']) is not None:
        conditions.append("release_year >= ?")
        params.append(safe_int(args['release_year_from']))
    if args.get('release_year_to') and safe_int(args['release_year_to']) is not None:
        conditions.append("release_year <= ?")
        params.append(safe_int(args['release_year_to']))
    if args.get('notes_search'):
        conditions.append("(notes LIKE ? OR methodology_notes LIKE ?)")
        params.extend([f"%{args['notes_search']}%"] * 2)
    if args.get('employer'):
        conditions.append("employer LIKE ?")
        params.append(f"%{args['employer']}%")
    if args.get('breadwinner_relation'):
        conditions.append("breadwinner_relation = ?")
        params.append(args['breadwinner_relation'])
    if args.get('age_from') and safe_int(args['age_from']) is not None:
        current_year = datetime.now().year
        max_birth_year = current_year - safe_int(args['age_from'])
        conditions.append("birth_year <= ? AND birth_year > 0")
        params.append(max_birth_year)
    if args.get('age_to') and safe_int(args['age_to']) is not None:
        current_year = datetime.now().year
        min_birth_year = current_year - safe_int(args['age_to'])
        conditions.append("birth_year >= ?")
        params.append(min_birth_year)
    if args.get('has_guardian') == 'yes':
        conditions.append("guardian_name IS NOT NULL AND guardian_name != ''")
    elif args.get('has_guardian') == 'no':
        conditions.append("(guardian_name IS NULL OR guardian_name = '')")
    if args.get('digital_evidence_url_status'):
        conditions.append("digital_evidence_url_status = ?")
        params.append(args['digital_evidence_url_status'])
    if args.get('collector_name'):
        conditions.append("collector_name = ?")
        params.append(args['collector_name'])
    # Data entry date range (created_at is TEXT like '2024-01-15 10:30:00')
    if args.get('created_from'):
        conditions.append("created_at >= ?")
        params.append(args['created_from'])
    if args.get('created_to'):
        conditions.append("created_at <= ?")
        params.append(args['created_to'] + ' 23:59:59')
    # Collection date range
    if args.get('collection_date_from'):
        conditions.append("collection_date >= ?")
        params.append(args['collection_date_from'])
    if args.get('collection_date_to'):
        conditions.append("collection_date <= ?")
        params.append(args['collection_date_to'])
    if args.get('source_type'):
        conditions.append("source_type = ?")
        params.append(args['source_type'])
    if args.get('has_phone') == 'yes':
        conditions.append("(phone IS NOT NULL AND phone != '')")
    elif args.get('has_phone') == 'no':
        conditions.append("(phone IS NULL OR phone = '')")
    if args.get('family_book_number'):
        conditions.append("family_book_number LIKE ?")
        params.append(f"%{args['family_book_number']}%")
    if args.get('national_id_search'):
        conditions.append("national_id LIKE ?")
        params.append(f"%{args['national_id_search']}%")
    if args.get('has_rent') == 'yes':
        conditions.append("rent_amount IS NOT NULL AND rent_amount != '' AND rent_amount != '0'")
    elif args.get('has_rent') == 'no':
        conditions.append("(rent_amount IS NULL OR rent_amount = '' OR rent_amount = '0')")
    if args.get('detention_facility_search'):
        conditions.append("detention_facilities_data LIKE ?")
        params.append(f"%{args['detention_facility_search']}%")
    # Service filters (subqueries on record_services) - match _build_record_filter_conditions
    svc_mode = args.get('service_filter_mode', '') or 'received'
    if svc_mode == 'not_received' and args.get('service_name'):
        conditions.append(
            "NOT EXISTS (SELECT 1 FROM record_services rs WHERE rs.record_id = records.id AND rs.service_name = ?)"
        )
        params.append(args['service_name'])
    elif args.get('service_name') and args.get('service_count_min'):
        conditions.append(
            "(SELECT COUNT(*) FROM record_services rs WHERE rs.record_id = records.id AND rs.service_name = ?) >= ?"
        )
        params.append(args['service_name'])
        params.append(safe_int(args['service_count_min'], 1))
    elif args.get('service_name'):
        conditions.append(
            "EXISTS (SELECT 1 FROM record_services rs WHERE rs.record_id = records.id AND rs.service_name = ?)"
        )
        params.append(args['service_name'])
    elif args.get('service_count_min'):
        conditions.append(
            "(SELECT COUNT(*) FROM record_services rs WHERE rs.record_id = records.id) >= ?"
        )
        params.append(safe_int(args['service_count_min'], 1))
    if args.get('service_provider'):
        conditions.append(
            "EXISTS (SELECT 1 FROM record_services rs WHERE rs.record_id = records.id AND rs.provider = ?)"
        )
        params.append(args['service_provider'])
    if args.get('last_service_from'):
        conditions.append(
            "EXISTS (SELECT 1 FROM record_services rs WHERE rs.record_id = records.id AND rs.service_date >= ?)"
        )
        params.append(args['last_service_from'])
    if args.get('last_service_to'):
        conditions.append(
            "(SELECT MAX(rs.service_date) FROM record_services rs WHERE rs.record_id = records.id) <= ?"
        )
        params.append(args['last_service_to'])

    return conditions, params, pdf_status_list


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
            extra = db.execute(f"SELECT * FROM records WHERE id IN ({placeholders})", missing_ids).fetchall()
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
            extra = db.execute(f"SELECT * FROM records WHERE id IN ({placeholders})", missing_ids).fetchall()
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
            extra = db.execute(f"SELECT * FROM records WHERE id IN ({placeholders})", missing_ids).fetchall()
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
        "FROM records WHERE has_kids = 'yes' AND children_data IS NOT NULL AND children_data != '' AND children_data != '[]' "
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
                        except: pass
                    elif c.get('age'):
                        try: age = int(c['age'])
                        except: pass
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
                        except: pass
                    elif c.get('age'):
                        try: age = int(c['age'])
                        except: pass
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
                        except: pass
                    elif c.get('age'):
                        try: age = int(c['age'])
                        except: pass
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
        "SELECT * FROM records WHERE first_name LIKE ? OR father_name LIKE ? OR last_name LIKE ? "
        "OR (COALESCE(first_name,'') || ' ' || COALESCE(father_name,'') || ' ' || COALESCE(last_name,'')) LIKE ? "
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
    record = db.execute("SELECT id FROM records WHERE id=?", (record_id,)).fetchone()
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
        return jsonify({'error': str(e)}), 500


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
            WHERE first_name LIKE ? OR father_name LIKE ? OR last_name LIKE ?
                  OR national_id LIKE ? OR phone LIKE ?
                  OR (COALESCE(first_name,'') || ' ' || COALESCE(father_name,'') || ' ' || COALESCE(last_name,'')) LIKE ?
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
        return jsonify({'error': str(e)}), 500


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
        return jsonify({'error': str(e)}), 500


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
        records = db.execute("SELECT * FROM records ORDER BY id").fetchall()
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
        for r in db.execute("SELECT * FROM records ORDER BY id").fetchall():
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

                first = g('first_name') or g('الاسم')
                last = g('last_name') or g('الكنية')
                if not first:
                    skipped.append(f'سطر {row_num}: الاسم مطلوب')
                    continue

                slug = f"{first}-{last}-{int(time.time())}".replace(' ', '-')
                try:
                    db.execute("""INSERT INTO records (first_name, father_name, last_name, mother_name,
                        gender, status, province, national_id, phone, birth_year,
                        marital, address, housing_type, record_slug)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (first, g('father_name') or g('اسم الأب'), last,
                         g('mother_name') or g('اسم الأم'),
                         g('gender') or g('الجنس'), g('status') or g('الحالة'),
                         g('province') or g('المحافظة'), g('national_id') or g('الرقم الوطني'),
                         g('phone') or g('الهاتف'), int(g('birth_year') or g('سنة الميلاد') or 0),
                         g('marital') or g('الحالة الاجتماعية'), g('address') or g('العنوان'),
                         g('housing_type') or g('نوع السكن'), slug))
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
    from openpyxl.styles import Font, PatternFill, Alignment

    import_type = request.args.get('type', 'records')
    wb = Workbook()
    ws = wb.active
    ws.sheet_view.rightToLeft = True

    if import_type == 'volunteers':
        headers = ['الاسم', 'الهاتف', 'البريد', 'الرقم الوطني', 'المحافظة', 'العنوان', 'الدور', 'التخصص']
        ws.title = 'متطوعون'
    elif import_type == 'members':
        headers = ['الاسم', 'اسم الأب', 'الهاتف', 'البريد', 'الرقم الوطني', 'المحافظة', 'العنوان', 'نوع العضوية']
        ws.title = 'منتسبون'
    else:
        headers = ['الاسم', 'اسم الأب', 'الكنية', 'اسم الأم', 'الجنس', 'الحالة', 'المحافظة',
                    'الرقم الوطني', 'الهاتف', 'سنة الميلاد', 'الحالة الاجتماعية', 'العنوان', 'نوع السكن']
        ws.title = 'سجلات'

    hfont = Font(bold=True, color='FFFFFF')
    hfill = PatternFill(start_color='1565C0', end_color='1565C0', fill_type='solid')
    for i, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=i, value=h)
        cell.font = hfont
        cell.fill = hfill
        cell.alignment = Alignment(horizontal='center')
        ws.column_dimensions[chr(64 + i)].width = 18

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
    args = parser.parse_args()

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
    print(f"  Password:   (stored in admin_password.hash)")
    print("="*60)
    print(f"  * Other devices on your network can connect using:")
    print(f"    http://{lan_ip}:{port}")
    if not fixed_ip:
        print(f"  * To set a fixed IP, run: python app.py --ip 192.168.1.100")
        print(f"    or configure in Admin > Server Config")
    print("="*60 + "\n")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
