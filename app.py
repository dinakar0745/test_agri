import ftplib
import hashlib
import os
import random

import MySQLdb.cursors
import requests
from flask import Flask, render_template, redirect, url_for, request, session, flash, send_from_directory, jsonify
from flask_mysqldb import MySQL
import uuid


app = Flask(__name__)
app.config['SECRET_KEY'] = 'Welcome987*'
app.config['MYSQL_HOST'] = 'agriuniklh.ddns.net'
app.config['MYSQL_USER'] = 'devout'
app.config['MYSQL_PASSWORD'] = '123456789'
app.config['MYSQL_DB'] = 'agriuni'
app.config['MYSQL_PORT'] = 3306

mysql = MySQL(app)

# FTP Config
FTP_SERVER = 'vedardhagudapati.ddns.net'
FTP_USERNAME = 'vedardha'
FTP_PASSWORD = 'mnr@123'
FTP_DIR = '/Uploads/'

def connect_ftp():
    """ Connects to the FTP server """
    ftp = ftplib.FTP(FTP_SERVER)
    ftp.login(FTP_USERNAME, FTP_PASSWORD)
    ftp.cwd(FTP_DIR)
    return ftp

# WebDAV Config
WEBDAV_BASE_URL = 'http://agriuniklh.ddns.net:200/agriculture/Uploads/'
WEBDAV_USERNAME = 'webdav'
WEBDAV_PASSWORD = 'mnr@123'


def fetch_images(case_id):
    """ Fetches image names from the FTP server for a particular case ID """
    ftp = connect_ftp()
    images = []
    try:
        ftp.cwd(f"{case_id}/")  # Assuming case images are stored in directories named after case IDs
        images = ftp.nlst()  # List files in the directory
    except Exception as e:
        print(f"Error fetching images: {e}")
    finally:
        ftp.quit()
    return images

def generate_new_case_id():
    """ Generates a new case ID using UUID v4 """
    return str(uuid.uuid4())  # Generates a UUID v4 string


# def save_new_case_id_to_db(case_id, selected_images):
#     """ Update the case_id for selected images in the database """
#     cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

#     try:
#         # Update the case_id for the selected images in the database
#         for image in selected_images:
#             cursor.execute("""
#                 UPDATE images SET case_id = %s WHERE fileName = %s
#             """, (case_id, image.split('/')[-1]))  # Use the image file name from the URL

#         mysql.connection.commit()
#     except MySQLdb.Error as e:
#         print(f"Error updating case ID: {e}")
#         mysql.connection.rollback()
#     finally:
#         cursor.close()
def save_new_case_id_to_db(case_id, selected_images):
    """ Update the case_id and current timestamp for selected images in the database """
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    try:
        # Update the case_id and the current timestamp (assuming an 'updated_at' column exists)
        for image in selected_images:
            cursor.execute("""
                UPDATE images 
                SET case_id = %s, uploaded_at = NOW()  -- Update case_id and set updated_at to the current timestamp
                WHERE fileName = %s
            """, (case_id, image.split('/')[-1]))  # Use the image file name from the URL

        mysql.connection.commit()
    except MySQLdb.Error as e:
        print(f"Error updating case ID: {e}")
        mysql.connection.rollback()
    finally:
        cursor.close()


@app.route('/temp/<filename>')
def get_temp_file(filename):
    return send_from_directory('temp', filename)

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Hash the password with SHA-256
        hashed_password = hashlib.sha256(password.encode()).hexdigest()

        # Connect to the database
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute("SELECT * FROM admin WHERE email = %s AND password = %s", (email, hashed_password))
        account = cursor.fetchone()

        if account:
            session['logged_in'] = True
            session['email'] = email
            session['admin_id'] = account['id']  # Save admin_id in session
            return redirect(url_for('admin'))
        else:
            flash('Incorrect email or password. Please try again.')
            return render_template('login.html')

    return render_template('login.html')

@app.route('/admin')
def admin():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('admin.html')

@app.route('/pending_cases')
def pending_cases():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    # Query the database for all case IDs from the images table
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT DISTINCT case_id FROM images WHERE status = 'open'")
    cases = cursor.fetchall()

    # Convert the list of dictionaries to a dictionary where case_id is the key
    case_dict = {case['case_id']: f"Case {case['case_id']}" for case in cases}

    return render_template('pending_cases.html', cases=case_dict)

@app.route('/submit_solution/<case_id>', methods=['GET', 'POST'])
def submit_solution(case_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Retrieve the form data
        crop_name = request.form['crop']
        category = request.form['category']
        issue = request.form['issue']
        admin_id = session.get('admin_id')
        solution = request.form.get('solution', '')  # Get the solution from hidden input

        # Database connection
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        
        # Fetch the uniqueId and email from the images table for the provided case_id
        cursor.execute(""" 
            SELECT uniqueId, email FROM images WHERE case_id = %s LIMIT 1
        """, [case_id])
        case_info = cursor.fetchone()

        if case_info:
            unique_id = case_info['uniqueId']  # Use the uniqueId from the images table
            email = case_info['email']

            # Generate path in the format: "cropname/category/issue"
            case_path = f"{crop_name}/{category}/{issue}"

            # Insert or update the case in the cases table
            try:
                cursor.execute(""" 
                    INSERT INTO cases (uniqueId, email, cropName, category, issue, status, solution, admin_id, path)
                    VALUES (%s, %s, %s, %s, %s, 'closed', %s, %s, %s)
                    ON DUPLICATE KEY UPDATE 
                        cropName = VALUES(cropName),
                        category = VALUES(category),
                        issue = VALUES(issue),
                        status = VALUES(status),
                        solution = VALUES(solution),
                        admin_id = VALUES(admin_id),
                        path = VALUES(path)
                """, (unique_id, email, crop_name, category, issue, solution, admin_id, case_path))
                cursor.execute("UPDATE images SET status = 'closed' WHERE case_id = %s", [case_id])
                cursor.execute("UPDATE images SET admin_id = %s WHERE case_id = %s", [admin_id, case_id])
                cursor.execute("UPDATE images SET solution = %s WHERE case_id = %s", [solution, case_id])
                cursor.execute("UPDATE images SET cropName = %s WHERE case_id = %s", [crop_name, case_id])
                cursor.execute("UPDATE images SET issue = %s WHERE case_id = %s", [issue, case_id])
                mysql.connection.commit()
            except MySQLdb.IntegrityError as e:
                flash(f"IntegrityError: {str(e)}")
                return redirect(url_for('submit_solution', case_id=case_id))

        flash('Solution submitted successfully.')
        return redirect(url_for('admin'))

    # Fetch the filenames from the database for display
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT fileName FROM images WHERE case_id = %s", [case_id])
    files = cursor.fetchall()

    # Generate WebDAV URLs for each file
    file_urls = []
    for file in files:
        file_name = file['fileName']
        webdav_file_url = f"{WEBDAV_BASE_URL}{file_name}"  # Construct the WebDAV URL
        file_urls.append(webdav_file_url)

    # Pass these URLs to the template for display
    return render_template('submit_solution.html', case_id=case_id, files=file_urls)



def upload_files_to_ftp(ftp_server, ftp_username, ftp_password, local_dir, remote_dir):
    try:
        # Connect to the FTP server
        ftp = ftplib.FTP(ftp_server)
        ftp.login(ftp_username, ftp_password)

        # Create the folder structure on FTP server
        try:
            ftp.cwd(remote_dir)
        except ftplib.error_perm:
            dirs = remote_dir.split('/')[1:]  # Skip the leading empty string
            current_path = ""
            for directory in dirs:
                current_path += f"/{directory}"
                try:
                    ftp.cwd(current_path)
                except ftplib.error_perm:
                    # Directory does not exist, create it
                    ftp.mkd(current_path)
                    ftp.cwd(current_path)

        # Upload each file from the local directory to the FTP server
        for filename in os.listdir(local_dir):
            local_file_path = os.path.join(local_dir, filename)
            with open(local_file_path, 'rb') as local_file:
                ftp.storbinary(f'STOR {filename}', local_file)
                print(f"Uploaded {filename} to {remote_dir}")

        ftp.quit()
    except ftplib.all_errors as e:
        print(f"FTP error: {e}")
    except Exception as e:
        print(f"Error: {e}")

@app.route('/solved_cases')
def solved_cases():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    # Query the database for solved cases
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT uniqueId FROM cases WHERE status = 'closed'")
    solved_cases_data = cursor.fetchall()

    # Convert the list of dictionaries to a dictionary where case_id is the key and a descriptive name is the value
    case_dict = {case['uniqueId']: f"Case {case['uniqueId']}" for case in solved_cases_data}

    return render_template('solved_cases.html', cases=case_dict)

@app.route('/solved_case/<case_id>')
def solved_case(case_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    # Fetch the case details using the case_id
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT * FROM cases WHERE uniqueId = %s", [case_id])
    case_details = cursor.fetchone()

    if not case_details:
        flash('Case not found.')
        return redirect(url_for('solved_cases'))

    return render_template('solved_case.html', case=case_details)


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('admin_id', None)
    return redirect(url_for('login'))

@app.route('/fetch-ftp-images/<case_id>', methods=['GET'])
def fetch_ftp_images(case_id):
    # Fetch images logic here (for now, simulating with sample data)
    images = [
        {'url': f'/static/images/{case_id}_image1.jpg', 'name': 'Image 1'},
        {'url': f'/static/images/{case_id}_image2.jpg', 'name': 'Image 2'},
    ]
    return jsonify({'images': images})

# Route for editing a specific case's images
@app.route('/edit-case/<case_id>', methods=['GET', 'POST'])
def edit_case(case_id):
    if request.method == 'POST':
        # Get the selected images
        selected_images = request.form.getlist('selected_images')
        # Generate new case ID
        new_case_id = f"CASE-{random.randint(10000, 99999)}"
        # Store the new case ID and selected images (custom logic here)
        # For now, redirect back to a confirmation page
        return redirect(url_for('confirm_edit', new_case_id=new_case_id))

    # Render a page to display images of a particular case ID
    return render_template('edit_case.html', case_id=case_id)

# Route for confirming the edit
@app.route('/confirm-edit/<new_case_id>')
def confirm_edit(new_case_id):
    return f"New Case ID generated: {new_case_id}. Your images have been updated."


@app.route('/select_images/<case_id>', methods=['GET', 'POST'])
def select_images(case_id):
    if request.method == 'POST':
        selected_images = request.form.get('selected_images').split(',')

        # Debugging statements to check if images are selected
        print(f"Selected images: {selected_images}")
        print(f"Action: {request.form.get('action')}")

        if 'action' in request.form:
            if request.form['action'] == 'submit':
                # Generate new case ID and save selected images logic
                new_case_id = generate_new_case_id()
                save_new_case_id_to_db(new_case_id, selected_images)
                flash(f"New case ID {new_case_id} generated and saved!", 'success')
                return redirect(url_for('admin'))

            elif request.form['action'] == 'delete':
                print("Delete action triggered")
                # Delete selected images from the database
                cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
                for image_url in selected_images:
                    file_name = image_url.split('/')[-1]  # Extract the filename
                    cursor.execute("DELETE FROM images WHERE case_id = %s AND fileName = %s", (case_id, file_name))
                mysql.connection.commit()

                flash(f"Selected images deleted successfully!", 'success')
                return redirect(url_for('pending_cases', case_id=case_id))

    # Fetch image filenames for the given case_id from the database
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT fileName FROM images WHERE case_id = %s", [case_id])
    images_data = cursor.fetchall()

    # Generate WebDAV URLs for the images
    images = [f"{WEBDAV_BASE_URL}{image['fileName']}" for image in images_data]

    return render_template('select_images.html', images=images, case_id=case_id)


def get_pdf_content(doc_id):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Fetch the document by its ID
    query = "SELECT * FROM documents WHERE id = %s"
    cursor.execute(query, (doc_id,))
    result = cursor.fetchone()
    cursor.close()

    # Return title and content using correct column names
    if result:
        return result['title'], result['content']  # Ensure these match your column names
    else:
        return None, None  # Handle the case where no result is found

@app.route('/upload_pdf', methods=['GET', 'POST'])
def upload_pdf_page():
    if request.method == 'POST':
        # Handle the PDF upload logic here
        return upload_pdf()
    return render_template('upload.html')  # Render the upload page when it's a GET request


# This handles the actual PDF file upload
@app.route('/upload', methods=['POST'])
def upload_pdf():
    if not session.get('logged_in'):
        flash('You must be logged in to upload files.', 'danger')
        return redirect(url_for('login'))

    file = request.files.get('file')
    title = request.form.get('title')

    # Validate input
    if not file or file.filename == '':
        flash('No file selected.', 'danger')
        return redirect(url_for('upload_pdf_page'))
    if not file.filename.endswith('.pdf'):
        flash('Invalid file type. Only PDF files are allowed.', 'danger')
        return redirect(url_for('upload_pdf_page'))
    if not title or title.strip() == '':
        flash('Title is required.', 'danger')
        return redirect(url_for('upload_pdf_page'))

    try:
        # Save the file locally
        local_path = os.path.join('temp', file.filename)
        file.save(local_path)

        # Upload to FTP server
        remote_path = f"{FTP_DIR}/{file.filename}"
        ftp = connect_ftp()
        with open(local_path, 'rb') as f:
            ftp.storbinary(f"STOR {file.filename}", f)
        ftp.quit()

        # Update the database (solutions table)
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute("""
            INSERT INTO solutions (title, path) VALUES (%s, %s)
        """, (title, remote_path))
        mysql.connection.commit()
        cursor.close()

        os.remove(local_path)  # Clean up the local file
        flash('PDF uploaded successfully!', 'success')
    except Exception as e:
        flash(f"Error uploading PDF: {e}", 'danger')

    return redirect(url_for('admin'))





if __name__ == '__main__':
    app.run(debug=True)
