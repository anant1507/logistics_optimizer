import os
import io
import csv
import random
from datetime import datetime, date, timedelta
import click

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, g, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fallback-secret-key')

# --- File Upload Configuration ---
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Database Connection Management ---
def get_db():
    if 'db' not in g:
        g.db = psycopg2.connect(os.getenv('DATABASE_URL'))
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# --- Database Initialization ---
def init_db_logic():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            name VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL,
            verified BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS suppliers (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            location VARCHAR(255),
            contact VARCHAR(255),
            status VARCHAR(50) DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS ports (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            capacity INTEGER NOT NULL,
            current_stock INTEGER DEFAULT 0,
            location VARCHAR(255),
            status VARCHAR(50) DEFAULT 'operational',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS plants (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            capacity INTEGER NOT NULL,
            current_stock INTEGER DEFAULT 0,
            location VARCHAR(255),
            status VARCHAR(50) DEFAULT 'operational',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS vessels (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            capacity INTEGER NOT NULL,
            status VARCHAR(50) DEFAULT 'available',
            current_location VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS rakes (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            capacity INTEGER NOT NULL,
            status VARCHAR(50) DEFAULT 'available',
            current_location VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS schedules (
            id SERIAL PRIMARY KEY,
            type VARCHAR(50) NOT NULL,
            supplier_id INTEGER REFERENCES suppliers(id),
            port_id INTEGER REFERENCES ports(id),
            plant_id INTEGER REFERENCES plants(id),
            vessel_id INTEGER REFERENCES vessels(id),
            rake_id INTEGER REFERENCES rakes(id),
            quantity INTEGER NOT NULL,
            scheduled_date DATE NOT NULL,
            status VARCHAR(50) DEFAULT 'scheduled',
            created_by VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS stock_levels (
            id SERIAL PRIMARY KEY,
            port_id INTEGER REFERENCES ports(id),
            plant_id INTEGER REFERENCES plants(id),
            stock_level INTEGER NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS user_activities (
            id SERIAL PRIMARY KEY,
            user_email VARCHAR(255) NOT NULL,
            action VARCHAR(255) NOT NULL,
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS uploaded_files (
            id SERIAL PRIMARY KEY,
            filename VARCHAR(255) NOT NULL,
            file_type VARCHAR(50) NOT NULL,
            uploaded_by VARCHAR(255) NOT NULL,
            file_path VARCHAR(500) NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('SELECT COUNT(*) FROM users')
    if cur.fetchone()[0] == 0:
        default_users = [
            ('owner@example.com', generate_password_hash('owner123'), 'System Owner', 'owner'),
            ('manager@example.com', generate_password_hash('manager123'), 'Supply Chain Manager', 'manager'),
            ('admin@example.com', generate_password_hash('admin123'), 'System Administrator', 'admin')
        ]
        cur.executemany(
            'INSERT INTO users (email, password, name, role, verified) VALUES (%s, %s, %s, %s, %s)',
            [(u[0], u[1], u[2], u[3], True) for u in default_users]
        )
    
    cur.execute('SELECT COUNT(*) FROM suppliers')
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO suppliers (name) VALUES ('Default Supplier')")
    cur.execute('SELECT COUNT(*) FROM ports')
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO ports (name, capacity, current_stock) VALUES ('Port X', 10000, 5000), ('Port Y', 15000, 8000)")
    cur.execute('SELECT COUNT(*) FROM plants')
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO plants (name, capacity, current_stock) VALUES ('Plant 1', 5000, 2000), ('Plant 2', 7000, 3000)")
    cur.execute('SELECT COUNT(*) FROM vessels')
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO vessels (name, capacity) VALUES ('Default Vessel', 5000)")
    cur.execute('SELECT COUNT(*) FROM rakes')
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO rakes (name, capacity) VALUES ('Default Rake', 2500)")
    
    cur.execute('SELECT COUNT(*) FROM schedules')
    if cur.fetchone()[0] == 0:
        schedules_to_add = [
            ('vessel-to-port', 1, 1, None, 1, None, 5000, date.today() + timedelta(days=5), 'scheduled', 'system'),
            ('port-to-plant', 1, 2, 1, None, 1, 2000, date.today() - timedelta(days=10), 'completed', 'system'),
            ('vessel-to-port', 1, 2, None, 1, None, 7500, date.today() + timedelta(days=2), 'in-progress', 'system')
        ]
        cur.executemany(
            '''INSERT INTO schedules (type, supplier_id, port_id, plant_id, vessel_id, rake_id, quantity, scheduled_date, status, created_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
            schedules_to_add
        )

    conn.commit()
    cur.close()

@app.cli.command('init-db')
def init_db_command():
    with app.app_context():
        init_db_logic()
    click.echo('Initialized the database.')

def execute_query(query, params=None, fetch=None):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(query, params or ())
    result = None
    if fetch == 'one':
        result = cur.fetchone()
    elif fetch == 'all':
        result = cur.fetchall()
    conn.commit()
    cur.close()
    return result

def log_activity(user_email, action, details=""):
    execute_query(
        'INSERT INTO user_activities (user_email, action, details) VALUES (%s, %s, %s)',
        (user_email, action, details)
    )

def can_edit_data(user_role):
    return user_role in ['admin', 'owner', 'manager']

def is_owner(user_role):
    return user_role in ['admin', 'owner']

@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        user = execute_query('SELECT * FROM users WHERE email = %s', (email,), fetch='one')
        if user and check_password_hash(user['password'], password) and user['role'] == role:
            session.update({'user': email, 'role': user['role'], 'name': user['name'], 'user_id': user['id']})
            log_activity(email, 'login', f'User logged in as {role}')
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid credentials or role mismatch')
    return render_template('login.html')

@app.route('/signup', methods=['POST'])
def signup():
    try:
        data = request.get_json()
        email, password, name, role = data.get('email'), data.get('password'), data.get('name'), 'user'
        if not all([email, password, name]):
            return jsonify({'success': False, 'message': 'All fields are required'})
        if execute_query('SELECT * FROM users WHERE email = %s', (email,), fetch='one'):
            return jsonify({'success': False, 'message': 'User already exists'})
        hashed_password = generate_password_hash(password)
        execute_query(
            'INSERT INTO users (email, password, name, role, verified) VALUES (%s, %s, %s, %s, %s)',
            (email, hashed_password, name, role, True)
        )
        log_activity(email, 'signup', f'New user registered as {role}')
        return jsonify({'success': True, 'message': 'Registration successful! You can now login.'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Registration error: {str(e)}'})

@app.route('/logout')
def logout():
    if 'user' in session:
        log_activity(session['user'], 'logout', 'User logged out')
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user' not in session: return redirect(url_for('login'))
    return render_template('dashboard.html', 
                          user=session.get('name', 'User'),
                          role=session.get('role', 'guest'), 
                          schedules=execute_query('SELECT * FROM schedules ORDER BY created_at DESC LIMIT 5', fetch='all'),
                          ports=execute_query('SELECT * FROM ports', fetch='all'),
                          plants=execute_query('SELECT * FROM plants', fetch='all'))

@app.route('/schedules')
def schedules_page():
    if 'user' not in session: return redirect(url_for('login'))
    schedules = execute_query('''
        SELECT s.*, su.name as supplier_name, p.name as port_name, pl.name as plant_name
        FROM schedules s
        LEFT JOIN suppliers su ON s.supplier_id = su.id
        LEFT JOIN ports p ON s.port_id = p.id
        LEFT JOIN plants pl ON s.plant_id = pl.id
        ORDER BY s.scheduled_date DESC
    ''', fetch='all')
    return render_template('schedules.html', schedules=schedules, can_edit=can_edit_data(session.get('role')))

@app.route('/create_schedule', methods=['GET', 'POST'])
def create_schedule():
    if 'user' not in session or not can_edit_data(session.get('role')): return redirect(url_for('schedules_page'))
    if request.method == 'POST':
        form = request.form
        execute_query(
            '''INSERT INTO schedules (type, supplier_id, port_id, plant_id, vessel_id, rake_id, 
               quantity, scheduled_date, status, created_by) 
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
            (form.get('type'), form.get('supplier_id'), form.get('port_id'), form.get('plant_id'),
             form.get('vessel_id'), form.get('rake_id'), form.get('quantity'), form.get('scheduled_date'),
             'scheduled', session['user'])
        )
        log_activity(session['user'], 'create_schedule', 'Created new schedule')
        return redirect(url_for('schedules_page'))
    
    return render_template('create_schedule.html', 
                          suppliers=execute_query('SELECT * FROM suppliers', fetch='all'), 
                          ports=execute_query('SELECT * FROM ports', fetch='all'), 
                          plants=execute_query('SELECT * FROM plants', fetch='all'),
                          vessels=execute_query('SELECT * FROM vessels', fetch='all'),
                          rakes=execute_query('SELECT * FROM rakes', fetch='all'))

@app.route('/schedules/<int:schedule_id>/status', methods=['POST'])
def update_schedule_status(schedule_id):
    if 'user' not in session or not can_edit_data(session.get('role')):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    new_status = request.json.get('status')
    if not new_status or new_status not in ['scheduled', 'in-progress', 'delayed', 'completed', 'canceled']:
        return jsonify({'success': False, 'message': 'Invalid status provided.'}), 400

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM schedules WHERE id = %s", (schedule_id,))
            schedule = cur.fetchone()
            if not schedule: return jsonify({'success': False, 'message': 'Schedule not found.'}), 404
            if schedule['status'] in ['completed', 'canceled']:
                return jsonify({'success': False, 'message': f"Schedule is already {schedule['status']}."}), 400

            if new_status == 'completed':
                quantity, port_id, plant_id = schedule['quantity'], schedule['port_id'], schedule['plant_id']
                if schedule['type'] == 'vessel-to-port':
                    cur.execute("UPDATE ports SET current_stock = current_stock + %s WHERE id = %s", (quantity, port_id))
                elif schedule['type'] == 'port-to-plant':
                    cur.execute("UPDATE ports SET current_stock = current_stock - %s WHERE id = %s", (quantity, port_id))
                    cur.execute("UPDATE plants SET current_stock = current_stock + %s WHERE id = %s", (quantity, plant_id))
                log_activity(session['user'], 'update_status', f'Completed schedule #{schedule_id} and updated stock.')
            else:
                log_activity(session['user'], 'update_status', f"Updated schedule #{schedule_id} to '{new_status}'.")

            cur.execute("UPDATE schedules SET status = %s WHERE id = %s", (new_status, schedule_id,))
        conn.commit()
        return jsonify({'success': True, 'message': f"Schedule #{schedule_id} updated to '{new_status}'."})
    except Exception as e:
        conn.rollback()
        print(f"Error updating schedule status: {e}")
        return jsonify({'success': False, 'message': 'An error occurred during the update.'}), 500

@app.route('/stock_levels')
def stock_levels_page():
    if 'user' not in session: return redirect(url_for('login'))
    return render_template('stock_levels.html', 
                          ports=execute_query('SELECT * FROM ports', fetch='all'), 
                          plants=execute_query('SELECT * FROM plants', fetch='all'), 
                          stock_levels=execute_query('SELECT * FROM stock_levels ORDER BY timestamp DESC LIMIT 20', fetch='all'))

@app.route('/manage_data')
def manage_data_page():
    if 'user' not in session or not is_owner(session.get('role')): return redirect(url_for('dashboard'))
    return render_template('manage_data.html',
                         ports=execute_query('SELECT * FROM ports', fetch='all'),
                         plants=execute_query('SELECT * FROM plants', fetch='all'),
                         vessels=execute_query('SELECT * FROM vessels', fetch='all'),
                         rakes=execute_query('SELECT * FROM rakes', fetch='all'))

@app.route('/add_location', methods=['POST'])
def add_location():
    if 'user' not in session or not is_owner(session.get('role')):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    try:
        data = request.json
        location_type, name, capacity_str = data.get('type'), data.get('name'), data.get('capacity')
        if not all([location_type, name, capacity_str]):
             return jsonify({'success': False, 'message': 'Missing required fields.'}), 400
        if location_type not in ['port', 'plant']:
            return jsonify({'success': False, 'message': 'Invalid location type.'}), 400
        capacity = int(capacity_str)
        table = f"{location_type}s"
        execute_query(f'INSERT INTO {table} (name, capacity, location) VALUES (%s, %s, %s)', (name, capacity, data.get('location', '')))
        log_activity(session['user'], 'add_location', f'Added {location_type}: {name}')
        return jsonify({'success': True, 'message': f'{location_type.capitalize()} added successfully'})
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Capacity must be a valid number.'}), 400
    except Exception as e:
        print(f"Error in add_location: {e}")
        return jsonify({'success': False, 'message': 'An unexpected server error occurred.'}), 500

@app.route('/delete_location', methods=['POST'])
def delete_location():
    if 'user' not in session or not is_owner(session.get('role')): return jsonify({'success': False, 'message': 'Unauthorized'})
    data = request.json
    location_type, location_id = data.get('type'), int(data.get('id'))
    execute_query(f'DELETE FROM {location_type}s WHERE id = %s', (location_id,))
    log_activity(session['user'], 'delete_location', f'Deleted {location_type} #{location_id}')
    return jsonify({'success': True, 'message': f'{location_type.capitalize()} deleted successfully'})

@app.route('/file_manager')
def file_manager():
    if 'user' not in session: return redirect(url_for('login'))
    return render_template('file_manager.html', 
                           files=execute_query('SELECT * FROM uploaded_files ORDER BY uploaded_at DESC', fetch='all'), 
                           can_upload=can_edit_data(session.get('role')))

@app.route('/upload_file', methods=['POST'])
def upload_file():
    if 'user' not in session or not can_edit_data(session.get('role')): return jsonify({'success': False, 'message': 'Unauthorized'})
    if 'file' not in request.files or not (file := request.files['file']) or file.filename == '' or not allowed_file(file.filename):
        return jsonify({'success': False, 'message': 'Invalid or no file selected'})
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(file_path)
    execute_query(
        'INSERT INTO uploaded_files (filename, file_type, uploaded_by, file_path) VALUES (%s, %s, %s, %s)',
        (file.filename, file.filename.rsplit('.', 1)[1].lower(), session['user'], file_path)
    )
    log_activity(session['user'], 'upload_file', f'Uploaded file: {file.filename}')
    return jsonify({'success': True, 'message': 'File uploaded successfully'})

@app.route('/download_file/<int:file_id>')
def download_file(file_id):
    if 'user' not in session: return redirect(url_for('login'))
    file_record = execute_query('SELECT * FROM uploaded_files WHERE id = %s', (file_id,), fetch='one')
    if not file_record: return 'File not found', 404
    server_filename = os.path.basename(file_record['file_path'])
    log_activity(session['user'], 'download_file', f"Downloaded file: {file_record['filename']}")
    return send_from_directory(UPLOAD_FOLDER, server_filename, as_attachment=True, download_name=file_record['filename'])

@app.route('/reports')
def reports_page():
    if 'user' not in session: return redirect(url_for('login'))
    return render_template('reports.html', 
                          total_schedules=execute_query('SELECT COUNT(*) as count FROM schedules', fetch='one')['count'],
                          completed_schedules=execute_query("SELECT COUNT(*) as count FROM schedules WHERE status = 'completed'", fetch='one')['count'],
                          delayed_schedules=execute_query("SELECT COUNT(*) as count FROM schedules WHERE status = 'delayed'", fetch='one')['count'],
                          port_utilization=execute_query("SELECT name as port, TRUNC((current_stock * 100.0 / capacity), 2) as utilization FROM ports WHERE capacity > 0", fetch='all'))

@app.route('/optimize', methods=['POST'])
def optimize():
    if 'user' not in session: return jsonify({'error': 'Unauthorized'}), 401
    return jsonify({'message': f"Optimization completed", 'estimated_savings': random.randint(1000, 10000)})

@app.route('/predict_delays')
def predict_delays():
    if 'user' not in session: return jsonify({'error': 'Unauthorized'}), 401
    schedules = execute_query("SELECT * FROM schedules WHERE status IN ('scheduled', 'in-progress')", fetch='all')
    delayed_schedules_list = [
        {'schedule_id': s['id'], 'reason': random.choice(['Weather conditions', 'Vessel maintenance', 'Port congestion']), 'estimated_delay_days': random.randint(1, 7)}
        for s in (schedules or []) if random.random() < 0.3
    ]
    return jsonify({'delayed_schedules': delayed_schedules_list})

@app.route('/export_data/<data_type>')
def export_data(data_type):
    if 'user' not in session: return redirect(url_for('login'))
    if data_type not in ['schedules', 'stock_levels']: return 'Invalid data type', 400
    data = execute_query(f'SELECT * FROM {data_type}', fetch='all')
    output = io.StringIO()
    if data:
        writer = csv.DictWriter(output, fieldnames=[k for k in data[0]])
        writer.writeheader()
        writer.writerows([dict(row) for row in data])
    return output.getvalue(), 200, {'Content-Type': 'text/csv', 'Content-Disposition': f'attachment; filename={data_type}.csv'}

if __name__ == '__main__':
    app.run(debug=True)