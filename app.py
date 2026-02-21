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

    query = Record.query

    if search_query:
        query = query.filter(
            (Record.first_name.contains(search_query)) |
            (Record.last_name.contains(search_query)) |
            (Record.father_name.contains(search_query)) |
            (Record.mother_name.contains(search_query))
        )

    if status_filter:
        query = query.filter(Record.status == status_filter)

    if province_filter:
        query = query.filter(Record.province == province_filter)

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
            record.phone = request.form.get('phone')
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
            record.phone = request.form.get('phone')
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
            'national_id': 'الرقم الوطني'
        }

        columns_to_print = []
        for col in selected_columns:
            if col in column_map:
                columns_to_print.append({'field': col, 'label': column_map[col]})

        if not columns_to_print:
            flash('الرجاء اختيار عمود واحد على الأقل', 'warning')
            return redirect(url_for('reports'))

        pdf_buffer = generate_pdf(records, "تقرير السجلات", columns_to_print)
        pdf_buffer.seek(0)

        return send_file(pdf_buffer, as_attachment=True, download_name='report.pdf', mimetype='application/pdf')

    return render_template('report_form.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
