package kobo

import "errors"

var (
	ErrNotAuthenticated = errors.New("user is not authenticated")
	ErrArchived         = errors.New("book is archived and cannot be downloaded")
	ErrAdobeDRM         = errors.New("book uses Adobe DRM which cannot be removed")
	ErrNoDownloadURL    = errors.New("no download URL found for book")
	ErrEmptyDownloadURL = errors.New("download URL list is empty (book may be archived)")
	ErrActivationFailed = errors.New("activation check failed or not yet complete")
)
