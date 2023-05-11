"""Imports"""
import logging
import os.path
import re
import zipfile
from flask import Flask, render_template, request, redirect, url_for, session
from flask_paginate import Pagination
from werkzeug.utils import secure_filename
from flask_session import Session
# pylint: disable-next=import-error
from upd import get_latest_version, update_needed

app = Flask(__name__)
app.secret_key = "secret_key"
# File settings
app.config['ALLOWED_EXTENSIONS'] = ['.zip']
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
# Session settings
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)
# Logging settings
logging.basicConfig(format='%(asctime)s:%(levelname)s:%(filename)s:%(funcName)s:%(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S',
                    level=logging.INFO)
# Upload folder
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
# Current version
CURRENT_VERSION = 'v1.11.4'
# Update needed
UPDATE_NEEDED = bool(update_needed(CURRENT_VERSION, get_latest_version()))


def create_upload_dir():
    """
    Create the upload directory if it does not exist.
    """
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def parse_usernames(html_source):
    """
    Parse usernames and links.
    """
    if not isinstance(html_source, str):
        raise TypeError('html_source must be a string')

    usernames_regexp = r'(?<=href="https://www\.instagram\.com/)[^"]+'
    try:
        return re.findall(usernames_regexp, html_source)
    except Exception as exc:
        raise ValueError(f'Error while parsing html source: {exc}') from exc


def find_unfollowers(file_path):
    """
    Find the unfollowers.
    """
    try:
        with zipfile.ZipFile(file_path) as instagram_file:

            files = instagram_file.namelist()
            followers_path = list(filter(
                lambda file: 'followers' in os.path.basename(file) and file.endswith('.html'),
                files))
            following_path = list(filter(
                lambda file: 'following' in os.path.basename(file) and file.endswith('.html'),
                files))
            followers_html = instagram_file.read(followers_path[0]).decode('utf-8')
            following_html = instagram_file.read(following_path[0]).decode('utf-8')
            if not (followers_path or following_path):
                return None
            # else
            following_list = parse_usernames(following_html)
            followers_list = parse_usernames(followers_html)
            unfollowers_list = list(set(following_list) - set(followers_list))
            logging.info('%s unfollowers found.', len(unfollowers_list))
            return unfollowers_list
    except zipfile.BadZipFile as exc:
        logging.error('Error while reading Instagram data file: %s', exc)
        return None


def get_unfollowers_paginated(unfollowers_list, offset, per_page):
    """
    Return the unfollowers, paginated.
    """
    return unfollowers_list[offset: offset + per_page]


@app.route('/', methods=['GET'])
def index():
    """
    Display the index page.
    """
    session['update_needed'] = UPDATE_NEEDED
    logging.info('Displaying the index page.')
    return render_template('index.html')


@app.route('/', methods=['POST'])
def upload_instagram_file():
    """
    Upload the instagram file.
    """
    logging.info('Starting file upload.')

    if 'file' not in request.files:
        logging.info('No file part.')
        return redirect(request.url)

    file = request.files['file']

    filename = file.filename
    if filename == '':
        logging.info('No file selected.')
        return redirect(request.url)
    # else:
    logging.info('Selected file is: %s', filename)

    file_ext = os.path.splitext(filename)[1]
    if file_ext in app.config['ALLOWED_EXTENSIONS']:
        secure_fname = secure_filename(filename)
        logging.info('Secure filename is: %s', secure_fname)
        file.save(os.path.join(UPLOAD_FOLDER, secure_fname))
        logging.info('File uploaded successfully')
        unfollowers_list = (find_unfollowers(os.path.join(UPLOAD_FOLDER, secure_fname)))
        if unfollowers_list:
            session["unfollowers"] = unfollowers_list
            return redirect(url_for('unfollowers'))
        # else:
        logging.error('Invalid structure.')
        return redirect(url_for('index', invalid_file_structure=1))
    # else:
    logging.info('Invalid file extension')
    return redirect(request.url)


@app.route('/unfollowers', methods=['GET'])
def unfollowers():
    """
    Display the unfollowers.
    """
    logging.info('Displaying the unfollowers.')
    unfollowers_list = session["unfollowers"]
    page = int(request.args.get('page', 1))
    per_page = 10
    offset = (page - 1) * per_page
    total = len(unfollowers_list)
    pagination_unfollowers = get_unfollowers_paginated(unfollowers_list,
                                                       offset=offset,
                                                       per_page=per_page)
    pagination = Pagination(page=page,
                            per_page=per_page,
                            total=total,
                            css_framework='bootstrap4')
    return render_template('unfollowers.html',
                           unfollowers=pagination_unfollowers,
                           page=page,
                           per_page=per_page,
                           pagination=pagination, )


if __name__ == '__main__':
    create_upload_dir()
    from waitress import serve

    server_port = os.environ.get('PORT', '5000')
    serve(app, host="0.0.0.0", port=server_port)
