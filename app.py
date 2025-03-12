import os
import logging
import tempfile
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import mysql.connector
from werkzeug.utils import secure_filename
from db_operations import (
    get_connection, test_connection, get_tables, 
    get_table_columns, create_table, perform_sync
)
from excel_operations import (
    get_excel_columns, validate_excel_file, 
    get_excel_preview
)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "a-very-secret-key")

# Set max upload size to 16MB
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Create temp directory if it doesn't exist
UPLOAD_FOLDER = tempfile.gettempdir()
ALLOWED_EXTENSIONS = {'xls', 'xlsx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    # Clear any existing session data
    session.clear()
    return render_template('index.html')

@app.route('/connection', methods=['GET', 'POST'])
def connection():
    if request.method == 'POST':
        # Get database connection parameters
        host = request.form.get('host')
        port = request.form.get('port')
        user = request.form.get('user')
        password = request.form.get('password')
        database = request.form.get('database')
        
        # Validate inputs
        if not all([host, port, user, database]):
            flash('All fields except password are required', 'danger')
            return render_template('connection.html')
        
        # Store connection info in session
        session['db_config'] = {
            'host': host,
            'port': int(port),
            'user': user,
            'password': password,
            'database': database
        }
        
        # Test connection
        try:
            test_connection(session['db_config'])
            flash('Connection successful!', 'success')
            return redirect(url_for('file_upload'))
        except Exception as e:
            flash(f'Connection failed: {str(e)}', 'danger')
            logger.error(f"Database connection error: {str(e)}")
            return render_template('connection.html')
    
    return render_template('connection.html')

@app.route('/file_upload', methods=['GET', 'POST'])
def file_upload():
    if 'db_config' not in session:
        flash('Please configure database connection first', 'warning')
        return redirect(url_for('connection'))
        
    if request.method == 'POST':
        # Check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
            
        file = request.files['file']
        
        # If user does not select file, browser also
        # submit an empty part without filename
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
            
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            
            # Validate Excel file
            try:
                validate_excel_file(filepath)
                session['excel_file'] = filepath
                flash('File uploaded successfully!', 'success')
                return redirect(url_for('table_selection'))
            except Exception as e:
                flash(f'Invalid Excel file: {str(e)}', 'danger')
                logger.error(f"Excel validation error: {str(e)}")
                return redirect(request.url)
        else:
            flash('Allowed file types are xls and xlsx', 'danger')
            
    return render_template('file_upload.html')

@app.route('/table_selection', methods=['GET', 'POST'])
def table_selection():
    if 'db_config' not in session or 'excel_file' not in session:
        flash('Please upload an Excel file first', 'warning')
        return redirect(url_for('file_upload'))
        
    excel_preview = get_excel_preview(session['excel_file'])
    session['excel_columns'] = get_excel_columns(session['excel_file'])
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'use_existing':
            table_name = request.form.get('existing_table')
            if not table_name:
                flash('Please select a table', 'danger')
                return redirect(request.url)
                
            session['table_name'] = table_name
            session['create_new'] = False
            
            return redirect(url_for('column_mapping'))
            
        elif action == 'create_new':
            table_name = request.form.get('new_table_name')
            if not table_name:
                flash('Please enter a table name', 'danger')
                return redirect(request.url)
                
            # Check if table already exists
            db_tables = get_tables(session['db_config'])
            if table_name in db_tables:
                flash(f'Table {table_name} already exists', 'danger')
                return redirect(request.url)
                
            session['table_name'] = table_name
            session['create_new'] = True
            
            return redirect(url_for('column_mapping'))
    
    try:
        tables = get_tables(session['db_config'])
        return render_template('table_selection.html', 
                               tables=tables, 
                               excel_preview=excel_preview,
                               excel_columns=session['excel_columns'])
    except Exception as e:
        flash(f'Error getting database tables: {str(e)}', 'danger')
        logger.error(f"Error fetching database tables: {str(e)}")
        return redirect(url_for('file_upload'))

@app.route('/column_mapping', methods=['GET', 'POST'])
def column_mapping():
    if ('db_config' not in session or 'excel_file' not in session or 
            'table_name' not in session or 'excel_columns' not in session):
        flash('Please select a table first', 'warning')
        return redirect(url_for('table_selection'))
    
    excel_columns = session['excel_columns']
    table_name = session['table_name']
    create_new = session.get('create_new', False)
    
    if request.method == 'POST':
        column_mapping = {}
        primary_key = request.form.get('primary_key')
        
        for excel_col in excel_columns:
            db_col = request.form.get(f'mapping_{excel_col}')
            if db_col and db_col != 'ignore':
                column_mapping[excel_col] = db_col
                
        if not column_mapping:
            flash('Please map at least one column', 'danger')
            return redirect(request.url)
            
        session['column_mapping'] = column_mapping
        session['primary_key'] = primary_key
        
        if create_new:
            # Define column types for new table
            column_types = {}
            for excel_col in column_mapping.keys():
                col_type = request.form.get(f'type_{excel_col}')
                if not col_type:
                    flash('Please specify types for all mapped columns', 'danger')
                    return redirect(request.url)
                column_types[excel_col] = col_type
                
            session['column_types'] = column_types
        
        return redirect(url_for('sync_data'))
    
    try:
        db_columns = []
        if not create_new:
            db_columns = get_table_columns(session['db_config'], table_name)
            
        return render_template('column_mapping.html',
                              excel_columns=excel_columns,
                              db_columns=db_columns,
                              table_name=table_name,
                              create_new=create_new,
                              excel_preview=get_excel_preview(session['excel_file']))
    except Exception as e:
        flash(f'Error getting table structure: {str(e)}', 'danger')
        logger.error(f"Error fetching table structure: {str(e)}")
        return redirect(url_for('table_selection'))

@app.route('/sync_data')
def sync_data():
    if ('db_config' not in session or 'excel_file' not in session or 
            'table_name' not in session or 'column_mapping' not in session):
        flash('Please map columns first', 'warning')
        return redirect(url_for('column_mapping'))
    
    try:
        # Initialize variables
        table_name = session['table_name']
        create_new = session.get('create_new', False)
        result = None
        
        if create_new:
            # Create new table
            column_mapping = session['column_mapping']
            column_types = session.get('column_types', {})
            primary_key = session.get('primary_key')
            
            # Create column definitions for new table
            column_defs = {}
            for excel_col, db_col in column_mapping.items():
                column_defs[db_col] = column_types[excel_col]
            
            create_table(session['db_config'], table_name, column_defs, primary_key)
            flash(f'Table {table_name} created successfully', 'success')
        
        # Perform sync operation
        result = perform_sync(
            session['db_config'],
            session['excel_file'],
            session['table_name'],
            session['column_mapping'],
            session.get('primary_key')
        )
        
        return render_template('sync_results.html', result=result)
        
    except Exception as e:
        flash(f'Error during synchronization: {str(e)}', 'danger')
        logger.error(f"Sync error: {str(e)}")
        return redirect(url_for('column_mapping'))

@app.route('/get_table_columns', methods=['POST'])
def get_table_columns_api():
    if 'db_config' not in session:
        return jsonify({'error': 'Database connection not configured'}), 400
        
    table_name = request.json.get('table_name')
    if not table_name:
        return jsonify({'error': 'Table name not provided'}), 400
        
    try:
        columns = get_table_columns(session['db_config'], table_name)
        return jsonify({'columns': columns})
    except Exception as e:
        logger.error(f"Error fetching table columns: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.errorhandler(413)
def request_entity_too_large(error):
    flash('File too large. Maximum size is 16MB.', 'danger')
    return redirect(url_for('file_upload'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
