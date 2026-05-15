package kobo

import (
	"bytes"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"

	"github.com/PuerkitoBio/goquery"
)

// AuthenticateDevice registers the device with Kobo and populates AccessToken/RefreshToken.
// Pass userKey from a completed web activation; omit (empty string) for an anonymous device registration.
func (c *Client) AuthenticateDevice(userKey string) error {
	if c.user.DeviceId == "" {
		c.user.DeviceId = randomHex(64)
		c.user.SerialNumber = randomHex(32)
		c.user.AccessToken = ""
		c.user.RefreshToken = ""
	}

	body := map[string]any{
		"AffiliateName": affiliate,
		"AppVersion":    applicationVersion,
		"ClientKey":     base64.StdEncoding.EncodeToString([]byte(defaultPlatformId)),
		"DeviceId":      c.user.DeviceId,
		"PlatformId":    defaultPlatformId,
		"SerialNumber":  c.user.SerialNumber,
	}
	if userKey != "" {
		body["UserKey"] = userKey
	}

	var resp AuthDeviceResponse
	if err := c.postJSON(storeBaseURL+"/auth/device", body, &resp); err != nil {
		return fmt.Errorf("device auth: %w", err)
	}
	if resp.TokenType != "Bearer" {
		return fmt.Errorf("device auth: unsupported token type %q", resp.TokenType)
	}

	c.user.AccessToken = resp.AccessToken
	c.user.RefreshToken = resp.RefreshToken
	if userKey != "" {
		c.user.UserKey = resp.UserKey
	}
	if !c.user.IsAuthenticated() {
		return fmt.Errorf("device auth: tokens not set after authentication")
	}
	return c.store.Save()
}

// RefreshAuth exchanges the refresh token for a new access token.
func (c *Client) RefreshAuth() error {
	body := map[string]any{
		"AppVersion":   applicationVersion,
		"ClientKey":    base64.StdEncoding.EncodeToString([]byte(defaultPlatformId)),
		"PlatformId":   defaultPlatformId,
		"RefreshToken": c.user.RefreshToken,
	}

	// Use an unauthenticated client here to avoid infinite recursion through the transport.
	var resp AuthDeviceResponse
	if err := c.postJSONWith(c.unauthenticatedClient(), storeBaseURL+"/auth/refresh", body, &resp); err != nil {
		return fmt.Errorf("token refresh: %w", err)
	}
	if resp.TokenType != "Bearer" {
		return fmt.Errorf("token refresh: unsupported token type %q", resp.TokenType)
	}

	c.user.AccessToken = resp.AccessToken
	c.user.RefreshToken = resp.RefreshToken
	return c.store.Save()
}

// LoadResources fetches the initialization endpoint to get resource URLs.
// Must be called after authentication.
func (c *Client) LoadResources() error {
	if !c.user.IsAuthenticated() {
		return ErrNotAuthenticated
	}
	var resp InitResponse
	if err := c.getJSON(storeBaseURL+"/initialization", nil, &resp); err != nil {
		return fmt.Errorf("load resources: %w", err)
	}
	c.resources = resp.Resources
	return nil
}

// ActivateOnWeb starts the web-based activation flow. Returns the poll URL and
// the numeric activation code the user must enter at kobo.com/activate.
func (c *Client) ActivateOnWeb() (pollURL, code string, err error) {
	params := url.Values{
		"pwspid": {defaultPlatformId},
		"wsa":    {affiliate},
		"pwsdid": {c.user.DeviceId},
		"pwsav":  {applicationVersion},
		"pwsdm":  {defaultPlatformId},
		"pwspos": {"3.0.35+"},
		"pwspov": {"NA"},
	}

	endpoint := authBaseURL + "/ActivateOnWeb?" + params.Encode()
	unauthHTTP := c.unauthenticatedClient()
	resp, err := unauthHTTP.Get(endpoint)
	if err != nil {
		return "", "", fmt.Errorf("activate on web: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", "", fmt.Errorf("activate on web: HTTP %d", resp.StatusCode)
	}

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		return "", "", fmt.Errorf("activate on web: parsing HTML: %w", err)
	}

	// data-poll-endpoint attribute contains the relative poll path.
	pollPath, exists := doc.Find("[data-poll-endpoint]").Attr("data-poll-endpoint")
	if !exists {
		return "", "", fmt.Errorf("activate on web: can't find data-poll-endpoint (page format may have changed)")
	}
	pollURL = authBaseURL + pollPath

	// QR code img src contains the activation code as the `code` query param.
	// The src is URL-encoded, e.g. %26code%3D123456
	imgSrc, exists := doc.Find("img[src*='qrcodegenerator']").Attr("src")
	if !exists {
		return "", "", fmt.Errorf("activate on web: can't find QR code img (page format may have changed)")
	}
	// The src may itself be a URL with encoded query params inside it.
	// Decode once to get the inner URL, then parse the code param.
	decoded, _ := url.QueryUnescape(imgSrc)
	u, err := url.Parse(decoded)
	if err != nil {
		return "", "", fmt.Errorf("activate on web: parsing QR URL: %w", err)
	}
	// Try the `code` param first; fall back to scanning for %26code%3D in raw src.
	code = u.Query().Get("code")
	if code == "" {
		// Some variants encode the inner URL's query differently; try splitting on "code="
		if idx := strings.Index(decoded, "code="); idx >= 0 {
			rest := decoded[idx+5:]
			if amp := strings.IndexAny(rest, "&?"); amp >= 0 {
				rest = rest[:amp]
			}
			code = rest
		}
	}
	if code == "" {
		return "", "", fmt.Errorf("activate on web: can't extract activation code (page format may have changed)")
	}

	return pollURL, code, nil
}

// CheckActivation polls the activation endpoint once.
// Returns (email, userId, userKey, nil) on success.
// Returns ("", "", "", ErrActivationFailed) if activation is not yet complete.
func (c *Client) CheckActivation(pollURL string) (email, userId, userKey string, err error) {
	unauthHTTP := c.unauthenticatedClient()
	resp, err := unauthHTTP.Post(pollURL, "application/json", bytes.NewReader([]byte("{}")))
	if err != nil {
		return "", "", "", fmt.Errorf("check activation: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", "", "", fmt.Errorf("check activation: HTTP %d", resp.StatusCode)
	}

	var body ActivationCheckResponse
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return "", "", "", fmt.Errorf("check activation: unexpected response format: %w", err)
	}

	if body.Status != "Complete" {
		return "", "", "", ErrActivationFailed
	}

	u, err := url.Parse(body.RedirectUrl)
	if err != nil {
		return "", "", "", fmt.Errorf("check activation: parsing redirect URL: %w", err)
	}
	q := u.Query()
	return q.Get("email"), q.Get("userId"), q.Get("userKey"), nil
}

// Login drives the full CLI login flow: starts activation, prints instructions,
// polls until the user completes activation in their browser, then authenticates.
func (c *Client) Login(printFn func(string)) error {
	pollURL, code, err := c.ActivateOnWeb()
	if err != nil {
		return err
	}

	printFn(fmt.Sprintf(
		"\nkobodl uses Kobo's web-based activation to log in (same as Kobo e-readers).\n"+
			"Open https://www.kobo.com/activate in your browser and enter: %s\n"+
			"Waiting for activation...\n", code,
	))

	for {
		email, userId, userKey, err := c.CheckActivation(pollURL)
		if err == ErrActivationFailed {
			continue
		}
		if err != nil {
			return err
		}

		c.user.Email = email
		c.user.UserId = userId
		return c.AuthenticateDevice(userKey)
	}
}

// randomHex returns n random lowercase hex characters.
func randomHex(n int) string {
	b := make([]byte, (n+1)/2)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	return fmt.Sprintf("%x", b)[:n]
}

// postJSON sends a JSON POST via the authenticated client.
func (c *Client) postJSON(endpoint string, body any, out any) error {
	return c.postJSONWith(c.http, endpoint, body, out)
}

func (c *Client) postJSONWith(client *http.Client, endpoint string, body any, out any) error {
	data, err := json.Marshal(body)
	if err != nil {
		return err
	}
	resp, err := client.Post(endpoint, "application/json", bytes.NewReader(data))
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("HTTP %d from %s", resp.StatusCode, endpoint)
	}
	return json.NewDecoder(resp.Body).Decode(out)
}

// getJSON sends a GET via the authenticated client.
func (c *Client) getJSON(endpoint string, params url.Values, out any) error {
	u := endpoint
	if len(params) > 0 {
		u += "?" + params.Encode()
	}
	resp, err := c.http.Get(u)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("HTTP %d from %s", resp.StatusCode, endpoint)
	}
	return json.NewDecoder(resp.Body).Decode(out)
}
