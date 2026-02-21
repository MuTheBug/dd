from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='data_entry')

class Record(db.Model):
    __tablename__ = 'records'

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.String, default=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    # Personal Info
    first_name = db.Column(db.String, nullable=False)
    father_name = db.Column(db.String, nullable=False)
    last_name = db.Column(db.String, nullable=False)
    gender = db.Column(db.String, nullable=False)
    mother_name = db.Column(db.String, nullable=False)
    birth_day = db.Column(db.Integer)
    birth_month = db.Column(db.Integer)
    birth_year = db.Column(db.Integer)
    province = db.Column(db.String, nullable=False)
    national_id = db.Column(db.String, nullable=False)
    phone = db.Column(db.String)
    blood_type = db.Column(db.String)
    photo_path = db.Column(db.String)
    document_path = db.Column(db.String)

    # Arrest/Detention
    arrest_day = db.Column(db.Integer)
    arrest_month = db.Column(db.Integer)
    arrest_year = db.Column(db.Integer)
    arrest_place = db.Column(db.String, nullable=False)
    arrest_authority = db.Column(db.String, nullable=False)
    arrest_reason = db.Column(db.String, nullable=False)
    arrest_causer = db.Column(db.String)
    status = db.Column(db.String)
    release_day = db.Column(db.Integer)
    release_month = db.Column(db.Integer)
    release_year = db.Column(db.Integer)
    death_day = db.Column(db.Integer)
    death_month = db.Column(db.Integer)
    death_year = db.Column(db.Integer)
    death_place = db.Column(db.String)

    # Family
    marital = db.Column(db.String)
    guardian_name = db.Column(db.String)
    guardian_relation = db.Column(db.String)
    guardian_phone = db.Column(db.String)
    spouse_name = db.Column(db.String)
    spouse_phone = db.Column(db.String)
    has_kids = db.Column(db.String)
    kids_count = db.Column(db.Integer)
    children_data = db.Column(db.String) # JSON
    ex_spouse_name = db.Column(db.String)
    has_kids_w = db.Column(db.String)
    kids_count_w = db.Column(db.Integer)
    children_data_w = db.Column(db.String) # JSON

    # Socio-Economic
    address = db.Column(db.String, nullable=False)
    housing_type = db.Column(db.String, nullable=False)
    employment = db.Column(db.String)
    profession = db.Column(db.String)
    employer = db.Column(db.String)
    breadwinner = db.Column(db.String)
    rent_amount = db.Column(db.String)
    breadwinner_job = db.Column(db.String)
    breadwinner_relation = db.Column(db.String)
    breadwinner_relation_other = db.Column(db.String)

    # Health
    chronic = db.Column(db.String)
    diseases = db.Column(db.String)
    has_hypertension = db.Column(db.Integer)
    has_diabetes = db.Column(db.Integer)
    other_diseases = db.Column(db.String)
    has_special_needs = db.Column(db.Integer)
    special_needs_details = db.Column(db.String)

    # Education
    education = db.Column(db.String)
    edu_type = db.Column(db.String)
    edu_specialization = db.Column(db.String)
    edu_university = db.Column(db.String)

    # Legal / Assoc
    kids_under_18_count = db.Column(db.Integer, default=0)
    legal = db.Column(db.String)
    legal_details = db.Column(db.String)
    assoc = db.Column(db.String)
    assoc_name = db.Column(db.String)
    service_type = db.Column(db.String)
    is_officially_registered = db.Column(db.Integer)
    notes = db.Column(db.String)

    # Survivor CV
    survivor_cv_path = db.Column(db.String)
    survivor_cv_text = db.Column(db.String)
    survivor_cv_photo_path = db.Column(db.String)

    # Verification / Berkeley Protocol
    source_type = db.Column(db.String)
    source_url = db.Column(db.String)
    collection_date = db.Column(db.String)
    collector_name = db.Column(db.String)
    verification_status = db.Column(db.String)
    methodology_notes = db.Column(db.String)
    cause_number = db.Column(db.String)
    record_slug = db.Column(db.String)
    photo_hash = db.Column(db.String)
    document_hash = db.Column(db.String)
    case_type = db.Column(db.String)

    # Reporter / Informant
    reporter_name = db.Column(db.String)
    reporter_relation = db.Column(db.String)
    reporter_phone = db.Column(db.String)
    reporter_id = db.Column(db.String)
    informant_consent = db.Column(db.Integer)
    witnesses_data = db.Column(db.String) # JSON

    # Digital Evidence
    digital_evidence_type = db.Column(db.String)
    digital_evidence_url = db.Column(db.String)
    digital_evidence_url_status = db.Column(db.String)
    digital_evidence_screenshot_path = db.Column(db.String)
    digital_evidence_date = db.Column(db.String)
    digital_evidence_description = db.Column(db.String)
    digital_evidence_person_name = db.Column(db.String)
    digital_evidence_death_date = db.Column(db.String)

    # Civil Registry
    civil_registry_status = db.Column(db.String)
    civil_registry_date = db.Column(db.String)
    civil_registry_document_path = db.Column(db.String)

    # Conflict / Analysis
    has_conflicting_info = db.Column(db.Integer)
    conflicting_info_details = db.Column(db.String)
    evidence_level = db.Column(db.String)
    evidence_sources_count = db.Column(db.Integer)
    last_known_alive_date = db.Column(db.String)
    last_known_location = db.Column(db.String)
    detention_facilities_data = db.Column(db.String) # JSON
