from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from models import db, User, Record
from utils import generate_pdf, allowed_file, calculate_file_hash
import os
import time
import json
import hashlib

app = Flask(__name__)
db_path = os.path.join(os.getcwd(), 'registry.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SECRET_KEY'] = 'dev_secret_key' # In prod, use random bytes
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')

def normalize_phone(phone):
    if not phone:
        return None
    # Strip non-digit characters
    digits = ''.join(filter(str.isdigit, phone))

    # Ensure leading 0 if length is 9 (common case)
    if len(digits) == 9 and not digits.startswith('0'):
        digits = '0' + digits

    # Max 10 digits
    # If starts with 963, remove it
    if digits.startswith('963') and len(digits) > 10:
        digits = digits[3:]
    elif digits.startswith('00963') and len(digits) > 12:
        digits = digits[5:]

    # Ensure leading 0 if length is 9 (common case)
    if len(digits) == 9 and not digits.startswith('0'):
        digits = '0' + digits

    # Max 10 digits
    if len(digits) > 10:
        digits = digits[-10:]

    return digits

db.init_app(app)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Login Unsuccessful. Please check username and password', 'danger')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    record_count = Record.query.count()
    return render_template('dashboard.html', record_count=record_count)

@app.route('/records')
@login_required
def list_records():
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('q', '')
    status_filter = request.args.get('status', '')
    province_filter = request.args.get('province', '')

    # New Filters
    chronic_filter = request.args.get('chronic_diseases_present')
    special_needs_filter = request.args.get('has_special_needs')
    kids_under_18_filter = request.args.get('kids_under_18')
    arrest_authority_filter = request.args.get('arrest_authority', '')
    date_start = request.args.get('date_range_start', '')
    date_end = request.args.get('date_range_end', '')
    conflicting_filter = request.args.get('has_conflicting_info')
    verification_filter = request.args.get('verification_status', '')
    evidence_filter = request.args.get('evidence_level', '')
    consent_filter = request.args.get('informant_consent')

    query = Record.query

    if search_query:
        query = query.filter(
            (Record.first_name.contains(search_query)) |
            (Record.last_name.contains(search_query)) |
            (Record.father_name.contains(search_query)) |
            (Record.mother_name.contains(search_query)) |
            (Record.record_slug.contains(search_query)) |
            (Record.cause_number.contains(search_query))
        )

    if status_filter:
        query = query.filter(Record.status == status_filter)

    if province_filter:
        query = query.filter(Record.province == province_filter)

    if chronic_filter:
        query = query.filter(Record.chronic_diseases_present == 1)

    if special_needs_filter:
        query = query.filter(Record.has_special_needs == 1)

    if kids_under_18_filter:
        query = query.filter(Record.kids_under_18_count > 0)

    if arrest_authority_filter:
        query = query.filter(Record.arrest_authority.contains(arrest_authority_filter))

    if date_start and date_end:
        # Assuming filtering by arrest year for simplicity in range, or created_at
        # Here implementing arrest year range
        try:
            start_year = int(date_start)
            end_year = int(date_end)
            query = query.filter(Record.arrest_year >= start_year, Record.arrest_year <= end_year)
        except ValueError:
            pass

    if conflicting_filter:
        query = query.filter(Record.has_conflicting_info == 1)

    if verification_filter:
        query = query.filter(Record.verification_status == verification_filter)

    if evidence_filter:
        query = query.filter(Record.evidence_level == evidence_filter)

    if consent_filter:
        query = query.filter(Record.informant_consent == 1)

    pagination = query.order_by(Record.created_at.desc()).paginate(page=page, per_page=20)

    return render_template('record_list.html', pagination=pagination)

@app.route('/records/new', methods=['GET', 'POST'])
@login_required
def new_record():
    if request.method == 'POST':
        try:
            record = Record()
            # Personal
            record.first_name = request.form.get('first_name')
            record.father_name = request.form.get('father_name')
            record.last_name = request.form.get('last_name')
            record.mother_name = request.form.get('mother_name')
            record.gender = request.form.get('gender')
            record.birth_year = request.form.get('birth_year')
            record.province = request.form.get('province')
            record.national_id = request.form.get('national_id')
            record.phone = normalize_phone(request.form.get('phone'))
            record.address = request.form.get('address')
            record.housing_type = request.form.get('housing_type')

            # Arrest
            record.arrest_year = request.form.get('arrest_year')
            record.arrest_place = request.form.get('arrest_place')
            record.arrest_authority = request.form.get('arrest_authority')
            record.arrest_reason = request.form.get('arrest_reason')
            record.status = request.form.get('status')

            # Family
            record.marital = request.form.get('marital')
            record.spouse_name = request.form.get('spouse_name')
            record.kids_under_18_count = request.form.get('kids_under_18_count', 0)
            record.children_data = request.form.get('children_data_json')

            # Health & Education
            record.has_special_needs = 1 if request.form.get('has_special_needs') else 0
            record.special_needs_details = request.form.get('special_needs_details')
            record.education = request.form.get('education')
            record.profession = request.form.get('profession')

            # Verification / Evidence
            record.verification_status = request.form.get('verification_status')
            record.source_type = request.form.get('source_type')
            record.civil_registry_status = request.form.get('civil_registry_status')
            record.has_conflicting_info = 1 if request.form.get('has_conflicting_info') else 0
            record.conflicting_info_details = request.form.get('conflicting_info_details')

            # New Fields
            record.chronic_diseases_present = 1 if request.form.get('chronic_diseases_present') else 0
            record.reporter_name = request.form.get('reporter_name')
            record.reporter_relation = request.form.get('reporter_relation')
            record.reporter_phone = normalize_phone(request.form.get('reporter_phone'))
            record.informant_consent = 1 if request.form.get('informant_consent') else 0
            record.evidence_level = request.form.get('evidence_level')

            # Files
            if 'photo' in request.files:
                file = request.files['photo']
                if file and allowed_file(file.filename):
                    filename = secure_filename(f"{int(time.time())}_{file.filename}")
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    record.photo_path = filename
                    record.photo_hash = calculate_file_hash(filepath)

            if 'document' in request.files:
                file = request.files['document']
                if file and allowed_file(file.filename):
                    filename = secure_filename(f"{int(time.time())}_doc_{file.filename}")
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    record.document_path = filename
                    record.document_hash = calculate_file_hash(filepath)

            db.session.add(record)
            db.session.commit()
            flash('تم إضافة السجل بنجاح', 'success')
            return redirect(url_for('list_records'))

        except Exception as e:
            flash(f'حدث خطأ: {str(e)}', 'danger')

    return render_template('record_form.html', record=None)

@app.route('/records/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_record(id):
    if current_user.role != 'admin':
        flash('غير مصرح لك بتعديل السجلات', 'danger')
        return redirect(url_for('list_records'))

    record = Record.query.get_or_404(id)

    if request.method == 'POST':
        try:
            record.first_name = request.form.get('first_name')
            record.father_name = request.form.get('father_name')
            record.last_name = request.form.get('last_name')
            record.mother_name = request.form.get('mother_name')
            record.gender = request.form.get('gender')
            record.birth_year = request.form.get('birth_year')
            record.province = request.form.get('province')
            record.national_id = request.form.get('national_id')
            record.phone = normalize_phone(request.form.get('phone'))
            record.address = request.form.get('address')
            record.housing_type = request.form.get('housing_type')

            record.arrest_year = request.form.get('arrest_year')
            record.arrest_place = request.form.get('arrest_place')
            record.arrest_authority = request.form.get('arrest_authority')
            record.arrest_reason = request.form.get('arrest_reason')
            record.status = request.form.get('status')

            record.marital = request.form.get('marital')
            record.spouse_name = request.form.get('spouse_name')
            record.kids_under_18_count = request.form.get('kids_under_18_count', 0)
            record.children_data = request.form.get('children_data_json')

            record.has_special_needs = 1 if request.form.get('has_special_needs') else 0
            record.special_needs_details = request.form.get('special_needs_details')
            record.education = request.form.get('education')
            record.profession = request.form.get('profession')

            record.verification_status = request.form.get('verification_status')
            record.source_type = request.form.get('source_type')
            record.civil_registry_status = request.form.get('civil_registry_status')
            record.has_conflicting_info = 1 if request.form.get('has_conflicting_info') else 0
            record.conflicting_info_details = request.form.get('conflicting_info_details')

            # New Fields
            record.chronic_diseases_present = 1 if request.form.get('chronic_diseases_present') else 0
            record.reporter_name = request.form.get('reporter_name')
            record.reporter_relation = request.form.get('reporter_relation')
            record.reporter_phone = normalize_phone(request.form.get('reporter_phone'))
            record.informant_consent = 1 if request.form.get('informant_consent') else 0
            record.evidence_level = request.form.get('evidence_level')

            if 'photo' in request.files:
                file = request.files['photo']
                if file and allowed_file(file.filename):
                    filename = secure_filename(f"{int(time.time())}_{file.filename}")
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    record.photo_path = filename
                    record.photo_hash = calculate_file_hash(filepath)

            if 'document' in request.files:
                file = request.files['document']
                if file and allowed_file(file.filename):
                    filename = secure_filename(f"{int(time.time())}_doc_{file.filename}")
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    record.document_path = filename
                    record.document_hash = calculate_file_hash(filepath)

            db.session.commit()
            flash('تم تعديل السجل بنجاح', 'success')
            return redirect(url_for('list_records'))

        except Exception as e:
            flash(f'حدث خطأ: {str(e)}', 'danger')

    return render_template('record_form.html', record=record)

@app.route('/reports', methods=['GET', 'POST'])
@login_required
def reports():
    if request.method == 'POST':
        status = request.form.get('status')
        province = request.form.get('province')

        query = Record.query
        if status:
            query = query.filter_by(status=status)
        if province:
            query = query.filter_by(province=province)

        records = query.all()

        selected_columns = request.form.getlist('columns')
        anonymize = 1 if request.form.get('anonymize') else 0

        # Map of field name -> Arabic Label
        column_map = {
            'first_name': 'الاسم الأول',
            'father_name': 'اسم الأب',
            'last_name': 'الكنية',
            'mother_name': 'اسم الأم',
            'province': 'المحافظة',
            'status': 'الحالة',
            'arrest_year': 'سنة الاعتقال',
            'phone': 'الهاتف',
            'national_id': 'الرقم الوطني',
            'chronic_diseases_present': 'أمراض مزمنة',
            'has_special_needs': 'احتياجات خاصة',
            'has_conflicting_info': 'تضارب معلومات'
        }

        columns_to_print = []
        for col in selected_columns:
            if col in column_map:
                columns_to_print.append({'field': col, 'label': column_map[col]})

        if not columns_to_print:
            flash('الرجاء اختيار عمود واحد على الأقل', 'warning')
            return redirect(url_for('reports'))

        pdf_buffer = generate_pdf(records, "تقرير السجلات", columns_to_print, anonymize=anonymize)
        pdf_buffer.seek(0)

        return send_file(pdf_buffer, as_attachment=True, download_name='report.pdf', mimetype='application/pdf')

    return render_template('report_form.html')

@app.route('/reports/export', methods=['POST'])
@login_required
def export_csv():
    # Similar logic to reports filtering
    status = request.form.get('status')
    province = request.form.get('province')
    anonymize = 1 if request.form.get('anonymize') else 0

    query = Record.query
    if status:
        query = query.filter_by(status=status)
    if province:
        query = query.filter_by(province=province)

    records = query.all()

    # Columns to export
    columns = [
        'id', 'first_name', 'father_name', 'last_name', 'mother_name',
        'province', 'status', 'arrest_year', 'phone', 'national_id',
        'chronic_diseases_present', 'has_special_needs', 'has_conflicting_info'
    ]

    import csv
    from io import StringIO

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(columns) # Header

    for record in records:
        row = []
        for col in columns:
            if anonymize and col in ['first_name', 'father_name', 'last_name', 'mother_name', 'national_id', 'phone']:
                if col == 'first_name':
                    row.append(f"Record ID: {record.id}")
                else:
                    row.append("---")
            else:
                val = getattr(record, col)
                row.append(val if val is not None else "")
        cw.writerow(row)

    output = si.getvalue()
    si.close()

    from flask import Response
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=export.csv"}
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
