import json
import os
import platform
from typing import List, TextIO, Tuple, Union, Generator

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

    return formatStr.format_map(
        {
            **bookMetadata,
            'Author': author,
            'Title': title,
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

# Wishlist item response example
# {'DateAdded': '2020-05-12T00:51:32.8860172Z', 'CrossRevisionId': '4dc63ad1-0b4d-3e52-a8bb-704e632963e8', 'IsPurchaseable': True, 'IsSupportedOnCurrentPlatform': True, 'ProductMetadata': {'Book': {'Contributors': 'Mohsin Hamid', 'WorkId': '75952d21-3893-40a6-a6a2-088ae9337c8a', 'Subtitle': 'A Novel', 'IsFree': False, 'ISBN': '9780735212183', 'PublicationDate': '2017-03-07T00:00:00.0000000Z', 'ExternalIds': ['od_2814358'], 'ContributorRoles': [{'Name': 'Mohsin Hamid', 'Role': 'Author'}], 'IsInternetArchive': False, 'IsRecommendation': False, 'CrossRevisionId': '4dc63ad1-0b4d-3e52-a8bb-704e632963e8', 'Title': 'Exit West', 'Description': '<p>**One of <em>The New York Times</em>’s 100 Best Books of the 21st Century</p><p>FINALIST FOR THE BOOKER PRIZE & WINNER OF THE <em>L.A. TIMES</em> BOOK PRIZE FOR FICTION and THE ASPEN WORDS LITERARY PRIZE**</p><p><strong>“It was as if Hamid knew what was going to happen to America and the world, and gave us a road map to our future… At once terrifying and … oddly hopeful.” —Ayelet Waldman, <em>The New York Times Book Review</em></strong></p><p><strong>“Moving, audacious, and indelibly hu...', 'Language': 'en', 'Locale': {'LanguageCode': 'eng', 'ScriptCode': '', 'CountryCode': ''}, 'ImageId': '573021a8-715d-465a-890f-b24207ab06c1', 'PublisherName': 'Penguin Publishing Group', 'Rating': 4.047826, 'TotalRating': 230, 'RatingHistogram': {'1': 5, '2': 10, '3': 41, '4': 87, '5': 0}, 'Slug': 'exit-west', 'IsContentSharingEnabled': True, 'RedirectPreviewUrls': [{'DrmType': 'None', 'Format': 'EPUB3_SAMPLE', 'Url': 'https://storedownloads.kobo.com/download?downloadToken=eyJ0eXAiOjIsInZlciI6bnVsbCwicHR5cCI6IlByZXZpZXdEb3dubG9hZFRva2VuIn0.cWoOja1aXK_bQjhEf72K0w.iEKSnYBwnUrYuNfhuMBUHMoAzbeXVrLetDoYjZ-9X9iWeePtNPb3J8Qwr4677v-BaUC6jb9RuBIVqb5eEb-fvB7ATEVKYUw-eRUVK0PzRtW323wKWN_VVRbyhzhnXmPcwZytK6V3MwI4DRkY7nD6IOdVZaZxfbkutyykmBY2fOYTGMke0UioXu4tYrTM65G6N2cw15UTDg8-7i0_WRlrNRAOCf8R4cRmvblfySKmZWT7V2grysKnMNPginyNX2YSkgCRfLVZgSwxOrtqiBi8ukUNjFJj4OSU6RvOwSPvu_R37cDnEW8Vft6tilrgc10nhXRKgUllGP8kN9DJXX6UbvhOKlrKCKzHJnkn4G272PQLFymSPSS_2frfbszEq_DuPiB-vNZgsgfP0B9ylHMx_oN497GSYfp8Kg9fiv8A9KZBz3DAU6r6Lgji5U5U0Dr0y4WBQ8hz2dVzKDTffwKkXDJFpbmd495Bb57BUf0JtsWt19n0aRALYJcjEQ3zKREpgKqLcHX4SpmBqrv1PkPr8tNwi-CINd1JXyll9SwSjmhfmHVcq7Lykgz4WCQ1oGwjGup3nEzHwpFwPq3RITFCZkUy41mc0QqZZ83PpWA3dqSNK-nsp5uZ84gw024C0CuUUq0GmefN3YD73fxBT2ASrA', 'Platform': 'Generic', 'Size': 742692}], 'HasPreview': True, 'Price': {'Currency': 'USD', 'Price': 13.99}, 'PromoCodeAllowed': False, 'EligibleForKoboLoveDiscount': False, 'IsPreOrder': False, 'RelatedGroupId': '180cc678-2429-c8da-0000-000000000000', 'AgeVerificationRequired': False, 'AccessibilityDetails': {'IsFixedLayout': False, 'IsTextToSpeechAllowed': False}, 'Id': 'ba03ec06-e024-46bb-b7fb-56b20c04f598'}}}
def GetWishList(users: List[User]) -> List[Book]:
    for user in users:
        kobo = Kobo(user)
        kobo.LoadInitializationSettings()
        wishList = kobo.GetMyWishList()
        for item in wishList:
            yield Book(
                RevisionId=item['CrossRevisionId'],
                Title=item['ProductMetadata']['Book']['Title'],
                Author=item['ProductMetadata']['Book']['Contributors'],
                Archived=False,
                Audiobook=False,
                Owner=user,
                Price=f"{item['ProductMetadata']['Book']['Price']['Price']} {item['ProductMetadata']['Book']['Price']['Currency']}",
            )


def Login(user: User) -> None:
    '''perform device initialization and get token'''
    kobo = Kobo(user)
    kobo.AuthenticateDevice()
    kobo.LoadInitializationSettings()
    kobo.Login()


def InitiateLogin(user: User) -> Tuple[str, str]:
    """Start the login process and return activation details"""
    kobo = Kobo(user)
    return kobo._Kobo__ActivateOnWeb()


def CheckActivation(user: User, check_url: str) -> bool:
    """Check if activation is complete and setup user if so"""
    kobo = Kobo(user)
    try:
        email, user_id, user_key = kobo._Kobo__CheckActivation(check_url)
        user.Email = email
        user.UserId = user_id
        kobo.AuthenticateDevice(user_key)
        kobo.LoadInitializationSettings()
        return True
    except Exception:
        return False


def GetBookOrBooks(
    user: User,
    outputPath: str,
    formatStr: str = r'{Author} - {Title} {ShortRevisionId}',
    productId: str = '',
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

        fileName = __MakeFileNameForBook(bookMetadata, formatStr)
        if book_type == BookType.EBOOK:
            # Audiobooks go in sub-directories
            # but epub files go directly in outputPath
            fileName += '.epub'
        outputFilePath = os.path.join(outputPath, fileName)

        if not productId and os.path.exists(outputFilePath):
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

        if productId:
            # TODO: support audiobook downloads from web
            return outputFilePath

    return None
