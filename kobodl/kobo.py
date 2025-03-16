import base64
import dataclasses
import html
import os
import re
import secrets
import string
import sys
import time
import urllib
from enum import Enum
from shutil import copyfile
from typing import Dict, Tuple, Union

import requests
from bs4 import BeautifulSoup
from dataclasses_json import dataclass_json

from kobodl.debug import debug_data
from kobodl.globals import Globals
from kobodl.koboDrmRemover import KoboDrmRemover
from kobodl.settings import User


@dataclass_json
@dataclasses.dataclass
class Book:
    RevisionId: str
    Title: str
    Author: str
    Archived: bool
    Audiobook: bool
    Owner: User


class BookType(Enum):
    EBOOK = 1
    AUDIOBOOK = 2
    SUBSCRIPTION = 3


class NotAuthenticatedException(Exception):
    pass


class KoboException(Exception):
    pass


class Kobo:
    Affiliate = "Kobo"
    ApplicationVersion = "4.38.23171"
    DefaultPlatformId = "00000000-0000-0000-0000-000000000373"
    DisplayProfile = "Android"
    DeviceModel = "Kobo Aura ONE"
    DeviceOs = "3.0.35+"
    DeviceOsVersion = "NA"
    # Use the user agent of the Kobo e-readers
    UserAgent = "Mozilla/5.0 (Linux; U; Android 2.0; en-us;) AppleWebKit/538.1 (KHTML, like Gecko) Version/4.0 Mobile Safari/538.1 (Kobo Touch 0373/4.38.23171)"

    def __init__(self, user: User):
        self.InitializationSettings = {}
        self.Session = requests.session()
        self.Session.headers.update({"User-Agent": Kobo.UserAgent})
        self.user = user

    # PRIVATE METHODS

    # This could be added to the session but then we would need to add { "Authorization": None } headers to all other
    # functions that doesn't need authorization.
    def __GetHeaderWithAccessToken(self) -> dict:
        authorization = "Bearer " + self.user.AccessToken
        headers = {"Authorization": authorization}
        return headers

    def __CheckActivation(self, activationCheckUrl) -> Union[Tuple[str, str, str], None]:
        response = self.Session.get(activationCheckUrl)
        response.raise_for_status()
        jsonResponse = response.json()
        if jsonResponse["Status"] == "Complete":
            return (jsonResponse["UserEmail"], jsonResponse["UserId"], jsonResponse["UserKey"])
        return None

    def __WaitTillActivation(self, activationCheckUrl) -> Tuple[str, str]:
        while True:
            print("Waiting for you to finish the activation...")
            time.sleep(5)
            response = self.__CheckActivation(activationCheckUrl)
            if response:
                return response

    def __ActivateOnWeb(self) -> Tuple[str, str]:
        print("Initiating web-based activation")

        params = {
            "pwspid": Kobo.DefaultPlatformId,
            "wsa": Kobo.Affiliate,
            "pwsdid": self.user.DeviceId,
            "pwsav": Kobo.ApplicationVersion,
            "pwsdm": Kobo.DefaultPlatformId,  # In the Android app this is the device model but Nickel sends the platform ID...
            "pwspos": Kobo.DeviceOs,
            "pwspov": Kobo.DeviceOsVersion,
        }

        response = self.Session.get("https://auth.kobobooks.com/ActivateOnWeb", params=params)
        response.raise_for_status()
        htmlResponse = response.text

        match = re.search('data-poll-endpoint="([^"]+)"', htmlResponse)
        if match is None:
            raise KoboException(
                "Can't find the activation poll endpoint in the response. The page format might have changed."
            )
        activationCheckUrl = "https://auth.kobobooks.com" + html.unescape(match.group(1))

        match = re.search(r"""qrcodegenerator/generate.+?%26code%3D(\d+)'""", htmlResponse)
        if match is None:
            raise KoboException(
                "Can't find the activation code in the response. The page format might have changed."
            )
        activationCode = match.group(1)

        return activationCheckUrl, activationCode

    def __RefreshAuthentication(self) -> None:
        headers = self.__GetHeaderWithAccessToken()

        postData = {
            "AppVersion": Kobo.ApplicationVersion,
            "ClientKey": base64.b64encode(Kobo.DefaultPlatformId.encode()).decode(),
            "PlatformId": Kobo.DefaultPlatformId,
            "RefreshToken": self.user.RefreshToken,
        }

        # The reauthentication hook is intentionally not set.
        response = self.Session.post(
            "https://storeapi.kobo.com/v1/auth/refresh", json=postData, headers=headers
        )
        debug_data("RefreshAuth", postData, response.text)
        response.raise_for_status()
        jsonResponse = response.json()

        if jsonResponse["TokenType"] != "Bearer":
            raise KoboException(
                "Authentication refresh returned with an unsupported token type: '%s'"
                % jsonResponse["TokenType"]
            )

        self.user.AccessToken = jsonResponse["AccessToken"]
        self.user.RefreshToken = jsonResponse["RefreshToken"]
        if not self.user.AreAuthenticationSettingsSet():
            raise KoboException("Authentication settings are not set after authentication refresh.")

        Globals.Settings.Save()

    # This could be added to the session too. See the comment at GetHeaderWithAccessToken.
    def __GetReauthenticationHook(self) -> dict:
        # The hook's workflow is based on this:
        # https://github.com/requests/toolbelt/blob/master/requests_toolbelt/auth/http_proxy_digest.py
        def ReauthenticationHook(r, *args, **kwargs):
            debug_data("Response", r.text)
            if r.status_code != requests.codes.unauthorized:  # 401
                return

            print("Refreshing expired authentication token...", file=sys.stderr)

            # Consume content and release the original connection to allow our new request to reuse the same one.
            r.content
            r.close()

            prep = r.request.copy()

            # Refresh the authentication token and use it.
            self.__RefreshAuthentication()
            headers = self.__GetHeaderWithAccessToken()
            prep.headers["Authorization"] = headers["Authorization"]

            # Don't retry to reauthenticate this request again.
            prep.deregister_hook("response", ReauthenticationHook)

            # Resend the failed request.
            _r = r.connection.send(prep, **kwargs)
            _r.history.append(r)
            _r.request = prep
            return _r

        return {"response": ReauthenticationHook}

    def __GetMyBookListPage(self, syncToken: str) -> Tuple[list, str]:
        url = self.InitializationSettings["library_sync"]
        headers = self.__GetHeaderWithAccessToken()
        hooks = self.__GetReauthenticationHook()

        if len(syncToken) > 0:
            headers["x-kobo-synctoken"] = syncToken

        debug_data("GetMyBookListPage")
        response = self.Session.get(url, headers=headers, hooks=hooks)
        response.raise_for_status()
        bookList = response.json()

        syncToken = ""
        syncResult = response.headers.get("x-kobo-sync")
        if syncResult == "continue":
            syncToken = response.headers.get("x-kobo-synctoken", "")

        return bookList, syncToken

    def __GetContentAccessBook(self, productId: str, displayProfile: str) -> dict:
        url = self.InitializationSettings["content_access_book"].replace("{ProductId}", productId)
        params = {"DisplayProfile": displayProfile}
        headers = self.__GetHeaderWithAccessToken()
        hooks = self.__GetReauthenticationHook()

        debug_data("GetContentAccessBook")
        response = self.Session.get(url, params=params, headers=headers, hooks=hooks)
        response.raise_for_status()
        jsonResponse = response.json()
        return jsonResponse

    @staticmethod
    def __GetContentKeys(contentAccessBookResponse: dict) -> Dict[str, str]:
        jsonContentKeys = contentAccessBookResponse.get("ContentKeys")
        if jsonContentKeys is None:
            return {}

        contentKeys = {}
        for contentKey in jsonContentKeys:
            contentKeys[contentKey["Name"]] = contentKey["Value"]
        return contentKeys

    @staticmethod
    def __getContentUrls(bookMetadata: dict) -> str:
        keys = bookMetadata.keys()
        jsonContentUrls = None
        if 'ContentUrls' in keys:
            jsonContentUrls = bookMetadata.get("ContentUrls")
        if 'DownloadUrls' in keys:
            jsonContentUrls = bookMetadata.get('DownloadUrls')
        return jsonContentUrls

    def __GetDownloadInfo(
        self, bookMetadata: dict, isAudiobook: bool, displayProfile: str = None
    ) -> Tuple[str, bool]:
        displayProfile = displayProfile or Kobo.DisplayProfile
        productId = Kobo.GetProductId(bookMetadata)

        if not isAudiobook:
            jsonResponse = self.__GetContentAccessBook(productId, displayProfile)
            jsonContentUrls = Kobo.__getContentUrls(jsonResponse)
        else:
            jsonContentUrls = Kobo.__getContentUrls(bookMetadata)

        if jsonContentUrls is None:
            raise KoboException(f"Download URL can't be found for product {productId}.")

        if len(jsonContentUrls) == 0:
            raise KoboException(
                f"Download URL list is empty for product '{productId}'. If this is an archived book then it must be unarchived first on the Kobo website (https://www.kobo.com/help/en-US/article/1799/restoring-deleted-books-or-magazines)."
            )

        for jsonContentUrl in jsonContentUrls:
            drm_keys = ['DrmType', 'DRMType']
            drm_types = ["KDRM", "AdobeDrm"]
            # will be empty (falsey) if the drm listed doesn't match one of the drm_types
            hasDrm = [
                jsonContentUrl.get(key)
                for key in drm_keys
                if (jsonContentUrl.get(key) in drm_types)
            ]

            download_keys = ['DownloadUrl', 'Url']
            for key in download_keys:
                download_url = jsonContentUrl.get(key, None)
                if download_url:
                    parsed = urllib.parse.urlparse( download_url )
                    parsedQueries = urllib.parse.parse_qs( parsed.query )
                    parsedQueries.pop( "b", None ) # https://github.com/TnS-hun/kobo-book-downloader/commit/54a7f464c7fdf552e62c209fb9c3e7e106dabd85
                    download_url = parsed._replace( query = urllib.parse.urlencode( parsedQueries, doseq = True ) ).geturl()
                    return download_url, hasDrm

        message = f"Download URL for supported formats can't be found for product '{productId}'.\n"
        message += "Available formats:"
        for jsonContentUrl in jsonContentUrls:
            message += f'\nDRMType: \'{jsonContentUrl["DRMType"]}\', UrlFormat: \'{jsonContentUrl["UrlFormat"]}\''
        raise KoboException(message)

    def __DownloadToFile(self, url, outputPath: str) -> None:
        response = self.Session.get(url, stream=True)
        response.raise_for_status()
        with open(outputPath, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                f.write(chunk)

    def __DownloadAudiobook(self, url, outputPath: str) -> None:
        response = self.Session.get(url)

        response.raise_for_status()
        if not os.path.isdir(outputPath):
            os.mkdir(outputPath)
        data = response.json()

        for item in data['Spine']:
            fileNum = int(item['Id']) + 1
            response = self.Session.get(item['Url'], stream=True)
            filePath = os.path.join(outputPath, str(fileNum) + '.' + item['FileExtension'])
            with open(filePath, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    f.write(chunk)

    @staticmethod
    def __GenerateRandomHexDigitString(length: int) -> str:
        id = "".join(secrets.choice(string.hexdigits) for _ in range(length))
        return id.lower()

    # PUBLIC METHODS:
    @staticmethod
    def GetProductId(bookMetadata: dict) -> str:
        revisionId = bookMetadata.get('RevisionId')
        Id = bookMetadata.get('Id')
        return revisionId or Id

    # The initial device authentication request for a non-logged in user doesn't require a user key, and the returned
    # user key can't be used for anything.
    def AuthenticateDevice(self, userKey: str = "") -> None:
        if len(self.user.DeviceId) == 0:
            self.user.DeviceId = Kobo.__GenerateRandomHexDigitString(64)
            self.user.SerialNumber = Kobo.__GenerateRandomHexDigitString(32)
            self.user.AccessToken = ""
            self.user.RefreshToken = ""

        postData = {
            "AffiliateName": Kobo.Affiliate,
            "AppVersion": Kobo.ApplicationVersion,
            "ClientKey": base64.b64encode(Kobo.DefaultPlatformId.encode()).decode(),
            "DeviceId": self.user.DeviceId,
            "PlatformId": Kobo.DefaultPlatformId,
            "SerialNumber": self.user.SerialNumber,
        }

        if len(userKey) > 0:
            postData["UserKey"] = userKey

        response = self.Session.post("https://storeapi.kobo.com/v1/auth/device", json=postData)
        debug_data("AuthenticateDevice", response.text)
        response.raise_for_status()
        jsonResponse = response.json()

        if jsonResponse["TokenType"] != "Bearer":
            raise KoboException(
                "Device authentication returned with an unsupported token type: '%s'"
                % jsonResponse["TokenType"]
            )

        self.user.AccessToken = jsonResponse["AccessToken"]
        self.user.RefreshToken = jsonResponse["RefreshToken"]
        if not self.user.AreAuthenticationSettingsSet():
            raise KoboException("Authentication settings are not set after device authentication.")

        if len(userKey) > 0:
            self.user.UserKey = jsonResponse["UserKey"]

        Globals.Settings.Save()

    # Downloading archived books is not possible, the "content_access_book" API endpoint returns with empty ContentKeys
    # and ContentUrls for them.
    def Download(self, bookMetadata: dict, isAudiobook: bool, outputPath: str) -> None:
        downloadUrl, hasDrm = self.__GetDownloadInfo(bookMetadata, isAudiobook)
        revisionId = Kobo.GetProductId(bookMetadata)
        temporaryOutputPath = outputPath + ".downloading"

        try:
            if isAudiobook:
                self.__DownloadAudiobook(downloadUrl, outputPath)
            else:
                self.__DownloadToFile(downloadUrl, temporaryOutputPath)

            if hasDrm:
                if hasDrm[0] == 'AdobeDrm':
                    print(
                        "WARNING: Unable to parse the Adobe Digital Editions DRM. Saving it as an encrypted 'ade' file.",
                        "Try https://github.com/apprenticeharper/DeDRM_tools",
                    )
                    copyfile(temporaryOutputPath, outputPath + ".ade")
                else:
                    contentAccessBook = self.__GetContentAccessBook(revisionId, self.DisplayProfile)
                    contentKeys = Kobo.__GetContentKeys(contentAccessBook)
                    drmRemover = KoboDrmRemover(self.user.DeviceId, self.user.UserId)
                    drmRemover.RemoveDrm(temporaryOutputPath, outputPath, contentKeys)
                os.remove(temporaryOutputPath)
            else:
                if not isAudiobook:
                    os.rename(temporaryOutputPath, outputPath)
        except:
            if os.path.isfile(temporaryOutputPath):
                os.remove(temporaryOutputPath)
            if os.path.isfile(outputPath):
                os.remove(outputPath)

            raise

    # The "library_sync" name and the synchronization tokens make it somewhat suspicious that we should use
    # "library_items" instead to get the My Books list, but "library_items" gives back less info (even with the
    # embed=ProductMetadata query parameter set).
    def GetMyBookList(self) -> list:
        if not self.user.AreAuthenticationSettingsSet():
            raise NotAuthenticatedException(f'User {self.user.Email} is not authenticated')

        fullBookList = []
        syncToken = ""
        while True:
            bookList, syncToken = self.__GetMyBookListPage(syncToken)
            fullBookList += bookList
            if len(syncToken) == 0:
                break

        return fullBookList

    def GetMyWishList(self) -> list:
        items = []
        currentPageIndex = 0

        while True:
            url = self.InitializationSettings["user_wishlist"]
            headers = self.__GetHeaderWithAccessToken()
            hooks = self.__GetReauthenticationHook()

            params = {
                "PageIndex": currentPageIndex,
                "PageSize": 100,  # 100 is the default if PageSize is not specified.
            }

            debug_data("GetMyWishList")
            response = self.Session.get(url, params=params, headers=headers, hooks=hooks)
            response.raise_for_status()
            wishList = response.json()

            items.extend(wishList["Items"])

            currentPageIndex += 1
            if currentPageIndex >= wishList["TotalPageCount"]:
                break

        return items

    def GetBookInfo(self, productId: str) -> dict:
        audiobook_url = self.InitializationSettings["audiobook"].replace("{ProductId}", productId)
        ebook_url = self.InitializationSettings["book"].replace("{ProductId}", productId)
        headers = self.__GetHeaderWithAccessToken()
        hooks = self.__GetReauthenticationHook()
        debug_data("GetBookInfo")
        try:
            response = self.Session.get(ebook_url, headers=headers, hooks=hooks)
            response.raise_for_status()
        except requests.HTTPError as err:
            response = self.Session.get(audiobook_url, headers=headers, hooks=hooks)
            response.raise_for_status()
        jsonResponse = response.json()
        return jsonResponse

    def LoadInitializationSettings(self) -> None:
        """
        to be called when authentication has been done
        """
        headers = self.__GetHeaderWithAccessToken()
        hooks = self.__GetReauthenticationHook()
        debug_data("LoadInitializationSettings")
        response = self.Session.get(
            "https://storeapi.kobo.com/v1/initialization", headers=headers, hooks=hooks
        )
        try:
            response.raise_for_status()
            jsonResponse = response.json()
            self.InitializationSettings = jsonResponse["Resources"]
        except requests.HTTPError as err:
            print(response.reason, response.text)
            raise err

    def Login(self) -> None:
        activationCheckUrl, activationCode = self.__ActivateOnWeb()

        print("")
        print("kobo-book-downloader uses the same web-based activation method to log in as the")
        print("Kobo e-readers. You will have to open the link below in your browser and enter")
        print("the code. You might need to login if kobo.com asks you to.")
        print("")
        print(f"Open https://www.kobo.com/activate and enter {activationCode}.")
        print("")
        print(
            "kobo-book-downloader will wait now and periodically check for the activation to complete."
        )
        print("")

        userEmail, userId, userKey = self.__WaitTillActivation(activationCheckUrl)
        print("")

        # We don't call Settings.Save here, AuthenticateDevice will do that if it succeeds.
        self.user.Email = userEmail
        self.user.UserId = userId
        self.AuthenticateDevice(userKey)
