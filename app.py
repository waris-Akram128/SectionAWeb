from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import requests
from functools import wraps
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, date, timedelta
import traceback
import os

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-1212')

# ============================================
# CONFIGURATION
# ============================================

SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://xgfutdszidrcacrysdyq.supabase.co')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhnZnV0ZHN6aWRyY2FjcnlzZHlxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIzMDIyNjksImV4cCI6MjA4Nzg3ODI2OX0.DkFF5QXvd8g3zu-DjNLcaRrPBZlgkCYg6-2tSYPWmvo')

# Connection pooling for performance
REQUESTS_SESSION = requests.Session()
REQUESTS_SESSION.headers.update({
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=representation'
})

# ============================================
# DECORATORS
# ============================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            if request.is_json:
                return jsonify({'success': False, 'message': 'Login required'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            if request.is_json:
                return jsonify({'success': False, 'message': 'Login required'}), 401
            return redirect(url_for('login'))
        if session['user'].get('role') != 'admin':
            if request.is_json:
                return jsonify({'success': False, 'message': 'Admin access required'}), 403
            return redirect(url_for('student_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ============================================
# HELPER FUNCTIONS
# ============================================

def supabase_request(method, endpoint, data=None):
    """Make request to Supabase REST API"""
    url = f"{SUPABASE_URL}/rest/v1/{endpoint.strip('/')}"
    
    try:
        if method == 'GET':
            response = REQUESTS_SESSION.get(url, params=data, timeout=10)
        elif method == 'POST':
            response = REQUESTS_SESSION.post(url, json=data, timeout=10)
        elif method == 'PATCH':
            response = REQUESTS_SESSION.patch(url, json=data, timeout=10)
        elif method == 'DELETE':
            response = REQUESTS_SESSION.delete(url, timeout=10)
        
        return response
        
    except Exception as e:
        print(f"Request error: {e}")
        return type('obj', (object,), {
            'status_code': 500, 
            'text': str(e), 
            'json': lambda: {'error': str(e)}
        })()

# ============================================
# AUTH ROUTES
# ============================================

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/')
def index():
    if 'user' in session:
        if session['user'].get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('student_dashboard'))
    return redirect(url_for('home'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'success': False, 'message': 'Email and password required'}), 400
        
        try:
            url = f"{SUPABASE_URL}/rest/v1/users?email=eq.{email}&select=*"
            response = REQUESTS_SESSION.get(url, timeout=10)
            result = response.json()
            
            if response.status_code == 200 and len(result) > 0:
                user = result[0]
                
                if user.get('password') == password:
                    role = user.get('role', 'student')
                    
                    session['user'] = {
                        'id': str(user.get('id')),
                        'email': user.get('email'),
                        'name': user.get('name') or email.split('@')[0],
                        'role': role,
                        'roll_no': user.get('roll_no')
                    }
                    
                    if role == 'admin':
                        return jsonify({'success': True, 'redirect': url_for('admin_dashboard')})
                    else:
                        return jsonify({'success': True, 'redirect': url_for('student_dashboard')})
                else:
                    return jsonify({'success': False, 'message': 'Invalid password'}), 401
            else:
                return jsonify({'success': False, 'message': 'User not found'}), 401
                
        except Exception as e:
            print(f"Login error: {e}")
            return jsonify({'success': False, 'message': 'Server error'}), 500
    
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

@app.route('/api/user', methods=['GET'])
@login_required
def get_current_user():
    return jsonify({
        'success': True,
        'data': session['user']
    })

# ============================================
# FIXED ATTENDANCE API
# ============================================

@app.route('/api/attendance/stats', methods=['GET'])
@login_required
def get_attendance_stats():
    """Get dashboard statistics"""
    try:
        user = session['user']
        
        if user['role'] == 'admin':
            today = date.today().isoformat()
            
            # Get all sessions today
            sessions_resp = supabase_request('GET', 
                f"attendance_sessions?date=eq.{today}&select=active")
            
            sessions = sessions_resp.json() if sessions_resp.status_code == 200 else []
            active_sessions = sum(1 for s in sessions if s.get('active', False))
            
            # Get student count
            students_resp = supabase_request('GET', 
                "users?role=eq.student&select=id")
            total_students = len(students_resp.json()) if students_resp.status_code == 200 else 0
            
            return jsonify({
                'success': True,
                'data': {
                    'active_sessions': active_sessions,
                    'total_students': total_students
                }
            })
        else:
            # Student stats
            student_id = user['id']
            
            records_resp = supabase_request('GET', 
                f"attendance_records?student_id=eq.{student_id}")
            
            if records_resp.status_code != 200:
                return jsonify({'success': True, 'data': []})
            
            records = records_resp.json()
            
            subject_stats = {}
            for rec in records:
                sess_resp = supabase_request('GET', 
                    f"attendance_sessions?id=eq.{rec['session_id']}&select=subject_id")
                if sess_resp.status_code != 200 or not sess_resp.json():
                    continue
                    
                subject_id = sess_resp.json()[0]['subject_id']
                
                sub_resp = supabase_request('GET', 
                    f"subjects?id=eq.{subject_id}&select=name")
                if sub_resp.status_code != 200 or not sub_resp.json():
                    continue
                    
                subject_name = sub_resp.json()[0]['name']
                
                if subject_id not in subject_stats:
                    subject_stats[subject_id] = {
                        'name': subject_name,
                        'present': 0,
                        'absent': 0,
                        'total': 0
                    }
                
                subject_stats[subject_id]['total'] += 1
                if rec.get('status') == 'present':
                    subject_stats[subject_id]['present'] += 1
                else:
                    subject_stats[subject_id]['absent'] += 1
            
            return jsonify({
                'success': True,
                'data': list(subject_stats.values())
            })
        
    except Exception as e:
        print(f"Stats error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/attendance/active-sessions', methods=['GET'])
@admin_required
def get_active_sessions():
    """Get all sessions for today"""
    try:
        today = date.today().isoformat()
        
        response = supabase_request('GET', 
            f"attendance_sessions?date=eq.{today}&order=created_at.desc")
        
        if response.status_code != 200:
            return jsonify({'success': False, 'message': 'Failed to fetch sessions'}), 400
        
        sessions = response.json()
        
        # Add subject names
        for sess in sessions:
            sub_resp = supabase_request('GET', 
                f"subjects?id=eq.{sess['subject_id']}&select=name")
            if sub_resp.status_code == 200 and sub_resp.json():
                sess['subject_name'] = sub_resp.json()[0]['name']
            else:
                sess['subject_name'] = 'Unknown Subject'
        
        return jsonify({'success': True, 'data': sessions})
        
    except Exception as e:
        print(f"Active sessions error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/attendance/start', methods=['POST'])
@admin_required
def start_attendance_session():
    """Start a new attendance session"""
    try:
        data = request.get_json()
        subject_id = data.get('subject_id')
        
        if not subject_id:
            return jsonify({'success': False, 'message': 'Subject ID required'}), 400
        
        today = date.today().isoformat()
        now = datetime.now().isoformat()
        
        # Check if session exists
        check_resp = supabase_request('GET', 
            f"attendance_sessions?subject_id=eq.{subject_id}&date=eq.{today}")
        
        if check_resp.status_code == 200 and check_resp.json():
            return jsonify({'success': False, 'message': 'Session already exists for today'}), 400
        
        # Create session
        session_data = {
            'subject_id': subject_id,
            'date': today,
            'started_by': session['user']['id'],
            'active': True,
            'created_at': now
        }
        
        response = supabase_request('POST', 'attendance_sessions', session_data)
        
        if response.status_code != 201:
            return jsonify({'success': False, 'message': f'Failed to create session: {response.text}'}), 400
        
        new_session = response.json()[0]
        
        # Get all students and create records
        students_resp = supabase_request('GET', 
            "users?role=eq.student&select=id")
        
        if students_resp.status_code == 200:
            students = students_resp.json()
            
            for student in students:
                record = {
                    'session_id': new_session['id'],
                    'student_id': student['id'],
                    'status': 'present',
                    'marked_by': session['user']['id'],
                    'marked_at': now
                }
                supabase_request('POST', 'attendance_records', record)
            
            new_session['total_students'] = len(students)
        
        # Get subject name
        sub_resp = supabase_request('GET', 
            f"subjects?id=eq.{subject_id}&select=name")
        if sub_resp.status_code == 200 and sub_resp.json():
            new_session['subject_name'] = sub_resp.json()[0]['name']
        
        return jsonify({'success': True, 'data': new_session})
        
    except Exception as e:
        print(f"Start session error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/attendance/session/<session_id>/students', methods=['GET'])
@admin_required
def get_session_students(session_id):
    """Get all students with their attendance status for a session - FIXED"""
    try:
        print(f"\n=== Getting students for session: {session_id} ===")
        
        # Get session info
        sess_resp = supabase_request('GET', 
            f"attendance_sessions?id=eq.{session_id}")
        
        if sess_resp.status_code != 200 or not sess_resp.json():
            return jsonify({'success': False, 'message': 'Session not found'}), 404
        
        session_info = sess_resp.json()[0]
        
        # Get subject name
        sub_resp = supabase_request('GET', 
            f"subjects?id=eq.{session_info['subject_id']}&select=name")
        subject_name = "Unknown"
        if sub_resp.status_code == 200 and sub_resp.json():
            subject_name = sub_resp.json()[0]['name']
        
        # Get all students
        students_resp = supabase_request('GET', 
            "users?role=eq.student&select=id,name,email,roll_no")
        
        if students_resp.status_code != 200:
            return jsonify({'success': False, 'message': 'Failed to fetch students'}), 400
        
        students = students_resp.json()
        print(f"Found {len(students)} total students")
        
        # Get existing attendance records
        records_resp = supabase_request('GET', 
            f"attendance_records?session_id=eq.{session_id}")
        
        records = {}
        if records_resp.status_code == 200:
            for rec in records_resp.json():
                records[str(rec['student_id'])] = rec
        
        print(f"Found {len(records)} existing records")
        
        # Build student list
        student_list = []
        for student in students:
            student_id = str(student['id'])
            student_data = {
                'id': student_id,
                'name': student.get('name') or student.get('email', 'Unknown'),
                'email': student.get('email', ''),
                'roll_no': student.get('roll_no', '-'),
                'status': 'present',
                'record_id': None
            }
            
            if student_id in records:
                student_data['status'] = records[student_id]['status']
                student_data['record_id'] = records[student_id]['id']
            
            student_list.append(student_data)
        
        print(f"Returning {len(student_list)} students")
        
        return jsonify({
            'success': True,
            'session': {
                'id': session_id,
                'subject_name': subject_name,
                'date': session_info['date']
            },
            'data': student_list
        })
        
    except Exception as e:
        print(f"Session students error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/attendance/mark-bulk', methods=['POST'])
@admin_required
def mark_bulk_attendance():
    """Mark attendance for multiple students - FIXED VERSION"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        students = data.get('students', [])
        
        print(f"\n=== Marking bulk attendance ===")
        print(f"Session: {session_id}")
        print(f"Students data received: {students}")
        
        if not session_id or not students:
            return jsonify({'success': False, 'message': 'Invalid data'}), 400
        
        now = datetime.now().isoformat()
        count = 0
        
        # First, get ALL existing records for this session in one query
        check_resp = supabase_request('GET', 
            f"attendance_records?session_id=eq.{session_id}&select=id,student_id,status")
        
        existing_records = {}
        if check_resp.status_code == 200:
            for rec in check_resp.json():
                existing_records[rec['student_id']] = {
                    'id': rec['id'],
                    'status': rec['status']
                }
            print(f"Found {len(existing_records)} existing records")
        
        for student_data in students:
            student_id = student_data.get('student_id')
            status = student_data.get('status', 'present')
            
            if not student_id:
                print(f"Skipping - no student_id")
                continue
            
            print(f"Processing student {student_id} -> {status}")
            
            # Check if this student already has a record
            if student_id in existing_records:
                # Update existing record
                record_id = existing_records[student_id]['id']
                current_status = existing_records[student_id]['status']
                
                # Only update if status changed
                if current_status != status:
                    update_data = {
                        'status': status,
                        'marked_by': session['user']['id'],
                        'marked_at': now
                    }
                    update_resp = supabase_request('PATCH', 
                        f"attendance_records?id=eq.{record_id}", update_data)
                    
                    if update_resp.status_code == 200:
                        print(f"  Updated record {record_id} from {current_status} to {status}")
                        count += 1
                    else:
                        print(f"  Update failed: {update_resp.text}")
                else:
                    print(f"  No change needed (already {status})")
                    count += 1  # Count as success since it's already correct
            else:
                # Create new record
                new_record = {
                    'session_id': session_id,
                    'student_id': student_id,
                    'status': status,
                    'marked_by': session['user']['id'],
                    'marked_at': now
                }
                create_resp = supabase_request('POST', 'attendance_records', new_record)
                
                if create_resp.status_code == 201:
                    print(f"  Created new record with status {status}")
                    count += 1
                else:
                    print(f"  Create failed: {create_resp.text}")
        
        print(f"Successfully processed {count} students")
        
        return jsonify({
            'success': True,
            'count': count,
            'message': f'Attendance saved for {count} students'
        })
        
    except Exception as e:
        print(f"Mark bulk error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500
@app.route('/api/attendance/stop/<session_id>', methods=['POST'])
@admin_required
def stop_attendance_session(session_id):
    """Stop an attendance session - FIXED"""
    try:
        print(f"\n=== Stopping session: {session_id} ===")
        
        # First verify the session exists
        check_resp = supabase_request('GET', 
            f"attendance_sessions?id=eq.{session_id}")
        
        if check_resp.status_code != 200 or not check_resp.json():
            return jsonify({'success': False, 'message': 'Session not found'}), 404
        
        # Update to inactive
        update_data = {'active': False}
        response = supabase_request('PATCH', 
            f"attendance_sessions?id=eq.{session_id}", 
            update_data)
        
        print(f"Update response: {response.status_code}")
        
        if response.status_code == 200:
            return jsonify({'success': True, 'message': 'Session stopped successfully'})
        else:
            print(f"Stop failed: {response.text}")
            return jsonify({'success': False, 'message': f'Failed to stop session: {response.text}'}), 400
            
    except Exception as e:
        print(f"Stop session error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/attendance/my', methods=['GET'])
@login_required
def get_my_attendance():
    """Student gets their attendance history"""
    try:
        student_id = session['user']['id']
        
        response = supabase_request('GET', 
            f"attendance_records?student_id=eq.{student_id}&order=marked_at.desc")
        
        if response.status_code != 200:
            return jsonify({'success': False, 'message': 'Failed to fetch records'}), 400
        
        records = response.json()
        
        # Enrich with subject info
        for rec in records:
            sess_resp = supabase_request('GET', 
                f"attendance_sessions?id=eq.{rec['session_id']}&select=subject_id,date")
            if sess_resp.status_code == 200 and sess_resp.json():
                sess = sess_resp.json()[0]
                rec['date'] = sess['date']
                
                sub_resp = supabase_request('GET', 
                    f"subjects?id=eq.{sess['subject_id']}&select=name,code")
                if sub_resp.status_code == 200 and sub_resp.json():
                    sub = sub_resp.json()[0]
                    rec['subject_name'] = sub['name']
                    rec['subject_code'] = sub['code']
        
        return jsonify({'success': True, 'data': records})
        
    except Exception as e:
        print(f"My attendance error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ============================================
# SUBJECTS API
# ============================================

@app.route('/api/subjects', methods=['GET'])
@login_required
def get_subjects():
    try:
        response = supabase_request('GET', 'subjects?order=name.asc')
        
        if response.status_code == 200:
            return jsonify({'success': True, 'data': response.json()})
        else:
            return jsonify({'success': False, 'message': 'Failed to fetch subjects'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/subjects', methods=['POST'])
@admin_required
def create_subject():
    try:
        data = request.get_json()
        
        if not data.get('name') or not data.get('code'):
            return jsonify({'success': False, 'message': 'Name and code required'}), 400
        
        subject_data = {
            'name': data.get('name').strip(),
            'code': data.get('code').strip().upper(),
            'description': data.get('description', '').strip(),
            'credits': int(data.get('credits', 3)),
            'created_by': session['user']['id']
        }
        
        response = supabase_request('POST', 'subjects', subject_data)
        
        if response.status_code == 201:
            return jsonify({'success': True, 'data': response.json()[0]})
        else:
            return jsonify({'success': False, 'message': response.text}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/subjects/<id>', methods=['DELETE'])
@admin_required
def delete_subject(id):
    try:
        response = supabase_request('DELETE', f'subjects?id=eq.{id}')
        
        if response.status_code == 200:
            return jsonify({'success': True, 'message': 'Subject deleted'})
        else:
            return jsonify({'success': False, 'message': 'Delete failed'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ============================================
# RESOURCES API
# ============================================

@app.route('/api/resources', methods=['GET'])
@login_required
def get_resources():
    try:
        subject_id = request.args.get('subject_id')
        
        if subject_id:
            endpoint = f"resources?subject_id=eq.{subject_id}&order=created_at.desc"
        else:
            endpoint = 'resources?order=created_at.desc'
            
        response = supabase_request('GET', endpoint)
        
        if response.status_code == 200:
            resources = response.json()
            
            for res in resources:
                sub_resp = supabase_request('GET', f"subjects?id=eq.{res['subject_id']}&select=name")
                if sub_resp.status_code == 200 and sub_resp.json():
                    res['subject_name'] = sub_resp.json()[0]['name']
                
                user_resp = supabase_request('GET', f"users?id=eq.{res['uploaded_by']}&select=name,email")
                if user_resp.status_code == 200 and user_resp.json():
                    user = user_resp.json()[0]
                    res['uploader_name'] = user.get('name', user['email'])
            
            return jsonify({'success': True, 'data': resources})
        else:
            return jsonify({'success': False, 'message': 'Failed to fetch resources'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/resources', methods=['POST'])
@admin_required
def create_resource():
    try:
        data = request.get_json()
        
        if not data.get('title') or not data.get('file_url') or not data.get('subject_id'):
            return jsonify({'success': False, 'message': 'Title, file URL and subject required'}), 400
        
        resource_data = {
            'title': data.get('title').strip(),
            'description': data.get('description', '').strip(),
            'file_url': data.get('file_url').strip(),
            'file_type': data.get('file_type', 'document'),
            'subject_id': data.get('subject_id'),
            'uploaded_by': session['user']['id']
        }
        
        response = supabase_request('POST', 'resources', resource_data)
        
        if response.status_code == 201:
            return jsonify({'success': True, 'data': response.json()[0]})
        else:
            return jsonify({'success': False, 'message': response.text}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/resources/<id>', methods=['DELETE'])
@admin_required
def delete_resource(id):
    try:
        response = supabase_request('DELETE', f'resources?id=eq.{id}')
        
        if response.status_code == 200:
            return jsonify({'success': True, 'message': 'Resource deleted'})
        else:
            return jsonify({'success': False, 'message': 'Delete failed'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ============================================
# ANNOUNCEMENTS API
# ============================================

@app.route('/api/announcements', methods=['GET'])
@login_required
def get_announcements():
    try:
        response = supabase_request('GET', 'announcements?order=created_at.desc')
        
        if response.status_code == 200:
            return jsonify({'success': True, 'data': response.json()})
        else:
            return jsonify({'success': False, 'message': 'Failed to fetch announcements'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/announcements', methods=['POST'])
@admin_required
def create_announcement():
    try:
        data = request.get_json()
        
        if not data.get('title') or not data.get('content'):
            return jsonify({'success': False, 'message': 'Title and content required'}), 400
        
        announcement_data = {
            'title': data.get('title').strip(),
            'content': data.get('content').strip(),
            'priority': data.get('priority', 'normal'),
            'author_name': session['user'].get('name', 'Admin'),
            'created_at': datetime.now().isoformat()
        }
        
        response = supabase_request('POST', 'announcements', announcement_data)
        
        if response.status_code == 201:
            return jsonify({'success': True, 'data': response.json()[0]})
        else:
            return jsonify({'success': False, 'message': response.text}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

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

# ============================================
# LEAVE MANAGEMENT API - NEW
# ============================================

@app.route('/api/leaves', methods=['POST'])
@login_required
def apply_for_leave():
    """Student applies for leave"""
    try:
        data = request.get_json()
        user = session['user']
        
        # Validate required fields
        required = ['start_date', 'end_date', 'reason', 'leave_type']
        for field in required:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'{field} is required'}), 400
        
        # Validate dates
        try:
            start = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
            end = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
            if end < start:
                return jsonify({'success': False, 'message': 'End date must be after start date'}), 400
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid date format. Use YYYY-MM-DD'}), 400
        
        leave_data = {
            'student_id': user['id'],
            'student_name': user.get('name', user['email']),
            'roll_no': user.get('roll_no', '-'),
            'start_date': data['start_date'],
            'end_date': data['end_date'],
            'reason': data['reason'].strip(),
            'leave_type': data['leave_type'],  # sick, casual, emergency, etc.
            'status': 'pending',
            'applied_at': datetime.now().isoformat()
        }
        
        response = supabase_request('POST', 'leaves', leave_data)
        
        if response.status_code == 201:
            return jsonify({
                'success': True, 
                'message': 'Leave application submitted successfully',
                'data': response.json()[0]
            })
        else:
            return jsonify({'success': False, 'message': f'Failed to submit: {response.text}'}), 400
            
    except Exception as e:
        print(f"Apply leave error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/leaves/my', methods=['GET'])
@login_required
def get_my_leaves():
    """Student views their leave applications"""
    try:
        student_id = session['user']['id']
        
        response = supabase_request('GET', 
            f"leaves?student_id=eq.{student_id}&order=applied_at.desc")
        
        if response.status_code == 200:
            return jsonify({'success': True, 'data': response.json()})
        else:
            return jsonify({'success': False, 'message': 'Failed to fetch leaves'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/leaves/pending', methods=['GET'])
@admin_required
def get_pending_leaves():
    """Admin views all pending leave applications"""
    try:
        response = supabase_request('GET', 
            f"leaves?status=eq.pending&order=applied_at.desc")
        
        if response.status_code == 200:
            leaves = response.json()
            return jsonify({'success': True, 'data': leaves})
        else:
            return jsonify({'success': False, 'message': 'Failed to fetch leaves'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/leaves/all', methods=['GET'])
@admin_required
def get_all_leaves():
    """Admin views all leave applications with filters"""
    try:
        status = request.args.get('status')
        
        if status:
            endpoint = f"leaves?status=eq.{status}&order=applied_at.desc"
        else:
            endpoint = "leaves?order=applied_at.desc"
            
        response = supabase_request('GET', endpoint)
        
        if response.status_code == 200:
            return jsonify({'success': True, 'data': response.json()})
        else:
            return jsonify({'success': False, 'message': 'Failed to fetch leaves'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/leaves/<leave_id>/approve', methods=['POST'])
@admin_required
def approve_leave(leave_id):
    """Admin approves a leave application"""
    try:
        data = request.get_json() or {}
        
        update_data = {
            'status': 'approved',
            'approved_by': session['user']['id'],
            'approved_at': datetime.now().isoformat(),
            'admin_remarks': data.get('remarks', '')
        }
        
        response = supabase_request('PATCH', 
            f"leaves?id=eq.{leave_id}", update_data)
        
        if response.status_code == 200:
            # Get student email to notify
            leave_resp = supabase_request('GET', 
                f"leaves?id=eq.{leave_id}&select=student_id")
            if leave_resp.status_code == 200 and leave_resp.json():
                student_id = leave_resp.json()[0]['student_id']
                # Could send email notification here
            
            return jsonify({'success': True, 'message': 'Leave approved'})
        else:
            return jsonify({'success': False, 'message': f'Failed: {response.text}'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/leaves/<leave_id>/reject', methods=['POST'])
@admin_required
def reject_leave(leave_id):
    """Admin rejects a leave application"""
    try:
        data = request.get_json() or {}
        
        if not data.get('reason'):
            return jsonify({'success': False, 'message': 'Rejection reason is required'}), 400
        
        update_data = {
            'status': 'rejected',
            'approved_by': session['user']['id'],
            'approved_at': datetime.now().isoformat(),
            'admin_remarks': data.get('reason', '')
        }
        
        response = supabase_request('PATCH', 
            f"leaves?id=eq.{leave_id}", update_data)
        
        if response.status_code == 200:
            return jsonify({'success': True, 'message': 'Leave rejected'})
        else:
            return jsonify({'success': False, 'message': f'Failed: {response.text}'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/leaves/<leave_id>/cancel', methods=['POST'])
@login_required
def cancel_leave(leave_id):
    """Student cancels their pending leave application"""
    try:
        student_id = session['user']['id']
        
        # Verify ownership
        check_resp = supabase_request('GET', 
            f"leaves?id=eq.{leave_id}&student_id=eq.{student_id}&status=eq.pending")
        
        if check_resp.status_code != 200 or not check_resp.json():
            return jsonify({'success': False, 'message': 'Leave not found or cannot be cancelled'}), 400
        
        response = supabase_request('DELETE', f"leaves?id=eq.{leave_id}")
        
        if response.status_code == 200:
            return jsonify({'success': True, 'message': 'Leave application cancelled'})
        else:
            return jsonify({'success': False, 'message': 'Failed to cancel'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    

# ============================================
# CSV EXPORT API - NEW
# ============================================

import csv
import io
from flask import Response, send_file

@app.route('/api/attendance/export', methods=['GET'])
@admin_required
def export_attendance_csv():
    """Export attendance data as CSV for a specific subject"""
    try:
        subject_id = request.args.get('subject_id')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if not subject_id:
            return jsonify({'success': False, 'message': 'Subject ID required'}), 400
        
        # Get subject details
        sub_resp = supabase_request('GET', f"subjects?id=eq.{subject_id}&select=name,code")
        if sub_resp.status_code != 200 or not sub_resp.json():
            return jsonify({'success': False, 'message': 'Subject not found'}), 404
        
        subject = sub_resp.json()[0]
        subject_name = subject['name']
        subject_code = subject['code']
        
        # Build session query
        session_endpoint = f"attendance_sessions?subject_id=eq.{subject_id}&select=id,date"
        if start_date:
            session_endpoint += f"&date=gte.{start_date}"
        if end_date:
            session_endpoint += f"&date=lte.{end_date}"
        session_endpoint += "&order=date.asc"
        
        sessions_resp = supabase_request('GET', session_endpoint)
        if sessions_resp.status_code != 200:
            return jsonify({'success': False, 'message': 'Failed to fetch sessions'}), 400
        
        sessions = sessions_resp.json()
        session_ids = [s['id'] for s in sessions]
        session_dates = {s['id']: s['date'] for s in sessions}
        
        if not session_ids:
            return jsonify({'success': False, 'message': 'No sessions found for this criteria'}), 404
        
        # Get all students
        students_resp = supabase_request('GET', "users?role=eq.student&select=id,name,email,roll_no&order=roll_no.asc")
        if students_resp.status_code != 200:
            return jsonify({'success': False, 'message': 'Failed to fetch students'}), 400
        
        students = students_resp.json()
        
        # Get attendance records for these sessions
        records_map = {}
        for session_id in session_ids:
            rec_resp = supabase_request('GET', f"attendance_records?session_id=eq.{session_id}&select=student_id,status")
            if rec_resp.status_code == 200:
                for rec in rec_resp.json():
                    key = f"{session_id}_{rec['student_id']}"
                    records_map[key] = rec['status']
        
        # Generate CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header row
        header = ['Roll No', 'Student Name', 'Email'] + [session_dates[sid] for sid in session_ids] + ['Total Present', 'Total Absent', 'Percentage']
        writer.writerow(header)
        
        # Data rows
        for student in students:
            row = [
                student.get('roll_no', '-'),
                student.get('name', 'Unknown'),
                student.get('email', '-')
            ]
            
            present_count = 0
            absent_count = 0
            
            for session_id in session_ids:
                key = f"{session_id}_{student['id']}"
                status = records_map.get(key, 'absent')
                row.append('P' if status == 'present' else 'A')
                
                if status == 'present':
                    present_count += 1
                else:
                    absent_count += 1
            
            total = present_count + absent_count
            percentage = round((present_count / total * 100), 2) if total > 0 else 0
            
            row.extend([present_count, absent_count, f"{percentage}%"])
            writer.writerow(row)
        
        # Summary rows
        writer.writerow([])
        writer.writerow(['Subject:', subject_name])
        writer.writerow(['Code:', subject_code])
        writer.writerow(['Period:', f"{start_date or 'All'} to {end_date or 'All'}"])
        writer.writerow(['Generated:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow(['Total Sessions:', len(session_ids)])
        
        output.seek(0)
        
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename=attendance_{subject_code}_{datetime.now().strftime("%Y%m%d")}.csv',
                'Content-Type': 'text/csv; charset=utf-8'
            }
        )
        
    except Exception as e:
        print(f"Export error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000, threaded=True)
