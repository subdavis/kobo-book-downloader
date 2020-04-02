import os
from typing import List

import click
import colorama

from kobodl.globals import Globals
from kobodl.kobo import (
    Book,
    Kobo,
    KoboException,
    NotAuthenticatedException,
)
from kobodl.settings import User


def __GetBookAuthor(book: dict) -> str:
    contributors = book.get("ContributorRoles")

    authors = []
    for contributor in contributors:
        role = contributor.get("Role")
        if role == "Author":
            authors.append(contributor["Name"])

    # Unfortunately the role field is not filled out in the data returned by the "library_sync" endpoint, so we only
    # use the first author and hope for the best. Otherwise we would get non-main authors too. For example Christopher
    # Buckley beside Joseph Heller for the -- terrible -- novel Catch-22.
    if len(authors) == 0 and len(contributors) > 0:
        authors.append(contributors[0]["Name"])

    return " & ".join(authors)


def __SanitizeFileName(fileName: str) -> str:
    result = ""
    for c in fileName:
        if c.isalnum() or " ,;.!(){}[]#$'-+@_".find(c) >= 0:
            result += c

    result = result.strip(" .")
    result = result[
        :100
    ]  # Limit the length -- mostly because of Windows. It would be better to do it on the full path using MAX_PATH.
    return result


def __MakeFileNameForBook(book: dict) -> str:
    fileName = ""

    author = __GetBookAuthor(book)
    if len(author) > 0:
        fileName = author + " - "

    fileName += book["Title"]
    fileName = __SanitizeFileName(fileName)
    fileName += ".epub"

    return fileName


def __IsBookArchived(newEntitlement: dict) -> bool:
    bookEntitlement = newEntitlement.get("BookEntitlement")
    if bookEntitlement is None:
        return False

    isRemoved = bookEntitlement.get("IsRemoved")
    if isRemoved is None:
        return False

    return isRemoved


def GetAllBooks(user: User, outputPath: str) -> None:
    kobo = Kobo(user)
    kobo.LoadInitializationSettings()
    bookList = kobo.GetMyBookList()
    for entitlement in bookList:
        newEntitlement = entitlement.get("NewEntitlement")
        if newEntitlement is None:
            continue
        try:
            bookMetadata = newEntitlement["BookMetadata"]
        except Exception:
            # skip audiobooks
            continue
        fileName = __MakeFileNameForBook(bookMetadata)
        outputFilePath = os.path.join(outputPath, fileName)

        # Skip archived books.
        if __IsBookArchived(newEntitlement):
            title = bookMetadata["Title"]
            author = __GetBookAuthor(bookMetadata)
            if len(author) > 0:
                title += " by " + author

            click.echo(f"Skipping archived book {title}")
            continue
        try:
            output = kobo.Download(bookMetadata["RevisionId"], outputFilePath)
            click.echo(f"Downloaded to {output}", err=True)
        except Exception as e:
            click.echo("could not download".format(bookMetadata["Title"]))
            click.echo(e)


def GetBook(user: User, revisionId: str, outputPath: str) -> None:
    kobo = Kobo(user)
    kobo.LoadInitializationSettings()
    book = kobo.GetBookInfo(revisionId)
    fileName = __MakeFileNameForBook(book)
    outputFilePath = os.path.join(outputPath, fileName)
    return kobo.Download(revisionId, outputFilePath)


def __IsBookRead(newEntitlement: dict) -> bool:
    readingState = newEntitlement.get("ReadingState")
    if readingState is None:
        return False

    statusInfo = readingState.get("StatusInfo")
    if statusInfo is None:
        return False

    status = statusInfo.get("Status")
    return status == "Finished"


def __GetBookList(kobo: Kobo, listAll: bool) -> list:
    bookList = kobo.GetMyBookList()
    rows = []

    for entitlement in bookList:
        newEntitlement = entitlement.get("NewEntitlement")
        if newEntitlement is None:
            continue

        bookEntitlement = newEntitlement.get("BookEntitlement")
        if bookEntitlement is not None:
            # Skip saved previews.
            if bookEntitlement.get("Accessibility") == "Preview":
                continue

            # Skip refunded books.
            if bookEntitlement.get("IsLocked"):
                continue

        if (not listAll) and __IsBookRead(newEntitlement):
            continue
        try:
            bookMetadata = newEntitlement["BookMetadata"]
        except Exception as e:
            # skip audiobook
            continue
        book = [
            bookMetadata["RevisionId"],
            bookMetadata["Title"],
            __GetBookAuthor(bookMetadata),
            __IsBookArchived(newEntitlement),
        ]
        rows.append(book)

    rows = sorted(rows, key=lambda columns: columns[1].lower())
    return rows


def ListBooks(users: List[User], listAll: bool) -> List[Book]:
    for user in users:
        kobo = Kobo(user)
        kobo.LoadInitializationSettings()
        rows = __GetBookList(kobo, listAll)
        for columns in rows:
            yield Book(
                RevisionId=columns[0],
                Title=columns[1],
                Author=columns[2],
                Archived=columns[3],
                Owner=user,
            )


def Login(user: User, password: str, captcha: str) -> None:
    kobo = Kobo(user)
    kobo.AuthenticateDevice()
    kobo.LoadInitializationSettings()
    kobo.Login(user.Email, password, captcha)
