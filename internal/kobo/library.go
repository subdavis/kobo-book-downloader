package kobo

import (
	"fmt"
	"net/url"
	"strings"
)

// GetLibrary fetches the complete book library, following sync-token pagination.
func (c *Client) GetLibrary() ([]LibraryEntitlement, error) {
	if !c.user.IsAuthenticated() {
		return nil, ErrNotAuthenticated
	}

	var all []LibraryEntitlement
	syncToken := ""
	for {
		page, next, err := c.getLibraryPage(syncToken)
		if err != nil {
			return nil, err
		}
		all = append(all, page...)
		if next == "" {
			break
		}
		syncToken = next
	}
	return all, nil
}

func (c *Client) getLibraryPage(syncToken string) ([]LibraryEntitlement, string, error) {
	endpoint := c.resources.LibrarySync
	if endpoint == "" {
		return nil, "", fmt.Errorf("resources not loaded; call LoadResources first")
	}

	req, err := newGetRequest(endpoint)
	if err != nil {
		return nil, "", err
	}
	if syncToken != "" {
		req.Header.Set("x-kobo-synctoken", syncToken)
	}

	resp, err := c.http.Do(req)
	if err != nil {
		return nil, "", fmt.Errorf("library sync: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, "", fmt.Errorf("library sync: HTTP %d", resp.StatusCode)
	}

	var entries []LibraryEntitlement
	if err := decodeJSON(resp.Body, &entries); err != nil {
		return nil, "", fmt.Errorf("library sync: %w", err)
	}

	next := ""
	if resp.Header.Get("x-kobo-sync") == "continue" {
		next = resp.Header.Get("x-kobo-synctoken")
	}
	return entries, next, nil
}

// GetWishlist fetches all wishlist items, paginating through all pages.
func (c *Client) GetWishlist() ([]WishlistItem, error) {
	if !c.user.IsAuthenticated() {
		return nil, ErrNotAuthenticated
	}
	endpoint := c.resources.UserWishlist
	if endpoint == "" {
		return nil, fmt.Errorf("resources not loaded; call LoadResources first")
	}

	var all []WishlistItem
	page := 0
	for {
		params := url.Values{
			"PageIndex": {fmt.Sprint(page)},
			"PageSize":  {"100"},
		}
		var resp WishlistResponse
		if err := c.getJSON(endpoint, params, &resp); err != nil {
			return nil, fmt.Errorf("wishlist page %d: %w", page, err)
		}
		all = append(all, resp.Items...)
		page++
		if page >= resp.TotalPageCount {
			break
		}
	}
	return all, nil
}

// GetContentAccess fetches content keys and URLs for a product.
func (c *Client) GetContentAccess(productId string) (*ContentAccessResponse, error) {
	endpoint := strings.ReplaceAll(c.resources.ContentAccessBook, "{ProductId}", productId)
	params := url.Values{"DisplayProfile": {displayProfile}}
	var resp ContentAccessResponse
	if err := c.getJSON(endpoint, params, &resp); err != nil {
		return nil, fmt.Errorf("content access for %s: %w", productId, err)
	}
	return &resp, nil
}

// ContentKeys builds a filename→key map from a ContentAccessResponse.
func ContentKeys(access *ContentAccessResponse) map[string]string {
	keys := make(map[string]string, len(access.ContentKeys))
	for _, k := range access.ContentKeys {
		keys[k.Name] = k.Value
	}
	return keys
}
