package kobo

import (
	"net/http"

	"github.com/subdavis/kobo-book-downloader/internal/config"
)

const (
	affiliate          = "Kobo"
	applicationVersion = "4.38.23171"
	defaultPlatformId  = "00000000-0000-0000-0000-000000000373"
	displayProfile     = "Android"
	userAgent          = "Mozilla/5.0 (Linux; U; Android 2.0; en-us;) AppleWebKit/538.1 (KHTML, like Gecko) Version/4.0 Mobile Safari/538.1 (Kobo Touch 0373/4.38.23171)"

	storeBaseURL = "https://storeapi.kobo.com/v1"
	authBaseURL  = "https://auth.kobobooks.com"
)

// Client wraps the Kobo store API for one user account.
type Client struct {
	user      *config.User
	store     *config.Store
	http      *http.Client
	resources InitResources
}

// New creates a Client with a transport that auto-injects and refreshes auth.
func New(user *config.User, store *config.Store) *Client {
	c := &Client{user: user, store: store}

	transport := &authTransport{
		base:      http.DefaultTransport,
		userAgent: userAgent,
		getToken:  func() string { return c.user.AccessToken },
		refresh:   c.RefreshAuth,
	}
	c.http = &http.Client{Transport: transport}
	return c
}

// unauthenticatedClient returns an http.Client with just the User-Agent set
// (no bearer token, no refresh) for requests that don't need auth.
func (c *Client) unauthenticatedClient() *http.Client {
	return &http.Client{
		Transport: &uaTransport{base: http.DefaultTransport, userAgent: userAgent},
	}
}

type uaTransport struct {
	base      http.RoundTripper
	userAgent string
}

func (t *uaTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	r := req.Clone(req.Context())
	r.Header.Set("User-Agent", t.userAgent)
	return t.base.RoundTrip(r)
}
