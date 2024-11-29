import base64
import dataclasses
import html
import os
import re
import sys
import time
import gzip
import urllib
import json
import copy
import http.cookiejar
from http.cookies import SimpleCookie
import uuid
from enum import Enum
from shutil import copyfile
from typing import Dict, Tuple

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

class Request:
    def __init__(self, url, data=None, headers=None, hooks=None):
        print(f"Making request to {url}")
        self.retries = 0
        self.max_retries = 10
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookie_jar))
        self.request = urllib.request.Request(url, data=data, headers=headers)
        self.hooks = hooks
        self.response = None
        self._copy = None

    def copy_http_response(self, original_response):
        content = original_response.read()

        new_content = content

        new_response = {
            'status': original_response.status,
            'reason': original_response.reason,
            'headers': copy.deepcopy(original_response.headers),
            'version': original_response.version,
            'msg': original_response.msg,
            'content': new_content,
            'request': original_response.request
        }

        return new_response

    def make_request(self):
        try:
            self.response = self.opener.open(self.request)
            self.response.request = self
            # Call optional hooks
            self._copy = self.copy_http_response(original_response=self.response)
            if self.hooks:
                self.hooks['response'](self._copy)
            return self._copy
        except urllib.error.HTTPError as err:
            err.request = self
            self._copy = self.copy_http_response(original_response=err)
            if self.hooks:
                self.hooks['response'](self._copy)
            if err.status == 403:
                print("403 Error")
                self.retries += 1
                if self.retries < self.max_retries:
                    print(f"Retrying... (Attempt {self.retries})")
                    time.sleep(5)
                    self.make_request()
        return self._copy

class Kobo:
    Affiliate = "Kobo"
    ApplicationVersion = "10.1.4.39810"
    DefaultPlatformId = "00000000-0000-0000-0000-000000004000"
    DisplayProfile = "Android"
    UserAgent = "Mozilla/5.0 (Linux; Android 6.0; Google Nexus 7 2013 Build/MRA58K; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/74.0.3729.186 Safari/537.36 KoboApp/8.40.2.29861 KoboPlatform Id/00000000-0000-0000-0000-000000004000 KoboAffiliate/Kobo KoboBuildFlavor/global"

    def __init__(self, user: User):
        self.InitializationSettings = {}
        self.headers = {
            "User-Agent": Kobo.UserAgent,
            "Accept": "*/*",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Site": "same-origin",
            "Priority": "u=4",
            "TE": "trailers",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
        }
        self.user = user

    # PRIVATE METHODS

    # This could be added to the session but then we would need to add { "Authorization": None } headers to all other
    # functions that doesn't need authorization.
    def __GetHeaderWithAccessToken(self) -> dict:
        authorization = "Bearer " + self.user.AccessToken
        headers = {"Authorization": authorization}
        headers['User-Agent'] = Kobo.UserAgent
        return headers

    def __RefreshAuthentication(self) -> None:
        headers = self.__GetHeaderWithAccessToken()

        postData = {
            "AppVersion": Kobo.ApplicationVersion,
            "ClientKey": base64.b64encode(Kobo.DefaultPlatformId.encode()).decode(),
            "PlatformId": Kobo.DefaultPlatformId,
            "RefreshToken": self.user.RefreshToken,
        }

        postData = urllib.parse.urlencode(postData).encode()

        # The reauthentication hook is intentionally not set.
        request = Request("https://storeapi.kobo.com/v1/auth/refresh", data=postData, headers=headers)
        response = request.make_request()
        jsonResponse = json.loads(response['content'])

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
            debug_data("Response", r)
            if r['status'] != requests.codes.unauthorized:  # 401
                return

            print("Refreshing expired authentication token...", file=sys.stderr)

            prep = r.copy()

            # Refresh the authentication token and use it.
            self.__RefreshAuthentication()
            headers = self.__GetHeaderWithAccessToken()
            prep['headers']["Authorization"] = headers["Authorization"]

            # Resend the failed request.
            prep['request'].hooks = None
            _r = prep['request'].make_request(**kwargs)
            return _r

        return {"response": ReauthenticationHook}

    def __GetExtraLoginParameters(self) -> Tuple[str, str, str, str]:
        signInUrl = self.InitializationSettings["sign_in_page"]

        params = {
            "wsa": Kobo.Affiliate,
            "pwsav": Kobo.ApplicationVersion,
            "pwspid": Kobo.DefaultPlatformId,
            "pwsdid": self.user.DeviceId,
        }

        headers = self.headers
        query_string = urllib.parse.urlencode(params)
        signInUrl += "&" + query_string

        request = Request(url=signInUrl, headers=headers)
        response = request.make_request()

        decoded_response = gzip.decompress(response['content']).decode("utf-8")
        htmlResponse = str(decoded_response)

        authCookie = '; '.join([f'{cookie.name}={cookie.value}' for cookie in response['request'].cookie_jar])

        # The link can be found in the response ('<a class="kobo-link partner-option kobo"') but this will do for now.
        parsed = urllib.parse.urlparse(signInUrl)
        koboSignInUrl = parsed._replace(query=None, path="/ww/en/signin/signin").geturl()

        match = re.search(r"""\?workflowId=([^"]{36})""", htmlResponse)
        if match is None:
            raise KoboException(
                "Can't find the workflow ID in the login form. The page format might have changed."
            )
        workflowId = html.unescape(match.group(1))

        match = re.search(
            r"""<input name="__RequestVerificationToken" type="hidden" value="([^"]+)" />""",
            htmlResponse,
        )
        if match is None:
            raise KoboException(
                "Can't find the request verification token in the login form. The page format might have changed."
            )
        requestVerificationToken = html.unescape(match.group(1))

        return koboSignInUrl, workflowId, requestVerificationToken, authCookie

    def __GetMyBookListPage(self, syncToken: str) -> Tuple[list, str]:
        url = self.InitializationSettings["library_sync"]
        headers = self.__GetHeaderWithAccessToken()
        hooks = self.__GetReauthenticationHook()

        if len(syncToken) > 0:
            headers["x-kobo-synctoken"] = syncToken

        debug_data("GetMyBookListPage")

        request = Request(url, headers=headers, hooks=hooks)
        response = request.make_request()

        bookList = json.loads(response['content'])

        syncToken = ""
        syncResult = response['headers'].get("x-kobo-sync")
        if syncResult == "continue":
            syncToken = response['headers'].get("x-kobo-synctoken", "")

        return bookList, syncToken

    def __GetContentAccessBook(self, productId: str, displayProfile: str) -> dict:
        url = self.InitializationSettings["content_access_book"].replace("{ProductId}", productId)
        params = {"DisplayProfile": displayProfile}
        headers = self.__GetHeaderWithAccessToken()
        hooks = self.__GetReauthenticationHook()

        debug_data("GetContentAccessBook")

        query_string = urllib.parse.urlencode(params)
        url += "?" + query_string

        request = Request(url, headers=headers, hooks=hooks)
        response = request.make_request()
        jsonResponse = json.loads(response['content'])
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
                    return download_url, hasDrm

        message = f"Download URL for supported formats can't be found for product '{productId}'.\n"
        message += "Available formats:"
        for jsonContentUrl in jsonContentUrls:
            message += f'\nDRMType: \'{jsonContentUrl["DRMType"]}\', UrlFormat: \'{jsonContentUrl["UrlFormat"]}\''
        raise KoboException(message)

    def __DownloadToFile(self, url, outputPath: str) -> None:
        request = Request(url, headers=self.headers)
        response = request.make_request()
        byte_string = response['content']
        with open(outputPath, "wb") as f:
            for i in range(0, len(byte_string), 1024 * 256):
                chunk = byte_string[i:i + 1024 * 256]
                f.write(chunk)

    def __DownloadAudiobook(self, url, outputPath: str) -> None:
        request = Request(url)
        response = request.make_request()

        if not os.path.isdir(outputPath):
            os.mkdir(outputPath)
        data = response['content']

        for item in data['Spine']:
            fileNum = int(item['Id']) + 1
            filePath = os.path.join(outputPath, str(fileNum) + '.' + item['FileExtension'])
            request = Request(item['Url'], headers=self.headers)
            response = request.make_request()
            byte_string = response['content']
            with open(filePath, "wb") as f:
                for i in range(0, len(byte_string), 1024 * 256):
                    chunk = byte_string[i:i + 1024 * 256]
                    f.write(chunk)

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
            self.user.DeviceId = str(uuid.uuid4())
            self.user.AccessToken = ""
            self.user.RefreshToken = ""

        postData = {
            "AffiliateName": Kobo.Affiliate,
            "AppVersion": Kobo.ApplicationVersion,
            "ClientKey": base64.b64encode(Kobo.DefaultPlatformId.encode()).decode(),
            "DeviceId": self.user.DeviceId,
            "PlatformId": Kobo.DefaultPlatformId,
        }

        if len(userKey) > 0:
            postData["UserKey"] = userKey

        postData = urllib.parse.urlencode(postData).encode()

        headers = {
            'User-Agent': Kobo.UserAgent
        }

        request = Request(url="https://storeapi.kobo.com/v1/auth/device", headers=headers, data=postData)
        response = request.make_request()

        debug_data("AuthenticateDevice", response['content'])
        jsonResponse = json.loads(response['content'])

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
            request = Request(url, headers=headers, hooks=hooks)
            response = request.make_request()
            wishList = json.loads(response['content'])

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
            request = Request(ebook_url, headers=headers, hooks=hooks)
            response = request.make_request()
        except requests.HTTPError as err:
            request = Request(audiobook_url, headers=headers, hooks=hooks)
            response = request.make_request()
        jsonResponse = json.loads(response['content'])
        return jsonResponse

    def LoadInitializationSettings(self) -> None:
        """
        to be called when authentication has been done
        """
        headers = self.__GetHeaderWithAccessToken()
        hooks = self.__GetReauthenticationHook()
        debug_data("LoadInitializationSettings")

        session_headers = self.headers
        session_headers['Authorization'] = headers['Authorization']

        try:
            request = Request(url="https://storeapi.kobo.com/v1/initialization", headers=session_headers, hooks=hooks)
            response = request.make_request()
            jsonResponse = json.loads(response['content'])
            self.InitializationSettings = jsonResponse["Resources"]
        except requests.HTTPError as err:
            print(response['reason'], response['content'])
            raise err

    def Login(self, email: str, password: str, captcha: str) -> None:
        (
            signInUrl,
            workflowId,
            requestVerificationToken,
            authCookie
        ) = self.__GetExtraLoginParameters()

        postData = {
            "LogInModel.WorkflowId": workflowId,
            "LogInModel.Provider": Kobo.Affiliate,
            "__RequestVerificationToken": requestVerificationToken,
            "LogInModel.UserName": email,
            "LogInModel.Password": password,
            "g-recaptcha-response": captcha,
            "h-captcha-response": captcha,
        }

        postData = urllib.parse.urlencode(postData).encode()

        headers = self.headers
        headers['Cookie'] = authCookie

        request = Request(signInUrl, data=postData, headers=headers)
        response = request.make_request()

        decoded_response = gzip.decompress(response['content']).decode('utf-8')
        htmlResponse = decoded_response

        match = re.search(r"'(kobo://UserAuthenticated\?[^']+)';", htmlResponse)
        if match is None:
            soup = BeautifulSoup(htmlResponse, 'html.parser')
            errors = soup.find(class_='validation-summary-errors') or soup.find(
                class_='field-validation-error'
            )
            if errors:
                raise KoboException('Login Failure! ' + errors.text)
            else:
                with open('loginpage_error.html', 'w') as loginpagefile:
                    loginpagefile.write(htmlResponse)
                raise KoboException(
                    "Authenticated user URL can't be found. The page format might have changed!\n\n"
                    "The bad page has been written to file 'loginpage_error.html'.  \n"
                    "You should open an issue on GitHub and attach this file for help: https://github.com/subdavis/kobo-book-downloader/issues\n"
                    "Please be sure to remove any personally identifying information from the file."
                )

        url = match.group(1)
        parsed = urllib.parse.urlparse(url)
        parsedQueries = urllib.parse.parse_qs(parsed.query)
        self.user.UserId = parsedQueries["userId"][
            0
        ]  # We don't call self.Settings.Save here, AuthenticateDevice will do that if it succeeds.
        userKey = parsedQueries["userKey"][0]

        cookie = SimpleCookie()
        cookie.load(authCookie)

        url = match.group(1)
        parsed = urllib.parse.urlparse(url)
        parsedQueries = urllib.parse.parse_qs(parsed.query)
        self.user.UserId = parsedQueries["userId"][
        0
        ]  # We don't call self.Settings.Save here, AuthenticateDevice will do that if it succeeds.
        userKey = parsedQueries["userKey"][0]
        self.AuthenticateDevice(userKey)
