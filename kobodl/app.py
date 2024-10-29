import json.decoder
import os

from flask import Flask, abort, redirect, render_template, request, send_from_directory
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


@app.route('/user/<userid>/remove', methods=['POST'])
def deleteUser(userid):
    user = Globals.Settings.UserList.getUser(userid)
    if not user:
        abort(404)
    Globals.Settings.UserList.users.remove(user)
    Globals.Settings.Save()
    return redirect('/user')


@app.route('/user/<userid>/book', methods=['GET'])
def getUserBooks(userid, error=None, success=None):
    user = Globals.Settings.UserList.getUser(userid)
    if not user:
        abort(404)
    books = actions.ListBooks([user], False, None)
    return render_template(
        'books.j2',
        books=books,
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


@app.route('/book', methods=['GET'])
def books():
    userlist = Globals.Settings.UserList.users
    books = actions.ListBooks(userlist, False, None)
    return render_template('books.j2', books=books)
