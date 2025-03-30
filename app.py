from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import qrcode
import io
import re
from dotenv import load_dotenv
import os
from datetime import datetime
import json
import logging
from functools import wraps
import csv
import cairosvg
from PIL import Image
import base64

# Konfiguracja logowania
logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///qr_generator.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Modele bazy danych
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    qr_codes = db.relationship('QRCode', backref='user', lazy=True)
    favorites = db.relationship('Favorite', backref='user', lazy=True)

class QRCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), nullable=False)
    data = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_favorite = db.Column(db.Boolean, default=False)
    password = db.Column(db.String(128))
    expiry_date = db.Column(db.DateTime)
    views = db.Column(db.Integer, default=0)

class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    qr_code_id = db.Column(db.Integer, db.ForeignKey('qr_code.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Statistics(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    total_qr_codes = db.Column(db.Integer, default=0)
    total_views = db.Column(db.Integer, default=0)
    most_popular_type = db.Column(db.String(20))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def compress_image(img, max_size=(800, 800)):
    img.thumbnail(max_size, Image.LANCZOS)
    return img

def cache_key_generator(*args, **kwargs):
    return f"qr_{hash(str(args) + str(kwargs))}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Nazwa użytkownika już istnieje'}), 400
    
    user = User(
        username=data['username'],
        email=data['email'],
        password_hash=generate_password_hash(data['password'])
    )
    db.session.add(user)
    db.session.commit()
    
    return jsonify({'message': 'Użytkownik został zarejestrowany'})

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(username=data['username']).first()
    
    if user and check_password_hash(user.password_hash, data['password']):
        login_user(user)
        return jsonify({'message': 'Zalogowano pomyślnie'})
    
    return jsonify({'error': 'Nieprawidłowe dane logowania'}), 401

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return jsonify({'message': 'Wylogowano pomyślnie'})

@app.route('/generate', methods=['POST'])
@login_required
def generate():
    try:
        data = request.get_json()
        qr_type = data.get('type', 'link')
        fill_color = data.get('fill_color', 'black')
        back_color = data.get('back_color', 'white')
        
        # Generowanie kodu QR (istniejący kod)
        qr_img = generate_qr_code(data, qr_type, fill_color, back_color)
        
        # Kompresja obrazu
        qr_img = compress_image(qr_img)
        
        # Zapisywanie do bazy danych
        qr_code = QRCode(
            type=qr_type,
            data=json.dumps(data),
            user_id=current_user.id,
            password=data.get('password'),
            expiry_date=datetime.fromisoformat(data.get('expiry_date')) if data.get('expiry_date') else None
        )
        db.session.add(qr_code)
        db.session.commit()
        
        # Aktualizacja statystyk
        update_statistics(qr_type)
        
        # Konwersja do base64
        img_buffer = io.BytesIO()
        qr_img.save(img_buffer, format='PNG')
        img_str = f"data:image/png;base64,{img_buffer.getvalue().hex()}"
        
        return jsonify({
            'qr_code': img_str,
            'qr_id': qr_code.id
        })
        
    except Exception as e:
        logger.error(f"Błąd podczas generowania kodu QR: {str(e)}")
        return jsonify({'error': 'Wystąpił błąd podczas generowania kodu QR'}), 500

@app.route('/favorites', methods=['GET', 'POST'])
@login_required
def handle_favorites():
    if request.method == 'GET':
        favorites = Favorite.query.filter_by(user_id=current_user.id).all()
        return jsonify([{
            'id': f.qr_code.id,
            'type': f.qr_code.type,
            'created_at': f.qr_code.created_at.isoformat()
        } for f in favorites])
    
    data = request.get_json()
    qr_code_id = data.get('qr_code_id')
    
    favorite = Favorite(user_id=current_user.id, qr_code_id=qr_code_id)
    db.session.add(favorite)
    db.session.commit()
    
    return jsonify({'message': 'Dodano do ulubionych'})

@app.route('/export', methods=['GET'])
@login_required
def export_data():
    format = request.args.get('format', 'csv')
    qr_codes = QRCode.query.filter_by(user_id=current_user.id).all()
    
    if format == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Typ', 'Data', 'Data utworzenia', 'Widoki'])
        
        for qr in qr_codes:
            writer.writerow([
                qr.id,
                qr.type,
                qr.data,
                qr.created_at,
                qr.views
            ])
        
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name='qr_codes.csv'
        )
    
    elif format == 'pdf':
        # Implementacja eksportu do PDF
        pass

@app.route('/statistics', methods=['GET'])
@login_required
def get_statistics():
    stats = Statistics.query.order_by(Statistics.date.desc()).first()
    return jsonify({
        'total_qr_codes': stats.total_qr_codes,
        'total_views': stats.total_views,
        'most_popular_type': stats.most_popular_type
    })

def update_statistics(qr_type):
    today = datetime.utcnow().date()
    stats = Statistics.query.filter_by(date=today).first()
    
    if not stats:
        stats = Statistics(date=today)
        db.session.add(stats)
    
    stats.total_qr_codes += 1
    stats.most_popular_type = qr_type
    db.session.commit()

# Istniejące funkcje pomocnicze
def modify_dropbox_link(link):
    if "dropbox.com" in link:
        link = re.sub(r"dl=0$", "dl=1", link)
    return link

def generate_qr_code(data, qr_type, fill_color='black', back_color='white'):
    # Istniejący kod generowania QR
    pass

def generate_vcard_qr(name, phone, email):
    vcard = f"""BEGIN:VCARD
VERSION:3.0
N:{name}
TEL:{phone}
EMAIL:{email}
END:VCARD"""
    return generate_qr_code(vcard)

def generate_calendar_event_qr(title, start_date, end_date, location, description):
    event = f"""BEGIN:VEVENT
SUMMARY:{title}
DTSTART:{start_date}
DTEND:{end_date}
LOCATION:{location}
DESCRIPTION:{description}
END:VEVENT"""
    return generate_qr_code(event)

def generate_location_qr(latitude, longitude, location_name):
    location = f"geo:{latitude},{longitude}?q={location_name}"
    return generate_qr_code(location)

@app.route('/themes', methods=['GET'])
def get_themes():
    themes = {
        'light': {
            'background': '#ffffff',
            'text': '#000000',
            'primary': '#3b82f6',
            'secondary': '#6b7280'
        },
        'dark': {
            'background': '#1f2937',
            'text': '#ffffff',
            'primary': '#60a5fa',
            'secondary': '#9ca3af'
        },
        'blue': {
            'background': '#eff6ff',
            'text': '#1e40af',
            'primary': '#3b82f6',
            'secondary': '#60a5fa'
        },
        'green': {
            'background': '#f0fdf4',
            'text': '#166534',
            'primary': '#22c55e',
            'secondary': '#4ade80'
        }
    }
    return jsonify(themes)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True) 