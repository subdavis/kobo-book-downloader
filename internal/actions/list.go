package actions

import (
	"fmt"

	"github.com/subdavis/kobo-book-downloader/internal/config"
	"github.com/subdavis/kobo-book-downloader/internal/kobo"
)

// ListBooks returns the Book list for the given users.
// If listAll is false, finished books are excluded.
func ListBooks(users []*config.User, store *config.Store, listAll bool) ([]Book, error) {
	var all []Book
	for _, u := range users {
		books, err := listUserBooks(u, store, listAll)
		if err != nil {
			return nil, fmt.Errorf("user %s: %w", u.DisplayName(), err)
		}
		all = append(all, books...)
	}
	return all, nil
}

func listUserBooks(u *config.User, store *config.Store, listAll bool) ([]Book, error) {
	client := kobo.New(u, store)
	if err := client.LoadResources(); err != nil {
		return nil, err
	}

	entries, err := client.GetLibrary()
	if err != nil {
		return nil, err
	}

	var books []Book
	for _, e := range entries {
		book, ok := entitlementToBook(&e, u, listAll)
		if !ok {
			continue
		}
		books = append(books, book)
	}
	return books, nil
}

// entitlementToBook parses one LibraryEntitlement into a Book.
// Returns ok=false for entries that should be skipped.
func entitlementToBook(e *kobo.LibraryEntitlement, owner *config.User, listAll bool) (Book, bool) {
	ne := e.NewEntitlement
	if ne == nil {
		return Book{}, false
	}

	// Skip saved previews and refunded books.
	if ne.BookEntitlement != nil {
		if ne.BookEntitlement.Accessibility == "Preview" {
			return Book{}, false
		}
		if ne.BookEntitlement.IsLocked {
			return Book{}, false
		}
	}

	// Skip finished books unless explicitly requested.
	if !listAll && isFinished(ne) {
		return Book{}, false
	}

	// Determine type and metadata.
	var meta *kobo.BookMetadata
	audiobook := false

	switch {
	case ne.BookMetadata != nil:
		meta = ne.BookMetadata
	case ne.AudiobookMetadata != nil:
		meta = ne.AudiobookMetadata
		audiobook = true
	case ne.BookSubscription != nil:
		return Book{}, false // subscription, skip silently
	default:
		return Book{}, false
	}

	return Book{
		RevisionId: meta.ProductId(),
		Title:      meta.Title,
		Author:     bookAuthor(meta),
		Archived:   isArchived(ne),
		Audiobook:  audiobook,
	}, true
}

func isArchived(ne *kobo.NewEntitlement) bool {
	if ne.BookEntitlement != nil {
		return ne.BookEntitlement.IsRemoved
	}
	if ne.AudiobookEntitlement != nil {
		return ne.AudiobookEntitlement.IsRemoved
	}
	return false
}

func isFinished(ne *kobo.NewEntitlement) bool {
	if ne.ReadingState == nil || ne.ReadingState.StatusInfo == nil {
		return false
	}
	return ne.ReadingState.StatusInfo.Status == "Finished"
}

// GetWishlist returns wishlist Books for the given users.
func GetWishlist(users []*config.User, store *config.Store) ([]Book, error) {
	var all []Book
	for _, u := range users {
		client := kobo.New(u, store)
		if err := client.LoadResources(); err != nil {
			return nil, fmt.Errorf("user %s: %w", u.DisplayName(), err)
		}
		items, err := client.GetWishlist()
		if err != nil {
			return nil, fmt.Errorf("user %s wishlist: %w", u.DisplayName(), err)
		}
		for _, item := range items {
			price := ""
			if item.ProductMetadata.Book.Price != nil {
				p := item.ProductMetadata.Book.Price
				price = fmt.Sprintf("%.2f %s", p.Price, p.Currency)
			}
			all = append(all, Book{
				RevisionId: item.CrossRevisionId,
				Title:      item.ProductMetadata.Book.Title,
				Author:     item.ProductMetadata.Book.Contributors,
				Price:      price,
			})
		}
	}
	return all, nil
}
