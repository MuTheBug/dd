from flask import Flask
from models import db, User
from werkzeug.security import generate_password_hash
import os

app = Flask(__name__)
# Use absolute path to ensure we use the correct DB
db_path = os.path.join(os.getcwd(), 'registry.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SECRET_KEY'] = 'dev'
db.init_app(app)

def init_db():
    with app.app_context():
        # This will create the User table. Record table already exists.
        db.create_all()

        # Check if admin exists
        if not User.query.filter_by(username='admin').first():
            user = User(
                username='admin',
                password_hash=generate_password_hash('admin123'),
                role='admin'
            )
            db.session.add(user)
            print("Admin user created.")
        else:
            print("Admin user already exists.")

        # Check if data entry user exists
        if not User.query.filter_by(username='user').first():
            user = User(
                username='user',
                password_hash=generate_password_hash('user123'),
                role='data_entry'
            )
            db.session.add(user)
            print("Data Entry user created.")
        else:
            print("Data Entry user already exists.")

        db.session.commit()
        print(f"Database initialized at {db_path}")

if __name__ == '__main__':
    init_db()
