package config

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

type User struct {
	Email        string `json:"Email"`
	DeviceId     string `json:"DeviceId"`
	SerialNumber string `json:"SerialNumber"`
	AccessToken  string `json:"AccessToken"`
	RefreshToken string `json:"RefreshToken"`
	UserId       string `json:"UserId"`
	UserKey      string `json:"UserKey"`
}

func (u *User) IsAuthenticated() bool {
	return u.AccessToken != "" && u.RefreshToken != "" && u.UserId != ""
}

// DisplayName returns the email or userId as a fallback identifier.
func (u *User) DisplayName() string {
	if u.Email != "" {
		return u.Email
	}
	return u.UserId
}

type UserList struct {
	Users []*User `json:"users"`
}

// Get returns the user matching email or userId (case-insensitive prefix ok for userId).
func (ul *UserList) Get(key string) *User {
	lower := strings.ToLower(key)
	for _, u := range ul.Users {
		if strings.EqualFold(u.Email, key) || strings.HasPrefix(strings.ToLower(u.UserId), lower) {
			return u
		}
	}
	return nil
}

func (ul *UserList) Remove(u *User) {
	out := ul.Users[:0]
	for _, v := range ul.Users {
		if v != u {
			out = append(out, v)
		}
	}
	ul.Users = out
}

type Store struct {
	path     string
	UserList UserList
}

func DefaultPath() (string, error) {
	base := os.Getenv("XDG_CONFIG_HOME")
	if base == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return "", err
		}
		base = filepath.Join(home, ".config")
	}
	return filepath.Join(base, "kobodl.json"), nil
}

func Load(path string) (*Store, error) {
	s := &Store{path: path}
	data, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return s, nil
	}
	if err != nil {
		return nil, fmt.Errorf("reading config %s: %w", path, err)
	}
	if err := json.Unmarshal(data, &s.UserList); err != nil {
		return nil, fmt.Errorf("parsing config %s: %w", path, err)
	}
	return s, nil
}

func (s *Store) Save() error {
	data, err := json.MarshalIndent(s.UserList, "", "    ")
	if err != nil {
		return err
	}
	dir := filepath.Dir(s.path)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return err
	}
	tmp := s.path + ".tmp"
	if err := os.WriteFile(tmp, data, 0o600); err != nil {
		return err
	}
	return os.Rename(tmp, s.path)
}

func (s *Store) Path() string { return s.path }
