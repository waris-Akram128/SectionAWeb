# app.py
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import requests
from functools import wraps

app = Flask(__name__)
app.secret_key = 'dev-secret-key-1212'

# Hardcoded Supabase credentials
SUPABASE_URL = 'https://xgfutdszidrcacrysdyq.supabase.co'
SUPABASE_KEY = 'sb_secret_ozOHJ0oI9yqENyBZ-CPxrQ_OMekr5Wp'

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        if session['user'].get('role') != 'admin':
            return jsonify({'success': False, 'message': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        if session['user'].get('role') != 'student':
            return jsonify({'success': False, 'message': 'Student access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

# Helper function for Supabase requests
def supabase_request(method, endpoint, data=None, token=None):
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {token or SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    
    if method == 'GET':
        response = requests.get(url, headers=headers, params=data)
    elif method == 'POST':
        response = requests.post(url, headers=headers, json=data)
    elif method == 'PATCH':
        response = requests.patch(url, headers=headers, json=data)
    elif method == 'DELETE':
        response = requests.delete(url, headers=headers)
    
    return response

@app.route('/home')
def home():
    return render_template('home.html')

@app.route('/')
def index():
    return redirect(url_for('home'))  # or keep as login if preferred

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        
        try:
            # Query users table to verify credentials
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/users?email=eq.{email}",
                headers={
                    'apikey': SUPABASE_KEY,
                    'Content-Type': 'application/json'
                }
            )
            
            result = response.json()
            
            if response.status_code == 200 and len(result) > 0:
                user = result[0]
                
                # Verify password
                if user.get('password') == password:
                    role = user.get('role', 'student')
                    
                    session['user'] = {
                        'id': user.get('id'),
                        'email': user.get('email'),
                        'role': role
                    }
                    
                    # Redirect based on role
                    if role == 'admin':
                        return jsonify({'success': True, 'redirect': url_for('admin_dashboard')})
                    else:
                        return jsonify({'success': True, 'redirect': url_for('student_dashboard')})
                else:
                    return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
            else:
                return jsonify({'success': False, 'message': 'User not found'}), 401
                
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 400
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    return render_template('admin.html')

@app.route('/student/dashboard')
@login_required
def student_dashboard():
    return render_template('student.html')

# ==================== ANNOUNCEMENT API ROUTES ====================

# API: Get all announcements
@app.route('/api/announcements', methods=['GET'])
@login_required
def get_announcements():
    try:
        # Order by created_at descending (newest first)
        response = supabase_request('GET', 'announcements?order=created_at.desc')
        
        if response.status_code == 200:
            return jsonify({'success': True, 'data': response.json()})
        else:
            return jsonify({'success': False, 'message': 'Failed to fetch announcements'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# API: Create announcement
@app.route('/api/announcements', methods=['POST'])
@admin_required
def create_announcement():
    try:
        data = request.get_json()
        
        announcement_data = {
        'title': data.get('title'),
        'content': data.get('content'),
        'priority': data.get('priority', 'normal'),
        'author_name': session['user'].get('email', 'Admin')
        }
        
        response = supabase_request('POST', 'announcements', announcement_data)
        
        if response.status_code == 201:
            return jsonify({'success': True, 'data': response.json()[0]})
        else:
            return jsonify({'success': False, 'message': response.text}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# API: Update announcement
@app.route('/api/announcements/<id>', methods=['PATCH'])
@admin_required
def update_announcement(id):
    try:
        data = request.get_json()
        
        update_data = {
            'title': data.get('title'),
            'content': data.get('content'),
            'priority': data.get('priority')
        }
        
        response = supabase_request('PATCH', f'announcements?id=eq.{id}', update_data)
        
        if response.status_code == 200:
            return jsonify({'success': True, 'data': response.json()[0]})
        else:
            return jsonify({'success': False, 'message': 'Update failed'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# API: Delete announcement
@app.route('/api/announcements/<id>', methods=['DELETE'])
@admin_required
def delete_announcement(id):
    try:
        response = supabase_request('DELETE', f'announcements?id=eq.{id}')
        
        if response.status_code == 200:
            return jsonify({'success': True, 'message': 'Announcement deleted'})
        else:
            return jsonify({'success': False, 'message': 'Delete failed'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)