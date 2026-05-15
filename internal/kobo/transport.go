package kobo

import (
	"fmt"
	"net/http"
	"sync"
)

// authTransport injects the bearer token and retries once on 401 by refreshing.
// It also sets the Kobo User-Agent on every request.
type authTransport struct {
	base      http.RoundTripper
	getToken  func() string
	refresh   func() error
	userAgent string
	mu        sync.Mutex
}

func (t *authTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	// Clone to avoid mutating the caller's request.
	r := req.Clone(req.Context())
	r.Header.Set("User-Agent", t.userAgent)
	if tok := t.getToken(); tok != "" {
		r.Header.Set("Authorization", "Bearer "+tok)
	}

	resp, err := t.base.RoundTrip(r)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode != http.StatusUnauthorized {
		return resp, nil
	}

	// Drain and close the 401 body before retrying.
	resp.Body.Close()

	// Serialize refresh so concurrent requests don't all race to refresh.
	t.mu.Lock()
	refreshErr := t.refresh()
	t.mu.Unlock()
	if refreshErr != nil {
		return nil, fmt.Errorf("token refresh failed: %w", refreshErr)
	}

	// Retry with the new token — no second retry on another 401.
	r2 := req.Clone(req.Context())
	r2.Header.Set("User-Agent", t.userAgent)
	r2.Header.Set("Authorization", "Bearer "+t.getToken())
	return t.base.RoundTrip(r2)
}
