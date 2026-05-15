package drm

import (
	"archive/zip"
	"bytes"
	"crypto/aes"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"io"
	"os"
)

// RemoveDRM decrypts a KDRM-protected EPUB at inputPath and writes the plain
// EPUB to outputPath.
//
// keys maps ZIP entry filename → base64-encoded encrypted content key.
// Entries without a key are copied as-is (they're already plaintext).
func RemoveDRM(inputPath, outputPath string, keys map[string]string, deviceId, userId string) error {
	deviceKey, err := deriveDeviceKey(deviceId, userId)
	if err != nil {
		return fmt.Errorf("derive device key: %w", err)
	}

	r, err := zip.OpenReader(inputPath)
	if err != nil {
		return fmt.Errorf("open encrypted epub: %w", err)
	}
	defer r.Close()

	f, err := os.Create(outputPath)
	if err != nil {
		return err
	}
	defer f.Close()

	w := zip.NewWriter(f)
	defer w.Close()

	for _, entry := range r.File {
		if err := processEntry(entry, w, keys, deviceKey); err != nil {
			return fmt.Errorf("processing %s: %w", entry.Name, err)
		}
	}
	return nil
}

func processEntry(entry *zip.File, w *zip.Writer, keys map[string]string, deviceKey []byte) error {
	rc, err := entry.Open()
	if err != nil {
		return err
	}
	defer rc.Close()

	data, err := io.ReadAll(rc)
	if err != nil {
		return err
	}

	if keyB64, ok := keys[entry.Name]; ok {
		data, err = decryptContent(data, keyB64, deviceKey)
		if err != nil {
			return err
		}
	}

	header := entry.FileHeader
	// EPUB spec requires `mimetype` to be the first file and stored uncompressed.
	if entry.Name == "mimetype" {
		header.Method = zip.Store
	} else {
		header.Method = zip.Deflate
	}

	ew, err := w.CreateHeader(&header)
	if err != nil {
		return err
	}
	_, err = ew.Write(data)
	return err
}

// decryptContent decrypts one ZIP entry's bytes using two-layer AES-ECB:
// 1. Decrypt the content key with the device key.
// 2. Decrypt the content with the content key, then remove PKCS7 padding.
func decryptContent(data []byte, contentKeyB64 string, deviceKey []byte) ([]byte, error) {
	encContentKey, err := base64.StdEncoding.DecodeString(contentKeyB64)
	if err != nil {
		return nil, fmt.Errorf("decode content key: %w", err)
	}

	contentKey, err := ecbDecrypt(deviceKey, encContentKey)
	if err != nil {
		return nil, fmt.Errorf("decrypt content key: %w", err)
	}

	plaintext, err := ecbDecrypt(contentKey, data)
	if err != nil {
		return nil, fmt.Errorf("decrypt content: %w", err)
	}

	return pkcs7Unpad(plaintext, aes.BlockSize)
}

// ecbDecrypt decrypts data with key using AES in ECB mode.
// Panics if len(data) is not a multiple of aes.BlockSize.
func ecbDecrypt(key, data []byte) ([]byte, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	if len(data)%aes.BlockSize != 0 {
		return nil, fmt.Errorf("ciphertext length %d is not a multiple of block size", len(data))
	}
	out := make([]byte, len(data))
	for i := 0; i < len(data); i += aes.BlockSize {
		block.Decrypt(out[i:], data[i:])
	}
	return out, nil
}

// deriveDeviceKey builds the 16-byte AES key from deviceId and userId.
// Key = sha256(deviceId + userId) hex string, bytes 32:64 (second half).
func deriveDeviceKey(deviceId, userId string) ([]byte, error) {
	h := sha256.Sum256([]byte(deviceId + userId))
	hexStr := hex.EncodeToString(h[:]) // 64 hex chars
	return hex.DecodeString(hexStr[32:])
}

// pkcs7Unpad removes PKCS7 padding.
func pkcs7Unpad(data []byte, blockSize int) ([]byte, error) {
	if len(data) == 0 {
		return nil, fmt.Errorf("empty data")
	}
	pad := int(data[len(data)-1])
	if pad == 0 || pad > blockSize || pad > len(data) {
		return nil, fmt.Errorf("invalid PKCS7 padding byte %d", pad)
	}
	if !bytes.Equal(data[len(data)-pad:], bytes.Repeat([]byte{byte(pad)}, pad)) {
		return nil, fmt.Errorf("invalid PKCS7 padding")
	}
	return data[:len(data)-pad], nil
}
