package actions

import (
	"runtime"
	"strings"
	"unicode"

	"github.com/subdavis/kobo-book-downloader/internal/kobo"
)

// Book is a parsed, display-ready representation of a library entry.
type Book struct {
	RevisionId string
	Title      string
	Author     string
	Archived   bool
	Audiobook  bool
	Price      string // non-empty only for wishlist items
}

// FormatFilename builds a file/directory name from a format string.
// Supported placeholders: {Author}, {Title}, {RevisionId}, {ShortRevisionId}.
func FormatFilename(meta *kobo.BookMetadata, fmtStr string) string {
	author := sanitize(bookAuthor(meta))
	title := sanitize(meta.Title)
	revId := meta.ProductId()
	shortId := revId
	if len(shortId) > 8 {
		shortId = shortId[:8]
	}

	r := strings.NewReplacer(
		"{Author}", author,
		"{Title}", title,
		"{RevisionId}", revId,
		"{ShortRevisionId}", shortId,
	)
	return r.Replace(fmtStr)
}

// bookAuthor returns the best author string for a book's metadata.
// Prefers contributors with Role=="Author"; falls back to first contributor.
func bookAuthor(meta *kobo.BookMetadata) string {
	var authors []string
	for _, c := range meta.ContributorRoles {
		if c.Role == "Author" {
			authors = append(authors, c.Name)
		}
	}
	if len(authors) == 0 && len(meta.ContributorRoles) > 0 {
		authors = []string{meta.ContributorRoles[0].Name}
	}
	return strings.Join(authors, " & ")
}

// sanitize removes filesystem-unsafe characters and trims whitespace/dots.
func sanitize(s string) string {
	var b strings.Builder
	for _, r := range s {
		if unicode.IsLetter(r) || unicode.IsDigit(r) || strings.ContainsRune(" ,;.!(){}[]#$'-+@_", r) {
			b.WriteRune(r)
		}
	}
	result := strings.Trim(b.String(), " .")
	if runtime.GOOS == "windows" && len(result) > 100 {
		result = result[:100]
	}
	return result
}
