package kobo

import (
	"encoding/json"
	"io"
	"net/http"
)

func newGetRequest(url string) (*http.Request, error) {
	return http.NewRequest(http.MethodGet, url, nil)
}

func decodeJSON(r io.Reader, out any) error {
	return json.NewDecoder(r).Decode(out)
}
