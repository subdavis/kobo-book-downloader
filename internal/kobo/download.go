package kobo

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"

	"github.com/subdavis/kobo-book-downloader/internal/drm"
)

const downloadChunkSize = 256 * 1024

// DownloadBook downloads a book to outputPath.
// For ebooks, outputPath is the .epub file path.
// For audiobooks, outputPath is the target directory.
func (c *Client) DownloadBook(meta *BookMetadata, isAudiobook bool, outputPath string) error {
	downloadURL, drmType, err := c.resolveDownloadURL(meta, isAudiobook)
	if err != nil {
		return err
	}

	if isAudiobook {
		return c.downloadAudiobook(downloadURL, outputPath)
	}

	// Download to a temp file, then handle DRM, then rename.
	tmp, err := os.CreateTemp(filepath.Dir(outputPath), ".kobodl-*.epub.tmp")
	if err != nil {
		return fmt.Errorf("create temp file: %w", err)
	}
	tmpPath := tmp.Name()
	tmp.Close()

	cleanup := func() {
		os.Remove(tmpPath)
	}

	if err := c.streamToFile(downloadURL, tmpPath); err != nil {
		cleanup()
		return err
	}

	switch drmType {
	case "":
		// No DRM — just rename.
		if err := os.Rename(tmpPath, outputPath); err != nil {
			cleanup()
			return err
		}

	case "AdobeDrm":
		adePath := outputPath + ".ade"
		if err := os.Rename(tmpPath, adePath); err != nil {
			cleanup()
			return err
		}
		fmt.Fprintf(os.Stderr,
			"WARNING: %s uses Adobe DRM and cannot be decrypted.\n"+
				"Saved as %s. Try https://github.com/apprenticeharper/DeDRM_tools\n",
			meta.Title, adePath)
		return ErrAdobeDRM

	default:
		// KDRM: fetch content keys and decrypt.
		access, err := c.GetContentAccess(meta.ProductId())
		if err != nil {
			cleanup()
			return fmt.Errorf("get content access: %w", err)
		}
		keys := ContentKeys(access)
		if err := drm.RemoveDRM(tmpPath, outputPath, keys, c.user.DeviceId, c.user.UserId); err != nil {
			cleanup()
			os.Remove(outputPath)
			return fmt.Errorf("DRM removal: %w", err)
		}
		cleanup()
	}

	return nil
}

func (c *Client) resolveDownloadURL(meta *BookMetadata, isAudiobook bool) (dlURL, drmType string, err error) {
	var contentURLs []ContentURL

	if isAudiobook {
		// Audiobook download URLs come directly in the metadata.
		contentURLs = append(contentURLs, meta.ContentUrls...)
		contentURLs = append(contentURLs, meta.DownloadUrls...)
	} else {
		access, err := c.GetContentAccess(meta.ProductId())
		if err != nil {
			return "", "", err
		}
		contentURLs = append(contentURLs, access.ContentUrls...)
		contentURLs = append(contentURLs, access.DownloadUrls...)
	}

	if contentURLs == nil {
		return "", "", ErrNoDownloadURL
	}
	if len(contentURLs) == 0 {
		return "", "", ErrEmptyDownloadURL
	}

	for _, cu := range contentURLs {
		rawURL := cu.EffectiveURL()
		if rawURL == "" {
			continue
		}
		// Remove the bogus `b` query param for non-S3 URLs.
		if !strings.Contains(rawURL, "amazonaws.com") {
			if cleaned, err := stripQueryParam(rawURL, "b"); err == nil {
				rawURL = cleaned
			}
		}
		return rawURL, cu.EffectiveDRM(), nil
	}

	return "", "", ErrNoDownloadURL
}

func (c *Client) streamToFile(rawURL, destPath string) error {
	req, err := newGetRequest(rawURL)
	if err != nil {
		return err
	}
	addDownloadHeaders(req, rawURL, c.user.AccessToken)

	// Use a UA-only client — download URLs are pre-signed S3 or Kobo CDN URLs.
	// Auth headers are set manually above; we don't want the auth transport to
	// unconditionally inject a bearer token on S3 pre-signed requests.
	resp, err := c.unauthenticatedClient().Do(req)
	if err != nil {
		return fmt.Errorf("download: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("download: HTTP %d from %s", resp.StatusCode, rawURL)
	}

	f, err := os.OpenFile(destPath, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0o644)
	if err != nil {
		return err
	}
	defer f.Close()

	buf := make([]byte, downloadChunkSize)
	_, err = io.CopyBuffer(f, resp.Body, buf)
	return err
}

func (c *Client) downloadAudiobook(spineURL, outputDir string) error {
	req, err := newGetRequest(spineURL)
	if err != nil {
		return err
	}
	addDownloadHeaders(req, spineURL, c.user.AccessToken)

	resp, err := c.unauthenticatedClient().Do(req)
	if err != nil {
		return fmt.Errorf("audiobook spine: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("audiobook spine: HTTP %d", resp.StatusCode)
	}

	var spine AudiobookSpine
	if err := json.NewDecoder(resp.Body).Decode(&spine); err != nil {
		return fmt.Errorf("audiobook spine: %w", err)
	}

	if err := os.MkdirAll(outputDir, 0o755); err != nil {
		return err
	}

	for _, part := range spine.Spine {
		filename := fmt.Sprintf("%d.%s", part.Id+1, part.FileExtension)
		destPath := filepath.Join(outputDir, filename)

		if err := c.streamToFile(part.Url, destPath); err != nil {
			return fmt.Errorf("audiobook part %s: %w", filename, err)
		}
	}
	return nil
}

// addDownloadHeaders sets auth headers appropriate for the download URL target.
func addDownloadHeaders(req *http.Request, rawURL, accessToken string) {
	if strings.Contains(rawURL, "amazonaws.com") {
		req.Header.Set("x-amz-request-payer", "requester")
	} else if strings.Contains(rawURL, "kobo.com") {
		req.Header.Set("Authorization", "Bearer "+accessToken)
	}
}

func stripQueryParam(rawURL, param string) (string, error) {
	u, err := url.Parse(rawURL)
	if err != nil {
		return rawURL, err
	}
	q := u.Query()
	q.Del(param)
	u.RawQuery = q.Encode()
	return u.String(), nil
}
