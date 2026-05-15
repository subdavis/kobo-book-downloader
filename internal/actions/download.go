package actions

import (
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"

	"github.com/subdavis/kobo-book-downloader/internal/config"
	"github.com/subdavis/kobo-book-downloader/internal/kobo"
)

const defaultFormat = "{Author} - {Title} {ShortRevisionId}"

// DownloadResult is returned by GetBookOrBooks for a single-book request.
type DownloadResult struct {
	Path string
}

// GetBookOrBooks downloads one book (by productId) or all books in the library.
// When productId is empty, all eligible books are downloaded.
// Returns the output path when productId is specified; otherwise returns ("", nil).
func GetBookOrBooks(
	u *config.User,
	store *config.Store,
	outputDir string,
	fmtStr string,
	productId string,
	progressFn func(msg string),
) (string, error) {
	if fmtStr == "" {
		fmtStr = defaultFormat
	}
	if progressFn == nil {
		progressFn = func(string) {
			// no-op: caller does not want progress messages
		}
	}

	outputDir, err := filepath.Abs(outputDir)
	if err != nil {
		return "", err
	}
	if err := os.MkdirAll(outputDir, 0o755); err != nil {
		return "", err
	}

	client := kobo.New(u, store)
	if err := client.LoadResources(); err != nil {
		return "", err
	}

	entries, err := client.GetLibrary()
	if err != nil {
		return "", err
	}

	// Sort for deterministic output order.
	sort.Slice(entries, func(i, j int) bool {
		mi := entryMeta(&entries[i])
		mj := entryMeta(&entries[j])
		if mi == nil || mj == nil {
			return false
		}
		return mi.Title < mj.Title
	})

	for i := range entries {
		path, done, err := tryDownload(client, &entries[i], outputDir, fmtStr, productId, progressFn)
		if err != nil {
			return "", err
		}
		if done {
			return path, nil
		}
	}

	if productId != "" {
		return "", fmt.Errorf("product %q not found in library", productId)
	}
	return "", nil
}

func downloadOne(
	client *kobo.Client,
	e *kobo.LibraryEntitlement,
	outputDir, fmtStr, productId string,
	progressFn func(string),
) (string, error) {
	ne := e.NewEntitlement
	if ne == nil {
		return "", nil
	}

	if isSkippable(ne) {
		return "", nil
	}

	var meta *kobo.BookMetadata
	audiobook := false
	switch {
	case ne.BookMetadata != nil:
		meta = ne.BookMetadata
	case ne.AudiobookMetadata != nil:
		meta = ne.AudiobookMetadata
		audiobook = true
	default:
		return "", nil
	}

	currentId := meta.ProductId()
	if productId != "" && productId != currentId {
		return "", nil
	}

	if isArchived(ne) {
		progressFn(fmt.Sprintf("skipping archived book: %s", meta.Title))
		return "", nil
	}

	filename := FormatFilename(meta, fmtStr)
	var outputPath string
	if audiobook {
		outputPath = filepath.Join(outputDir, filename)
	} else {
		outputPath = filepath.Join(outputDir, filename+".epub")
	}

	// When downloading all, skip already-existing files.
	if productId == "" {
		if _, err := os.Stat(outputPath); err == nil {
			progressFn(fmt.Sprintf("skipping already downloaded: %s", outputPath))
			return "", nil
		}
	}

	if err := os.MkdirAll(filepath.Dir(outputPath), 0o755); err != nil {
		return "", err
	}

	progressFn(fmt.Sprintf("downloading %s → %s", currentId, outputPath))

	err := client.DownloadBook(meta, audiobook, outputPath)
	if errors.Is(err, kobo.ErrAdobeDRM) {
		// Already saved as .ade and warned; not fatal for bulk download.
		return "", nil
	}
	if err != nil {
		return "", err
	}
	return outputPath, nil
}

// InitiateLogin sets up the device and starts the web activation flow.
// Returns (pollURL, activationCode, error).
func InitiateLogin(u *config.User, store *config.Store) (string, string, error) {
	client := kobo.New(u, store)
	if err := client.AuthenticateDevice(""); err != nil {
		return "", "", fmt.Errorf("device auth: %w", err)
	}
	if err := client.LoadResources(); err != nil {
		return "", "", fmt.Errorf("load resources: %w", err)
	}
	pollURL, code, err := client.ActivateOnWeb()
	return pollURL, code, err
}

// CheckActivation polls once and, on success, completes device auth and saves the user.
func CheckActivation(u *config.User, store *config.Store, pollURL string) (bool, error) {
	client := kobo.New(u, store)
	email, userId, userKey, err := client.CheckActivation(pollURL)
	if errors.Is(err, kobo.ErrActivationFailed) {
		return false, nil
	}
	if err != nil {
		return false, err
	}

	u.Email = email
	u.UserId = userId
	return true, client.AuthenticateDevice(userKey)
}

// CLILogin runs the full blocking login flow suitable for the CLI.
func CLILogin(u *config.User, store *config.Store, out io.Writer) error {
	client := kobo.New(u, store)
	if err := client.AuthenticateDevice(""); err != nil {
		return err
	}
	if err := client.LoadResources(); err != nil {
		return err
	}
	return client.Login(func(msg string) {
		fmt.Fprintln(out, msg)
	})
}

// helpers

// tryDownload calls downloadOne and handles the skip-on-error-for-bulk logic.
// Returns (path, done, err): done is true when the target book was found.
func tryDownload(
	client *kobo.Client,
	e *kobo.LibraryEntitlement,
	outputDir, fmtStr, productId string,
	progressFn func(string),
) (string, bool, error) {
	path, err := downloadOne(client, e, outputDir, fmtStr, productId, progressFn)
	if err != nil {
		if productId != "" {
			return "", false, err
		}
		progressFn(fmt.Sprintf("skipping %s: %v", entryTitle(e), err))
		return "", false, nil
	}
	return path, path != "" && productId != "", nil
}

// isSkippable reports whether a library entry should be silently skipped.
func isSkippable(ne *kobo.NewEntitlement) bool {
	if ne.BookSubscription != nil {
		return true
	}
	return ne.BookEntitlement != nil && (ne.BookEntitlement.Accessibility == "Preview" || ne.BookEntitlement.IsLocked)
}

func entryMeta(e *kobo.LibraryEntitlement) *kobo.BookMetadata {
	if e.NewEntitlement == nil {
		return nil
	}
	if e.NewEntitlement.BookMetadata != nil {
		return e.NewEntitlement.BookMetadata
	}
	return e.NewEntitlement.AudiobookMetadata
}

func entryTitle(e *kobo.LibraryEntitlement) string {
	m := entryMeta(e)
	if m == nil {
		return "(unknown)"
	}
	return m.Title
}
