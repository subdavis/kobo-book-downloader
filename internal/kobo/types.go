package kobo

// Kobo API response types. Fields use PascalCase to match the wire format directly.

type AuthDeviceResponse struct {
	AccessToken  string `json:"AccessToken"`
	RefreshToken string `json:"RefreshToken"`
	TokenType    string `json:"TokenType"`
	UserKey      string `json:"UserKey"`
}

type InitResources struct {
	LibrarySync       string `json:"library_sync"`
	ContentAccessBook string `json:"content_access_book"`
	Book              string `json:"book"`
	Audiobook         string `json:"audiobook"`
	UserWishlist      string `json:"user_wishlist"`
}

type InitResponse struct {
	Resources InitResources `json:"Resources"`
}

// LibraryEntitlement is one item returned by library_sync.
type LibraryEntitlement struct {
	NewEntitlement *NewEntitlement `json:"NewEntitlement"`
}

type NewEntitlement struct {
	BookEntitlement      *BookEntitlement  `json:"BookEntitlement"`
	AudiobookEntitlement *BookEntitlement  `json:"AudiobookEntitlement"`
	BookMetadata         *BookMetadata     `json:"BookMetadata"`
	AudiobookMetadata    *BookMetadata     `json:"AudiobookMetadata"`
	BookSubscription     *struct{}         `json:"BookSubscriptionEntitlement"`
	ReadingState         *ReadingState     `json:"ReadingState"`
	DownloadUrls         []ContentURL      `json:"DownloadUrls"`
}

type BookEntitlement struct {
	Accessibility string `json:"Accessibility"`
	IsLocked      bool   `json:"IsLocked"`
	IsRemoved     bool   `json:"IsRemoved"`
}

type BookMetadata struct {
	RevisionId       string            `json:"RevisionId"`
	Id               string            `json:"Id"`
	Title            string            `json:"Title"`
	ContributorRoles []ContributorRole `json:"ContributorRoles"`
	ContentUrls      []ContentURL      `json:"ContentUrls"`
	DownloadUrls     []ContentURL      `json:"DownloadUrls"`
}

func (m *BookMetadata) ProductId() string {
	if m.RevisionId != "" {
		return m.RevisionId
	}
	return m.Id
}

type ContributorRole struct {
	Name string `json:"Name"`
	Role string `json:"Role"`
}

type ReadingState struct {
	StatusInfo *StatusInfo `json:"StatusInfo"`
}

type StatusInfo struct {
	Status string `json:"Status"`
}

type ContentURL struct {
	DrmType     string `json:"DrmType"`
	DRMType     string `json:"DRMType"` // alternate casing in some responses
	UrlFormat   string `json:"UrlFormat"`
	DownloadUrl string `json:"DownloadUrl"`
	Url         string `json:"Url"`
}

func (c *ContentURL) EffectiveDRM() string {
	if c.DrmType != "" {
		return c.DrmType
	}
	return c.DRMType
}

func (c *ContentURL) EffectiveURL() string {
	if c.DownloadUrl != "" {
		return c.DownloadUrl
	}
	return c.Url
}

type ContentAccessResponse struct {
	ContentKeys []ContentKey `json:"ContentKeys"`
	ContentUrls []ContentURL `json:"ContentUrls"`
	DownloadUrls []ContentURL `json:"DownloadUrls"`
}

type ContentKey struct {
	Name  string `json:"Name"`
	Value string `json:"Value"`
}

type WishlistResponse struct {
	Items         []WishlistItem `json:"Items"`
	TotalPageCount int           `json:"TotalPageCount"`
}

type WishlistItem struct {
	CrossRevisionId string          `json:"CrossRevisionId"`
	ProductMetadata WishlistProduct `json:"ProductMetadata"`
}

type WishlistProduct struct {
	Book WishlistBook `json:"Book"`
}

type WishlistBook struct {
	Title        string         `json:"Title"`
	Contributors string         `json:"Contributors"`
	Price        *WishlistPrice `json:"Price"`
}

type WishlistPrice struct {
	Price    float64 `json:"Price"`
	Currency string  `json:"Currency"`
}

// AudiobookSpine is the response from the audiobook download URL.
type AudiobookSpine struct {
	Spine []AudiobookPart `json:"Spine"`
}

type AudiobookPart struct {
	Id            int    `json:"Id"`
	Url           string `json:"Url"`
	FileExtension string `json:"FileExtension"`
}

// ActivationCheckResponse is returned by the activation poll endpoint.
type ActivationCheckResponse struct {
	Status      string `json:"Status"`
	RedirectUrl string `json:"RedirectUrl"`
}
