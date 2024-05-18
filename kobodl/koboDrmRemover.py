import base64
import binascii
import hashlib
import zipfile
from typing import Dict

from Crypto.Cipher import AES
from Crypto.Util import Padding


# Based on obok.py by Physisticated.
class KoboDrmRemover:
    def __init__(self, deviceId: str, userId: str):
        self.DeviceIdUserIdKey = KoboDrmRemover.__MakeDeviceIdUserIdKey(deviceId, userId)

    @staticmethod
    def __MakeDeviceIdUserIdKey(deviceId: str, userId: str) -> bytes:
        deviceIdUserId = (deviceId + userId).encode()
        key = hashlib.sha256(deviceIdUserId).hexdigest()
        return binascii.a2b_hex(key[32:])

    def __DecryptContents(self, contents: bytes, contentKeyBase64: str) -> bytes:
        contentKey = base64.b64decode(contentKeyBase64)
        keyAes = AES.new(self.DeviceIdUserIdKey, AES.MODE_ECB)
        decryptedContentKey = keyAes.decrypt(contentKey)

        contentAes = AES.new(decryptedContentKey, AES.MODE_ECB)
        decryptedContents = contentAes.decrypt(contents)
        return Padding.unpad(decryptedContents, AES.block_size, "pkcs7")

    def RemoveDrm(self, inputPath: str, outputPath: str, contentKeys: Dict[str, str]) -> None:
        with zipfile.ZipFile(inputPath, "r") as inputZip:
            with zipfile.ZipFile(outputPath, "w", zipfile.ZIP_DEFLATED) as outputZip:
                for filename in inputZip.namelist():
                    contents = inputZip.read(filename)
                    contentKeyBase64 = contentKeys.get(filename, None)
                    if contentKeyBase64 is not None:
                        contents = self.__DecryptContents(contents, contentKeyBase64)
                    if filename == "mimetype":
                        outputZip.writestr(filename, contents, compress_type=zipfile.ZIP_STORED)
                    else:
                        outputZip.writestr(filename, contents)
