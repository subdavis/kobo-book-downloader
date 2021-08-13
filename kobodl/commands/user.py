import click
import pyperclip
from tabulate import tabulate

from kobodl import actions, cli
from kobodl.globals import Globals
from kobodl.kobo import Kobo
from kobodl.settings import User


@click.group(name='user', short_help='show and create users')
def user():
    pass


@user.command(name='list', help='list all users')
@click.pass_obj
def list(ctx):
    userlist = Globals.Settings.UserList.users
    headers = ['Email', 'UserKey', 'DeviceId']
    data = sorted(
        [
            (
                user.Email,
                user.UserKey,
                user.DeviceId,
            )
            for user in userlist
        ]
    )
    click.echo(tabulate(data, headers, tablefmt=ctx['fmt']))


@user.command(name='rm', help='remove user by Email, UserKey, or DeviceID')
@click.argument('identifier', type=click.STRING)
@click.pass_obj
def list(ctx, identifier):
    removed = Globals.Settings.UserList.removeUser(identifier)
    if removed:
        Globals.Settings.Save()
        click.echo(f'Removed {removed.Email}')
    else:
        click.echo(f'No user with email, key, or device id that matches "{identifier}"')


@user.command(name='add', help='add new user')
@click.option('--email', prompt=True, hide_input=False, type=click.STRING, help="kobo.com email.")
@click.password_option(help="kobo.com password (not stored)")
@click.pass_obj
def add(ctx, email, password):
    user = User(Email=email)
    click.echo(
        """
    1. Open https://authorize.kobo.com/signin in a private/incognito window in your browser.
    2. wait till the page loads (do not login!)
    3. open the developer tools (use F12 in Firefox/Chrome, or right-click and choose "inspect")
    4. select the console tab,
    5. copy-paste the following code to the console there and then press Enter.

    var newCaptchaDiv = document.createElement("div");
    newCaptchaDiv.id = "new-hcaptcha-container";
    var siteKey = document.getElementById('hcaptcha-container').getAttribute('data-sitekey');
    document.body.replaceChildren(newCaptchaDiv);
    grecaptcha.render(newCaptchaDiv.id, {
        sitekey: siteKey,
        callback: function(r) {console.log("Captcha response:");console.log(r);}
    });
    console.log('Click the checkbox to get the code');

    A captcha should show up below the Sign-in form. Once you solve the captcha its response will be written
    below the pasted code in the browser's console. Copy the response (the line below "Captcha response:")
    and paste it here.  It will be very long!
    """
    )
    input('Press enter after copying the captcha code...')
    captcha = pyperclip.paste().strip()
    click.echo(f'Read captcha code from clipboard: {captcha}')
    actions.Login(user, password, captcha)
    Globals.Settings.UserList.users.append(user)
    Globals.Settings.Save()
    click.echo('Login Success. Try to list your books with `kobodl book list`')


cli.add_command(user)
