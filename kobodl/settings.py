import dataclasses
import os
from typing import List, Union, Dict, Set

from dataclasses_json import dataclass_json


@dataclass_json
@dataclasses.dataclass
class User:
    Email: str = ""
    DeviceId: str = ""
    SerialNumber: str = ""
    AccessToken: str = ""
    RefreshToken: str = ""
    UserId: str = ""
    UserKey: str = ""

    def AreAuthenticationSettingsSet(self) -> bool:
        return len(self.DeviceId) > 0 and len(self.AccessToken) > 0 and len(self.RefreshToken) > 0

    def IsLoggedIn(self) -> bool:
        return len(self.UserId) > 0 and len(self.UserKey) > 0


@dataclass_json
@dataclasses.dataclass
class UserList:
    users: List[User] = dataclasses.field(default_factory=list)

    def getUser(self, identifier: str) -> Union[User, None]:
        for user in self.users:
            if (
                user.Email == identifier
                or user.UserKey == identifier
                or user.DeviceId == identifier
            ):
                return user
        return None

    def removeUser(self, identifier: str) -> Union[User, None]:
        """returns the removed user"""
        user = self.getUser(identifier)
        if user:
            i = self.users.index(user)
            return self.users.pop(i)
        return None


@dataclass_json
@dataclasses.dataclass
class DownloadedBooks:
    books_by_user: Dict[str, Set[str]] = dataclasses.field(default_factory=dict)

    def mark_downloaded(self, user_id: str, product_id: str) -> None:
        if user_id not in self.books_by_user:
            self.books_by_user[user_id] = set()
        self.books_by_user[user_id].add(product_id)

    def is_downloaded(self, user_id: str, product_id: str) -> bool:
        user_downloads = self.books_by_user.get(user_id, set())
        return product_id in user_downloads


class Settings:
    def __init__(self, configpath=None):
        self.SettingsFilePath = configpath or Settings.__GetCacheFilePath()
        self.UserList = self.Load()
        self.DownloadedBooks = self.LoadDownloadedBooks()

    def Load(self) -> UserList:
        if not os.path.isfile(self.SettingsFilePath):
            return UserList()
        with open(self.SettingsFilePath, "r") as f:
            jsonText = f.read()
            return UserList.from_json(jsonText)

    def LoadDownloadedBooks(self) -> DownloadedBooks:
        downloads_path = self._get_downloads_file_path()
        if not os.path.isfile(downloads_path):
            return DownloadedBooks()
        try:
            with open(downloads_path, "r") as f:
                jsonText = f.read()
                return DownloadedBooks.from_json(jsonText)
        except:
            # If file is corrupted or has issues, start fresh
            return DownloadedBooks()

    def Save(self) -> None:
        with open(self.SettingsFilePath, "w") as f:
            f.write(self.UserList.to_json(indent=4))

    def SaveDownloadedBooks(self) -> None:
        downloads_path = self._get_downloads_file_path()
        os.makedirs(os.path.dirname(downloads_path), exist_ok=True)
        with open(downloads_path, "w") as f:
            f.write(self.DownloadedBooks.to_json(indent=4))

    def _get_downloads_file_path(self) -> str:
        # Store the downloads tracking file in the kobo_downloads directory
        download_dir = os.path.join(os.getcwd(), "kobo_downloads")
        # Make sure the directory exists
        os.makedirs(download_dir, exist_ok=True)
        return os.path.join(download_dir, "kobodl_downloads.json")

    @staticmethod
    def __GetCacheFilePath() -> str:
        cacheHome = os.environ.get("XDG_CONFIG_HOME")
        if (cacheHome is None) or (not os.path.isdir(cacheHome)):
            home = os.path.expanduser("~")
            cacheHome = os.path.join(home, ".config")
            if not os.path.isdir(cacheHome):
                cacheHome = home

        return os.path.join(cacheHome, "kobodl.json")
