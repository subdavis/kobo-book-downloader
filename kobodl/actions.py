import json
import os
import platform
import subprocess
from typing import List, TextIO, Tuple, Union

import click

from kobodl.globals import Globals
from kobodl.kobo import Book, BookType, Kobo, KoboException, NotAuthenticatedException
from kobodl.settings import User

SUPPORTED_BOOK_TYPES = [
    BookType.EBOOK,
    BookType.AUDIOBOOK,
]


def __GetBookAuthor(book: dict) -> str:
    contributors = book.get('ContributorRoles')

    authors = []
    for contributor in contributors:
        role = contributor.get('Role')
        if role == 'Author':
            authors.append(contributor['Name'])

    # Unfortunately the role field is not filled out in the data returned by the 'library_sync' endpoint, so we only
    # use the first author and hope for the best. Otherwise we would get non-main authors too. For example Christopher
    # Buckley beside Joseph Heller for the -- terrible -- novel Catch-22.
    if len(authors) == 0 and len(contributors) > 0:
        authors.append(contributors[0]['Name'])

    return ' & '.join(authors)


def __SanitizeString(string: str) -> str:
    result = ''
    for c in string:
        if c.isalnum() or ' ,;.!(){}[]#$\'-+@_'.find(c) >= 0:
            result += c

    result = result.strip(' .')
    if platform.system() == 'Windows':
        # Limit the length -- mostly because of Windows. It would be better to do it on the full path using MAX_PATH.
        result = result[:100]
    return result


def __MakeFileNameForBook(bookMetadata: dict, formatStr: str) -> str:
    '''filename without extension'''
    fileName = ''
    author = __SanitizeString(__GetBookAuthor(bookMetadata))
    title = __SanitizeString(bookMetadata['Title'])
    bookSeries = __SanitizeString(bookMetadata.get('Series', {}).get('Name', ''))
    bookSeriesNumber = __SanitizeString(bookMetadata.get('Series', {}).get('Number', ''))

    return formatStr.format_map(
        {
            **bookMetadata,
            'Author': author,
            'Title': title,
            'Series': bookSeries,
            'SeriesNumber': bookSeriesNumber,
            # Append a portion of revisionId to prevent name collisions.
            'ShortRevisionId': bookMetadata['RevisionId'][:8],
        }
    )


def __GetBookMetadata(entitlement: dict) -> Tuple[dict, BookType]:
    keys = entitlement.keys()
    if 'BookMetadata' in keys:
        return entitlement['BookMetadata'], BookType.EBOOK
    if 'AudiobookMetadata' in keys:
        return entitlement['AudiobookMetadata'], BookType.AUDIOBOOK
    if 'BookSubscriptionEntitlement' in keys:
        return entitlement['BookSubscriptionEntitlement'], BookType.SUBSCRIPTION
    print(f'WARNING: unsupported object detected with contents {entitlement}')
    print('Please open an issue at https://github.com/subdavis/kobo-book-downloader/issues')
    return None, None


def __IsBookArchived(newEntitlement: dict) -> bool:
    keys = newEntitlement.keys()
    bookEntitlement: dict = {}
    if 'BookEntitlement' in keys:
        bookEntitlement = newEntitlement['BookEntitlement']
    if 'AudiobookEntitlement' in keys:
        bookEntitlement = newEntitlement['AudiobookEntitlement']
    return bookEntitlement.get('IsRemoved', False)


def __IsBookRead(newEntitlement: dict) -> bool:
    readingState = newEntitlement.get('ReadingState')
    if readingState is None:
        return False

    statusInfo = readingState.get('StatusInfo')
    if statusInfo is None:
        return False

    status = statusInfo.get('Status')
    return status == 'Finished'


def __GetBookList(kobo: Kobo, listAll: bool, exportFile: Union[TextIO, None]) -> list:
    bookList = kobo.GetMyBookList()
    rows = []

    if exportFile:
        exportFile.write(json.dumps(bookList, indent=2))

    for entitlement in bookList:
        newEntitlement = entitlement.get('NewEntitlement')
        if newEntitlement is None:
            continue

        bookEntitlement = newEntitlement.get('BookEntitlement')
        if bookEntitlement is not None:
            # Skip saved previews.
            if bookEntitlement.get('Accessibility') == 'Preview':
                continue

            # Skip refunded books.
            if bookEntitlement.get('IsLocked'):
                continue

        if (not listAll) and __IsBookRead(newEntitlement):
            continue

        bookMetadata, book_type = __GetBookMetadata(newEntitlement)

        if book_type is None:
            click.echo('Skipping book of unknown type')
            continue

        elif book_type in SUPPORTED_BOOK_TYPES:
            book = [
                bookMetadata['RevisionId'],
                bookMetadata['Title'],
                __GetBookAuthor(bookMetadata),
                __IsBookArchived(newEntitlement),
                book_type == BookType.AUDIOBOOK,
            ]
            rows.append(book)

    rows = sorted(rows, key=lambda columns: columns[1].lower())
    return rows


def __CreateM4BFile(outputPath: str, filename: str, bookMetadata: dict) -> None:
    # Check if ffmpeg is installed
    try:
        subprocess.run(["ffmpeg", "-version"], check=True)
    except subprocess.CalledProcessError:
        click.echo("ffmpeg is not installed. Please install ffmpeg and try again.")
        return

    # Concatenate all mp3 files into one file
    subprocess.run(
        [
            "ffmpeg",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            "files.txt",
            "-c",
            "copy",
            "-y",
            "build_01_concat.mp3",
        ],
        check=True,
        cwd=outputPath,
    )

    # Add cover
    subprocess.run(
        [
            "ffmpeg",
            "-i",
            "build_01_concat.mp3",
            "-i",
            "cover.jpg",
            "-c",
            "copy",
            "-map",
            "0",
            "-map",
            "1",
            "-y",
            "build_02_cover.mp3",
        ],
        check=True,
        cwd=outputPath,
    )

    # Convert mp3 to m4a
    subprocess.run(
        ["ffmpeg", "-y", "-i", "build_02_cover.mp3", "-c:v", "copy", "build_03_m4a.m4a"],
        check=True,
        cwd=outputPath,
    )

    # Add metadata to the m4a file and convert to m4b
    subprocess.run(
        [
            "ffmpeg",
            "-i",
            "build_03_m4a.m4a",
            "-i",
            "metadata.txt",
            "-map",
            "0",
            "-map_metadata",
            "1",
            "-c",
            "copy",
            "-y",
            f'{filename}.m4b',
        ],
        check=True,
        cwd=outputPath,
    )

    # Remove all build_* files using python
    for f in os.listdir(outputPath):
        if f.startswith("build_"):
            os.remove(os.path.join(outputPath, f))

    return os.path.join(outputPath, f'{bookMetadata["Title"]}.m4b')


def ListBooks(users: List[User], listAll: bool, exportFile: Union[TextIO, None]) -> List[Book]:
    '''list all books currently in the account'''
    for user in users:
        kobo = Kobo(user)
        kobo.LoadInitializationSettings()
        rows = __GetBookList(kobo, listAll, exportFile)
        for columns in rows:
            yield Book(
                RevisionId=columns[0],
                Title=columns[1],
                Author=columns[2],
                Archived=columns[3],
                Audiobook=columns[4],
                Owner=user,
            )


def Login(user: User, password: str, captcha: str) -> None:
    '''perform device initialization and get token'''
    kobo = Kobo(user)
    kobo.AuthenticateDevice()
    kobo.LoadInitializationSettings()
    kobo.Login(user.Email, password, captcha)


def GetBookOrBooks(
    user: User,
    outputPath: str,
    formatStr: str = r'{Author} - {Title} {ShortRevisionId}',
    productId: str = '',
    generateAudiobook: bool = False,
) -> Union[None, str]:
    """
    download 1 or all books to file
    returns output filepath if identifier is passed, otherwise returns None
    """
    outputPath = os.path.abspath(outputPath)
    kobo = Kobo(user)
    kobo.LoadInitializationSettings()

    # Must call GetBookList every time, even if you're only getting 1 book,
    # because it invokes a library sync endpoint.
    # This is the only known endpoint that returns
    # download URLs along with book metadata.
    bookList = kobo.GetMyBookList()

    for entitlement in bookList:
        newEntitlement = entitlement.get('NewEntitlement')
        if newEntitlement is None:
            continue

        bookMetadata, book_type = __GetBookMetadata(newEntitlement)
        if book_type is None:
            click.echo('Skipping book of unknown type')
            continue

        elif book_type == BookType.SUBSCRIPTION:
            click.echo('Skipping subscribtion entity')
            continue

        # Save metadata to JSON file
        with open(os.path.join(outputPath, f'{bookMetadata["Title"]}.json'), 'w') as f:
            f.write(json.dumps(bookMetadata, indent=2))

        fileName = __MakeFileNameForBook(bookMetadata, formatStr)
        if book_type == BookType.EBOOK:
            # Audiobooks go in sub-directories
            # but epub files go directly in outputPath
            fileName += '.epub'
        outputFilePath = os.path.join(outputPath, fileName)

        if (
            not productId
            and os.path.exists(outputFilePath)
            and (
                generateAudiobook
                and book_type == BookType.AUDIOBOOK
                and os.path.exists(os.path.join(outputFilePath, f'{fileName}.m4b'))
            )
        ):
            # when downloading ALL books, skip books we've downloaded before
            click.echo(f'Skipping already downloaded book {outputFilePath}')
            continue

        currentProductId = Kobo.GetProductId(bookMetadata)
        if productId and productId != currentProductId:
            # user only asked for a single title,
            # and this is not the book they want
            continue

        # Skip archived books.
        if __IsBookArchived(newEntitlement):
            click.echo(f'Skipping archived book {fileName}')
            continue

        try:
            click.echo(f'Downloading {currentProductId} to {outputFilePath}', err=True)
            kobo.Download(bookMetadata, book_type == BookType.AUDIOBOOK, outputFilePath)
        except KoboException as e:
            if productId:
                raise e
            else:
                click.echo(
                    (
                        f'Skipping failed download for {currentProductId}: {str(e)}'
                        '\n  -- Try downloading it as a single book to get the complete exception details'
                        ' and open an issue on the project GitHub page: https://github.com/subdavis/kobo-book-downloader/issues'
                    ),
                    err=True,
                )

        # Create final audiobook file
        if book_type == BookType.AUDIOBOOK and generateAudiobook:
            try:
                __CreateM4BFile(outputFilePath, fileName, bookMetadata)
            except Exception as e:
                click.echo(f'Failed to create audiobook file: {str(e)}', err=True)

        if productId:
            # TODO: support audiobook downloads from web
            return outputFilePath

    return None
