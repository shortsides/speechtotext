import os
import time
import speech_recognition as sr
import azure.cognitiveservices.speech as speechsdk

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, send_from_directory, session, url_for
from flask_session import Session
from flask_login import current_user
from tempfile import mkdtemp
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
from helpers import allowed_file, login_required


app = Flask(__name__)

# set max file upload size to 16mb
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024

# configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# configure Microsoft Azure Speech
speech_key, service_region = "API KEY", "REGION"
speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///speechtotext.db")

# set base file path
base_path = 'static/files/'
files_path = 'files/'

@app.route('/')
def index():
    # display page
    if not session.get("user_id"):
        return render_template('index.html')

    # get current user's audio files
    print('You are now Logged In')
    files = db.execute("SELECT filename, transcript FROM files JOIN users ON users.id = files.user_id WHERE user_id = :user_id", 
                        user_id=session["user_id"])
    return render_template('index.html', files=files, files_path=files_path)

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        # check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']
        # check if user has not selected a filename
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        # save file to static/files and store metadata in database
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(base_path, filename))
            db.execute("INSERT INTO files (filename, user_id) VALUES (:filename, :user_id)", 
                        filename=filename, user_id=session["user_id"])
            flash("File Uploaded")
            return redirect('files')
    else:
        return render_template('upload.html')

@app.route('/files', methods=["GET", "POST"])
@login_required
def files():
    if request.method == 'POST':

        # Ensure file is selected
        file = request.form.get("file")
        if not file:
            return "choose a file to transcribe", 403
        
        # get the full audio file path
        path = base_path + file

        # recognize speech using Microsoft Azure Speech
        audio_input = speechsdk.audio.AudioConfig(filename=path)
        speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_input)

        # perform continuous speech recognition with input from an audio file
        done = False

        def stop_cb(evt):
            """callback that signals to stop continuous recognition upon receiving an event `evt`"""
            print('CLOSING on {}'.format(evt))
            nonlocal done
            done = True

        all_results = []
        def handle_final_result(evt):
            all_results.append(evt.result.text)

        # connect callbacks to the events fired by the speech recognizer
        speech_recognizer.recognizing.connect(lambda evt: print('RECOGNIZING: {}'.format(evt)))
        speech_recognizer.recognized.connect(handle_final_result)
        speech_recognizer.recognized.connect(lambda evt: print('RECOGNIZED: {}'.format(evt)))
        speech_recognizer.session_started.connect(lambda evt: print('SESSION STARTED: {}'.format(evt)))
        speech_recognizer.session_stopped.connect(lambda evt: print('SESSION STOPPED {}'.format(evt)))
        speech_recognizer.canceled.connect(lambda evt: print('CANCELED {}'.format(evt)))
        # stop continuous recognition on either session stopped or canceled events
        speech_recognizer.session_stopped.connect(stop_cb)
        speech_recognizer.canceled.connect(stop_cb)

        # start continuous speech recognition
        speech_recognizer.start_continuous_recognition()
        while not done:
            time.sleep(.5)
        
        speech_recognizer.stop_continuous_recognition()
       
        # function to convert list to string
        def listToString(s):
            str1 = ""
            return (str1.join(s))

        # store transcription result
        text = listToString(all_results)
        db.execute("UPDATE files SET transcript = :text WHERE filename = :filename", 
                    text=text, filename=file)

        # redirect to files
        return render_template('files.html', text=text)

    else:
        # get list of uploaded files
        files = db.execute("SELECT filename FROM files JOIN users ON users.id = files.user_id WHERE user_id = :user_id", 
                            user_id=session["user_id"])

        return render_template('files.html', files=files, files_path=files_path)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return "must provide username", 403

        # Ensure password was submitted
        elif not request.form.get("password"):
            return "must provide password", 403

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return "invalid username and/or password", 403

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via GET
    if request.method == "GET":
        return render_template("register.html")

    # User reached route via POST
    else:

        # Ensure username was submitted
        if not request.form.get("username"):
            return "must provide username", 403

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username does not already exist
        if len(rows) != 0:
            return "Username already exists", 403

        # Ensure password was submitted
        elif not request.form.get("password"):
            return "must provide password", 403

        # Ensure password confirmation was submitted
        elif not request.form.get("confirmation"):
            return "must provide password confirmation", 403

        # Ensure the passwords match
        elif request.form.get("password") != request.form.get("confirmation"):
            return "passwords do not match", 403

        # Store username and hash the password
        username = request.form.get("username")
        hash = generate_password_hash(request.form.get("password"))

        # Insert new user into users in the database
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", 
                    username=username, hash=hash)

        # Redirect user to home page
        return redirect("/")

@app.route("/change password", methods=["GET", "POST"])
@login_required
def change_password():
    """Change user password"""

    # User reached route via POST
    if request.method == "POST":

        # Get user login details
        rows = db.execute("SELECT * FROM users WHERE id = :user_id", user_id=session["user_id"])

        # Ensure current password was submitted
        if not request.form.get("password"):
            return "must provide current password", 403

        # Ensure current password is correct
        if not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return "password incorrect", 403

        # Ensure new password was submitted
        elif not request.form.get("new_password"):
            return "must provide new password", 403

        # Ensure password confirmation was submitted
        elif not request.form.get("confirmation"):
            return "must provide password confirmation", 403

        # Ensure the passwords match
        elif request.form.get("new_password") != request.form.get("confirmation"):
            return "passwords do not match", 403

        # Hash new password
        hash = generate_password_hash(request.form.get("new_password"))

        # Update user password in the database
        db.execute("UPDATE users SET hash = :hash WHERE id = :user_id", user_id=session["user_id"], hash=hash)

        # Flash password change success message
        flash("Password Changed Successfully")

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET
    else:
        return render_template("change_password.html")

@app.errorhandler(413)
def too_large(e):
    return "File is too large", 413

# run the application
if __name__ == '__main__':
    app.run(debug = True)
