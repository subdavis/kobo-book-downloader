package drm

import (
	"archive/zip"
	"bytes"
	"crypto/aes"
	"encoding/base64"
	"os"
	"testing"
)

func TestRoundTrip(t *testing.T) {
	deviceId := "aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899"
	userId := "test-user-id-1234"
	plaintext := []byte("Hello, Kobo DRM world! This is test content for the round trip test!!")

	// 1. Derive the key the same way the code does.
	deviceKey, err := deriveDeviceKey(deviceId, userId)
	if err != nil {
		t.Fatalf("deriveDeviceKey: %v", err)
	}

	// 2. Generate a random content key (16 bytes, valid AES-128 key).
	contentKey := make([]byte, aes.BlockSize)
	copy(contentKey, []byte("testcontentkey12")) // deterministic for testing

	// 3. PKCS7-pad the plaintext to a block boundary.
	padded := pkcs7Pad(plaintext, aes.BlockSize)

	// 4. Encrypt the content with the content key (ECB).
	encryptedContent, err := ecbEncrypt(contentKey, padded)
	if err != nil {
		t.Fatalf("ecbEncrypt content: %v", err)
	}

	// 5. Encrypt the content key with the device key (ECB).
	encryptedKey, err := ecbEncrypt(deviceKey, contentKey)
	if err != nil {
		t.Fatalf("ecbEncrypt key: %v", err)
	}
	contentKeyB64 := base64.StdEncoding.EncodeToString(encryptedKey)

	// 6. Build an in-memory EPUB zip with one encrypted entry and one plain entry.
	var buf bytes.Buffer
	zw := zip.NewWriter(&buf)

	// mimetype: unencrypted, stored (EPUB spec).
	mimeEntry, _ := zw.CreateHeader(&zip.FileHeader{Name: "mimetype", Method: zip.Store})
	mimeEntry.Write([]byte("application/epub+zip"))

	// chapter.html: encrypted.
	chEntry, _ := zw.Create("chapter.html")
	chEntry.Write(encryptedContent)

	zw.Close()

	// 7. Write the fake EPUB to a temp file.
	inFile, err := os.CreateTemp("", "kobodl-test-in-*.epub")
	if err != nil {
		t.Fatal(err)
	}
	inFile.Write(buf.Bytes())
	inFile.Close()
	defer os.Remove(inFile.Name())

	outFile, err := os.CreateTemp("", "kobodl-test-out-*.epub")
	if err != nil {
		t.Fatal(err)
	}
	outFile.Close()
	defer os.Remove(outFile.Name())

	// 8. Run RemoveDRM.
	keys := map[string]string{"chapter.html": contentKeyB64}
	if err := RemoveDRM(inFile.Name(), outFile.Name(), keys, deviceId, userId); err != nil {
		t.Fatalf("RemoveDRM: %v", err)
	}

	// 9. Open the output and verify content.
	verifyOutput(t, outFile.Name(), plaintext)
}

func verifyOutput(t *testing.T, path string, plaintext []byte) {
	t.Helper()
	r, err := zip.OpenReader(path)
	if err != nil {
		t.Fatalf("open output: %v", err)
	}
	defer r.Close()

	for _, f := range r.File {
		if f.Name == "mimetype" {
			if f.Method != zip.Store {
				t.Errorf("mimetype should be stored (uncompressed), got method %d", f.Method)
			}
		}
		if f.Name == "chapter.html" {
			rc, _ := f.Open()
			got, _ := readAll(rc)
			rc.Close()
			if !bytes.Equal(got, plaintext) {
				t.Errorf("decrypted content mismatch:\n got: %q\nwant: %q", got, plaintext)
			}
		}
	}
}

// ecbEncrypt is the inverse of ecbDecrypt, used only in tests.
func ecbEncrypt(key, data []byte) ([]byte, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	out := make([]byte, len(data))
	for i := 0; i < len(data); i += aes.BlockSize {
		block.Encrypt(out[i:], data[i:])
	}
	return out, nil
}

func pkcs7Pad(data []byte, blockSize int) []byte {
	pad := blockSize - len(data)%blockSize
	padding := bytes.Repeat([]byte{byte(pad)}, pad)
	return append(data, padding...)
}

func readAll(r interface{ Read([]byte) (int, error) }) ([]byte, error) {
	var buf bytes.Buffer
	b := make([]byte, 512)
	for {
		n, err := r.Read(b)
		buf.Write(b[:n])
		if err != nil {
			break
		}
	}
	return buf.Bytes(), nil
}
