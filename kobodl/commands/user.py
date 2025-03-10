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
@click.pass_obj
def add(ctx):
    user = User()
    actions.Login(user)
    Globals.Settings.UserList.users.append(user)
    Globals.Settings.Save()
    click.echo('Login Success. Try to list your books with `kobodl book list`')


cli.add_command(user)
