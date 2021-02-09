import json.decoder
import os

from flask import Flask, abort, redirect, render_template, request, send_from_directory, url_for
from requests import Request, Session
from requests.auth import HTTPBasicAuth
from requests.exceptions import HTTPError

from kobodl import actions
from kobodl.globals import Globals
from kobodl.settings import User

app = Flask(__name__)


@app.route('/')
def index():
    return redirect('/user')


@app.route('/user', methods=['GET', 'POST'])
def users():
    error = None
    if request.method == 'POST':
        print(request.form)
        email = request.form.get('email')
        password = request.form.get('password')
        captcha = request.form.get('captcha')
        print(email, password, captcha)
        if email and password and captcha:
            user = User(Email=email)
            try:
                actions.Login(user, password, captcha)
                Globals.Settings.UserList.users.append(user)
                Globals.Settings.Save()
            except Exception as err:
                error = str(err)
        else:
            error = 'email, password, or captcha missing'
    users = Globals.Settings.UserList.users
    return render_template('users.j2', users=users, error=error)


@app.route('/user/<userid>/book', methods=['GET'])
def getUserBooks(userid, error=None, success=None):
    user = Globals.Settings.UserList.getUser(userid)
    if not user:
        abort(404)
    books = actions.ListBooks([user], False, None)
    calibre = Globals.Settings.UserList.calibre_web
    return render_template(
        'books.j2',
        books=books,
        calibre=calibre,
        error=error,
        success=success,
    )


@app.route('/user/<userid>/book/<productid>', methods=['GET'])
def downloadBook(userid, productid):
    user = Globals.Settings.UserList.getUser(userid)
    if not user:
        abort(404)
    outputDir = app.config.get('output_dir')
    os.makedirs(outputDir, exist_ok=True)
    # GetBookOrBooks always returns an absolute path
    outputFileName = actions.GetBookOrBooks(user, outputDir, productId=productid)
    absOutputDir, tail = os.path.split(outputFileName)
    # send_from_directory must be given an absolute path to avoid confusion
    # (relative paths are relative to root_path, not working dir)
    return send_from_directory(absOutputDir, tail, as_attachment=True, attachment_filename=tail)


@app.route('/user/<userid>/book/<productid>/send_to_calibre', methods=['POST'])
def sendToCalibre(userid, productid):
    user = Globals.Settings.UserList.getUser(userid)
    if not user:
        abort(404)
    outputDir = app.config.get('output_dir')
    os.makedirs(outputDir, exist_ok=True)
    # GetBookOrBooks always returns an absolute path
    outputFileName = actions.GetBookOrBooks(user, outputDir, productId=productid)
    req = Request(
        'POST',
        url=Globals.Settings.UserList.calibre_web.url,
        files={'btn-upload': open(outputFileName, 'rb')},
    )
    if Globals.Settings.UserList.calibre_web.username:
        req.auth = HTTPBasicAuth(
            Globals.Settings.UserList.calibre_web.username,
            Globals.Settings.UserList.calibre_web.password,
        )
    success = None
    try:
        resp = Session().send(req.prepare())
        resp.raise_for_status()
        success = f"New book uploaded to {resp.json()['location']}"
    except HTTPError as err:
        return getUserBooks(userid=userid, error=err)
    except json.decoder.JSONDecodeError:
        return getUserBooks(
            userid=userid, error="Could not decode response.  Check your CalibreWeb Credentials."
        )
    return getUserBooks(userid=userid, success=success)


@app.route('/book', methods=['GET'])
def books():
    userlist = Globals.Settings.UserList.users
    books = actions.ListBooks(userlist, False, None)
    calibre = Globals.Settings.UserList.calibre_web
    return render_template('books.j2', books=books, calibre=calibre)
